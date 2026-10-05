"""Controlled tutorial executable; it makes no model requests or robot calls."""
import json
from pathlib import Path
import sys


def main():
    if sys.argv[1:] == ['--version']:
        print('controlled-navigation-tutorial-v1 (no model)')
        return 0
    inputs = json.loads(sys.stdin.read().splitlines()[-1])
    action = {'prepare': 'visit_a', 'after_a': 'visit_b', 'after_revision': 'visit_b', 'after_failure':'visit_b', 'final': 'observed_complete'}[inputs['phase']]
    instruction = inputs.get('checkpoint_instruction')
    if instruction is not None:
        action = {'continue_b':'visit_b','finish_at_a':'finish_at_a'}[instruction['action']]
    if action not in inputs['allowed_actions']:
        raise ValueError('controlled tutorial action is not allowed')
    answer = {key: inputs[key] for key in ('task_id', 'phase', 'observation_reference')}
    answer.update(action=action, reason='controlled tutorial proposal; no model or independent task assessment')
    if instruction is not None:
        answer['checkpoint_id'] = instruction['checkpoint_id']
    if 'revision_instruction' in inputs:
        command = inputs['revision_instruction']
        if command['action'] != 'redirect_b':
            raise ValueError('controlled revision requires redirect_b')
        answer['revision_id'] = command['revision_id']
    if 'failure_context' in inputs:
        command = inputs['failure_context']
        if command['native_outcome'] != 'failed':
            raise ValueError('controlled recovery requires confirmed failed A')
        answer.update({key: command[key] for key in ('recovery_id','request_id','operation_id','goal_id')})
    output = Path(sys.argv[sys.argv.index('--output-last-message') + 1])
    output.write_text(json.dumps(answer, allow_nan=False) + '\n')
    print(json.dumps({'item': {'type': 'agent_message'}}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
