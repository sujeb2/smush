import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from game.AssetWorker import load_minigame_assets
from game.led import defaults
from game.minigame import MinigameUI
from game.persistence import load_seen_tutorials, save_progress, save_seen_tutorials
from moderngl_framework import ModernGLCanvas


class HowToPlayTests(unittest.TestCase):
    def game(self, progress_path):
        game = MinigameUI.__new__(MinigameUI)
        game.running = True
        game.game_mode = "4k"
        game.extra_stage_active = False
        game.seen_tutorials = load_seen_tutorials(progress_path)
        game.progress_path = progress_path
        game.settings = {"gauge": "GROOVE"}
        game.track = SimpleNamespace(audio_lead_in=0, audio_path="test.mp3", path="test.osu")
        game.audio = Mock()
        game.root = Mock()
        game.root.after.return_value = "audio_job"
        game.canvas = Mock()
        game._prepare_game_media = Mock()
        game._build_scene = Mock()
        game._print = Mock()
        game.transition_phase = game.loading_phase = None
        game.entry_title_fade_started = game.title_entry_morph_started = game.mode_morph_in_started = None
        game._x = game._y = lambda value: value
        return game

    def test_first_play_waits_for_input_then_remembers_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "progress.json")
            save_progress(path, 1, 3, [100, 0, 0])
            game = self.game(path)
            game._open_gameplay_scene("game", 2.0, 0.0)
            self.assertEqual(game.how_to_play_mode, "4k")
            self.assertIsNone(game.game_started)
            self.assertIsNone(game.game_audio_job)
            self.assertEqual(game._game_elapsed(), 0.0)
            game.root.after.assert_not_called()
            game._handle_key(SimpleNamespace(keysym="d"))
            self.assertIsNone(game.how_to_play_mode)
            game.canvas.delete.assert_called_once_with("how_to_play")
            game.root.after.assert_called_once_with(2000, game._start_chart_audio)
            self.assertIn("4k", load_seen_tutorials(path))
            with open(path, encoding="utf-8") as file:
                self.assertEqual(json.load(file)["track_index"], 1)
            game.root.reset_mock()
            game._open_gameplay_scene("game", 2.0, 0.0)
            self.assertIsNone(game.how_to_play_mode)
            game.root.after.assert_called_once_with(2000, game._start_chart_audio)

    def test_extra_and_catch_have_separate_first_play_guides(self):
        with tempfile.TemporaryDirectory() as directory:
            game = self.game(os.path.join(directory, "progress.json"))
            game.seen_tutorials.add("4k")
            game.extra_stage_active = True
            game._open_gameplay_scene("game", 2.0, 0.0)
            self.assertEqual(game.how_to_play_mode, "extra")
            game.press_button(5)
            self.assertIn("extra", game.seen_tutorials)
            game.game_mode = "catch"
            game.extra_stage_active = False
            game._open_gameplay_scene("game", 2.0, 0.0)
            self.assertEqual(game.how_to_play_mode, "catch")
            game.press_button(0)
            self.assertEqual(load_seen_tutorials(game.progress_path), {"4k", "extra", "catch"})

    def test_fifteen_second_timeout_pauses_game_and_starts_chart_once(self):
        with tempfile.TemporaryDirectory() as directory:
            game = self.game(os.path.join(directory, "progress.json"))
            with patch("game.gameflow.time.monotonic", return_value=100.0):
                game._open_gameplay_scene("game", 2.0, 0.0)
            self.assertEqual(game.how_to_play_deadline, 115.0)
            game.unrecoverable_error = False
            game._poll_events = game._animate_common = Mock()
            game._animate_game_media = game._update_game_frame = Mock()
            with patch("game.AnimationFramework.time.monotonic", return_value=114.99):
                game._animate()
            game._update_game_frame.assert_not_called()
            game.root.after.assert_called_once_with(16, game._animate)
            game.root.reset_mock()
            with patch("game.AnimationFramework.time.monotonic", return_value=115.0):
                game._animate()
            self.assertIsNone(game.how_to_play_mode)
            self.assertIn("4k", load_seen_tutorials(game.progress_path))
            game.root.after.assert_any_call(2000, game._start_chart_audio)
            game._update_game_frame.assert_not_called()

    def test_led_tick_uses_frozen_chart_time_while_guide_is_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            game = self.game(os.path.join(directory, "progress.json"))
            game.track.tempo_points = ()
            game._open_gameplay_scene("game", 2.0, 0.0)
            game.unrecoverable_error = False
            game.led_data = defaults()
            game.led_data["neopixel"]["enabled"] = True
            game.led_reload_at = float("inf")
            game.led_scene_key = None
            game.led_started = 0.0
            game.led_preview_visible = False
            game.led_preview_state = None
            game.demo_mode = True
            game.serial = None
            game._tick_leds()
            game.root.after.assert_called_with(50, game._tick_leds)
            self.assertEqual(game._game_elapsed(), 0.0)

    def test_demonstration_skips_guide_and_overlay_uses_reference_location(self):
        with tempfile.TemporaryDirectory() as directory:
            game = self.game(os.path.join(directory, "progress.json"))
            game._open_gameplay_scene("demonstration", 1.0, 0.0)
            self.assertIsNone(game.how_to_play_mode)
            self.assertEqual(game.seen_tutorials, set())
            game.sources, _, _ = load_minigame_assets(".")
            game.how_to_play_mode = "4k"
            game.scale = 1.0
            game.photo_cache = {}
            game.canvas = ModernGLCanvas.__new__(ModernGLCanvas)
            game.canvas.items, game.canvas.order, game.canvas.next_item = {}, [], 1
            game._build_how_to_play()
            item = game.canvas.items[game.canvas.order[-1]]
            self.assertEqual(item.coords, [0, 690])
            self.assertEqual(item.image.size, (1080, 355))
            self.assertIn("how_to_play", item.tags)

    def test_seen_guides_survive_event_progress_saves(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "progress.json")
            save_seen_tutorials(path, {"4k", "catch"})
            save_progress(path, 2, 3, [100, 200, 300])
            self.assertEqual(load_seen_tutorials(path), {"4k", "catch"})


if __name__ == "__main__":
    unittest.main()
