"""Complete caller/owners with synthetic camera and public Session-shaped facts."""
import json
from dataclasses import replace
import threading
import time
import unittest

from robot_agent._inspection_runtime import RuleDecision, run_inspection
from robot_agent._inspection_policy import Proposal
from combination.inspection_fixture import Camera
from robot_agent.navigation import NavigationBudget
from test_navigation import SessionFixture




class Session(SessionFixture):
    def __init__(self):
        super().__init__()
        self.closed = False
        self.io_threads = []

    def close(self):
        self.io_threads.append(threading.current_thread())
        self.closed = True
        return {'closure': 'unknown', 'owner_reaped': False}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.camera, self.session = Camera(), Session()
        self.stop = threading.Event()
        self.labels = {'A': 'normal', 'B': 'normal'}
        self.provider = RuleDecision()

    def run_task(self, **changes):
        args = dict(camera_factory=lambda: self.camera, decision_factory=lambda: self.provider,
            budget=NavigationBudget(task_seconds=2., operation_seconds=1., decision_seconds=.6),
            stop_requested=self.stop.is_set, startup_seconds=.6, cleanup_seconds=.5,
            interpreter=lambda frame: (self.labels[frame.site], 1., 1.))
        args.update(changes)
        return run_inspection(lambda: self.session, **args)

    def assert_closed(self, result):
        self.assertTrue(self.camera.closed)
        self.assertTrue(result['coordination']['resources_closed'], result)
        self.assertTrue(self.session.closed)
        self.assertTrue(all(not row.is_alive() for row in self.session.io_threads))
        self.assertEqual(result['native_cleanup'], 'unknown')
        self.assertEqual(result['task_verdict'], 'unassessed')

    def test_normal_a_ends_once_with_no_b_and_no_pixel_or_truth_in_report(self):
        result = self.run_task()
        self.assertEqual(result['status'], 'completed', result)
        self.assertEqual(result['outcome'], 'normal_observed')
        self.assertEqual([args['site'] for _, args in self.session.submissions], ['A'])
        self.assertEqual([row['classification'] for row in result['checks']], ['normal'])
        self.assertNotIn('pixels', json.dumps(result))
        self.assertNotIn('physical_truth', json.dumps(result))
        self.assert_closed(result)

    def test_abnormal_a_one_b_retains_history_pending_and_business_result(self):
        self.labels['A'] = 'abnormal'
        result = self.run_task()
        self.assertEqual(result['status'], 'completed', result)
        self.assertEqual(result['outcome'], 'recheck_normal')
        self.assertEqual([args['site'] for _, args in self.session.submissions], ['A', 'B'])
        self.assertEqual([row['classification'] for row in result['checks']], ['abnormal', 'normal'])
        self.assertFalse(result['operations'][-1]['reusable'])
        b = result['operations'][-1]['request_id']
        self.assertEqual(result['execution_records'][b]['record']['receipt']['settlement'], 'pending')
        self.assert_closed(result)

    def test_unknown_at_either_site_never_admits_a_successor(self):
        for site in ('A', 'B'):
            with self.subTest(site=site):
                self.setUp()
                self.labels.update(A='unknown' if site == 'A' else 'abnormal', B='unknown')
                result = self.run_task()
                self.assertEqual(result['status'], 'needs_help', result)
                self.assertEqual([args['site'] for _, args in self.session.submissions], ['A'] if site == 'A' else ['A', 'B'])
                self.assertEqual(result['checks'][-1]['classification'], 'unknown')
                self.assert_closed(result)

    def waiting_provider(self, site):
        started = threading.Event()
        parent = self
        class Waiting(RuleDecision):
            def decide(self, key, record, deadline, stop):
                if record.site == site:
                    started.set()
                    while not stop() and time.monotonic() < deadline:
                        time.sleep(.001)
                return super().decide(key, record, deadline, stop)
        parent.provider = Waiting()
        return started

    def test_source_fault_during_a_decision_keeps_anomaly_and_zero_b(self):
        self.labels['A'] = 'abnormal'
        started = self.waiting_provider('A')
        self.camera.on_pump = lambda: self.camera.source.events.invalidate('controlled image loss') if started.is_set() else None
        result = self.run_task()
        self.assertEqual(result['status'], 'needs_help', result)
        self.assertEqual([args['site'] for _, args in self.session.submissions], ['A'])
        self.assertEqual(result['checks'][0]['classification'], 'abnormal')
        self.assertTrue(result['decisions'][0]['withdrawn'])
        self.assertFalse(self.session.cancellations)  # A was already actually released.
        self.assert_closed(result)

    def test_source_fault_during_b_decision_cancels_original_pending_b(self):
        self.labels['A'] = 'abnormal'
        started = self.waiting_provider('B')
        self.camera.on_pump = lambda: self.camera.source.events.invalidate('controlled image loss') if started.is_set() else None
        result = self.run_task()
        self.assertEqual(result['status'], 'needs_help', result)
        self.assertEqual(len(result['checks']), 2)
        self.assertEqual(self.session.cancellations, [result['operations'][-1]['request_id']])
        self.assertTrue(result['decisions'][-1]['withdrawn'])
        self.assert_closed(result)

    def test_continuous_new_image_health_allows_historical_record_during_slow_decision(self):
        class Slow(RuleDecision):
            def decide(self, key, record, deadline, stop):
                time.sleep(.12)
                return super().decide(key, record, deadline, stop)
        self.provider = Slow()
        result = self.run_task()
        self.assertEqual(result['status'], 'completed', result)
        self.assertGreater(self.camera.pumps, 10)
        self.assertFalse(result['decisions'][0]['withdrawn'])
        self.assertIsNone(self.camera.source._latest)
        self.assertIsNone(self.camera.source._reader)
        self.assert_closed(result)

    def progress_gate(self):
        entered = threading.Event()
        original = self.session.status
        def status(request):
            entered.set()
            time.sleep(.03)
            return original(request)
        self.session.status = status
        return entered

    def test_camera_loss_after_confirmed_acceptance_allows_independent_a_to_finish(self):
        entered = self.progress_gate()
        self.camera.on_pump = lambda: self.camera.source.events.invalidate('camera independent of navigation') if entered.is_set() else None
        result = self.run_task()
        self.assertEqual(result['status'], 'needs_help', result)
        self.assertTrue(result['operations'][0]['reusable'])
        self.assertFalse(result['checks'])
        self.assertFalse(self.session.cancellations)
        self.assert_closed(result)

    def test_explicit_stop_during_original_io_retains_late_arrival_and_cancels_once(self):
        entered = self.progress_gate()
        self.camera.on_pump = lambda: self.stop.set() if entered.is_set() else None
        result = self.run_task()
        self.assertEqual(result['status'], 'cancelled', result)
        a = result['operations'][0]
        self.assertGreater(a['operation_id'], 0)
        self.assertTrue(a['reusable'])
        self.assertEqual(self.session.cancellations, [a['request_id']])
        self.assertFalse(result['checks'])
        self.assert_closed(result)

    def test_ambiguous_submit_has_one_send_and_original_cancel_without_b(self):
        self.session.ambiguous = True
        result = self.run_task()
        self.assertEqual(result['status'], 'needs_help', result)
        self.assertEqual(len(self.session.submissions), 1)
        self.assertEqual(self.session.cancellations, [result['operations'][0]['request_id']])
        self.assert_closed(result)

    def test_model_error_does_not_admit_b_or_claim_goal_change(self):
        self.labels['A'] = 'abnormal'
        class Broken:
            def decide(self, *args): raise RuntimeError('controlled provider failure')
        self.provider = Broken()
        result = self.run_task()
        self.assertEqual(result['status'], 'needs_help')
        self.assertIn('controlled provider failure', result['reason'])
        self.assertEqual(len(self.session.submissions), 1)
        self.assert_closed(result)

    def test_wrong_decision_key_does_not_admit_b(self):
        self.labels['A'] = 'abnormal'
        class Wrong:
            def decide(self, key, record, *args):
                return Proposal(replace(key, check_reference='foreign-window'), 'visit_b', 'wrong key')
        self.provider = Wrong()
        result = self.run_task()
        self.assertEqual(result['status'], 'needs_help')
        self.assertEqual(len(self.session.submissions), 1)
        self.assert_closed(result)

    def test_navigation_conditions_fail_while_model_waits_and_invalidate_its_decision(self):
        started = self.waiting_provider('A')
        self.camera.on_pump = lambda: setattr(self.session, 'valid', False) if started.is_set() else None
        result = self.run_task()
        self.assertEqual(result['status'], 'needs_help', result)
        self.assertTrue(result['decisions'][0]['withdrawn'])
        self.assertEqual(len(self.session.submissions), 1)
        self.assert_closed(result)

    def test_source_fault_in_actual_submit_preparation_has_zero_navigation_effects(self):
        self.session.after_observe = lambda: self.camera.source.events.invalidate('source failed before submit') if self.session.counter >= 2 else None
        result = self.run_task()
        self.assertEqual(result['status'], 'needs_help')
        self.assertFalse(self.session.submissions)
        self.assertFalse(self.session.cancellations)
        self.assert_closed(result)

    def test_ignoring_withdrawal_keeps_late_answer_serializable_and_never_admits_b(self):
        self.labels['A'] = 'abnormal'
        started = threading.Event()
        class Late:
            def decide(self, key, record, *args):
                started.set(); time.sleep(.03)
                return Proposal(key, 'visit_b', 'late answer ignores withdrawal')
        self.provider = Late()
        self.camera.on_pump = lambda: self.camera.source.events.invalidate('image loss') if started.is_set() else None
        result = self.run_task()
        self.assertEqual(result['status'], 'needs_help')
        self.assertEqual(len(self.session.submissions), 1)
        late = [row for row in result['coordination']['late_completions'] if row['role'] == 'decision']
        self.assertEqual(late[0]['value']['action'], 'visit_b')
        json.dumps(result)
        self.assert_closed(result)

    def test_uncooperative_provider_is_draining_not_closed_and_can_be_joined_later(self):
        started, release = threading.Event(), threading.Event()
        threads = []
        class Held:
            def decide(self, key, record, *args):
                threads.append(threading.current_thread()); started.set()
                if not release.wait(2.): raise TimeoutError('controlled provider gate')
                return Proposal(key, 'report_normal', 'late held answer')
        self.provider = Held()
        self.camera.on_pump = lambda: self.camera.source.events.invalidate('image loss') if started.is_set() else None
        try:
            result = self.run_task(cleanup_seconds=.02)
            self.assertEqual(result['status'], 'needs_help')
            self.assertFalse(result['coordination']['resources_closed'])
            self.assertFalse(result['coordination']['owners']['decision']['thread_stopped'])
            self.assertTrue(threads[0].is_alive())
            self.assertTrue(self.camera.closed)
            self.assertEqual(len(self.session.submissions), 1)
        finally:
            release.set()
            for thread in threads:
                thread.join(1.)
                self.assertFalse(thread.is_alive())

    def test_startup_counts_original_budget_and_does_not_prepare_after_expiry(self):
        created = []
        result = self.run_task(started_at=time.monotonic()-3,
                               camera_factory=lambda: created.append(True))
        self.assertEqual(result['status'], 'needs_help')
        self.assertFalse(created)
        self.assertFalse(self.session.submissions)
        self.assertTrue(result['coordination']['resources_closed'])

    def test_close_error_keeps_original_receipts_and_still_closes_camera(self):
        def close(): raise OSError('controlled close failure')
        self.session.close = close
        result = self.run_task()
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(self.camera.closed)
        self.assertFalse(result['coordination']['resources_closed'])
        self.assertEqual(result['coordination']['owners']['io']['close'], 'error')
        self.assertTrue(result['execution_records'])

    def test_interpretation_crossing_normal_deadline_keeps_prior_window_history(self):
        self.camera = Camera(window_seconds=.08)
        samples = []
        def interpret(frame):
            samples.append(frame.sequence)
            if len(samples) == 4:
                time.sleep(.09)
            return 'normal', 1., 1.
        result = self.run_task(interpreter=interpret)
        self.assertEqual(result['status'], 'completed', result)
        self.assertEqual(result['checks'][0]['samples'], 3)
        self.assertEqual(result['checks'][0]['classification'], 'normal')
        self.assertIsNone(result['runtime_error'])
        self.assert_closed(result)

    def test_interpreter_fault_with_original_progress_keeps_a_serializable_report(self):
        self.camera = Camera(window_seconds=.25)
        progress = threading.Event()
        original = self.session.status
        count = 0
        def status(request):
            nonlocal count
            count += 1
            if count == 2:
                progress.set()
            return original(request)
        self.session.status = status
        def interpret(frame):
            if progress.is_set():
                raise ValueError('controlled interpretation failure during original progress')
            return 'normal', 1., 1.
        result = self.run_task(interpreter=interpret)
        self.assertTrue(progress.is_set())
        self.assertEqual(result['status'], 'needs_help')
        self.assertIn('controlled interpretation failure', result['runtime_error'])
        self.assertGreater(result['operations'][0]['operation_id'], 0)
        json.dumps(result)
        self.assert_closed(result)

    def test_budget_expires_between_reservation_and_authorization_without_cleanup_exception(self):
        result = self.run_task(budget=NavigationBudget(task_seconds=2., operation_seconds=1e-9))
        self.assertEqual(result['status'], 'needs_help', result)
        self.assertFalse(self.session.submissions)
        self.assertFalse(self.session.cancellations)
        self.assertIn('invalid original inspection admission', result['runtime_error'])
        self.assertEqual(result['cancellation_responses'][0]['response']['closure'], 'not_authorized')
        json.dumps(result)
        self.assert_closed(result)


if __name__ == '__main__':
    unittest.main()
