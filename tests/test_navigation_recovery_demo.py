"""Explicit recovery scene selection and owned trusted-client lifecycle."""
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

from robot_agent._navigation_demo import run_controlled_recovery

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('navigation_tutorial',ROOT/'examples/navigation/run.py')
selector=importlib.util.module_from_spec(spec);spec.loader.exec_module(selector)
MAP='turtlebot3-occupied-a-probe-v1'


class RecoveryDemoTests(unittest.TestCase):
    def arguments(self, root, *extra):
        for directory in ('harness','core','agent/bin','agent/robot_agent'):
            (root/directory).mkdir(parents=True,exist_ok=True)
        for filename in ('robot_agent/navigation_demo_client.py','bin/robot-agent-navigation-controlled','bin/robot-agent-navigation-host-proposal'):
            (root/'agent'/filename).touch()
        return ['run.py','--harness-source',str(root/'harness'),'--python-prefix',str(root/'core'),
                '--agent-prefix',str(root/'agent'),'--image','test-image','--output',str(root/'scene'),*extra]

    def test_recovery_scene_reaches_controlled_and_host_with_matching_identity(self):
        for scene,map_id in (('normal','turtlebot3-world-v1'),('occupied-a',MAP)):
            for provider in ('controlled','host-codex'):
                with self.subTest(scene=scene,provider=provider),tempfile.TemporaryDirectory() as temporary:
                    root=Path(temporary)
                    args=self.arguments(root,'--task','recovery','--scene',scene,'--provider',provider)
                    if provider=='host-codex':args+=['--model','explicit-model','--host-output',str(root/'private')]
                    revision=re.search(r'version: ([0-9a-f]{40})',(ROOT/'workspace.repos').read_text()).group(1)
                    with patch('sys.argv',args),patch.object(selector.subprocess,'check_output',return_value=revision+'\n'),patch.object(selector.subprocess,'run'),patch('robot_agent._navigation_demo.run_controlled_recovery',return_value=0) as controlled,patch('robot_agent._navigation_demo.run_host',return_value=0) as host,patch.object(selector.os,'execv') as replace:
                        self.assertEqual(selector.main(),0)
                    called=host if provider=='host-codex' else controlled
                    command=called.call_args.args[0]
                    self.assertEqual(command[command.index('--scene')+1],scene)
                    self.assertEqual(command[command.index('--profile')+1],'scoped-two-context-nav2-failure-recovery-v1')
                    if provider=='host-codex':self.assertEqual(host.call_args.kwargs['recovery'],dict(expected_map_id=map_id))
                    else:self.assertEqual(controlled.call_args.args[1],map_id)
                    replace.assert_not_called()

    def test_occupied_scene_or_instruction_conflicts_fail_before_source_or_process_access(self):
        for extra in (('--task','fixed','--scene','occupied-a'),('--task','recovery','--instruction','stop')):
            with self.subTest(extra=extra),tempfile.TemporaryDirectory() as temporary:
                args=self.arguments(Path(temporary),*extra)
                with patch('sys.argv',args),patch.object(selector.subprocess,'check_output') as git,patch.object(selector.subprocess,'Popen') as launch:
                    with self.assertRaises(SystemExit) as caught:selector.main()
                    self.assertEqual(caught.exception.code,2);git.assert_not_called();launch.assert_not_called()

    def test_controlled_recovery_keeps_exact_bind_until_owned_launcher_finishes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);script=root/'launch.py';record=root/'client.json'
            script.write_text('import json,sys\nfrom pathlib import Path\n'
                'client=Path(sys.argv[sys.argv.index("--client-script")+1])\n'
                f'Path({str(record)!r}).write_text(json.dumps(dict(path=str(client),source=client.read_text())))\n')
            self.assertEqual(run_controlled_recovery([sys.executable,str(script),'--client-script','unused'],MAP),0)
            result=json.loads(record.read_text())
            self.assertIn('main(task="recovery"',result['source']);self.assertIn(MAP,result['source'])
            self.assertFalse(Path(result['path']).exists())

    def test_unknown_map_starts_no_owned_process(self):
        with patch('robot_agent._navigation_demo.subprocess.Popen') as launch:
            with self.assertRaises(ValueError):run_controlled_recovery(['unused'],'foreign-map')
            launch.assert_not_called()


if __name__=='__main__':unittest.main()
