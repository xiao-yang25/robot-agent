"""Installed host/relay/CLI/Core composition; controlled subprocess, no model/physics."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import robot_agent.navigation_host_model
from robot_agent._navigation_demo import finish


class InstalledNavigationHostTests(unittest.TestCase):
    def run_case(self, model, tool_error=False):
        prefix = Path(os.environ['COMBINATION_AGENT_PREFIX']).resolve()
        self.assertTrue(Path(robot_agent.navigation_host_model.__file__).resolve().is_relative_to(prefix))
        self.assertTrue((prefix/'bin/robot-agent-navigation-host-proposal').is_file())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scene, private = root/'scene', root/'private'
            scene.mkdir(); private.mkdir()
            endpoint, audit = root/'nav.sock', root/'audit.json'
            relay = root/'relay'
            relay.write_text(f'#!{sys.executable}\nfrom pathlib import Path\n'
                'from robot_agent.navigation_host_proposal import main\n'
                f'raise SystemExit(main(exchange=Path({str(scene)!r})))\n')
            relay.chmod(0o755)
            executable = prefix/'bin/robot-agent-navigation-controlled'
            if tool_error:
                executable = root/'proposal'
                source = Path(__file__).with_name('navigation_proposal_fixture.py').read_text()
                executable.write_text(f'#!{sys.executable}\n'+source.split('\n', 1)[1])
                executable.chmod(0o755)
            processes = []
            with (root/'host.log').open('w+') as host_log, (root/'owner.log').open('w+') as owner_log, (root/'agent.log').open('w+') as agent_log:
                try:
                    host = subprocess.Popen([sys.executable, '-m', 'robot_agent.navigation_host_model',
                        '--exchange', str(scene), '--output', str(private), '--model', model,
                        '--executable', str(executable)], stdout=host_log, stderr=subprocess.STDOUT,
                        start_new_session=True)
                    processes.append(host)
                    owner = subprocess.Popen([sys.executable, str(Path(__file__).with_name('navigation_owner.py')),
                        str(endpoint), str(audit)], stdout=owner_log, stderr=subprocess.STDOUT,
                        start_new_session=True)
                    processes.append(owner)
                    until = time.monotonic()+5
                    while (not endpoint.exists() or not (private/'ready.json').exists()) and time.monotonic()<until:
                        time.sleep(.01)
                    self.assertTrue(endpoint.exists()); self.assertTrue((private/'ready.json').exists())
                    result = subprocess.run([sys.executable, '-m', 'robot_agent.navigation_cli',
                        '--endpoint', str(endpoint), '--output', str(scene/'agent'),
                        '--model', model, '--executable', str(relay)],
                        stdout=agent_log, stderr=subprocess.STDOUT, timeout=15)
                    agent_log.seek(0)
                    self.assertEqual(result.returncode, int(tool_error), agent_log.read())
                    self.assertEqual(owner.wait(timeout=5), 0)
                    report = json.loads((scene/'agent/report.json').read_text())
                    facts = json.loads(audit.read_text())
                    self.assertEqual(report['task_verdict'], 'unassessed')
                    self.assertEqual(report['native_cleanup'], 'unknown')
                    if tool_error:
                        self.assertEqual(report['status'], 'needs_help')
                        self.assertIn('decision CLI exited 1', report['reason'])
                        reply = json.loads((scene/'model-requests/prepare/response.json').read_text())
                        self.assertIn('attempted tools', reply['error'])
                        events = [json.loads(line) for line in (private/'decisions/decision-1/events.jsonl').read_text().splitlines()]
                        self.assertTrue(any(row.get('item', {}).get('type') == 'command_execution' for row in events))
                        self.assertEqual(report['operations'], [])
                        self.assertEqual(facts['records'], [])
                        self.assertEqual(facts['stops'], [])
                    else:
                        self.assertEqual(report['status'], 'completed')
                        self.assertEqual([r['answer']['action'] for r in report['decisions']],
                                         ['visit_a', 'visit_b', 'observed_complete'])
                        self.assertEqual(facts['records'][0]['receipt']['settlement'], 'settled')
                        self.assertEqual(facts['records'][1]['receipt']['settlement'], 'pending')
                    host.terminate()
                    self.assertEqual(host.wait(timeout=5), 0)
                    self.assertTrue(json.loads((private/'model-server.json').read_text())['stop_observed'])
                    for base in (scene/'agent/decisions', private/'decisions'):
                        paths = list(base.glob('*/process.json'))
                        self.assertEqual(len(paths), 1 if tool_error else 3)
                        for path in paths:
                            child = json.loads(path.read_text())
                            self.assertTrue(child['reaped'])
                            with self.assertRaises(ProcessLookupError): os.kill(child['pid'], 0)
                finally:
                    for process in reversed(processes):
                        finish(process, 1)

    def test_installed_host_relay_completes_and_preserves_pending_settlement(self):
        self.run_case('controlled-tutorial-no-model')

    def test_host_tool_event_crosses_relay_as_error_with_zero_admissions(self):
        self.run_case('error-before-a', tool_error=True)


if __name__ == '__main__':
    unittest.main()
