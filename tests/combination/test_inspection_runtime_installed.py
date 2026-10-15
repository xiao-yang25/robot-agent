"""Installed complete caller with real public Session/Core, controlled camera/native facts."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from robot_agent import _inspection_runtime as runtime
from robot_harness import NavigationSession
from inspection_fixture import BindingCamera, Camera


class InstalledLoopTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(runtime.__file__).resolve().is_relative_to(
            Path(os.environ['COMBINATION_AGENT_PREFIX']).resolve()))
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.endpoint, self.audit = self.root/'nav.sock', self.root/'audit.json'
        self.log = (self.root/'owner.log').open('w+')
        self.addCleanup(self.log.close)
        self.owner = subprocess.Popen([sys.executable, str(Path(__file__).with_name('navigation_owner.py')),
            str(self.endpoint), str(self.audit)], stdout=self.log, stderr=subprocess.STDOUT)
        self.addCleanup(self.reap)
        until = time.monotonic()+5
        while not self.endpoint.exists() and self.owner.poll() is None and time.monotonic() < until:
            time.sleep(.01)
        self.assertTrue(self.endpoint.exists())
        self.camera = Camera()

    def reap(self):
        try:
            code = self.owner.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.owner.kill(); self.owner.wait(timeout=5)
            self.fail('synthetic Core owner required forced termination')
        self.log.seek(0)
        self.assertEqual(code, 0, self.log.read())
        self.assertFalse(self.endpoint.exists())

    def run_task(self, a_status, provider=runtime.RuleDecision, interpreter=None):
        result = runtime.run_inspection(lambda: NavigationSession(self.endpoint),
            camera_factory=lambda: self.camera, decision_factory=provider,
            interpreter=interpreter or (lambda frame: (a_status if frame.site == 'A' else 'normal', 1., 1.)))
        self.assertTrue(result['coordination']['resources_closed'], result)
        self.assertEqual(result['native_cleanup'], 'unknown')
        self.assertEqual(result['task_verdict'], 'unassessed')
        json.dumps(result)
        self.reap()
        return result, json.loads(self.audit.read_text())

    def test_installed_whole_loop_normal_a_has_one_actual_core_request(self):
        result, facts = self.run_task('normal')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['outcome'], 'normal_observed')
        self.assertEqual([row['site'] for row in facts['records']], ['A'])
        self.assertEqual(facts['records'][0]['receipt']['authority_disposition'], 'released')
        self.assertFalse(facts['stops'])
        self.assertTrue(self.camera.closed)

    def test_installed_whole_loop_single_b_keeps_a_anomaly_and_pending_context(self):
        result, facts = self.run_task('abnormal')
        self.assertEqual(result['status'], 'completed', result)
        self.assertEqual(result['outcome'], 'recheck_normal')
        self.assertEqual([row['classification'] for row in result['checks']], ['abnormal', 'normal'])
        self.assertEqual([row['site'] for row in facts['records']], ['A', 'B'])
        b = result['operations'][-1]
        self.assertEqual(facts['stops'], [b['request_id']])
        self.assertEqual(facts['records'][-1]['operation_id'], b['operation_id'])
        self.assertEqual(facts['records'][-1]['receipt']['settlement'], 'pending')
        self.assertFalse(b['reusable'])

    def test_installed_source_loss_during_b_decision_cancels_exact_core_operation(self):
        waiting = threading.Event()
        class Wait(runtime.RuleDecision):
            def decide(self, key, record, deadline, stop):
                if record.site == 'B':
                    waiting.set()
                    while not stop() and time.monotonic() < deadline:
                        time.sleep(.001)
                return super().decide(key, record, deadline, stop)
        self.camera.on_pump = lambda: self.camera.source.events.invalidate('controlled image loss') if waiting.is_set() else None
        result, facts = self.run_task('abnormal', Wait)
        self.assertEqual(result['status'], 'needs_help')
        b = result['operations'][-1]
        self.assertEqual(facts['stops'], [b['request_id']])
        self.assertEqual(facts['records'][-1]['operation_id'], b['operation_id'])
        self.assertEqual(facts['records'][-1]['receipt']['authority_disposition'], 'revoked')
        self.assertEqual(facts['records'][-1]['receipt']['settlement'], 'pending')
        self.assertEqual(len(facts['records']), 2)
        self.assertTrue(result['decisions'][-1]['withdrawn'])
        self.assertEqual(len(result['checks']), 2)

    def check_camera_fault(self, fault):
        self.camera = BindingCamera(fault)
        def forbidden(frame):
            self.fail('Unusable camera image reached interpretation')
        result, facts = self.run_task('abnormal', interpreter=forbidden)
        self.assertEqual(result['status'], 'needs_help', result)
        self.assertIsNone(result['runtime_error'])
        self.assertIsNotNone(self.camera.opened)
        self.assertGreater(self.camera.bad_inputs, 0)
        with self.camera.source.events.lock:
            reason = self.camera.source.events.failure
        self.assertEqual(reason, 'inspection sample association invalid' if fault == 'wrong-association'
                         else 'inspection source health or clock expired')
        self.assertEqual(result['samples'], 0)
        for key in ('checks', 'decisions', 'reading_diagnostics', 'cancellation_responses'):
            self.assertFalse(result[key])
        self.assertEqual([row['site'] for row in facts['records']], ['A'])
        self.assertEqual(len(result['operations']), 1)
        self.assertFalse(facts['stops'])
        operation = result['operations'][0]
        record = facts['records'][0]
        self.assertEqual((record['request_id'], record['operation_id']),
                         (operation['request_id'], operation['operation_id']))
        self.assertEqual(record['receipt']['settlement'], 'settled')
        self.assertEqual(record['receipt']['authority_disposition'], 'released')
        self.assertTrue(operation['reusable'])
        self.assertTrue(self.camera.closed)

    def test_installed_missing_window_images_have_only_released_a(self):
        self.check_camera_fault('missing-frame')

    def test_installed_old_window_images_have_only_released_a(self):
        self.check_camera_fault('stale-frame')

    def test_installed_wrong_window_pose_has_only_released_a(self):
        self.check_camera_fault('wrong-association')


if __name__ == '__main__':
    unittest.main()
