"""Installed checkpoint application / public Session / real Core, synthetic native edges."""
from copy import deepcopy
import json
import time
import unittest

from robot_agent import CheckpointNavigationTask
from robot_agent.navigation import NavigationBudget
import test_navigation_installed as installed


class Instruction:
    def __init__(self, action, callback=lambda context, answer: None):
        self.action, self.callback, self.count = action, callback, 0

    def request(self, context, deadline, stopped):
        self.count += 1
        if 'Session' in context or 'physical_truth' in context:
            raise AssertionError('undeclared authority/input reached business provider')
        answer = {key: context[key] for key in ('task_id','checkpoint_id','session_id','epoch','map_id','frame')}
        answer['action'] = self.action
        self.callback(context, answer)
        return answer


class Proposal(installed.Proposal):
    def __init__(self):
        super().__init__()
        self.contexts = []

    def decide(self, context, observation, deadline, stopped):
        self.contexts.append(deepcopy(context))
        answer = super().decide(context, observation, deadline, stopped)
        if 'checkpoint_instruction' in context:
            answer.update(action=context['allowed_actions'][0],
                          checkpoint_id=context['checkpoint_instruction']['checkpoint_id'])
        return answer


class InstalledCheckpointTests(unittest.TestCase):
    # Reuse only the existing owned process/socket fixture, not its test cases.
    setUp = installed.InstalledNavigationTests.setUp
    reap_owner = installed.InstalledNavigationTests.reap_owner

    def run_task(self, provider, **kwargs):
        proposal = Proposal()
        report = CheckpointNavigationTask(proposal, provider, **kwargs).run(self.session)
        self.assertEqual(provider.count, 1)
        self.assertEqual(report['task_verdict'], 'unassessed')
        self.assertEqual(report['native_cleanup'], 'unknown')
        closed = self.session.close()
        self.assertEqual(closed['closure'], 'unknown')
        self.assertFalse(closed['owner_reaped'])
        self.reap_owner()
        audit = json.loads(self.audit.read_text())
        self.assertEqual(audit['records'][0]['receipt']['authority_disposition'], 'released')
        return report, audit, proposal

    def test_finish_instruction_completes_only_a_and_caller_reaps_real_owner(self):
        report, audit, proposal = self.run_task(Instruction('finish_at_a'))
        self.assertEqual(report['status'], 'completed', report)
        self.assertEqual(report['completed_sites'], ['A'])
        self.assertEqual(report['execution_cleanup'], 'unknown')
        self.assertEqual(len(audit['records']), 1)
        self.assertFalse(audit['stops'])
        self.assertEqual([context['phase'] for context in proposal.contexts], ['prepare','after_a'])

    def test_continue_instruction_keeps_actual_b_pending_and_close_revokes_exact_b(self):
        report, audit, proposal = self.run_task(Instruction('continue_b'))
        self.assertEqual(report['status'], 'completed', report)
        self.assertEqual(report['completed_sites'], ['A','B'])
        a, b = report['operations']
        self.assertEqual(a['receipt']['settlement'], 'settled')
        self.assertEqual(b['receipt']['settlement'], 'pending')
        self.assertEqual(b['receipt']['authority_disposition'], 'current')
        self.assertEqual(audit['stops'], [b['request_id']])
        self.assertEqual(audit['records'][1]['receipt']['authority_disposition'], 'revoked')
        self.assertEqual(audit['records'][1]['receipt']['settlement'], 'pending')
        self.assertEqual(b['observation_reference'], report['decisions'][1]['revalidated_observation']['reference'])
        self.assertNotEqual(b['observation_reference'], proposal.references[1])
        self.assertEqual(b['receipt']['native_identity'], b['goal_id'])

    def test_foreign_instruction_never_creates_a_second_core_record(self):
        report, audit, proposal = self.run_task(Instruction('continue_b',
            lambda context, answer: answer.update(checkpoint_id='previous-task')))
        self.assertEqual(report['status'], 'needs_help', report)
        self.assertFalse(report['checkpoint']['accepted'])
        self.assertEqual(len(audit['records']), 1)
        self.assertFalse(audit['stops'])
        self.assertEqual(len(proposal.contexts), 1)

    def test_actual_slow_provider_respects_shorter_shared_budget_without_new_admission(self):
        provider = Instruction('continue_b', lambda *args: time.sleep(.3))
        report, audit, proposal = self.run_task(provider, budget=NavigationBudget(decision_seconds=.2))
        self.assertEqual(report['status'], 'needs_help', report)
        self.assertFalse(report['checkpoint']['accepted'])
        self.assertEqual(len(audit['records']), 1)
        self.assertFalse(audit['stops'])
        self.assertEqual(len(proposal.contexts), 1)


if __name__ == '__main__':
    unittest.main()
