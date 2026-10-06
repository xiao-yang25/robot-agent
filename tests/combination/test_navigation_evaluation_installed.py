"""Fresh installed offline CLI on synthetic records, no physics qualification."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from navigation_evaluation_fixture import make_run,write_run


class InstalledNavigationEvaluationTests(unittest.TestCase):
    def test_installed_stdlib_cli_three_verdicts_and_refused_overwrite(self):
        prefix=Path(os.environ['COMBINATION_AGENT_PREFIX']).resolve()
        import robot_agent.evaluate_navigation as evaluator
        self.assertTrue(Path(evaluator.__file__).resolve().is_relative_to(prefix))
        self.assertEqual(evaluator.load_profile()['id'],'normal-scoped-nav2-two-stop-arrival-v1')
        executable=prefix/'bin/robot-agent-evaluate-navigation'
        self.assertTrue(executable.is_file())
        for expected,code in (('succeeded',0),('failed',1),('unknown',2)):
            with self.subTest(verdict=expected),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);data=make_run(root)
                if expected=='failed':data['physical.jsonl'][2]['xyz_rpy'][0]=-1.
                if expected=='unknown':data['physical.jsonl'].pop()
                write_run(root,data)
                output=root/'evaluation.json'
                result=subprocess.run([sys.executable,'-S',str(executable),'--run',str(root),'--output',str(output)],
                    capture_output=True,text=True,timeout=5)
                self.assertEqual(result.returncode,code,result.stderr)
                value=json.loads(output.read_text())
                self.assertEqual(value['verdict'],expected)
                self.assertEqual(value['execution']['operations'][1]['owner_reported_settlement'],'pending')
                original=output.read_bytes()
                refused=subprocess.run([sys.executable,'-S',str(executable),'--run',str(root/'absent'),
                    '--output',str(output)],capture_output=True,text=True,timeout=5)
                self.assertEqual(refused.returncode,2)
                self.assertEqual(output.read_bytes(),original)


if __name__=='__main__':unittest.main()
