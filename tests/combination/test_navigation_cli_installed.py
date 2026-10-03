"""Actual installed CLI process interruption; synthetic native provider only."""
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


class InstalledNavigationCliTests(unittest.TestCase):
    def test_sigint_cancels_running_b_without_a_final_proposal(self):
        prefix = Path(os.environ['COMBINATION_AGENT_PREFIX']).resolve()
        self.assertTrue(Path(robot_agent.navigation_cli.__file__).resolve().is_relative_to(prefix))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            endpoint, audit = root/'nav.sock', root/'audit.json'
            executable = root/'proposal'
            executable.write_text(f'#!{sys.executable}\n' + '''import json,sys
from pathlib import Path
if '--version' in sys.argv:
 print('controlled-navigation-proposal');raise SystemExit(0)
inputs=json.loads(sys.stdin.read().splitlines()[-1])
answer={k:inputs[k] for k in ('task_id','phase','observation_reference')}
answer.update(action=inputs['allowed_actions'][0],reason='controlled proposal, no model request')
Path(sys.argv[sys.argv.index('--output-last-message')+1]).write_text(json.dumps(answer))
print(json.dumps({'item':{'type':'agent_message'}}))
''')
            executable.chmod(0o755)
            with (root/'owner.log').open('w+') as owner_log, (root/'agent.log').open('w+') as agent_log:
                owner = subprocess.Popen([sys.executable, str(Path(__file__).with_name('navigation_owner.py')),
                    str(endpoint), str(audit), '--hold-b'], stdout=owner_log, stderr=subprocess.STDOUT)
                agent = None
                try:
                    until = time.monotonic()+5
                    while not endpoint.exists() and owner.poll() is None and time.monotonic() < until:
                        time.sleep(.01)
                    owner_log.flush()
                    owner_log.seek(0)
                    self.assertTrue(endpoint.exists(), 'owner did not listen: '+owner_log.read())
                    agent = subprocess.Popen([sys.executable, '-m', 'robot_agent.navigation_cli',
                        '--endpoint', str(endpoint), '--output', str(root/'agent'),
                        '--model', 'controlled-fixture', '--executable', str(executable)],
                        stdout=agent_log, stderr=subprocess.STDOUT)
                    ready = audit.with_suffix('.running.json')
                    until = time.monotonic()+5
                    while not ready.exists() and agent.poll() is None and time.monotonic() < until:
                        time.sleep(.01)
                    self.assertTrue(ready.exists(), 'Agent did not admit/accept B')
                    running = json.loads(ready.read_text())
                    self.assertEqual(running['site'], 'B')
                    self.assertEqual(running['receipt']['native_acceptance'], 'accepted')
                    agent.send_signal(signal.SIGINT)
                    self.assertEqual(agent.wait(timeout=5), 1, 'interruption must not report completion')
                    self.assertEqual(owner.wait(timeout=5), 0)
                    report = json.loads((root/'agent/report.json').read_text())
                    self.assertEqual(report['status'], 'cancelled', report)
                    self.assertEqual(report['task_verdict'], 'unassessed')
                    self.assertEqual(report['native_cleanup'], 'unknown')
                    self.assertEqual(report['connection_close'], 'local_closed')
                    self.assertEqual([r['context']['phase'] for r in report['decisions']], ['prepare', 'after_a'])
                    self.assertEqual(report['interrupted_operation']['request_id'], running['request_id'])
                    self.assertTrue(report['cancel_response']['affected_current'])
                    self.assertEqual(report['close_response']['closure'], 'unknown')
                    facts = json.loads(audit.read_text())
                    self.assertEqual(facts['stops'], [running['request_id']])
                    self.assertEqual([r['site'] for r in facts['records']], ['A', 'B'])
                    a, b = facts['records']
                    self.assertEqual(a['receipt']['settlement'], 'settled')
                    self.assertEqual(a['receipt']['authority_disposition'], 'released')
                    self.assertEqual(b['receipt']['native_identity'], running['goal_id'])
                    self.assertEqual(b['receipt']['authority_disposition'], 'revoked')
                    self.assertEqual(b['receipt']['settlement'], 'pending')
                    self.assertIsNone(b['result'])
                    self.assertFalse(endpoint.exists())
                    self.assertFalse((root/'agent/decisions/decision-3').exists())
                    for path in (root/'agent/decisions').glob('*/process.json'):
                        child = json.loads(path.read_text())
                        self.assertTrue(child['reaped'])
                        with self.assertRaises(ProcessLookupError):
                            os.kill(child['pid'], 0)
                finally:
                    for process in (agent, owner):
                        if process is not None:
                            if process.poll() is None:
                                process.kill()
                            process.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
