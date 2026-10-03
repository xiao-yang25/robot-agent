"""Controlled tutorial executable; it makes no model requests or robot calls."""
import json
from pathlib import Path
import sys


def main():
    if sys.argv[1:] == ['--version']:
        print('controlled-navigation-tutorial-v1 (no model)')
        return 0
    inputs = json.loads(sys.stdin.read().splitlines()[-1])
    action = {'prepare': 'visit_a', 'after_a': 'visit_b', 'final': 'observed_complete'}[inputs['phase']]
    if action not in inputs['allowed_actions']:
        raise ValueError('controlled tutorial action is not allowed')
    answer = {key: inputs[key] for key in ('task_id', 'phase', 'observation_reference')}
    answer.update(action=action, reason='controlled tutorial proposal; no model or independent task assessment')
    output = Path(sys.argv[sys.argv.index('--output-last-message') + 1])
    output.write_text(json.dumps(answer, allow_nan=False) + '\n')
    print(json.dumps({'item': {'type': 'agent_message'}}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
