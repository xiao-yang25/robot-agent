"""CI-only controlled camera frames/health; no ROS or physical observations."""
import time
from types import SimpleNamespace as N
from robot_agent._inspection_camera import CameraBinding
from robot_agent._inspection_source import Frame, InspectionSource, SourceProfile, SITES


class Camera:
    """Synthetic new-image health/frames; no ROS, classification is supplied separately."""
    def __init__(self, window_seconds=.25):
        # This fixture must provide >=3 samples even on coarse CI scheduling.
        # Production window/budget and source-quality predicates are unchanged.
        self.source = InspectionSource(7, profile=SourceProfile(window_seconds=window_seconds))
        self.binding = type('Binding', (), {'failure': None})()
        self.clock = 10.
        self.source.health(7, self.clock)
        self.window_deadline = None
        self.site = None
        self.closed = False
        self.sequence = self.pumps = 0
        self.on_pump = lambda: None

    def pump(self):
        self.pumps += 1
        self.on_pump()
        self.clock += .2
        self.source.health(7, self.clock)
        if self.site is not None:
            self.sequence += 1
            self.source.ingest(Frame(7, self.sequence, self.site, f'indicator-{self.site}',
                self.clock, time.monotonic(), SITES[self.site], bytes(640*480*3)))
        time.sleep(.001)

    def open_window(self, site, target):
        self.source.open_window(site, target)
        self.site = site
        self.window_deadline = self.source.window_deadline

    def finish_window(self):
        record = self.source.finish_window()
        self.site, self.window_deadline = None, None
        return record

    def close(self):
        self.source.close()
        self.closed = True


class BindingCamera:
    """Synthetic ROS-shaped producer through the actual message binding, no ROS.

    Faults start only at the original sampling window. Clocks, CameraInfo and
    navigation are independent; the fixture never renews Source health directly.
    """
    def __init__(self, fault=None, *, window_seconds=5.):
        self.fault, self.clock, self.site = fault, 10., None
        self.closed = False
        self.window_deadline = self.opened = None
        self.original_image = None
        self.bad_inputs = 0
        self.binding = CameraBinding(lambda: ('synthetic-camera',), self.transforms,
            profile=SourceProfile(window_seconds=window_seconds))

    @property
    def source(self):
        return self.binding.source

    @staticmethod
    def stamp(value):
        total = round(value*1e9)
        return N(sec=total//10**9, nanosec=total%10**9)

    def transforms(self, acquired, need_map):
        pose = None if not need_map else SITES[self.site]
        if need_map and self.fault == 'wrong-association':
            pose = SITES['B']
        return pose, (.1, 0., .3), acquired if need_map else None

    def pump(self):
        self.clock += .2
        header = lambda: N(stamp=self.stamp(self.clock), frame_id='inspection_optical')
        self.binding.clock_message(N(clock=self.stamp(self.clock)))
        self.binding.info_message(N(header=header(), width=640, height=480,
            k=[552., 0., 320.5, 0., 552., 240.5, 0., 0., 1.]))
        self.binding.pose_message(N(header=N(stamp=self.stamp(self.clock), frame_id='map')))
        message = N(header=header(), width=640, height=480, encoding='rgb8',
            step=1920, data=bytes(640*480*3))
        if self.site is not None and self.fault is not None:
            self.bad_inputs += 1
            if self.fault == 'missing-frame':
                message = None
            elif self.fault == 'stale-frame':
                message = self.original_image  # Original stamp, new receive sequence.
        if message is not None:
            self.binding.image_message(message)
        consumed = self.binding.pump()
        if self.original_image is None and consumed:
            self.original_image = message
        time.sleep(.001)

    def open_window(self, site, target):
        reference = self.source.open_window(site, target)
        self.site = site
        self.binding.observation = site, target
        self.window_deadline = self.source.window_deadline
        self.opened = dict(reference=reference, clock=self.clock,
                           sequence=self.binding.sequence, at=time.monotonic())
        return reference

    def finish_window(self):
        record = self.source.finish_window()
        self.site = self.binding.observation = self.window_deadline = None
        return record

    def close(self):
        self.binding.close()
        self.closed = True
