"""History is usable during slow decisions; live dependencies cannot be replaced by it."""
from dataclasses import FrozenInstanceError, replace
import threading
import time
import unittest

from robot_agent._inspection_source import Frame, InspectionSource, SourceProfile, SITES
from robot_agent._task_runtime import Coordinator, Owner


class Clock:
    def __init__(self):
        self.value = 0.
    def __call__(self):
        return self.value


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.source = InspectionSource(7, clock=self.clock)
        self.source.health(7, 0.)
        self.window = self.source.open_window('A', 'indicator-A')

    def frame(self, seq, *, site='A', pixels=None, **changes):
        return replace(Frame(7, seq, site, f'indicator-{site}', self.clock.value,
            self.clock.value, SITES[site], pixels if pixels is not None else bytes(640*480*3)), **changes)

    def tick(self, value):
        self.clock.value = value
        self.assertTrue(self.source.health(7, value))

    def sample(self, seq, status='abnormal'):
        self.tick((seq+1)*.2)
        self.assertTrue(self.source.ingest(self.frame(seq)))
        event = self.source.events.take()[2]
        reader = self.source.borrow(event.reference)
        try:
            self.assertTrue(self.source.record(reader, status))
        finally:
            reader.release()

    def finish(self, statuses=('abnormal',)*3):
        for seq, status in enumerate(statuses):
            self.sample(seq, status)
        for i in range(1, 6):
            self.tick(.6+i*.88)
        return self.source.finish_window()

    def test_closed_record_survives_ten_second_wait_with_declared_health_updates(self):
        record = self.finish()
        for step in range(1, 21):
            self.tick(5.+step*.5)
            # Sampling is closed; new frames cannot grow the pixel window or rewrite history.
            self.assertFalse(self.source.ingest(self.frame(100+step)))
            self.assertTrue(self.source.applicable(record))
        self.assertEqual(record.classification, 'abnormal')
        self.assertEqual(record.samples,3)
        self.assertAlmostEqual(record.acquired_first,.2)
        self.assertAlmostEqual(record.acquired_last,.6)
        with self.assertRaises(FrozenInstanceError):
            record.classification = 'normal'
        self.assertIsNone(self.source._latest)

    def test_missing_health_is_latched_even_if_a_late_heartbeat_arrives(self):
        record = self.finish()
        self.clock.value += 1.01
        self.assertFalse(self.source.health(7, self.clock.value))
        self.assertFalse(self.source.applicable(record))
        self.assertEqual(record.classification, 'abnormal')
        self.assertEqual(self.source.events.take()[1], 'inspection source health or clock expired')

    def test_poll_expiry_withdraws_blocked_model_but_keeps_original_io(self):
        record = self.finish()
        entered, release = threading.Event(), threading.Event()
        coordinator = Coordinator('inspection', lambda: False, 1, events=self.source.events)
        class Model:
            def decide(self):
                entered.set()
                if not release.wait(2):
                    raise AssertionError('gate not released')
                return {'next': 'B', 'inspection': record.reference}
        owner = Owner(coordinator.exchange, 'decision', Model)
        owner.start()
        try:
            decision = coordinator.begin('decision', 'decide', (), {}, deadline=time.monotonic()+2)
            self.assertTrue(entered.wait(1))
            io = coordinator.begin('io', 'status', (), {}, deadline=time.monotonic()+2,
                                   association={'request_id':'original-A'})
            coordinator.exchange.claim('io')
            coordinator.exchange.complete('io', io, {'outcome':'unknown'}, None)
            self.clock.value += 1.01
            result = coordinator.poll()
            self.assertTrue(decision.withdrawn)
            self.assertFalse(io.withdrawn)
            self.assertEqual(result['io'].association['request_id'], 'original-A')
            self.assertEqual(result['io'].value['outcome'], 'unknown')
            self.assertFalse(release.is_set())
        finally:
            release.set()
            self.assertTrue(owner.finish(time.monotonic()+2)['thread_stopped'])
        self.assertTrue(coordinator.poll()['decision'].withdrawn)

    def test_original_model_completion_can_use_history_after_long_wait(self):
        record = self.finish()
        entered, release = threading.Event(), threading.Event()
        coordinator = Coordinator('inspection', lambda: False, 1, events=self.source.events)
        class Model:
            def decide(self):
                entered.set()
                if not release.wait(2):
                    raise AssertionError('gate not released')
                return {'next': 'B', 'inspection': record.reference}
        owner = Owner(coordinator.exchange, 'decision', Model)
        owner.start()
        try:
            coordinator.begin('decision','decide',(),{},deadline=time.monotonic()+2)
            self.assertTrue(entered.wait(1))
            for step in range(1,11):
                self.tick(5.+step*.5)
                self.assertEqual(coordinator.poll(),{})
            release.set()
            with coordinator.exchange.condition:
                self.assertTrue(coordinator.exchange.condition.wait_for(
                    lambda: coordinator.exchange.slots['decision'].state=='completed',timeout=1))
            result=coordinator.poll()['decision']
            self.assertFalse(result.withdrawn)
            self.assertEqual(result.value['inspection'],record.reference)
            self.assertTrue(self.source.applicable(record))
        finally:
            release.set()
            self.assertTrue(owner.finish(time.monotonic()+2)['thread_stopped'])

    def test_duplicate_result_close_and_release_cannot_create_new_evidence(self):
        self.tick(.2)
        self.source.ingest(self.frame(0))
        reader=self.source.borrow('0')
        self.assertTrue(self.source.record(reader,'normal'))
        self.assertFalse(self.source.record(reader,'abnormal'))
        reader.release()
        with self.assertRaises(RuntimeError):
            self.source.record(reader,'normal')
        for value in (1.,1.8,2.6,3.4,4.2,5.):
            self.tick(value)
        self.assertEqual(self.source.finish_window().classification,'unknown')
        self.assertIsNone(self.source.events.take()[2])
        with self.assertRaises(RuntimeError):
            self.source.finish_window()

    def test_invalid_pixel_layout_faults_and_stop_wins_over_latest(self):
        self.tick(.2)
        self.assertFalse(self.source.ingest(self.frame(0,pixels=b'')))
        self.assertEqual(self.source.events.take()[1],'inspection pixel layout invalid')
        self.setUp()
        self.tick(.2)
        self.source.ingest(self.frame(0))
        self.source.events.stop()
        coordinator=Coordinator('inspection',lambda:False,1,events=self.source.events)
        coordinator.poll()
        call=coordinator.begin('io','submit',(),{},deadline=time.monotonic()+1)
        self.assertFalse(call.started)
        self.assertIsInstance(coordinator.poll()['io'].error,InterruptedError)

    def test_borrowed_frame_is_not_reused_after_mutable_producer_or_latest_changes(self):
        pixels = bytearray(640*480*3)
        pixels[0] = 17
        self.tick(.2)
        self.source.ingest(self.frame(0,pixels=pixels))
        reader = self.source.borrow('0')
        pixels[0] = 99
        self.tick(.4)
        self.source.ingest(self.frame(1))
        self.assertEqual(reader.read().pixels[0],17)
        with self.assertRaises(RuntimeError):
            self.source.borrow('1')
        self.tick(1.21)
        with self.assertRaises(RuntimeError):
            reader.read()
        reader.release()
        with self.assertRaises(RuntimeError):
            reader.read()
        next_reader = self.source.borrow('1')
        self.assertEqual(next_reader.read().pixels[0],0)
        next_reader.release()

    def test_stale_future_duplicate_and_pre_window_samples_cannot_become_evidence(self):
        self.tick(.5)
        for seq, changes in enumerate(({'acquired':-2.}, {'received':-2.}, {'acquired':.6}, {'received':.6})):
            self.assertFalse(self.source.ingest(self.frame(seq,**changes)))
        self.assertTrue(self.source.ingest(self.frame(4)))
        self.assertFalse(self.source.ingest(self.frame(4)))
        self.assertFalse(self.source.ingest(self.frame(5,acquired=.4)))
        self.assertEqual(self.source.events.take()[2].reference,'4')

    def test_wrong_station_or_target_invalidates_without_relabeled_frame(self):
        for changes in ({'map_xy':SITES['B']},{'target':'indicator-B'},{'frame_id':'overview'}):
            source=InspectionSource(7, clock=self.clock)
            source.health(7,0.)
            source.open_window('A','indicator-A')
            self.assertFalse(source.ingest(self.frame(0,**changes)))
            self.assertEqual(source.events.take()[1],'inspection sample association invalid')

    def test_pose_snapshot_is_validated_and_published_without_rereading_producer(self):
        class ChangingPose(list):
            def __init__(self):
                super().__init__(SITES['A'])
                self.iterations=0
            def __iter__(self):
                self.iterations+=1
                if self.iterations>=3:
                    self[:]=SITES['B']
                return super().__iter__()
        pose=ChangingPose()
        self.tick(.2)
        self.assertTrue(self.source.ingest(self.frame(0,map_xy=pose)))
        pose[:]=SITES['B']
        reader=self.source.borrow('0')
        self.assertEqual(reader.read().map_xy,SITES['A'])
        self.assertEqual(pose.iterations,1)
        reader.release()

    def test_malformed_pose_latches_failure_and_does_not_leave_history_applicable(self):
        for pose in (None,('invalid',-.5),(True,-.5),(float('nan'),-.5),(10**1000,-.5),(.7,)):
            self.setUp()
            record=self.finish()
            self.source.open_window('B','indicator-B')
            self.tick(5.2)
            self.assertFalse(self.source.ingest(self.frame(20,site='B',map_xy=pose)))
            self.assertEqual(self.source.events.take()[1],'inspection sample association invalid')
            self.assertFalse(self.source.applicable(record))
            self.assertEqual(record.classification,'abnormal')

    def test_numeric_overflow_is_controlled_for_health_and_sample_times(self):
        for field in ('acquired','received'):
            self.setUp()
            self.tick(.2)
            self.assertFalse(self.source.ingest(self.frame(0,**{field:10**1000})))
            self.assertEqual(self.source.events.take()[1],'inspection timestamp invalid')
        self.setUp()
        self.assertFalse(self.source.health(7,10**1000))
        self.assertEqual(self.source.events.take()[1],'inspection source health invalid')
        with self.assertRaises(ValueError):
            SourceProfile(health_seconds=10**1000)

    def test_generation_change_clock_pause_and_rollback_are_irreversible(self):
        for fault in ('generation','pause','rollback'):
            source=InspectionSource(7,clock=self.clock)
            self.clock.value=0.
            source.health(7,1.)
            if fault=='generation':
                self.assertFalse(source.health(8,1.1))
            elif fault=='rollback':
                self.assertFalse(source.health(7,.9))
            else:
                self.clock.value=.8
                self.assertTrue(source.health(7,1.))
                self.clock.value=1.01
                self.assertFalse(source.health(7,1.))
            self.assertFalse(source.health(7,2.))
            self.assertIsNotNone(source.events.take()[1])

    def test_unknown_or_conflicting_samples_do_not_choose_favorable_frames(self):
        for statuses in (('unknown','abnormal','abnormal'),('normal','abnormal','abnormal')):
            self.setUp()
            record=self.finish(statuses)
            self.assertEqual(record.classification,'unknown')
            self.assertFalse(self.source.applicable(record))

    def test_new_same_domain_window_does_not_change_closed_record_or_accept_old_read(self):
        a=self.finish()
        self.source.open_window('B','indicator-B')
        self.tick(5.2)
        self.source.ingest(self.frame(20,site='B'))
        reader=self.source.borrow('20')
        self.source.record(reader,'normal')
        reader.release()
        self.assertTrue(self.source.applicable(a))
        self.assertEqual(a.classification,'abnormal')
        for i in range(1,6):
            self.tick(5.2+i*.96)
        b=self.source.finish_window()
        self.assertEqual(b.classification,'unknown')
        with self.assertRaises(RuntimeError):
            self.source.open_window('A','indicator-A')

    def test_close_and_explicit_stop_block_reads_and_leave_records_unchanged(self):
        record=self.finish()
        self.source.events.stop()
        self.assertFalse(self.source.applicable(record))
        self.source.close()
        self.assertEqual(record.classification,'abnormal')
        with self.assertRaises(RuntimeError):
            self.source.open_window('B','indicator-B')

    def test_profile_rejects_nonfinite_or_expanded_bounds(self):
        for changes in ({'health_seconds':float('nan')},{'window_seconds':6},
                        {'maximum_samples':26},{'minimum_samples':True}):
            with self.assertRaises(ValueError):
                SourceProfile(**changes)


if __name__=='__main__':
    unittest.main()
