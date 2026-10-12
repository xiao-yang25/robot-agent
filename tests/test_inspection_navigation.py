"""Public Session adaptation and submission-time guards; no ROS or movement."""
from copy import deepcopy
from dataclasses import replace
import threading
import time
import unittest

from robot_agent._inspection_navigation import Admission, InspectionNavigation
from robot_agent._inspection_source import Frame, InspectionSource, SourceProfile, SITES
from robot_agent._task_runtime import Coordinator, Owner
from test_inspection_source import Clock
from test_navigation import SessionFixture


def ready_source(*, record=False):
    clock = Clock()
    source = InspectionSource(7, clock=clock, profile=SourceProfile(window_seconds=.6))
    source.health(7, 0.)
    basis = None
    if record:
        source.open_window('A', 'indicator-A')
        for seq, stamp in enumerate((.1, .3, .5)):
            clock.value = stamp
            source.health(7, stamp)
            source.ingest(Frame(7, seq, 'A', 'indicator-A', stamp, stamp,
                                SITES['A'], bytes(640*480*3)))
            latest = source.events.take()[2]
            reader = source.borrow(latest.reference)
            try:
                source.record(reader, 'abnormal')
            finally:
                reader.release()
        clock.value = .61
        source.health(7, .61)
        basis = source.finish_window()
    return source, clock, basis


class Session(SessionFixture):
    def close(self):
        return {'closure': 'unknown'}


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.source, self.clock, self.basis = ready_source(record=True)
        self.session = Session()
        self.binding = InspectionNavigation(lambda: self.session, self.source,
            task_deadline=20., clock=self.clock)

    def admission(self, site='A', **changes):
        return replace(Admission(f'inspection-{site}', site, 7, 10., 5.,
                                 None if site == 'A' else self.basis), **changes)

    def visit_a(self):
        self.binding.authorize(self.admission())
        self.assertEqual(self.binding.submit('inspection-A').outcome, 'pending')
        return self.binding.status('inspection-A')

    def test_correlated_a_then_b_keeps_final_context_pending(self):
        a = self.visit_a()
        self.assertEqual((a.outcome, a.pose_verified, a.reusable), ('arrived', True, True))
        self.binding.authorize(self.admission('B'))
        b = self.binding.submit('inspection-B')
        self.assertEqual(b.outcome, 'pending')
        b = self.binding.status('inspection-B')
        self.assertEqual((b.outcome, b.pose_verified, b.reusable), ('arrived', True, False))
        self.assertNotEqual(a.operation_id, b.operation_id)
        self.assertEqual(self.binding.attempts['inspection-B']['record']['receipt']['settlement'], 'pending')

    def test_guard_checks_source_stop_revoke_and_deadline_after_prepare_rpc(self):
        for fault in ('source', 'stop', 'revoke', 'deadline', 'permission'):
            with self.subTest(fault=fault):
                self.setUp()
                stop = threading.Event()
                self.binding.stopped = stop.is_set
                self.binding.authorize(self.admission())
                def invalidate():
                    if fault == 'source': self.source.events.invalidate('camera lost during RPC')
                    if fault == 'stop': stop.set()
                    if fault == 'revoke': self.binding.revoke('inspection-A')
                    if fault == 'deadline': self.clock.value = 5.
                if fault == 'permission': self.session.available = False
                else: self.session.after_observe = invalidate
                with self.assertRaises((ValueError, InterruptedError)):
                    self.binding.submit('inspection-A')
                self.assertFalse(self.session.submissions)
                self.assertFalse(self.binding.attempts)

    def test_source_check_cannot_carry_earlier_permission_across_revoke_stop_or_expiry(self):
        for fault in ('revoke', 'stop', 'deadline'):
            with self.subTest(fault=fault):
                self.setUp()
                stopped = threading.Event()
                self.binding.stopped = stopped.is_set
                self.binding.authorize(self.admission())
                original = self.source.refresh
                count = 0
                def checked():
                    nonlocal count
                    count += 1
                    result = original()
                    if count == 2:
                        if fault == 'revoke': self.binding.revoke('inspection-A')
                        if fault == 'stop': stopped.set()
                        if fault == 'deadline': self.clock.value = 5.
                    return result
                self.source.refresh = checked
                with self.assertRaises(InterruptedError): self.binding.submit('inspection-A')
                self.assertFalse(self.session.submissions)
                self.assertFalse(self.binding.attempts)

    def test_admissions_cannot_be_replaced_or_extended_and_forged_basis_cannot_admit_b(self):
        self.binding.authorize(self.admission())
        with self.assertRaises(RuntimeError): self.binding.authorize(self.admission(operation_deadline=11.))
        self.binding.submit('inspection-A'); self.binding.status('inspection-A')
        self.binding.authorize(self.admission('B', basis=replace(self.basis)))
        with self.assertRaises(ValueError): self.binding.submit('inspection-B')
        self.assertEqual([args['site'] for _, args in self.session.submissions], ['A'])

    def test_revocation_preserves_site_reservation_and_cannot_allow_a_second_a(self):
        original = self.admission()
        self.binding.authorize(original)
        self.binding.revoke(original.request_id)
        with self.assertRaises(RuntimeError):
            self.binding.authorize(replace(original, request_id='replacement-A'))
        with self.assertRaises(InterruptedError): self.binding.submit(original.request_id)
        self.assertEqual(self.binding.grants[original.request_id], original)
        self.assertFalse(self.session.submissions)

    def test_b_requires_actual_a_release_fresh_pose_and_same_realm(self):
        for fault in ('pending', 'pose', 'epoch', 'session'):
            with self.subTest(fault=fault):
                self.setUp()
                self.session.pending_a = fault == 'pending'
                self.visit_a()
                if fault == 'pose': self.session.pose = [-2., -.5]
                if fault == 'epoch': self.session.epoch += 1
                if fault == 'session': self.session.session_id = 'foreign'
                self.binding.authorize(self.admission('B'))
                with self.assertRaises(ValueError): self.binding.submit('inspection-B')
                self.assertEqual(len(self.session.submissions), 1)

    def test_ambiguous_submit_retains_reference_and_can_only_query_original(self):
        self.session.ambiguous = True
        self.binding.authorize(self.admission())
        with self.assertRaises(RuntimeError): self.binding.submit('inspection-A')
        original = deepcopy(self.binding.attempts['inspection-A']['reference'])
        with self.assertRaises(RuntimeError): self.binding.submit('inspection-A')
        fact = self.binding.status('inspection-A')
        self.assertEqual(fact.outcome, 'arrived')
        self.assertEqual(len(self.session.submissions), 1)
        self.assertEqual(self.binding.attempts['inspection-A']['reference'], original)

    def test_foreign_operation_native_identity_target_or_reference_cannot_become_arrival(self):
        for key in ('request', 'operation', 'native', 'target', 'reference', 'binding'):
            with self.subTest(key=key):
                self.setUp()
                self.binding.authorize(self.admission())
                self.binding.submit('inspection-A')
                original = self.session.status
                def changed(request):
                    row = original(request)
                    if key == 'request': row['request_id'] = 'foreign'
                    if key == 'operation': row['operation_id'] += 1
                    if key == 'native': row['goal_id'] = 'b'*32
                    if key == 'target': row['target'][0] += 1
                    if key == 'reference': row['observation_reference']['observation_id'] = 'foreign'
                    if key == 'binding': row['receipt']['authority']['binding']['generation'] += 1
                    return row
                self.session.status = changed
                with self.assertRaises(ValueError): self.binding.status('inspection-A')
                self.assertEqual(self.binding.facts['inspection-A'].outcome, 'pending')
                self.assertEqual(len(self.session.submissions), 1)

    def test_actual_arrival_still_requires_current_pose_and_nonrollback_measurement(self):
        for fault in ('pose', 'stamp'):
            with self.subTest(fault=fault):
                self.setUp()
                self.binding.authorize(self.admission()); self.binding.submit('inspection-A')
                original = self.session.observe
                def changed():
                    row = original()
                    if fault == 'pose': row['pose'] = [-2., -.5]
                    else: row['sample_sim_seconds'] = .01
                    return row
                self.session.observe = changed
                with self.assertRaises(ValueError): self.binding.status('inspection-A')
                self.assertFalse(self.binding.facts['inspection-A'].reusable)

    def test_camera_fault_does_not_prevent_original_status_cancel_or_close(self):
        self.binding.authorize(self.admission()); self.binding.submit('inspection-A')
        self.source.events.invalidate('independent camera lost')
        a = self.binding.status('inspection-A')
        self.assertTrue(a.reusable)
        # Actual close/cancel replies are reported, never promoted to native stop.
        result = self.binding.cancel('inspection-A')
        self.assertEqual(result['closure'], 'unknown')
        self.assertEqual(self.session.cancellations, ['inspection-A'])
        self.assertEqual(self.binding.close()['closure'], 'unknown')

    def test_pre_submit_cancel_and_invalid_identity_never_touch_session(self):
        for change in ({'generation': True}, {'admission_deadline': float('nan')},
                       {'operation_deadline': 21.}, {'site': 'C'}):
            with self.assertRaises(ValueError): self.binding.authorize(self.admission(**change))
        self.binding.authorize(self.admission())
        self.assertEqual(self.binding.cancel('inspection-A')['closure'], 'not_submitted')
        self.assertFalse(self.session.submissions)
        self.assertFalse(self.session.cancellations)

    def test_claimed_io_revalidates_at_actual_submit_and_keeps_late_original_result(self):
        source, clock, _ = ready_source()
        coordinator = Coordinator('binding', lambda: False, 2.)
        entered, gate = threading.Event(), threading.Event()
        session = Session()
        original = session.observe
        def paused():
            entered.set()
            if not gate.wait(2.): raise TimeoutError('fixture gate')
            return original()
        session.observe = paused
        binding = InspectionNavigation(lambda: session, source, task_deadline=time.monotonic()+10)
        until = time.monotonic()+5
        binding.authorize(Admission('original-A', 'A', 7, until, until))
        owner = Owner(coordinator.exchange, 'io', lambda: binding, close=lambda b: b.close())
        owner.start()
        try:
            call = coordinator.begin('io', 'submit', ('original-A',), {}, deadline=until)
            self.assertTrue(entered.wait(1.))
            source.events.invalidate('camera failed after I/O claim')
            coordinator.exchange.withdraw('io', call)
            gate.set()
            completed = None
            while time.monotonic() < until and completed is None:
                completed = coordinator.poll().get('io')
                time.sleep(.001)
            self.assertIs(completed, call)
            self.assertTrue(call.started)
            self.assertTrue(call.withdrawn)
            self.assertIsInstance(call.error, ValueError)
            self.assertFalse(session.submissions)
        finally:
            gate.set()
            result = owner.finish(time.monotonic()+2)
            self.assertTrue(result['thread_stopped'])


if __name__ == '__main__':
    unittest.main()
