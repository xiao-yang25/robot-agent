"""One bounded A→B application using only the public navigation Session."""
from copy import deepcopy
from dataclasses import dataclass
import math
import time
import uuid

PROFILE = 'scoped-two-context-nav2-shim-v1'
MAP = 'turtlebot3-world-v1'
SITES = {'A': [0.7, -0.5, 0.0], 'B': [-1.5, -0.5, 0.0]}
GOAL = 'Visit registered site A, then site B, using fresh map feedback after each visit.'
ACTIONS = {'prepare': ('visit_a', 'help'), 'after_a': ('visit_b', 'help'),
           'final': ('observed_complete', 'not_met', 'help')}
REFERENCE_FIELDS = ('session_id', 'observation_id', 'epoch', 'map_id', 'frame')


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


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def measurements(raw):
    """Expose only the public map measurement whitelist, never simulator truth."""
    ref = raw.get('reference', {})
    if (raw.get('valid') is not True or type(raw.get('epoch')) is not int or raw['epoch'] < 0
            or raw.get('map_id') != MAP or raw.get('frame') != 'map'
            or not isinstance(ref, dict) or type(ref.get('epoch')) is not int
            or ref['epoch'] != raw['epoch'] or ref.get('map_id') != MAP or ref.get('frame') != 'map'
            or any(not isinstance(ref.get(k), str) or not 0 < len(ref[k]) <= 128
                   for k in ('session_id', 'observation_id'))):
        raise ValueError('invalid navigation observation identity')
    pose, stamp, health = raw.get('pose'), raw.get('sample_sim_seconds'), raw.get('sensor_health', {})
    if (not isinstance(pose, list) or len(pose) != 2 or not all(finite(v) for v in pose)
            or not finite(stamp) or stamp <= 0 or not isinstance(health, dict)
            or health.get('localization') is not True or not finite(health.get('clock_age'))
            or not 0 <= health['clock_age'] <= 1):
        raise ValueError('invalid navigation measurement')
    streams = health.get('streams')
    if (not isinstance(streams, list) or len(streams) != 2 or any(
            not isinstance(row, (tuple, list)) or len(row) != 3 or not all(finite(v) for v in row)
            or row[0] <= 0 or not all(0 <= age <= 1 for age in row[1:]) for row in streams)):
        raise ValueError('invalid navigation sensor health')
    return {'reference': {key: ref[key] for key in REFERENCE_FIELDS},
            'pose': list(pose), 'sample_sim_seconds': stamp,
            'sensor_health': {'localization': True, 'clock_age': health['clock_age'],
                              'streams': deepcopy(streams)}}


class _NavigationExecution:
    """Borrow one trusted prepared owner; caller owns the connection and close.

    Model proposals cannot submit, rebind, settle or restore execution authority.
    A finite result is distinct from pending resource settlement and task verdict.
    """
    goal = GOAL
    profile = PROFILE
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
        observation = measurements(session.observe())
        self.check_budget()
        realm = tuple(observation['reference'][key] for key in ('session_id', 'epoch', 'map_id', 'frame'))
        if self.realm is not None and realm != self.realm:
            raise ValueError('navigation session/map/epoch changed')
        self.realm = realm
        return observation

    def capabilities(self, session, *, require_available):
        self.check_budget()
        cap = session.capabilities()
        self.check_budget()
        if (cap.get('skill') != 'navigation.visit_site' or cap.get('profile') != self.profile
                or cap.get('map_id') != MAP or cap.get('frame') != 'map'
                or not isinstance(cap.get('sites'), list) or any(site not in cap['sites'] for site in SITES)
                or type(cap.get('maximum_deadline_ms')) is not int
                or not 0 < cap['maximum_deadline_ms'] <= 147000
                or (require_available and cap.get('available') is not True)):
            raise ValueError('qualified navigation capability unavailable')
        self.maximum_deadline_ms = cap['maximum_deadline_ms']
        return cap

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

    def associated_receipt(self, record, request, site, operation_id, reference):
        if (record.get('request_id') != request or record.get('site') != site
                or record.get('skill') != 'navigation.visit_site'
                or type(record.get('operation_id')) is not int or record['operation_id'] != operation_id
                or record.get('observation_reference') != reference):
            raise ValueError('navigation operation association changed')
        receipt = record.get('receipt', {})
        authority = receipt.get('authority', {})
        if type(authority.get('operation_id')) is not int or authority['operation_id'] != operation_id:
            raise ValueError('navigation receipt authority mismatch')
        binding = authority.get('binding')
        if (not isinstance(binding, dict) or binding.get('provider') != 'scoped-nav2'
                or binding.get('domain') != 'exclusive-waffle-drive'
                or any(type(binding.get(key)) is not int or binding[key] < 1 for key in ('revision', 'generation'))
                or (self.binding is not None and binding != self.binding)):
            raise ValueError('navigation authority binding changed')
        self.binding = deepcopy(binding)
        return receipt

    def validate_record(self, record, request, site, operation_id, reference):
        receipt = self.associated_receipt(record, request, site, operation_id, reference)
        if receipt.get('authority_disposition') == 'revoked' or receipt.get('native_outcome') in ('failed', 'cancelled'):
            raise ValueError('navigation operation failed or revoked')
        payload = record.get('result')
        if payload is None:
            return False
        goal_id = record.get('goal_id')
        if (not isinstance(payload, dict) or not isinstance(goal_id, str) or len(goal_id) != 32
                or any(c not in '0123456789abcdef' for c in goal_id)
                or receipt.get('native_identity') != goal_id or payload.get('goal_id') != goal_id
                or payload.get('stage') != site or receipt.get('result_reference') != request
                or receipt.get('native_acceptance') != 'accepted' or receipt.get('native_outcome') != 'succeeded'
                or receipt.get('output') != 'accepted' or record.get('target') != SITES[site]):
            raise ValueError('navigation result/native identity incomplete or mismatched')
        if site == 'A':
            return (record.get('state') == 'finished' and receipt.get('settlement') == 'settled'
                    and receipt.get('authority_disposition') == 'released')
        if (receipt.get('settlement') != 'pending' or receipt.get('authority_disposition') != 'current'):
            raise ValueError('unexpected final-context settlement')
        return True

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
