import sys
import unittest
from unittest.mock import patch

import camera_select

FACETIME = {"_name": "FaceTime HD Camera", "spcamera_model-id": "FaceTime HD Camera",
            "spcamera_unique-id": "FDF90FEB-59E5-4FCF-AABD-DA03C4E19BFB"}
IPHONE = {"_name": "iPhone Camera", "spcamera_model-id": "iPhone13,3",
          "spcamera_unique-id": "B4AB3AC1-7A84-4583-81F4-0C8600000001"}


class CameraSelectTests(unittest.TestCase):
    def select(self, devices, preferred=-1):
        with patch.object(sys, "platform", "darwin"), \
                patch.object(camera_select, "_mac_cameras", return_value=sorted(
                    devices, key=lambda device: device["spcamera_unique-id"])):
            return camera_select.camera_index(preferred)

    def test_continuity_camera_sorted_first_is_skipped(self):
        self.assertEqual(self.select([FACETIME, IPHONE]), 1)

    def test_only_continuity_camera_is_refused(self):
        self.assertIsNone(self.select([IPHONE]))
        with patch.object(camera_select, "camera_index", return_value=None):
            with self.assertRaises(RuntimeError):
                camera_select.open_camera()

    def test_configured_index_overrides_detection(self):
        self.assertEqual(self.select([IPHONE], preferred=0), 0)

    def test_other_platforms_use_first_camera(self):
        with patch.object(sys, "platform", "win32"):
            self.assertEqual(camera_select.camera_index(), 0)

    def test_listing_failure_falls_back_to_first_camera(self):
        with patch.object(sys, "platform", "darwin"), \
                patch.object(camera_select, "_mac_cameras", side_effect=OSError("missing")):
            self.assertEqual(camera_select.camera_index(), 0)


if __name__ == "__main__":
    unittest.main()
