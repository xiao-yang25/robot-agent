"""Installed host/relay/CLI/Core composition; controlled subprocess, no model/physics."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import robot_agent.navigation_host_model
from robot_agent._navigation_demo import finish


class InstalledNavigationHostTests(unittest.TestCase):
    def run_case(self, model, tool_error=False, checkpoint=None, revision=None, recovery=None,
                 coordination=False, stop_final=False):
        prefix = Path(os.environ['COMBINATION_AGENT_PREFIX']).resolve()
        self.assertTrue(Path(robot_agent.navigation_host_model.__file__).resolve().is_relative_to(prefix))
        self.assertTrue((prefix/'bin/robot-agent-navigation-host-proposal').is_file())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scene, private = root/'scene', root/'private'
            scene.mkdir(); private.mkdir()
            endpoint, audit = root/'nav.sock', root/'audit.json'
            relay = root/'relay'
            relay.write_text(f'#!{sys.executable}\nfrom pathlib import Path\n'
                'from robot_agent.navigation_host_proposal import main\n'
                f'raise SystemExit(main(exchange=Path({str(scene)!r})))\n')
            relay.chmod(0o755)
            executable = prefix/'bin/robot-agent-navigation-controlled'
            if tool_error:
                executable = root/'proposal'
                source = Path(__file__).with_name('navigation_proposal_fixture.py').read_text()
                executable.write_text(f'#!{sys.executable}\n'+source.split('\n', 1)[1])
                executable.chmod(0o755)
            if stop_final:
                executable = root/'waiting-proposal'
                executable.write_text(f'#!{sys.executable}\n'+'''import json,os,sys,time
from pathlib import Path
if '--version' in sys.argv: print('waiting-final-fixture-no-model');raise SystemExit(0)
value=json.loads(sys.stdin.read().splitlines()[-1])
out=Path(sys.argv[sys.argv.index('--output-last-message')+1])
if value['phase']=='final':
    (out.parent/'waiting.json').write_text(json.dumps({'pid':os.getpid()}))
    time.sleep(30)
answer={key:value[key] for key in ('task_id','phase','observation_reference')}
answer.update(action={'prepare':'visit_a','after_a':'visit_b','final':'observed_complete'}[value['phase']],reason='controlled fixture')
out.write_text(json.dumps(answer))
print(json.dumps({'item':{'type':'agent_message'}}))
''')
                executable.chmod(0o755)
            processes = []
            with (root/'host.log').open('w+') as host_log, (root/'owner.log').open('w+') as owner_log, (root/'agent.log').open('w+') as agent_log:
                try:
                    host_command = [sys.executable, '-m', 'robot_agent.navigation_host_model',
                        '--exchange', str(scene), '--output', str(private), '--model', model,
                        '--executable', str(executable)]
                    if recovery is not None:
                        host_command.extend(['--task','recovery'])
                    elif revision is not None:
                        host_command.extend(['--task','revision'])
                    elif checkpoint is not None:
                        host_command.extend(['--task','checkpoint'])
                    host = subprocess.Popen(host_command, stdout=host_log, stderr=subprocess.STDOUT,
                        start_new_session=True)
                    processes.append(host)
                    owner = subprocess.Popen([sys.executable, str(Path(__file__).with_name('navigation_owner.py')),
                        str(endpoint), str(audit), *(['--failure-normal' if recovery=='normal' else '--failure'] if recovery is not None else ['--revision'] if revision is not None else [])], stdout=owner_log, stderr=subprocess.STDOUT,
                        start_new_session=True)
                    processes.append(owner)
                    until = time.monotonic()+5
                    while (not endpoint.exists() or not (private/'ready.json').exists()) and time.monotonic()<until:
                        time.sleep(.01)
                    self.assertTrue(endpoint.exists()); self.assertTrue((private/'ready.json').exists())
                    client_command = [sys.executable, '-m', 'robot_agent.navigation_cli',
                        '--endpoint', str(endpoint), '--output', str(scene/'agent'),
                        '--model', model, '--executable', str(relay)]
                    if coordination:
                        code=('from pathlib import Path; import json; '
                            'from robot_harness import NavigationSession; '
                            'from robot_agent.navigation_coordination_demo import _run_tutorial; '
                            f'report=_run_tutorial(lambda:NavigationSession({str(endpoint)!r}), '
                            f'output=Path({str(scene/"agent")!r}),scenario="normal",provider="host-codex", '
                            f'model={model!r},executable={str(relay)!r}); '
                            'raise SystemExit(0 if report["status"]=="completed" and report["coordination"]["resources_closed"] else 1)')
                        client_command=[sys.executable,'-c',code]
                    if recovery is not None:
                        client_command.extend(['--task','recovery'])
                    if checkpoint is not None or revision is not None:
                        module = 'navigation_revision_demo' if revision is not None else 'navigation_checkpoint_demo'
                        instruction = revision if revision is not None else checkpoint
                        code=(f'from pathlib import Path;from robot_agent.{module} import run;'
                            'from robot_agent.navigation_decision import NavigationCodexDecision;'
                            f'backend=NavigationCodexDecision(Path({str(scene / "agent-proposals")!r}),model={model!r},executable={str(relay)!r});'
                            f'raise SystemExit(run({str(endpoint)!r},{str(scene / "agent")!r},instruction={instruction!r},delay=0,backend=backend))')
                        client_command=[sys.executable,'-c',code]
                    if stop_final:
                        import signal
                        client = subprocess.Popen(client_command, stdout=agent_log, stderr=subprocess.STDOUT,
                                                  start_new_session=True)
                        processes.append(client)
                        waiting = private/'decisions/decision-3/waiting.json'
                        until = time.monotonic()+10
                        while not waiting.exists() and client.poll() is None and time.monotonic()<until:
                            time.sleep(.01)
                        self.assertTrue(waiting.exists(), 'host proposal never entered final wait')
                        client.send_signal(signal.SIGINT)
                        returncode = client.wait(timeout=10)
                    else:
                        result = subprocess.run(client_command,
                            stdout=agent_log, stderr=subprocess.STDOUT, timeout=15)
                        returncode = result.returncode
                    agent_log.seek(0)
                    self.assertEqual(returncode, int(tool_error or stop_final), agent_log.read())
                    self.assertEqual(owner.wait(timeout=5), 0)
                    report = json.loads((scene/'agent/report.json').read_text())
                    facts = json.loads(audit.read_text())
                    self.assertEqual(report['task_verdict'], 'unassessed')
                    self.assertEqual(report['native_cleanup'], 'unknown')
                    if coordination:
                        self.assertTrue(report['coordination']['resources_closed'])
                        self.assertEqual(report['tutorial']['proposal'], 'host-codex')
                    if tool_error:
                        self.assertEqual(report['status'], 'needs_help')
                        self.assertIn('decision CLI exited 1', report['reason'])
                        reply = json.loads((scene/'model-requests/prepare/response.json').read_text())
                        self.assertIn('attempted tools', reply['error'])
                        events = [json.loads(line) for line in (private/'decisions/decision-1/events.jsonl').read_text().splitlines()]
                        self.assertTrue(any(row.get('item', {}).get('type') == 'command_execution' for row in events))
                        self.assertEqual(report['operations'], [])
                        self.assertEqual(facts['records'], [])
                        self.assertEqual(facts['stops'], [])
                    elif stop_final:
                        self.assertEqual(report['status'], 'cancelled')
                        b=report['operations'][-1]
                        self.assertEqual(facts['stops'], [b['request_id']])
                        self.assertEqual([row['site'] for row in facts['records']], ['A', 'B'])
                        self.assertEqual(report['interrupted_operation']['request_id'], b['request_id'])
                        self.assertEqual(report['connection_close'], 'local_closed')
                        self.assertFalse((scene/'model-requests/final/response.json').exists())
                        self.assertTrue((scene/'model-requests/final/cancelled').exists())
                    else:
                        self.assertEqual(report['status'], 'stopped_by_instruction' if revision == 'stop' else 'completed')
                        if checkpoint is not None:
                            self.assertTrue(report['checkpoint']['accepted'])
                            self.assertEqual(report['checkpoint']['instruction']['action'],checkpoint)
                            self.assertEqual(report['decisions'][1]['answer']['checkpoint_id'],report['checkpoint']['instruction']['checkpoint_id'])
                        if revision is not None:
                            self.assertEqual(report['completed_sites'], [] if revision == 'stop' else ['A'] if revision == 'none' else ['B'])
                            self.assertEqual(report['revision']['accepted'], revision != 'none')
                            if revision == 'redirect_b':
                                self.assertEqual(report['decisions'][1]['answer']['revision_id'],report['revision']['instruction']['revision_id'])
                        if recovery is not None:
                            self.assertEqual(report['completed_sites'],['A'] if recovery=='normal' else ['B'])
                            if recovery=='failure':
                                a = report['operations'][0]
                                self.assertEqual(a['receipt']['native_outcome'],'failed')
                                self.assertEqual(a['receipt']['output_non_delivery_reason'],'no_output')
                                self.assertEqual(report['decisions'][1]['answer']['goal_id'],a['goal_id'])
                                self.assertIn('A_released',facts['events'])
                            else:
                                self.assertNotIn('recovery',report)
                        finish_a = checkpoint == 'finish_at_a' or revision in ('none','stop') or recovery=='normal'
                        actions = ['visit_a'] if revision == 'stop' else ['visit_a','observed_complete'] if revision == 'none' else ['visit_a','finish_at_a'] if checkpoint == 'finish_at_a' else ['visit_a','visit_b','observed_complete']
                        if recovery == 'normal': actions = ['visit_a','observed_complete']
                        self.assertEqual([r['answer']['action'] for r in report['decisions']],
                                         actions)
                        self.assertEqual(facts['records'][0]['receipt']['settlement'], 'settled')
                        if finish_a:
                            self.assertEqual(len(facts['records']),1)
                            if revision == 'stop':
                                self.assertEqual(facts['stops'],[report['operations'][0]['request_id']])
                            else:
                                self.assertFalse(facts['stops'])
                                self.assertEqual(report['completed_sites'],['A'])
                        else:
                            self.assertEqual(facts['records'][1]['receipt']['settlement'], 'pending')
                    host.terminate()
                    self.assertEqual(host.wait(timeout=5), 0)
                    self.assertTrue(json.loads((private/'model-server.json').read_text())['stop_observed'])
                    for base in (scene/('agent-proposals' if checkpoint is not None or revision is not None else 'agent/decisions'), private/'decisions'):
                        paths = list(base.glob('*/process.json'))
                        self.assertEqual(len(paths), 1 if tool_error else 3 if stop_final else len(report['decisions']))
                        for path in paths:
                            child = json.loads(path.read_text())
                            self.assertTrue(child['reaped'])
                            with self.assertRaises(ProcessLookupError): os.kill(child['pid'], 0)
                finally:
                    for process in reversed(processes):
                        finish(process, 1)

    def test_installed_revision_host_relay_completes_a_without_redirect_proposal(self):
        self.run_case('controlled-tutorial-no-model', revision='none')

    def test_installed_recovery_cli_host_relay_completes_only_normal_a(self):
        self.run_case('controlled-tutorial-no-model',recovery='normal')

    def test_installed_recovery_cli_host_relay_echoes_failed_a_then_one_b(self):
        self.run_case('controlled-tutorial-no-model',recovery='failure')

    def test_installed_revision_host_relay_stops_without_a_second_model_call(self):
        self.run_case('controlled-tutorial-no-model', revision='stop')

    def test_installed_revision_host_relay_echoes_bound_revision_before_b(self):
        self.run_case('controlled-tutorial-no-model', revision='redirect_b')

    def test_installed_host_relay_completes_and_preserves_pending_settlement(self):
        self.run_case('controlled-tutorial-no-model')

    def test_installed_coordination_host_relay_completes_original_task(self):
        self.run_case('controlled-tutorial-no-model', coordination=True)

    def test_installed_coordination_host_tool_attempt_has_zero_admissions(self):
        self.run_case('error-before-a', tool_error=True, coordination=True)

    def test_installed_coordination_external_stop_reaps_waiting_host_child(self):
        self.run_case('controlled-fixture-no-model', coordination=True, stop_final=True)

    def test_host_tool_event_crosses_relay_as_error_with_zero_admissions(self):
        self.run_case('error-before-a', tool_error=True)

    def test_installed_checkpoint_host_relay_finishes_at_a_without_b(self):
        self.run_case('controlled-tutorial-no-model',checkpoint='finish_at_a')

    def test_installed_checkpoint_host_relay_continues_b_with_bound_instruction(self):
        self.run_case('controlled-tutorial-no-model',checkpoint='continue_b')


if __name__ == '__main__':
    unittest.main()
