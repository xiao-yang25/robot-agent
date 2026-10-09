"""Experimental ALOHA assembly reusing private task handoff and original policy."""
import argparse
import json
import math
from pathlib import Path
import signal
import threading
import time

from ._task_runtime import SessionBinding, TaskCalls, run_owned_task
from .handoff import Budget, HandoffTask, PROFILE


class _Binding(SessionBinding):
    def close(self):
        self.session.close()
        # Public Session close confirms worker cleanup and Host reap. Navigation
        # connection disposal has a different contract and is not interpreted here.
        return {key: getattr(self.session, key) for key in ('host_pid', 'worker_pid')
                if hasattr(self.session, key)}


class _HandoffCalls(TaskCalls):
    def submit(self, request, **kwargs):
        return self.submit_bound(request, kwargs, {
            'request_id': request, 'skill': kwargs['skill'], 'steps': kwargs['steps'],
            'observation_reference': kwargs['expected_observation']})


def run_handoff(session_factory, decision_factory, *, budget=Budget(),
                stop_requested=lambda: False, started_at=None, cleanup_seconds=30.):
    """Keep the original business policy; expose resource close independently.

    The selected Session has five-second RPC waits and up to ten seconds in close.
    Thirty seconds allows an in-flight RPC, cancel/status and close in sequence;
    it is a software waiting budget, not a guarantee for startup/plugins/motion.
    """
    if type(cleanup_seconds) not in (int, float) or not math.isfinite(cleanup_seconds) or not 0 < cleanup_seconds <= 30:
        raise ValueError('cleanup wait must be finite and in (0, 30] seconds')
    calls = _HandoffCalls()
    task = HandoffTask(calls, budget=budget, stop_requested=calls.stopped, started_at=started_at)
    report = run_owned_task(task, calls, lambda: _Binding(session_factory), decision_factory,
                            stop_requested=stop_requested, cleanup_seconds=cleanup_seconds)
    for call in report['coordination']['late_completions']:
        value = call['value']
        if call['role'] == 'io' and call['method'] == 'observe' and isinstance(value, dict) and 'rgb' in value:
            # Raw camera bytes belong to observations, not the JSON task report.
            # Keep the measured reference/state and explicitly label omission;
            # this retained metadata is not a reusable complete model observation.
            call['value'] = {key: field for key, field in value.items() if key != 'rgb'}
            call['value']['rgb_retention'] = 'omitted_from_task_report'
    io = report['coordination']['owners']['io']
    report['cleanup'] = 'confirmed' if io['thread_stopped'] and io['close'] == 'confirmed' else 'unconfirmed'
    if 'close_response' in io:
        report.update(io['close_response'])
    if 'close_error' in io:
        report['cleanup_error'] = io['close_error']
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker-script', type=Path,
                        default=Path(__file__).with_name('aloha_worker.py'))
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--executable', default='codex')
    parser.add_argument('--device', choices=('mps', 'cpu'), default='mps')
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    stopped = threading.Event()
    handlers = {sig: signal.signal(sig, lambda *_: stopped.set()) for sig in (signal.SIGINT, signal.SIGTERM)}
    started = time.monotonic()
    try:
        from .codex_decision import CodexDecision
        def session_factory():
            from robot_harness import Session
            return Session(startup_timeout=90, mujoco={
                'profile': PROFILE, 'output': str(output / 'episodes'), 'seed': args.seed,
                'worker_script': str(args.worker_script.resolve()),
                'checkpoint': str(args.checkpoint.resolve()), 'device': args.device})
        report = run_handoff(session_factory,
            lambda: CodexDecision(output / 'decisions', model=args.model, executable=args.executable),
            stop_requested=stopped.is_set, started_at=started)
        report['wall_seconds'] = time.monotonic() - started
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'completed' and report['cleanup'] == 'confirmed' and report['coordination']['resources_closed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
