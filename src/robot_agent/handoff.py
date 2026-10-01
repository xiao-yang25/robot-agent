"""One bounded ALOHA task consuming the public, single-caller Session interface."""

from dataclasses import dataclass
import math
import time
import uuid

TRANSFER = 'aloha.transfer_cube_segment'
HOLD = 'aloha.hold_current_target'
PROFILE = 'mujoco-stepped-handoff-v1'
GOAL = 'Transfer the red cube from the right gripper to the left and hold it for one simulated second.'
ACTIONS = {'prepare': ('transfer', 'help'),
           'after_transfer': ('hold', 'help'),
           'final': ('observed_success', 'not_met', 'help')}


@dataclass(frozen=True)
class Budget:
    task_seconds: float = 300
    decision_seconds: float = 60
    operation_seconds: float = 60

    def __post_init__(self):
        for value, maximum in ((self.task_seconds, 300), (self.decision_seconds, 60),
                               (self.operation_seconds, 60)):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= maximum:
                raise ValueError('budget must be finite, positive and within the qualified limit')


def reference(observation):
    return {key: observation[key] for key in ('epoch', 'sequence')}


def measurements(raw):
    """Allow only real camera/joint measurements; never pass evaluator truth."""
    if raw.get('valid') is not True:
        raise ValueError('invalid observation')
    for key in ('epoch', 'sequence'):
        if type(raw.get(key)) is not int or raw[key] < 0:
            raise ValueError('invalid observation identity')
    if raw.get('image') != {'shape': [480, 640, 3], 'dtype': 'uint8', 'camera': 'top'}:
        raise ValueError('unsupported camera description')
    rgb, joints = raw.get('rgb'), raw.get('joints')
    if not isinstance(rgb, bytes) or len(rgb) != 480 * 640 * 3:
        raise ValueError('incomplete RGB observation')
    if not isinstance(joints, list) or len(joints) != 14 or any(
            type(v) not in (int, float) or not math.isfinite(v) for v in joints):
        raise ValueError('invalid joint measurements')
    stamp = raw.get('sim_seconds')
    if type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp < 0:
        raise ValueError('invalid simulation time')
    return {'epoch': raw['epoch'], 'sequence': raw['sequence'], 'image': dict(raw['image']),
            'joints': list(joints), 'sim_seconds': stamp, 'rgb': rgb}


class HandoffTask:
    """Borrow one Session for one task. The caller owns startup, reset and close.

    The decision backend only returns proposals. This object serializes Session
    calls, binds proposals to current observations and never creates Core authority.
    stop_requested is checked before/after calls; it is not a hard stop deadline.
    """

    def __init__(self, decision_backend, *, budget=Budget(), started_at=None,
                 clock=time.monotonic, sleep=time.sleep, stop_requested=lambda: False):
        self.backend = decision_backend
        self.budget = budget
        self.clock, self.sleep, self.stop_requested = clock, sleep, stop_requested
        self.started_at = self.clock() if started_at is None else started_at
        self.deadline = self.started_at + budget.task_seconds
        self.task_id = uuid.uuid4().hex
        self.phase = 'prepare'
        self.active = None
        self.report = {'task_id': self.task_id, 'goal': GOAL, 'status': 'running',
                       'decisions': [], 'operations': [], 'task_verdict': 'unassessed'}
        self.used = False

    def check_budget(self):
        if self.stop_requested():
            raise InterruptedError('task cancellation requested')
        if self.clock() >= self.deadline:
            raise TimeoutError('task budget exhausted')

    def decide(self, session, expected_sequence, expected_stage):
        self.check_budget()
        raw = session.observe()
        self.check_budget()
        observation = measurements(raw)
        if raw.get('stage') != expected_stage or observation['sequence'] != expected_sequence:
            raise ValueError('observation not at the required task boundary')
        if self.report.get('epoch', observation['epoch']) != observation['epoch']:
            raise ValueError('episode changed during task')
        self.report['epoch'] = observation['epoch']
        context = {'task_id': self.task_id, 'phase': self.phase, **reference(observation),
                   'goal': GOAL, 'allowed_actions': list(ACTIONS[self.phase])}
        if len(self.report['decisions']) >= 3:
            raise ValueError('decision count exhausted')
        deadline = min(self.deadline, self.clock() + self.budget.decision_seconds)
        # Keep a separate expected context: a backend may not mutate its binding.
        answer = self.backend.decide(dict(context), observation, deadline, self.stop_requested)
        entry = {'context': context, 'answer': answer, 'accepted': False}
        self.report['decisions'].append(entry)
        self.check_budget()
        if self.clock() >= deadline:
            raise TimeoutError('decision budget exhausted')
        if not isinstance(answer, dict) or any(answer.get(k) != context[k]
                for k in ('task_id', 'phase', 'epoch', 'sequence')):
            raise ValueError('decision belongs to a different task/phase/observation')
        if any(type(answer.get(k)) is not int for k in ('epoch', 'sequence')):
            raise ValueError('invalid decision identity')
        if answer.get('action') not in ACTIONS[self.phase] or not isinstance(answer.get('reason'), str) or not 0 < len(answer['reason']) <= 2000:
            raise ValueError('unsupported or unexplained decision')
        current = session.observe()
        measurements(current)
        self.check_budget()
        if self.clock() >= deadline:
            raise TimeoutError('decision expired before revalidation')
        if reference(current) != reference(observation) or current.get('stage') != expected_stage:
            raise ValueError('observation changed while deciding')
        entry['accepted'] = True
        return answer['action'], observation, deadline

    def execute(self, session, skill, observation, steps, decision_deadline):
        self.check_budget()
        capabilities = session.capabilities()
        if capabilities.get('profile') != PROFILE or not any(
                item.get('skill') == skill and item.get('available') is True
                for item in capabilities.get('skills', [])):
            raise ValueError('skill unavailable')
        self.check_budget()
        if self.clock() >= decision_deadline:
            raise TimeoutError('decision expired before submission')
        request = f'{self.task_id}-{self.phase}'
        deadline = min(self.deadline, self.clock() + self.budget.operation_seconds)
        remaining_ms = int((deadline - self.clock()) * 1000)
        if remaining_ms < 1:
            raise TimeoutError('no operation budget remains')
        # Reserve before sending: a lost response never permits automatic retry.
        self.active = request
        submission = session.submit(request, skill=skill, steps=steps,
                                    deadline_ms=remaining_ms,
                                    expected_observation=reference(observation))
        self.report['operations'].append(submission)
        if submission.get('state') not in ('running', 'finished'):
            self.active = None
            raise ValueError('Runtime refused operation')
        operation_id = submission.get('operation_id')
        if type(operation_id) is not int or operation_id < 1:
            raise ValueError('admitted operation identity missing')
        while True:
            self.check_budget()
            if self.clock() >= deadline:
                raise TimeoutError('operation budget exhausted')
            result = session.status(request)
            self.report['operations'][-1] = result
            self.check_budget()
            if self.clock() >= deadline:
                raise TimeoutError('operation result arrived after deadline')
            if result.get('state') == 'finished':
                break
            self.sleep(.01)
        receipt = result.get('receipt', {})
        payload = result.get('result')
        if (result.get('request_id') != request or result.get('skill') != skill or
                type(result.get('operation_id')) is not int or result['operation_id'] != operation_id or
                result.get('epoch') != observation['epoch'] or result.get('steps') != steps or
                receipt.get('authority', {}).get('operation_id') != operation_id or
                receipt.get('result_reference') != request or
                receipt.get('native_outcome') != 'succeeded' or receipt.get('output') != 'accepted' or
                receipt.get('settlement') != 'settled' or receipt.get('authority_disposition') != 'released' or
                not isinstance(payload, dict) or payload.get('skill') != skill or
                payload.get('operation_id') != result.get('operation_id') or
                payload.get('epoch') != observation['epoch'] or payload.get('steps') != steps):
            raise ValueError('operation result/settlement incomplete or mismatched')
        self.active = None

    def run(self, session):
        if self.used:
            raise ValueError('a task cannot be replayed; create a new task after explicit reset')
        self.used = True
        try:
            for phase, sequence, stage, skill, steps in (
                    ('prepare', 0, 'transfer_ready', TRANSFER, 400),
                    ('after_transfer', 400, 'hold_ready', HOLD, 50),
                    ('final', 450, 'needs_reset', None, None)):
                self.phase = phase
                action, observation, decision_deadline = self.decide(session, sequence, stage)
                if action == 'help':
                    self.report.update(status='needs_help', reason='decision_backend_abstained')
                    break
                if skill is None:
                    self.report.update(status='completed', visual_assessment=action)
                else:
                    self.execute(session, skill, observation, steps, decision_deadline)
        except Exception as error:
            self.report.update(status='cancelled' if isinstance(error, InterruptedError) else 'needs_help',
                               reason=f'{type(error).__name__}: {error}')
        finally:
            if self.active is not None:
                try:
                    self.report['cancel_response'] = session.cancel(self.active)
                    self.report['interrupted_operation'] = session.status(self.active)
                except Exception as error:
                    self.report['operation_outcome'] = 'unknown'
                    self.report['cancel_error'] = str(error)
            self.report['phase'] = self.phase
        return self.report
