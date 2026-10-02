"""Installed Agent + actual Session/Host/Core, with no-physics environment/worker.

No Session or Host is replaced. Only external camera/action/recording and policy
providers are fixtures. This checks interfaces/settlement, not task success.
"""
import json
import os
from pathlib import Path
import tempfile
import unittest

import robot_agent.handoff
import robot_harness.session
from robot_agent.handoff import HandoffTask, HOLD, PROFILE, TRANSFER
from robot_harness import Session


class Proposal:
    def __init__(self, after_transfer='hold'):
        self.after_transfer = after_transfer
        self.seen = []

    def decide(self, context, observation, deadline, stop_requested):
        if 'contacts' in observation or 'qpos' in observation:
            raise AssertionError('evaluator truth reached task decisions')
        self.seen.append((context['epoch'], observation['sequence'], observation['rgb'][0]))
        answer = {key: context[key] for key in ('task_id', 'phase', 'epoch', 'sequence')}
        action = {'prepare': 'transfer', 'after_transfer': self.after_transfer,
                  'final': 'observed_success'}[context['phase']]
        answer.update(action=action, reason='CI-only controlled proposal')
        if self.after_transfer == 'stale' and context['phase'] == 'after_transfer':
            answer.update(sequence=0, action='hold')
        return answer


class InstalledCombinationTests(unittest.TestCase):
    def setUp(self):
        # The workflow supplies the exact new install roots. Fail rather than
        # quietly consuming repository source or an unrelated host installation.
        for module, variable in ((robot_agent.handoff, 'COMBINATION_AGENT_PREFIX'),
                                 (robot_harness.session, 'COMBINATION_HARNESS_PREFIX')):
            prefix = Path(os.environ[variable]).resolve()
            self.assertTrue(Path(module.__file__).resolve().is_relative_to(prefix), module.__file__)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.session = Session(mujoco={
            'profile': PROFILE, 'output': str(self.root / 'episodes'),
            'worker_script': str(Path(__file__).with_name('worker.py')),
            'checkpoint': 'ci-no-policy', 'device': 'ci-no-physics'})
        self.addCleanup(self.close_and_check)

    def close_and_check(self):
        pids = self.session.host_pid, self.session.worker_pid
        self.session.close()
        for pid in pids:
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def steps(self):
        return [json.loads(line) for line in
                (self.root / 'episodes/episode-0.jsonl').read_text().splitlines()
                if json.loads(line)['event'] == 'step']

    def test_normal_two_operations_real_settlement_and_installed_boundary(self):
        proposal = Proposal()
        report = HandoffTask(proposal).run(self.session)
        self.assertEqual(report['status'], 'completed', report)
        self.assertEqual(report['task_verdict'], 'unassessed')
        self.assertEqual(proposal.seen, [(0, 0, 0), (0, 400, 144), (0, 450, 194)])
        operations = report['operations']
        self.assertEqual([op['skill'] for op in operations], [TRANSFER, HOLD])
        self.assertNotEqual(operations[0]['operation_id'], operations[1]['operation_id'])
        for op in operations:
            receipt = op['receipt']
            self.assertEqual(receipt['authority']['operation_id'], op['operation_id'])
            self.assertEqual(receipt['result_reference'], op['request_id'])
            self.assertEqual(receipt['output'], 'accepted')
            self.assertEqual(receipt['settlement'], 'settled')
            self.assertEqual(receipt['authority_disposition'], 'released')
        rows = self.steps()
        self.assertEqual(len(rows), 450)
        self.assertEqual([row['action'] for row in rows[400:]], [[400.] * 14] * 50)
        self.assertEqual(self.session.observe()['stage'], 'needs_reset')

    def test_help_after_transfer_has_no_hold_effects(self):
        report = HandoffTask(Proposal('help')).run(self.session)
        self.assertEqual(report['status'], 'needs_help')
        self.assertEqual(len(report['operations']), 1)
        self.assertEqual(len(self.steps()), 400)

    def test_old_observation_answer_has_no_hold_effects(self):
        report = HandoffTask(Proposal('stale')).run(self.session)
        self.assertEqual(report['status'], 'needs_help')
        self.assertIn('different task/phase/observation', report['reason'])
        self.assertEqual(len(report['operations']), 1)
        self.assertEqual(len(self.steps()), 400)


if __name__ == '__main__':
    unittest.main()
