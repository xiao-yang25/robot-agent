"""Installed shared runtime with actual Session/Host/Core; no physics or model."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

import robot_agent._handoff_runtime as runtime
import robot_harness.session
from robot_agent.handoff import HOLD, PROFILE, TRANSFER
from robot_harness import Session
from test_installed import Proposal


class InstalledHandoffRuntimeTests(unittest.TestCase):
    def setUp(self):
        for module, key in ((runtime, 'COMBINATION_AGENT_PREFIX'),
                            (robot_harness.session, 'COMBINATION_HARNESS_PREFIX')):
            self.assertTrue(Path(module.__file__).resolve().is_relative_to(Path(os.environ[key]).resolve()))
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.worker = Path(__file__).with_name('worker.py')

    def session_factory(self):
        return Session(mujoco={'profile': PROFILE, 'output': str(self.root / 'episodes'),
            'worker_script': str(self.worker), 'checkpoint': 'ci-no-policy', 'device': 'ci-no-physics'})

    def steps(self, output=None):
        return [json.loads(row) for row in
            ((self.root if output is None else output) / 'episodes/episode-0.jsonl').read_text().splitlines()
            if json.loads(row)['event'] == 'step']

    def assert_cleanup(self, report):
        self.assertEqual(report['cleanup'], 'confirmed', report)
        self.assertTrue(report['coordination']['resources_closed'])
        for key in ('host_pid', 'worker_pid'):
            self.assertGreater(report[key], 0)
            with self.assertRaises(ProcessLookupError):
                os.kill(report[key], 0)

    def test_shared_assembly_preserves_real_400_50_steps_and_release(self):
        proposal = Proposal()
        report = runtime.run_handoff(self.session_factory, lambda: proposal)
        self.assertEqual(report['status'], 'completed', report)
        self.assertEqual(report['task_verdict'], 'unassessed')
        self.assertEqual(proposal.seen, [(0, 0, 0), (0, 400, 144), (0, 450, 194)])
        self.assertEqual([row['skill'] for row in report['operations']], [TRANSFER, HOLD])
        self.assertEqual([row['steps'] for row in report['operations']], [400, 50])
        self.assertNotEqual(*[row['operation_id'] for row in report['operations']])
        for row in report['operations']:
            receipt = row['receipt']
            self.assertEqual(receipt['authority']['operation_id'], row['operation_id'])
            self.assertEqual(receipt['result_reference'], row['request_id'])
            self.assertEqual(receipt['settlement'], 'settled')
            self.assertEqual(receipt['authority_disposition'], 'released')
        steps = self.steps()
        self.assertEqual(len(steps), 450)
        self.assertEqual([row['action'] for row in steps[400:]], [[400.] * 14] * 50)
        self.assert_cleanup(report)

    def test_stale_after_transfer_proposal_has_zero_hold_effects(self):
        report = runtime.run_handoff(self.session_factory, lambda: Proposal('stale'))
        self.assertEqual(report['status'], 'needs_help', report)
        self.assertIn('different task/phase/observation', report['reason'])
        self.assertEqual(len(report['operations']), 1)
        self.assertEqual(len(self.steps()), 400)
        self.assert_cleanup(report)

    def test_actual_cli_sigterm_during_image_decision_has_zero_hold_and_reaps_children(self):
        executable = self.root / 'proposal'
        executable.write_text(f'#!{sys.executable}\n' + '''
import json, os, signal, sys, time
from pathlib import Path
if '--version' in sys.argv:
    print('controlled-aloha-runtime-proposal'); raise SystemExit(0)
inputs = json.loads(sys.stdin.read().splitlines()[-1])
image = Path(sys.argv[sys.argv.index('--image') + 1])
if not image.exists() or image.read_bytes()[:8] != b'\\x89PNG\\r\\n\\x1a\\n':
    raise RuntimeError('missing actual camera image')
if any(key in inputs['measurement'] for key in ('contacts', 'qpos', 'rgb')):
    raise RuntimeError('unexpected model measurement')
output = Path(sys.argv[sys.argv.index('--output-last-message') + 1])
if inputs['phase'] == 'after_transfer':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    (output.parent / 'blocked.json').write_text(json.dumps({'pid': os.getpid()}))
    time.sleep(45)
    raise RuntimeError('cancelled child was not reaped')
answer = {key: inputs[key] for key in ('task_id', 'phase', 'epoch', 'sequence')}
answer.update(action=inputs['allowed_actions'][0], reason='controlled proposal; no model')
output.write_text(json.dumps(answer))
print(json.dumps({'item': {'type': 'agent_message'}}))
''')
        executable.chmod(0o700)
        output = self.root / 'agent'
        with (self.root / 'agent.log').open('w+') as log:
            caller = subprocess.Popen([sys.executable, '-m', 'robot_agent._handoff_runtime',
                '--output', str(output), '--worker-script', str(self.worker),
                '--checkpoint', 'ci-no-policy', '--device', 'cpu',
                '--model', 'controlled-fixture', '--executable', str(executable)],
                stdout=log, stderr=subprocess.STDOUT)
            try:
                marker = output / 'decisions/decision-2/blocked.json'
                until = time.monotonic() + 10
                while not marker.exists() and caller.poll() is None and time.monotonic() < until:
                    time.sleep(.01)
                log.seek(0)
                self.assertTrue(marker.exists(), log.read())
                caller.send_signal(signal.SIGTERM)
                self.assertEqual(caller.wait(timeout=8), 1)
            finally:
                if caller.poll() is None:
                    caller.kill()
                caller.wait(timeout=5)
            report = json.loads((output / 'report.json').read_text())
        self.assertEqual(report['status'], 'cancelled', report)
        self.assertEqual(report['task_verdict'], 'unassessed')
        self.assertEqual([row['context']['phase'] for row in report['decisions']], ['prepare'])
        self.assertEqual([row['skill'] for row in report['operations']], [TRANSFER])
        self.assertEqual(len(self.steps(output)), 400)
        self.assert_cleanup(report)
        for path in (output / 'decisions').glob('*/process.json'):
            child = json.loads(path.read_text())
            self.assertTrue(child['reaped'])
            with self.assertRaises(ProcessLookupError):
                os.kill(child['pid'], 0)


if __name__ == '__main__':
    unittest.main()
