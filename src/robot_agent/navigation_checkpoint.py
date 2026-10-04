"""One instruction at released A; no in-motion revision or task recovery."""
from copy import deepcopy
import math
import uuid

from .navigation import SITES, _NavigationExecution

INSTRUCTION_SECONDS = 10
IDENTITY_FIELDS = ('task_id', 'checkpoint_id', 'session_id', 'epoch', 'map_id', 'frame')


class CheckpointNavigationTask(_NavigationExecution):
    """Borrow Session; caller provides one cooperative bounded instruction source.

    The provider implements request(context, deadline, stop_requested). It receives
    no Session, model tools or physical evaluator data. The task does not own or
    stop the provider's resources; the caller owns those and connection close.
    """
    goal = 'Visit A, then accept one business instruction to continue to B or finish this task at A.'

    def __init__(self, decision_backend, instruction_provider, **kwargs):
        super().__init__(decision_backend, **kwargs)
        self.instruction_provider = instruction_provider
        self.report['native_cleanup'] = 'unknown'

    def _checkpoint_observation(self, session, deadline, previous=None):
        self.check_budget(deadline)
        if self.active is not None or len(self.report['operations']) != 1:
            raise ValueError('checkpoint requires one released A and no active request')
        original = self.report['operations'][0]
        record = session.status(original['request_id'])
        self.check_budget(deadline)
        if (record.get('goal_id') != original.get('goal_id')
                or not self.validate_record(record, original['request_id'], 'A',
                                            original['operation_id'], original['observation_reference'])):
            raise ValueError('checkpoint A is no longer correlated and released')
        self.capabilities(session, require_available=False)
        observation = self.observe(session)
        self.check_budget(deadline)
        if (math.dist(observation['pose'], SITES['A'][:2]) > .3
                or (previous is not None and (
                    observation['sample_sim_seconds'] < previous['sample_sim_seconds']
                    or math.dist(observation['pose'], previous['pose']) > .05))):
            raise ValueError('checkpoint feedback changed or no longer confirms A')
        self.report['operations'][0] = record
        return observation

    def _instruction(self, session, deadline):
        observation = self._checkpoint_observation(session, deadline)
        request = dict(task_id=self.task_id, checkpoint_id=uuid.uuid4().hex,
                       **{key: observation['reference'][key] for key in ('session_id', 'epoch', 'map_id', 'frame')})
        context = dict(request, allowed_actions=['continue_b', 'finish_at_a'])
        until = min(deadline, self.clock()+INSTRUCTION_SECONDS)
        self.report['checkpoint'] = dict(request=deepcopy(context), accepted=False,
                                         deadline=until, decision_deadline=deadline)
        self.check_budget(until)
        answer = self.instruction_provider.request(deepcopy(context), until, self.stop_requested)
        self.check_budget(until)
        if (not isinstance(answer, dict) or type(answer.get('epoch')) is not int
                or any(answer.get(key) != request[key] for key in IDENTITY_FIELDS)
                or answer.get('action') not in context['allowed_actions']):
            raise ValueError('missing, unsupported or foreign checkpoint instruction')
        # Retain semantic fields only. Unknown optional provider metadata is not
        # task authority and does not enter model context or reports.
        instruction = {key: answer[key] for key in (*IDENTITY_FIELDS, 'action')}
        current = self._checkpoint_observation(session, deadline, observation)
        self.report['checkpoint'].update(accepted=True, instruction=deepcopy(instruction))
        return instruction, current

    def _run_steps(self, session):
        action, observation, deadline = self.decide(session)
        if action == 'help':
            self.report.update(status='needs_help', reason='decision_backend_abstained')
            return
        self.execute(session, 'A', observation, deadline)
        self.phase = 'after_a'
        deadline = min(self.deadline, self.clock()+self.budget.decision_seconds)
        instruction, checkpoint_observation = self._instruction(session, deadline)
        proposed_action = 'visit_b' if instruction['action'] == 'continue_b' else 'finish_at_a'
        action, observation, deadline = self.decide(session, deadline=deadline,
            actions=(proposed_action, 'help'), instruction=instruction,
            require_available=proposed_action == 'visit_b')
        if action == 'help':
            self.report.update(status='needs_help', reason='decision_backend_abstained')
            return
        # Check A's retained association and fresh feedback after the proposal.
        # No slow status call may carry an earlier observation into B admission.
        current = self._checkpoint_observation(session, deadline, observation)
        if (current['sample_sim_seconds'] < checkpoint_observation['sample_sim_seconds']
                or math.dist(current['pose'], checkpoint_observation['pose']) > .05):
            raise ValueError('checkpoint scene changed after instruction consumption')
        self.report['decisions'][-1]['revalidated_observation'] = deepcopy(current)
        if action == 'finish_at_a':
            self.check_budget(deadline)
            self.report.update(status='completed', completed_sites=['A'],
                               execution_cleanup='unknown', requires_connection_close=True)
            return
        self.execute(session, 'B', current, deadline)
        self.phase = 'final'
        action, observation, deadline = self.decide(session)
        if action == 'help':
            self.report.update(status='needs_help', reason='decision_backend_abstained')
            return
        self.report.update(status='completed', completed_sites=['A', 'B'],
                           observation_assessment=action, execution_cleanup='pending',
                           requires_connection_close=True)
