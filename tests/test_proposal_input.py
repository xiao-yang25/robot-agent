"""Actual local CLI input/exit regression; no model or Harness execution."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from robot_agent._codex_proposal import run_proposal


class ProposalInputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.run = self.root / 'run'
        self.run.mkdir()
        (self.run / 'schema.json').write_text('{}\n')
        self.executable = self.root / 'proposal-fixture'
        self.executable.write_text(f'#!{sys.executable}\n' + '''
import json, os, sys, time
from pathlib import Path
answer = Path(sys.argv[sys.argv.index('--output-last-message') + 1])
(answer.parent / 'started.json').write_text(json.dumps({'pid': os.getpid()}))
mode = sys.argv[sys.argv.index('--model') + 1]
if mode == 'unread':
    time.sleep(2)  # Finite fixture lifetime bounds the pre-fix failure.
    raise SystemExit(0)
if mode == 'slow-reader':
    time.sleep(.05)
data = sys.stdin.buffer.read()
(answer.parent / 'received.txt').write_bytes(data)
answer.write_text(json.dumps({'action': 'help', 'reason': 'local fixture'}))
''')
        self.executable.chmod(0o700)

    def request(self, prompt, *, mode='normal', deadline=None, stopped=lambda: False):
        return run_proposal(str(self.executable), mode, self.run, prompt,
                            time.monotonic() + 5 if deadline is None else deadline, stopped)

    def reaped(self):
        record = json.loads((self.run / 'process.json').read_text())
        self.assertTrue(record['reaped'])
        self.assertEqual(record['pid'], json.loads((self.run / 'started.json').read_text())['pid'])
        with self.assertRaises(ProcessLookupError):
            os.kill(record['pid'], 0)

    def test_backpressure_preserves_exact_unicode_input_and_eof(self):
        prompt = '导航🚶\n' * 20000
        self.assertEqual(self.request(prompt, mode='slow-reader')['action'], 'help')
        self.assertEqual((self.run / 'received.txt').read_bytes(), prompt.encode('utf-8'))
        self.reaped()

    def test_unread_large_input_cancel_ends_and_reaps_child(self):
        with self.assertRaises(InterruptedError):
            self.request('x' * 524288, mode='unread', stopped=lambda: (self.run / 'started.json').exists())
        self.reaped()

    def test_unread_large_input_deadline_ends_and_reaps_child(self):
        with self.assertRaises(TimeoutError):
            self.request('x' * 524288, mode='unread', deadline=time.monotonic() + 1)
        self.reaped()

    def test_oversized_utf8_input_is_rejected_before_child_launch(self):
        with self.assertRaisesRegex(ValueError, 'prompt'):
            self.request('界' * 400000, mode='unread')
        record = json.loads((self.run / 'process.json').read_text())
        self.assertIsNone(record['pid'])
        self.assertFalse(record['reaped'])
        self.assertFalse((self.run / 'started.json').exists())

    def decode_race(self, cancel):
        decoded = False
        real_loads = json.loads
        deadline = time.monotonic() + 5

        def decode(value, *args, **kwargs):
            nonlocal decoded
            answer = real_loads(value, *args, **kwargs)
            decoded = True
            return answer

        clock = SimpleNamespace(monotonic=lambda: deadline + 1 if decoded and not cancel else time.monotonic(),
                                sleep=time.sleep)
        with patch('robot_agent._codex_proposal.json.loads', side_effect=decode), \
                patch('robot_agent._codex_proposal.time', clock):
            with self.assertRaises(InterruptedError if cancel else TimeoutError):
                self.request('local input', deadline=deadline, stopped=lambda: decoded and cancel)
        self.reaped()

    def test_cancellation_during_decode_rejects_completed_proposal(self):
        self.decode_race(cancel=True)

    def test_deadline_during_decode_rejects_completed_proposal(self):
        self.decode_race(cancel=False)


if __name__ == '__main__':
    unittest.main()
