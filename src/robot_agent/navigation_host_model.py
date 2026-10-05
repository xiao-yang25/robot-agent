"""Host-only model worker for one public isolated navigation demonstration."""
import argparse
import json
import os
from pathlib import Path
import signal
import threading
import time

from ._navigation_relay import PHASES, cancelled, directory, proposal_request, read_json, write_json
from .navigation_decision import NavigationCodexDecision


def serve(exchange, output, model, executable, stopped, *, task='fixed'):
    deadline = time.monotonic() + 420
    records = []
    backend = NavigationCodexDecision(output / 'decisions', model=model, executable=executable)
    (output / 'ready.json').write_text(json.dumps(dict(model_requested=model, version=backend.version)) + '\n')
    try:
        while not exchange.exists():
            if stopped.is_set():
                return records
            if time.monotonic() >= deadline:
                raise TimeoutError('scene output was not created within the host budget')
            time.sleep(.02)
        with directory(exchange) as scene:
            stages = [('prepare',), ('after_revision', 'final'), ('final',)] if task == 'revision' else [(p,) for p in PHASES]
            for choices in stages:
                while not stopped.is_set():
                    if time.monotonic() >= deadline:
                        raise TimeoutError('host navigation model budget elapsed')
                    received = False
                    phase = choices[0]
                    try:
                        # Revision may complete A without an after_revision proposal.
                        # Select one published slot; model calls remain serial and once.
                        with directory('model-requests', parent=scene) as slots:
                            for candidate in choices:
                                try:
                                    os.stat(candidate, dir_fd=slots, follow_symlinks=False)
                                    phase = candidate
                                    break
                                except FileNotFoundError:
                                    continue
                            else:
                                raise FileNotFoundError('no proposal slot yet')
                        with directory('model-requests', parent=scene) as slots, directory(phase, parent=slots) as slot:
                            data = read_json(slot, 'request.json')
                            received = True
                            nonce, budget, context, observation = proposal_request(data, phase, model, task=task)
                            stop = lambda: stopped.is_set() or cancelled(slot)
                            if stop():
                                raise InterruptedError('proposal withdrawn before host decision')
                            try:
                                answer = backend.decide(context, observation,
                                    min(deadline, time.monotonic() + budget), stop)
                                response = dict(nonce=nonce, answer=answer)
                            except Exception as error:
                                response = dict(nonce=nonce, error=f'{type(error).__name__}: {error}')
                            if not stop():
                                write_json(slot, 'response.json', response)
                            records.append(dict(phase=phase, nonce=nonce, answered='answer' in response,
                                                withdrawn=stop()))
                            break
                    except FileNotFoundError:
                        if received:
                            raise  # Never replay a model call after exchange disappearance.
                        time.sleep(.02)
                if stopped.is_set():
                    return records
                if phase == 'final':
                    break
            while not stopped.is_set() and time.monotonic() < deadline:
                time.sleep(.02)
            if not stopped.is_set():
                raise TimeoutError('model worker was not stopped after the scene')
        return records
    finally:
        (output / 'model-server.json').write_text(json.dumps(dict(requests=records,
            model_requested=model, stop_observed=stopped.is_set(), remote_cleanup='unknown'), indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exchange', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='private host directory created by the launcher')
    parser.add_argument('--model', required=True)
    parser.add_argument('--executable', default='codex')
    parser.add_argument('--task', choices=('fixed', 'checkpoint', 'revision'), default='fixed')
    args = parser.parse_args()
    stopped = threading.Event()
    previous = {sig: signal.signal(sig, lambda *_: stopped.set()) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        serve(args.exchange, args.output, args.model, args.executable, stopped, task=args.task)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
