"""One in-motion stop/redirect instruction; public Session alone grants reuse."""
from copy import deepcopy
import math
import uuid

from .navigation import ACTIONS, SITES, _NavigationExecution

PROFILE = 'scoped-two-context-nav2-revision-v1'
IDENTITY_FIELDS = ('task_id', 'revision_id', 'request_id', 'operation_id', 'goal_id',
                   'session_id', 'epoch', 'map_id', 'frame')


def instruction_matches(answer, context):
    return (isinstance(answer, dict) and type(answer.get('epoch')) is int
            and type(answer.get('operation_id')) is int
            and all(answer.get(key) == context[key] for key in IDENTITY_FIELDS)
            and answer.get('action') in ('stop', 'redirect_b'))


class RevisionNavigationTask(_NavigationExecution):
    """Caller lends Session and a cooperative nonblocking poll provider.

    poll(context, deadline, stop_requested) returns None or one business input.
    It receives no Session/tools; caller owns its resources and connection close.
    The task signs at most one ten-second window after measured A motion. No
    instruction completes only A; redirect completes only B. Poll/RPC calls are
    cooperative and have no hard interruption guarantee.
    """
    goal = 'Visit A; during A motion accept one stop or redirect to registered B; otherwise finish at A.'
    profile = PROFILE
    instruction_field = 'revision_instruction'
    instruction_id = 'revision_id'

    def __init__(self, decision_backend, instruction_provider, **kwargs):
        super().__init__(decision_backend, **kwargs)
        self.instruction_provider = instruction_provider
        self.a = None
        self.completed_site = None
        self.report['native_cleanup'] = 'unknown'

    def preceding_site(self):
        return self.completed_site if self.phase == 'final' else None

    def proposal_context(self):
        return {'completion_site': self.completed_site} if self.phase == 'final' else {}

    def _a_receipt(self, record):
        receipt = self.associated_receipt(record, self.a['request_id'], 'A',
                                         self.a['operation_id'], self.a['observation_reference'])
        goal = record.get('goal_id')
        if (not isinstance(goal, str) or len(goal) != 32
                or any(c not in '0123456789abcdef' for c in goal)
                or receipt.get('native_acceptance') != 'accepted'
                or receipt.get('native_identity') != goal
                or goal != self.a['goal_id'] or record.get('target') != SITES['A']):
            raise ValueError('A native goal association changed')
        if 'expiry_observed_at' not in receipt or receipt['expiry_observed_at'] is not None:
            raise ValueError('A authority expiry is unknown or observed')
        return receipt

    def _pending(self, record):
        receipt = self._a_receipt(record)
        return (record.get('state') == 'running' and record.get('result') is None
                and receipt.get('native_outcome') == 'pending'
                and receipt.get('authority_disposition') == 'current')

    def _status_a(self, session, deadline):
        self.check_budget(deadline)
        record = session.status(self.a['request_id'])
        self.report['operations'][0] = deepcopy(record)
        self.check_budget(deadline)
        self._a_receipt(record)
        return record

    def _released(self, record):
        receipt = self._a_receipt(record)
        if receipt.get('native_outcome') not in ('pending', 'cancelled', 'succeeded'):
            raise ValueError('A native outcome cannot support reuse')
        if (record.get('state') != 'finished' or receipt.get('settlement') != 'settled'
                or receipt.get('authority_disposition') != 'released'):
            return False
        outcome, output = receipt['native_outcome'], receipt.get('output')
        if outcome == 'cancelled':
            valid = (output == 'not_delivered' and record.get('result') is None
                     and receipt.get('output_non_delivery_reason') == 'no_output')
        elif outcome == 'succeeded' and output == 'not_delivered':
            valid = (record.get('result') is None
                     and receipt.get('output_non_delivery_reason') == 'authority_revoked'
                     and receipt.get('result_reference') == self.a['request_id'])
        elif outcome == 'succeeded' and output == 'accepted':
            valid = self.validate_record(record, self.a['request_id'], 'A',
                                         self.a['operation_id'], self.a['observation_reference'])
        else:
            valid = False
        if not valid:
            raise ValueError('released A lacks a correlated terminal/output disposition')
        return True

    def _release_observation(self, session, deadline, previous=None):
        if not self._released(self._status_a(session, deadline)):
            raise ValueError('A is no longer confirmed released')
        self.capabilities(session, require_available=True)
        observation = self.observe(session)
        self.check_budget(deadline)
        if previous is not None and (observation['sample_sim_seconds'] < previous['sample_sim_seconds']
                or math.dist(observation['pose'], previous['pose']) > .05):
            raise ValueError('released scene changed while deciding')
        return observation

    def _cancel_a(self, session, operation_deadline):
        self.check_budget(operation_deadline)
        deadline = min(self.deadline, operation_deadline, self.clock()+15)
        # Cancellation precedes any model call. An ambiguous reply never grants B.
        self.report['revision']['cancel_response'] = session.cancel(self.a['request_id'])
        while True:
            record = self._status_a(session, deadline)
            if self._released(record):
                self.active = None
                self.report['revision']['released_a'] = deepcopy(record)
                return
            self.sleep(.1)

    def _visit_a(self, session, observation, decision_deadline):
        record, request, operation, deadline = self.start_operation(session, 'A', observation, decision_deadline)
        baseline = window = previous = None
        closed = False
        while True:
            self.check_budget(deadline)
            self.associated_receipt(record, request, 'A', operation, observation['reference'])
            if self.validate_record(record, request, 'A', operation, observation['reference']):
                self.active = None
                if window is not None:
                    self.report['revision']['window_closed'] = True
                return None, deadline
            if record.get('receipt', {}).get('native_acceptance') == 'accepted':
                if self.a is None:
                    self.a = {key: deepcopy(record[key]) for key in
                              ('request_id', 'operation_id', 'goal_id', 'observation_reference')}
                if not self._pending(record):
                    closed = True
                elif not closed:
                    current = self.observe(session)
                    self.check_budget(deadline)
                    if baseline is None:
                        baseline = current
                    if previous is not None and current['sample_sim_seconds'] < previous['sample_sim_seconds']:
                        raise ValueError('A measurement time regressed')
                    previous = current
                    if (window is None and current['sample_sim_seconds']-baseline['sample_sim_seconds'] >= .5
                            and math.dist(current['pose'], baseline['pose']) > .1):
                        window = dict(task_id=self.task_id, revision_id=uuid.uuid4().hex,
                                      **{key: self.a[key] for key in ('request_id','operation_id','goal_id')},
                                      **{key: current['reference'][key] for key in ('session_id','epoch','map_id','frame')},
                                      allowed_actions=['stop', 'redirect_b'])
                        until = min(deadline, self.deadline, self.clock()+10)
                        self.report['revision'] = dict(request=deepcopy(window), accepted=False,
                                                       deadline=until, invalid_inputs=0, window_closed=False)
                    if window is not None:
                        if self.clock() >= until:
                            closed = True
                        else:
                            answer = self.instruction_provider.poll(deepcopy(window), until, self.stop_requested)
                            self.check_budget(deadline)
                            # Poll may race native completion. Recheck the exact A and realm
                            # before consuming a business command, even if poll returns immediately.
                            record = self._status_a(session, deadline)
                            latest = self.observe(session)
                            if latest['sample_sim_seconds'] < previous['sample_sim_seconds']:
                                raise ValueError('A measurement time regressed during poll')
                            previous = latest
                            self.check_budget(deadline)
                            if self.clock() >= until or not self._pending(record):
                                closed = True
                            elif instruction_matches(answer, window):
                                command = {key: deepcopy(answer[key]) for key in (*IDENTITY_FIELDS, 'action')}
                                self.report['revision'].update(accepted=True, instruction=command, window_closed=True)
                                self._cancel_a(session, deadline)
                                return command, deadline
                            elif answer is not None:
                                self.report['revision']['invalid_inputs'] += 1
            if closed and window is not None:
                self.report['revision']['window_closed'] = True
            self.sleep(.1)
            self.check_budget(deadline)
            record = session.status(request)
            self.report['operations'][0] = deepcopy(record)

    def _run_steps(self, session):
        action, observation, deadline = self.decide(session)
        if action == 'help':
            self.report.update(status='needs_help', reason='decision_backend_abstained')
            return
        command, _ = self._visit_a(session, observation, deadline)
        if command is not None and command['action'] == 'stop':
            self.check_budget()
            self.report.update(status='stopped_by_instruction', completed_sites=[],
                               execution_cleanup='unknown', requires_connection_close=True)
            return
        if command is not None:
            self.phase = 'after_revision'
            deadline = min(self.deadline, self.clock()+self.budget.decision_seconds)
            previous = self._release_observation(session, deadline)
            action, observation, deadline = self.decide(session, deadline=deadline,
                actions=('visit_b', 'help'), instruction=command)
            if action == 'help':
                self.report.update(status='needs_help', reason='decision_backend_abstained')
                return
            current = self._release_observation(session, deadline, previous)
            if (current['sample_sim_seconds'] < observation['sample_sim_seconds']
                    or math.dist(current['pose'], observation['pose']) > .05):
                raise ValueError('B admission feedback changed after the proposal')
            self.report['decisions'][-1]['revalidated_observation'] = deepcopy(current)
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
                           observation_assessment=action, execution_cleanup='pending' if self.completed_site == 'B' else 'unknown',
                           requires_connection_close=True)
