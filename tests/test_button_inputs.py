import unittest

from game.AnimationFramework import MinigameAnimationMixin


class SixButtonInputTests(unittest.TestCase):
    def setUp(self):
        self.game = MinigameAnimationMixin()
        self.game.settings = {
            "button_1": "forwarded", "button_2": "forwarded_2",
            "button_3": "forwarded_3", "button_4": "forwarded_4", "coin_message": "coin",
        }
        self.game.serial_buffer = ""
        self.pressed = []
        self.game.press_button = self.pressed.append

    def test_all_six_buttons_preserve_logical_actions(self):
        self.game._consume_serial("Forwarded\r\nForwarded_2\nForwarded_3\nForwarded_4\nBTN1\nBTN2\n")
        self.game._drain_serial_buffer(force=True)
        self.assertEqual(self.pressed, [0, 1, 2, 3, 0, 1])

    def test_new_and_old_messages_split_across_reads(self):
        for chunk in ("B", "TN", "1\nFor", "warded_", "4\r\nBT", "N2\n"):
            self.game._consume_serial(chunk)
        self.game._drain_serial_buffer(force=True)
        self.assertEqual(self.pressed, [0, 3, 1])

    def test_old_configured_messages_are_still_supported(self):
        self.game.settings.update(button_1="sw1", button_2="sw2", button_3="sw3", button_4="sw4")
        self.game._consume_serial("SW1\nSW2\nSW3\nSW4\nBTN1\nBTN2\n")
        self.assertEqual(self.pressed, [0, 1, 2, 3, 0, 1])

    def test_first_button_dispatches_at_line_ending_without_idle_wait(self):
        self.game._consume_serial("Forwarded\r\n")
        self.assertEqual(self.pressed, [0])
        self.assertEqual(self.game.serial_buffer, "")

    def test_split_terminator_finishes_first_button_immediately(self):
        self.game._consume_serial("Forwarded")
        self.assertEqual(self.pressed, [])
        self.game._consume_serial("\r")
        self.assertEqual(self.pressed, [0])
        self.game._consume_serial("\n")
        self.assertEqual(self.pressed, [0])

    def test_legacy_prefix_still_waits_for_suffix(self):
        self.game._consume_serial("Forwarded")
        self.assertFalse(self.pressed)
        self.game._consume_serial("_2\n")
        self.assertEqual(self.pressed, [1])

    def test_consecutive_framed_first_buttons_do_not_merge(self):
        self.game._consume_serial("Forwarded\nForwarded\n")
        self.assertEqual(self.pressed, [0, 0])
