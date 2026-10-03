"""Real local subprocess fixtures; these do not call a visual model service."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from robot_agent.codex_decision import CodexDecision
from robot_agent.handoff import Budget, HandoffTask
from test_handoff import SessionFixture


class CodexProcessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.executable = self.root / 'proposal-fixture'
        self.executable.write_text(f'#!{sys.executable}\n' + '''
import json
from pathlib import Path
import signal
import sys
import time

if '--version' in sys.argv:
    print('proposal-process-fixture')
    raise SystemExit(0)
answer_path = Path(sys.argv[sys.argv.index('--output-last-message') + 1])
context = json.loads(sys.stdin.read().split('Current task and measurement:\\n', 1)[1])
answer = {key: context[key] for key in ('task_id', 'phase', 'epoch', 'sequence')}
answer.update(action='hold', reason='controlled subprocess proposal, not visual perception')

def finish(*unused):
    answer_path.write_text(json.dumps(answer))
    print(json.dumps({'type': 'turn.completed'}), flush=True)
    raise SystemExit(0)

signal.signal(signal.SIGTERM, finish)
if 'ignore' in Path(__file__).name:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
(answer_path.parent / 'ready').touch()
if 'immediate' in Path(__file__).name:
    finish()
while True:
    time.sleep(.01)
''')
        self.executable.chmod(0o755)
        self.backend = CodexDecision(self.root / 'decisions', model='process-fixture',
                                     executable=str(self.executable))
        self.context = {'task_id': 'fixture-task', 'phase': 'after_transfer', 'epoch': 0,
                        'sequence': 400, 'goal': 'fixture goal', 'allowed_actions': ['hold', 'help']}
        self.observation = {'epoch': 0, 'sequence': 400, 'sim_seconds': 8., 'joints': [0.] * 14,
                            'image': {'shape': [480, 640, 3], 'dtype': 'uint8', 'camera': 'top'},
                            'rgb': bytes(480 * 640 * 3)}

    def process_record(self):
        record = json.loads((self.root / 'decisions/decision-1/process.json').read_text())
        self.assertTrue(record['reaped'])
        # Popen's successful wait is corroborated by the child no longer existing.
        with self.assertRaises(ProcessLookupError):
            import os
            os.kill(record['pid'], 0)
        return record

    def test_cancel_before_launch_is_interruption_and_creates_no_child(self):
        with self.assertRaises(InterruptedError):
            self.backend.decide(self.context, self.observation, time.monotonic() + 5, lambda: True)
        record = json.loads((self.root / 'decisions/decision-1/process.json').read_text())
        self.assertIsNone(record['pid'])
        self.assertFalse(record['reaped'])

    def test_expiry_before_launch_creates_no_child(self):
        with self.assertRaises(TimeoutError):
            self.backend.decide(self.context, self.observation, time.monotonic() - 1, lambda: False)
        record = json.loads((self.root / 'decisions/decision-1/process.json').read_text())
        self.assertIsNone(record['pid'])

    def test_running_child_timeout_reaps_late_answer(self):
        with self.assertRaises(TimeoutError):
            self.backend.decide(self.context, self.observation, time.monotonic() + 1, lambda: False)
        self.assertEqual(self.process_record()['returncode'], 0)
        answer = json.loads((self.root / 'decisions/decision-1/answer.json').read_text())
        self.assertEqual(answer['action'], 'hold')

    def test_running_child_cancel_late_hold_cannot_reach_session(self):
        stopped = False
        backend = self.backend
        ready = self.root / 'decisions/decision-1/ready'

        def stop_requested():
            nonlocal stopped
            stopped = stopped or ready.exists()
            return stopped

        class MixedBackend:
            def decide(self, context, observation, deadline, stop):
                if context['phase'] == 'prepare':
                    return {**{key: context[key] for key in ('task_id', 'phase', 'epoch', 'sequence')},
                            'action': 'transfer', 'reason': 'test initial proposal'}
                return backend.decide(context, observation, deadline, stop)

        session = SessionFixture()
        report = HandoffTask(MixedBackend(), stop_requested=stop_requested).run(session)
        self.assertEqual(report['status'], 'cancelled')
        self.assertEqual(len(session.submissions), 1)
        self.assertEqual(len(report['decisions']), 1)
        self.assertEqual(self.process_record()['returncode'], 0)
        self.assertEqual(json.loads((ready.parent / 'answer.json').read_text())['action'], 'hold')

    def test_running_child_timeout_late_hold_cannot_reach_session(self):
        backend = self.backend

        class MixedBackend:
            def decide(self, context, observation, deadline, stop):
                if context['phase'] == 'prepare':
                    return {**{key: context[key] for key in ('task_id', 'phase', 'epoch', 'sequence')},
                            'action': 'transfer', 'reason': 'test initial proposal'}
                return backend.decide(context, observation, deadline, stop)

        session = SessionFixture()
        report = HandoffTask(MixedBackend(), budget=Budget(decision_seconds=1)).run(session)
        self.assertEqual(report['status'], 'needs_help')
        self.assertIn('deadline', report['reason'])
        self.assertEqual(len(session.submissions), 1)
        self.assertEqual(self.process_record()['returncode'], 0)
        answer = json.loads((self.root / 'decisions/decision-1/answer.json').read_text())
        self.assertEqual(answer['action'], 'hold')

    def test_child_ignoring_terminate_is_killed_and_reaped(self):
        ignoring = self.root / 'ignore-fixture'
        self.executable.rename(ignoring)
        self.backend.executable = str(ignoring)
        with self.assertRaises(TimeoutError):
            self.backend.decide(self.context, self.observation, time.monotonic() + 1, lambda: False)
        import signal
        self.assertEqual(self.process_record()['returncode'], -signal.SIGKILL)

    def exit_race(self, *, cancel=False):
        immediate = self.root / 'immediate-fixture'
        self.executable.rename(immediate)
        self.backend.executable = str(immediate)
        exited = False
        real_popen = subprocess.Popen
        deadline = time.monotonic() + 10

        def popen(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            original_poll = process.poll

            def poll():
                nonlocal exited
                result = original_poll()
                if result is not None:
                    exited = True
                return result

            process.poll = poll
            return process

        clock = SimpleNamespace(monotonic=lambda: deadline + 1 if exited and not cancel else time.monotonic(),
                                sleep=time.sleep)
        with patch('robot_agent._codex_proposal.subprocess.Popen', side_effect=popen), \
                patch('robot_agent._codex_proposal.time', clock):
            with self.assertRaises(InterruptedError if cancel else TimeoutError):
                self.backend.decide(self.context, self.observation, deadline, lambda: exited and cancel)
        self.assertEqual(self.process_record()['returncode'], 0)

    def test_process_exit_racing_cancellation_rejects_completed_answer(self):
        self.exit_race(cancel=True)

    def test_process_exit_racing_deadline_rejects_completed_answer(self):
        self.exit_race()


if __name__ == '__main__':
    unittest.main()
