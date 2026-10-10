"""Explicit controlled coordination tutorial; no model or physical-stop verdict."""
import json
from pathlib import Path
import platform
import signal
import sys
import threading
import time

from ._navigation_runtime import run_navigation

SCENARIOS = ('normal', 'final-decision-stop')


class _Trace:
    def __init__(self, path):
        path.touch(exist_ok=False)
        self.path, self.lock, self.sequence = path, threading.Lock(), 0

    def event(self, event, **fields):
        # No open stream is borrowed by owners that may still be draining.
        with self.lock:
            self.sequence += 1
            row = dict(event=event, sequence=self.sequence, steady=time.monotonic(),
                       thread=threading.current_thread().name, **fields)
            with self.path.open('a') as stream:
                stream.write(json.dumps(row, allow_nan=False) + '\n')


class _RecordedSession:
    def __init__(self, session, trace, closed):
        self.session, self.trace, self.closed = session, trace, closed
        try:
            trace.event('session_ready')
        except Exception:
            # Ownership has not reached the I/O owner yet.
            try:
                session.close()
            finally:
                closed.set()
            raise

    def capabilities(self):
        return self.session.capabilities()

    def observe(self):
        value = self.session.observe()
        self.trace.event('observation', value=value)
        return value

    def submit(self, request, **arguments):
        self.trace.event('submit', request=request, arguments=arguments)
        value = self.session.submit(request, **arguments)
        self.trace.event('submit_return', request=request, value=value)
        return value

    def status(self, request):
        value = self.session.status(request)
        if value.get('state') == 'finished':
            self.trace.event('finished', request=request, value=value)
        return value

    def cancel(self, request):
        try:
            self.trace.event('cancel', request=request)
        finally:
            value = self.session.cancel(request)
        self.trace.event('cancel_return', request=request, value=value)
        return value

    def close(self):
        try:
            try:
                self.trace.event('close_requested')
            finally:
                # Diagnostics cannot prevent the owned resource close attempt.
                value = self.session.close()
            self.trace.event('close_return', value=value)
            return value
        except Exception as error:
            try:
                self.trace.event('close_error', error=str(error))
            except Exception:
                pass
            raise
        finally:
            self.closed.set()


class _ControlledProposal:
    def __init__(self, scenario, trace, stopped, closed):
        self.scenario, self.trace, self.stopped, self.closed = scenario, trace, stopped, closed

    def decide(self, context, observation, deadline, stop_requested):
        self.trace.event('decision_begin', context=context, observation=observation)
        phase = context['phase']
        if self.scenario == 'final-decision-stop' and phase == 'final':
            # Deterministic tutorial input: withdraw while this decision remains
            # in flight, then release it only after the separate I/O close attempt.
            self.trace.event('task_stop', phase=phase)
            self.stopped.set()
            if not self.closed.wait(45):
                raise TimeoutError('I/O close did not release the controlled decision')
            self.trace.event('blocked_decision_released', phase=phase)
        action = {'prepare': 'visit_a', 'after_a': 'visit_b', 'final': 'observed_complete'}[phase]
        answer = {**context, 'action': action,
                  'reason': 'Controlled coordination tutorial; no model or independent task verdict.'}
        self.trace.event('decision_return', answer=answer)
        return answer


def _run_tutorial(session_factory, *, output, scenario):
    if scenario not in SCENARIOS:
        raise ValueError('unsupported coordination scenario')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    trace = _Trace(output / 'coordination.jsonl')
    stopped, closed = threading.Event(), threading.Event()
    handlers = {sig: signal.signal(sig, lambda *_: stopped.set())
                for sig in (signal.SIGINT, signal.SIGTERM)}
    started = time.monotonic()
    try:
        trace.event('start', domain='navigation',
                    scenario='normal' if scenario == 'normal' else 'stop-decision',
                    tutorial_scenario=scenario, python=platform.python_version(),
                    assembly='experimental-coordination', proposal='controlled-no-model')
        report = run_navigation(lambda: _RecordedSession(session_factory(), trace, closed),
            lambda: _ControlledProposal(scenario, trace, stopped, closed),
            stop_requested=stopped.is_set, started_at=started)
        report['wall_seconds'] = time.monotonic() - started
        report['tutorial'] = dict(assembly='experimental-coordination', scenario=scenario,
                                  proposal='controlled-no-model')
        (output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        trace.event('task_report', report=report)
        return report
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


def main(*, scenario='normal'):
    import robot_agent
    import robot_harness
    from robot_harness import NavigationSession
    for module, prefix in ((robot_agent, '/client-prefix'), (robot_harness, '/installed')):
        if not Path(module.__file__).resolve().is_relative_to(prefix):
            raise ValueError('coordination tutorial did not import its declared installed packages')
    report = _run_tutorial(lambda: NavigationSession(sys.argv[1]),
                           output='/output/agent', scenario=scenario)
    expected = 'completed' if scenario == 'normal' else 'cancelled'
    successful = (report['status'] == expected and report['coordination']['resources_closed']
                  and 'cancel_error' not in report
                  and all(row['error'] is None for row in report['coordination']['late_completions']))
    return 0 if successful else 1
