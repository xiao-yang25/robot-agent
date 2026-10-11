"""Actual-image health provenance and immutable ROS-message association snapshots."""
from types import SimpleNamespace as N
from fractions import Fraction
import unittest

from robot_agent._inspection_camera import CameraBinding, seconds
from robot_agent._inspection_marker import classify
from robot_agent._inspection_source import Frame, SITES
from test_inspection_source import Clock


def stamp(value):
    total=round(value*1e9)
    return N(sec=total//10**9,nanosec=total%10**9)


def image(value, data=None):
    return N(header=N(stamp=stamp(value),frame_id='inspection_optical'),
             width=640,height=480,encoding='rgb8',step=1920,
             data=bytes(640*480*3) if data is None else data)


def info(value):
    return N(header=N(stamp=stamp(value),frame_id='inspection_optical'),
             width=640,height=480,k=[552.,0.,320.5,0.,552.,240.5,0.,0.,1.])


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.clock=Clock()
        self.publisher=['original-camera']
        self.tf_available=True
        self.pose=SITES['A']
        self.binding=CameraBinding(lambda:tuple(self.publisher),self.transforms,clock=self.clock)

    def transforms(self,value,need_map):
        if not self.tf_available:
            return None
        return (self.pose if need_map else None,(.1,0.,.3),value if need_map else None)

    def feed(self,value,with_image=True):
        self.clock.value=value
        self.binding.clock_message(N(clock=stamp(value)))
        self.binding.info_message(info(value))
        self.binding.pose_message(N(header=N(stamp=stamp(value),frame_id='map')))
        if with_image:
            self.binding.image_message(image(value))
        return self.binding.pump()

    def test_clock_and_info_without_new_image_cannot_renew_source_health(self):
        self.assertTrue(self.feed(.2))
        source=self.binding.source
        for value in (.4,.6,.8,1.,1.2,1.4):
            self.assertFalse(self.feed(value,False))
        self.assertFalse(source.refresh())
        self.assertIn('expired',source.events.take()[1])

    def test_future_image_waits_for_matching_clock_without_changing_receive_time(self):
        self.clock.value=.2
        self.binding.image_message(image(.2))
        self.assertFalse(self.binding.pump())
        original=self.binding.pending.received
        self.clock.value=.3
        self.binding.clock_message(N(clock=stamp(.2)))
        self.binding.info_message(info(.2))
        self.assertTrue(self.binding.pump())
        self.assertEqual(self.binding.last_consumed['received'],original)

    def test_delayed_tf_within_original_age_can_publish_owned_snapshot(self):
        self.assertTrue(self.feed(.2))
        self.binding.source.open_window('A','indicator-A')
        self.binding.observation='A','indicator-A'
        self.tf_available=False
        data=bytearray(640*480*3)
        data[0]=17
        self.clock.value=.4
        self.binding.clock_message(N(clock=stamp(.4)))
        self.binding.info_message(info(.4))
        self.binding.pose_message(N(header=N(stamp=stamp(.4),frame_id='map')))
        self.binding.image_message(image(.4,data))
        self.assertFalse(self.binding.pump())
        data[0]=99
        self.tf_available=True
        self.clock.value=.5
        self.assertTrue(self.binding.pump())
        reference=self.binding.source.events.take()[2].reference
        reader=self.binding.source.borrow(reference)
        self.assertEqual(reader.read().pixels[0],17)
        reader.release()

    def test_stale_image_cannot_initialize_health_and_clock_rollback_is_latched(self):
        self.clock.value=.2
        self.binding.image_message(image(.2))
        self.clock.value=1.3
        self.binding.clock_message(N(clock=stamp(1.3)))
        self.binding.info_message(info(.2))
        self.assertFalse(self.binding.pump())
        self.assertIsNone(self.binding.source)
        self.feed(1.4)
        self.binding.clock_message(N(clock=stamp(1.3)))
        self.assertEqual(self.binding.source.events.take()[1],'camera clock rolled back')

    def test_map_tf_delay_preserves_image_without_repeated_health_renewal(self):
        self.feed(.2)
        self.binding.source.open_window('A','indicator-A')
        self.binding.observation='A','indicator-A'
        self.binding.transforms=lambda value,need_map:(None,(.1,0.,.3),None)
        self.assertFalse(self.feed(.4))
        self.assertIsNotNone(self.binding.pending)
        consumed=self.binding.last_consumed
        self.clock.value=.5
        self.binding.clock_message(N(clock=stamp(.5)))
        self.assertFalse(self.binding.pump())
        self.assertIs(self.binding.last_consumed,consumed)
        self.binding.transforms=self.transforms
        self.assertTrue(self.binding.pump())
        reference=self.binding.source.events.take()[2].reference
        reader=self.binding.source.borrow(reference)
        self.assertEqual(reader.read().acquired,.4)
        self.assertEqual(self.binding.last_observed['tf_stamp'],.4)
        self.assertEqual(self.binding.last_observed['consumed'],.5)
        self.assertEqual(self.binding.last_consumed['consumed'],.4)
        reader.release()

    def test_unresolved_map_tf_cannot_turn_one_image_into_continuous_health(self):
        self.feed(.2)
        self.binding.source.open_window('A','indicator-A')
        self.binding.observation='A','indicator-A'
        self.binding.transforms=lambda value,need_map:(None,(.1,0.,.3),None)
        self.assertFalse(self.feed(.4))
        for value in (.6,.8,1.,1.2,1.4,1.6):
            self.assertFalse(self.feed(value,False))
        self.assertFalse(self.binding.source.refresh())
        self.assertIn('expired',self.binding.source.events.take()[1])

    def test_camera_info_snapshot_and_nonfinite_focal_rejection(self):
        message=info(.2)
        self.binding.info_message(message)
        message.k[0]=float('nan')
        self.assertEqual(self.binding.info[4][0],552.)
        self.binding.info_message(message)
        self.assertEqual(self.binding.failure,'camera intrinsics invalid')
        self.assertFalse(self.feed(.4))

    def test_typed_real_intrinsics_normalize_but_strings_and_bools_fail(self):
        message=info(.2)
        message.k[0]=Fraction(552)
        self.binding.info_message(message)
        self.assertIs(type(self.binding.info[4][0]),float)
        for bad in ('552',True):
            self.setUp()
            message.k[0]=bad
            self.binding.info_message(message)
            self.assertEqual(self.binding.failure,'camera intrinsics invalid')

    def test_publisher_change_latches_fault_after_initial_actual_image(self):
        self.feed(.2)
        self.publisher[:]=['replacement-camera']
        self.assertFalse(self.feed(.4))
        self.assertEqual(self.binding.source.events.take()[1],'camera publisher changed')
        self.publisher[:]=['original-camera']
        self.assertFalse(self.feed(.6))

    def test_missing_publisher_or_optical_transform_cannot_claim_readiness(self):
        for fault in ('publisher','tf'):
            self.setUp()
            if fault=='publisher':
                self.publisher[:]=[]
            else:
                self.tf_available=False
            self.assertFalse(self.feed(.2))
            self.assertIsNone(self.binding.source)

    def test_health_after_window_needs_camera_but_not_old_station_pose(self):
        self.feed(.2)
        self.pose=SITES['B']
        self.assertTrue(self.feed(.4))
        self.assertTrue(self.binding.source.refresh())
        self.assertIsNone(self.binding.last_consumed['map_xy'])
        self.binding.source.open_window('A','indicator-A')
        self.binding.observation='A','indicator-A'
        self.assertFalse(self.feed(.6))
        self.assertEqual(self.binding.source.events.take()[1],'inspection sample association invalid')

    def test_close_blocks_publication_and_invalidates_source(self):
        self.feed(.2)
        self.binding.close()
        self.assertFalse(self.feed(.4))
        self.assertFalse(self.binding.source.refresh())
        self.assertIsNone(self.binding.pending)

    def test_marker_reads_pixels_only_and_keeps_grey_border_unknown(self):
        for color,white,expected in (([18,255,18],255,'normal'),([255,18,18],255,'abnormal'),
                                      ([18,255,18],100,'unknown')):
            data=bytearray(640*480*3)
            for y in range(100,380):
                for x in range(180,460):
                    offset=(y*640+x)*3
                    if abs(x-320)<=64 and abs(y-240)<=64:
                        data[offset:offset+3]=bytes(color)
                    elif 110<=max(abs(x-320),abs(y-240))<=139:
                        data[offset:offset+3]=bytes([white]*3)
            frame=Frame(1,1,'A','indicator-A',.2,.2,SITES['A'],bytes(data))
            self.assertEqual(classify(frame)[0],expected)

    def test_invalid_ros_stamp_fails_without_initializing_source(self):
        with self.assertRaises(ValueError):
            seconds(N(sec=0,nanosec=10**9))
        bad=image(.2)
        bad.header.stamp.sec=-1
        self.binding.image_message(bad)
        self.assertEqual(self.binding.failure,'camera image invalid')
        self.assertIsNone(self.binding.source)


if __name__=='__main__':
    unittest.main()
