"""Contract tests: proposals must influence effects and remain tied to fresh state."""

import copy
import unittest

from robot_agent.handoff import Budget, HandoffTask, HOLD, PROFILE, TRANSFER


class SessionFixture:
    def __init__(self):
        self.epoch, self.sequence, self.stage = 0, 0, 'transfer_ready'
        self.submissions, self.cancellations = [], []
        self.records = {}
        self.valid = True
        self.settlement = 'settled'
        self.running = False
        self.refuse = False
        self.picture = 1
        self.after_status = lambda: None
        self.after_observe = lambda: None

    def observe(self):
        result = {'epoch': self.epoch, 'sequence': self.sequence, 'stage': self.stage,
                  'valid': self.valid, 'joints': [0.] * 14, 'sim_seconds': self.sequence * .02,
                  'image': {'shape': [480, 640, 3], 'dtype': 'uint8', 'camera': 'top'},
                  'rgb': bytes([self.picture]) * (480 * 640 * 3),
                  'contacts': 'must never reach the decision backend'}
        self.after_observe()
        return result

    def capabilities(self):
        return {'profile': PROFILE, 'skills': [
            {'skill': TRANSFER, 'available': self.stage == 'transfer_ready'},
            {'skill': HOLD, 'available': self.stage == 'hold_ready'}]}

    def submit(self, request_id, **args):
        self.submissions.append((request_id, args))
        if self.refuse:
            return {'state': 'rejected', 'reason': 'unavailable'}
        self.assert_reference(args['expected_observation'])
        self.sequence += args['steps']
        self.stage = 'hold_ready' if args['skill'] == TRANSFER else 'needs_reset'
        result = {'state': 'finished', 'request_id': request_id, 'skill': args['skill'],
                  'epoch': self.epoch, 'steps': args['steps'], 'operation_id': len(self.submissions),
                  'receipt': {'authority': {'operation_id': len(self.submissions)},
                              'result_reference': request_id,
                              'settlement': self.settlement, 'output': 'accepted',
                              'native_outcome': 'succeeded', 'authority_disposition': 'released'},
                  'result': {'skill': args['skill'], 'epoch': self.epoch, 'steps': args['steps'],
                             'operation_id': len(self.submissions)}}
        if self.running:
            result['state'] = 'running'
        self.records[request_id] = result
        return copy.deepcopy(result)

    def assert_reference(self, reference):
        if reference != {'epoch': self.epoch, 'sequence': self.sequence}:
            raise AssertionError('application submitted against stale state')

    def status(self, request):
        self.after_status()
        return copy.deepcopy(self.records[request])

    def cancel(self, request):
        self.cancellations.append(request)
        return {'state': 'revocation_requested'}

    def reset(self):
        self.epoch += 1
        self.sequence, self.stage = 0, 'transfer_ready'


class DecisionFixture:
    """Test-only measurement-driven decisions; no claim of visual understanding."""
    def __init__(self, hook=lambda context, observation: None):
        self.hook = hook
        self.seen = []

    def decide(self, context, observation, deadline, stop_requested):
        self.seen.append((dict(context), dict(observation)))
        action = {'prepare': 'transfer', 'after_transfer': 'hold', 'final': 'observed_success'}[context['phase']]
        if observation['rgb'][0] == 2:
            action = 'help'
        answer = {k: context[k] for k in ('task_id', 'phase', 'epoch', 'sequence')}
        answer.update(action=action, reason='test measurement proposal')
        change = self.hook(context, observation)
        return answer if change is None else {**answer, **change}


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.session = SessionFixture()
        self.clock_value = 0
        self.stopped = False

    def task(self, backend=None, **kwargs):
        return HandoffTask(backend or DecisionFixture(), clock=lambda: self.clock_value,
                           sleep=lambda _: setattr(self, 'clock_value', self.clock_value + 1),
                           stop_requested=lambda: self.stopped, **kwargs)

    def test_normal_two_operations_distinct_identity_same_episode(self):
        backend = DecisionFixture()
        result = self.task(backend).run(self.session)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['task_verdict'], 'unassessed')
        self.assertEqual(result['visual_assessment'], 'observed_success')
        self.assertEqual([args['skill'] for _, args in self.session.submissions], [TRANSFER, HOLD])
        self.assertEqual([args['expected_observation']['sequence'] for _, args in self.session.submissions], [0, 400])
        self.assertEqual([c['sequence'] for c, _ in backend.seen], [0, 400, 450])
        self.assertEqual(self.session.epoch, 0)
        self.assertNotEqual(*[request for request, _ in self.session.submissions])
        self.assertTrue(all('contacts' not in obs for _, obs in backend.seen))

    def test_new_measurement_changes_hold_submission(self):
        def change(context, observation):
            if context['phase'] == 'prepare':
                self.session.picture = 2
        result = self.task(DecisionFixture(change)).run(self.session)
        self.assertEqual(result['status'], 'needs_help')
        self.assertEqual(len(self.session.submissions), 1)
        self.assertEqual(result['decisions'][-1]['answer']['action'], 'help')

    def test_old_answer_cannot_start_hold(self):
        result = self.task(DecisionFixture(lambda c, o: {'sequence': 0}
                                          if c['phase'] == 'after_transfer' else None)).run(self.session)
        self.assertEqual(len(self.session.submissions), 1)
        self.assertIn('different task', result['reason'])

    def test_cancel_during_decision_blocks_hold(self):
        def cancel(context, observation):
            if context['phase'] == 'after_transfer':
                self.stopped = True
        result = self.task(DecisionFixture(cancel)).run(self.session)
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(len(self.session.submissions), 1)

    def test_expired_decision_blocks_hold(self):
        def expire(context, observation):
            if context['phase'] == 'after_transfer':
                self.clock_value += 60
        result = self.task(DecisionFixture(expire)).run(self.session)
        self.assertEqual(len(self.session.submissions), 1)
        self.assertIn('decision budget', result['reason'])

    def test_epoch_change_during_decision_blocks_hold(self):
        def reset(context, observation):
            if context['phase'] == 'after_transfer':
                self.session.reset()
        result = self.task(DecisionFixture(reset)).run(self.session)
        self.assertEqual(len(self.session.submissions), 1)
        self.assertIn('observation changed', result['reason'])

    def test_capability_query_cannot_extend_decision_deadline(self):
        def near_expiry(context, observation):
            if context['phase'] == 'after_transfer':
                self.clock_value += 59
        original = self.session.capabilities
        def slow_capabilities():
            result = original()
            if self.session.stage == 'hold_ready':
                self.clock_value += 2
            return result
        self.session.capabilities = slow_capabilities
        result = self.task(DecisionFixture(near_expiry)).run(self.session)
        self.assertEqual(len(self.session.submissions), 1)
        self.assertIn('decision expired before submission', result['reason'])

    def test_invalid_observation_no_model_or_operation(self):
        self.session.valid = False
        backend = DecisionFixture()
        result = self.task(backend).run(self.session)
        self.assertEqual(result['status'], 'needs_help')
        self.assertEqual(backend.seen, [])
        self.assertEqual(self.session.submissions, [])

    def test_pending_settlement_blocks_hold(self):
        self.session.settlement = 'pending'
        result = self.task().run(self.session)
        self.assertEqual(result['status'], 'needs_help')
        self.assertEqual(len(self.session.submissions), 1)
        self.assertEqual(len(self.session.cancellations), 1)
        self.assertEqual(result['interrupted_operation']['receipt']['settlement'], 'pending')

    def test_rejected_operation_not_retried(self):
        self.session.refuse = True
        result = self.task().run(self.session)
        self.assertEqual(result['status'], 'needs_help')
        self.assertEqual(len(self.session.submissions), 1)
        self.assertEqual(self.session.cancellations, [])

    def test_operation_deadline_requests_cancel_preserves_pending(self):
        self.session.running = True
        result = self.task(budget=Budget(operation_seconds=2)).run(self.session)
        self.assertEqual(len(self.session.submissions), 1)
        self.assertEqual(len(self.session.cancellations), 1)
        self.assertEqual(result['interrupted_operation']['state'], 'running')
        self.assertIn('operation budget', result['reason'])

    def test_ambiguous_submit_cannot_retry(self):
        original = self.session.submit
        def uncertain(*args, **kwargs):
            original(*args, **kwargs)
            raise TimeoutError('reply lost')
        self.session.submit = uncertain
        result = self.task().run(self.session)
        self.assertEqual(len(self.session.submissions), 1)
        self.assertEqual(len(self.session.cancellations), 1)
        self.assertEqual(result['status'], 'needs_help')

    def test_unsupported_action_never_submits(self):
        result = self.task(DecisionFixture(lambda c, o: {'action': 'reset'})).run(self.session)
        self.assertEqual(self.session.submissions, [])
        self.assertIn('unsupported', result['reason'])

    def test_second_task_requires_operator_reset(self):
        first = self.task()
        self.assertEqual(first.run(self.session)['status'], 'completed')
        with self.assertRaises(ValueError):
            first.run(self.session)
        self.assertEqual(self.task().run(self.session)['status'], 'needs_help')
        self.assertEqual(len(self.session.submissions), 2)
        self.session.reset()
        second = self.task().run(self.session)
        self.assertEqual(second['status'], 'completed')
        self.assertEqual(second['epoch'], 1)

    def test_total_budget_includes_startup(self):
        self.clock_value = 300
        result = self.task(started_at=0).run(self.session)
        self.assertEqual(self.session.submissions, [])
        self.assertIn('task budget', result['reason'])

    def test_receipt_mismatch_cannot_start_hold(self):
        original = self.session.status
        def mismatched(request):
            result = original(request)
            result['result']['operation_id'] += 1
            return result
        self.session.status = mismatched
        result = self.task().run(self.session)
        self.assertEqual(len(self.session.submissions), 1)
        self.assertIn('mismatched', result['reason'])

    def test_receipt_identity_and_reference_required(self):
        for change in ({'authority': {'operation_id': 999}}, {'result_reference': 'old-request'},
                       {'authority': {}}, {'result_reference': None}):
            with self.subTest(change=change):
                session = SessionFixture()
                original = session.status
                def wrong_receipt(request):
                    result = original(request)
                    result['receipt'].update(change)
                    return result
                session.status = wrong_receipt
                result = self.task().run(session)
                self.assertEqual(len(session.submissions), 1)
                self.assertIn('mismatched', result['reason'])


if __name__ == '__main__':
    unittest.main()
