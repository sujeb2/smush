import os
import unittest

from ui_framework import enlarge_unrecoverable_image, format_console_log, load_svg_image


class UnrecoverableErrorScreenTests(unittest.TestCase):
    def test_svg_asset_rasterizes_for_both_ui_renderers(self):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        image = load_svg_image(os.path.join(base, "files", "img", "unrecoverable_system_error.svg"))
        self.assertEqual(image.size, (500, 275))
        self.assertEqual(image.mode, "RGBA")

    def test_unrecoverable_artwork_is_enlarged_without_distortion(self):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        source = load_svg_image(os.path.join(base, "files", "img", "unrecoverable_system_error.svg"))
        enlarged = enlarge_unrecoverable_image(source)
        self.assertEqual(enlarged.size, (900, 495))

    def test_console_log_contains_error_code_and_detail(self):
        console = format_console_log("RUNTIME_FAILURE", "camera stopped")
        self.assertIn("CONSOLE LOG", console)
        self.assertIn("[RUNTIME_FAILURE]", console)
        self.assertIn("camera stopped", console)

    def test_console_log_is_limited_to_the_bottom_panel(self):
        console = format_console_log("RUNTIME_FAILURE", "\n".join(f"line {index}" for index in range(20)))
        self.assertLessEqual(len(console.splitlines()), 8)
        self.assertIn("line 19", console)


if __name__ == "__main__":
    unittest.main()
