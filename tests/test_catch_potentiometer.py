import unittest
from unittest.mock import Mock, patch

from game.AnimationFramework import MinigameAnimationMixin
from game.gamemanager import MinigameGameplayMixin


class Controller(MinigameAnimationMixin, MinigameGameplayMixin):
    pass


class CatchPotentiometerTests(unittest.TestCase):
    def setUp(self):
        self.game = Controller()
        g = self.game
        g.settings = {"button_1": "forwarded", "button_2": "forwarded_2",
                      "button_3": "forwarded_3", "button_4": "forwarded_4", "coin_message": "coin"}
        g.serial_buffer = ""
        g.press_button = Mock()
        g.scene, g.game_mode = "game", "catch"
        g.debug_autoplay = False
        g.catcher_x, g.catcher_velocity, g.catcher_last_update = 540.0, 0.0, 100.0
        g.catcher_item, g.canvas = 1, Mock()
        g._x = g._y = lambda value: value

    def test_endpoints_and_middle_map_to_existing_catcher_bounds(self):
        g = self.game
        for index, value in enumerate((0, 512, 1023)):
            start = 100 + index
            g.catcher_last_update = start
            with patch("game.gamemanager.time.monotonic", return_value=start):
                g._set_catch_potentiometer(value)
            for frame in range(1, 31):
                g._animate_catcher(start + frame / 60)
            self.assertAlmostEqual(g.catcher_x, 180 + value / 1023 * 720)
            self.assertEqual(g.catcher_velocity, 0)
            g.canvas.coords.assert_called_with(1, g.catcher_x, 1725)

    def test_split_frames_and_buttons_share_serial_stream(self):
        g = self.game
        for chunk in ("BT", "N1\nPO", "T:05", "12;\r\nFor", "warded_", "4\nPOT:1023;BTN2"):
            g._consume_serial(chunk)
        self.assertEqual(g.catch_pot_value, 1023)
        self.assertEqual([call.args[0] for call in g.press_button.call_args_list], [0, 3, 1])

    def test_partial_value_is_not_accepted_by_forced_flush(self):
        g = self.game
        g._consume_serial("POT:00")
        g._drain_serial_buffer(force=True)
        self.assertIsNone(getattr(g, "catch_pot_value", None))
        g._consume_serial("64;")
        self.assertEqual(g.catch_pot_value, 64)

    def test_malformed_values_rejected_and_stream_recovers(self):
        g = self.game
        g._consume_serial("POT:0500;")
        for frame in ("POT:1024;", "POT:-001;", "POT:abcd;", "POT:00000;", "POT:9999;"):
            g._consume_serial(frame)
            self.assertEqual(g.catch_pot_value, 500)
        g._consume_serial("POT:00BTN1\nPOT:0900;")
        g.press_button.assert_called_once_with(0)
        self.assertEqual(g.catch_pot_value, 900)

    def test_no_control_in_other_modes_or_autoplay(self):
        g = self.game
        with patch("game.gamemanager.time.monotonic", return_value=100):
            g._set_catch_potentiometer(0)
        for scene, mode, autoplay in (("select", "catch", False), ("game", "2k", False),
                                      ("game", "4k", False), ("demonstration", "catch", False),
                                      ("game", "catch", True)):
            g.scene, g.game_mode, g.debug_autoplay = scene, mode, autoplay
            self.assertFalse(g._catch_pot_active(100))

    def test_stale_stream_restores_button_control(self):
        g = self.game
        with patch("game.gamemanager.time.monotonic", return_value=100):
            g._set_catch_potentiometer(512)
            g._move_catcher(1)
        self.assertEqual(g.catcher_velocity, 0)
        with patch("game.gamemanager.time.monotonic", return_value=101.1):
            g._move_catcher(1)
        self.assertEqual(g.catcher_velocity, 520)

    def test_stationary_noise_does_not_move_target_or_catcher(self):
        g = self.game
        with patch("game.gamemanager.time.monotonic", return_value=100):
            g._set_catch_potentiometer(512)
        for frame in range(1, 31):
            g._animate_catcher(100 + frame / 60)
        settled = g.catcher_x
        for index, value in enumerate([509, 513, 511, 515, 510, 514] * 10):
            now = 100.5 + (index + 1) / 50
            with patch("game.gamemanager.time.monotonic", return_value=now):
                g._set_catch_potentiometer(value)
            g._animate_catcher(now)
            self.assertEqual(g.catch_pot_value, 512)
            self.assertEqual(g.catcher_x, settled)
            self.assertTrue(g._catch_pot_active(now))

    def test_movement_is_smoothed_and_frame_rate_independent(self):
        g = self.game
        with patch("game.gamemanager.time.monotonic", return_value=100):
            g._set_catch_potentiometer(1023)
        g._animate_catcher(100 + 1 / 60)
        self.assertGreater(g.catcher_x, 540)
        self.assertLess(g.catcher_x, 900)
        positions = []
        for fps in (30, 60, 120):
            g.catcher_x, g.catcher_last_update = 540.0, 100.0
            for frame in range(1, round(fps * .1) + 1):
                g._animate_catcher(100 + frame / fps)
            positions.append(g.catcher_x)
        self.assertAlmostEqual(positions[0], positions[1])
        self.assertAlmostEqual(positions[1], positions[2])

    def test_fresh_input_does_not_drop_out_when_frame_timestamp_is_older(self):
        g = self.game
        with patch("game.gamemanager.time.monotonic", return_value=100.001):
            g._set_catch_potentiometer(512)
        self.assertTrue(g._catch_pot_active(100))
