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

    def test_switch_led_command_is_newline_delimited(self):
        self.serial_io.set_switch_led(1, True)
        self.serial_io.set_switch_led(4, False)

        self.assertEqual(
            self.serial_port.write.call_args_list,
            [
                unittest.mock.call(b"SW1_ON\n"),
                unittest.mock.call(b"SW4_OFF\n"),
            ],
        )

    def test_switch_number_must_be_one_through_four(self):
        for switch_number in (0, 5, True):
            with self.subTest(switch_number=switch_number):
                with self.assertRaises(ValueError):
                    self.serial_io.set_switch_led(switch_number, True)

    def test_multiline_command_is_rejected(self):
        with self.assertRaises(ValueError):
            self.serial_io.write_command("SW1_ON\nSW2_ON")


if __name__ == "__main__":
    unittest.main()
