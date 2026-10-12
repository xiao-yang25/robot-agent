"""Private nonblocking station policy; caller commits state and executes intents.

Navigation facts are normalized by the capability binding, including arrival,
pose and native reuse. Conditions are refreshed by the caller/source adapter.
This module owns no Session, model, source, thread or execution authority.
"""
from dataclasses import asdict, dataclass, replace

from ._inspection_source import CheckRecord, _finite_number
from .navigation import NavigationBudget

TARGETS = {'A': 'indicator-A', 'B': 'indicator-B'}
TERMINAL = ('completed', 'needs_help', 'cancelled')


@dataclass(frozen=True)
class DecisionKey:
    task_id: str
    revision: int
    site: str
    check_reference: str
    generation: int


@dataclass(frozen=True)
class Operation:
    request_id: str
    site: str
    deadline: float
    operation_id: int | None = None
    outcome: str = 'reserved'
    reusable: bool = False


@dataclass(frozen=True)
class State:
    task_id: str
    deadline: float
    budget: NavigationBudget
    revision: int = 0
    phase: str = 'prepare'
    generation: int | None = None
    operations: tuple = ()
    checks: tuple = ()
    decision: DecisionKey | None = None
    decision_deadline: float | None = None
    source_failure: str | None = None
    reason: str | None = None
    outcome: str | None = None
    last_now: float | None = None


def new_task(task_id, *, started_at, budget=NavigationBudget()):
    if (not isinstance(task_id, str) or not 0 < len(task_id) <= 64
            or not _finite_number(started_at) or started_at < 0
            or not isinstance(budget, NavigationBudget)):
        raise ValueError('invalid inspection task identity or budget')
    return State(task_id, started_at+budget.task_seconds, budget, last_now=started_at)


@dataclass(frozen=True)
class Conditions:
    now: float
    generation: int | None
    source_valid: bool
    navigation_valid: bool
    can_submit: bool
    record_applicable: bool = False

    def __post_init__(self):
        if (not _finite_number(self.now) or self.now < 0
                or (self.generation is not None and (type(self.generation) is not int
                    or not 0 <= self.generation < 2**63))
                or any(type(v) is not bool for v in (self.source_valid, self.navigation_valid,
                                                    self.can_submit, self.record_applicable))
                or self.source_valid and self.generation is None):
            raise ValueError('invalid current inspection conditions')


@dataclass(frozen=True)
class Control:
    kind: str  # start, tick, stop, goal_changed


@dataclass(frozen=True)
class NavigationFact:
    request_id: str
    site: str
    operation_id: int | None
    outcome: str  # pending means Harness accepted; not merely queued local intent.
    pose_verified: bool = False
    reusable: bool = False


@dataclass(frozen=True)
class WindowClosed:
    record: CheckRecord


@dataclass(frozen=True)
class Proposal:
    key: DecisionKey
    action: str
    reason: str


@dataclass(frozen=True)
class Intent:
    kind: str  # navigate, observe, decide, withdraw, withdraw_submission, cancel
    site: str | None = None
    request_id: str | None = None
    decision: DecisionKey | None = None
    deadline: float | None = None


@dataclass(frozen=True)
class Transition:
    state: State
    intents: tuple = ()


def _end(state, phase, reason, *, outcome=None):
    intents = []
    if state.decision is not None:
        intents.append(Intent('withdraw', decision=state.decision))
    if phase != 'completed' and state.operations:
        active = state.operations[-1]
        if not active.reusable and active.outcome != 'rejected':
            if active.outcome == 'reserved':
                # Withdraw queued exchange work; if already claimed, retain its
                # completion and cancel/query the original possible effect.
                intents.append(Intent('withdraw_submission', active.site, active.request_id))
            intents.append(Intent('cancel', active.site, active.request_id))
    return Transition(replace(state, phase=phase, reason=reason, outcome=outcome,
                              decision=None, decision_deadline=None), tuple(intents))


def _navigate(state, site, now):
    if site in [op.site for op in state.operations] or len(state.operations) >= 2:
        return _end(state, 'needs_help', 'inspection navigation limit reached')
    operation = Operation(f'{state.task_id}-inspection-{site}', site,
                          min(state.deadline, now+state.budget.operation_seconds))
    return Transition(replace(state, phase=f'navigation_{site.lower()}',
                              operations=state.operations+(operation,), decision=None,
                              decision_deadline=None),
                      (Intent('navigate', site, operation.request_id, deadline=operation.deadline),))


def _navigation(state, event):
    positions = [i for i, op in enumerate(state.operations)
                 if op.request_id == event.request_id and op.site == event.site]
    if not positions:
        return state, 'unexpected navigation result'
    index = positions[0]
    original = state.operations[index]
    if (event.request_id != original.request_id or event.site != original.site
            or event.outcome not in ('pending', 'arrived', 'unknown', 'failed', 'rejected')
            or type(event.pose_verified) is not bool or type(event.reusable) is not bool
            or (event.operation_id is not None and (type(event.operation_id) is not int
                or not 0 < event.operation_id < 2**64))
            or (original.operation_id is not None and event.operation_id is not None
                and event.operation_id != original.operation_id)
            or (event.outcome in ('pending', 'arrived') and event.operation_id is None)
            or (event.outcome == 'rejected' and original.operation_id is not None)
            or (event.reusable and event.outcome != 'arrived')
            or (original.reusable and not event.reusable)):
        return state, 'navigation result association or contract invalid'
    # A late progress/unknown query cannot erase an already verified arrival.
    outcome = (original.outcome if original.outcome == 'arrived'
               and event.outcome in ('pending', 'unknown') else event.outcome)
    updated = replace(original, operation_id=original.operation_id if event.operation_id is None
                      else event.operation_id, outcome=outcome, reusable=event.reusable)
    return replace(state, operations=state.operations[:index]+(updated,)
                   +state.operations[index+1:]), None


def _check_matches(state, record):
    site = state.operations[-1].site
    return (isinstance(record, CheckRecord) and record.site == site
            and record.target == TARGETS[site] and type(record.generation) is int
            and record.generation == state.generation
            and isinstance(record.reference, str) and 0 < len(record.reference) <= 128
            and record.classification in ('normal', 'abnormal', 'unknown'))


def recommended_action(state):
    """Deterministic baseline; providers can choose help, never enlarge branches."""
    check = state.checks[-1]
    if check.site == 'B':
        return 'report_recheck'
    return 'report_normal' if check.classification == 'normal' else 'visit_b'


def advance(state, event, conditions):
    """One finite pure turn; the caller assigns returned state before any effect.

    Faults cannot cancel independent in-flight navigation. Stop/goal change,
    navigation failure or expiry emit original-request cancel; never resubmit.
    Late correlated execution facts remain recorded after business termination.
    """
    if isinstance(event, NavigationFact):
        state, error = _navigation(state, event)
        if error is not None:
            return Transition(state) if state.phase in TERMINAL else _end(state, 'needs_help', error)
    if state.phase in TERMINAL:
        return Transition(state)
    if isinstance(event, Control) and event.kind == 'stop':
        return _end(state, 'cancelled', 'explicit inspection stop')
    if isinstance(event, Control) and event.kind == 'goal_changed':
        return _end(state, 'needs_help', 'inspection goal changed; no automatic restart')
    if state.last_now is not None and conditions.now < state.last_now:
        return _end(state, 'needs_help', 'inspection caller clock rolled back')
    state = replace(state, last_now=conditions.now)
    if conditions.now >= state.deadline:
        return _end(state, 'needs_help', 'original inspection task budget elapsed')
    if not conditions.navigation_valid:
        return _end(state, 'needs_help', 'navigation execution conditions invalid')
    if (isinstance(event, NavigationFact)
            and event.request_id == state.operations[-1].request_id
            and event.outcome in ('unknown', 'failed', 'rejected')):
        return _end(state, 'needs_help', f'navigation result {event.outcome}')
    if (not conditions.source_valid or (state.generation is not None
                                       and conditions.generation != state.generation)):
        state = replace(state, source_failure=state.source_failure or 'inspection source unavailable or changed')
    if state.phase.startswith('navigation_'):
        active = state.operations[-1]
        if state.source_failure is not None and active.outcome == 'reserved':
            return _end(state, 'needs_help', 'inspection source lost before navigation acceptance confirmed')
        if conditions.now >= active.deadline:
            return _end(state, 'needs_help', 'original navigation operation budget elapsed')
        if isinstance(event, NavigationFact) and event.request_id == active.request_id:
            if event.outcome == 'arrived':
                if not event.pose_verified:
                    return _end(state, 'needs_help', 'navigation arrival pose unconfirmed')
                if active.site == 'A' and not active.reusable:
                    return Transition(state)  # A must release before inspection/reuse.
                if state.source_failure is not None:
                    return _end(state, 'needs_help', state.source_failure)
                return Transition(replace(state, phase=f'check_{active.site.lower()}'),
                                  (Intent('observe', active.site, active.request_id),))
        return Transition(state)  # Healthy original navigation is still progressing.
    if state.source_failure is not None:
        return _end(state, 'needs_help', state.source_failure)
    if state.phase.startswith('decision_'):
        if not conditions.record_applicable or conditions.now >= state.decision_deadline:
            return _end(state, 'needs_help', 'inspection basis invalid or original decision budget elapsed')
    if isinstance(event, Control):
        if event.kind == 'start' and state.phase == 'prepare':
            if not conditions.can_submit:
                return _end(state, 'needs_help', 'navigation not ready for initial visit')
            return _navigate(replace(state, generation=conditions.generation), 'A', conditions.now)
        if event.kind in ('tick', 'start'):
            return Transition(state)
        return _end(state, 'needs_help', 'unsupported inspection control')
    if isinstance(event, NavigationFact):
        return Transition(state)  # Duplicate associated arrival cannot reopen a window.
    if isinstance(event, WindowClosed):
        record = event.record
        if state.checks and record is state.checks[-1]:
            return Transition(state)
        if not state.phase.startswith('check_') or not _check_matches(state, record):
            return _end(state, 'needs_help', 'inspection record association invalid')
        if record.classification != 'unknown' and not conditions.record_applicable:
            return _end(state, 'needs_help', 'inspection basis unavailable')
        state = replace(state, checks=state.checks+(record,))
        if record.classification == 'unknown' or not conditions.record_applicable:
            return _end(state, 'needs_help', 'inspection unknown or basis unavailable')
        key = DecisionKey(state.task_id, state.revision, record.site, record.reference, record.generation)
        deadline = min(state.deadline, conditions.now+state.budget.decision_seconds)
        return Transition(replace(state, phase=f'decision_{record.site.lower()}',
                                  decision=key, decision_deadline=deadline),
                          (Intent('decide', record.site, decision=key, deadline=deadline),))
    if isinstance(event, Proposal):
        key = event.key
        if (not state.phase.startswith('decision_') or not isinstance(key, DecisionKey)
                or type(key.revision) is not int or type(key.generation) is not int
                or key != state.decision or event.action not in (recommended_action(state), 'help')
                or not isinstance(event.reason, str) or not 0 < len(event.reason) <= 2000):
            return _end(state, 'needs_help', 'inspection proposal association or branch invalid')
        state = replace(state, decision=None, decision_deadline=None)
        if event.action == 'help':
            return _end(state, 'needs_help', event.reason)
        if event.action == 'visit_b':
            if not state.operations[-1].reusable or not conditions.can_submit:
                return _end(state, 'needs_help', 'A not reusable or B not ready for admission')
            return _navigate(state, 'B', conditions.now)
        outcome = 'normal_observed' if event.action == 'report_normal' else f'recheck_{state.checks[-1].classification}'
        reason = ('A status observed normal' if event.action == 'report_normal'
                  else f'A anomaly retained; B status observed {state.checks[-1].classification}')
        return _end(state, 'completed', reason, outcome=outcome)
    return _end(state, 'needs_help', 'unsupported inspection event')


def report(state):
    """Pixel-free business facts; neither execution settlement nor physical verdict."""
    return dict(task_id=state.task_id, revision=state.revision, phase=state.phase,
                outcome=state.outcome, reason=state.reason, source_failure=state.source_failure,
                checks=[asdict(check) for check in state.checks],
                operations=[asdict(operation) for operation in state.operations],
                task_verdict='unassessed', native_cleanup='unknown')
