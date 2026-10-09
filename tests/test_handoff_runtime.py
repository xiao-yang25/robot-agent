"""Private shared assembly with original ALOHA policy; no model or physics."""
import json
import threading
import time
import unittest
from unittest.mock import patch

from robot_agent._handoff_runtime import _HandoffCalls, run_handoff
from robot_agent.handoff import Budget, HOLD, TRANSFER
from test_handoff import DecisionFixture, SessionFixture


class OwnedSession(SessionFixture):
    def __init__(self):
        super().__init__()
        self.owner = threading.get_ident()
        self.closed = threading.Event()

    def record(self):
        if threading.get_ident() != self.owner:
            raise AssertionError('Session crossed its creating owner')

    def observe(self):
        self.record()
        return super().observe()

    def capabilities(self):
        self.record()
        return super().capabilities()

    def submit(self, *args, **kwargs):
        self.record()
        return super().submit(*args, **kwargs)

    def status(self, request):
        self.record()
        return super().status(request)

    def cancel(self, request):
        self.record()
        return super().cancel(request)

    def close(self):
        self.record()
        self.closed.set()


class HandoffRuntimeTests(unittest.TestCase):
    def run_task(self, backend=None, configure=lambda session: None, **options):
        def factory():
            self.session = OwnedSession()
            configure(self.session)
            return self.session
        return run_handoff(factory, lambda: backend or DecisionFixture(), **options)

    def test_normal_preserves_steps_measurements_release_and_actual_owners(self):
        owners = []
        def decision(context, observation):
            owners.append(threading.get_ident())
            self.assertNotIn('contacts', observation)
            self.assertNotIn('qpos', observation)
        report = self.run_task(DecisionFixture(decision))
        self.assertEqual(report['status'], 'completed', report)
        self.assertEqual(report['task_verdict'], 'unassessed')
        self.assertEqual(report['visual_assessment'], 'observed_success')
        self.assertEqual([row['skill'] for row in report['operations']], [TRANSFER, HOLD])
        self.assertEqual([row['steps'] for row in report['operations']], [400, 50])
        self.assertEqual([args['expected_observation']['sequence'] for _, args in self.session.submissions], [0, 400])
        self.assertEqual([row['receipt']['authority_disposition'] for row in report['operations']], ['released', 'released'])
        self.assertTrue(report['coordination']['resources_closed'])
        self.assertEqual(report['cleanup'], 'confirmed')
        self.assertTrue(self.session.closed.is_set())
        self.assertEqual(len(set(owners)), 1)
        self.assertNotEqual(owners[0], self.session.owner)
        self.assertNotEqual(owners[0], threading.get_ident())

    def test_changed_episode_rejects_hold_from_old_observation(self):
        def change(context, observation):
            if context['phase'] == 'after_transfer':
                self.session.epoch += 1
        report = self.run_task(DecisionFixture(change))
        self.assertEqual(report['status'], 'needs_help', report)
        self.assertIn('observation changed', report['reason'])
        self.assertEqual(len(self.session.submissions), 1)
        self.assertEqual(report['cleanup'], 'confirmed')

    def test_new_measurement_drives_help_and_zero_hold(self):
        def change(context, observation):
            if context['phase'] == 'prepare':
                self.session.picture = 2
        report = self.run_task(DecisionFixture(change))
        self.assertEqual(report['status'], 'needs_help')
        self.assertEqual(len(self.session.submissions), 1)
        self.assertEqual(report['decisions'][-1]['answer']['action'], 'help')

    def test_pending_transfer_release_blocks_hold_and_cancels_original(self):
        report = self.run_task(configure=lambda session: setattr(session, 'settlement', 'pending'))
        self.assertEqual(report['status'], 'needs_help', report)
        self.assertEqual(len(self.session.submissions), 1)
        self.assertEqual(self.session.cancellations, [self.session.submissions[0][0]])
        self.assertEqual(report['interrupted_operation']['receipt']['settlement'], 'pending')
        self.assertEqual(report['cleanup'], 'confirmed')

    def test_stopped_waiting_decision_cannot_add_hold_and_io_closes_independently(self):
        entered, stop, release = (threading.Event() for _ in range(3))
        reports = []
        def decision(context, observation):
            if context['phase'] == 'after_transfer':
                entered.set()
                if not release.wait(3):
                    raise AssertionError('test did not release decision')
        caller = threading.Thread(target=lambda: reports.append(self.run_task(
            DecisionFixture(decision), stop_requested=stop.is_set)))
        caller.start()
        try:
            self.assertTrue(entered.wait(3))
            stop.set()
            self.assertTrue(self.session.closed.wait(2))
            self.assertFalse(release.is_set())
        finally:
            release.set()
            caller.join(3)
        self.assertFalse(caller.is_alive())
        report = reports[0]
        self.assertEqual(report['status'], 'cancelled', report)
        self.assertEqual(len(self.session.submissions), 1)
        # Transfer already released. Unlike final navigation B, no active native
        # obligation remains for a cancellation request at this boundary.
        self.assertEqual(self.session.cancellations, [])
        self.assertTrue(report['coordination']['resources_closed'])
        self.assertFalse(any(row['context']['phase'] == 'after_transfer' for row in report['decisions']))

    def test_effect_before_stopped_response_retains_original_and_never_replays(self):
        entered, stop, release = (threading.Event() for _ in range(3))
        reports = []
        def configure(session):
            original = session.submit
            def submit(request, **kwargs):
                value = original(request, **kwargs)
                entered.set()
                if not release.wait(3):
                    raise AssertionError('test did not release submit')
                return value
            session.submit = submit
        caller = threading.Thread(target=lambda: reports.append(self.run_task(
            configure=configure, stop_requested=stop.is_set)))
        caller.start()
        try:
            self.assertTrue(entered.wait(3))
            stop.set()
        finally:
            release.set()
            caller.join(3)
        self.assertFalse(caller.is_alive())
        report = reports[0]
        self.assertEqual(report['status'], 'cancelled', report)
        self.assertEqual(len(self.session.submissions), 1)
        request = self.session.submissions[0][0]
        self.assertEqual(self.session.cancellations, [request])
        self.assertEqual(report['interrupted_operation']['request_id'], request)
        late = next(row for row in report['coordination']['late_completions'] if row['method'] == 'submit')
        self.assertEqual(late['value']['request_id'], request)
        self.assertEqual(report['cleanup'], 'confirmed')

    def test_unknown_inflight_report_retains_original_skill_and_observation(self):
        entered, stop, release = (threading.Event() for _ in range(3))
        reports = []
        def configure(session):
            original = session.submit
            def submit(request, **kwargs):
                value = original(request, **kwargs)
                entered.set()
                if not release.wait(3):
                    raise AssertionError('test did not release submit')
                return value
            session.submit = submit
        caller = threading.Thread(target=lambda: reports.append(self.run_task(
            configure=configure, stop_requested=stop.is_set, cleanup_seconds=.03)))
        caller.start()
        try:
            self.assertTrue(entered.wait(3))
            stop.set()
            caller.join(2)
            self.assertFalse(caller.is_alive())
            report = reports[0]
            self.assertEqual(report['operation_outcome'], 'unknown')
            self.assertEqual(report['cleanup'], 'unconfirmed')
            self.assertFalse(report['coordination']['resources_closed'])
            call = next(row for row in report['coordination']['late_completions'] if row['method'] == 'submit')
            request, args = self.session.submissions[0]
            self.assertEqual(call['association'], {'request_id': request, 'skill': TRANSFER,
                'steps': 400, 'observation_reference': args['expected_observation']})
            self.assertTrue(call['started'])
            self.assertEqual(call['state'], 'claimed')
        finally:
            release.set()
            caller.join(3)
            for thread in threading.enumerate():
                if thread.ident == self.session.owner:
                    thread.join(3)
                    self.assertFalse(thread.is_alive())
        self.assertTrue(self.session.closed.is_set())

    def test_caller_delay_does_not_refresh_operation_budget(self):
        original = _HandoffCalls.submit
        def delayed(calls, request, **kwargs):
            time.sleep(.03)
            return original(calls, request, **kwargs)
        with patch.object(_HandoffCalls, 'submit', delayed):
            report = self.run_task(budget=Budget(operation_seconds=.01))
        self.assertEqual(report['status'], 'needs_help', report)
        self.assertFalse(self.session.submissions)
        self.assertEqual(report['cleanup'], 'confirmed')

    def test_stopped_observation_report_is_serializable_and_labels_omitted_rgb(self):
        entered, stop, release = (threading.Event() for _ in range(3))
        reports = []
        def configure(session):
            original = session.observe
            def observe():
                value = original()
                entered.set()
                if not release.wait(3):
                    raise AssertionError('test did not release observation')
                return value
            session.observe = observe
        caller = threading.Thread(target=lambda: reports.append(self.run_task(
            configure=configure, stop_requested=stop.is_set)))
        caller.start()
        try:
            self.assertTrue(entered.wait(3))
            stop.set()
        finally:
            release.set()
            caller.join(3)
        self.assertFalse(caller.is_alive())
        report = reports[0]
        self.assertEqual(report['status'], 'cancelled', report)
        self.assertFalse(self.session.submissions)
        # The same serialization used by the actual CLI must succeed even when
        # a raw camera observation arrives after its caller was withdrawn.
        saved = json.loads(json.dumps(report))
        value = next(row['value'] for row in saved['coordination']['late_completions']
                     if row['method'] == 'observe')
        self.assertEqual((value['epoch'], value['sequence']), (0, 0))
        self.assertEqual(value['stage'], 'transfer_ready')
        self.assertNotIn('rgb', value)
        self.assertEqual(value['rgb_retention'], 'omitted_from_task_report')
        self.assertEqual(report['cleanup'], 'confirmed')

    def test_prestart_stop_and_expiry_create_no_resources(self):
        created = []
        factory = lambda: created.append(True)
        report = run_handoff(factory, factory, stop_requested=lambda: True)
        self.assertEqual(report['status'], 'cancelled')
        self.assertEqual(report['cleanup'], 'unconfirmed')
        self.assertTrue(report['coordination']['resources_closed'])
        report = run_handoff(factory, factory, budget=Budget(task_seconds=.001), started_at=time.monotonic()-1)
        self.assertEqual(report['status'], 'needs_help')
        self.assertFalse(created)

    def test_provider_start_failure_and_session_close_error_stay_distinct(self):
        def fail():
            raise ValueError('provider not ready')
        sessions = []
        def factory():
            session = OwnedSession()
            sessions.append(session)
            return session
        report = run_handoff(factory, fail)
        self.assertEqual(report['status'], 'needs_help', report)
        self.assertTrue(sessions[0].closed.is_set())
        self.assertEqual(report['cleanup'], 'confirmed')
        self.assertFalse(report['coordination']['resources_closed'])
        def configure(session):
            original = session.close
            def close():
                original()
                raise OSError('worker cleanup not confirmed')
            session.close = close
        report = self.run_task(configure=configure)
        self.assertEqual(report['status'], 'completed')
        self.assertEqual(report['cleanup'], 'unconfirmed')
        self.assertIn('worker cleanup not confirmed', report['cleanup_error'])
        self.assertFalse(report['coordination']['resources_closed'])


if __name__ == '__main__':
    unittest.main()
