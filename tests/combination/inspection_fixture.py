"""CI-only controlled camera frames/health; no ROS or physical observations."""
import time
from robot_agent._inspection_source import Frame, InspectionSource, SourceProfile, SITES


class Camera:
    """Synthetic new-image health/frames; no ROS, classification is supplied separately."""
    def __init__(self, window_seconds=.04):
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
