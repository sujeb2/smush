import unittest
from unittest.mock import Mock, patch

from game.AnimationFramework import MinigameAnimationMixin
from game.gameflow import MinigameFlowMixin


class EndingHarness(MinigameFlowMixin, MinigameAnimationMixin):
    pass


class GameEndedTests(unittest.TestCase):
    def make_scene(self):
        game = EndingHarness()
        game.scene = "game_ended"
        game.scene_started = 100.0
        game.game_ended_deadline = 120.0
        game.game_ended_exit_started = None
        game.loading_phase = None
        game.canvas = Mock()
        game.play_card_frames = tuple(range(24))
        game.play_card_frame_shown = 0
        game.play_card_item = "card"
        game.play_card_saved_item = "saved"
        game.play_card_saved_frames = tuple(range(17))
        game.game_ended_time_item = "timer"
        game._update_timer = Mock()
        game._play_sfx = Mock()
        game._start_loading = Mock()
        return game

    def test_message_blinks_without_changing_opacity_then_stays_visible(self):
        game = self.make_scene()
        for elapsed, state in ((0.5, "hidden"), (0.81, "normal"),
                               (1.15, "hidden"), (1.45, "normal"), (4, "normal")):
            game._animate_game_ended(100 + elapsed)
            game.canvas.itemconfigure.assert_called_with("saved", state=state)
        game._start_loading.assert_not_called()

    def test_next_waits_for_card_opening_and_fades_before_game_over(self):
        game = self.make_scene()
        with patch("game.gameflow.time.monotonic", return_value=100.3):
            game.start_game_ended_transition()
        self.assertIsNone(game.game_ended_exit_started)
        with patch("game.gameflow.time.monotonic", return_value=102.0):
            game.start_game_ended_transition()
            game.start_game_ended_transition()
        game._play_sfx.assert_called_once_with("ok.wav")
        game._animate_game_ended(102.3)
        game.canvas.itemconfigure.assert_called_with("saved", state="normal", image=8)
        game._start_loading.assert_not_called()
        game._animate_game_ended(102.7)
        game.canvas.itemconfigure.assert_called_with("saved", state="normal", image=16)
        game._start_loading.assert_called_once_with("ending", game.show_ending)

    def test_timeout_also_fades_before_game_over(self):
        game = self.make_scene()
        with patch("game.gameflow.time.monotonic", return_value=120.0):
            game._animate_game_ended(120.0)
        self.assertEqual(game.game_ended_exit_started, 120.0)
        game._start_loading.assert_not_called()
        game._animate_game_ended(120.7)
        game._start_loading.assert_called_once_with("ending", game.show_ending)


class GameEndedCanvasTests(unittest.TestCase):
    def test_scene_builds_with_real_opengl_canvas_and_hidden_save_message(self):
        from pathlib import Path
        from PIL import Image
        from game.result_scene import MinigameResultSceneMixin
        from game.scenemanager import MinigameSceneMixin
        from moderngl_framework import ModernGLCanvas

        class Scene(MinigameResultSceneMixin, MinigameSceneMixin):
            pass

        game = Scene()
        # Exercise the actual canvas API without requiring a GPU/window.
        game.canvas = ModernGLCanvas.__new__(ModernGLCanvas)
        game.canvas.items = {}
        game.canvas.order = []
        game.canvas.next_item = 1
        base = Path(__file__).resolve().parents[1]
        with Image.open(base / 'game/imgs/generic/playcard.png') as source:
            game.sources = {'playcard': source.convert('RGBA')}
        game.sources.update(logo=Image.new('RGBA', (1, 1)),
                            result_down_button=Image.new('RGBA', (1, 1)))
        game.display_font_path = str(base / 'files/fonts/KERISKEDU_B.ttf')
        game.entry_card_source_frames = {}
        game.game_ended_deadline = 120.0
        game._x = game._y = lambda value: value
        game._photo = lambda source: source
        game._asset_photo = lambda name: game.sources[name]
        game._text = lambda *args: Image.new('RGBA', (1, 1))
        with patch('game.result_scene.time.monotonic', return_value=100.0):
            game._build_game_ended()
        saved = game.canvas.items[game.play_card_saved_item]
        card = game.canvas.items[game.play_card_item]
        self.assertEqual(saved.state, 'hidden')
        self.assertEqual(card.state, 'normal')
        game.canvas.itemconfigure(game.play_card_saved_item, state='normal')
        self.assertEqual(saved.state, 'normal')
