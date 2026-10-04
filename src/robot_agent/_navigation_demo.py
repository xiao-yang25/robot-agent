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


def run_host(command, *, output, host_output, model, executable, mounted_roots=()):
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
            client.write_text('from robot_agent.navigation_demo_client import main\n'
                              f'main(provider="host-codex", model={model!r})\n')
            command = list(command)
            command[command.index('--client-script') + 1] = str(client)
            host = subprocess.Popen([sys.executable, '-m', 'robot_agent.navigation_host_model',
                '--exchange', str(output), '--output', str(host_output), '--model', model,
                '--executable', executable], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
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
