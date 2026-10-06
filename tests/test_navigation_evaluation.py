"""Offline contract boundaries with synthetic records, no ROS/model/physics."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from robot_agent import evaluate_navigation as evaluation
from combination.navigation_evaluation_fixture import make_run,write_run


class NavigationEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name);self.data=make_run(self.root)

    def test_complete_goal_preserves_final_pending_and_input_bytes(self):
        original=(self.root/'agent/report.json').read_bytes()
        verdict=evaluation.evaluate_run(self.root)
        self.assertEqual(verdict['verdict'],'succeeded',verdict)
        self.assertEqual(verdict['metrics']['arrival_distance_m'],{'A':0.,'B':0.})
        self.assertEqual(verdict['execution']['operations'][1]['owner_reported_settlement'],'pending')
        self.assertEqual(verdict['execution']['agent_task_verdict'],'unassessed')
        self.assertEqual((self.root/'agent/report.json').read_bytes(),original)

    def test_measured_wrong_endpoint_is_failed(self):
        self.data['physical.jsonl'][2]['xyz_rpy'][0]=-1.
        write_run(self.root,self.data)
        verdict=evaluation.evaluate_run(self.root)
        self.assertEqual(verdict['verdict'],'failed')
        self.assertEqual(verdict['metrics']['arrival_distance_m']['B'],.5)

    def test_arrival_limit_boundary(self):
        self.data['physical.jsonl'][2]['xyz_rpy'][0]=-1.25
        write_run(self.root,self.data)
        self.assertEqual(evaluation.evaluate_run(self.root)['verdict'],'succeeded')
        self.data['physical.jsonl'][2]['xyz_rpy'][0]=-1.249
        write_run(self.root,self.data)
        self.assertEqual(evaluation.evaluate_run(self.root)['verdict'],'failed')

    def test_missing_trace_is_unknown(self):
        (self.root/'caller.jsonl').unlink()
        self.assertEqual(evaluation.evaluate_run(self.root)['verdict'],'unknown')

    def test_controller_semantics_cannot_be_replaced_under_same_profile_id(self):
        self.data['navigation-profile.json']['controller']={'plugin':'other.Controller'}
        write_run(self.root,self.data)
        self.assertEqual(evaluation.evaluate_run(self.root)['verdict'],'unknown')

    def test_jointly_invalid_receipt_enum_and_float_native_status_are_unknown(self):
        original=deepcopy(self.data)
        for field in ('settlement','status'):
            data=deepcopy(original)
            if field=='settlement':
                data['agent/report.json']['operations'][1]['receipt']['settlement']='bogus'
                for row in data['caller.jsonl']:
                    if row['event']=='core_visit_closed' and row['stage']=='B':
                        row['record']['receipt']['settlement']='bogus'
            else:
                for row in data['caller.jsonl']:
                    if row['event'] in ('native_result','arrival'):row['status']=4.0
            with self.subTest(field=field):
                write_run(self.root,data)
                self.assertEqual(evaluation.evaluate_run(self.root)['verdict'],'unknown')

    def test_optional_reference_and_authority_metadata_are_allowed(self):
        for row in self.data['caller.jsonl']:
            if row['event']=='core_admitted':row['record']['observation_reference']['optional_note']='extra'
            if row['event']=='core_visit_closed':row['record']['receipt']['authority']['optional_note']='extra'
        write_run(self.root,self.data)
        self.assertEqual(evaluation.evaluate_run(self.root)['verdict'],'succeeded')

    def test_finite_coordinates_with_overflowing_distance_retain_unknown_cli_report(self):
        self.data['physical.jsonl'][2]['xyz_rpy'][:2]=[sys.float_info.max,sys.float_info.max]
        write_run(self.root,self.data)
        output=self.root/'evaluation.json'
        with patch.object(sys,'argv',['evaluate','--run',str(self.root),'--output',str(output)]),patch('builtins.print'):
            self.assertEqual(evaluation.main(),2)
        self.assertEqual(json.loads(output.read_text())['verdict'],'unknown')

    def test_foreign_ambiguous_late_alignment_and_unreaped_are_unknown(self):
        cases=[('foreign_sample',lambda d:d['physical.jsonl'][1].update(run_id='9'*32)),
            ('duplicate_arrival',lambda d:d['caller.jsonl'].append(deepcopy(next(
                row for row in d['caller.jsonl'] if row['event']=='arrival' and row['stage']=='A')))),
            ('late',lambda d:d['physical.jsonl'][1].update(finished=147.)),
            ('query_too_long',lambda d:d['physical.jsonl'][1].update(started=141.,finished=146.1)),
            ('B_already_reserved',lambda d:d['physical.jsonl'][1].update(started=150.,finished=150.1)),
            ('unknown_transform',lambda d:d['collection-context.json']['alignment'].update(map_to_world_xy_yaw=[1,0,0])),
            ('bad_anchor',lambda d:d['physical.jsonl'][0]['xyz_rpy'].__setitem__(0,-1.)),
            ('mixed_session',lambda d:d['agent/report.json']['operations'][1]['observation_reference'].update(session_id='9'*32)),
            ('goal_mismatch',lambda d:d['physical.jsonl'][1].update(goal_id='9'*32)),
            ('nonfinite',lambda d:d['physical.jsonl'][1]['xyz_rpy'].__setitem__(0,float('nan'))),
            ('unreaped_query',lambda d:d['collection.json']['children'][0].update(reaped=False)),
            ('forced_collector',lambda d:d['collector-process.json'].update(group_forced=True)),
            ('unsupported_profile',lambda d:d['run.json'].update(profile='another-profile'))]
        original=deepcopy(self.data)
        for name,mutate in cases:
            with self.subTest(name=name):
                data=deepcopy(original);mutate(data);write_run(self.root,data)
                self.assertEqual(evaluation.evaluate_run(self.root)['verdict'],'unknown')

    def test_owner_release_fact_is_required_before_B(self):
        for file in ('agent/report.json','caller.jsonl'):
            if file.endswith('jsonl'):
                for row in self.data[file]:
                    if row['event']=='core_visit_closed' and row['stage']=='A':
                        row['record']['receipt']['authority_disposition']='current'
            else:self.data[file]['operations'][0]['receipt']['authority_disposition']='current'
        write_run(self.root,self.data)
        self.assertEqual(evaluation.evaluate_run(self.root)['verdict'],'unknown')

    def test_A_capture_after_B_reservation_is_unknown_even_with_valid_query_window(self):
        self.data['physical.jsonl'][1]['finished']=145.
        for row in self.data['caller.jsonl']:
            if row.get('stage')=='B' and row['event']=='core_admitted':row['steady']=143.5
            if row.get('stage')=='B' and row['event']=='core_native_reserved':row['steady']=144.
        write_run(self.root,self.data)
        verdict=evaluation.evaluate_run(self.root)
        self.assertEqual(verdict['verdict'],'unknown')
        self.assertIn('pre-native-send sample order',verdict['reason'])

    def test_optional_metadata_is_allowed(self):
        for row in self.data['physical.jsonl']:row['optional_note']='extra'
        self.data['collection-context.json']['optional_note']='extra'
        self.data['collection-context.json']['alignment']['spawn']['optional_note']='extra'
        self.data['navigation-profile.json']['controller']['optional_note']='extra'
        self.data['collector-process.json']['optional_number']=float('nan')
        write_run(self.root,self.data)
        self.assertEqual(evaluation.evaluate_run(self.root)['verdict'],'succeeded')

    def test_invalid_required_number_does_not_break_unknown_report_serialization(self):
        self.data['collector-process.json']['returncode']=float('nan')
        write_run(self.root,self.data)
        output=self.root/'evaluation.json'
        with patch.object(sys,'argv',['evaluate','--run',str(self.root),'--output',str(output)]),patch('builtins.print'):
            self.assertEqual(evaluation.main(),2)
        self.assertEqual(json.loads(output.read_text())['verdict'],'unknown')

    def test_existing_output_refused_before_evaluation(self):
        output=self.root/'evaluation.json';output.write_text('retained')
        with patch.object(sys,'argv',['evaluate','--run',str(self.root),'--output',str(output)]),\
                patch.object(evaluation,'evaluate_run') as evaluate, self.assertRaises(SystemExit):
            evaluation.main()
        evaluate.assert_not_called()
        self.assertEqual(output.read_text(),'retained')

    def test_cli_unknown_is_retained_and_exit_two(self):
        (self.root/'caller.jsonl').write_text('{broken')
        output=self.root/'evaluation.json'
        with patch.object(sys,'argv',['evaluate','--run',str(self.root),'--output',str(output)]),patch('builtins.print'):
            self.assertEqual(evaluation.main(),2)
        self.assertEqual(json.loads(output.read_text())['verdict'],'unknown')


if __name__=='__main__':unittest.main()
