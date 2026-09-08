import os
import tempfile
import unittest
from types import SimpleNamespace

from game.gamemanager import MinigameGameplayMixin
from game.osu_chart import ChartNote, derive_4k_chart, parse_osu_catch, parse_osu_mania_2k, parse_osu_mania_4k
from game.scroll import ScrollTimeline, parse_scroll_points, parse_tempo_points


class ScrollTests(unittest.TestCase):
    def test_inherited_velocity_and_bpm_reset(self):
        points = parse_scroll_points(("0,500", "1000,-50,4,2,1,60,0,0",
                                      "2000,-200,4,2,1,60,0,0", "3000,250"))
        timeline = ScrollTimeline(points, 500)
        self.assertEqual(timeline.rates, (1, 2, .5, 2))
        self.assertEqual([timeline.position(t) for t in range(5)], [0, 1, 3, 3.5, 5.5])

    def test_same_timestamp_sv_keeps_initial_multiplier(self):
        points = parse_scroll_points(("0,-50,4,2,1,60,0,0", "0,500"))
        timeline = ScrollTimeline(points, 500)
        self.assertEqual(timeline.position(-1), -1)
        self.assertEqual(timeline.position(1), 2)

    def test_invalid_velocity_is_ignored_and_extremes_clamped(self):
        points = parse_scroll_points(("0,500", "1000,0,4,2,1,60,0,0", "1000,nan",
                                      "1000,-1,4,2,1,60,0,0", "2000,-10000,4,2,1,60,0,0"))
        self.assertEqual(ScrollTimeline(points, 500).rates, (1, 10, .1))

    def test_constant_tempo_and_missing_timing_preserve_speed(self):
        for points in ((), ((3, 400),)):
            timeline = ScrollTimeline(points)
            for seconds in (-2, 0, 3, 100):
                self.assertAlmostEqual(timeline.position(seconds), seconds)

    def test_changes_are_continuous_and_scale_speed(self):
        timeline = ScrollTimeline(((0, 500), (2, 250), (4, 1000)))
        self.assertEqual(timeline.position(2), 2)
        self.assertEqual(timeline.position(3), 4)
        self.assertEqual(timeline.position(4), 6)
        self.assertEqual(timeline.position(6), 7)
        for boundary in (2, 4):
            self.assertLess(abs(timeline.position(boundary + 1e-8) - timeline.position(boundary - 1e-8)), 1e-7)

    def test_parser_ignores_inherited_and_invalid_points(self):
        points = parse_tempo_points(("2000,250,4,2,1,60,1,0", "0,500", "1000,-50,4,2,1,60,0,0",
                                    "1500,100,4,2,1,60,0,0", "nan,500", "0,inf", "bad", "0,0"))
        self.assertEqual(points, ((0, 500), (2, 250)))

    def test_all_chart_modes_retain_tempo_and_hit_times(self):
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, "audio.mp3"), "wb"):
                pass
            for mode, keys, parser in ((3, 2, parse_osu_mania_2k), (3, 4, parse_osu_mania_4k), (2, 5, parse_osu_catch)):
                path = os.path.join(folder, "chart.osu")
                with open(path, "w") as output:
                    output.write(f"osu file format v14\n[General]\nAudioFilename: audio.mp3\nMode:{mode}\n"
                                 f"[Difficulty]\nCircleSize:{keys}\n[TimingPoints]\n0,500\n2000,250\n"
                                 "2000,-50,4,2,1,60,0,0\n"
                                 "[HitObjects]\n64,192,3000,1,0\n")
                chart = parser(path)
                self.assertEqual(chart.notes[0].time, 3)
                self.assertEqual(chart.scroll_position(3), 6)
                if keys == 2:
                    self.assertEqual(derive_4k_chart(chart).scroll_position(3), 6)

    def test_hold_spanning_change_and_hit_line(self):
        game = MinigameGameplayMixin()
        timeline = ScrollTimeline(((0, 500), (2, 250)))
        game.track = SimpleNamespace(scroll_position=timeline.position)
        note = ChartNote(1.5, 0, 2.5)
        head, tail, _, _ = game._mania_note_positions(note, 1.5, 2, 520, 1560, True)
        self.assertEqual(head, 1560)
        self.assertEqual(tail, 780)
        self.assertEqual(game._scroll_distance(2.5, 2.5), 0)
        self.assertAlmostEqual(game._scroll_distance(3, 2) - game._scroll_distance(3, 2.1), .2)
