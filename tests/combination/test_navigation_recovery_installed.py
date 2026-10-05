"""Installed recovery/public Session/real Core; controlled native edges, no ROS."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from robot_agent import RecoveryNavigationTask
from robot_agent.navigation import NavigationBudget
import robot_agent.navigation_recovery
from robot_harness import NavigationSession


class Proposal:
    def __init__(self, action='visit_b', callback=lambda context, answer: None):
        self.action, self.callback, self.contexts = action, callback, []

    def decide(self, context, observation, deadline, stopped):
        self.contexts.append(deepcopy(context))
        if set(observation) != {'reference','pose','sample_sim_seconds','sensor_health'}:
            raise AssertionError('undeclared truth reached model')
        answer=dict(task_id=context['task_id'], phase=context['phase'],
                    observation_reference=deepcopy(context['observation_reference']),
                    action=context['allowed_actions'][0], reason='controlled installed proposal')
        if context['phase']=='after_failure':
            answer.update(action=self.action, **{key:context['failure_context'][key]
                for key in ('recovery_id','request_id','operation_id','goal_id')})
        self.callback(context,answer)
        return answer


class InstalledRecoveryTests(unittest.TestCase):
    def exercise(self, mode='--failure', proposal=None):
        self.assertTrue(Path(robot_agent.navigation_recovery.__file__).resolve().is_relative_to(
            Path(os.environ['COMBINATION_AGENT_PREFIX']).resolve()))
        proposal=proposal or Proposal()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            endpoint,audit=root/'nav.sock',root/'audit.json'
            with (root/'owner.log').open('w+') as log:
                owner=subprocess.Popen([sys.executable,str(Path(__file__).with_name('navigation_owner.py')),
                    str(endpoint),str(audit),mode],stdout=log,stderr=subprocess.STDOUT)
                try:
                    until=time.monotonic()+5
                    while not endpoint.exists() and owner.poll() is None and time.monotonic()<until: time.sleep(.01)
                    log.seek(0)
                    self.assertTrue(endpoint.exists(),log.read())
                    budget=NavigationBudget(operation_seconds=.5) if mode=='--failure-missing-close' else NavigationBudget()
                    with NavigationSession(endpoint) as session:
                        report=RecoveryNavigationTask(proposal,budget=budget).run(session)
                    self.assertEqual(owner.wait(timeout=5),0)
                    self.assertFalse(endpoint.exists())
                    with self.assertRaises(ProcessLookupError): os.kill(owner.pid,0)
                    self.assertEqual(report['task_verdict'],'unassessed')
                    self.assertEqual(report['native_cleanup'],'unknown')
                    return report,json.loads(audit.read_text()),proposal
                finally:
                    if owner.poll() is None: owner.kill()
                    owner.wait(timeout=5)

    def test_real_failed_no_output_release_before_one_fresh_b(self):
        report,audit,proposal=self.exercise()
        self.assertEqual(report['status'],'completed',report)
        self.assertEqual(report['completed_sites'],['B'])
        a,b=report['operations']
        self.assertEqual(a['receipt']['native_outcome'],'failed')
        self.assertEqual(a['receipt']['output_non_delivery_reason'],'no_output')
        self.assertEqual(a['receipt']['authority_disposition'],'released')
        self.assertEqual(b['receipt']['settlement'],'pending')
        self.assertNotEqual(a['goal_id'],b['goal_id'])
        self.assertEqual(b['observation_reference'],report['decisions'][1]['revalidated_observation']['reference'])
        self.assertEqual(audit['events'],['A_failed','A_released','B_submit'])
        self.assertEqual(audit['stops'],[b['request_id']])
        self.assertEqual([c['phase'] for c in proposal.contexts],['prepare','after_failure','final'])

    def test_normal_a_is_only_visit_and_skips_backup(self):
        report,audit,proposal=self.exercise('--failure-normal')
        self.assertEqual(report['status'],'completed',report)
        self.assertEqual(report['completed_sites'],['A'])
        self.assertEqual(len(audit['records']),1)
        self.assertFalse(audit['stops'])
        self.assertEqual(proposal.contexts[-1]['completion_site'],'A')

    def test_unreleased_failed_a_has_zero_recovery_proposals_and_zero_b(self):
        report,audit,proposal=self.exercise('--failure-missing-close')
        self.assertEqual(report['status'],'needs_help',report)
        self.assertEqual(len(audit['records']),1)
        self.assertEqual(audit['records'][0]['receipt']['settlement'],'pending')
        self.assertEqual(audit['records'][0]['receipt']['authority_disposition'],'revoked')
        self.assertEqual(len(proposal.contexts),1)

    def test_help_or_foreign_failure_reference_has_no_second_core_record(self):
        for proposal in (Proposal('help'),Proposal(callback=lambda c,a:a.update(request_id='foreign')
                                                if c['phase']=='after_failure' else None)):
            with self.subTest(proposal=proposal):
                report,audit,_=self.exercise(proposal=proposal)
                self.assertEqual(report['status'],'needs_help',report)
                self.assertEqual(len(audit['records']),1)
                self.assertFalse(audit['stops'])

    def test_failed_backup_is_not_another_recovery_and_is_cancelled_exactly(self):
        report,audit,proposal=self.exercise('--failure-b-failed')
        self.assertEqual(report['status'],'needs_help',report)
        self.assertEqual(len(audit['records']),2)
        self.assertEqual(len(proposal.contexts),2)
        self.assertEqual(audit['records'][1]['receipt']['native_outcome'],'failed')
        self.assertEqual(audit['stops'],[audit['records'][1]['request_id']])
        self.assertFalse(report['completed_sites'])


if __name__=='__main__': unittest.main()
