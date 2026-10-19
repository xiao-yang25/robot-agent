"""No-ROS subprocess camera fixture for the actual installed command."""
from dataclasses import replace
from pathlib import Path
import sys

from inspection_fixture import Camera
from robot_agent import inspection_cli


def image(color):
    pixels = bytearray(640*480*3)
    for y in range(100, 300):
        for x in range(150, 450):
            value = color if 170 <= x < 430 and 120 <= y < 280 else (255, 255, 255)
            offset = (y*640+x)*3
            pixels[offset:offset+3] = bytes(value)
    return bytes(pixels)


def main():
    scenario, endpoint, output, ready = sys.argv[1:]
    assert scenario in ('normal', 'recheck', 'unknown', 'stop', 'close-failure')
    green, red = image((10, 220, 10)), image((220, 10, 10))
    class Pixels(Camera):
        def __init__(self):
            super().__init__(window_seconds=5.)
            ingest = self.source.ingest
            def record(frame):
                pixels = (bytes(640*480*3) if scenario == 'unknown' else
                          red if scenario in ('recheck', 'stop') and frame.site == 'A' else green)
                return ingest(replace(frame, pixels=pixels))
            self.source.ingest = record

        def open_window(self, site, target):
            result = super().open_window(site, target)
            if scenario == 'stop' and site == 'B':
                Path(ready).write_text('B sampling active')
            return result

        def close(self):
            super().close()
            if scenario == 'close-failure':
                raise RuntimeError('controlled camera close failure')

    inspection_cli.RosCamera = Pixels
    return inspection_cli.main(['--endpoint', endpoint, '--output', output,
                                '--marker-reader', 'located-bright-panel'])


if __name__ == '__main__':
    raise SystemExit(main())
