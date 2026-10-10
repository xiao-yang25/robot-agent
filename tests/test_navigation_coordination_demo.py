"""Explicit tutorial assembly and ordered stop; no ROS or physical verdict."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from robot_agent.navigation_coordination_demo import _RecordedSession, _run_tutorial
from robot_agent.navigation_coordination_demo import main
from test_navigation_runtime import OwnedSession
from test_navigation import Backend

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('coordination_selector', ROOT / 'examples/navigation/run.py')
selector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selector)


class CoordinationDemoTests(unittest.TestCase):
    def test_host_provider_uses_owned_backend_and_original_task(self):
        sessions, providers = [], []
        def session_factory():
            session = OwnedSession()
            sessions.append(session)
            return session
        def backend_factory(*args, **kwargs):
            providers.append(threading.get_ident())
            self.assertEqual(kwargs, dict(model='explicit-model', executable='relay'))
            return Backend()
        with tempfile.TemporaryDirectory() as temporary, \
                patch('robot_agent.navigation_decision.NavigationCodexDecision', side_effect=backend_factory):
            report = _run_tutorial(session_factory, output=Path(temporary)/'run', scenario='normal',
                provider='host-codex', model='explicit-model', executable='relay')
        self.assertEqual(report['status'], 'completed')
        self.assertEqual([row['site'] for row in report['operations']], ['A', 'B'])
        self.assertTrue(report['coordination']['resources_closed'])
        self.assertNotEqual(providers[0], sessions[0].owner)
        self.assertNotEqual(providers[0], threading.get_ident())
        self.assertEqual(report['tutorial']['proposal'], 'host-codex')

    def test_host_stop_scenario_or_missing_model_creates_no_resource(self):
        cases = [dict(provider='host-codex', model='explicit', executable='relay', scenario='final-decision-stop'),
                 dict(provider='host-codex', executable='relay', scenario='normal'),
                 dict(provider='unsupported', scenario='normal')]
        with tempfile.TemporaryDirectory() as temporary:
            for arguments in cases:
                with self.subTest(arguments=arguments), patch('robot_agent.navigation_coordination_demo.run_navigation') as run:
                    with self.assertRaises(ValueError):
                        _run_tutorial(lambda: None, output=Path(temporary)/'run', **arguments)
                    run.assert_not_called()
                    self.assertFalse((Path(temporary)/'run').exists())

    def test_installed_entry_rejects_cleanup_call_or_late_answer_error(self):
        import robot_agent
        harness = SimpleNamespace(__file__='/installed/robot_harness/__init__.py', NavigationSession=None)
        reports = [dict(status='cancelled', coordination=dict(resources_closed=True,
                            late_completions=[]), cancel_error='record unavailable'),
                   dict(status='cancelled', coordination=dict(resources_closed=True,
                            late_completions=[dict(error='record unavailable')]))]
        with patch.object(robot_agent, '__file__', '/client-prefix/robot_agent/__init__.py'), \
                patch.dict(sys.modules, robot_harness=harness), patch('sys.argv', ['client', '/endpoint']):
            for report in reports:
                with self.subTest(report=report), patch('robot_agent.navigation_coordination_demo._run_tutorial', return_value=report):
                    self.assertEqual(main(scenario='final-decision-stop'), 1)

    def test_recording_failure_cannot_abandon_session_or_cleanup(self):
        class FailedTrace:
            def __init__(self, event):
                self.failed_event = event
            def event(self, event, **fields):
                if event == self.failed_event:
                    raise OSError('record unavailable')
        for failed_event in ('session_ready', 'close_requested', 'cancel'):
            with self.subTest(event=failed_event):
                session, closed = OwnedSession(), threading.Event()
                trace = FailedTrace(failed_event)
                with self.assertRaisesRegex(OSError, 'record unavailable'):
                    wrapper = _RecordedSession(session, trace, closed)
                    if failed_event == 'cancel':
                        try:
                            wrapper.cancel('original-request')
                        finally:
                            wrapper.close()
                    else:
                        wrapper.close()
                self.assertTrue(session.closed)
                self.assertTrue(closed.is_set())
                if failed_event == 'cancel':
                    self.assertEqual(session.cancellations, ['original-request'])

    def exercise(self, scenario, *, close_error=False):
        sessions = []
        def factory():
            session = OwnedSession()
            if close_error:
                def fail():
                    session.record()
                    raise OSError('close unavailable before disposal')
                session.close = fail
            sessions.append(session)
            return session
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'agent'
            report = _run_tutorial(factory, output=output, scenario=scenario)
            self.assertEqual(json.loads((output / 'report.json').read_text()), report)
            events = [json.loads(line) for line in (output / 'coordination.jsonl').read_text().splitlines()]
        self.assertEqual(len(sessions), 1)
        return report, events, sessions[0]

    def test_normal_uses_existing_task_and_retains_domain_limits(self):
        report, events, session = self.exercise('normal')
        self.assertEqual(report['status'], 'completed')
        self.assertEqual([op['site'] for op in report['operations']], ['A', 'B'])
        self.assertEqual(report['operations'][-1]['receipt']['settlement'], 'pending')
        self.assertEqual(report['task_verdict'], 'unassessed')
        self.assertEqual(report['native_cleanup'], 'unknown')
        self.assertTrue(report['coordination']['resources_closed'])
        self.assertTrue(session.closed)
        io = {e['thread'] for e in events if e['event'] in ('session_ready', 'submit', 'close_return')}
        decisions = {e['thread'] for e in events if e['event'] == 'decision_begin'}
        self.assertEqual(len(io), 1)
        self.assertEqual(len(decisions), 1)
        self.assertNotEqual(io, decisions)

    def test_stop_closes_before_releasing_and_retains_late_decision(self):
        report, events, session = self.exercise('final-decision-stop')
        self.assertEqual(report['status'], 'cancelled')
        self.assertTrue(report['coordination']['resources_closed'])
        self.assertEqual(session.cancellations, [session.submissions[-1][0]])
        positions = {name: next(e['sequence'] for e in events if e['event'] == name)
                     for name in ('task_stop', 'cancel', 'close_requested', 'close_return', 'blocked_decision_released')}
        self.assertEqual(list(positions.values()), sorted(positions.values()))
        self.assertFalse(any(e['sequence'] > positions['task_stop'] for e in events if e['event'] == 'submit'))
        self.assertEqual([d['context']['phase'] for d in report['decisions']], ['prepare', 'after_a'])
        returned = next(e['answer'] for e in events if e['event'] == 'decision_return' and e['answer']['phase'] == 'final')
        late = [e for e in report['coordination']['late_completions'] if e['role'] == 'decision']
        self.assertEqual(len(late), 1)
        self.assertEqual(late[0]['value'], returned)
        self.assertEqual(report['task_verdict'], 'unassessed')

    def test_close_failure_is_unknown_and_not_resource_success(self):
        report, events, session = self.exercise('final-decision-stop', close_error=True)
        self.assertEqual(report['connection_close'], 'unknown')
        self.assertFalse(report['coordination']['resources_closed'])
        self.assertFalse(session.closed)
        self.assertIn('close unavailable', report['close_error'])
        self.assertFalse(any(e['event'] == 'close_return' for e in events))
        self.assertTrue(any(e['event'] == 'blocked_decision_released' for e in events))

    def test_invalid_scenario_creates_no_output_or_session(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'new'
            with patch('robot_agent.navigation_coordination_demo.run_navigation') as run:
                with self.assertRaises(ValueError):
                    _run_tutorial(lambda: None, output=output, scenario='other')
                run.assert_not_called()
            self.assertFalse(output.exists())

    def arguments(self, root, *extra):
        for directory in ('harness', 'core', 'agent/bin', 'agent/robot_agent'):
            (root / directory).mkdir(parents=True, exist_ok=True)
        for name in ('robot_agent/navigation_demo_client.py', 'robot_agent/navigation_coordination_demo.py',
                     'bin/robot-agent-navigation-controlled', 'bin/robot-agent-navigation-host-proposal'):
            (root / 'agent' / name).touch()
        return ['run.py', '--harness-source', str(root / 'harness'), '--python-prefix', str(root / 'core'),
                '--agent-prefix', str(root / 'agent'), '--image', 'test-image', '--output', str(root / 'new'), *extra]

    def test_selector_binds_scenario_budget_and_new_installed_client(self):
        for scenario in ('normal', 'final-decision-stop'):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                args = self.arguments(Path(temporary), '--assembly', 'experimental-coordination',
                    '--coordination-scenario', scenario, '--terminal-query-seconds', '8', '--record-evaluation')
                revision = re.search(r'version: ([0-9a-f]{40})', (ROOT / 'workspace.repos').read_text()).group(1)
                with patch('sys.argv', args), patch.object(selector.subprocess, 'check_output', return_value=revision), \
                        patch.object(selector.subprocess, 'run'), patch.object(selector.os, 'execv') as legacy, \
                        patch('robot_agent._navigation_demo.run_controlled_client', return_value=0) as launch:
                    self.assertEqual(selector.main(), 0)
                command, source = launch.call_args.args
                self.assertEqual(command[command.index('--terminal-query-seconds') + 1], '8.0')
                self.assertIn('--record-evaluation', command)
                self.assertIn('robot_agent.navigation_coordination_demo', source)
                self.assertIn(f'scenario={scenario!r}', source)
                legacy.assert_not_called()

    def test_host_selector_retains_query_budget_and_uses_host_supervisor(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            args = self.arguments(root, '--assembly', 'experimental-coordination',
                '--coordination-scenario', 'normal', '--terminal-query-seconds', '8',
                '--provider', 'host-codex', '--model', 'explicit', '--host-output', str(root/'private'))
            revision = re.search(r'version: ([0-9a-f]{40})', (ROOT/'workspace.repos').read_text()).group(1)
            with patch('sys.argv', args), patch.object(selector.subprocess, 'check_output', return_value=revision), \
                    patch.object(selector.subprocess, 'run'), patch('robot_agent._navigation_demo.run_host', return_value=0) as host, \
                    patch('robot_agent._navigation_demo.run_controlled_client') as controlled:
                self.assertEqual(selector.main(), 0)
            command = host.call_args.args[0]
            self.assertEqual(command[command.index('--terminal-query-seconds')+1], '8.0')
            self.assertTrue(host.call_args.kwargs['coordination'])
            self.assertEqual(host.call_args.kwargs['model'], 'explicit')
            controlled.assert_not_called()

    def test_invalid_combinations_fail_before_dependencies_or_processes(self):
        selected = ['--assembly', 'experimental-coordination', '--coordination-scenario', 'normal',
                    '--terminal-query-seconds', '8']
        cases = [selected + ['--terminal-query-seconds=' + value] for value in ('0', '-1', 'nan', 'inf', '10.01')]
        cases += [selected + ['--task', 'revision'], selected + ['--provider', 'host-codex'],
                  selected + ['--provider', 'host-codex', '--model', 'explicit', '--host-output', 'private',
                              '--coordination-scenario', 'final-decision-stop'],
                  ['--assembly', 'experimental-coordination'], ['--terminal-query-seconds', '8']]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for extra in cases:
                with self.subTest(extra=extra), patch('sys.argv', self.arguments(root, *extra)), \
                        patch.object(selector.subprocess, 'check_output') as git, \
                        patch.object(selector.subprocess, 'Popen') as process, \
                        contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as caught:
                        selector.main()
                    self.assertEqual(caught.exception.code, 2)
                    git.assert_not_called()
                    process.assert_not_called()
                    self.assertFalse((root / 'new').exists())
