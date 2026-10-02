"""Focused independent-input examples for the bounded task predicate."""

import copy
import math
import unittest
import contextlib
import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from robot_agent.evaluate_handoff import evaluate, load_profile


class HandoffPredicateTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile()
        self.frames = [dict(step=i, phase='policy' if i <= 400 else 'hold',
                            sim_seconds=i * .02, action=[0.] * 14,
                            contacts=[['red_box', finger] for finger in self.profile['left_fingers']],
                            relative_position=[.1, 0., 0.], relative_rotation=[1., 0., 0., 0., 1., 0., 0., 0., 1.],
                            table_clearance_m=.1) for i in range(1, 451)]

    def verdict(self, frames=None):
        return evaluate(self.frames if frames is None else frames, self.profile)

    def test_known_stationary_one_second_grasp(self):
        self.frames[-1]['optional_annotation'] = 'does not change semantics'
        for pair in self.frames[-1]['contacts']:
            pair.reverse()
        result = self.verdict()
        self.assertEqual(result['verdict'], 'succeeded')
        self.assertAlmostEqual(result['metrics']['window_sim_seconds'], 1.)

    def test_right_hand_or_table_support_is_failure(self):
        for support in ['vx300s_right/10_left_gripper_finger', 'table']:
            with self.subTest(support=support):
                frames = copy.deepcopy(self.frames)
                frames[425]['contacts'].append([support, 'red_box'])
                self.assertEqual(self.verdict(frames)['verdict'], 'failed')

    def test_touching_with_one_finger_is_failure(self):
        self.frames[425]['contacts'] = self.frames[425]['contacts'][:1]
        self.assertEqual(self.verdict()['verdict'], 'failed')

    def test_slip_and_rotation_are_failures(self):
        self.frames[-1]['relative_position'][0] += .006
        self.assertIn('relative_translation_exceeded', self.verdict()['reason'])
        self.frames[-1]['relative_position'][0] -= .006
        angle = math.radians(16)
        self.frames[-1]['relative_rotation'] = [math.cos(angle), -math.sin(angle), 0., math.sin(angle), math.cos(angle), 0., 0., 0., 1.]
        self.assertIn('relative_rotation_exceeded', self.verdict()['reason'])

    def test_geometric_clearance_is_failure(self):
        self.frames[-1]['table_clearance_m'] = .004
        self.assertIn('table_clearance_insufficient', self.verdict()['reason'])

    def test_missing_frame_or_contact_measurement_is_unknown(self):
        self.assertEqual(self.verdict(self.frames[:-1])['verdict'], 'unknown')
        del self.frames[425]['contacts']
        self.assertEqual(self.verdict()['verdict'], 'unknown')

    def test_frozen_physics_is_unknown(self):
        self.frames[425]['sim_seconds'] = self.frames[424]['sim_seconds']
        self.assertEqual(self.verdict()['verdict'], 'unknown')

    def test_changed_hold_target_is_unknown(self):
        self.frames[425]['action'][0] = .1
        self.assertEqual(self.verdict()['verdict'], 'unknown')


class EvaluationCommandTests(unittest.TestCase):
    def test_nonobject_trace_reports_unknown_without_model_loading(self):
        from robot_agent.evaluate_handoff import evaluate_run
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run / 'trace.jsonl').write_text('[]\n')
            result = evaluate_run(run)
            self.assertEqual(result['verdict'], 'unknown')
            self.assertIn('trace record is not an object', result['reason'])
            self.assertEqual(result['consumed_profile']['id'], 'aloha-left-handoff-hold-v1')

    def test_missing_trace_command_writes_unknown_with_exit_two(self):
        from robot_agent.evaluate_handoff import main
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'evaluation.json'
            with patch('sys.argv', ['evaluate', '--run', directory, '--output', str(report)]), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(), 2)
            self.assertEqual(json.loads(report.read_text())['verdict'], 'unknown')

    def test_existing_report_is_preserved_without_re_evaluation(self):
        from robot_agent.evaluate_handoff import main
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'evaluation.json'
            report.write_text('retained report')
            with patch('sys.argv', ['evaluate', '--run', directory, '--output', str(report)]), \
                    patch('robot_agent.evaluate_handoff.evaluate_run') as evaluator, \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    main()
            self.assertEqual(caught.exception.code, 2)
            self.assertEqual(report.read_text(), 'retained report')
            evaluator.assert_not_called()


if __name__ == '__main__':
    unittest.main()
