import os
import tempfile
import unittest
from types import SimpleNamespace

from game.minigame import (
    EVENT_TRACK_COUNT,
    MAX_SCORE,
    calculate_score,
    combo_after_judgement,
    event_result_destination,
    group_charts_by_song,
    is_clear,
    hold_tick_times,
    load_event_results,
    load_progress,
    save_progress,
)
from game.osu_chart import UnsupportedOsuChartError, discover_osu_mania_2k, parse_osu_mania_2k


class ScoreTests(unittest.TestCase):
    def test_all_perfect_score_is_exact_maximum(self):
        self.assertEqual(calculate_score(["perfect"] * 226, 226), MAX_SCORE)

    def test_score_uses_chart_note_count(self):
        judgements = ["perfect", "good", "bad", "miss"]
        self.assertEqual(calculate_score(judgements, 4), 4275)

    def test_clear_requires_five_percent_health(self):
        self.assertFalse(is_clear(0))
        self.assertFalse(is_clear(4.99))
        self.assertTrue(is_clear(5))

    def test_combo_increments_for_hits_and_resets_for_miss(self):
        combo = 0
        for judgement in ("perfect", "good", "bad"):
            combo = combo_after_judgement(combo, judgement)
        self.assertEqual(combo, 3)
        self.assertEqual(combo_after_judgement(combo, "miss"), 0)

    def test_hold_ticks_follow_quarter_second_interval(self):
        self.assertEqual(hold_tick_times(1.0, 2.0), (1.25, 1.5, 1.75, 2.0))
        self.assertEqual(hold_tick_times(1.0, None), ())


class OsuChartTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.audio_path = os.path.join(self.directory.name, "audio.mp3")
        with open(self.audio_path, "wb") as file:
            file.write(b"audio")

    def tearDown(self):
        self.directory.cleanup()

    def _write_chart(self, circle_size="2"):
        path = os.path.join(self.directory.name, "test.osu")
        with open(path, "w", encoding="utf-8") as file:
            file.write(
                "osu file format v126\n"
                "[General]\nAudioFilename: audio.mp3\nAudioLeadIn: 0\nMode: 3\n"
                "[Metadata]\nTitle:Test Song\nArtist:Test Artist\nCreator:Mapper\nVersion:Test 2K\n"
                f"[Difficulty]\nHPDrainRate:5\nCircleSize:{circle_size}\nOverallDifficulty:8\n"
                "[Events]\nSprite,Foreground,Centre,storyboard.png,320,240\n"
                "256,192,999,1,0,0:0:0:0:\n"
                "[HitObjects]\n64,192,1000,1,0,0:0:0:0:\n"
                "448,192,1500,128,0,2000:0:0:0:0:\n"
            )
        return path

    def test_v126_mania_chart_uses_only_hit_objects(self):
        chart = parse_osu_mania_2k(self._write_chart())
        self.assertEqual(chart.format_version, 126)
        self.assertEqual(chart.title, "Test Song")
        self.assertEqual([(note.time, note.lane) for note in chart.notes], [(1.0, 0), (1.5, 1)])
        self.assertEqual(chart.notes[1].end_time, 2.0)

    def test_non_2k_chart_is_rejected(self):
        with self.assertRaises(UnsupportedOsuChartError):
            parse_osu_mania_2k(self._write_chart(circle_size="6"))

    def test_sample_folder_discovers_only_2k_difficulty(self):
        charts, rejected = discover_osu_mania_2k(os.path.join("game", "charts", "sample-chart"))
        self.assertEqual(len(charts), 1)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(charts[0].difficulty, "Learn 2 Alternate!")


class ProgressTests(unittest.TestCase):
    def test_progress_defaults_and_wraps_to_available_chart_count(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "progress.json")
            self.assertEqual(load_progress(path, 3), 0)
            save_progress(path, 1, 3)
            self.assertEqual(load_progress(path, 3), 1)
            save_progress(path, 3, 3)
            self.assertEqual(load_progress(path, 3), 0)
            with open(path, "w", encoding="utf-8") as file:
                file.write('{"track_index": 4}')
            self.assertEqual(load_progress(path, 3), 0)

    def test_event_progression_has_three_tracks(self):
        self.assertEqual(EVENT_TRACK_COUNT, 3)
        self.assertEqual(event_result_destination(0, True), ("select", 1))
        self.assertEqual(event_result_destination(1, True), ("select", 2))
        self.assertEqual(event_result_destination(2, True), ("total_result", 0))
        self.assertEqual(event_result_destination(1, False), ("ending", 0))

    def test_track_results_are_saved_for_total_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "progress.json")
            scores = [9000, 7200, 8100]
            names = ["First", "Second", "Final"]
            save_progress(path, 2, 3, scores, names)
            self.assertEqual(load_event_results(path, 3), (scores, names))


class SelectionTests(unittest.TestCase):
    def test_charts_are_grouped_by_song_and_sorted_by_difficulty(self):
        charts = (
            SimpleNamespace(artist="Artist", title="Song", level=8, difficulty="Hard", path="hard.osu"),
            SimpleNamespace(artist="Artist", title="Song", level=3, difficulty="Easy", path="easy.osu"),
            SimpleNamespace(artist="Other", title="Second", level=5, difficulty="2K", path="second.osu"),
        )
        groups = group_charts_by_song(charts)
        self.assertEqual(len(groups), 2)
        self.assertEqual([chart.difficulty for chart in groups[0]], ["Easy", "Hard"])


if __name__ == "__main__":
    unittest.main()
