"""Private caller-owned station inspection loop; ROS imports are lazy.

The caller commits policy state and pumps the camera. Existing separate owners
perform model and public Session work. No replay or execution authority lives here.
"""
from copy import deepcopy
from dataclasses import asdict, replace
import math
import time
import uuid

from ._inspection_camera import RosCamera
from ._inspection_marker import classify
from ._inspection_navigation import Admission, InspectionNavigation
from ._inspection_policy import (Conditions, Control, Failure, NavigationFact, Proposal,
    TERMINAL, TARGETS, WindowClosed, advance, new_task, report)
from ._navigation_contract import SITES, finite
from ._task_runtime import Coordinator, Owner
from .navigation import NavigationBudget


class RuleDecision:
    """First bounded provider: routes classifications, never claims physical repair."""
    def decide(self, key, record, deadline, stop_requested):
        if stop_requested() or time.monotonic() >= deadline:
            raise InterruptedError('inspection decision withdrawn or expired')
        action = ('report_recheck' if record.site == 'B' else
                  'report_normal' if record.classification == 'normal' else 'visit_b')
        return Proposal(key, action, 'Finite station rule; no model called')


class _Loop:
    def __init__(self, session_factory, camera_factory, decision_factory, budget,
                 stop_requested, started_at, startup_seconds, cleanup_seconds, interpreter):
        self.session_factory, self.camera_factory = session_factory, camera_factory
        self.decision_factory, self.interpret = decision_factory, interpreter
        self.stop_requested = stop_requested
        self.state = new_task(uuid.uuid4().hex, started_at=started_at, budget=budget)
        self.startup_deadline = min(self.state.deadline, started_at+startup_seconds)
        self.cleanup_seconds = cleanup_seconds
        self.camera = self.source = self.coordinator = self.binding = None
        self.owners = []
        self.nav = None
        self.nav_error = None
        self.next_read = 0.
        self.camera_failed = False
        self.camera_attempted = False
        self.io_snapshot = None
        self.queue = []  # finite intents from the bounded two-site policy
        self.cancelled = set()
        self.samples = 0
        self.turns = 0
        self.decisions = []
        self.closing_calls = []
        self.runtime_error = None

    def _pump(self):
        if self.camera_failed:
            return
        try:
            self.camera.pump()
        except Exception as error:
            self.camera_failed = True
            self.runtime_error = f'{type(error).__name__}: {error}'
            if self.source is None:
                raise
            self.source.events.invalidate(self.runtime_error[:256])

    def _conditions(self, incoming_record=None):
        now = time.monotonic()
        valid = self.nav is not None and self.nav_error is None
        valid = valid and 0 <= now-self.nav['received_at'] <= 1.
        if valid and self.state.phase.startswith(('check_', 'decision_')):
            site = self.state.operations[-1].site
            valid = math.dist(self.nav['observation']['pose'], SITES[site][:2]) <= .3
        basis = incoming_record if incoming_record is not None else self.state.checks[-1] if self.state.checks else None
        return Conditions(now, None if self.source is None else self.source.generation,
            self.source is not None and self.source.refresh(), bool(valid),
            bool(valid and self.nav['available']),
            self.source is not None and basis is not None and self.source.applicable(basis))

    def _step(self, event):
        decision_deadline = self.state.decision_deadline
        transition = advance(self.state, event, self._conditions(
            event.record if isinstance(event, WindowClosed) else None))
        self.state = transition.state  # Commit before dispatching any side effect.
        for intent in transition.intents:
            if intent.kind == 'navigate':
                admission_deadline = min(intent.deadline, decision_deadline if decision_deadline is not None
                    else time.monotonic()+self.state.budget.decision_seconds)
                basis = self.state.checks[-1] if intent.site == 'B' else None
                self.binding.authorize(Admission(intent.request_id, intent.site,
                    self.source.generation, intent.deadline, admission_deadline, basis))
                self.queue.append(intent)
            elif intent.kind == 'observe':
                self.camera.open_window(intent.site, TARGETS[intent.site])
            elif intent.kind == 'decide':
                record = self.state.checks[-1]
                self.coordinator.begin('decision', 'decide',
                    (intent.decision, record, intent.deadline,
                     lambda: self.coordinator.exchange.owner_stopped('decision')),
                    {}, deadline=intent.deadline, association=asdict(intent.decision))
            elif intent.kind in ('withdraw', 'withdraw_submission'):
                role = 'decision' if intent.kind == 'withdraw' else 'io'
                call = self.coordinator.pending[role]
                if call is not None and (role == 'decision' or call.method == 'submit'):
                    self.coordinator.exchange.withdraw(role, call)
                if intent.kind == 'withdraw_submission':
                    self.binding.revoke(intent.request_id, missing_ok=True)
            elif intent.kind == 'cancel':
                if intent.request_id not in self.cancelled:
                    self.cancelled.add(intent.request_id)
                    if self.binding.revoke(intent.request_id, missing_ok=True):
                        self.queue.append(intent)
                    else:
                        self.closing_calls.append(dict(request_id=intent.request_id,
                            response=dict(submit_attempted=False, closure='not_authorized')))

    def _source_event(self, kind, value):
        if kind != 'observation' or not self.state.phase.startswith('check_'):
            return
        if self.camera.window_deadline is None or time.monotonic() >= self.camera.window_deadline:
            return
        reader = None
        recording = False
        try:
            reader = self.source.borrow(value.reference)
            frame = reader.read()
            classification, _, _ = self.interpret(frame)
            if time.monotonic() >= self.camera.window_deadline:
                return  # Normal closure drops a late interpretation, not history.
            recording = True
            if self.source.record(reader, classification):
                self.samples += 1
        except Exception as error:
            normal_end = (recording and isinstance(error, RuntimeError) and self.source.refresh()
                          and time.monotonic() >= self.camera.window_deadline)
            if not normal_end:
                self.runtime_error = f'{type(error).__name__}: {error}'
                self.source.events.invalidate(self.runtime_error[:256])
        finally:
            if reader is not None:
                reader.release()

    def _prepared(self, value):
        if self.nav is not None and value['observation']['sample_sim_seconds'] < self.nav['observation']['sample_sim_seconds']:
            self.nav_error = 'navigation measurement clock rolled back'
        else:
            self.nav, self.nav_error = value, None

    def _retain(self, role, call):
        self.coordinator.retain(role, call)

    @staticmethod
    def _wire_row(original):
        # One report boundary also covers Coordinator's exception-retention path.
        row = dict(original)
        if isinstance(row['value'], (Proposal, NavigationFact)):
            row['value'] = asdict(row['value'])
        elif isinstance(row['value'], dict) and isinstance(row['value'].get('fact'), NavigationFact):
            row['value'] = dict(row['value'], fact=asdict(row['value']['fact']))
        elif row['role'] == 'decision' and row['value'] is not None:
            row['value'] = dict(unsupported_provider_value=type(row['value']).__name__)
        return row

    def _consume(self, completed):
        # Preserve original I/O before interpreting any decision from this turn.
        call = completed.get('io')
        if call is not None:
            if self.state.phase in TERMINAL or call.withdrawn:
                self._retain('io', call)
            if call.error is not None:
                self.nav_error = f'{type(call.error).__name__}: {call.error}'
                if call.method in ('submit', 'progress', 'status') and self.state.operations:
                    active = self.state.operations[-1]
                    self._step(NavigationFact(active.request_id, active.site, active.operation_id, 'unknown',
                                              reusable=active.reusable))
                elif self.state.phase not in TERMINAL:
                    self._step(Control('tick'))
            elif call.method == 'prepare':
                self._prepared(call.value)
                if self.state.phase == 'prepare':
                    self._step(Control('start'))
            elif call.method == 'progress':
                if call.value['condition_error'] is None:
                    self._prepared(call.value['prepared'])
                else:
                    self.nav_error = call.value['condition_error']
                self._step(call.value['fact'])
            elif call.method in ('submit', 'status'):
                self._step(call.value)
            elif call.method == 'cancel':
                self.closing_calls.append(dict(request_id=call.args[0], response=call.value))
        call = completed.get('decision')
        if call is not None:
            self.decisions.append(dict(association=call.association, withdrawn=call.withdrawn,
                error=None if call.error is None else f'{type(call.error).__name__}: {call.error}'))
            if call.withdrawn or self.state.phase in TERMINAL:
                self._retain('decision', call)
            elif call.error is not None:
                self.runtime_error = f'{type(call.error).__name__}: {call.error}'
                self._step(Failure(self.runtime_error[:2000]))
            else:
                self._step(call.value)

    def _dispatch(self, *, cleanup=False):
        if self.coordinator.pending['io'] is not None:
            return
        if self.queue:
            intent = self.queue.pop(0)
            if intent.kind == 'navigate' and self.state.phase in TERMINAL:
                return  # No effect from an obsolete local intent.
            until = self.coordinator.cleanup_until() if intent.kind == 'cancel' else intent.deadline
            self.coordinator.begin('io', 'cancel' if intent.kind == 'cancel' else 'submit',
                (intent.request_id,), {}, deadline=until, cleanup=intent.kind == 'cancel',
                association=dict(request_id=intent.request_id, site=intent.site))
        elif not cleanup and time.monotonic() >= self.next_read:
            self.next_read = time.monotonic()+.1
            active = self.state.operations[-1] if self.state.operations else None
            progressing = active is not None and active.outcome != 'reserved'
            self.coordinator.begin('io', 'progress' if progressing else 'prepare',
                (active.request_id,) if progressing else (),
                {} if progressing else dict(require_available=False),
                deadline=min(self.state.deadline, active.deadline)
                    if progressing and self.state.phase.startswith('navigation_') else self.state.deadline)

    def _close_io(self, binding):
        # Snapshot on the same owner, after its current method returned.
        try:
            return binding.close()
        finally:
            self.io_snapshot = deepcopy(binding.attempts)

    def _start(self):
        if self.stop_requested():
            raise InterruptedError('inspection stopped before preparation')
        if time.monotonic() >= self.startup_deadline:
            raise TimeoutError('original inspection startup budget elapsed')
        self.camera_attempted = True
        self.camera = self.camera_factory()
        while self.camera.source is None:
            if self.stop_requested():
                raise InterruptedError('inspection stopped during camera startup')
            if time.monotonic() >= self.startup_deadline:
                raise TimeoutError('original inspection startup budget elapsed')
            self._pump()
            failure = self.camera.binding.failure
            if failure is not None:
                raise ValueError(failure)
        self.source = self.camera.source
        self.coordinator = Coordinator(self.state.task_id, self.stop_requested,
            self.cleanup_seconds, events=self.source.events, on_event=self._source_event)
        def factory():
            binding = InspectionNavigation(self.session_factory, self.source,
                task_deadline=self.state.deadline, stop_requested=self.coordinator.stopped)
            with self.coordinator.exchange.condition:
                self.binding = binding
            return binding
        self.owners = [Owner(self.coordinator.exchange, 'io', factory, close=self._close_io),
                       Owner(self.coordinator.exchange, 'decision', self.decision_factory)]
        for owner in self.owners:
            owner.start()
        self.coordinator.begin('io', 'prepare', (), {}, deadline=self.startup_deadline)

    def run(self):
        camera_close = dict(returned=False)
        terminal = {}
        try:
            self._start()
            while self.state.phase not in TERMINAL:
                self.turns += 1
                self._pump()
                if self.coordinator.stopped():
                    self._step(Control('stop'))
                # Initial condition read has its own original startup deadline.
                elif self.state.phase != 'prepare':
                    self._step(Control('tick'))
                elif not self.source.refresh() or time.monotonic() >= self.startup_deadline:
                    self._step(Control('tick'))
                completed = self.coordinator.poll()
                self._consume(completed)
                if self.state.phase in TERMINAL:
                    break
                if (self.state.phase.startswith('check_') and self.camera.window_deadline is not None
                        and time.monotonic() >= self.camera.window_deadline):
                    self._step(WindowClosed(self.camera.finish_window()))
                self._dispatch()
                with self.coordinator.exchange.condition:
                    self.coordinator.exchange.condition.wait(.005)
        except Exception as error:
            self.runtime_error = f'{type(error).__name__}: {error}'
            if self.coordinator is not None and self.binding is not None:
                self._step(Control('stop') if isinstance(error, InterruptedError)
                           else Failure(self.runtime_error[:2000]))
            else:
                # No business submission can precede resource readiness.
                self.state = replace(self.state, phase='cancelled' if isinstance(error, InterruptedError)
                                     else 'needs_help', reason=self.runtime_error)
        finally:
            if self.coordinator is not None:
                until = self.coordinator.cleanup_until()
                # Withdrawal is visible to an outstanding decision without
                # discarding a claimed I/O completion or its possible effect.
                call = self.coordinator.pending['decision']
                if call is not None:
                    self.coordinator.exchange.withdraw('decision', call)
                try:
                    while time.monotonic() < until:
                        self._pump()
                        self._consume(self.coordinator.poll())
                        self._dispatch(cleanup=True)
                        if not self.queue and self.coordinator.pending['io'] is None:
                            break
                        with self.coordinator.exchange.condition:
                            self.coordinator.exchange.condition.wait(.005)
                except Exception as error:
                    self.runtime_error = f'cleanup {type(error).__name__}: {error}'
                for owner in self.owners:
                    self.coordinator.exchange.close(owner.role)
                terminal = {owner.role: owner.finish(until) for owner in self.owners}
                for role in ('io', 'decision'):
                    call = self.coordinator.exchange.collect(role)
                    if call is not None:
                        try:
                            self._consume({role: call})
                        except Exception as error:
                            self.runtime_error = f'late {type(error).__name__}: {error}'
                    elif self.coordinator.pending[role] is not None:
                        self._retain(role, self.coordinator.pending[role])
            if self.camera is not None:
                try:
                    self.camera.close()
                    camera_close = dict(returned=True)
                except Exception as error:
                    camera_close = dict(returned=False, error=f'{type(error).__name__}: {error}')
            elif not self.camera_attempted:
                camera_close = dict(returned=True, not_started=True)
        result = report(self.state)
        result.update(status=self.state.phase, decisions=self.decisions, camera_close=camera_close,
                      runtime_error=self.runtime_error, samples=self.samples, turns=self.turns,
                      cancellation_responses=self.closing_calls)
        result['coordination'] = dict(owners=terminal,
            late_completions=[] if self.coordinator is None else
                [self._wire_row(row) for row in self.coordinator.late],
            resources_closed=camera_close['returned'] and all(row['thread_stopped']
                and row['close'] in ('confirmed', 'not_needed') and 'owner_error' not in row
                for row in terminal.values()))
        io_stopped = terminal.get('io', {}).get('thread_stopped', False)
        result['execution_records'] = self.io_snapshot if io_stopped else None
        return result


def run_inspection(session_factory, *, camera_factory=RosCamera, decision_factory=RuleDecision,
                   budget=NavigationBudget(), stop_requested=lambda: False, started_at=None,
                   startup_seconds=55., cleanup_seconds=12., interpreter=classify):
    """One opt-in task; caller owns camera, original owners hold Session/provider."""
    now = time.monotonic()
    started_at = now if started_at is None else started_at
    if not finite(started_at) or not 0 <= started_at <= now:
        raise ValueError('invalid original inspection start')
    for value, maximum in ((startup_seconds, 55.), (cleanup_seconds, 12.)):
        if not finite(value) or not 0 < value <= maximum:
            raise ValueError('invalid inspection startup/closing limit')
    return _Loop(session_factory, camera_factory, decision_factory, budget, stop_requested,
                 started_at, startup_seconds, cleanup_seconds, interpreter).run()


def main():
    import argparse
    import json
    from pathlib import Path
    import signal
    import threading
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    stopped = threading.Event()
    handlers = {sig: signal.signal(sig, lambda *_: stopped.set())
                for sig in (signal.SIGINT, signal.SIGTERM)}
    started = time.monotonic()
    try:
        from robot_harness import NavigationSession
        result = run_inspection(lambda: NavigationSession(args.endpoint),
                                stop_requested=stopped.is_set, started_at=started)
        (args.output/'report.json').write_text(json.dumps(result, indent=2)+'\n')
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
    return 0 if result['status'] == 'completed' and result['coordination']['resources_closed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
