"""Navigation task boundaries: stale proposals cannot become fresh authority."""
from copy import deepcopy
import unittest

from robot_agent.navigation import MAP, PROFILE, SITES, NavigationBudget, NavigationTask


class SessionFixture:
    def __init__(self):
        self.pose, self.stamp, self.counter = [-2., -.5], 1., 0
        self.epoch, self.session_id = 0, 'session'
        self.submissions, self.cancellations, self.records = [], [], {}
        self.available, self.valid = True, True
        self.pending_a, self.revoked, self.mismatch, self.ambiguous, self.reject = False, False, False, False, False
        self.after_observe = lambda: None

    def observe(self):
        self.counter += 1
        self.stamp += .1
        raw = {'epoch': self.epoch, 'map_id': MAP, 'frame': 'map', 'valid': self.valid,
               'pose': list(self.pose), 'sample_sim_seconds': self.stamp,
               'sensor_health': {'localization': True, 'clock_age': .01,
                                 'streams': [[self.stamp, .01, .01]] * 2},
               'reference': {'session_id': self.session_id, 'observation_id': str(self.counter),
                             'epoch': self.epoch, 'map_id': MAP, 'frame': 'map'},
               'contacts': 'must not reach model', 'physical_truth': 'must not reach model'}
        self.after_observe()
        return raw

    def capabilities(self):
        return {'skill': 'navigation.visit_site', 'profile': PROFILE, 'map_id': MAP, 'frame': 'map',
                'sites': ['A', 'B'], 'available': self.available, 'maximum_deadline_ms': 147000}

    def submit(self, request_id, **args):
        self.submissions.append((request_id, deepcopy(args)))
        if self.reject:
            return {'state': 'rejected', 'request_id': request_id}
        if args['expected_observation']['observation_id'] != str(self.counter):
            raise AssertionError('expired original reference was used instead of revalidated reference')
        op = len(self.submissions)
        row = {'request_id': request_id, 'site': args['site'], 'skill': 'navigation.visit_site',
               'observation_reference': deepcopy(args['expected_observation']),
               'operation_id': op, 'state': 'running', 'target': deepcopy(SITES[args['site']]),
               'receipt': {'authority': {'operation_id': op, 'binding': {'provider': 'scoped-nav2', 'domain': 'exclusive-waffle-drive', 'revision': 1, 'generation': 1}},
                           'native_outcome': 'pending', 'authority_disposition': 'current'}, 'result': None}
        self.records[request_id] = row
        if self.ambiguous:
            raise RuntimeError('submission response lost')
        return deepcopy(row)

    def status(self, request_id):
        row = self.records[request_id]
        site = row['site']
        self.pose = SITES[site][:2]
        row.update(goal_id='a' * 32, result={'stage': site, 'goal_id': 'a' * 32})
        row['receipt'].update(native_identity='a' * 32, result_reference=request_id,
                              native_acceptance='accepted', native_outcome='succeeded', output='accepted',
                              settlement='settled' if site == 'A' and not self.pending_a else 'pending',
                              authority_disposition='released' if site == 'A' and not self.pending_a else 'current')
        row['state'] = 'finished' if site == 'A' and not self.pending_a else 'running'
        if site == 'B':
            self.available = False
        if self.revoked:
            row['receipt']['authority_disposition'] = 'revoked'
        if self.mismatch:
            row['result']['goal_id'] = 'b' * 32
        return deepcopy(row)

    def cancel(self, request):
        self.cancellations.append(request)
        return {'intent_received': True, 'closure': 'unknown'}


class Backend:
    def __init__(self, callback=lambda context, observation: None):
        self.callback, self.seen = callback, []

    def decide(self, context, observation, deadline, stop):
        if set(observation) != {'reference', 'pose', 'sample_sim_seconds', 'sensor_health'}:
            raise AssertionError('measurement whitelist was bypassed')
        self.seen.append(deepcopy(observation))
        answer = {'task_id': context['task_id'], 'phase': context['phase'],
                  'observation_reference': deepcopy(context['observation_reference']),
                  'action': {'prepare': 'visit_a', 'after_a': 'visit_b', 'final': 'observed_complete'}[context['phase']],
                  'reason': 'Controlled test proposal'}
        replacement = self.callback(context, observation)
        return replacement if replacement is not None else answer


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.session = SessionFixture()
        self.now = 0.

    def task(self, backend=None, **kwargs):
        def sleep(seconds):
            self.now += seconds
        return NavigationTask(backend or Backend(), clock=lambda: self.now, sleep=sleep, **kwargs)

    def test_startup_time_counts_towards_task_budget(self):
        self.now = 5.
        result = self.task(budget=NavigationBudget(task_seconds=4), started_at=0.).run(self.session)
        self.assertEqual(result['status'], 'needs_help')
        self.assertFalse(self.session.submissions)

    def test_normal_uses_new_reference_after_model_and_keeps_b_pending(self):
        backend = Backend()
        task = self.task(backend)
        result = task.run(self.session)
        self.assertEqual(result['status'], 'completed', result)
        self.assertEqual([row['site'] for row in result['operations']], ['A', 'B'])
        self.assertEqual(result['operations'][0]['receipt']['authority_disposition'], 'released')
        self.assertEqual(result['operations'][1]['receipt']['settlement'], 'pending')
        self.assertEqual(result['task_verdict'], 'unassessed')
        self.assertEqual(result['execution_cleanup'], 'pending')
        self.assertTrue(result['requires_connection_close'])
        self.assertEqual(backend.seen[1]['pose'], SITES['A'][:2])
        self.assertEqual(backend.seen[2]['pose'], SITES['B'][:2])
        for index, (_, args) in enumerate(self.session.submissions):
            original = result['decisions'][index]['context']['observation_reference']
            self.assertNotEqual(original['observation_id'], args['expected_observation']['observation_id'])
        with self.assertRaises(ValueError):
            task.run(self.session)

    def test_nested_backend_mutation_cannot_change_expected_binding(self):
        def mutate(context, observation):
            context['observation_reference']['epoch'] = 8
            return {**context, 'action': 'visit_a', 'reason': 'mutated'}
        result = self.task(Backend(mutate)).run(self.session)
        self.assertEqual(result['status'], 'needs_help')
        self.assertEqual(result['decisions'][0]['context']['observation_reference']['epoch'], 0)
        self.assertFalse(self.session.submissions)

    def test_changed_pose_epoch_or_session_admits_nothing(self):
        for kind in ('pose', 'epoch', 'session', 'invalid'):
            with self.subTest(kind=kind):
                self.session = SessionFixture()
                def change(context, observation):
                    if kind == 'pose': self.session.pose[0] += .1
                    if kind == 'epoch': self.session.epoch += 1
                    if kind == 'session': self.session.session_id = 'other'
                    if kind == 'invalid': self.session.valid = False
                result = self.task(Backend(change)).run(self.session)
                self.assertEqual(result['status'], 'needs_help')
                self.assertFalse(self.session.submissions)

    def test_late_or_cancelled_proposal_has_zero_effects(self):
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled):
                self.session = SessionFixture()
                stopped = [False]
                def change(context, observation):
                    stopped[0] = cancelled
                    self.now += 31
                result = self.task(Backend(change), stop_requested=lambda: stopped[0]).run(self.session)
                self.assertEqual(result['status'], 'cancelled' if cancelled else 'needs_help')
                self.assertFalse(self.session.submissions)

    def test_pending_a_times_out_and_never_admits_b(self):
        self.session.pending_a = True
        result = self.task(budget=NavigationBudget(operation_seconds=.5)).run(self.session)
        self.assertEqual(result['status'], 'needs_help')
        self.assertEqual(len(self.session.submissions), 1)
        self.assertEqual(self.session.cancellations, [self.session.submissions[0][0]])
        self.assertEqual(result['cancel_response']['closure'], 'unknown')

    def test_revoked_or_wrong_native_result_never_admits_b(self):
        for kind in ('revoked', 'mismatch'):
            with self.subTest(kind=kind):
                self.session = SessionFixture()
                setattr(self.session, kind, True)
                result = self.task().run(self.session)
                self.assertEqual(result['status'], 'needs_help')
                self.assertEqual(len(self.session.submissions), 1)
                self.assertEqual(len(self.session.cancellations), 1)

    def test_ambiguous_submission_is_not_retried_and_retains_exact_cancel(self):
        self.session.ambiguous = True
        result = self.task().run(self.session)
        self.assertEqual(result['status'], 'needs_help')
        self.assertEqual(len(self.session.submissions), 1)
        request = self.session.submissions[0][0]
        self.assertEqual(self.session.cancellations, [request])
        self.assertEqual(result['interrupted_operation']['request_id'], request)

    def test_refused_fresh_reference_never_retries(self):
        self.session.reject = True
        result = self.task().run(self.session)
        self.assertEqual(result['status'], 'needs_help')
        self.assertEqual(len(self.session.submissions), 1)
        self.assertFalse(self.session.cancellations)

    def test_help_after_a_never_submits_b(self):
        def help_after(context, observation):
            if context['phase'] == 'after_a':
                return {'task_id': context['task_id'], 'phase': context['phase'],
                        'observation_reference': context['observation_reference'], 'action': 'help', 'reason': 'unclear'}
        result = self.task(Backend(help_after)).run(self.session)
        self.assertEqual(result['status'], 'needs_help')
        self.assertEqual(len(self.session.submissions), 1)

    def test_final_help_preserves_b_cancellation_obligation(self):
        def help_final(context, observation):
            if context['phase'] == 'final':
                return {'task_id': context['task_id'], 'phase': context['phase'],
                        'observation_reference': context['observation_reference'], 'action': 'help', 'reason': 'unclear'}
        result = self.task(Backend(help_final)).run(self.session)
        self.assertEqual(result['status'], 'needs_help')
        self.assertEqual(self.session.cancellations, [self.session.submissions[-1][0]])
        self.assertEqual(result['interrupted_operation']['receipt']['settlement'], 'pending')


if __name__ == '__main__':
    unittest.main()
