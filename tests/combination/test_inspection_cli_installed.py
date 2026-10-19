"""Actual installed command/Core/socket; synthetic external image/native edges."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from robot_agent import inspection_cli
import robot_harness


class InstalledInspectionCommandTests(unittest.TestCase):
    def setUp(self):
        for module, name in ((inspection_cli, 'COMBINATION_AGENT_PREFIX'),
                             (robot_harness, 'COMBINATION_HARNESS_PREFIX')):
            self.assertTrue(Path(module.__file__).resolve().is_relative_to(
                Path(os.environ[name]).resolve()), module.__file__)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.endpoint, self.audit = self.root/'nav.sock', self.root/'audit.json'
        self.log = (self.root/'owner.log').open('w+')
        self.addCleanup(self.log.close)
        self.owner = subprocess.Popen([sys.executable, str(Path(__file__).with_name('navigation_owner.py')),
            str(self.endpoint), str(self.audit)], stdout=self.log, stderr=subprocess.STDOUT)
        self.addCleanup(self.reap_owner)
        until = time.monotonic()+5
        while not self.endpoint.exists() and self.owner.poll() is None and time.monotonic() < until:
            time.sleep(.01)
        self.assertTrue(self.endpoint.exists())

    def reap_owner(self):
        try:
            code = self.owner.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.owner.kill(); self.owner.wait(timeout=5)
            self.fail('controlled Owner required forced termination')
        self.log.seek(0)
        self.assertEqual(code, 0, self.log.read())
        self.assertFalse(self.endpoint.exists())

    def run_command(self, scenario):
        ready = self.root/'stop-ready'
        command = [sys.executable, str(Path(__file__).with_name('inspection_command_camera.py')),
            scenario, str(self.endpoint), str(self.root/'task'), str(ready)]
        with (self.root/'command.log').open('w+') as log:
            child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            try:
                if scenario == 'stop':
                    until = time.monotonic()+15
                    while not ready.exists() and child.poll() is None and time.monotonic() < until:
                        time.sleep(.005)
                    self.assertTrue(ready.exists(), 'B sampling was never reached')
                    os.kill(child.pid, signal.SIGINT)
                code = child.wait(timeout=20)
            finally:
                if child.poll() is None:
                    child.kill(); child.wait(timeout=5)
                    self.fail('installed inspection command required forced termination')
            log.seek(0)
            self.assertEqual(code, 0 if scenario in ('normal', 'recheck') else 1, log.read())
        self.reap_owner()
        result = json.loads((self.root/'task/report.json').read_text())
        self.assertEqual(result['application']['decision_provider'], 'rules-no-model')
        self.assertEqual(result['task_verdict'], 'unassessed')
        self.assertEqual(result['native_cleanup'], 'unknown')
        return result, json.loads(self.audit.read_text())

    def test_normal_pixels_complete_only_original_a(self):
        result, facts = self.run_command('normal')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['checks'][0]['classification'], 'normal')
        self.assertEqual([row['site'] for row in facts['records']], ['A'])
        self.assertEqual(facts['records'][0]['receipt']['authority_disposition'], 'released')
        self.assertTrue(result['coordination']['resources_closed'])

    def test_abnormal_pixels_allow_only_one_correlated_b_and_keep_pending(self):
        result, facts = self.run_command('recheck')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual([row['classification'] for row in result['checks']], ['abnormal', 'normal'])
        self.assertEqual([row['site'] for row in facts['records']], ['A', 'B'])
        b = result['operations'][-1]
        self.assertEqual(facts['stops'], [b['request_id']])
        self.assertEqual(facts['records'][-1]['operation_id'], b['operation_id'])
        self.assertEqual(facts['records'][-1]['receipt']['settlement'], 'pending')
        self.assertTrue(result['coordination']['resources_closed'])

    def test_unknown_pixels_help_with_zero_followup(self):
        result, facts = self.run_command('unknown')
        self.assertEqual(result['status'], 'needs_help')
        self.assertEqual(result['checks'][0]['classification'], 'unknown')
        self.assertFalse(result['decisions'])
        self.assertEqual([row['site'] for row in facts['records']], ['A'])
        self.assertFalse(facts['stops'])
        self.assertTrue(result['coordination']['resources_closed'])

    def test_signal_during_b_sampling_cancels_original_b_and_reaps(self):
        result, facts = self.run_command('stop')
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual([row['site'] for row in facts['records']], ['A', 'B'])
        b = result['operations'][-1]
        self.assertEqual(facts['stops'], [b['request_id']])
        self.assertEqual(facts['records'][-1]['operation_id'], b['operation_id'])
        self.assertEqual(facts['records'][-1]['receipt']['authority_disposition'], 'revoked')
        self.assertEqual(facts['records'][-1]['receipt']['settlement'], 'pending')
        self.assertTrue(result['coordination']['resources_closed'])

    def test_completed_observation_with_close_error_is_unsuccessful(self):
        result, facts = self.run_command('close-failure')
        self.assertEqual(result['status'], 'completed')
        self.assertFalse(result['camera_close']['returned'])
        self.assertFalse(result['coordination']['resources_closed'])
        self.assertIn('controlled camera close failure', result['camera_close']['error'])
        self.assertEqual([row['site'] for row in facts['records']], ['A'])


if __name__ == '__main__':
    unittest.main()
