#!/usr/bin/env python3
"""Controlled executable proposals; never calls a model or robot tools."""
import json
import os
from pathlib import Path
import signal
import sys
import time


def main():
    if '--version' in sys.argv:
        print('controlled-navigation-fault-proposal-v1')
        return
    inputs = json.loads(sys.stdin.read().splitlines()[-1])
    case, phase = inputs['model_requested'], inputs['phase']
    if case not in ('error-before-a', 'help-after-a', 'late-final'):
        raise ValueError('unsupported controlled proposal case')
    output = Path(sys.argv[sys.argv.index('--output-last-message')+1])
    answer = {key: inputs[key] for key in ('task_id', 'phase', 'observation_reference')}
    answer.update(action={'prepare': 'visit_a', 'after_a': 'visit_b',
                          'final': 'observed_complete'}[phase], reason='controlled test proposal')
    (output.parent/'fixture-start.json').write_text(json.dumps(
        dict(case=case, phase=phase, pid=os.getpid(), steady=time.monotonic())))

    def publish(kind='agent_message'):
        output.write_text(json.dumps(answer))
        print(json.dumps({'item': {'type': kind}}), flush=True)

    if case == 'late-final' and phase == 'final':
        def late_answer(*_):
            publish()
            (output.parent/'fixture-late.json').write_text(json.dumps(
                dict(phase=phase, pid=os.getpid(), steady=time.monotonic(), on_termination=True)))
            raise SystemExit(0)
        signal.signal(signal.SIGTERM, late_answer)
        time.sleep(60)  # Beyond the unchanged public CLI proposal budget (30s).
        raise RuntimeError('expired proposal child was not terminated')
    if case == 'help-after-a' and phase == 'after_a':
        answer.update(action='help', reason='controlled uncertainty after fresh A feedback')
    publish('command_execution' if case == 'error-before-a' else 'agent_message')


if __name__ == '__main__':
    main()
