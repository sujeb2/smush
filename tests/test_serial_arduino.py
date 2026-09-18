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


if __name__ == "__main__":
    unittest.main()
