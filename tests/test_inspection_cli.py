"""Command validation and process-facing failure semantics; no ROS or model."""
import contextlib
import io
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from robot_agent import inspection_cli as cli


class InspectionCommandTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name)/'new'
        self.args = ['--endpoint', '/prepared/nav.sock', '--output', str(self.output),
                     '--marker-reader', 'located-bright-panel']
        self.session = object()
        self.session_type = patch.dict(sys.modules, robot_harness=SimpleNamespace(
            NavigationSession=lambda endpoint: self.session))
        self.session_type.start()
        self.addCleanup(self.session_type.stop)
        self.before = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
        self.addCleanup(self.check_handlers)

    def check_handlers(self):
        for sig, previous in self.before.items():
            self.assertIs(signal.getsignal(sig), previous)

    def invoke(self, result, effect=None):
        with patch.object(cli, 'run_inspection', side_effect=effect, return_value=result) as run:
            with contextlib.redirect_stdout(io.StringIO()):
                code = cli.main(self.args)
        return code, json.loads((self.output/'report.json').read_text()), run

    def test_completed_report_uses_original_loop_and_explicit_reader(self):
        code, report, run = self.invoke(dict(status='completed', runtime_error=None,
            coordination=dict(resources_closed=True), native_cleanup='unknown', task_verdict='unassessed'))
        self.assertEqual(code, 0)
        factory = run.call_args.args[0]
        self.assertIs(factory(), self.session)
        options = run.call_args.kwargs
        self.assertIs(options['camera_factory'], cli.RosCamera)
        self.assertIs(options['interpreter'], cli.read_bright_marker)
        self.assertFalse(options['stop_requested']())
        self.assertNotIn('budget', options)
        self.assertNotIn('decision_factory', options)
        self.assertEqual(report['application']['decision_provider'], 'rules-no-model')
        self.assertEqual(report['native_cleanup'], 'unknown')
        self.assertEqual(report['task_verdict'], 'unassessed')

    def test_help_cancel_or_unclean_close_cannot_return_success(self):
        for status, closed, error in (('needs_help', True, None), ('cancelled', True, None),
                                      ('completed', False, None), ('completed', True, 'close failed')):
            with self.subTest(status=status, closed=closed, error=error):
                self.output = self.output.parent/f'{status}-{closed}-{bool(error)}'
                self.args[self.args.index('--output')+1] = str(self.output)
                code, report, _ = self.invoke(dict(status=status, runtime_error=error,
                    coordination=dict(resources_closed=closed), task_verdict='unassessed', native_cleanup='unknown'))
                self.assertEqual(code, 1)
                self.assertEqual(report['status'], status)

    def test_signal_requests_existing_stop_without_interrupting_resource_owner(self):
        def run(factory, **options):
            self.assertFalse(options['stop_requested']())
            signal.raise_signal(signal.SIGINT)
            self.assertTrue(options['stop_requested']())
            return dict(status='cancelled', runtime_error=None, coordination=dict(resources_closed=True))
        code, report, _ = self.invoke(None, run)
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'cancelled')

    def test_unexpected_loop_failure_records_unknown_closure_and_nonzero_exit(self):
        code, report, _ = self.invoke(None, RuntimeError('controlled loop failure'))
        self.assertEqual(code, 1)
        self.assertIn('controlled loop failure', report['runtime_error'])
        self.assertFalse(report['coordination']['resources_closed'])
        self.assertEqual(report['task_verdict'], 'unassessed')

    def test_invalid_arguments_and_model_selection_create_no_output_or_task(self):
        invalid = [self.args[:-2], self.args[:-1]+['unknown'], self.args+['--model', 'not-supported'],
                   ['--endpoint', ' ', *self.args[2:]]]
        for arguments in invalid:
            with self.subTest(arguments=arguments), patch.object(cli, 'run_inspection') as run:
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exit:
                    cli.main(arguments)
                self.assertEqual(exit.exception.code, 2)
                run.assert_not_called()
                self.assertFalse(self.output.exists())

    def test_help_does_not_load_harness_ros_or_model_frameworks(self):
        source = str(Path(__file__).resolve().parents[1]/'src')
        code = f"""
import importlib.abc, sys
sys.path.insert(0, {source!r})
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('robot_harness', 'rclpy', 'torch', 'transformers'):
            raise AssertionError('unexpected help dependency: '+fullname)
sys.meta_path.insert(0, Block())
from robot_agent.inspection_cli import main
main(['--help'])
"""
        result = subprocess.run([sys.executable, '-c', code], cwd=self.output.parent,
            capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--marker-reader', result.stdout)
        self.assertFalse(self.output.exists())

    def test_existing_output_is_not_overwritten(self):
        self.output.mkdir(); original = self.output/'report.json'
        original.write_text('keep original')
        with patch.object(cli, 'run_inspection') as run, self.assertRaises(FileExistsError):
            cli.main(self.args)
        run.assert_not_called()
        self.assertEqual(original.read_text(), 'keep original')

    def test_report_failure_still_restores_signal_handlers(self):
        with patch.object(cli, 'run_inspection', return_value=dict(status='completed',
                runtime_error=None, coordination=dict(resources_closed=True))):
            with patch.object(Path, 'write_text', side_effect=OSError('disk failure')):
                with self.assertRaisesRegex(OSError, 'disk failure'):
                    cli.main(self.args)
        self.check_handlers()


if __name__ == '__main__':
    unittest.main()
