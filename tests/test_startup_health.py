import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from startup_health import (
    StartupHealthError,
    check_disk,
    check_runtime_files,
    clear_previous_error,
    mark_unrecoverable_error,
    previous_error_details,
)


class StartupHealthTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.base = self.directory.name
        os.makedirs(os.path.join(self.base, "files", "img"))

    def tearDown(self):
        self.directory.cleanup()

    def test_error_marker_round_trip(self):
        self.assertIsNone(previous_error_details(self.base))
        mark_unrecoverable_error(self.base, "RUNTIME_FAILURE", "camera stopped")
        marker = previous_error_details(self.base)
        self.assertEqual(marker["code"], "RUNTIME_FAILURE")
        self.assertEqual(marker["detail"], "camera stopped")
        clear_previous_error(self.base)
        self.assertIsNone(previous_error_details(self.base))

    def test_damaged_error_marker_still_triggers_recovery(self):
        marker_path = os.path.join(self.base, "files", ".last_unrecoverable_error.json")
        with open(marker_path, "w", encoding="utf-8") as file:
            file.write("not json")
        self.assertEqual(previous_error_details(self.base)["code"], "DAMAGED_ERROR_MARKER")

    def test_disk_check_verifies_free_space_and_read_write(self):
        usage = check_disk(self.base, minimum_free_bytes=0)
        self.assertGreater(usage.total, 0)
        leftovers = [name for name in os.listdir(os.path.join(self.base, "files")) if "disk-check" in name]
        self.assertEqual(leftovers, [])

    def test_disk_check_rejects_low_free_space(self):
        usage = SimpleNamespace(total=1024, used=1023, free=1)
        with patch("startup_health.shutil.disk_usage", return_value=usage):
            with self.assertRaisesRegex(StartupHealthError, "insufficient disk space"):
                check_disk(self.base, minimum_free_bytes=2)

    def test_recovery_file_check_accepts_valid_critical_files(self):
        os.makedirs(os.path.join(self.base, "files", "models"))
        os.makedirs(os.path.join(self.base, "game"))
        with open(os.path.join(self.base, "requirements.txt"), "w", encoding="utf-8") as file:
            file.write("Pillow\n")
        with open(os.path.join(self.base, "files", "main_conf.ini"), "w", encoding="utf-8") as file:
            file.write("[GENERIC]\nModelPath=files/models/model.pt\n[UI]\nEnabled=True\n")
        with open(os.path.join(self.base, "files", "model_conf.ini"), "w", encoding="utf-8") as file:
            file.write("[GENERIC]\nVerbose=True\n")
        with open(os.path.join(self.base, "files", "models", "model.pt"), "wb") as file:
            file.write(b"model")
        with open(os.path.join(self.base, "files", "img", "unrecoverable_system_error.svg"), "w", encoding="utf-8") as file:
            file.write('<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>')
        image_path = os.path.join(self.base, "files", "img", "valid.png")
        Image.new("RGBA", (2, 2), "white").save(image_path)
        with open(os.path.join(self.base, "game", "minigame_progress.json"), "w", encoding="utf-8") as file:
            json.dump({"track_index": 0}, file)
        required = (
            "requirements.txt", "files/main_conf.ini", "files/model_conf.ini",
            "files/models/model.pt", "files/img/unrecoverable_system_error.svg",
        )
        self.assertTrue(check_runtime_files(self.base, required_paths=required, image_paths=("files/img/valid.png",)))

    def test_recovery_file_check_reports_missing_configured_model(self):
        with open(os.path.join(self.base, "files", "main_conf.ini"), "w", encoding="utf-8") as file:
            file.write("[GENERIC]\nModelPath=files/models/missing.pt\n[UI]\nEnabled=True\n")
        with open(os.path.join(self.base, "files", "model_conf.ini"), "w", encoding="utf-8") as file:
            file.write("[GENERIC]\nVerbose=True\n")
        with self.assertRaisesRegex(StartupHealthError, "required file is missing"):
            check_runtime_files(
                self.base,
                required_paths=("files/main_conf.ini", "files/model_conf.ini"),
                image_paths=(),
            )


if __name__ == "__main__":
    unittest.main()
