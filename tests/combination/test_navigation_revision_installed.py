"""Installed application/public Session/real Core; synthetic motion and native edges."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from robot_agent import RevisionNavigationTask
from robot_agent.navigation import NavigationBudget
from robot_agent.navigation_revision_demo import ControlledRevisionDecision, TutorialPoll, run
from robot_harness import NavigationSession
import robot_agent.navigation_revision


class InstalledRevisionTests(unittest.TestCase):
    def exercise(self, instruction, mode='--revision', *, caller=False):
        self.assertTrue(Path(robot_agent.navigation_revision.__file__).resolve().is_relative_to(
            Path(os.environ['COMBINATION_AGENT_PREFIX']).resolve()))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            endpoint, audit = root/'nav.sock', root/'audit.json'
            with (root/'owner.log').open('w+') as log:
                owner = subprocess.Popen([sys.executable, str(Path(__file__).with_name('navigation_owner.py')),
                    str(endpoint), str(audit), mode], stdout=log, stderr=subprocess.STDOUT)
                try:
                    until = time.monotonic()+5
                    while not endpoint.exists() and owner.poll() is None and time.monotonic() < until: time.sleep(.01)
                    log.seek(0)
                    self.assertTrue(endpoint.exists(), log.read())
                    if caller:
                        code = run(endpoint, root/'agent', instruction=instruction, delay=0)
                        self.assertEqual(code, 0)
                        report = json.loads((root/'agent/report.json').read_text())
                        self.assertEqual(report['connection_close'], 'local_closed')
                    else:
                        with NavigationSession(endpoint) as session:
                            provider = TutorialPoll(instruction, 0, root)
                            budget = NavigationBudget(operation_seconds=1.4) if mode == '--revision-missing-close' else NavigationBudget()
                            report = RevisionNavigationTask(ControlledRevisionDecision(), provider, budget=budget).run(session)
                    self.assertEqual(owner.wait(timeout=5), 0)
                    self.assertFalse(endpoint.exists())
                    return report, json.loads(audit.read_text())
                finally:
                    if owner.poll() is None: owner.kill()
                    owner.wait(timeout=5)

    def test_no_instruction_finishes_only_actual_a(self):
        report, audit = self.exercise('none')
        self.assertEqual(report['status'], 'completed', report)
        self.assertEqual(report['completed_sites'], ['A'])
        self.assertEqual(len(audit['records']), 1)
        self.assertFalse(audit['stops'])

    def test_stop_real_cancelled_core_release_and_public_caller_close(self):
        report, audit = self.exercise('stop', caller=True)
        self.assertEqual(report['status'], 'stopped_by_instruction', report)
        self.assertEqual(report['completed_sites'], [])
        a = report['operations'][0]
        self.assertEqual(a['receipt']['native_outcome'], 'cancelled')
        self.assertEqual(a['receipt']['output_non_delivery_reason'], 'no_output')
        self.assertEqual(a['receipt']['authority_disposition'], 'released')
        self.assertEqual(audit['stops'], [a['request_id']])
        self.assertEqual(len(report['decisions']), 1)

    def test_redirect_uses_real_release_fresh_reference_then_one_b(self):
        report, audit = self.exercise('redirect_b')
        self.assertEqual(report['status'], 'completed', report)
        self.assertEqual(report['completed_sites'], ['B'])
        a, b = report['operations']
        self.assertEqual(a['receipt']['settlement'], 'settled')
        self.assertEqual(b['receipt']['settlement'], 'pending')
        self.assertEqual(b['receipt']['authority_disposition'], 'current')
        self.assertEqual(b['observation_reference'], report['decisions'][1]['revalidated_observation']['reference'])
        self.assertNotEqual(a['goal_id'], b['goal_id'])
        self.assertEqual(audit['stops'], [a['request_id'], b['request_id']])
        self.assertEqual(len(audit['records']), 2)
        self.assertEqual(audit['events'][:3], ['A_native_accepted', 'A_cancel', 'A_released'])
        self.assertEqual(report['task_verdict'], 'unassessed')
        self.assertEqual(report['native_cleanup'], 'unknown')

    def test_success_racing_cancel_keeps_real_succeeded_disposition(self):
        report, _ = self.exercise('redirect_b', '--revision-race')
        self.assertEqual(report['status'], 'completed', report)
        a = report['operations'][0]
        self.assertEqual(a['receipt']['native_outcome'], 'succeeded')
        self.assertEqual(a['receipt']['output_non_delivery_reason'], 'authority_revoked')
        self.assertEqual(report['completed_sites'], ['B'])

    def test_unconfirmed_closure_keeps_actual_core_pending_and_zero_b(self):
        report, audit = self.exercise('redirect_b', '--revision-missing-close')
        self.assertEqual(report['status'], 'needs_help', report)
        self.assertEqual(len(audit['records']), 1)
        self.assertEqual(audit['records'][0]['receipt']['settlement'], 'pending')
        self.assertEqual(audit['records'][0]['receipt']['authority_disposition'], 'revoked')
        self.assertEqual(len(report['decisions']), 1)


if __name__ == '__main__': unittest.main()
