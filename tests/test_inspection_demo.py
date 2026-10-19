"""Thin selector contracts; no ROS, Docker, motion or model claims."""
import contextlib
import importlib.util
import io
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from robot_agent import inspection_demo_client as client

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('inspection_selector', ROOT/'examples/inspection/run.py')
selector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selector)
REVISION = re.search(r'version: ([0-9a-f]{40})', (ROOT/'workspace.repos').read_text()).group(1)


class InspectionDemoTests(unittest.TestCase):
    def arguments(self, root, *extra):
        files = ('agent/robot_agent/inspection_demo_client.py', 'agent/robot_agent/inspection_cli.py',
                 'agent/bin/robot-agent-inspection',
                 'core/lib/robot-harness/python/robot_harness_nav2/_inspection.py')
        (root/'harness').mkdir()
        for name in files:
            path=root/name; path.parent.mkdir(parents=True,exist_ok=True); path.touch()
        return ['run.py','--harness-source',str(root/'harness'),'--python-prefix',str(root/'core'),
                '--agent-prefix',str(root/'agent'),'--image','visual-image','--output',str(root/'new'),*extra]

    def test_both_scene_selections_exec_the_existing_launcher_with_installed_client(self):
        for case in ('normal','recheck'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary).resolve();args=self.arguments(root,'--case',case,'--record-evaluation')
                with patch('sys.argv',args), patch.object(selector.subprocess,'check_output',side_effect=[REVISION,'']) as git, \
                        patch.object(selector.os,'execv') as execute:
                    selector.main()
                self.assertEqual(git.call_args.args[0], ['git','-C',str(root/'harness'),'status','--porcelain','--untracked-files=normal'])
                executable, command=execute.call_args.args
                self.assertEqual(executable,sys.executable)
                self.assertEqual(command[:3],[sys.executable,str(root/'harness/integrations/ros2/simulation/simulate.py'),'session'])
                self.assertEqual(command[command.index('--inspection-case')+1],case)
                self.assertEqual(command[command.index('--client-script')+1],str(root/'agent/robot_agent/inspection_demo_client.py'))
                self.assertEqual(command[command.index('--caller-wait-seconds')+1],'45')
                self.assertIn('--record-evaluation',command)
                self.assertNotIn('--model',command)
                self.assertFalse((root/'new').exists())

    def test_unsupported_or_existing_output_rejects_before_git_or_process(self):
        for extra in ((),('--case','other'),('--case','normal','--model','model'),('--case','normal','--scene','occupied-a'),('--case','normal','--existing')):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary).resolve()
                if '--existing' in extra:
                    (root/'new').mkdir();extra=extra[:-1]
                args=self.arguments(root,*extra)
                with patch('sys.argv',args), contextlib.redirect_stderr(io.StringIO()), \
                        patch.object(selector.subprocess,'check_output') as git, patch.object(selector.os,'execv') as execute:
                    with self.assertRaises(SystemExit) as caught:selector.main()
                self.assertEqual(caught.exception.code,2);git.assert_not_called();execute.assert_not_called()

    def test_wrong_dirty_pin_or_old_installs_cannot_launch(self):
        for failure in ('pin','dirty','untracked','agent','core'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary).resolve();args=self.arguments(root,'--case','normal')
                if failure=='agent':(root/'agent/robot_agent/inspection_demo_client.py').unlink()
                if failure=='core':(root/'core/lib/robot-harness/python/robot_harness_nav2/_inspection.py').unlink()
                status = ' M changed.py' if failure=='dirty' else '?? extra.py' if failure=='untracked' else ''
                with patch('sys.argv',args), contextlib.redirect_stderr(io.StringIO()), \
                        patch.object(selector.subprocess,'check_output',side_effect=['0'*40 if failure=='pin' else REVISION,status]), patch.object(selector.os,'execv') as execute:
                    with self.assertRaises(SystemExit):selector.main()
                execute.assert_not_called();self.assertFalse((root/'new').exists())

    def test_installed_client_execs_original_cli_with_fixed_reader_and_no_fixture_input(self):
        modules = {'robot_agent':SimpleNamespace(__file__='/client-prefix/robot_agent/__init__.py'),
                   'robot_harness':SimpleNamespace(__file__='/installed/lib/robot-harness/python/robot_harness/__init__.py')}
        with patch.dict(sys.modules,modules), patch.object(client.os,'execv') as execute:
            client.main(['/prepared/navigation.sock'])
        execute.assert_called_once_with(sys.executable,[sys.executable,'-m','robot_agent.inspection_cli',
            '--endpoint','/prepared/navigation.sock','--output','/output/agent','--marker-reader','located-bright-panel'])

    def test_wrong_import_roots_reject_before_cli_exec(self):
        for bad in ('robot_agent','robot_harness'):
            modules={name:SimpleNamespace(__file__=path) for name,path in (
                ('robot_agent','/client-prefix/robot_agent/__init__.py'),
                ('robot_harness','/installed/lib/robot-harness/python/robot_harness/__init__.py'))}
            modules[bad].__file__='/source/'+bad+'/__init__.py'
            with self.subTest(bad=bad), patch.dict(sys.modules,modules),patch.object(client.os,'execv') as execute:
                with self.assertRaises(ValueError):client.main(['/prepared/navigation.sock'])
                execute.assert_not_called()



if __name__=='__main__':unittest.main()
