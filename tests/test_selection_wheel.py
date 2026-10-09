import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from game.AssetWorker import load_minigame_assets
from game.minigame import MinigameUI
from game.rules import group_charts_by_song
from game.scenemanager import (
    SELECTION_WHEEL_SECONDS,
    _SELECTION_WHEEL_POINTS,
    _selection_wheel_opacity,
    _selection_wheel_point,
)
from game.state import MinigameStateMixin
from moderngl_framework import ModernGLCanvas, _CanvasItem


def chart(title, level=5):
    return SimpleNamespace(
        title=title, artist="ARTIST", difficulty="NORMAL", level=level, path=f"{title}.osu",
        video_path=None, background_path=None, preview_time=-1, audio_path=f"{title}.mp3",
        has_scroll_speed_changes=False,
    )


def select_game(song_count=6):
    game = MinigameUI.__new__(MinigameUI)
    game.base, game.scale, game.offset_x, game.offset_y = ".", 1.0, 0.0, 0.0
    game.running, game.unrecoverable_error = True, False
    game.settings = {"mode": "EVENT", "select_seconds": 60}
    game.sources, _, _ = load_minigame_assets(".")
    game.novecento_demibold_font_path = "files/fonts/Novecentosanswide-DemiBold.otf"
    game.display_font_path = "files/fonts/KERISKEDU_B.ttf"
    game.canvas = ModernGLCanvas.__new__(ModernGLCanvas)
    game.canvas.items, game.canvas.order, game.canvas.next_item = {}, [], 1
    game.charts = tuple(chart(f"SONG {index}") for index in range(song_count))
    game.song_groups = group_charts_by_song(game.charts)
    game.track_index, game.coins_per_credit, game.coin_count, game.credit_count = 0, 0, 0, 0
    game.two_player = False
    MinigameStateMixin._initialize_state(game)
    game.scene, game.selection_phase = "select", "song"
    game.select_deadline = time.monotonic() + 60
    game._play_sfx = game._print = Mock()
    game._schedule_select_preview = Mock()
    game._prepare_select_media = Mock()
    game._build_scene()
    return game


def preview_labels(game):
    """(x, y, opacity, squash) of each neighbour label, in stacking order."""
    return [
        (*map(round, game.canvas.items[label].coords), game.canvas.items[label].opacity,
         game.canvas.items[label].scale_y)
        for _, label, _, _ in game.selection_preview_items
    ]


class SelectionWheelPathTests(unittest.TestCase):
    def test_path_rests_exactly_on_each_slot(self):
        for slot, point in _SELECTION_WHEEL_POINTS.items():
            self.assertEqual(tuple(round(value, 6) for value in _selection_wheel_point(slot)), point)

    def test_cards_fade_into_the_centre_card_and_past_the_outer_slots(self):
        self.assertEqual(_selection_wheel_opacity(0), 0)
        self.assertEqual([_selection_wheel_opacity(slot) for slot in (-2, -1, 1, 2)], [1, 1, 1, 1])
        self.assertEqual(_selection_wheel_opacity(3), 0)
        self.assertAlmostEqual(_selection_wheel_opacity(2.5), 0.5)
        self.assertAlmostEqual(_selection_wheel_opacity(-0.5), 0.5)


class GroupFlipRendererTests(unittest.TestCase):
    def test_items_squash_toward_a_shared_pivot(self):
        canvas = ModernGLCanvas.__new__(ModernGLCanvas)
        image = SimpleNamespace(width=100, height=40)
        top = _CanvasItem("image", [0, 100], image=image, anchor="nw", scale_y=0.5, pivot_y=200)
        bottom = _CanvasItem("rectangle", [0, 260, 100, 300], scale_y=0.5, pivot_y=200)
        self.assertEqual(canvas._item_box(top), (0, 150.0, 100, 20.0))
        self.assertEqual(canvas._item_box(bottom), (0, 230.0, 100, 20.0))

    def test_without_pivot_scale_y_keeps_its_own_anchor(self):
        canvas = ModernGLCanvas.__new__(ModernGLCanvas)
        image = SimpleNamespace(width=100, height=40)
        item = _CanvasItem("image", [50, 100], image=image, anchor="center", scale_y=0.5)
        self.assertEqual(canvas._item_box(item), (0, 90.0, 100, 20.0))

    def test_opacity_fades_the_tint(self):
        self.assertEqual(ModernGLCanvas._faded((1, 1, 1, 1), 0.25), (1, 1, 1, 0.25))


class SelectionWheelTurnTests(unittest.TestCase):
    def test_resting_layout_keeps_the_original_neighbour_slots(self):
        game = select_game()
        self.assertEqual(
            [(round(game.canvas.items[card].coords[0]), round(game.canvas.items[card].coords[1]))
             for card, _, _, _ in game.selection_preview_items],
            [(850, 1497), (850, 1000), (950, 1660), (950, 925)],
        )

    def test_turn_flips_the_card_and_rotates_neighbours_then_settles(self):
        game = select_game()
        resting = preview_labels(game)
        game._cycle_selection()
        started = game.selection_scroll_started
        self.assertIsNotNone(started)
        game._animate_selection_scroll(started + SELECTION_WHEEL_SECONDS * 0.3)
        old_card = [game.canvas.items[item] for item in game.canvas._matching("select_card_old")]
        self.assertTrue(old_card and all(0 < item.scale_y < 1 and item.opacity < 1 for item in old_card))
        self.assertTrue(all(squash < 1 for *_, squash in preview_labels(game)))
        game._animate_selection_scroll(started + SELECTION_WHEEL_SECONDS * 0.7)
        self.assertFalse(game.canvas._matching("select_card_old"))
        self.assertTrue(game.canvas._matching("select_card"))
        game._animate_selection_scroll(started + SELECTION_WHEEL_SECONDS)
        self.assertIsNone(game.selection_scroll_started)
        settled = [game.canvas.items[item] for item in game.canvas._matching("select_card")]
        self.assertTrue(all(item.scale_y == 1.0 and item.opacity == 1.0 and item.pivot_y is None
                            for item in settled))
        self.assertEqual(preview_labels(game), resting)
        self.assertEqual(game.song_index, 1)

    def test_quick_second_press_finishes_the_turn_instead_of_being_dropped(self):
        game = select_game()
        for name in ("transition_phase", "loading_phase", "entry_title_fade_started",
                     "title_entry_morph_started", "mode_morph_in_started", "select_fade_in_started",
                     "select_morph_in_started"):
            setattr(game, name, None)
        game.press_button(0)
        game.press_button(0)
        self.assertEqual(game.song_index, 2)
        game._finish_selection_wheel()
        self.assertFalse(game.canvas._matching("select_card_old"))

    def test_speed_change_warning_stays_above_neighbour_cards_after_a_turn(self):
        game = select_game()
        game.charts[1].has_scroll_speed_changes = True
        game._cycle_selection()
        game._finish_selection_wheel()
        self.assertIsNotNone(game.scroll_speed_warning_item)
        self.assertEqual(game.canvas.order[-1], game.scroll_speed_warning_item)

    def test_previous_song_name_sits_below_the_card_that_overlaps_it(self):
        game = select_game()
        labels = {(x, round(y)) for x, y, _, _ in preview_labels(game)}
        half_height = game.sources["previous"].height / 2
        above_card_bottom = _SELECTION_WHEEL_POINTS[-2][1] + half_height
        previous_card_bottom = _SELECTION_WHEEL_POINTS[-1][1] + half_height
        previous_label = next(y for x, y in labels if x == 850 and y < 1248)
        self.assertGreater(previous_label, above_card_bottom)
        self.assertLess(previous_label, previous_card_bottom)
        self.assertIn((950, 925), labels)

    def test_short_lists_without_an_overlapping_card_keep_names_centred(self):
        game = select_game(song_count=4)
        self.assertIn((850, 1000), {(x, y) for x, y, _, _ in preview_labels(game)})

    def test_two_song_list_still_turns_without_duplicate_cards(self):
        game = select_game(song_count=2)
        game._cycle_selection()
        labels = [label for _, label, _, _ in game.selection_preview_items]
        self.assertEqual(len(labels), 2)
        game._finish_selection_wheel()
        self.assertEqual(len(game.selection_preview_items), 1)


if __name__ == "__main__":
    unittest.main()
