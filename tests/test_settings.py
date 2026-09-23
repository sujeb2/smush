import random
import time
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch


from game.AssetWorker import load_minigame_assets
from game.minigame import MinigameUI
from game.osu_chart import ChartNote, OsuManiaChart
from game.session import GameSession
from game.settings import arrange_chart
from moderngl_framework import ModernGLCanvas


def settings_game():
    game = MinigameUI.__new__(MinigameUI)
    game.running, game.scene = True, "select"
    for name in ("loading_phase", "transition_phase", "select_fade_in_started", "select_morph_in_started",
                 "selection_scroll_started", "settings_phase"):
        setattr(game, name, None)
    game.settings = dict(scroll_speed=1.3, arrangement="NONE", gauge="GROOVE",
                         button_1="forwarded", button_2="forwarded_2", button_3="forwarded_3",
                         button_4="forwarded_4", coin_message="coin")
    game.sources, _, _ = load_minigame_assets(".")
    game.novecento_demibold_font_path = "files/fonts/Novecentosanswide-DemiBold.otf"
    game.display_font_path = "files/fonts/KERISKEDU_B.ttf"
    game.canvas = ModernGLCanvas.__new__(ModernGLCanvas)
    game.canvas.items, game.canvas.order, game.canvas.next_item = {}, [], 1
    game.canvas.create_rectangle(0, 0, 1080, 1920, fill="#bd98e8")
    game.canvas.create_rectangle(100, 900, 300, 1100, fill="white")
    game.select_deadline = time.monotonic() + 30
    game._play_sfx = game._print = Mock()
    game.serial_buffer = ""
    return game


class SettingsTests(unittest.TestCase):
    def test_keyboard_open_navigation_values_and_animated_close(self):
        game = settings_game()
        original = game.canvas.snapshot()
        deadline = game.select_deadline
        game._handle_key(SimpleNamespace(keysym="d"))
        self.assertEqual(game.settings_phase, "opening")
        self.assertNotEqual(game.settings_background.getpixel((99, 1000)), original.getpixel((99, 1000)))
        game._animate_settings(game.settings_animation_started + .45)
        self.assertEqual(game.settings_phase, "open")
        self.assertEqual(game.canvas.items[game.settings_card_item].scale_y, 1.0)
        game._handle_key(SimpleNamespace(keysym="j"))
        self.assertEqual(game.settings["scroll_speed"], 1.4)
        game._handle_key(SimpleNamespace(keysym="d"))
        start = game.settings_cursor_started
        self.assertEqual(game._settings_cursor_y(start), 402)
        self.assertTrue(402 < game._settings_cursor_y(start + .09) < 517)
        game._handle_key(SimpleNamespace(keysym="j"))
        self.assertEqual(game.settings["arrangement"], "RANDOM")
        game._handle_key(SimpleNamespace(keysym="j"))
        self.assertEqual(game.settings["arrangement"], "MIRROR")
        game._handle_key(SimpleNamespace(keysym="d"))
        game._handle_key(SimpleNamespace(keysym="j"))
        self.assertEqual(game.settings["gauge"], "HARD")
        game._handle_key(SimpleNamespace(keysym="k"))
        start = game.settings_animation_started
        game._animate_settings(start + .15)
        self.assertTrue(0 < game.canvas.items[game.settings_card_item].scale_y < 1)
        game._animate_settings(start + .45)
        self.assertIsNone(game.settings_phase)
        self.assertFalse(game.canvas._matching("settings"))
        self.assertEqual(game.select_deadline, deadline)

    def test_animation_reuses_textures_and_keeps_highlight_below_text(self):
        game = settings_game()
        game._open_settings()
        card = game.settings_card
        cursor = game.canvas.items[game.settings_cursor_item].image
        start = game.settings_animation_started
        scales = []
        for elapsed in (0, .07, .14, .21, .28, .35, .42):
            game._animate_settings(start + elapsed)
            scales.append(game.canvas.items[game.settings_card_item].scale_y)
            self.assertIs(game.canvas.items[game.settings_card_item].image, card)
            self.assertIs(game.canvas.items[game.settings_cursor_item].image, cursor)
            self.assertLess(game.canvas.order.index(game.settings_cursor_item),
                            game.canvas.order.index(game.settings_card_item))
        self.assertEqual(scales, sorted(scales))
        self.assertAlmostEqual(scales[0], 0)
        self.assertAlmostEqual(scales[-1], 1)
        self.assertLess(scales[1] - scales[0], scales[3] - scales[2])
        game._animate_settings(start + .45)
        game._press_selection_key(0)
        game._animate_settings(game.settings_cursor_started + .09)
        self.assertIs(game.settings_card, card)

    def test_timer_runs_above_overlay_and_expires_in_every_animation_phase(self):
        for phase in ("opening", "open", "closing"):
            with self.subTest(phase=phase):
                game = settings_game()
                game.select_time_item = game.canvas.create_image(970, 780, tags=("select_time",))
                label = game.canvas.create_image(970, 725, tags=("select_time",))
                game._open_settings()
                game.settings_phase = phase
                game.settings_animation_started = 100.0
                game.select_deadline = 101.0
                game.unrecoverable_error = False
                game._poll_events = game._animate_common = Mock()
                game._update_timer = Mock()
                game.root = Mock()
                game._build_scene = Mock()
                game.track = SimpleNamespace(path="test.osu")
                with patch("game.AnimationFramework.time.monotonic", return_value=100.1):
                    game._animate()
                game._update_timer.assert_called_with(game.select_time_item, 1, "select_time_shown")
                self.assertEqual(game.canvas.order[-2:], [game.select_time_item, label])
                self.assertEqual(game.select_deadline, 101.0)
                game.settings_animation_started = 101.0
                with patch("game.AnimationFramework.time.monotonic", return_value=101.1):
                    game._animate()
                game._update_timer.assert_called_with(game.select_time_item, 0, "select_time_shown")
                self.assertEqual(game.scene, "next")
                self.assertIsNone(game.settings_phase)
                self.assertFalse(game.canvas._matching("settings"))

    def test_serial_keys_and_side_buttons_are_separate(self):
        game = settings_game()
        game._cycle_selection = Mock()
        game._confirm_song = Mock()
        game.selection_phase = "song"
        game.entry_title_fade_started = game.title_entry_morph_started = game.mode_morph_in_started = None
        game._consume_serial("BTN1\nBTN2\nForwarded\n")
        game._cycle_selection.assert_called_once()
        game._confirm_song.assert_called_once()
        self.assertEqual(game.settings_phase, "opening")
        game._animate_settings(game.settings_animation_started + .45)
        game._consume_serial("BTN1\nBTN2\nForwarded_2\nForwarded_3\nForwarded_4\n")
        game._cycle_selection.assert_called_once()
        game._confirm_song.assert_called_once()
        self.assertAlmostEqual(game.settings["scroll_speed"], 1.3)
        self.assertEqual(game.settings_phase, "closing")

    def test_scroll_limits_and_opening_input_lock(self):
        game = settings_game()
        game._press_selection_key(0)
        game._press_selection_key(3)
        self.assertEqual(game.settings_phase, "opening")
        game._animate_settings(game.settings_animation_started + .45)
        for _ in range(40):
            game._press_selection_key(1)
        self.assertEqual(game.settings["scroll_speed"], .5)
        for _ in range(40):
            game._press_selection_key(2)
        self.assertEqual(game.settings["scroll_speed"], 3)

    def test_hard_latches_failure_groove_recovers_and_extra_ignores_health(self):
        for mode in ("4k", "catch"):
            for gauge in ("GROOVE", "HARD"):
                session = GameSession.for_mode(mode)
                session.gauge, session.health = gauge, 1
                if mode == "catch":
                    session.resolve_catch(0, False, 2)
                    session.resolve_catch(1, True, 2)
                else:
                    session.resolve_note(0, ChartNote(0, 0), "miss", 2, 0)
                    session.resolve_note(1, ChartNote(1, 0), "perfect", 2, 1)
                self.assertEqual(session.failed, gauge == "HARD")
                self.assertEqual(session.health > 0, gauge == "GROOVE")
        session = GameSession(health_enabled=False, gauge="HARD", health=1)
        session.resolve_note(0, ChartNote(0, 0), "miss", 1, 0)
        self.assertFalse(session.failed)
        self.assertEqual(session.health, 1)

    def test_arrangements_preserve_chords_holds_and_source_chart(self):
        chart = OsuManiaChart("test", ".", 14, "Test", "Artist", "Mapper", "Hard", 5, 5,
                              "audio", 0, tuple(ChartNote(1, lane, 3, lane * 128) for lane in range(4)),
                              circle_size=4)
        mirror = arrange_chart(chart, "MIRROR")
        self.assertEqual([n.lane for n in mirror.notes], [3, 2, 1, 0])
        shuffled = arrange_chart(chart, "RANDOM", random.Random(12))
        self.assertEqual({n.lane for n in shuffled.notes}, {0, 1, 2, 3})
        self.assertTrue(all(n.time == 1 and n.end_time == 3 for n in shuffled.notes))
        self.assertEqual([n.lane for n in chart.notes], [0, 1, 2, 3])
        extra = replace(chart, circle_size=6, notes=tuple(ChartNote(1, lane) for lane in (4, 0, 1, 2, 3, 5)))
        self.assertEqual([n.lane for n in arrange_chart(extra, "MIRROR").notes], [5, 3, 2, 1, 0, 4])
        catch = replace(chart, mode=2)
        self.assertEqual([n.x for n in arrange_chart(catch, "MIRROR").notes], [512, 384, 256, 128])
        self.assertEqual({n.x for n in arrange_chart(catch, "RANDOM").notes}, {0, 128, 256, 384})
