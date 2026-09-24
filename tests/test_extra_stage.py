import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from game.gameflow import MinigameFlowMixin
from game.result_scene import MinigameResultSceneMixin
from game.osu_chart import discover_osu_supported
from game.persistence import load_event_ranks, save_progress


class ExtraStageTests(unittest.TestCase):
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
                               extra_challenge_started=None, extra_challenge_offset=1120,
                               scale=1, canvas=Mock(), _play_sfx=Mock())
        for now in (10, 10.25, 10.5, 11):
            MinigameResultSceneMixin._animate_extra_challenge_prompt(game, now)
        game._play_sfx.assert_called_once_with("information.wav")
        self.assertEqual(game.extra_challenge_offset, 0)
        self.assertEqual(sum(call.args[2] for call in game.canvas.move.call_args_list), -1120)

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

    def test_prompt_uses_information_asset_at_view_center(self):
        game = SimpleNamespace(extra_challenge_offset=0, _image=Mock(), _text_photo=Mock(),
                               display_font_path="font", scene_photos=[], canvas=Mock(),
                               _x=lambda x: x, _y=lambda y: y)
        MinigameResultSceneMixin._build_extra_challenge_prompt(game)
        game._image.assert_called_once_with("information", 540, 960, tags=("extra_challenge",))
        from game.AssetWorker import IMAGE_PATHS
        self.assertEqual(IMAGE_PATHS["information"], ("generic", "information.png"))

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
