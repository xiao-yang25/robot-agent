"""Business commands change a released checkpoint, never unknown native work."""
from copy import deepcopy
import unittest

from robot_agent.navigation import NavigationBudget, GOAL
from robot_agent.navigation_checkpoint import CheckpointNavigationTask
from test_navigation import SessionFixture


class Proposal:
    def __init__(self, change=lambda context, answer: None):
        self.contexts, self.deadlines, self.change = [], [], change

    def decide(self, context, observation, deadline, stopped):
        self.contexts.append(deepcopy(context))
        self.deadlines.append(deadline)
        answer = dict(task_id=context['task_id'], phase=context['phase'],
                      observation_reference=deepcopy(context['observation_reference']),
                      action=context['allowed_actions'][0], reason='controlled proposal')
        if 'checkpoint_instruction' in context:
            answer['checkpoint_id'] = context['checkpoint_instruction']['checkpoint_id']
        self.change(context, answer)
        return answer


class Provider:
    def __init__(self, action='continue_b', change=lambda context, answer: None):
        self.action, self.change, self.contexts, self.deadlines = action, change, [], []

    def request(self, context, deadline, stopped):
        self.contexts.append(deepcopy(context))
        self.deadlines.append(deadline)
        answer = {key: context[key] for key in ('task_id', 'checkpoint_id', 'session_id', 'epoch', 'map_id', 'frame')}
        answer['action'] = self.action
        self.change(context, answer)
        return answer


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.session, self.now, self.stopped = SessionFixture(), 0., False

    def task(self, provider=None, proposal=None, **kwargs):
        return CheckpointNavigationTask(proposal or Proposal(), provider or Provider(),
            clock=lambda: self.now, sleep=lambda seconds: setattr(self, 'now', self.now+seconds),
            stop_requested=lambda: self.stopped, **kwargs)

    def assert_a_only(self, report):
        self.assertEqual(report['status'], 'needs_help', report)
        self.assertEqual([row[1]['site'] for row in self.session.submissions], ['A'])
        self.assertEqual(report['operations'][0]['receipt']['authority_disposition'], 'released')
        self.assertFalse(self.session.cancellations)
        self.assertEqual(report['task_verdict'], 'unassessed')

    def test_finish_at_a_is_completion_of_new_goal_and_keeps_cleanup_unknown(self):
        provider, proposal = Provider('finish_at_a'), Proposal()
        task = self.task(provider, proposal)
        report = task.run(self.session)
        self.assertEqual(report['status'], 'completed', report)
        self.assertNotEqual(report['goal'], GOAL)
        self.assertEqual(report['completed_sites'], ['A'])
        self.assertEqual(report['execution_cleanup'], 'unknown')
        self.assertEqual(report['native_cleanup'], 'unknown')
        self.assertEqual(report['task_verdict'], 'unassessed')
        self.assertTrue(report['requires_connection_close'])
        self.assertEqual(report['operations'][0]['receipt']['authority_disposition'], 'released')
        self.assertEqual(len(self.session.submissions), 1)
        self.assertFalse(self.session.cancellations)
        self.assertEqual([c['phase'] for c in proposal.contexts], ['prepare', 'after_a'])
        self.assertEqual(len(provider.contexts), 1)
        self.assertEqual(proposal.contexts[1]['allowed_actions'], ['finish_at_a', 'help'])
        with self.assertRaises(ValueError):
            task.run(self.session)
        self.assertEqual(len(provider.contexts), 1)

    def test_continue_b_consumes_command_and_fresh_reference_once(self):
        provider, proposal = Provider(), Proposal()
        report = self.task(provider, proposal).run(self.session)
        self.assertEqual(report['status'], 'completed', report)
        self.assertEqual(report['completed_sites'], ['A', 'B'])
        self.assertEqual(report['operations'][1]['receipt']['settlement'], 'pending')
        self.assertEqual(report['execution_cleanup'], 'pending')
        self.assertEqual(len(provider.contexts), 1)
        command = report['checkpoint']['instruction']
        self.assertEqual(command['checkpoint_id'], proposal.contexts[1]['checkpoint_instruction']['checkpoint_id'])
        self.assertNotIn('checkpoint_instruction', proposal.contexts[0])
        self.assertNotIn('checkpoint_instruction', proposal.contexts[2])
        self.assertEqual([args['site'] for _, args in self.session.submissions], ['A', 'B'])
        reference = self.session.submissions[1][1]['expected_observation']
        self.assertEqual(reference, report['decisions'][1]['revalidated_observation']['reference'])
        self.assertNotEqual(reference, proposal.contexts[1]['observation_reference'])

    def test_missing_foreign_or_unsupported_command_never_defaults_to_b(self):
        for key, value in (('task_id','old-task'), ('checkpoint_id','old-checkpoint'),
                           ('session_id','other'), ('epoch',True), ('map_id','other'),
                           ('frame','odom'), ('action','visit_c')):
            with self.subTest(key=key):
                self.session = SessionFixture()
                provider = Provider(change=lambda context, answer: answer.update({key: value}))
                proposal = Proposal()
                report = self.task(provider, proposal).run(self.session)
                self.assert_a_only(report)
                self.assertFalse(report['checkpoint']['accepted'])
                self.assertEqual(len(proposal.contexts), 1)
        for missing in (None, {}, {'action':'continue_b'}):
            self.session = SessionFixture()
            provider = Provider()
            provider.request = lambda *args: missing
            self.assert_a_only(self.task(provider).run(self.session))

    def test_instruction_window_and_shared_phase_budget_do_not_reset(self):
        provider = Provider(change=lambda *args: setattr(self, 'now', self.now+9))
        def slow_model(context, answer):
            if context['phase'] == 'after_a':
                self.now += 22
        report = self.task(provider, Proposal(slow_model)).run(self.session)
        self.assert_a_only(report)
        self.assertTrue(report['checkpoint']['accepted'])
        self.assertFalse(report['decisions'][-1]['accepted'])
        self.assertAlmostEqual(provider.deadlines[0], 10.1)

    def test_instruction_at_exact_window_deadline_is_rejected(self):
        provider = Provider()
        def late(context, answer):
            self.now = provider.deadlines[-1]
        provider.change = late
        report = self.task(provider).run(self.session)
        self.assert_a_only(report)
        self.assertFalse(report['checkpoint']['accepted'])

    def test_shorter_task_budget_also_bounds_instruction_and_model(self):
        provider, proposal = Provider(), Proposal()
        report = self.task(provider, proposal, budget=NavigationBudget(task_seconds=2)).run(self.session)
        self.assertEqual(report['status'], 'completed', report)
        self.assertEqual(provider.deadlines[0], 2)
        self.assertEqual(proposal.deadlines[1], 2)

    def test_provider_context_mutation_and_unknown_metadata_do_not_change_authority(self):
        def mutate(context, answer):
            context['checkpoint_id'] = 'replacement'
            answer['optional_metadata'] = object()
        report = self.task(Provider(change=mutate)).run(self.session)
        self.assertEqual(report['status'], 'completed', report)
        self.assertNotIn('optional_metadata', report['checkpoint']['instruction'])
        self.assertNotEqual(report['checkpoint']['instruction']['checkpoint_id'], 'replacement')

    def test_proposal_must_echo_current_checkpoint_and_cannot_change_business_action(self):
        for change in (lambda answer: answer.update(checkpoint_id='old'),
                       lambda answer: answer.pop('checkpoint_id'),
                       lambda answer: answer.update(action='visit_b')):
            self.session = SessionFixture()
            def mutate(context, answer):
                if context['phase'] == 'after_a': change(answer)
            report = self.task(Provider('finish_at_a'), Proposal(mutate)).run(self.session)
            self.assert_a_only(report)
            self.assertFalse(report['decisions'][-1]['accepted'])

    def test_unreleased_a_never_requests_instruction(self):
        self.session.pending_a = True
        provider = Provider()
        report = self.task(provider, budget=NavigationBudget(operation_seconds=.5)).run(self.session)
        self.assertEqual(report['status'], 'needs_help')
        self.assertFalse(provider.contexts)
        self.assertEqual(self.session.cancellations, [self.session.submissions[0][0]])

    def test_feedback_or_released_association_loss_after_instruction_prevents_b(self):
        for kind in ('epoch','session','pose','valid','goal'):
            with self.subTest(kind=kind):
                self.session = SessionFixture()
                provider = Provider()
                def lose(context, answer):
                    if kind == 'epoch': self.session.epoch += 1
                    if kind == 'session': self.session.session_id = 'other'
                    if kind == 'pose':
                        original = self.session.observe
                        def moved():
                            row = original()
                            row['pose'][0] += .1
                            return row
                        self.session.observe = moved
                    if kind == 'valid': self.session.valid = False
                    if kind == 'goal': self.session.mismatch = True
                provider.change = lose
                report = self.task(provider).run(self.session)
                self.assert_a_only(report)

    def test_cancellation_at_instruction_or_after_model_does_not_submit_b(self):
        for during_model in (False, True):
            self.session, self.stopped = SessionFixture(), False
            provider = Provider(change=lambda *args: setattr(self, 'stopped', not during_model))
            def cancel(context, answer):
                if during_model and context['phase'] == 'after_a': self.stopped = True
            report = self.task(provider, Proposal(cancel)).run(self.session)
            self.assertEqual(report['status'], 'cancelled', report)
            self.assertEqual(len(self.session.submissions), 1)
            self.assertFalse(self.session.cancellations)

    def test_ambiguous_b_retains_exact_request_without_replaying_a_or_command(self):
        provider = Provider(change=lambda *args: setattr(self.session, 'ambiguous', True))
        report = self.task(provider).run(self.session)
        self.assertEqual(report['status'], 'needs_help')
        self.assertEqual([args['site'] for _, args in self.session.submissions], ['A','B'])
        self.assertEqual(self.session.cancellations, [self.session.submissions[1][0]])
        self.assertEqual(len(provider.contexts), 1)
        self.assertEqual(report['interrupted_operation']['request_id'], self.session.submissions[1][0])

    def test_finish_at_a_needs_no_fresh_b_admission_capability(self):
        report = self.task(Provider('finish_at_a', change=lambda *args: setattr(self.session, 'available', False))).run(self.session)
        self.assertEqual(report['status'], 'completed', report)
        self.assertEqual(len(self.session.submissions), 1)


if __name__ == '__main__':
    unittest.main()
