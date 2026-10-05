"""Installed controlled tutorial executable and real CLI/Core; no physics/model."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


class InstalledNavigationDemoTests(unittest.TestCase):
    def test_installed_recovery_supervisor_binds_map_and_removes_exact_client(self):
        import robot_agent._navigation_demo as demo
        prefix=Path(os.environ['COMBINATION_AGENT_PREFIX']).resolve()
        self.assertTrue(Path(demo.__file__).resolve().is_relative_to(prefix))
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);launch=root/'launch.py';record=root/'client.json'
            launch.write_text('import json,sys\nfrom pathlib import Path\n'
                'client=Path(sys.argv[sys.argv.index("--client-script")+1])\n'
                f'Path({str(record)!r}).write_text(json.dumps(dict(path=str(client),source=client.read_text())))\n')
            self.assertEqual(demo.run_controlled_recovery([sys.executable,str(launch),'--client-script','unused'],
                'turtlebot3-occupied-a-probe-v1'),0)
            value=json.loads(record.read_text())
            self.assertIn('main(task="recovery"',value['source'])
            self.assertIn('turtlebot3-occupied-a-probe-v1',value['source'])
            self.assertFalse(Path(value['path']).exists())

    def test_packaged_controlled_proposals_complete_without_fabricated_settlement(self):
        executable = Path(os.environ['COMBINATION_AGENT_PREFIX']) / 'bin/robot-agent-navigation-controlled'
        self.assertTrue(executable.is_file())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            endpoint, audit = root/'nav.sock', root/'audit.json'
            with (root/'owner.log').open('w+') as owner_log, (root/'agent.log').open('w+') as agent_log:
                owner = subprocess.Popen([sys.executable, str(Path(__file__).with_name('navigation_owner.py')),
                    str(endpoint), str(audit)], stdout=owner_log, stderr=subprocess.STDOUT)
                try:
                    until = time.monotonic()+5
                    while not endpoint.exists() and owner.poll() is None and time.monotonic() < until:
                        time.sleep(.01)
                    self.assertTrue(endpoint.exists(), 'owner did not listen')
                    result = subprocess.run([sys.executable, '-m', 'robot_agent.navigation_cli',
                        '--endpoint', str(endpoint), '--output', str(root/'agent'),
                        '--model', 'controlled-tutorial-no-model', '--executable', str(executable)],
                        stdout=agent_log, stderr=subprocess.STDOUT, timeout=10)
                    agent_log.seek(0)
                    self.assertEqual(result.returncode, 0, agent_log.read())
                    self.assertEqual(owner.wait(timeout=5), 0)
                    self.assertFalse(endpoint.exists())
                    report = json.loads((root/'agent/report.json').read_text())
                    self.assertEqual(report['status'], 'completed')
                    self.assertEqual(report['task_verdict'], 'unassessed')
                    self.assertEqual(report['native_cleanup'], 'unknown')
                    self.assertEqual(report['execution_cleanup'], 'pending')
                    self.assertEqual([r['answer']['action'] for r in report['decisions']],
                                     ['visit_a', 'visit_b', 'observed_complete'])
                    self.assertTrue(all(r['accepted'] for r in report['decisions']))
                    facts = json.loads(audit.read_text())
                    self.assertEqual(facts['records'][0]['receipt']['settlement'], 'settled')
                    self.assertEqual(facts['records'][1]['receipt']['settlement'], 'pending')
                    for path in (root/'agent/decisions').glob('*/process.json'):
                        child = json.loads(path.read_text())
                        self.assertTrue(child['reaped'])
                        with self.assertRaises(ProcessLookupError):
                            os.kill(child['pid'], 0)
                finally:
                    if owner.poll() is None:
                        owner.kill()
                    owner.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
