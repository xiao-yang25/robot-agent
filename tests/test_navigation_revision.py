"""Business revision boundaries; synthetic native facts, no stop-time claim."""
from copy import deepcopy
import unittest

from robot_agent.navigation import NavigationBudget, SITES
from robot_agent.navigation_revision import RevisionNavigationTask, IDENTITY_FIELDS, PROFILE
from test_navigation import SessionFixture


class Proposal:
    def __init__(self, callback=lambda context, answer: None):
        self.contexts, self.callback = [], callback

    def decide(self, context, observation, deadline, stopped):
        self.contexts.append(deepcopy(context))
        if set(observation) != {'reference', 'pose', 'sample_sim_seconds', 'sensor_health'}:
            raise AssertionError('measurement whitelist changed')
        answer = dict(task_id=context['task_id'], phase=context['phase'],
                      observation_reference=deepcopy(context['observation_reference']),
                      action=context['allowed_actions'][0], reason='controlled proposal')
        if 'revision_instruction' in context:
            answer['revision_id'] = context['revision_instruction']['revision_id']
        self.callback(context, answer)
        return answer


class Provider:
    def __init__(self, action=None, callback=lambda context, answer: None):
        self.action, self.callback, self.contexts, self.deadlines = action, callback, [], []

    def poll(self, context, deadline, stopped):
        self.contexts.append(deepcopy(context)); self.deadlines.append(deadline)
        answer = None if self.action is None else {**{k: context[k] for k in IDENTITY_FIELDS}, 'action': self.action}
        self.callback(context, answer)
        return answer


class MovingSession(SessionFixture):
    def __init__(self, now):
        super().__init__()
        self.now, self.cancel_at, self.finish_at = now, None, 3
        self.close_delay, self.close_outcome, self.events = .3, 'cancelled', []

    def capabilities(self):
        return {**super().capabilities(), 'profile': PROFILE}

    def status(self, request):
        row = self.records[request]
        if row['site'] == 'B' or (self.cancel_at is None and self.now() >= self.finish_at):
            return super().status(request)
        row['goal_id'] = 'a'*32
        receipt = row['receipt']
        receipt.update(native_identity=row['goal_id'], native_acceptance='accepted',
                       native_outcome='pending', settlement='pending', output='pending', expiry_observed_at=None)
        if self.cancel_at is None:
            self.pose[0] = -2 + .3*self.now()
        else:
            receipt['authority_disposition'] = 'revoked'
            if self.now()-self.cancel_at >= self.close_delay:
                row['state'] = 'finished'
                receipt.update(native_outcome=self.close_outcome, settlement='settled', authority_disposition='released',
                               output='not_delivered', output_non_delivery_reason='no_output' if self.close_outcome == 'cancelled' else 'authority_revoked',
                               result_reference='' if self.close_outcome == 'cancelled' else request)
                self.events.append('released')
        return deepcopy(row)

    def observe(self):
        result = super().observe()
        result['sample_sim_seconds'] = 1+self.now()
        return result

    def cancel(self, request):
        self.events.append('cancel')
        self.cancel_at = self.now() if self.cancel_at is None else self.cancel_at
        return super().cancel(request)

    def submit(self, request, **args):
        if args['site'] == 'B': self.events.append('B')
        return super().submit(request, **args)


class RevisionTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.
        self.session = MovingSession(lambda: self.now)
        self.stopped = False

    def task(self, provider=None, proposal=None, **kwargs):
        def sleep(seconds): self.now += seconds
        return RevisionNavigationTask(proposal or Proposal(), provider or Provider(),
            clock=lambda: self.now, sleep=sleep, stop_requested=lambda: self.stopped, **kwargs)

    def test_no_instruction_completes_only_a_with_one_unrefreshed_window(self):
        provider, proposal = Provider(), Proposal()
        report = self.task(provider, proposal).run(self.session)
        self.assertEqual(report['status'], 'completed', report)
        self.assertEqual(report['completed_sites'], ['A'])
        self.assertEqual(proposal.contexts[-1]['completion_site'], 'A')
        self.assertEqual([c['phase'] for c in proposal.contexts], ['prepare','final'])
        self.assertGreater(len(provider.contexts), 1)
        self.assertTrue(all(c == provider.contexts[0] for c in provider.contexts))
        self.assertEqual(len(set(provider.deadlines)), 1)
        self.assertFalse(self.session.cancellations)
        self.assertEqual(len(self.session.submissions), 1)

    def test_window_expires_once_and_no_measured_motion_never_calls_provider(self):
        self.session.finish_at = 25
        provider = Provider()
        report = self.task(provider).run(self.session)
        self.assertEqual(report['status'], 'completed', report)
        self.assertLess(self.now-provider.deadlines[0], 16)
        self.assertGreater(self.now, provider.deadlines[0])
        self.assertEqual(len(set(provider.deadlines)), 1)
        self.assertTrue(report['revision']['window_closed'])
        self.setUp()
        observe = self.session.observe
        def stationary():
            raw = observe(); raw['pose'] = [-2, -.5] if self.now < 3 else SITES['A'][:2]
            return raw
        self.session.observe = stationary
        provider = Provider('redirect_b')
        report = self.task(provider).run(self.session)
        self.assertEqual(report['status'], 'completed', report)
        self.assertFalse(provider.contexts)
        self.assertFalse(self.session.cancellations)

    def test_stop_cancels_exact_a_waits_release_and_is_not_arrival_or_model_success(self):
        provider, proposal = Provider('stop'), Proposal()
        report = self.task(provider, proposal).run(self.session)
        self.assertEqual(report['status'], 'stopped_by_instruction', report)
        self.assertEqual(report['completed_sites'], [])
        self.assertEqual(len(proposal.contexts), 1)
        self.assertEqual(self.session.cancellations, [report['operations'][0]['request_id']])
        self.assertEqual(report['operations'][0]['receipt']['native_outcome'], 'cancelled')
        self.assertEqual(report['operations'][0]['receipt']['authority_disposition'], 'released')
        self.assertEqual(report['native_cleanup'], 'unknown')
        self.assertEqual(report['task_verdict'], 'unassessed')
        self.assertLess(self.session.pose[0], 0)
        self.assertEqual(len(provider.contexts), 1)

    def test_redirect_release_precedes_model_and_exactly_one_fresh_b(self):
        def model(context, answer):
            if context['phase'] == 'after_revision':
                self.assertIn('released', self.session.events)
                self.session.events.append('model')
        provider = Provider('redirect_b', lambda c,a: a.update(optional_metadata='ignored'))
        report = self.task(provider, Proposal(model)).run(self.session)
        self.assertEqual(report['status'], 'completed', report)
        self.assertEqual(report['completed_sites'], ['B'])
        self.assertLess(self.session.events.index('cancel'), self.session.events.index('model'))
        self.assertLess(self.session.events.index('model'), self.session.events.index('B'))
        self.assertNotIn('optional_metadata', report['revision']['instruction'])
        self.assertEqual(report['operations'][1]['observation_reference'], report['decisions'][1]['revalidated_observation']['reference'])
        self.assertEqual(report['operations'][1]['receipt']['settlement'], 'pending')
        self.assertEqual(len(provider.contexts), 1)

    def test_raced_native_success_stays_success_and_does_not_count_a_as_visited(self):
        self.session.close_outcome = 'succeeded'
        report = self.task(Provider('redirect_b')).run(self.session)
        self.assertEqual(report['status'], 'completed', report)
        self.assertEqual(report['operations'][0]['receipt']['native_outcome'], 'succeeded')
        self.assertEqual(report['completed_sites'], ['B'])

    def test_foreign_or_invalid_instruction_ignored_without_cancel_or_b(self):
        for key, wrong in (('revision_id','foreign'), ('request_id','other'), ('operation_id',True),
                           ('goal_id','b'*32), ('epoch',True), ('session_id','other'), ('action','visit_c')):
            with self.subTest(key=key):
                self.setUp()
                provider = Provider('redirect_b', lambda c,a: a.update({key:wrong}))
                report = self.task(provider).run(self.session)
                self.assertEqual(report['status'], 'completed', report)
                self.assertFalse(report['revision']['accepted'])
                self.assertGreater(report['revision']['invalid_inputs'], 0)
                self.assertEqual(len(self.session.submissions), 1)
                self.assertFalse(self.session.cancellations)

    def test_expired_reply_and_terminal_race_close_window_without_consuming(self):
        for advance in (3, 10):
            with self.subTest(advance=advance):
                self.setUp()
                def late(c,a): self.now += advance
                provider = Provider('redirect_b', late)
                report = self.task(provider).run(self.session)
                self.assertEqual(report['status'], 'completed', report)
                self.assertEqual(report['completed_sites'], ['A'])
                self.assertFalse(report['revision']['accepted'])
                self.assertEqual(len(provider.contexts), 1)
                self.assertFalse(self.session.cancellations)

    def test_provider_failure_or_global_stop_cancels_a_without_model_or_b(self):
        for mode in ('failure','stop','epoch','invalid_observation'):
            with self.subTest(mode=mode):
                self.setUp()
                def fault(c,a):
                    if mode == 'failure': raise RuntimeError('provider fault')
                    if mode == 'stop': self.stopped = True
                    if mode == 'epoch': self.session.epoch += 1
                    if mode == 'invalid_observation': self.session.valid = False
                proposal = Proposal()
                report = self.task(Provider('redirect_b',fault), proposal).run(self.session)
                self.assertEqual(report['status'], 'cancelled' if mode == 'stop' else 'needs_help', report)
                self.assertEqual(len(self.session.submissions), 1)
                self.assertEqual(len(proposal.contexts), 1)
                self.assertTrue(self.session.cancellations)

    def test_missing_release_cannot_use_cancel_ack_as_b_permission(self):
        self.session.close_delay = 100
        proposal = Proposal()
        report = self.task(Provider('redirect_b'), proposal).run(self.session)
        self.assertEqual(report['status'], 'needs_help', report)
        self.assertEqual(len(self.session.submissions), 1)
        self.assertEqual(len(proposal.contexts), 1)
        self.assertLess(self.now, 17)
        self.assertEqual(report['operations'][0]['receipt']['settlement'], 'pending')

    def test_short_original_operation_budget_clips_window_and_closure(self):
        self.session.close_delay = 5
        provider = Provider('redirect_b')
        report = self.task(provider, budget=NavigationBudget(operation_seconds=1)).run(self.session)
        self.assertEqual(report['status'], 'needs_help', report)
        self.assertEqual(provider.deadlines, [1])
        self.assertLess(self.now, 1.2)
        self.assertEqual(len(self.session.submissions), 1)

    def test_model_identity_release_loss_scene_change_and_global_stop_never_submit_b(self):
        for mode in ('identity','release','scene','stop','late'):
            with self.subTest(mode=mode):
                self.setUp()
                def bad(context, answer):
                    if context['phase'] != 'after_revision': return
                    if mode == 'identity': answer['revision_id'] = 'other'
                    if mode == 'release': self.session.close_delay = 100
                    if mode == 'scene': self.session.pose[0] += .2
                    if mode == 'stop': self.stopped = True
                    if mode == 'late': self.now += 30
                report = self.task(Provider('redirect_b'), Proposal(bad)).run(self.session)
                self.assertEqual(report['status'], 'cancelled' if mode == 'stop' else 'needs_help', report)
                self.assertEqual(len(self.session.submissions), 1)

    def test_ambiguous_b_retains_exact_id_and_never_replays_command_or_a(self):
        def ambiguous(context, answer):
            if context['phase'] == 'after_revision': self.session.ambiguous = True
        provider = Provider('redirect_b')
        report = self.task(provider, Proposal(ambiguous)).run(self.session)
        self.assertEqual(report['status'], 'needs_help', report)
        self.assertEqual(len(self.session.submissions), 2)
        self.assertEqual(self.session.cancellations[-1], self.session.submissions[1][0])
        self.assertEqual(len(provider.contexts), 1)

    def test_missing_expiry_fact_cannot_be_treated_as_confirmed_unexpired_release(self):
        status = self.session.status
        def missing(request):
            record = status(request)
            if self.session.cancel_at is not None:
                record['receipt'].pop('expiry_observed_at', None)
            return record
        self.session.status = missing
        proposal = Proposal()
        report = self.task(Provider('redirect_b'), proposal).run(self.session)
        self.assertEqual(report['status'], 'needs_help', report)
        self.assertEqual(len(self.session.submissions), 1)
        self.assertEqual(len(proposal.contexts), 1)

    def test_old_profile_rejected_before_any_submission(self):
        self.session.capabilities = lambda: SessionFixture.capabilities(self.session)
        report = self.task(Provider('redirect_b')).run(self.session)
        self.assertEqual(report['status'], 'needs_help', report)
        self.assertFalse(self.session.submissions)

    def test_task_cannot_be_replayed(self):
        task = self.task(Provider('stop')); task.run(self.session)
        with self.assertRaises(ValueError): task.run(self.session)


if __name__ == '__main__': unittest.main()
