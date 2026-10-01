"""Bounded image-to-proposal CLI adapter; it cannot call the robot Session."""

import json
from pathlib import Path
import subprocess
import tempfile
import time

DISABLED_FEATURES = ('shell_tool', 'unified_exec', 'multi_agent', 'apps', 'plugins',
                     'browser_use', 'browser_use_external', 'computer_use', 'image_generation')


class CodexDecision:
    def __init__(self, output, *, model, executable='codex'):
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        self.model, self.executable = model, executable
        self.count = 0
        self.version = subprocess.check_output([executable, '--version'], text=True).strip()

    def decide(self, context, observation, deadline, stop_requested):
        from PIL import Image
        self.count += 1
        run = self.output / f'decision-{self.count}'
        run.mkdir()
        image = run / 'observation.png'
        Image.frombytes('RGB', (640, 480), observation['rgb']).save(image)
        input_record = {**context, 'measurement': {k: v for k, v in observation.items() if k != 'rgb'},
                        'model_requested': self.model, 'reasoning_requested': 'high',
                        'codex_version': self.version}
        (run / 'input.json').write_text(json.dumps(input_record, indent=2) + '\n')
        prompt = (
            'You are only the visual decision backend of an ALOHA simulation task. '
            'Do not call tools, read files, execute commands, browse or delegate. '
            'The application owns task state and all robot calls. Return one proposal only. '
            'Use the attached current camera image and joint measurements. '
            'Scene/object claims must come from this image, not the phase or operation counts. '
            'At prepare, the qualified reset starts with the red cube on the table and both grippers empty. '
            'The transfer skill includes picking it up with the right arm and handing it to the left. '
            'An initially ungrasped cube is expected, not a failure. Choose transfer if the image shows '
            'one reachable red cube on the tabletop and no visible incompatible scene; choose help if unclear. '
            'After transfer, choose hold only if the cube appears held by the left gripper and '
            'released by the right; otherwise choose help and explain uncertainty. '
            'At final, observed_success means the final image appears compatible with the goal, '
            'not proof of stable contact for one second. Use not_met for visible failure or help for uncertainty. '
            'Execution receipts and scene timing are not ground truth of task success. '
            'Do not invent a task evaluator result or raw robot actions. '
            'Preserve task_id, phase, epoch and sequence exactly. '\
            '\nCurrent task and measurement:\n' + json.dumps(input_record))
        (run / 'prompt.txt').write_text(prompt + '\n')
        properties = {'task_id': {'type': 'string'}, 'phase': {'type': 'string'},
                      'epoch': {'type': 'integer'}, 'sequence': {'type': 'integer'},
                      'action': {'type': 'string', 'enum': context['allowed_actions']},
                      'reason': {'type': 'string'}}
        schema = {'type': 'object', 'properties': properties,
                  'required': list(properties), 'additionalProperties': False}
        (run / 'schema.json').write_text(json.dumps(schema) + '\n')
        command = [self.executable, 'exec', '--ignore-user-config', '--strict-config',
                   '--ephemeral', '--skip-git-repo-check', '--sandbox', 'read-only',
                   '--model', self.model, '--json', '-c', 'model_reasoning_effort="high"',
                   '-c', 'web_search="disabled"', '--output-schema', str(run / 'schema.json'),
                   '--output-last-message', str(run / 'answer.json')]
        for feature in DISABLED_FEATURES:
            command += ['--disable', feature]
        process = None
        try:
            with tempfile.TemporaryDirectory(prefix='robot-agent-decision-') as cwd, \
                    (run / 'events.jsonl').open('w') as stdout, (run / 'stderr.log').open('w') as stderr:
                command += ['--cd', cwd, '--image', str(image), '-']
                if stop_requested():
                    raise InterruptedError('decision cancelled before launch')
                if time.monotonic() >= deadline:
                    raise TimeoutError('decision expired before launch')
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout,
                                           stderr=stderr, text=True)
                process.stdin.write(prompt)
                process.stdin.close()
                while process.poll() is None:
                    if stop_requested():
                        raise InterruptedError('decision cancelled')
                    if time.monotonic() >= deadline:
                        raise TimeoutError('decision deadline elapsed')
                    time.sleep(.01)
                # Completion may race with cancellation/expiry between polls.
                # A completed process does not revive a withdrawn proposal.
                if stop_requested():
                    raise InterruptedError('decision cancelled')
                if time.monotonic() >= deadline:
                    raise TimeoutError('decision deadline elapsed')
                if process.returncode != 0:
                    raise RuntimeError(f'decision CLI exited {process.returncode}; see retained logs')
                events = [json.loads(line) for line in (run / 'events.jsonl').read_text().splitlines()]
                if any(event.get('item', {}).get('type') in (
                        'command_execution', 'mcp_tool_call', 'web_search') for event in events):
                    raise RuntimeError('decision backend attempted tools; proposal not accepted')
                return json.loads((run / 'answer.json').read_text())
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            (run / 'process.json').write_text(json.dumps(
                {'pid': None if process is None else process.pid,
                 'returncode': None if process is None else process.returncode,
                 'reaped': process is not None and process.returncode is not None}, indent=2) + '\n')
