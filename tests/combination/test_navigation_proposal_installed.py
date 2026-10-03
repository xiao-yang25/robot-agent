"""Actual public CLI proposal failures at real decision sites; no physics/model."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

import robot_agent.navigation_cli


class InstalledNavigationProposalTests(unittest.TestCase):
    def run_case(self, case):
        prefix = Path(os.environ['COMBINATION_AGENT_PREFIX']).resolve()
        self.assertTrue(Path(robot_agent.navigation_cli.__file__).resolve().is_relative_to(prefix))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            endpoint, audit = root/'nav.sock', root/'audit.json'
            # Use the same interpreter as the installed packages; no global
            # Python/virtualenv assumptions are baked into the executable.
            source = Path(__file__).with_name('navigation_proposal_fixture.py').read_text()
            executable = root/'proposal'
            executable.write_text(f'#!{sys.executable}\n'+source.split('\n', 1)[1])
            executable.chmod(0o755)
            with (root/'owner.log').open('w+') as owner_log, (root/'agent.log').open('w+') as agent_log:
                command = [sys.executable, str(Path(__file__).with_name('navigation_owner.py')),
                           str(endpoint), str(audit)]
                if case == 'late-final':
                    command.append('--wait-proposal')
                owner = subprocess.Popen(command, stdout=owner_log, stderr=subprocess.STDOUT)
                agent = None
                try:
                    until = time.monotonic()+5
                    while not endpoint.exists() and owner.poll() is None and time.monotonic() < until:
                        time.sleep(.01)
                    owner_log.flush()
                    owner_log.seek(0)
                    self.assertTrue(endpoint.exists(), owner_log.read())
                    agent = subprocess.Popen([sys.executable, '-m', 'robot_agent.navigation_cli',
                        '--endpoint', str(endpoint), '--output', str(root/'agent'),
                        '--model', case, '--executable', str(executable)],
                        stdout=agent_log, stderr=subprocess.STDOUT)
                    self.assertEqual(agent.wait(timeout=40), 1)
                    self.assertEqual(owner.wait(timeout=5), 0)
                    report = json.loads((root/'agent/report.json').read_text())
                    facts = json.loads(audit.read_text())
                    self.assertEqual(report['status'], 'needs_help', report)
                    self.assertEqual(report['task_verdict'], 'unassessed')
                    self.assertEqual(report['native_cleanup'], 'unknown')
                    self.assertEqual(report['connection_close'], 'local_closed')
                    self.assertEqual(report['close_response']['closure'], 'unknown')
                    self.assertFalse(endpoint.exists())
                    self.assertNotIn('observation_assessment', report)
                    self.assertNotIn('execution_cleanup', report)
                    phases = [r['context']['phase'] for r in report['decisions']]
                    sites = [r['site'] for r in facts['records']]
                    decisions = sorted((root/'agent/decisions').glob('decision-*'))
                    if case == 'error-before-a':
                        self.assertIn('attempted tools', report['reason'])
                        self.assertEqual((report['phase'], phases, sites, facts['stops']),
                                         ('prepare', [], [], []))
                        self.assertEqual(report['operations'], [])
                        self.assertEqual(len(decisions), 1)
                    elif case == 'help-after-a':
                        self.assertEqual(report['reason'], 'decision_backend_abstained')
                        self.assertEqual((report['phase'], phases, sites, facts['stops']),
                                         ('after_a', ['prepare', 'after_a'], ['A'], []))
                        self.assertEqual(report['decisions'][-1]['answer']['action'], 'help')
                        self.assertEqual(len(decisions), 2)
                    else:
                        self.assertIn('TimeoutError: decision deadline elapsed', report['reason'])
                        self.assertGreaterEqual(report['wall_seconds'], 30)
                        self.assertEqual((report['phase'], phases, sites),
                                         ('final', ['prepare', 'after_a'], ['A', 'B']))
                        self.assertEqual(len(decisions), 3)
                        last = decisions[-1]
                        inputs = json.loads((last/'input.json').read_text())
                        answer = json.loads((last/'answer.json').read_text())
                        self.assertEqual(answer['action'], 'observed_complete')
                        self.assertEqual(answer['task_id'], report['task_id'])
                        self.assertEqual(answer['phase'], 'final')
                        self.assertEqual(answer['observation_reference'], inputs['observation_reference'])
                        late = json.loads((last/'fixture-late.json').read_text())
                        self.assertTrue(late['on_termination'])
                        self.assertEqual(late['pid'], json.loads((last/'process.json').read_text())['pid'])
                        b = facts['records'][1]
                        self.assertEqual(facts['stops'], [b['request_id']])
                        self.assertTrue(report['cancel_response']['affected_current'])
                        self.assertEqual(report['interrupted_operation']['request_id'], b['request_id'])
                        self.assertEqual(b['receipt']['authority_disposition'], 'revoked')
                        self.assertEqual(b['receipt']['settlement'], 'pending')
                        self.assertEqual(b['receipt']['native_outcome'], 'succeeded')
                        self.assertEqual(b['receipt']['output'], 'accepted')
                        self.assertEqual(b['result']['goal_id'], b['receipt']['native_identity'])
                    if sites:
                        self.assertEqual(facts['records'][0]['receipt']['settlement'], 'settled')
                        self.assertEqual(facts['records'][0]['receipt']['authority_disposition'], 'released')
                    for path in decisions:
                        child = json.loads((path/'process.json').read_text())
                        self.assertEqual(child['returncode'], 0)
                        self.assertTrue(child['reaped'])
                        with self.assertRaises(ProcessLookupError):
                            os.kill(child['pid'], 0)
                finally:
                    for process in (agent, owner):
                        if process is not None:
                            if process.poll() is None:
                                process.send_signal(signal.SIGTERM)
                                try:
                                    process.wait(timeout=5)
                                except subprocess.TimeoutExpired:
                                    process.kill()
                            process.wait(timeout=5)

    def test_tool_event_before_a_has_zero_admissions(self):
        self.run_case('error-before-a')

    def test_help_after_a_releases_a_without_admitting_b(self):
        self.run_case('help-after-a')

    def test_final_answer_written_on_timeout_cannot_complete_or_release_b(self):
        self.run_case('late-final')


if __name__ == '__main__':
    unittest.main()
