"""Opt-in local file control for one inspection; not an execution authority."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import uuid


PROTOCOL = 'inspection-control-v1'


def _atomic(path, value):
    descriptor, temporary = tempfile.mkstemp(prefix='.control-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(value, stream, allow_nan=False)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_status(directory):
    with (Path(directory)/'status.json').open() as stream:
        value = json.load(stream)
    if (not isinstance(value, dict) or value.get('protocol') != PROTOCOL
            or not isinstance(value.get('instance_id'), str) or len(value['instance_id']) != 32):
        raise ValueError('unsupported task control status')
    return value


def request_cancel(directory):
    """Enqueue an idempotent request; only the Agent can acknowledge consumption."""
    directory = Path(directory)
    status = read_status(directory)
    if status.get('lifecycle') in ('closing', 'finished'):
        raise ValueError('task is closing or finished; inspect final results')
    request = dict(protocol=PROTOCOL, instance_id=status['instance_id'], command='cancel')
    _atomic(directory/'request.json', request)
    return dict(request='written', instance_id=status['instance_id'], acknowledged=False,
                note='Writing a request does not confirm Agent consumption or physical stopping.')


class LocalTaskControl:
    """One bounded latest-state slot and file worker; never calls a robot API."""
    def __init__(self, output, stopped):
        self.directory = Path(output)/'control'
        self.directory.mkdir(exist_ok=False)
        self.stopped = stopped
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.error = None
        self.state = dict(protocol=PROTOCOL, instance_id=uuid.uuid4().hex,
            lifecycle='starting', task=None, task_updated_at=None,
            cancel_requested=False, request_error=None, control_error=None,
            native_cleanup='unknown', task_verdict='unassessed')
        self.thread = threading.Thread(target=self._run, name='inspection-control', daemon=True)

    def start(self):
        self.thread.start()

    def publish(self, task):
        # Called by the task owner: only bounded in-memory work under the lock.
        with self.lock:
            self.state['task'] = task
            self.state['task_updated_at'] = time.time()
            self.state['lifecycle'] = ('closing' if task['phase'] in
                ('completed', 'cancelled', 'needs_help') else 'running')

    def _request(self):
        try:
            with (self.directory/'request.json').open() as stream:
                raw = stream.read(4097)
            if len(raw) > 4096:
                raise ValueError('oversized cancellation request')
            request = json.loads(raw)
            with self.lock:
                if (not isinstance(request, dict) or request.get('protocol') != PROTOCOL
                        or request.get('instance_id') != self.state['instance_id']
                        or request.get('command') != 'cancel'):
                    raise ValueError('invalid or stale cancellation request')
                if self.state['lifecycle'] in ('closing', 'finished'):
                    return
                self.state['request_error'] = None
                self.state['cancel_requested'] = True
                self.stopped.set()
        except FileNotFoundError:
            pass
        except (ValueError, OSError) as error:
            with self.lock:
                self.state['request_error'] = str(error)

    def _write(self):
        with self.lock:
            value = dict(self.state, published_at=time.time())
        _atomic(self.directory/'status.json', value)

    def _run(self):
        try:
            while not self.done.is_set():
                self._request()
                self._write()
                self.done.wait(.1)
            self._write()
        except Exception as error:
            self.error = f'{type(error).__name__}: {error}'
            self.stopped.set()  # Lost control reporting must not silently look healthy.

    def finish(self, result):
        with self.lock:
            self.state.update(lifecycle='finished', task=dict(task_id=result.get('task_id'),
                phase=result['status'], reason=result.get('reason')),
                task_updated_at=time.time(), native_cleanup=result.get('native_cleanup', 'unknown'),
                task_verdict=result.get('task_verdict', 'unassessed'),
                coordination=result.get('coordination'), runtime_error=result.get('runtime_error'))
        self.done.set()
        if self.thread.ident is not None:
            self.thread.join(timeout=1)
        return dict(worker_stopped=not self.thread.is_alive(), error=self.error,
                    instance_id=self.state['instance_id'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('status', 'cancel'))
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = read_status(args.directory) if args.command == 'status' else request_cancel(args.directory)
    except (OSError, ValueError) as error:
        parser.exit(2, f'Task control error: {error}\n')
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
