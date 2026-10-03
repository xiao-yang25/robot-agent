"""Installed application/public Unix Session/Core; no ROS, model or physics."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import robot_agent.navigation
import robot_harness.navigation
from robot_agent.navigation import NavigationTask
from robot_harness import NavigationSession


class Proposal:
    def __init__(self, final='observed_complete'):
        self.final = final
        self.references = []

    def decide(self, context, observation, deadline, stop_requested):
        if set(observation) != {'reference', 'pose', 'sample_sim_seconds', 'sensor_health'}:
            raise AssertionError('undeclared measurement reached task decisions')
        self.references.append(observation['reference'])
        return dict(task_id=context['task_id'], phase=context['phase'],
                    observation_reference=context['observation_reference'],
                    action={'prepare': 'visit_a', 'after_a': 'visit_b', 'final': self.final}[context['phase']],
                    reason='CI-only controlled proposal')


class InstalledNavigationTests(unittest.TestCase):
    def setUp(self):
        for module, variable in ((robot_agent.navigation, 'COMBINATION_AGENT_PREFIX'),
                                 (robot_harness.navigation, 'COMBINATION_HARNESS_PREFIX')):
            self.assertTrue(Path(module.__file__).resolve().is_relative_to(
                Path(os.environ[variable]).resolve()), module.__file__)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.endpoint, self.audit = self.root/'nav.sock', self.root/'audit.json'
        self.log = (self.root/'owner.log').open('w+')
        self.addCleanup(self.log.close)
        self.owner = subprocess.Popen([sys.executable, str(Path(__file__).with_name('navigation_owner.py')),
                                       str(self.endpoint), str(self.audit)],
                                      stdout=self.log, stderr=subprocess.STDOUT)
        self.addCleanup(self.reap_owner)
        deadline = time.monotonic()+5
        while not self.endpoint.exists() and self.owner.poll() is None and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(self.endpoint.exists(), 'owner fixture did not listen')
        self.session = NavigationSession(self.endpoint)
        self.addCleanup(self.session.close)

    def reap_owner(self):
        try:
            code = self.owner.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.owner.kill()
            self.owner.wait(timeout=5)
            self.fail('owner fixture needed forced termination')
        self.log.seek(0)
        self.assertEqual(code, 0, self.log.read())
        self.assertFalse(self.endpoint.exists(), 'owner socket retained after process exit')

    def run_task(self, final):
        proposal = Proposal(final)
        report = NavigationTask(proposal).run(self.session)
        self.assertEqual(report['task_verdict'], 'unassessed')
        self.assertEqual(len(proposal.references), 3, report)
        operations = report['operations']
        self.assertEqual([row['site'] for row in operations], ['A', 'B'], report)
        self.assertNotEqual(operations[0]['operation_id'], operations[1]['operation_id'])
        self.assertNotEqual(operations[0]['goal_id'], operations[1]['goal_id'])
        for index, row in enumerate(operations):
            receipt = row['receipt']
            self.assertEqual(receipt['authority']['operation_id'], row['operation_id'])
            self.assertEqual(receipt['native_identity'], row['goal_id'])
            self.assertEqual(receipt['result_reference'], row['request_id'])
            self.assertEqual(receipt['output'], 'accepted')
            self.assertEqual(receipt['native_outcome'], 'succeeded')
            self.assertNotEqual(row['observation_reference'], proposal.references[index])
            self.assertEqual(row['observation_reference'],
                             report['decisions'][index]['revalidated_observation']['reference'])
        self.assertEqual(operations[0]['receipt']['settlement'], 'settled')
        self.assertEqual(operations[0]['receipt']['authority_disposition'], 'released')
        self.assertEqual(operations[1]['receipt']['settlement'], 'pending')
        self.assertEqual(operations[1]['receipt']['authority_disposition'], 'current')
        closed = self.session.close()
        self.assertEqual(closed['closure'], 'unknown')
        self.assertFalse(closed['owner_reaped'])
        self.reap_owner()
        audit = json.loads(self.audit.read_text())
        self.assertEqual(len(audit['records']), 2)
        self.assertEqual(audit['stops'], [operations[1]['request_id']])
        self.assertEqual(audit['records'][0]['receipt']['authority_disposition'], 'released')
        self.assertEqual(audit['records'][1]['receipt']['authority_disposition'], 'revoked')
        self.assertEqual(audit['records'][1]['receipt']['settlement'], 'pending')
        return report

    def test_normal_public_session_preserves_final_pending_and_unknown_close(self):
        report = self.run_task('observed_complete')
        self.assertEqual(report['status'], 'completed', report)
        self.assertEqual(report['execution_cleanup'], 'pending')
        self.assertTrue(report['requires_connection_close'])

    def test_final_help_cancels_the_exact_pending_context(self):
        report = self.run_task('help')
        self.assertEqual(report['status'], 'needs_help', report)
        self.assertTrue(report['cancel_response']['affected_current'])
        interrupted = report['interrupted_operation']
        self.assertEqual(interrupted['request_id'], report['operations'][1]['request_id'])
        self.assertEqual(interrupted['receipt']['authority_disposition'], 'revoked')
        self.assertEqual(interrupted['receipt']['settlement'], 'pending')


if __name__ == '__main__':
    unittest.main()
