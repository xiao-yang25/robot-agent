"""One bounded A→B application using only the public navigation Session."""
from copy import deepcopy
from dataclasses import dataclass
import math
import time
import uuid

from ._navigation_contract import (MAP, PROFILE, SITES, REFERENCE_FIELDS,
                                   NavigationContract, finite, measurements)

GOAL = 'Visit registered site A, then site B, using fresh map feedback after each visit.'
ACTIONS = {'prepare': ('visit_a', 'help'), 'after_a': ('visit_b', 'help'),
           'final': ('observed_complete', 'not_met', 'help')}


@dataclass(frozen=True)
class NavigationBudget:
    task_seconds: float = 240
    decision_seconds: float = 30
    operation_seconds: float = 160

    def __post_init__(self):
        for value, maximum in ((self.task_seconds, 240), (self.decision_seconds, 30),
                               (self.operation_seconds, 160)):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= maximum:
                raise ValueError('navigation budget must be finite, positive and within limits')



class _NavigationExecution(NavigationContract):
    """Borrow one trusted prepared owner; caller owns the connection and close.

    Model proposals cannot submit, rebind, settle or restore execution authority.
    A finite result is distinct from pending resource settlement and task verdict.
    """
    goal = GOAL
    profile = PROFILE
    expected_map_id = MAP
    instruction_field = "checkpoint_instruction"
    instruction_id = "checkpoint_id"

    def __init__(self, decision_backend, *, budget=NavigationBudget(), clock=time.monotonic,
                 sleep=time.sleep, stop_requested=lambda: False, started_at=None):
        self.backend, self.budget = decision_backend, budget
        self.clock, self.sleep, self.stop_requested = clock, sleep, stop_requested
        started_at = clock() if started_at is None else started_at
        if not finite(started_at) or started_at > clock():
            raise ValueError('invalid navigation start time')
        self.deadline = started_at + budget.task_seconds
        self.task_id = uuid.uuid4().hex
        self.phase, self.active, self.used, self.realm = 'prepare', None, False, None
        self.binding = None
        self.maximum_deadline_ms = 147000
        self.report = {'task_id': self.task_id, 'goal': self.goal, 'status': 'running',
                       'decisions': [], 'operations': [], 'task_verdict': 'unassessed'}

    def check_budget(self, deadline=None):
        if self.stop_requested():
            raise InterruptedError('navigation task cancelled')
        if self.clock() >= min(self.deadline, deadline if deadline is not None else self.deadline):
            raise TimeoutError('navigation task or phase deadline elapsed')

    def observe(self, session):
        self.check_budget()
        observation = self.normalize_observation(session.observe())
        self.check_budget()
        return observation

    def capabilities(self, session, *, require_available):
        self.check_budget()
        cap = session.capabilities()
        self.check_budget()
        return self.validate_capabilities(cap, require_available=require_available)

    def preceding_site(self):
        return None if self.phase == 'prepare' else ('A' if self.phase == 'after_a' else 'B')

    def proposal_context(self):
        return {}

    def instruction_answer_matches(self, answer, instruction):
        return answer.get(self.instruction_id) == instruction[self.instruction_id]

    def decide(self, session, *, deadline=None, actions=None, instruction=None, require_available=None):
        require_available = self.phase != 'final' if require_available is None else require_available
        self.capabilities(session, require_available=require_available)
        observation = self.observe(session)
        site = self.preceding_site()
        if site is not None:
            previous = SITES[site]
            if math.dist(observation['pose'], previous[:2]) > .3:
                raise ValueError('new map feedback does not confirm preceding visit')
        context = {'task_id': self.task_id, 'phase': self.phase, 'goal': self.goal,
                   'observation_reference': deepcopy(observation['reference']),
                   'registered_sites': deepcopy(SITES),
                   'allowed_actions': list(ACTIONS[self.phase] if actions is None else actions)}
        if instruction is not None:
            context[self.instruction_field] = deepcopy(instruction)
        context.update(self.proposal_context())
        deadline = min(self.deadline, self.clock() + self.budget.decision_seconds
                       if deadline is None else deadline)
        self.check_budget(deadline)
        answer = self.backend.decide(deepcopy(context), deepcopy(observation), deadline, self.stop_requested)
        entry = {'context': context, 'answer': answer, 'accepted': False}
        self.report['decisions'].append(entry)
        self.check_budget(deadline)
        if (not isinstance(answer, dict) or answer.get('task_id') != self.task_id
                or answer.get('phase') != self.phase
                or answer.get('observation_reference') != context['observation_reference']
                or type(answer.get('observation_reference', {}).get('epoch')) is not int
                or answer.get('action') not in context['allowed_actions']
                or (instruction is not None and not self.instruction_answer_matches(answer, instruction))
                or not isinstance(answer.get('reason'), str) or not 0 < len(answer['reason']) <= 2000):
            raise ValueError('proposal is unsupported or belongs to a different observation/task/phase')
        self.capabilities(session, require_available=require_available)
        current = self.observe(session)
        self.check_budget(deadline)
        if (current['sample_sim_seconds'] < observation['sample_sim_seconds']
                or math.dist(current['pose'], observation['pose']) > .05):
            raise ValueError('navigation scene changed while deciding')
        entry.update(accepted=True, revalidated_observation=deepcopy(current))
        return answer['action'], current, deadline

    def start_operation(self, session, site, observation, decision_deadline):
        self.check_budget(decision_deadline)
        request = f'{self.task_id}-{self.phase}'
        deadline = min(self.deadline, self.clock() + self.budget.operation_seconds)
        remaining_ms = min(self.maximum_deadline_ms, int((deadline - self.clock()) * 1000))
        if remaining_ms < 1:
            raise TimeoutError('no navigation operation budget remains')
        deadline = min(deadline, self.clock() + remaining_ms/1000)
        self.active = request  # Reserve before send, including ambiguous submission.
        record = session.submit(request, site=site, expected_observation=observation['reference'],
                                deadline_ms=remaining_ms)
        self.report['operations'].append(record)
        self.check_budget(deadline)
        if record.get('state') == 'rejected':
            self.active = None
            raise ValueError('navigation Runtime refused request')
        operation_id = record.get('operation_id')
        if type(operation_id) is not int or operation_id < 1:
            raise ValueError('navigation admission identity missing')
        return record, request, operation_id, deadline

    def execute(self, session, site, observation, decision_deadline):
        record, request, operation_id, deadline = self.start_operation(
            session, site, observation, decision_deadline)
        while True:
            self.check_budget(deadline)
            done = self.validate_record(record, request, site, operation_id, observation['reference'])
            if done:
                if site == 'A':
                    self.active = None
                return
            self.sleep(.1)
            self.check_budget(deadline)
            record = session.status(request)
            self.report['operations'][-1] = record
            self.check_budget(deadline)

    def run(self, session):
        if self.used:
            raise ValueError('navigation task cannot be replayed')
        self.used = True
        try:
            self._run_steps(session)
        except Exception as error:
            self.report.update(status='cancelled' if isinstance(error, InterruptedError) else 'needs_help',
                               reason=f'{type(error).__name__}: {error}')
        finally:
            if self.active is not None and self.report['status'] != 'completed':
                try:
                    self.report['cancel_response'] = session.cancel(self.active)
                    self.report['interrupted_operation'] = session.status(self.active)
                except Exception as error:
                    self.report.update(operation_outcome='unknown', cancel_error=str(error))
            self.report['phase'] = self.phase
        return self.report


class NavigationTask(_NavigationExecution):
    """Fixed A→B task; borrow Session while caller owns connection and close."""
    def _run_steps(self, session):
        for phase, site in (('prepare', 'A'), ('after_a', 'B'), ('final', None)):
            self.phase = phase
            action, observation, deadline = self.decide(session)
            if action == 'help':
                self.report.update(status='needs_help', reason='decision_backend_abstained')
                break
            if site is None:
                self.report.update(status='completed', observation_assessment=action,
                                   execution_cleanup='pending', requires_connection_close=True)
            else:
                self.execute(session, site, observation, deadline)
