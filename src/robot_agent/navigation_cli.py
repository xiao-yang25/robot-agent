"""One navigation application; connect to an operator-prepared isolated owner."""
import argparse
import json
from pathlib import Path
import signal
import threading
import time

from .navigation import MAP, NavigationTask
from .navigation_recovery import RecoveryNavigationTask, validate_map_id
from .navigation_decision import NavigationCodexDecision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--executable', default='codex')
    parser.add_argument('--task', choices=('fixed', 'recovery'), default='fixed')
    parser.add_argument('--expected-map-id', help='explicit prepared recovery scene identity; default world-v1')
    args = parser.parse_args()
    if args.task != 'recovery' and args.expected_map_id is not None:
        parser.error('--expected-map-id requires --task recovery')
    task_type = RecoveryNavigationTask if args.task == 'recovery' else NavigationTask
    task_options = dict(expected_map_id=args.expected_map_id if args.expected_map_id is not None else MAP) if args.task == 'recovery' else {}
    # Validate configuration before output, model preparation or opening a Session.
    if args.task == 'recovery':
        try: validate_map_id(task_options['expected_map_id'])
        except ValueError as error: parser.error(str(error))
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    stopped = threading.Event()
    handlers = {sig: signal.signal(sig, lambda *_: stopped.set())
                for sig in (signal.SIGINT, signal.SIGTERM)}
    session = None
    started = time.monotonic()
    report = {'status': 'needs_help', 'task_verdict': 'unassessed', 'connection_close': 'not_started'}
    try:
        from robot_harness import NavigationSession
        backend = NavigationCodexDecision(output / 'decisions', model=args.model, executable=args.executable)
        session = NavigationSession(args.endpoint)
        report = task_type(backend, stop_requested=stopped.is_set, started_at=started, **task_options).run(session)
    except Exception as error:
        report.update(reason=f'{type(error).__name__}: {error}')
    finally:
        try:
            if session is not None:
                report['close_response'] = session.close()
                report['connection_close'] = 'local_closed'
        except Exception as error:
            # NavigationSession.close disposes its local connection even when
            # the RPC outcome is unknown. Do not turn that into native closure.
            report.update(connection_close='local_closed', close_error=str(error))
        finally:
            report['native_cleanup'] = 'unknown'
            report['wall_seconds'] = time.monotonic() - started
            (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'completed' and report.get('connection_close') == 'local_closed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
