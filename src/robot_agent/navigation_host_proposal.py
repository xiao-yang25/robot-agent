"""CLI-shaped proposal transport inside the isolated navigation container."""
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time
import uuid

from ._navigation_relay import PHASES, cancelled, directory, read_json, write_json
from .navigation import finite


def main(*, exchange=Path("/output")):
    if sys.argv[1:] == ['--version']:
        print('navigation-host-proposal-relay-v1 (model runs on host)')
        return 0
    started = time.monotonic()
    budget = float(os.environ['ROBOT_AGENT_PROPOSAL_REMAINING_SECONDS'])
    if not finite(budget) or not 0 < budget <= 30:
        raise ValueError('invalid inherited navigation proposal budget')
    deadline = started + budget
    inputs = json.loads(sys.stdin.read().splitlines()[-1])
    phase = inputs['phase']
    if phase not in PHASES:
        raise ValueError('unsupported navigation phase')
    answer_path = Path(sys.argv[sys.argv.index('--output-last-message') + 1])
    stopped = threading.Event()
    previous = {sig: signal.signal(sig, lambda *_: stopped.set()) for sig in (signal.SIGINT, signal.SIGTERM)}
    with directory(exchange) as output:
        try:
            os.mkdir('model-requests', mode=0o700, dir_fd=output)
        except FileExistsError:
            pass
        with directory('model-requests', parent=output) as exchange:
            os.mkdir(phase, mode=0o700, dir_fd=exchange)
            with directory(phase, parent=exchange) as request:
                nonce = uuid.uuid4().hex
                complete = False
                try:
                    remaining = deadline - time.monotonic()
                    if stopped.is_set() or remaining <= 0:
                        raise InterruptedError('proposal stopped before relay publication')
                    write_json(request, 'request.json', dict(nonce=nonce, inputs=inputs, remaining_seconds=remaining))
                    while True:
                        if stopped.is_set() or cancelled(request):
                            raise InterruptedError('host proposal cancelled')
                        if time.monotonic() >= deadline:
                            raise TimeoutError('host proposal deadline elapsed')
                        try:
                            response = read_json(request, 'response.json')
                        except FileNotFoundError:
                            time.sleep(.01)
                            continue
                        if response.get('nonce') != nonce:
                            raise ValueError('host proposal response identity changed')
                        if 'error' in response:
                            raise RuntimeError('host proposal failed: ' + response['error'])
                        if stopped.is_set() or time.monotonic() >= deadline:
                            raise TimeoutError('host proposal arrived after withdrawal/deadline')
                        answer_path.write_text(json.dumps(response['answer'], allow_nan=False) + '\n')
                        print(json.dumps({'item': {'type': 'agent_message'}}))
                        complete = True
                        return 0
                finally:
                    if not complete:
                        write_json(request, 'cancelled', {})
                    for sig, handler in previous.items():
                        signal.signal(sig, handler)


if __name__ == '__main__':
    raise SystemExit(main())
