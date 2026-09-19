import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from game.AnimationFramework import MinigameAnimationMixin
from game.AssetWorker import load_minigame_assets
from game.gameflow import MinigameFlowMixin
from game.gamemanager import MinigameGameplayMixin
from game.osu_chart import ChartNote, discover_osu_supported
from game.scenemanager import MinigameSceneMixin
from game.scenes import MinigameGameSceneMixin
from game.session import GameSession


class Extra4KTests(unittest.TestCase):
    def test_six_lane_charts_are_extra_only_and_preserve_lane_order_and_holds(self):
        with tempfile.TemporaryDirectory() as directory:
            open(os.path.join(directory, "audio.mp3"), "wb").close()
            with open(os.path.join(directory, "test.osu"), "w", encoding="utf-8") as chart:
                chart.write("osu file format v14\n[General]\nMode:3\nAudioFilename:audio.mp3\n"
                            "[Metadata]\nTitle:Extra\nCreator:Test Author\nVersion:Hard\n"
                            "[Difficulty]\nCircleSize:6\n[HitObjects]\n")
                for x in (42, 128, 213, 298, 384, 469):
                    chart.write(f"{x},192,1000,128,0,2000:0:0:0:0:\n")
            normal, rejected = discover_osu_supported(directory)
            self.assertFalse(normal["4k"])
            self.assertEqual(len(rejected), 1)
            extra, rejected = discover_osu_supported(directory, allow_extra=True)
            self.assertFalse(rejected)
            chart = extra["4k"][0]
            self.assertEqual(chart.creator, "Test Author")
            self.assertEqual({note.x: note.lane for note in chart.notes},
                             {42: 4, 128: 0, 213: 1, 298: 2, 384: 3, 469: 5})
            self.assertTrue(all(note.end_time == 2 for note in chart.notes))

    def test_serial_side_buttons_are_separate_from_center_keys_only_during_extra(self):
        game = MinigameAnimationMixin()
        game.settings = dict(button_1="forwarded", button_2="forwarded_2",
                             button_3="forwarded_3", button_4="forwarded_4", coin_message="coin")
        game.serial_buffer = ""
        game.scene, game.game_mode, game.extra_stage_active = "game", "4k", True
        game.press_button = Mock()
        game._consume_serial("BTN1\nForwarded\nForwarded_2\nForwarded_3\nForwarded_4\nBTN2\n")
        self.assertEqual([call.args[0] for call in game.press_button.call_args_list], [4, 0, 1, 2, 3, 5])
        game.press_button.reset_mock()
        game.scene = "select"
        game._consume_serial("BTN1\nBTN2\n")
        self.assertEqual([call.args[0] for call in game.press_button.call_args_list], [0, 1])

    def test_keyboard_has_six_distinct_extra_inputs(self):
        game = MinigameFlowMixin()
        game.scene, game.game_mode, game.extra_stage_active = "game", "4k", True
        game.press_button = Mock()
        for key in "adfjkl":
            game._handle_key(SimpleNamespace(keysym=key))
        self.assertEqual([call.args[0] for call in game.press_button.call_args_list], [4, 0, 1, 2, 3, 5])

    def test_disabled_health_still_records_misses_score_and_hold_combos(self):
        session = GameSession(health_enabled=False)
        for index in range(30):
            session.resolve_note(index, ChartNote(index, 4), "miss", 31, index)
        self.assertEqual(session.health, 100)
        self.assertEqual(session.counts["miss"], 30)
        self.assertEqual(session.combo, 0)
        session.resolve_note(30, ChartNote(30, 5, 31), "perfect", 31, 30)
        session.health = 42
        self.assertTrue(list(session.advance_holds(31)))
        self.assertEqual(session.health, 42)
        self.assertGreater(session.combo, 1)
        self.assertGreater(session.score, 0)

    def test_extra_cannot_finish_early_even_with_zero_health(self):
        game = MinigameGameplayMixin()
        game.scene, game.game_mode = "game", "4k"
        game.game_started, game.game_finishing = 0, False
        game.gameplay = GameSession(health=0, health_enabled=False)
        game.track = SimpleNamespace(notes=(), duration=10)
        game._game_elapsed = Mock(return_value=1)
        game._update_hold_ticks = game._autoplay_mania_notes = Mock()
        game._autoplay_active = Mock(return_value=False)
        game._scroll_lead_time = Mock(return_value=2)
        game.judgement_line_y, game.note_items = 1850, {}
        game.canvas, game.audio, game._start_loading, game.show_result = Mock(), Mock(), Mock(), Mock()
        game._animate_combo = game._animate_health = game._animate_lane_help = game._update_feedback_image = Mock()
        game._update_game_frame(1)
        game._start_loading.assert_not_called()
        game._game_elapsed.return_value = 12
        game._update_game_frame(12)
        game._start_loading.assert_called_once_with("result", game.show_result)

    def test_extra_field_has_smaller_side_notes_and_no_health_widgets(self):
        game = MinigameGameSceneMixin()
        game.game_mode, game.extra_stage_active = "4k", True
        game.track = SimpleNamespace(title="Extra", difficulty="Hard")
        game.score, game.combo = 0, 0
        game.canvas, game._image, game._text_image = Mock(), Mock(), Mock()
        game._x = game._y = lambda value: value
        game._asset_photo = lambda name: name
        game._build_game_media = game._build_header = game._ensure_preloaded_gameplay_photos = Mock()
        game.preloaded_judgement_frames = ()
        game.preloaded_lane_help_frames = {
            name: (name,) for name in ("lane_help_4k_0", "lane_help_4k_1", "lane_help_extra_0", "lane_help_extra_1")
        }
        game._update_health_image = Mock()
        game._build_game()
        self.assertIsNone(game.health_fill_item)
        self.assertFalse(any("health" in call.args[0] for call in game._image.call_args_list))
        self.assertEqual(len(game.lane_help_items), 6)
        sources, _, _ = load_minigame_assets(os.getcwd())
        self.assertLess(sources["note_extra_0"].width, game.lane_width)
        self.assertLess(sources["note_extra_1"].width, game.lane_width)
        self.assertEqual(sources["main_layer_4k_extra"].width, 1080)

    def test_next_places_warning_behind_title_and_creator_below_level(self):
        from PIL import Image
        game = MinigameSceneMixin()
        game.extra_stage_active = True
        game.track = SimpleNamespace(title="Title", difficulty="Hard", level=99, creator="Chart Author")
        game._image, game._text_image, game.canvas = Mock(), Mock(), Mock()
        game._x = game._y = game._photo = lambda value: value
        game.sources = {name: Image.new("RGBA", (2, 2)) for name in ("next_arrow", "next_arrow_left")}
        game._build_next()
        game._image.assert_called_once_with("extra_mode_warning", 540, 1235, tags=("next",))
        self.assertIn((("Chart Author", 26, 540, 1635), {"tags": ("next",)}), game._text_image.call_args_list)
        game.extra_stage_active = False
        game._image.reset_mock()
        game._text_image.reset_mock()
        game._build_next()
        game._image.assert_not_called()
        self.assertNotIn("Chart Author", [call.args[0] for call in game._text_image.call_args_list])


if __name__ == "__main__":
    unittest.main()
