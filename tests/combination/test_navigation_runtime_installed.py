"""Installed private assembly with real Session/Core; synthetic native facts only."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

import robot_agent._navigation_runtime as runtime
from robot_harness import NavigationSession
from test_navigation_installed import Proposal


class InstalledRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(runtime.__file__).resolve().is_relative_to(
            Path(os.environ['COMBINATION_AGENT_PREFIX']).resolve()))
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.endpoint, self.audit = self.root / 'nav.sock', self.root / 'audit.json'
        self.log = (self.root / 'owner.log').open('w+')
        self.addCleanup(self.log.close)
        self.owner = subprocess.Popen([sys.executable, str(Path(__file__).with_name('navigation_owner.py')),
                                       str(self.endpoint), str(self.audit)],
                                      stdout=self.log, stderr=subprocess.STDOUT)
        self.addCleanup(self.reap_owner)
        until = time.monotonic() + 5
        while not self.endpoint.exists() and self.owner.poll() is None and time.monotonic() < until:
            time.sleep(.01)
        self.assertTrue(self.endpoint.exists(), 'owner did not listen')

    def reap_owner(self):
        try:
            code = self.owner.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.owner.kill()
            self.owner.wait(timeout=5)
            self.fail('native fixture required forced termination')
        self.log.seek(0)
        self.assertEqual(code, 0, self.log.read())
        self.assertFalse(self.endpoint.exists())

    def test_installed_normal_retains_real_core_domain_results(self):
        report = runtime.run_navigation(lambda: NavigationSession(self.endpoint), Proposal)
        self.assertEqual(report['status'], 'completed', report)
        self.assertEqual(report['connection_close'], 'local_closed')
        self.assertEqual(report['native_cleanup'], 'unknown')
        self.assertTrue(report['coordination']['resources_closed'])
        a, b = report['operations']
        self.assertEqual([a['site'], b['site']], ['A', 'B'])
        self.assertEqual(a['receipt']['settlement'], 'settled')
        self.assertEqual(a['receipt']['authority_disposition'], 'released')
        self.assertEqual(b['receipt']['settlement'], 'pending')
        self.assertEqual(b['receipt']['authority_disposition'], 'current')
        self.assertNotEqual(a['operation_id'], b['operation_id'])
        self.reap_owner()
        facts = json.loads(self.audit.read_text())
        self.assertEqual(len(facts['records']), 2)
        self.assertEqual(facts['stops'], [b['request_id']])

    def test_installed_cli_stop_during_final_proposal_reaps_actual_children(self):
        executable = self.root / 'proposal'
        executable.write_text(f'#!{sys.executable}\n' + '''
import json, os, signal, sys, time
from pathlib import Path
if '--version' in sys.argv:
    print('controlled-private-runtime-proposal'); raise SystemExit(0)
inputs = json.loads(sys.stdin.read().splitlines()[-1])
output = Path(sys.argv[sys.argv.index('--output-last-message') + 1])
if inputs['phase'] == 'final':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    (output.parent / 'blocked.json').write_text(json.dumps({'pid': os.getpid()}))
    time.sleep(45)
    raise RuntimeError('cancelled child was not reaped')
answer = {key: inputs[key] for key in ('task_id', 'phase', 'observation_reference')}
answer.update(action=inputs['allowed_actions'][0], reason='controlled proposal; no model')
output.write_text(json.dumps(answer))
print(json.dumps({'item': {'type': 'agent_message'}}))
''')
        executable.chmod(0o700)
        output = self.root / 'agent'
        with (self.root / 'agent.log').open('w+') as log:
            caller = subprocess.Popen([sys.executable, '-m', 'robot_agent._navigation_runtime',
                '--endpoint', str(self.endpoint), '--output', str(output),
                '--model', 'controlled-fixture', '--executable', str(executable)],
                stdout=log, stderr=subprocess.STDOUT)
            try:
                marker = output / 'decisions' / 'decision-3' / 'blocked.json'
                until = time.monotonic() + 5
                while not marker.exists() and caller.poll() is None and time.monotonic() < until:
                    time.sleep(.01)
                self.assertTrue(marker.exists(), 'caller did not reach the final decision')
                caller.send_signal(signal.SIGINT)
                self.assertEqual(caller.wait(timeout=5), 1)
            finally:
                if caller.poll() is None:
                    caller.kill()
                caller.wait(timeout=5)
            log.seek(0)
            report = json.loads((output / 'report.json').read_text())
            self.assertEqual(report['status'], 'cancelled', log.read())
        self.assertTrue(report['coordination']['resources_closed'])
        self.assertEqual(report['task_verdict'], 'unassessed')
        self.assertEqual(report['native_cleanup'], 'unknown')
        self.assertEqual(report['connection_close'], 'local_closed')
        self.assertEqual([row['context']['phase'] for row in report['decisions']], ['prepare', 'after_a'])
        b = report['operations'][-1]
        self.assertEqual(report['interrupted_operation']['request_id'], b['request_id'])
        self.assertTrue(report['cancel_response']['affected_current'])
        self.reap_owner()
        facts = json.loads(self.audit.read_text())
        self.assertEqual([row['site'] for row in facts['records']], ['A', 'B'])
        self.assertEqual(facts['stops'], [b['request_id']])
        for path in (output / 'decisions').glob('*/process.json'):
            child = json.loads(path.read_text())
            self.assertTrue(child['reaped'])
            with self.assertRaises(ProcessLookupError):
                os.kill(child['pid'], 0)


if __name__ == '__main__':
    unittest.main()
