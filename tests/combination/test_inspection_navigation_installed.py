"""Installed policy/binding with real Session/socket/Core, synthetic native/source facts."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from robot_agent import _inspection_navigation as binding_module
from robot_agent._inspection_navigation import Admission, InspectionNavigation
from robot_agent._inspection_policy import Conditions, Control, Proposal, WindowClosed, advance, new_task
from robot_agent._inspection_source import Frame, InspectionSource, SourceProfile, SITES
from robot_agent._task_runtime import Coordinator, Owner
from robot_harness import NavigationSession


class InstalledInspectionTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(binding_module.__file__).resolve().is_relative_to(
            Path(os.environ['COMBINATION_AGENT_PREFIX']).resolve()))
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.endpoint, self.audit = self.root/'nav.sock', self.root/'audit.json'
        self.log = (self.root/'owner.log').open('w+')
        self.addCleanup(self.log.close)
        self.owner = subprocess.Popen([sys.executable, str(Path(__file__).with_name('navigation_owner.py')),
            str(self.endpoint), str(self.audit)], stdout=self.log, stderr=subprocess.STDOUT)
        self.addCleanup(self.reap)
        until = time.monotonic()+5
        while not self.endpoint.exists() and self.owner.poll() is None and time.monotonic() < until:
            time.sleep(.01)
        self.assertTrue(self.endpoint.exists())
        self.logical = 0.
        self.source = InspectionSource(7, clock=lambda: self.logical,
                                       profile=SourceProfile(window_seconds=.6))
        self.source.health(7, 0.)

    def reap(self):
        try:
            code = self.owner.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.owner.kill(); self.owner.wait(timeout=5)
            self.fail('synthetic Core owner required forced termination')
        self.log.seek(0)
        self.assertEqual(code, 0, self.log.read())
        self.assertFalse(self.endpoint.exists())

    def closed_a_anomaly(self):
        self.source.open_window('A', 'indicator-A')
        for seq, stamp in enumerate((.1, .3, .5)):
            self.logical = stamp
            self.assertTrue(self.source.health(7, stamp))
            self.assertTrue(self.source.ingest(Frame(7, seq, 'A', 'indicator-A', stamp, stamp,
                SITES['A'], bytes(640*480*3))))
            read = self.source.borrow(self.source.events.take()[2].reference)
            try:
                self.assertTrue(self.source.record(read, 'abnormal'))
            finally:
                read.release()
        self.logical = .61; self.source.health(7, .61)
        return self.source.finish_window()

    def test_installed_policy_consumes_real_correlated_a_b_facts_with_pending_b(self):
        until = time.monotonic()+5
        shared = {}
        coordinator = Coordinator('inspection', lambda: False, 2.)
        def factory():
            shared['binding'] = InspectionNavigation(lambda: NavigationSession(self.endpoint),
                self.source, task_deadline=until)
            return shared['binding']
        owner = Owner(coordinator.exchange, 'io', factory, close=lambda b: b.close())
        owner.start()
        def call(method, *args):
            return coordinator.call('io', method, args, {}, deadline=until)
        try:
            prepared = call('prepare')
            state = new_task('inspection', started_at=time.monotonic())
            # Qualification caller supplies real adapter results, not arbitrary
            # arrival/settlement flags; source clock/classification remain synthetic.
            def step(event, applicable=False):
                nonlocal state
                transition = advance(state, event, Conditions(time.monotonic(), 7,
                    self.source.refresh(), True, True, applicable))
                state = transition.state
                return transition
            self.assertTrue(prepared['available'])
            start = step(Control('start'))
            a_intent = start.intents[0]
            shared['binding'].authorize(Admission(a_intent.request_id, 'A', 7,
                min(until, a_intent.deadline), min(until, a_intent.deadline)))
            step(call('submit', a_intent.request_id))
            while state.phase == 'navigation_a' and time.monotonic() < until:
                step(call('status', a_intent.request_id)); time.sleep(.01)
            self.assertEqual(state.phase, 'check_a')
            self.assertTrue(state.operations[0].reusable)
            record = self.closed_a_anomaly()
            step(WindowClosed(record), True)
            b_intent = step(Proposal(state.decision, 'visit_b', 'controlled rule'), True).intents[0]
            shared['binding'].authorize(Admission(b_intent.request_id, 'B', 7,
                min(until, b_intent.deadline), min(until, b_intent.deadline), record))
            step(call('submit', b_intent.request_id))
            while state.phase == 'navigation_b' and time.monotonic() < until:
                step(call('status', b_intent.request_id)); time.sleep(.01)
            self.assertEqual(state.phase, 'check_b')
            self.assertEqual(state.checks, (record,))
            self.assertFalse(state.operations[-1].reusable)
            self.assertEqual(shared['binding'].attempts[b_intent.request_id]['record']['receipt']['settlement'], 'pending')
        finally:
            stopped = owner.finish(time.monotonic()+2)
            self.assertTrue(stopped['thread_stopped'])
            self.assertEqual(stopped['close'], 'confirmed')
        self.reap()
        facts = json.loads(self.audit.read_text())
        self.assertEqual([row['site'] for row in facts['records']], ['A', 'B'])
        self.assertEqual(facts['stops'], [b_intent.request_id])

    def test_installed_camera_loss_preserves_original_navigation_and_blocks_b(self):
        basis = self.closed_a_anomaly()  # Controlled source history, not a camera inspection.
        until = time.monotonic()+5
        binding = InspectionNavigation(lambda: NavigationSession(self.endpoint), self.source,
            task_deadline=until)
        self.addCleanup(binding.close)
        binding.authorize(Admission('original-A', 'A', 7, until, until))
        fact = binding.submit('original-A')
        self.assertEqual(fact.outcome, 'pending')
        self.source.events.invalidate('controlled camera loss')
        while fact.outcome == 'pending' and time.monotonic() < until:
            fact = binding.status('original-A'); time.sleep(.01)
        self.assertTrue(fact.reusable)
        self.assertEqual(fact.request_id, 'original-A')
        binding.authorize(Admission('next-B', 'B', 7, until, until, basis))
        with self.assertRaises(ValueError): binding.submit('next-B')
        self.assertEqual(binding.cancel('original-A')['closure'], 'unknown')
        binding.close(); self.reap()
        facts = json.loads(self.audit.read_text())
        self.assertEqual([row['request_id'] for row in facts['records']], ['original-A'])

    def test_installed_lost_submit_response_queries_original_without_replay(self):
        session = NavigationSession(self.endpoint)
        class LostReply:
            def __init__(self): self.submits = 0
            def __getattr__(self, name): return getattr(session, name)
            def submit(self, *args, **kwargs):
                self.submits += 1
                session.submit(*args, **kwargs)
                raise RuntimeError('controlled lost reply after actual Core admission')
        until = time.monotonic()+5
        proxy = LostReply()
        binding = InspectionNavigation(lambda: proxy, self.source, task_deadline=until)
        self.addCleanup(binding.close)
        binding.authorize(Admission('original-A', 'A', 7, until, until))
        with self.assertRaises(RuntimeError): binding.submit('original-A')
        with self.assertRaises(RuntimeError): binding.submit('original-A')
        self.assertEqual(proxy.submits, 1)  # Core idempotence alone cannot prove zero replay.
        fact = binding.status('original-A')
        self.assertGreater(fact.operation_id, 0)
        self.assertEqual(fact.request_id, 'original-A')
        binding.close(); self.reap()
        facts = json.loads(self.audit.read_text())
        self.assertEqual(len(facts['records']), 1)


if __name__ == '__main__':
    unittest.main()
