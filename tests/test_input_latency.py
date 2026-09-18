import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from game.minigame import MinigameUI
from moderngl_framework import PygameRoot
from serial_arduino import SerialIO


class BufferedPort:
    is_open = True

    def __init__(self, data):
        self.data = data

    @property
    def in_waiting(self):
        return len(self.data)

    def read(self, size):
        data, self.data = self.data[:size], self.data[size:]
        return data


class InputLatencyTests(unittest.TestCase):
    def test_serial_press_reaches_game_before_same_frame_update_and_render(self):
        game = MinigameUI.__new__(MinigameUI)
        game.running, game.unrecoverable_error = True, False
        game.serial_buffer = ""
        game.serial_buffer_updated_at = 0
        game.settings = {"button_1": "forwarded", "button_2": "forwarded_2",
                         "button_3": "forwarded_3", "button_4": "forwarded_4",
                         "coin_message": "coin"}
        game.serial = SerialIO.__new__(SerialIO)
        game.serial.ser = BufferedPort(b"Forwarded\r\nForwarded_2\r\n")
        events = []
        game.press_button = lambda lane: events.append(("press", lane))
        game.canvas = SimpleNamespace(render=lambda: events.append("render"))
        game.fps_counter = SimpleNamespace(update=lambda: False)
        game._shutdown_display = Mock()
        pygame = Mock()
        pygame.event.get.return_value = []
        pygame.time.Clock.return_value.tick.side_effect = lambda _: setattr(game, "running", False)
        root = game.root = PygameRoot(game, pygame)
        root.after(0, lambda: events.append("update"))
        root.mainloop()
        self.assertEqual(events, [("press", 0), ("press", 1), "update", "render"])
        self.assertEqual(root.jobs, [])  # No second serial polling timer.
        game._shutdown_display.assert_called_once()

    def test_error_screen_does_not_process_input(self):
        game = MinigameUI.__new__(MinigameUI)
        game.running, game.unrecoverable_error = True, True
        game.serial = Mock()
        game.poll_input()
        game.serial.read.assert_not_called()

    def test_legacy_scene_properties_share_the_extracted_session(self):
        game = MinigameUI.__new__(MinigameUI)
        game.score = 123
        self.assertEqual(game.gameplay.score, 123)
        game.gameplay.health = 70
        self.assertEqual(game.health, 70)
        self.assertIs(game.resolved_notes, game.gameplay.resolved_notes)
