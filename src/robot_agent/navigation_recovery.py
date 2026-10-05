"""One pre-authorized backup after public confirmation of failed A's release."""
from copy import deepcopy
import math
import uuid

from .navigation import ACTIONS, SITES, _NavigationExecution

PROFILE = 'scoped-two-context-nav2-failure-recovery-v1'
FAILURE_FIELDS = ('recovery_id', 'request_id', 'operation_id', 'goal_id')


def native_id(value):
    return (isinstance(value, str) and len(value) == 32
            and all(c in '0123456789abcdef' for c in value))


class RecoveryNavigationTask(_NavigationExecution):
    """Borrow Session and backend; caller owns their resources and close.

    The business goal permits registered B as one backup. Unknown submission,
    cancellation, expiry, lost input or unreleased work never select recovery.
    Failed A is not a visit. Public release is a trusted Owner assertion, not an
    Agent check of ROS closure or a general physical-unreachable classification.
    """
    goal = 'Visit A; if A navigation explicitly fails and is released, choose registered B once or ask for help.'
    profile = PROFILE
    instruction_field = 'failure_context'
    instruction_id = 'recovery_id'

    def __init__(self, decision_backend, **kwargs):
        super().__init__(decision_backend, **kwargs)
        self.a = self.a_admission = self.a_goal = None
        self.completed_site = None
        self.report.update(native_cleanup='unknown', completed_sites=[])

    def preceding_site(self):
        return self.completed_site if self.phase == 'final' else None

    def proposal_context(self):
        return {'completion_site': self.completed_site} if self.phase == 'final' else {}

    def instruction_answer_matches(self, answer, instruction):
        return (type(answer.get('operation_id')) is int
                and all(answer.get(key) == instruction[key] for key in FAILURE_FIELDS))

    def _a_receipt(self, record):
        receipt = self.associated_receipt(record, self.a['request_id'], 'A',
                                         self.a['operation_id'], self.a['observation_reference'])
        reference = record.get('observation_reference', {})
        authority = receipt.get('authority', {})
        if (type(reference.get('epoch')) is not int or record.get('target') != SITES['A']
                or record.get('stage') != 'A' or not native_id(record.get('scope_id'))
                or type(record.get('generation')) is not int or record['generation'] < 1
                or type(authority.get('admitted_at')) is not int
                or type(receipt.get('deadline')) is not int
                or receipt['deadline'] <= authority['admitted_at']):
            raise ValueError('A admission/native context is incomplete')
        identity = (record['scope_id'], record['generation'], authority['admitted_at'], receipt['deadline'])
        if self.a_admission is None:
            self.a_admission = identity
        if identity != self.a_admission:
            raise ValueError('A admission context or original deadline changed')
        if (receipt.get('cancellation_requested_at', 'unknown') is not None
                or receipt.get('expiry_observed_at', 'unknown') is not None
                or receipt.get('authority_disposition') not in ('current', 'released')):
            raise ValueError('A cancelled, expired or lost authority')
        if receipt.get('native_acceptance') == 'accepted':
            goal = record.get('goal_id')
            if not native_id(goal) or receipt.get('native_identity') != goal:
                raise ValueError('A actual native identity is incomplete')
            if self.a_goal is None:
                self.a_goal = goal
            if self.a_goal != goal:
                raise ValueError('A native identity changed')
        elif receipt.get('native_acceptance') != 'pending' or self.a_goal is not None:
            raise ValueError('A native acceptance is rejected, unknown or regressed')
        return receipt

    def _failed_released(self, record):
        receipt = self._a_receipt(record)
        if receipt.get('native_outcome') != 'failed':
            raise ValueError('A no longer has a confirmed native failure')
        if receipt.get('native_acceptance') != 'accepted' or record.get('result') is not None:
            raise ValueError('failed A lacks accepted identity or has contradictory output')
        if receipt.get('authority_disposition') != 'released':
            return False
        if (record.get('state') != 'finished' or receipt.get('settlement') != 'settled'
                or receipt.get('output') != 'not_delivered'
                or receipt.get('output_non_delivery_reason') != 'no_output'
                or receipt.get('result_reference') != ''):
            raise ValueError('released failed A lacks a no-output disposition')
        return True

    def _visit_a(self, session, observation, decision_deadline):
        record, request, operation, deadline = self.start_operation(session, 'A', observation, decision_deadline)
        self.a = dict(request_id=request, operation_id=operation,
                      observation_reference=deepcopy(observation['reference']))
        failed = False
        while True:
            self.check_budget(deadline)
            receipt = self._a_receipt(record)
            outcome = receipt.get('native_outcome')
            if outcome == 'failed':
                failed = True
                if self._failed_released(record):
                    self.active = None
                    self.report['recovery'] = dict(released_a=deepcopy(record), accepted=False)
                    return True
            elif failed:
                raise ValueError('A failed outcome regressed')
            elif self.validate_record(record, request, 'A', operation, observation['reference']):
                self.active = None
                return False
            self.sleep(.1)
            self.check_budget(deadline)
            record = session.status(request)
            self.report['operations'][0] = deepcopy(record)
            self.check_budget(deadline)

    def _release_observation(self, session, deadline, previous=None):
        self.check_budget(deadline)
        record = session.status(self.a['request_id'])
        self.report['operations'][0] = deepcopy(record)
        self.check_budget(deadline)
        if not self._failed_released(record):
            raise ValueError('failed A is no longer confirmed released')
        self.capabilities(session, require_available=True)
        current = self.observe(session)
        self.check_budget(deadline)
        if previous is not None and (current['sample_sim_seconds'] < previous['sample_sim_seconds']
                or math.dist(current['pose'], previous['pose']) > .05):
            raise ValueError('released scene changed during recovery')
        return current

    def _run_steps(self, session):
        action, observation, deadline = self.decide(session)
        if action == 'help':
            self.report.update(status='needs_help', reason='decision_backend_abstained')
            return
        if self._visit_a(session, observation, deadline):
            self.phase = 'after_failure'
            deadline = min(self.deadline, self.clock()+self.budget.decision_seconds)
            previous = self._release_observation(session, deadline)
            context = dict(recovery_id=uuid.uuid4().hex, request_id=self.a['request_id'],
                           operation_id=self.a['operation_id'], goal_id=self.a_goal,
                           observation_reference=deepcopy(self.a['observation_reference']),
                           native_outcome='failed')
            self.report['recovery']['context'] = deepcopy(context)
            action, observation, deadline = self.decide(session, deadline=deadline,
                actions=('visit_b', 'help'), instruction=context)
            if action == 'help':
                self.report.update(status='needs_help', reason='decision_backend_abstained')
                return
            current = self._release_observation(session, deadline, previous)
            if (current['sample_sim_seconds'] < observation['sample_sim_seconds']
                    or math.dist(current['pose'], observation['pose']) > .05):
                raise ValueError('B admission feedback changed after recovery proposal')
            self.report['decisions'][-1]['revalidated_observation'] = deepcopy(current)
            self.report['recovery']['accepted'] = True
            self.execute(session, 'B', current, deadline)
            self.completed_site = 'B'
        else:
            self.completed_site = 'A'
        self.phase = 'final'
        action, _, _ = self.decide(session, actions=ACTIONS['final'])
        if action == 'help':
            self.report.update(status='needs_help', reason='decision_backend_abstained')
            return
        self.report.update(status='completed', completed_sites=[self.completed_site],
                           observation_assessment=action, requires_connection_close=True,
                           execution_cleanup='pending' if self.completed_site == 'B' else 'unknown')
