"""Hand-drawn controlled panels; expected behavior does not use reader helpers."""
from dataclasses import FrozenInstanceError, replace
import json
import unittest

from robot_agent._inspection_marker import classify, read_marker
from robot_agent._inspection_source import Frame, SITES


def paint(data, rectangle, color):
    left, top, right, bottom = rectangle
    for y in range(max(0, top), min(480, bottom)):
        a, b = max(0, left), min(640, right)
        if a < b:
            data[(y*640+a)*3:(y*640+b)*3] = bytes(color)*(b-a)


def panel(data, x=200, y=140, *, color=(20, 240, 20), white=(240, 240, 240),
          width=240, height=160):
    paint(data, (x, y, x+width, y+height), white)
    paint(data, (x+20, y+30, x+width-20, y+height-30), color)


def frame(data):
    return Frame(1, 1, 'A', 'indicator-A', .2, .2, SITES['A'], bytes(data))


class LocatedMarkerTests(unittest.TestCase):
    def test_complete_centered_and_shifted_panels_keep_their_pixel_color(self):
        for x, y in ((200, 140), (20, 20), (380, 300)):
            for color, expected in (((20, 240, 20), 'normal'), ((240, 20, 20), 'abnormal')):
                with self.subTest(x=x, y=y, expected=expected):
                    data = bytearray(640*480*3)
                    panel(data, x, y, color=color)
                    reading = read_marker(frame(data))
                    self.assertEqual(reading.classification, expected)
                    self.assertIsNone(reading.reason)
                    self.assertEqual(reading.region, (x, y, x+240, y+160))
                    self.assertGreaterEqual(reading.color_fraction, .7)

    def test_shifted_complete_panel_distinguishes_old_fixed_center(self):
        data = bytearray(640*480*3)
        panel(data, 20, 20)
        actual = frame(data)
        self.assertEqual(classify(actual)[0], 'unknown')
        self.assertEqual(read_marker(actual).classification, 'normal')

    def test_no_target_and_color_walls_are_unknown(self):
        for color in ((0, 0, 0), (100, 100, 100), (20, 240, 20), (240, 20, 20), (240, 240, 240)):
            with self.subTest(color=color):
                reading = read_marker(frame(bytes(color)*(640*480)))
                self.assertEqual(reading.classification, 'unknown')

    def test_clipped_panel_is_not_reconstructed_from_its_visible_color(self):
        for x, y in ((-20, 140), (430, 140), (200, -20), (200, 350)):
            data = bytearray(640*480*3)
            panel(data, x, y)
            self.assertEqual(read_marker(frame(data)).classification, 'unknown')

    def test_missing_whole_border_side_is_rejected_despite_other_white_sides(self):
        sides = ((200, 140, 440, 170), (200, 270, 440, 300),
                 (200, 140, 220, 300), (420, 140, 440, 300))
        for side in sides:
            data = bytearray(640*480*3)
            panel(data)
            paint(data, side, (0, 0, 0))
            reading = read_marker(frame(data))
            self.assertEqual(reading.classification, 'unknown')

    def test_two_complete_candidates_remain_ambiguous_even_when_same_color(self):
        for second in ((20, 240, 20), (240, 20, 20)):
            data = bytearray(640*480*3)
            panel(data, 20, 140)
            panel(data, 380, 140, color=second)
            reading = read_marker(frame(data))
            self.assertEqual(reading.classification, 'unknown')
            self.assertEqual(reading.reason, 'target_not_unique')

    def test_incomplete_candidate_cannot_be_hidden_by_one_complete_candidate(self):
        data = bytearray(640*480*3)
        panel(data, 20, 140)
        panel(data, 430, 140)
        self.assertEqual(read_marker(frame(data)).classification, 'unknown')

    def test_severely_clipped_second_panel_is_not_discarded_by_size_or_aspect(self):
        for x, y in ((600, 250), (570, 250), (550, 250), (300, -120)):
            data = bytearray(640*480*3)
            panel(data, 20, 20)
            panel(data, x, y)
            self.assertEqual(read_marker(frame(data)).classification, 'unknown')

    def test_adjacent_white_frames_are_not_one_target(self):
        for width in (160, 200, 220, 240):
            data = bytearray(640*480*3)
            panel(data, 20, 140, width=width)
            panel(data, 20+width, 140, width=width)
            self.assertEqual(read_marker(frame(data)).classification, 'unknown')

    def test_adjacent_incomplete_panel_cannot_hide_behind_one_enclosed_panel(self):
        data = bytearray(640*480*3)
        panel(data, 20, 140, width=200)
        panel(data, 220, 140, width=200)
        paint(data, (285, 140, 355, 170), (0, 0, 0))
        self.assertEqual(read_marker(frame(data)).classification, 'unknown')

    def test_white_frame_with_no_colored_state_is_unknown(self):
        data = bytearray(640*480*3)
        panel(data, color=(80, 80, 80))
        reading = read_marker(frame(data))
        self.assertEqual(reading.classification, 'unknown')
        self.assertEqual(reading.reason, 'color_evidence_insufficient')

    def test_half_red_half_green_is_not_a_majority_vote(self):
        data = bytearray(640*480*3)
        panel(data)
        paint(data, (320, 170, 420, 270), (240, 20, 20))
        reading = read_marker(frame(data))
        self.assertEqual(reading.classification, 'unknown')
        self.assertEqual(reading.reason, 'conflicting_colors')

    def test_small_surviving_color_patch_cannot_define_a_pure_color_crop(self):
        data = bytearray(640*480*3)
        panel(data, color=(80, 80, 80))
        paint(data, (300, 205, 340, 235), (20, 240, 20))
        self.assertEqual(read_marker(frame(data)).classification, 'unknown')

    def test_grey_border_and_too_small_panel_are_unknown(self):
        for kwargs in ({'white': (100, 100, 100)}, {'width': 70, 'height': 50}):
            data = bytearray(640*480*3)
            panel(data, **kwargs)
            self.assertEqual(read_marker(frame(data)).classification, 'unknown')

    def test_unframed_color_and_small_white_noise_do_not_change_a_unique_panel(self):
        data = bytearray(640*480*3)
        panel(data, 20, 20)
        paint(data, (360, 200, 600, 400), (240, 20, 20))
        for x in range(10, 90, 10):
            paint(data, (x, 420, x+1, 421), (240, 240, 240))
        self.assertEqual(read_marker(frame(data)).classification, 'normal')

    def test_complex_speckled_scene_is_bounded_and_unknown(self):
        data = bytearray(640*480*3)
        for index in range(129):
            x, y = (index % 40)*10, (index // 40)*10
            paint(data, (x, y, x+1, y+1), (240, 240, 240))
        self.assertEqual(read_marker(frame(data)).reason, 'scene_too_complex')

    def test_valid_metadata_does_not_supply_color_or_target_identity(self):
        data = bytearray(640*480*3)
        panel(data, color=(240, 20, 20))
        original = frame(data)
        other = replace(original, site='B', target='other', map_xy=SITES['B'])
        self.assertEqual(read_marker(original), read_marker(other))

    def test_invalid_layout_is_an_error_and_reading_is_pixel_free_immutable(self):
        data = bytearray(640*480*3)
        panel(data)
        original = frame(data)
        for changes in ({'width': 320}, {'encoding': 'bgr8'}, {'pixels': b''}, {'pixels': data}):
            with self.assertRaises(ValueError):
                read_marker(replace(original, **changes))
        reading = read_marker(original)
        with self.assertRaises(FrozenInstanceError):
            reading.reason = 'changed'
        from dataclasses import asdict
        self.assertNotIn('pixels', json.dumps(asdict(reading)))


if __name__ == '__main__':
    unittest.main()
