"""Experimental station inspection application for a prepared Owner and ROS camera."""
import argparse
import json
from pathlib import Path
import signal
import threading
import time

from ._inspection_camera import RosCamera
from ._inspection_marker import classify, read_bright_marker, read_marker
from ._inspection_runtime import run_inspection


READERS = {'fixed-center': classify, 'located-white-panel': read_marker,
           'located-bright-panel': read_bright_marker}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', required=True, help='operator-prepared public NavigationSession endpoint')
    parser.add_argument('--output', type=Path, required=True, help='new task output directory')
    parser.add_argument('--marker-reader', choices=tuple(READERS), required=True,
                        help='explicit controlled marker interpretation; no automatic fallback')
    args = parser.parse_args(argv)
    if not args.endpoint.strip():
        parser.error('--endpoint must not be empty')
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    stopped, handlers = threading.Event(), {}
    started = time.monotonic()
    result = dict(status='needs_help', task_verdict='unassessed', native_cleanup='unknown',
                  runtime_error=None, coordination=dict(resources_closed=False))
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            handlers[sig] = signal.signal(sig, lambda *_: stopped.set())
        from robot_harness import NavigationSession
        result = run_inspection(lambda: NavigationSession(args.endpoint),
            camera_factory=RosCamera, stop_requested=stopped.is_set, started_at=started,
            interpreter=READERS[args.marker_reader])
    except Exception as error:
        # An unexpected loop/import failure cannot certify resource closure.
        result.update(runtime_error=f'{type(error).__name__}: {error}')
    finally:
        try:
            result['wall_seconds'] = time.monotonic() - started
            result['application'] = dict(name='station-inspection',
                marker_reader=args.marker_reader, decision_provider='rules-no-model')
            (output/'report.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if (result['status'] == 'completed' and result['runtime_error'] is None
                 and result['coordination']['resources_closed']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
