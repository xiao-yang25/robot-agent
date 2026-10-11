"""Bounded metadata/control turns and original effects under slow decisions."""
import threading
import time
import unittest

from robot_agent._task_events import EventInbox
from robot_agent._task_runtime import Coordinator, Owner
from robot_agent._navigation_runtime import run_navigation
from robot_agent.navigation import NavigationBudget
from test_navigation import Backend
from test_navigation_runtime import OwnedSession


class EventTests(unittest.TestCase):
    def test_actual_io_owner_completes_while_model_owner_remains_blocked(self):
        entered, release = threading.Event(), threading.Event()
        coordinator = Coordinator('task', lambda: False, 1, events=EventInbox())
        class Model:
            def decide(self):
                entered.set()
                if not release.wait(2):
                    raise AssertionError('model gate not released')
                return {'action': 'B'}
        class Io:
            def status(self):
                return {'request_id': 'original-A', 'outcome': 'unknown'}
        owners = [Owner(coordinator.exchange, 'decision', Model),
                  Owner(coordinator.exchange, 'io', Io)]
        for owner in owners:
            owner.start()
        try:
            deadline = time.monotonic() + 2
            decision = coordinator.begin('decision', 'decide', (), {}, deadline=deadline)
            self.assertTrue(entered.wait(1))
            io = coordinator.begin('io', 'status', (), {}, deadline=deadline,
                                   association={'request_id': 'original-A'})
            with coordinator.exchange.condition:
                self.assertTrue(coordinator.exchange.condition.wait_for(
                    lambda: io.state == 'completed', timeout=1))
            completed = coordinator.poll()
            self.assertEqual(completed['io'].value['outcome'], 'unknown')
            self.assertNotIn('decision', completed)
            self.assertEqual(decision.state, 'claimed')
            self.assertFalse(release.is_set())
        finally:
            release.set()
            for owner in owners:
                self.assertTrue(owner.finish(time.monotonic() + 2)['thread_stopped'])

    def test_latest_metadata_is_bounded_and_fault_cannot_be_overwritten(self):
        inbox = EventInbox()
        for sequence in range(10000):
            self.assertTrue(inbox.observe(1, sequence, str(sequence)))
        self.assertFalse(inbox.observe(1, 9999, 'duplicate'))
        self.assertFalse(inbox.observe(0, 10000, 'old-generation'))
        inbox.invalidate('camera failed')
        inbox.invalidate('replacement must not erase original')
        self.assertFalse(inbox.observe(1, 10000, 'restored'))
        stop, failure, latest = inbox.take()
        self.assertFalse(stop)
        self.assertEqual(failure, 'camera failed')
        self.assertEqual(latest.reference, '9999')
        self.assertEqual(inbox.take(), (False, 'camera failed', None))
        with self.assertRaises(ValueError):
            inbox.observe(True, 1, 'invalid')
        with self.assertRaises(ValueError):
            inbox.observe(1, 10001, 'x' * 129)

    def test_generation_change_is_latched_without_restarting_source(self):
        inbox = EventInbox()
        inbox.observe(3, 9, 'original')
        self.assertFalse(inbox.observe(4, 0, 'new-generation'))
        self.assertFalse(inbox.observe(3, 10, 'late-original'))
        self.assertEqual(inbox.take()[1], 'event source generation changed')

    def test_fault_withdraws_decision_but_preserves_original_io_completion(self):
        inbox = EventInbox()
        events = []
        coordinator = Coordinator('task', lambda: False, 1, events=inbox,
                                  on_event=lambda kind, value: events.append(kind))
        deadline = time.monotonic() + 2
        decision = coordinator.begin('decision', 'decide', (), {}, deadline=deadline)
        io = coordinator.begin('io', 'status', (), {}, deadline=deadline,
                               association={'request_id': 'original-A'})
        self.assertIs(coordinator.exchange.claim('decision'), decision)
        self.assertIs(coordinator.exchange.claim('io'), io)
        coordinator.exchange.complete('io', io, {'outcome': 'unknown'}, None)
        inbox.observe(1, 0, 'fact')
        inbox.invalidate('dependency lost')
        completed = coordinator.poll()
        self.assertEqual(events, ['invalidated', 'observation'])
        self.assertTrue(decision.withdrawn)
        self.assertFalse(io.withdrawn)
        self.assertEqual(completed['io'].association, {'request_id': 'original-A'})
        self.assertEqual(completed['io'].value, {'outcome': 'unknown'})
        with self.assertRaises(RuntimeError):
            coordinator.begin('decision', 'decide', (), {}, deadline=deadline)
        coordinator.exchange.complete('decision', decision, {'action': 'B'}, None)
        self.assertTrue(coordinator.poll()['decision'].withdrawn)

    def test_stop_precedes_observation_and_zero_new_owner_invocations(self):
        inbox, events = EventInbox(), []
        coordinator = Coordinator('task', lambda: False, 1, events=inbox,
                                  on_event=lambda *event: events.append(event))
        inbox.observe(1, 0, 'fact')
        inbox.stop()
        coordinator.poll()
        call = coordinator.begin('io', 'submit', (), {}, deadline=time.monotonic() + 1)
        self.assertFalse(events)
        self.assertFalse(call.started)
        self.assertIsInstance(coordinator.poll()['io'].error, InterruptedError)

    def test_completed_proposal_becomes_withdrawn_before_consumption(self):
        inbox = EventInbox()
        coordinator = Coordinator('task', lambda: False, 1, events=inbox)
        call = coordinator.begin('decision', 'decide', (), {}, deadline=time.monotonic() + 1)
        coordinator.exchange.claim('decision')
        coordinator.exchange.complete('decision', call, {'action': 'B'}, None)
        inbox.invalidate('association corrected')
        result = coordinator.poll()['decision']
        self.assertEqual(result.value, {'action': 'B'})
        self.assertTrue(result.withdrawn)

    def test_expired_completion_retains_original_value_and_identity(self):
        coordinator = Coordinator('task', lambda: False, 1, events=EventInbox())
        call = coordinator.begin('io', 'submit', (), {}, deadline=time.monotonic() + 1,
                                 association={'request_id': 'original'})
        coordinator.exchange.claim('io')
        coordinator.exchange.complete('io', call, {'accepted': True}, None)
        coordinator.waiting_until['io'] = time.monotonic() - 1
        result = coordinator.poll()['io']
        self.assertTrue(result.withdrawn)
        self.assertEqual(result.value, {'accepted': True})
        self.assertEqual(result.association['request_id'], 'original')

    def test_policy_error_cannot_drop_consumed_io_effects(self):
        def handler(kind, value):
            raise ValueError('unusable observation')
        inbox = EventInbox()
        coordinator = Coordinator('task', lambda: False, 1, events=inbox, on_event=handler)
        call = coordinator.begin('io', 'submit', (), {}, deadline=time.monotonic() + 1,
                                 association={'request_id': 'original'})
        coordinator.exchange.claim('io')
        coordinator.exchange.complete('io', call, {'accepted': True}, None)
        inbox.observe(1, 0, 'bad')
        with self.assertRaisesRegex(ValueError, 'unusable observation'):
            coordinator.poll()
        self.assertEqual(coordinator.late[0]['value'], {'accepted': True})
        self.assertEqual(coordinator.late[0]['association']['request_id'], 'original')


class NavigationEventTests(unittest.TestCase):
    def run_task(self, inbox, backend=None, configure=lambda session: None, **options):
        def factory():
            self.session = OwnedSession()
            configure(self.session)
            return self.session
        return run_navigation(factory, lambda: backend or Backend(), events=inbox, **options)

    def test_unrelated_updates_preserve_existing_navigation_and_pending_scope(self):
        inbox = EventInbox()
        def update(context, observation):
            for sequence in range(1000):
                inbox.observe(1, len(context['phase']) * 1000 + sequence, str(sequence))
        report = self.run_task(inbox, Backend(update))
        self.assertEqual(report['status'], 'completed', report)
        self.assertEqual([row['site'] for row in report['operations']], ['A', 'B'])
        self.assertEqual(report['operations'][-1]['receipt']['settlement'], 'pending')
        self.assertEqual(report['native_cleanup'], 'unknown')
        self.assertTrue(report['coordination']['resources_closed'])
        self.assertIn('latest_context_event', report)

    def test_fault_during_slow_final_decision_cancels_original_before_model_exits(self):
        inbox = EventInbox()
        entered, release, cancelled = (threading.Event() for _ in range(3))
        reports = []
        def decide(context, observation):
            if context['phase'] == 'final':
                entered.set()
                if not release.wait(3):
                    raise AssertionError('model gate not released')
        def configure(session):
            original = session.cancel
            def cancel(request):
                value = original(request)
                cancelled.set()
                return value
            session.cancel = cancel
        caller = threading.Thread(target=lambda: reports.append(
            self.run_task(inbox, Backend(decide), configure)))
        caller.start()
        try:
            self.assertTrue(entered.wait(2))
            inbox.invalidate('localization unavailable')
            for sequence in range(10000):
                inbox.observe(1, sequence, str(sequence))
            self.assertTrue(cancelled.wait(2))
            self.assertFalse(release.is_set())
        finally:
            release.set()
            caller.join(3)
        self.assertFalse(caller.is_alive())
        report = reports[0]
        self.assertEqual(report['status'], 'needs_help', report)
        self.assertEqual(self.session.cancellations, [self.session.submissions[-1][0]])
        self.assertEqual(len(self.session.submissions), 2)
        self.assertFalse(any(row['context']['phase'] == 'final' for row in report['decisions']))
        self.assertTrue(report['coordination']['resources_closed'])
        self.assertTrue(report['coordination']['late_completions'][0]['started'])

    def test_fault_before_first_decision_has_zero_submits_and_no_retry(self):
        inbox = EventInbox()
        backend = Backend(lambda *_: inbox.invalidate('permission changed'))
        report = self.run_task(inbox, backend)
        self.assertEqual(report['status'], 'needs_help', report)
        self.assertEqual(self.session.submissions, [])
        self.assertEqual(len(backend.seen), 1)
        self.assertTrue(report['coordination']['resources_closed'])

    def test_event_stop_during_submit_retains_effect_and_original_cancellation(self):
        inbox = EventInbox()
        def configure(session):
            original = session.submit
            def submit(request, **kwargs):
                result = original(request, **kwargs)
                inbox.stop()
                return result
            session.submit = submit
        report = self.run_task(inbox, configure=configure)
        self.assertEqual(report['status'], 'cancelled', report)
        self.assertEqual(len(self.session.submissions), 1)
        request = self.session.submissions[0][0]
        self.assertEqual(self.session.cancellations, [request])
        original = [row for row in report['coordination']['late_completions']
                    if row['method'] == 'submit'][0]
        self.assertEqual(original['association']['request_id'], request)
        self.assertIsNotNone(original['value'])

    def test_deadline_during_model_wait_is_help_not_user_cancel(self):
        def decision(*_):
            time.sleep(.03)
        report = self.run_task(EventInbox(), Backend(decision),
                               budget=NavigationBudget(decision_seconds=.01))
        self.assertEqual(report['status'], 'needs_help', report)
        self.assertIn('TimeoutError', report['reason'])
        self.assertEqual(self.session.submissions, [])
        self.assertTrue(report['coordination']['resources_closed'])


if __name__ == '__main__':
    unittest.main()
