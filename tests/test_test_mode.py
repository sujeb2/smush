import os
import tempfile
import unittest

from test_mode import ConfigRepository, setting_kind, split_serial_commands, update_config_value


class SerialCommandTests(unittest.TestCase):
    def test_commands_are_extracted_across_reads(self):
        buffer, commands = split_serial_commands("", "te")
        self.assertEqual(commands, [])
        buffer, commands = split_serial_commands(buffer, "st_up\r\ntest_down")
        self.assertEqual(commands, ["test_up", "test_down"])
        self.assertEqual(buffer, "")

    def test_reset_is_detected_with_other_text(self):
        buffer, commands = split_serial_commands("noise", "RESETtest_back")
        self.assertEqual(commands, ["reset", "test_back"])
        self.assertEqual(buffer, "")


class ConfigRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.main_path = os.path.join(self.directory.name, "main_conf.ini")
        self.model_path = os.path.join(self.directory.name, "model_conf.ini")
        with open(self.main_path, "w", encoding="utf-8") as file:
            file.write(
                "[GENERIC]\nModelPath=files/models/test.pt\nSkipSerialCheck=False\n"
                "[SERIAL]\nSerialPort=COM3\nSerialBaudrate=9600\n"
                "[MOTOR]\nMaximumForceAvailable=50\n"
                "[UI]\nEnabled=True\n[UPDATE]\nEnabled=True\n"
                "[TEST_MODE]\nEnabled=False\n"
            )
        with open(self.model_path, "w", encoding="utf-8") as file:
            file.write(
                "[GENERIC]\nVerbose=True\nCameraFPS=480\n"
                "[DETECTION]\nExpectedObject_1=cup\n"
                "[SERIAL]\nPort=COM3\nBaudRate=9600\n"
            )

    def tearDown(self):
        self.directory.cleanup()

    def test_groups_cover_both_configuration_files(self):
        repository = ConfigRepository(self.main_path, self.model_path)
        generic_labels = [setting.label for setting in repository.groups["GENERIC SETUP"]]
        serial_labels = [setting.label for setting in repository.groups["SERIAL SETUP"]]
        model_labels = [setting.label for setting in repository.groups["MODEL CONFIGURATION"]]
        self.assertIn("GENERIC / MODEL PATH", generic_labels)
        self.assertIn("UI / ENABLED", generic_labels)
        self.assertIn("APP / SERIAL / SERIAL PORT", serial_labels)
        self.assertIn("MODEL / SERIAL / PORT", serial_labels)
        self.assertIn("DETECTION / EXPECTED OBJECT 1", model_labels)

    def test_save_preserves_other_lines_and_key_case(self):
        repository = ConfigRepository(self.main_path, self.model_path)
        setting = next(item for item in repository.groups["GENERIC SETUP"] if item.option == "SkipSerialCheck")
        repository.save(setting, "True")
        with open(self.main_path, "r", encoding="utf-8") as file:
            content = file.read()
        self.assertIn("SkipSerialCheck=True", content)
        self.assertIn("ModelPath=files/models/test.pt", content)

    def test_config_value_update_rejects_missing_option(self):
        with self.assertRaises(KeyError):
            update_config_value(self.main_path, "GENERIC", "Missing", "value")


class SettingKindTests(unittest.TestCase):
    def test_supported_value_types(self):
        self.assertEqual(setting_kind("True"), "boolean")
        self.assertEqual(setting_kind("-12"), "integer")
        self.assertEqual(setting_kind("0.25"), "float")
        self.assertEqual(setting_kind("files/model.pt"), "text")


if __name__ == "__main__":
    unittest.main()
