import unittest

from animviewer.animations import CATALOG
from animviewer.app import format_time
from animviewer.model import PlaybackController


class CatalogTests(unittest.TestCase):
    def test_catalog_has_unique_names_and_valid_keyframes(self):
        self.assertEqual(len(CATALOG), len({animation.name for animation in CATALOG}))
        self.assertEqual({animation.group for animation in CATALOG}, {"SMUSH UI", "MINIGAME"})
        for animation in CATALOG:
            self.assertGreater(animation.duration, 0)
            self.assertGreater(animation.fps, 0)
            self.assertTrue(animation.keyframes)
            self.assertEqual(tuple(sorted(animation.keyframes, key=lambda item: item.time)), animation.keyframes)
            self.assertTrue(all(0 <= item.time <= animation.duration for item in animation.keyframes))

    def test_last_frame_uses_duration_and_fps(self):
        animation = CATALOG[0]
        self.assertEqual(animation.last_frame, round(animation.duration * animation.fps) - 1)


class PlaybackTests(unittest.TestCase):
    def setUp(self):
        self.player = PlaybackController()
        self.player.select(CATALOG[0])

    def test_play_pause_stop_and_frame_seek(self):
        self.player.play(10.0)
        self.player.update(10.25)
        self.assertEqual(self.player.state, "playing")
        self.assertAlmostEqual(self.player.current_time, .25)
        self.player.pause(10.25)
        self.player.seek_frame(12)
        self.assertEqual(self.player.current_frame, 12)
        self.player.stop()
        self.assertEqual((self.player.state, self.player.current_time, self.player.current_frame), ("stopped", 0.0, 0))

    def test_playback_stops_at_last_frame(self):
        self.player.play(20.0)
        self.player.update(30.0)
        self.assertEqual(self.player.state, "paused")
        self.assertEqual(self.player.current_time, self.player.animation.duration)
        self.assertEqual(self.player.current_frame, self.player.animation.last_frame)

    def test_active_keyframe_tracks_current_time(self):
        self.player.seek(self.player.animation.duration)
        self.assertEqual(self.player.active_keyframe, self.player.animation.keyframes[-1])

    def test_time_format(self):
        self.assertEqual(format_time(0), "0:00.00")
        self.assertEqual(format_time(65.25), "1:05.25")


if __name__ == "__main__":
    unittest.main()
