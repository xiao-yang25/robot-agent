"""Experimental fixed navigation assembly; existing public task paths are unchanged."""
import argparse
import json
import math
from pathlib import Path
import signal
import threading
import time

from ._task_runtime import SessionBinding as _Binding, TaskCalls, run_owned_task
from .navigation import NavigationBudget, NavigationTask


class _NavigationCalls(TaskCalls):
    def submit(self, request, **kwargs):
        return self.submit_bound(request, kwargs, {
            'request_id': request, 'site': kwargs['site'],
            'observation_reference': kwargs['expected_observation']})


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
    report = run_owned_task(task, calls, lambda: _Binding(session_factory), decision_factory,
                            stop_requested=stop_requested, cleanup_seconds=cleanup_seconds)
    io = report['coordination']['owners']['io']
    report['native_cleanup'] = 'unknown'
    # The factory may fail before or after disposal; an error proves neither.
    report['connection_close'] = ('local_closed' if io['close'] == 'confirmed' else
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
