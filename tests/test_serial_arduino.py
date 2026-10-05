import unittest
from unittest.mock import patch

from serial_arduino import SerialIO


class SerialIOTests(unittest.TestCase):
    def setUp(self):
        serial_patcher = patch("serial_arduino.serial.Serial")
        self.addCleanup(serial_patcher.stop)
        serial_class = serial_patcher.start()
        self.serial_port = serial_class.return_value
        self.serial_port.is_open = True
        self.serial_io = SerialIO("TEST", 9600, timeout=1)

    def test_neopixel_frame_has_no_button_lamp_output(self):
        self.serial_io.set_led_frame((True,) * 4, ((255, 0, 0),) * 4)
        self.serial_port.write.assert_called_once_with(b"LED0:FF0000FF0000FF0000FF0000\n")
        self.assertFalse(hasattr(self.serial_io, "set_switch_led"))

    def test_multiline_command_is_rejected(self):
        with self.assertRaises(ValueError):
            self.serial_io.write_command("SW1_ON\nSW2_ON")

    def test_reads_preserve_framing_for_immediate_input(self):
        self.serial_port.in_waiting = 11
        self.serial_port.read.return_value = b"Forwarded\r\n"
        self.assertEqual(self.serial_io.read(), "Forwarded\r\n")

    def receive(self, message):
        self.serial_port.in_waiting = len(message)
        self.serial_port.read.return_value = message.encode()
        state = self.serial_io.poll_machine_status()
        self.serial_port.in_waiting = 0
        return state

    def test_fragmented_status_pauses_and_resumes_without_losing_ui_messages(self):
        self.assertEqual(self.receive("crush"), (False, 0))
        self.assertEqual(self.receive("ing_busy\r\ntrash_full\n"), (True, 1))
        self.assertGreater(self.serial_io.in_waiting, 0)
        self.assertEqual(self.serial_io.read(), "crush")
        self.assertEqual(self.serial_io.read(), "ing_busy\r\ntrash_full\n")
        self.assertIsNone(self.serial_io.read())
        self.assertEqual(self.receive("CRUSHING_IDLE\n"), (False, 2))

    def test_ui_read_updates_shared_state(self):
        self.serial_port.in_waiting = 14
        self.serial_port.read.return_value = b"crushing_busy\n"
        self.serial_io.read()
        self.assertTrue(self.serial_io.crushing_busy)

    def test_legacy_firmware_done_message_resumes_recognition(self):
        self.receive("crushing_busy\n")
        self.assertEqual(self.receive("crushing_done\n"), (False, 2))

    def test_detection_write_checks_pending_busy_and_preserves_reply(self):
        self.serial_port.in_waiting = 14
        self.serial_port.read.return_value = b"crushing_busy\n"
        self.assertFalse(self.serial_io.write_detection("obj1_detect[can]\n", 0))
        self.serial_port.write.assert_not_called()
        self.assertEqual(self.serial_io.read(), "crushing_busy\n")

    def test_busy_idle_during_inference_rejects_old_frame(self):
        self.assertEqual(self.receive("crushing_busy\ncrushing_idle\n"), (False, 2))
        self.assertFalse(self.serial_io.write_detection("obj1_detect[can]\n", 0))
        self.serial_port.write.assert_not_called()
        self.assertTrue(self.serial_io.write_detection("obj1_detect[can]\n", 2))
        self.serial_port.write.assert_called_once_with(b"obj1_detect[can]\n")


if __name__ == "__main__":
    unittest.main()
