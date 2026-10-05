"""Single nonblocking tutorial slot and owned supervisor; no model/physics."""
from pathlib import Path
import sys
import tempfile
import time
import unittest

from robot_agent.navigation_revision_demo import TutorialPoll
from robot_agent._navigation_demo import run_controlled_checkpoint


class RevisionDemoTests(unittest.TestCase):
    def test_poll_returns_none_without_wait_and_delivers_bound_command_only_once(self):
        context = dict(task_id='task',revision_id='revision',request_id='request',operation_id=1,
                       goal_id='a'*32, session_id='s',epoch=0,map_id='m',frame='map')
        with tempfile.TemporaryDirectory() as temporary:
            provider = TutorialPoll('redirect_b', 9, temporary)
            deadline = time.monotonic()+10
            self.assertIsNone(provider.poll(context, deadline, lambda:False))
            provider.available_at = time.monotonic()-1
            self.assertEqual(provider.poll(context,deadline,lambda:False),dict(context,action='redirect_b'))
            self.assertIsNone(provider.poll(context,deadline,lambda:False))
            with self.assertRaises(ValueError): provider.poll({**context,'revision_id':'other'},deadline,lambda:False)
            with self.assertRaises(InterruptedError): provider.poll(context,deadline,lambda:True)
            self.assertIsNone(TutorialPoll('none',0,temporary).poll(context,deadline,lambda:False))
            self.assertIsNone(TutorialPoll('stop',0,temporary).poll(context,time.monotonic()-1,lambda:False))

    def test_invalid_tutorial_configuration_has_no_side_effects(self):
        for action,delay in (('visit_c',0),('stop',True),('stop',float('nan')),('redirect_b',10)):
            with self.subTest(action=action), self.assertRaises(ValueError): TutorialPoll(action,delay,'unused')

    def test_revision_supervisor_selects_installed_entry_and_removes_owned_stub(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); script=root/'launch.py'; output=root/'client.txt'
            script.write_text('import sys\nfrom pathlib import Path\n'
                'client=Path(sys.argv[sys.argv.index("--client-script")+1])\n'
                f'Path({str(output)!r}).write_text(str(client)+"\\n"+client.read_text())\n')
            code=run_controlled_checkpoint([sys.executable,str(script),'--client-script','unused'],
                dict(instruction='stop',delay=0),revision=True)
            self.assertEqual(code,0)
            filename,source=output.read_text().split('\n',1)
            self.assertIn('navigation_revision_demo import main',source)
            self.assertIn("instruction='stop'",source)
            self.assertFalse(Path(filename).exists())


if __name__ == '__main__': unittest.main()
