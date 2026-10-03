"""Actual text-only CLI child and rejected tool/late proposal boundaries."""
import json
import os
import sys
from pathlib import Path
import tempfile
import time
import unittest

from robot_agent.navigation_decision import NavigationCodexDecision


class NavigationDecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.executable = self.root / 'proposal-cli'
        self.executable.write_text(f'#!{sys.executable}\n' + '''import json,sys,time
from pathlib import Path
if '--version' in sys.argv:
 print('navigation-process-fixture');raise SystemExit(0)
inputs=json.loads(sys.stdin.read().splitlines()[-1])
if '--image' in sys.argv: raise SystemExit(3)
output=Path(sys.argv[sys.argv.index('--output-last-message')+1])
(output.parent/'arguments.json').write_text(json.dumps(sys.argv))
if '--model' in sys.argv and sys.argv[sys.argv.index('--model')+1]=='slow-fixture':time.sleep(.4)
answer={k:inputs[k] for k in ('task_id','phase','observation_reference')}
answer.update(action=inputs['allowed_actions'][0],reason='controlled text proposal')
output.write_text(json.dumps(answer))
kind='command_execution' if sys.argv[sys.argv.index('--model')+1]=='tool-fixture' else 'agent_message'
print(json.dumps({'item':{'type':kind}}))
''')
        self.executable.chmod(0o755)
        self.context = {'task_id': 'fixture', 'phase': 'prepare',
            'observation_reference': {'session_id': 's', 'observation_id': 'o', 'epoch': 0,
                                      'map_id': 'turtlebot3-world-v1', 'frame': 'map'},
            'registered_sites': {'A': [.7, -.5, 0], 'B': [-1.5, -.5, 0]},
            'allowed_actions': ['visit_a', 'help'], 'goal': 'visit A then B'}

    def backend(self, model='process-fixture'):
        return NavigationCodexDecision(self.root / 'decisions', model=model, executable=str(self.executable))

    def reaped(self):
        record = json.loads((self.root / 'decisions/decision-1/process.json').read_text())
        self.assertTrue(record['reaped'])
        with self.assertRaises(ProcessLookupError):
            os.kill(record['pid'], 0)

    def test_hanging_version_probe_times_out_and_reaps_actual_child(self):
        hanging = self.root / 'version-hangs'
        pid_path = self.root / 'version.pid'
        hanging.write_text(f"#!{sys.executable}\nimport os,time\nfrom pathlib import Path\n" +
                           f"Path({str(pid_path)!r}).write_text(str(os.getpid()))\nwhile True: time.sleep(.01)\n")
        hanging.chmod(0o755)
        import subprocess
        with self.assertRaises(subprocess.TimeoutExpired):
            NavigationCodexDecision(self.root / 'version-output', model='fixture', executable=str(hanging))
        with self.assertRaises(ProcessLookupError):
            os.kill(int(pid_path.read_text()), 0)

    def test_text_proposal_preserves_nested_reference_without_image_or_tools(self):
        answer = self.backend().decide(self.context, {'pose': [-2., -.5]}, time.monotonic()+5, lambda: False)
        self.assertEqual(answer['observation_reference'], self.context['observation_reference'])
        self.assertEqual(answer['action'], 'visit_a')
        arguments = json.loads((self.root / 'decisions/decision-1/arguments.json').read_text())
        self.assertIn('--strict-config', arguments)
        self.assertNotIn('--image', arguments)
        self.reaped()

    def test_tool_event_is_rejected_after_actual_child_exit(self):
        with self.assertRaisesRegex(RuntimeError, 'attempted tools'):
            self.backend('tool-fixture').decide(self.context, {}, time.monotonic()+5, lambda: False)
        self.reaped()

    def test_running_text_proposal_timeout_reaps_child(self):
        with self.assertRaises(TimeoutError):
            self.backend('slow-fixture').decide(self.context, {}, time.monotonic()+.2, lambda: False)
        self.reaped()


if __name__ == '__main__':
    unittest.main()
