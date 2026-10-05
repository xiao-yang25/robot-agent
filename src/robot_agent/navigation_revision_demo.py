"""Explicit revision tutorial caller; controlled business input, no recovery."""
from copy import deepcopy
import json
from pathlib import Path
import signal
import threading
import time

from .navigation import finite
from .navigation_revision import RevisionNavigationTask, IDENTITY_FIELDS
from .navigation_decision import NavigationCodexDecision


class TutorialPoll:
    """One caller-owned local slot; no blocking wait, thread or message service."""
    def __init__(self, action, delay, output):
        if action not in ('none', 'stop', 'redirect_b') or not finite(delay) or not 0 <= delay <= 9:
            raise ValueError('tutorial requires none/stop/redirect_b and delay in [0, 9]')
        self.action, self.delay, self.output = action, delay, Path(output)
        self.identity, self.available_at, self.delivered = None, None, False

    def emit(self, event, **fields):
        with (self.output/'instruction.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(event=event, steady=time.monotonic(), **fields), allow_nan=False)+'\n')

    def poll(self, context, deadline, stop_requested):
        if stop_requested():
            raise InterruptedError('tutorial business instruction cancelled')
        now = time.monotonic()
        if self.identity is None:
            self.identity = {key: context[key] for key in IDENTITY_FIELDS}
            self.available_at = now+self.delay
            self.emit('instruction_window', context=context, deadline=deadline)
        if any(context[key] != self.identity[key] for key in IDENTITY_FIELDS):
            raise ValueError('tutorial slot cannot be reused for another revision')
        if self.delivered or self.action == 'none' or now >= deadline or now < self.available_at:
            return None
        self.delivered = True
        answer = dict(self.identity, action=self.action)
        self.emit('instruction_returned', answer=answer)
        return answer


class ControlledRevisionDecision:
    """Tutorial-only proposal, without a model service or execution interface."""
    def decide(self, context, observation, deadline, stop_requested):
        answer = dict(task_id=context['task_id'], phase=context['phase'],
                      observation_reference=deepcopy(context['observation_reference']),
                      action=context['allowed_actions'][0], reason='controlled revision tutorial; no model')
        if 'revision_instruction' in context:
            answer['revision_id'] = context['revision_instruction']['revision_id']
        return answer


def run(endpoint, output, *, instruction, delay=0, backend=None):
    """Caller owns the local Session and poll provider; task borrows both."""
    output = Path(output).resolve()
    provider = TutorialPoll(instruction, delay, output)
    output.mkdir(parents=True, exist_ok=False)
    stopped = threading.Event()
    handlers = {sig: signal.signal(sig, lambda *_: stopped.set()) for sig in (signal.SIGINT, signal.SIGTERM)}
    started, session = time.monotonic(), None
    report = dict(status='needs_help', task_verdict='unassessed', connection_close='not_started')
    try:
        from robot_harness import NavigationSession
        decision = ControlledRevisionDecision() if backend is None else backend
        session = NavigationSession(endpoint)
        report = RevisionNavigationTask(decision, provider, stop_requested=stopped.is_set,
                                          started_at=started).run(session)
    except Exception as error:
        report['reason'] = f'{type(error).__name__}: {error}'
    finally:
        try:
            if session is not None:
                report['close_response'] = session.close()
                report['connection_close'] = 'local_closed'
        except Exception as error:
            report.update(connection_close='local_closed', close_error=str(error))
        finally:
            report.update(native_cleanup='unknown', wall_seconds=time.monotonic()-started)
            (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
    return 0 if report['status'] in ('completed', 'stopped_by_instruction') and report['connection_close'] == 'local_closed' else 1


def main(*, instruction, delay=0, provider='controlled', model='controlled-revision-no-model'):
    import sys
    import robot_agent
    import robot_harness
    for module, prefix in ((robot_agent, '/client-prefix'), (robot_harness, '/installed')):
        if not Path(module.__file__).resolve().is_relative_to(Path(prefix)):
            raise ValueError('revision tutorial requires its declared installed packages')
    if provider not in ('controlled', 'host-codex'):
        raise ValueError('unsupported revision proposal provider')
    backend = None
    if provider == 'host-codex':
        # Only a local proposal relay runs here; model credentials stay on the host.
        backend = NavigationCodexDecision(Path('/output/agent-proposals'), model=model,
            executable='/client-prefix/bin/robot-agent-navigation-host-proposal')
    return run(sys.argv[1], '/output/agent', instruction=instruction, delay=delay, backend=backend)
