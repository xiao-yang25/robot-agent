"""Experimental fixed navigation assembly; existing public task paths are unchanged."""
import argparse
import json
import math
from pathlib import Path
import signal
import threading
import time

from ._task_runtime import Coordinator, Owner
from .navigation import NavigationBudget, NavigationTask


class _Binding:
    def __init__(self, factory):
        self.session = factory()

    def capabilities(self):
        return self.session.capabilities()

    def observe(self):
        return self.session.observe()

    def submit(self, request, *, deadline_ms, admission_deadline, operation_deadline, **kwargs):
        now = time.monotonic()
        if now >= admission_deadline:
            raise TimeoutError('proposal expired before actual submission')
        remaining = min(deadline_ms, int((operation_deadline - now) * 1000))
        if remaining < 1:
            raise TimeoutError('no original operation budget remains')
        return self.session.submit(request, deadline_ms=remaining, **kwargs)

    def status(self, request):
        return self.session.status(request)

    def cancel(self, request):
        return self.session.cancel(request)

    def close(self):
        return self.session.close()


class _NavigationCalls:
    def stopped(self):
        return self.coordinator.stopped()

    def decide(self, context, observation, deadline, stop_requested):
        self.decision_deadline = deadline
        return self.coordinator.call('decision', 'decide', (context, observation, deadline, lambda: self.coordinator.exchange.owner_stopped('decision')),
                         {}, deadline=deadline)

    def capabilities(self):
        return self.coordinator.call('io', 'capabilities', (), {}, deadline=self.task.deadline)

    def observe(self):
        value = self.coordinator.call('io', 'observe', (), {}, deadline=self.task.deadline)
        self.observation_completed_at = time.monotonic()
        return value

    def submit(self, request, **kwargs):
        # Revalidation precedes the original policy's operation-budget start.
        # This conservative anchor also counts caller delay before enqueueing.
        operation_deadline = min(self.task.deadline,
                                 self.observation_completed_at + self.task.budget.operation_seconds,
                                 time.monotonic() + kwargs['deadline_ms'] / 1000)
        kwargs.update(admission_deadline=self.decision_deadline, operation_deadline=operation_deadline)
        return self.coordinator.call('io', 'submit', (request,), kwargs, deadline=operation_deadline,
                         claim_deadline=min(self.decision_deadline, operation_deadline),
                         association={'request_id': request, 'site': kwargs['site'],
                                      'observation_reference': kwargs['expected_observation']})

    def status(self, request):
        cleanup = self.task.report['status'] != 'running'
        return self.coordinator.call('io', 'status', (request,), {}, cleanup=cleanup,
                         deadline=self.coordinator.cleanup_until() if cleanup else self.task.deadline,
                         association={'request_id': request})

    def cancel(self, request):
        return self.coordinator.call('io', 'cancel', (request,), {}, cleanup=True,
                                     deadline=self.coordinator.cleanup_until(),
                                     association={'request_id': request})


def run_navigation(session_factory, decision_factory, *, budget=NavigationBudget(),
                   stop_requested=lambda: False, started_at=None, cleanup_seconds=12.):
    """One-shot assembly; factories and Session close run only in their owners.

    Twelve seconds is a software closing wait for this selected binding (five
    second RPC/version waits), not a guarantee of thread or native termination.
    Uncooperative owners remain non-daemon and are reported as draining.
    """
    if type(cleanup_seconds) not in (int, float) or not math.isfinite(cleanup_seconds) or not 0 < cleanup_seconds <= 12:
        raise ValueError('cleanup wait must be finite and in (0, 12] seconds')
    calls = _NavigationCalls()
    task = NavigationTask(calls, budget=budget, stop_requested=calls.stopped, started_at=started_at)
    coordinator = Coordinator(task.task_id, stop_requested, cleanup_seconds)
    calls.coordinator, calls.task = coordinator, task
    calls.decision_deadline = task.deadline
    owners = [Owner(coordinator.exchange, 'io', lambda: _Binding(session_factory), close=lambda binding: binding.close()),
              Owner(coordinator.exchange, 'decision', decision_factory)]
    report = task.report
    try:
        coordinator.stopped()
        task.check_budget()
        for owner in owners:
            owner.start()
        report = task.run(calls)
    except Exception as error:
        report.update(status='cancelled' if isinstance(error, InterruptedError) else 'needs_help',
                      reason=f'{type(error).__name__}: {error}')
    finally:
        until = coordinator.cleanup_until()
        # Signal both owners before joining either; close is independent of slots.
        for owner in owners:
            coordinator.exchange.close(owner.role)
        terminal = {owner.role: owner.finish(until) for owner in owners}
        for owner in owners:
            call = coordinator.exchange.collect(owner.role)
            if call is not None:
                coordinator.retain(owner.role, call)
            elif coordinator.pending[owner.role] is not None:
                coordinator.retain(owner.role, coordinator.pending[owner.role])
        io = terminal['io']
        report.update(native_cleanup='unknown', coordination={
            'owners': terminal, 'late_completions': coordinator.late,
            'resources_closed': all(row['thread_stopped'] and row['close'] in ('confirmed', 'not_needed')
                                    and 'owner_error' not in row for row in terminal.values())})
        report['connection_close'] = ('local_closed' if io['close'] in ('confirmed', 'error') else
                                      'not_started' if io['initialization'] == 'not_started' else 'unknown')
        if 'close_response' in io:
            report['close_response'] = io['close_response']
        if 'close_error' in io:
            report['close_error'] = io['close_error']
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--executable', default='codex')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    stopped = threading.Event()
    handlers = {sig: signal.signal(sig, lambda *_: stopped.set()) for sig in (signal.SIGINT, signal.SIGTERM)}
    started = time.monotonic()
    try:
        from .navigation_decision import NavigationCodexDecision
        def session_factory():
            from robot_harness import NavigationSession
            return NavigationSession(args.endpoint)
        report = run_navigation(session_factory,
            lambda: NavigationCodexDecision(output / 'decisions', model=args.model, executable=args.executable),
            stop_requested=stopped.is_set, started_at=started)
        report['wall_seconds'] = time.monotonic() - started
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'completed' and report['coordination']['resources_closed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
