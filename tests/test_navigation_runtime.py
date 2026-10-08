"""Private coordinator with original domain policy; no model or physics."""
import threading
import time
import unittest
from unittest.mock import patch

from robot_agent._navigation_runtime import _NavigationCalls, run_navigation
from robot_agent.navigation import NavigationBudget
from test_navigation import Backend, SessionFixture


class OwnedSession(SessionFixture):
    def __init__(self):
        super().__init__()
        self.owner = threading.get_ident()
        self.threads = []
        self.closed = False

    def record(self):
        self.threads.append(threading.get_ident())
        if self.threads[-1] != self.owner:
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

    def status(self, *args):
        self.record()
        return super().status(*args)

    def cancel(self, *args):
        self.record()
        return super().cancel(*args)

    def close(self):
        self.record()
        self.closed = True
        return {'closure': 'unknown', 'owner_reaped': False}


class NavigationRuntimeTests(unittest.TestCase):
    def run_task(self, backend=None, configure=lambda session: None, **options):
        self.session = None
        def factory():
            self.session = OwnedSession()
            configure(self.session)
            return self.session
        return run_navigation(factory, lambda: backend or Backend(), **options)

    def test_normal_retains_original_navigation_contract_and_owner_close(self):
        report = self.run_task()
        self.assertEqual(report['status'], 'completed', report)
        self.assertEqual([row['site'] for row in report['operations']], ['A', 'B'])
        self.assertEqual(report['operations'][0]['receipt']['authority_disposition'], 'released')
        self.assertEqual(report['operations'][1]['receipt']['settlement'], 'pending')
        self.assertEqual(report['task_verdict'], 'unassessed')
        self.assertEqual(report['native_cleanup'], 'unknown')
        self.assertEqual(report['connection_close'], 'local_closed')
        self.assertTrue(report['coordination']['resources_closed'])
        self.assertTrue(self.session.closed)
        self.assertNotEqual(self.session.owner, threading.get_ident())

    def test_old_observation_rejects_proposal_without_a_submit(self):
        report = self.run_task(Backend(lambda *_: self.session.pose.__setitem__(0, 1.)))
        self.assertEqual(report['status'], 'needs_help', report)
        self.assertFalse(self.session.submissions)
        self.assertTrue(self.session.closed)

    def test_unknown_submit_is_not_replayed_and_cancels_original_request(self):
        report = self.run_task(configure=lambda session: setattr(session, 'ambiguous', True))
        self.assertEqual(report['status'], 'needs_help', report)
        self.assertEqual(len(self.session.submissions), 1)
        request = self.session.submissions[0][0]
        self.assertEqual(self.session.cancellations, [request])
        self.assertEqual(report['interrupted_operation']['request_id'], request)
        self.assertTrue(report['coordination']['resources_closed'])

    def test_decision_wait_does_not_delay_business_stop_or_io_cancel(self):
        entered, stop, cancelled, release = (threading.Event() for _ in range(4))
        decision_threads, reports = [], []
        def decision(context, observation):
            decision_threads.append(threading.get_ident())
            if context['phase'] == 'final':
                entered.set()
                if not release.wait(3):
                    raise AssertionError('test did not release decision')
        def configure(session):
            original = session.cancel
            def cancel(request):
                value = original(request)
                cancelled.set()
                return value
            session.cancel = cancel
        caller = threading.Thread(target=lambda: reports.append(self.run_task(
            Backend(decision), configure=configure, stop_requested=stop.is_set)))
        caller.start()
        try:
            self.assertTrue(entered.wait(3))
            stop.set()
            # Deterministic ordering: cancel is observed while model remains blocked.
            self.assertTrue(cancelled.wait(2))
            self.assertFalse(release.is_set())
        finally:
            release.set()
            caller.join(3)
        self.assertFalse(caller.is_alive())
        report = reports[0]
        self.assertEqual(report['status'], 'cancelled', report)
        self.assertEqual(self.session.cancellations, [self.session.submissions[-1][0]])
        self.assertTrue(report['coordination']['resources_closed'])
        self.assertEqual(len(set(decision_threads)), 1)
        self.assertNotEqual(decision_threads[0], self.session.owner)
        self.assertFalse(any(row['context']['phase'] == 'final' for row in report['decisions']))
        self.assertTrue(any(row['role'] == 'decision' for row in report['coordination']['late_completions']))

    def test_inflight_response_stop_preserves_late_fact_and_original_cancel(self):
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
            release.set()
        finally:
            release.set()
            caller.join(3)
        self.assertFalse(caller.is_alive())
        report = reports[0]
        self.assertEqual(report['status'], 'cancelled', report)
        request = self.session.submissions[0][0]
        self.assertEqual(self.session.cancellations, [request])
        self.assertEqual(len(self.session.submissions), 1)
        self.assertEqual(report['interrupted_operation']['request_id'], request)
        self.assertTrue(report['coordination']['resources_closed'])

    def test_unfinished_submit_report_keeps_original_request_for_reconciliation(self):
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
            self.assertTrue(entered.wait(2))
            stop.set()
            caller.join(1)
            self.assertFalse(caller.is_alive())
            report = reports[0]
            self.assertEqual(report['status'], 'cancelled', report)
            self.assertEqual(report['operation_outcome'], 'unknown')
            self.assertFalse(report['coordination']['resources_closed'])
            self.assertFalse(report['coordination']['owners']['io']['thread_stopped'])
            self.assertEqual(report['operations'], [])
            request, params = self.session.submissions[0]
            pending = report['coordination']['late_completions'][0]
            self.assertEqual(pending['state'], 'claimed')
            self.assertTrue(pending['started'])
            self.assertEqual(pending['association']['request_id'], request)
            self.assertEqual(pending['association']['site'], params['site'])
            self.assertEqual(pending['association']['observation_reference'], params['expected_observation'])
            self.assertEqual(len(self.session.submissions), 1)
        finally:
            release.set()
            caller.join(2)
            if self.session is not None:
                for thread in threading.enumerate():
                    if thread.ident == self.session.owner:
                        thread.join(2)
                self.assertTrue(self.session.closed)

    def test_original_budget_and_pre_start_stop_open_no_resources(self):
        factories = []
        def factory():
            factories.append(True)
            raise AssertionError('resource factory must not run')
        for options, expected in (({'stop_requested': lambda: True}, 'cancelled'),
                                  ({'budget': NavigationBudget(task_seconds=1),
                                    'started_at': time.monotonic() - 2}, 'needs_help')):
            report = run_navigation(factory, factory, **options)
            self.assertEqual(report['status'], expected)
            self.assertEqual(report['connection_close'], 'not_started')
            self.assertTrue(report['coordination']['resources_closed'])
        self.assertFalse(factories)

    def test_caller_delay_before_enqueue_does_not_refresh_operation_budget(self):
        original = _NavigationCalls.submit
        def delayed(calls, request, **kwargs):
            time.sleep(.03)  # Beyond the explicit 10 ms operation budget.
            return original(calls, request, **kwargs)
        with patch.object(_NavigationCalls, 'submit', delayed):
            report = self.run_task(budget=NavigationBudget(operation_seconds=.01))
        self.assertEqual(report['status'], 'needs_help', report)
        self.assertFalse(self.session.submissions)
        self.assertTrue(report['coordination']['resources_closed'])

    def test_partial_start_and_close_failure_keep_cleanup_facts(self):
        def backend_failure():
            raise ValueError('provider not ready')
        session = []
        def factory():
            resource = OwnedSession()
            session.append(resource)
            return resource
        report = run_navigation(factory, backend_failure)
        self.assertEqual(report['status'], 'needs_help', report)
        self.assertTrue(session[0].closed)
        self.assertFalse(report['coordination']['resources_closed'])
        def configure(resource):
            original = resource.close
            def close():
                original()
                raise OSError('native close reply lost')
            resource.close = close
        report = self.run_task(configure=configure)
        self.assertEqual(report['status'], 'completed')
        self.assertEqual(report['connection_close'], 'local_closed')
        self.assertEqual(report['native_cleanup'], 'unknown')
        self.assertFalse(report['coordination']['resources_closed'])
        self.assertIn('native close reply lost', report['close_error'])


if __name__ == '__main__':
    unittest.main()
