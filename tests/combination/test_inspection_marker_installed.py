"""Installed opt-in pixel reader and source association outside source trees."""
import os
from pathlib import Path
import unittest

from robot_agent import _inspection_marker as marker
from robot_agent._inspection_source import Frame, InspectionSource, SITES


class InstalledMarkerTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(marker.__file__).resolve().is_relative_to(
            Path(os.environ['COMBINATION_AGENT_PREFIX']).resolve()))

    def pixels(self, clipped=False, background=0):
        data = bytearray(bytes((background,)*3)*(640*480))
        x = 430 if clipped else 20
        for y in range(20, 180):
            for col in range(x, min(x+240, 640)):
                color = (240, 20, 20) if x+20 <= col < x+220 and 50 <= y < 150 else (240, 240, 240)
                offset = (y*640+col)*3
                data[offset:offset+3] = bytes(color)
        return bytes(data)

    def test_installed_shifted_and_clipped_pixels_have_distinct_readings(self):
        for clipped, expected in ((False, 'abnormal'), (True, 'unknown')):
            actual = Frame(7, 1, 'A', 'indicator-A', .2, .2, SITES['A'], self.pixels(clipped))
            reading = marker.read_marker(actual)
            self.assertEqual(reading.classification, expected)
            if clipped:
                self.assertIsNotNone(reading.reason)

    def test_installed_visual_reading_still_requires_original_fresh_source_record(self):
        now = [0.]
        source = InspectionSource(7, clock=lambda: now[0])
        source.health(7, 0.)
        source.open_window('A', 'indicator-A')
        for sequence in range(1, 4):
            now[0] = sequence*.2
            source.health(7, now[0])
            actual = Frame(7, sequence, 'A', 'indicator-A', now[0], now[0], SITES['A'], self.pixels())
            self.assertTrue(source.ingest(actual))
            reference = source.events.take()[2].reference
            reader = source.borrow(reference)
            try:
                self.assertTrue(source.record(reader, marker.read_marker(reader.read()).classification))
            finally:
                reader.release()
        for value in (1.4, 2.2, 3., 3.8, 4.6, 5.):
            now[0] = value
            source.health(7, value)
        record = source.finish_window()
        self.assertEqual(record.classification, 'abnormal')
        self.assertTrue(source.applicable(record))
        now[0] = 6.1
        self.assertFalse(source.applicable(record))
        self.assertEqual(record.classification, 'abnormal')
        source.close()

    def test_installed_bright_profile_separates_grey_but_keeps_clipping_unknown(self):
        for clipped, expected in ((False, 'abnormal'), (True, 'unknown')):
            actual = Frame(7, 1, 'A', 'indicator-A', .2, .2, SITES['A'],
                           self.pixels(clipped, background=178))
            reading = marker.read_bright_marker(actual)
            self.assertEqual(reading.classification, expected)
            self.assertEqual(reading.profile, 'located-bright-panel-v2')
