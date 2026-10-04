"""Tutorial business input and owned launcher lifecycle; no physics/model."""
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

from robot_agent.navigation_checkpoint_demo import TutorialInstruction
from robot_agent._navigation_demo import run_controlled_checkpoint


class CheckpointDemoTests(unittest.TestCase):
    def test_provider_emits_one_identity_bound_answer_and_checks_stop_and_deadline(self):
        with tempfile.TemporaryDirectory() as temporary:
            provider=TutorialInstruction('finish_at_a',0,temporary)
            context=dict(task_id='task',checkpoint_id='checkpoint',session_id='s',epoch=0,map_id='m',frame='map')
            answer=provider.request(context,time.monotonic()+1,lambda:False)
            self.assertEqual(answer,dict(context,action='finish_at_a'))
            rows=[json.loads(line) for line in (Path(temporary)/'instruction.jsonl').read_text().splitlines()]
            self.assertEqual([row['event'] for row in rows],['instruction_requested','instruction_returned'])
            with self.assertRaises(TimeoutError): provider.request(context,time.monotonic()-1,lambda:False)
            with self.assertRaises(InterruptedError): provider.request(context,time.monotonic()+1,lambda:True)

    def test_tutorial_refuses_unsupported_input_before_creating_provider_resources(self):
        for action,delay in (('visit_c',0),('continue_b',True),('continue_b',float('nan')),('finish_at_a',10)):
            with self.subTest(action=action,delay=delay),self.assertRaises(ValueError):
                TutorialInstruction(action,delay,'unused')

    def test_controlled_supervisor_keeps_exact_client_bind_and_reaps_finished_launcher(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);script=root/'launch.py';record=root/'record.json'
            script.write_text('import json,sys\nfrom pathlib import Path\n'
                'client=Path(sys.argv[sys.argv.index("--client-script")+1])\n'
                f'Path({str(record)!r}).write_text(json.dumps(dict(path=str(client),text=client.read_text())))\n')
            code=run_controlled_checkpoint([sys.executable,str(script),'--client-script','placeholder'],
                                          dict(instruction='finish_at_a',delay=0))
            self.assertEqual(code,0)
            value=json.loads(record.read_text())
            self.assertIn("instruction='finish_at_a'",value['text'])
            self.assertFalse(Path(value['path']).exists())


if __name__ == '__main__':
    unittest.main()
