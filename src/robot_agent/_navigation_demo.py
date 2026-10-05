"""Host ownership for the opt-in local model demonstration; Harness owns Docker."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


def finish(process, seconds):
    """Stop one owned leader, then remove any surviving owned process group."""
    forced = False
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            forced = True
    try:
        os.killpg(process.pid, signal.SIGKILL)
        forced = True
    except ProcessLookupError:
        pass
    process.wait(timeout=5)
    return {'pid': process.pid, 'returncode': process.returncode, 'reaped': True, 'group_forced': forced}


def checkpoint_client(configuration, *, provider='controlled', model='controlled-checkpoint-no-model'):
    from .navigation_checkpoint_demo import TutorialInstruction
    instruction, delay = configuration['instruction'], configuration['delay']
    TutorialInstruction(instruction, delay, '.')
    return ('from robot_agent.navigation_checkpoint_demo import main\n'
            f'raise SystemExit(main(instruction={instruction!r}, delay={delay!r}, '
            f'provider={provider!r}, model={model!r}))\n')


def revision_client(configuration, *, provider='controlled', model='controlled-revision-no-model'):
    from .navigation_revision_demo import TutorialPoll
    instruction, delay = configuration['instruction'], configuration['delay']
    TutorialPoll(instruction, delay, '.')
    return ('from robot_agent.navigation_revision_demo import main\n'
            f'raise SystemExit(main(instruction={instruction!r}, delay={delay!r}, '
            f'provider={provider!r}, model={model!r}))\n')


def run_controlled_checkpoint(command, configuration, *, revision=False):
    stopped = 0
    def stop(signum, _frame):
        nonlocal stopped
        stopped = signum
    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    process = None
    result = 1
    try:
        with tempfile.TemporaryDirectory(prefix='robot-agent-checkpoint-client-') as temporary:
            client = Path(temporary)/'client.py'
            client.write_text(revision_client(configuration) if revision else checkpoint_client(configuration))
            command = list(command)
            command[command.index('--client-script')+1] = str(client)
            try:
                if stopped:
                    return 128+stopped
                process = subprocess.Popen(command, start_new_session=True)
                while process.poll() is None and not stopped:
                    time.sleep(.05)
                if stopped and process.poll() is None:
                    process.send_signal(stopped)
                record = finish(process, 110)
                result = 128+stopped if stopped else record['returncode']
                if record['group_forced']:
                    result = result or 1
            finally:
                if process is not None and process.poll() is None:
                    finish(process, 110)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    return result


def run_host(command, *, output, host_output, model, executable, mounted_roots=(), checkpoint=None, revision=None):
    if checkpoint is not None and revision is not None:
        raise ValueError("select one navigation business task")
    output, host_output = Path(output).resolve(), Path(host_output).resolve()
    if output.exists() or host_output.is_relative_to(output) or output.is_relative_to(host_output):
        raise ValueError('use new, separate scene and private host output directories')
    for root in mounted_roots:
        root = Path(root).resolve()
        if host_output.is_relative_to(root) or root.is_relative_to(host_output):
            raise ValueError('private host output must not overlap any container mount')
    host_output.mkdir(parents=True, exist_ok=False)
    stopped = 0

    def stop(signum, _frame):
        nonlocal stopped
        stopped = signum

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    host = launcher = None
    result = 1
    record = {'model_requested': model, 'remote_cleanup': 'unknown'}
    temporary = tempfile.TemporaryDirectory(prefix='robot-agent-navigation-client-')
    try:
        with (host_output / 'model-server.log').open('w') as log:
            client = Path(temporary.name) / 'client.py'
            client.write_text(revision_client(revision, provider='host-codex', model=model)
                if revision is not None else checkpoint_client(checkpoint, provider='host-codex', model=model)
                if checkpoint is not None else 'from robot_agent.navigation_demo_client import main\n'
                f'main(provider="host-codex", model={model!r})\n')
            command = list(command)
            command[command.index('--client-script') + 1] = str(client)
            host_command = [sys.executable, '-m', 'robot_agent.navigation_host_model',
                '--exchange', str(output), '--output', str(host_output), '--model', model,
                '--executable', executable]
            if revision is not None:
                host_command.extend(['--task', 'revision'])
            elif checkpoint is not None:
                host_command.extend(['--task', 'checkpoint'])
            host = subprocess.Popen(host_command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            ready_until = time.monotonic() + 6
            while not (host_output/'ready.json').exists():
                if stopped or host.poll() is not None or time.monotonic() >= ready_until:
                    raise RuntimeError('host model version preparation failed or stopped; see host log')
                time.sleep(.02)
            if stopped or host.poll() is not None:
                raise InterruptedError('host model withdrawn before scene launch')
            launcher = subprocess.Popen(command, start_new_session=True)
            while launcher.poll() is None:
                if stopped or host.poll() is not None:
                    launcher.send_signal(stopped or signal.SIGTERM)
                    result = 128 + stopped if stopped else 1
                    break
                time.sleep(.05)
            else:
                result = launcher.returncode
    finally:
        # Keep the read-only client bind file until Harness finishes cleanup.
        for name, process, grace in (('launcher', launcher, 110), ('host_model', host, 6)):
            if process is None:
                continue
            try:
                record[name] = finish(process, grace)
                if record[name]['group_forced'] or record[name]['returncode'] != 0:
                    result = result or 1
            except Exception as error:
                record[name] = {'pid': process.pid, 'cleanup_error': str(error), 'reaped': False}
                result = result or 1
        temporary.cleanup()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        record.update(exit_code=result, interrupted_by=stopped)
        (host_output/'processes.json').write_text(json.dumps(record, indent=2) + '\n')
    return result
