import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image

from game.gameflow import MinigameFlowMixin
from game.mediaplayer import MinigameMediaMixin
from game.result_scene import EXTRA_CHALLENGE_SLIDE, MinigameResultSceneMixin
from game.osu_chart import discover_osu_supported
from game.persistence import load_event_ranks, save_progress
from game.scenemanager import _extra_stage_levels, _is_japanese_title


class ExtraStageTests(unittest.TestCase):
    def test_extra_selection_caps_timer_and_starts_with_difficulties(self):
        for configured, expected in ((60, 30), (20, 20)):
            game = self.game(extra_stage_active=True, settings={"select_seconds": configured},
                             song_groups=[[Mock()]], audio=Mock(), root=Mock(),
                             _build_scene=Mock(), _schedule_select_preview=Mock(),
                             _print=Mock(), _broadcast_selection=Mock())
            with patch("game.gameflow.time.monotonic", return_value=100):
                game.show_select()
            self.assertEqual(game.selection_phase, "difficulty")
            self.assertEqual(game.select_deadline, 100 + expected)

    def test_extra_confirmation_fades_directly_to_game(self):
        for remote in (False, True):
            game = self.game(extra_stage_active=True, scene="select", loading_phase=None,
                             applying_shared_selection=remote, settings_phase="open",
                             _broadcast_selection=Mock(return_value=True), audio=Mock(),
                             _clear_settings_overlay=Mock(), _start_loading=Mock())
            game.show_next()
            self.assertEqual(game.scene, "select")
            game._start_loading.assert_called_once_with("game", game._start_game_scene)
            game._clear_settings_overlay.assert_called_once()
            game.audio.stop.assert_called_once_with(480)
            if not remote:
                game._broadcast_selection.assert_called_once_with("next")

    def test_extra_stage_title_font_selection(self):
        self.assertTrue(_is_japanese_title("夜に駆ける"))
        self.assertTrue(_is_japanese_title("カタカナ"))
        self.assertFalse(_is_japanese_title("AA"))

    def test_extra_stage_level_slots(self):
        charts = [SimpleNamespace(difficulty=name, level=level) for name, level in (
            ("HARD", 12), ("EASY", 4), ("NORMAL", 8),
        )]
        self.assertEqual([chart.level for chart in _extra_stage_levels(charts)], [4, 8, 12])
        self.assertEqual(
            [chart.level if chart else None for chart in _extra_stage_levels(
                [SimpleNamespace(difficulty="EXTRA", level=15)]
            )],
            [None, None, 15],
        )

    def test_extra_stage_media_uses_full_background(self):
        media = MinigameMediaMixin()
        media.scene = "select"
        media.extra_stage_active = True
        source = Image.new("RGB", (320, 240), "red")
        self.assertEqual(media._selection_media_image(source, True).size, (1080, 1920))
        media.extra_stage_active = False
        self.assertEqual(media._selection_media_image(source, True).size, (170, 150))

    def test_extra_stage_difficulty_keeps_template(self):
        chart = SimpleNamespace(title="AA")
        game = self.game(scene="select", song_groups=[[chart]], song_index=0,
                         selection_heading_item=None, canvas=Mock(), _play_sfx=Mock(),
                         _refresh_selection_list=Mock(), _print=Mock(), _broadcast_selection=Mock())
        game.extra_stage_active = True
        game._confirm_song()
        self.assertEqual(game.selection_phase, "difficulty")
        game.canvas.delete.assert_not_called()
        game._refresh_selection_list.assert_called_once()

    def game(self, **values):
        game = MinigameFlowMixin()
        game.track_ranks = ["S", "X", "S"]
        game.extra_stage_active = False
        game.extra_charts_by_mode = {"2k": (), "4k": (Mock(),), "catch": ()}
        game.__dict__.update(values)
        return game

    def test_requires_three_a_or_higher_ranks(self):
        for ranks, eligible in ((["A", "A", "A"], True), (["S", "A", "X"], True),
                                (["S", "B", "X"], False), (["S", "S", ""], False),
                                (["S", "S"], False)):
            with self.subTest(ranks=ranks):
                self.assertEqual(self.game(track_ranks=ranks)._extra_challenge_available(), eligible)
        self.assertFalse(self.game(extra_stage_active=True)._extra_challenge_available())
        self.assertFalse(self.game(extra_charts_by_mode={})._extra_challenge_available())

    def test_rank_persistence_and_legacy_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "progress.json")
            save_progress(path, 1, 3, [100, 0, 0], ["song", "", ""])
            self.assertEqual(load_event_ranks(path, 3), ["", "", ""])
            save_progress(path, 2, 3, track_ranks=["S", "X", ""])
            self.assertEqual(load_event_ranks(path, 3), ["S", "X", ""])
            save_progress(path, 0, 3, track_ranks=["", "", ""])
            self.assertEqual(load_event_ranks(path, 3), ["", "", ""])

    def test_demo_requires_two_a_or_higher_ranks(self):
        for ranks, eligible in ((["A", "A", ""], True), (["X", "S", "B"], True),
                                (["S", "B", "S"], False), (["S", "", ""], False)):
            with self.subTest(ranks=ranks):
                game = self.game(demo_mode=True, track_ranks=ranks)
                self.assertEqual(game._extra_challenge_available(), eligible)
        self.assertFalse(self.game(demo_mode=True, extra_stage_active=True)._extra_challenge_available())

    def test_demo_offers_extra_on_second_result(self):
        game = self.game(demo_mode=True, scene="game", game_mode="4k", track_index=1,
                         track=SimpleNamespace(notes=[1], title="second"), resolved_notes={0},
                         audio=Mock(), judgements=["perfect"], counts={"perfect": 1},
                         track_scores=[1, 0, 0], track_names=["first", "", ""],
                         track_ranks=["S", "", ""], health=100,
                         settings={"result_seconds": 20}, _build_scene=Mock(), root=Mock(), _print=Mock())
        game.show_result()
        self.assertTrue(game.extra_challenge_prompt)
        self.assertEqual(game.track_ranks, ["S", "X", ""])

    def test_extra_folder_is_separate_from_normal_selection(self):
        normal, _ = discover_osu_supported("game/charts", excluded_folders=("extrastage",))
        extra, rejected = discover_osu_supported("game/charts/extrastage", allow_extra=True)
        self.assertFalse(rejected)
        self.assertTrue(extra["4k"])
        for charts in normal.values():
            self.assertTrue(all(os.path.basename(chart.folder) != "extrastage" for chart in charts))
        game = self.game(extra_charts_by_mode=extra, game_mode="2k", show_select=Mock())
        game._show_extra_select()
        self.assertTrue(game.extra_stage_active)
        self.assertEqual(game.game_mode, "4k")
        self.assertEqual(len(game.song_groups), 1)
        self.assertTrue(all(os.path.basename(chart.folder) == "extrastage" for chart in game.charts))
        self.assertEqual(game._track_key(), "EXTRA")
        game.show_select.assert_called_once()

    def test_accept_fades_before_changing_selection(self):
        game = self.game(scene="result", loading_phase=None, extra_challenge_prompt=True,
                         extra_challenge_started=1, result_unlock_at=0,
                         _stop_result_rank_audio=Mock(), progress_path="unused",
                         track_scores=[1, 2, 3], track_names=["a", "b", "c"],
                         _play_sfx=Mock(), audio=Mock(), _start_loading=Mock())
        with patch("game.gameflow.save_progress") as save:
            game._accept_extra_challenge()
        save.assert_called_once_with("unused", 0, 3, [1, 2, 3], ["a", "b", "c"], ["S", "X", "S"])
        game._start_loading.assert_called_once_with("select", game._show_extra_select)
        game.audio.stop.assert_called_once_with(480)
        self.assertFalse(game.extra_stage_active)
        game._accept_extra_challenge()
        self.assertEqual(game._start_loading.call_count, 1)

    def test_cancel_and_timeout_end_normally(self):
        game = self.game(scene="total_result", loading_phase=None, total_result_count_channel=None,
                         _play_sfx=Mock(), _start_loading=Mock())
        game.start_total_result_transition()
        game._start_loading.assert_called_once_with("game_ended", game.show_game_ended)

    def test_extra_result_ends_without_advancing_regular_stages(self):
        game = self.game(scene="result", loading_phase=None, result_unlock_at=0,
                         extra_stage_active=True, track_index=0, track_scores=[1, 2, 3],
                         _stop_result_rank_audio=Mock(), _play_sfx=Mock(), _start_loading=Mock())
        game.start_result_transition()
        game._start_loading.assert_called_once_with("game_ended", game.show_game_ended)
        self.assertEqual(game.track_index, 0)
        self.assertEqual(game.track_scores, [1, 2, 3])

    def test_prompt_slides_up_and_plays_information_once(self):
        game = SimpleNamespace(extra_challenge_prompt=True, result_unlock_at=9,
                               extra_challenge_started=None, extra_challenge_offset=EXTRA_CHALLENGE_SLIDE,
                               scale=1, canvas=Mock(), _play_sfx=Mock())
        for now in (10, 10.25, 10.5, 11):
            MinigameResultSceneMixin._animate_extra_challenge_prompt(game, now)
        game._play_sfx.assert_called_once_with("information.wav")
        self.assertEqual(game.extra_challenge_offset, 0)
        self.assertEqual(sum(call.args[2] for call in game.canvas.move.call_args_list), -EXTRA_CHALLENGE_SLIDE)
        game.canvas.itemconfigure.assert_any_call("extra_challenge", opacity=1.0)
        game.canvas.itemconfigure.assert_any_call("extra_challenge_dim", opacity=0.55)

    def test_buttons_route_to_accept_and_cancel(self):
        game = self.game(running=True, transition_phase=None, loading_phase=None,
                         entry_title_fade_started=None, title_entry_morph_started=None,
                         mode_morph_in_started=None, scene="result", extra_challenge_prompt=True,
                         _accept_extra_challenge=Mock(), start_result_transition=Mock())
        game.press_button(0)
        game._accept_extra_challenge.assert_called_once()
        game.start_result_transition.assert_not_called()
        game.press_button(1)
        game.start_result_transition.assert_called_once()

    def test_third_result_enables_prompt_and_total_result_does_not(self):
        game = self.game(scene="game", game_mode="4k", track_index=2,
                         track=SimpleNamespace(notes=[1], title="third"), resolved_notes={0},
                         audio=Mock(), judgements=["perfect"], counts={"perfect": 1},
                         track_scores=[1, 2, 0], track_names=["a", "b", ""],
                         health=100, settings={"result_seconds": 20}, _build_scene=Mock(),
                         root=Mock(), _print=Mock())
        game.show_result()
        self.assertEqual(game.scene, "result")
        self.assertTrue(game.extra_challenge_prompt)
        self.assertEqual(game.track_ranks, ["S", "X", "X"])
        game.show_total_result()
        self.assertFalse(game.extra_challenge_prompt)

    def test_prompt_band_starts_hidden_below_view_center_over_a_dim_layer(self):
        band = Mock()
        game = SimpleNamespace(extra_challenge_offset=EXTRA_CHALLENGE_SLIDE, canvas=Mock(),
                               _x=lambda x: x, _y=lambda y: y, _scaled_photo=lambda image: image,
                               _extra_challenge_band_source=lambda: band)
        game.canvas.create_rectangle.return_value = "dim"
        game.canvas.create_image.return_value = "band"
        MinigameResultSceneMixin._build_extra_challenge_prompt(game)
        game.canvas.create_rectangle.assert_called_once_with(
            0, 0, 1080, 1920, fill="#000000", outline="", tags=("extra_challenge_dim",),
        )
        game.canvas.create_image.assert_called_once_with(
            540, 960 + EXTRA_CHALLENGE_SLIDE, image=band, anchor="center", tags=("extra_challenge",),
        )
        game.canvas.itemconfigure.assert_any_call("dim", opacity=0.0)
        game.canvas.itemconfigure.assert_any_call("band", opacity=0.0)

    def test_prompt_band_shows_title_message_and_both_buttons(self):
        game = SimpleNamespace(sources={}, novecento_demibold_font_path="files/fonts/Novecentosanswide-DemiBold.otf",
                               display_font_path="files/fonts/KERISKEDU_B.ttf")
        band = MinigameResultSceneMixin._extra_challenge_band_source(game)
        self.assertEqual(band.size, (1080, 450))
        self.assertIs(MinigameResultSceneMixin._extra_challenge_band_source(game), band)
        # BT1 (sky blue) and BT2 (green) chip centres.
        red, green, blue, _ = band.getpixel((330, 340))
        self.assertTrue(160 <= red <= 215 and green > 225 and blue > 245)
        red, green, blue, _ = band.getpixel((650, 340))
        self.assertTrue(red < 110 and green > 240 and 120 <= blue <= 185)

    def test_cancel_from_third_result_continues_to_total_result(self):
        game = self.game(scene="result", loading_phase=None, result_unlock_at=0,
                         extra_challenge_prompt=True, health=100, track_index=2,
                         track_scores=[1, 2, 3], track_names=["a", "b", "c"], progress_path="unused",
                         _stop_result_rank_audio=Mock(), _play_sfx=Mock(), _start_loading=Mock())
        with patch("game.gameflow.save_progress"):
            game.start_result_transition()
        self.assertFalse(game.extra_challenge_prompt)
        game._start_loading.assert_called_once_with("total_result", game.show_total_result)


if __name__ == "__main__":
    unittest.main()
