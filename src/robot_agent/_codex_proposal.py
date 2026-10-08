"""Private bounded proposal subprocess; no robot execution capability."""
import json
import os
import subprocess
import tempfile
import time

DISABLED_FEATURES = ('shell_tool', 'unified_exec', 'multi_agent', 'apps', 'plugins',
                     'browser_use', 'browser_use_external', 'computer_use', 'image_generation')
MAX_PROMPT_BYTES = 1024 * 1024


def _check_pending(deadline, stop_requested):
    if stop_requested():
        raise InterruptedError('decision cancelled')
    if time.monotonic() >= deadline:
        raise TimeoutError('decision deadline elapsed')


def _write_prompt(stream, payload, deadline, stop_requested):
    # The child may never read stdin. Do not block the owner while writing.
    try:
        descriptor = stream.fileno()
        os.set_blocking(descriptor, False)
        offset = 0
        while offset < len(payload):
            _check_pending(deadline, stop_requested)
            try:
                offset += os.write(descriptor, payload[offset:offset + 65536])
            except BlockingIOError:
                time.sleep(.01)
    finally:
        stream.close()  # EOF; no buffered text writes to flush.


def run_proposal(executable, model, run, prompt, deadline, stop_requested, *, image=None):
    command = [executable, 'exec', '--ignore-user-config', '--strict-config',
               '--ephemeral', '--skip-git-repo-check', '--sandbox', 'read-only',
               '--model', model, '--json', '-c', 'model_reasoning_effort="high"',
               '-c', 'web_search="disabled"', '--output-schema', str(run / 'schema.json'),
               '--output-last-message', str(run / 'answer.json')]
    for feature in DISABLED_FEATURES:
        command += ['--disable', feature]
    process = None
    try:
        with tempfile.TemporaryDirectory(prefix='robot-agent-decision-') as cwd, \
                (run / 'events.jsonl').open('w') as stdout, (run / 'stderr.log').open('w') as stderr:
            command += ['--cd', cwd]
            if image is not None:
                command += ['--image', str(image)]
            command += ['-']
            if stop_requested():
                raise InterruptedError('decision cancelled before launch')
            if time.monotonic() >= deadline:
                raise TimeoutError('decision expired before launch')
            if len(prompt) > MAX_PROMPT_BYTES:
                raise ValueError('decision prompt exceeds 1 MiB UTF-8 limit')
            payload = prompt.encode('utf-8')
            if len(payload) > MAX_PROMPT_BYTES:
                raise ValueError('decision prompt exceeds 1 MiB UTF-8 limit')
            _check_pending(deadline, stop_requested)
            environment = dict(os.environ, ROBOT_AGENT_PROPOSAL_REMAINING_SECONDS=str(deadline-time.monotonic()))
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout,
                                       stderr=stderr, text=True, env=environment)
            _write_prompt(process.stdin, payload, deadline, stop_requested)
            while process.poll() is None:
                _check_pending(deadline, stop_requested)
                time.sleep(.01)
            # Completion may race with cancellation/expiry between polls.
            # A completed process does not revive a withdrawn proposal.
            _check_pending(deadline, stop_requested)
            if process.returncode != 0:
                raise RuntimeError(f'decision CLI exited {process.returncode}; see retained logs')
            events = [json.loads(line) for line in (run / 'events.jsonl').read_text().splitlines()]
            if any(event.get('item', {}).get('type') in (
                    'command_execution', 'mcp_tool_call', 'web_search') for event in events):
                raise RuntimeError('decision backend attempted tools; proposal not accepted')
            answer = json.loads((run / 'answer.json').read_text())
            _check_pending(deadline, stop_requested)
            return answer
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
