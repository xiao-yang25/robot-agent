"""Run one application task; the operator selects worker/model/recording paths."""

import argparse
import json
from pathlib import Path
import signal
import threading
import time

from .codex_decision import CodexDecision
from .handoff import HandoffTask, PROFILE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker-script', type=Path,
                        default=Path(__file__).with_name('aloha_worker.py'))
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--device', choices=('mps', 'cpu'), default='mps')
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    stopped = threading.Event()
    previous_handler = signal.signal(signal.SIGINT, lambda *_: stopped.set())
    session = None
    report = {'status': 'starting', 'task_verdict': 'unassessed', 'cleanup': 'unconfirmed'}
    started = time.monotonic()
    try:
        from robot_harness import Session
        backend = CodexDecision(output / 'decisions', model=args.model)
        session = Session(startup_timeout=90, mujoco={
            'profile': PROFILE, 'output': str(output / 'episodes'), 'seed': args.seed,
            'worker_script': str(args.worker_script.resolve()),
            'checkpoint': str(args.checkpoint.resolve()), 'device': args.device})
        task = HandoffTask(backend, started_at=started, stop_requested=stopped.is_set)
        report = task.run(session)
        report.update(host_pid=session.host_pid, worker_pid=session.worker_pid, cleanup='unconfirmed')
    except Exception as error:
        report.update(status='needs_help', reason=f'{type(error).__name__}: {error}')
    finally:
        try:
            if session is not None:
                session.close()
                report['cleanup'] = 'confirmed'
        except Exception as error:
            report['cleanup_error'] = str(error)
            report['cleanup'] = 'unconfirmed'
        finally:
            report['wall_seconds'] = time.monotonic() - started
            (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            signal.signal(signal.SIGINT, previous_handler)
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'completed' and report['cleanup'] == 'confirmed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
