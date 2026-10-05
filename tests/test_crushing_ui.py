import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from gui import RecyclingUI


def make_ui():
    ui = RecyclingUI.__new__(RecyclingUI)
    ui.running = True
    ui.screen_state = "ready"
    ui.scale = 0.5
    ui.root, ui.canvas = Mock(), Mock()
    ui.serial_buffer = ""
    ui.serial_messages = ("forwarded", "forwarded_2")
    ui.serial_materials = {"forwarded": "can", "forwarded_2": "plastic_bottle"}
    ui.trigger_recycle = Mock()
    ui._request_test_mode = Mock()
    ui.crushing_busy = ui.trash_full = False
    ui.status_card_kind = ui.status_card_job = None
    ui.status_card_id = 1
    ui.status_card_progress = ui.status_card_target = 0.0
    ui.status_card_duration = 0.45
    base = Path(__file__).resolve().parents[1] / "files" / "img"
    ui.status_sources = {
        "crushing_busy": Image.open(base / "crush_please_wait.png").convert("RGBA"),
        "trash_full": Image.open(base / "trash_full.png").convert("RGBA"),
    }
    return ui


class CrushingCardTests(unittest.TestCase):
    def setUp(self):
        self.ui = make_ui()
        patcher = patch("gui.ImageTk.PhotoImage", side_effect=lambda image: image)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_busy_opens_idle_closes_card_with_intermediate_frames(self):
        ui = self.ui
        ui._consume_serial_messages("crushing_busy\n")
        start = ui.status_card_started
        with patch("gui.time.monotonic", return_value=start + .225):
            ui._animate_status_card()
        self.assertAlmostEqual(ui.status_card_progress, .5)
        self.assertEqual(ui.status_card_photo.size, (540, 480))
        with patch("gui.time.monotonic", return_value=start + .5):
            ui._animate_status_card()
        self.assertEqual(ui.status_card_progress, 1)
        ui._consume_serial_messages("crushing_idle\n")
        start = ui.status_card_started
        with patch("gui.time.monotonic", return_value=start + .225):
            ui._animate_status_card()
        self.assertAlmostEqual(ui.status_card_progress, .5)
        with patch("gui.time.monotonic", return_value=start + .5):
            ui._animate_status_card()
        self.assertIsNone(ui.status_card_kind)
        ui.canvas.itemconfigure.assert_called_with(1, state="hidden")

    def test_fragments_and_drop_messages_keep_serial_order(self):
        ui = self.ui
        for chunk in ("crush", "ing_busy\r\nFor", "warded_2\ncrushing_", "idle\ntrash_", "full\n"):
            ui._consume_serial_messages(chunk)
        self.assertFalse(ui.crushing_busy)
        self.assertTrue(ui.trash_full)
        self.assertEqual(ui.status_card_kind, "trash_full")
        ui.trigger_recycle.assert_called_once_with("plastic_bottle")

    def test_full_warning_survives_idle_and_repeated_busy_messages(self):
        ui = self.ui
        ui._consume_serial_messages("trash_full\ncrushing_busy\ncrushing_idle\n")
        self.assertEqual(ui.status_card_target, 1)
        self.assertEqual(ui.status_card_kind, "trash_full")

    def test_idle_can_reverse_opening_without_jumping(self):
        ui = self.ui
        ui._handle_machine_status("crushing_busy")
        start = ui.status_card_started
        with patch("gui.time.monotonic", return_value=start + .15):
            ui._animate_status_card()
            progress = ui.status_card_progress
            ui._handle_machine_status("crushing_idle")
        self.assertEqual(ui.status_card_progress, progress)
        self.assertEqual(ui.status_card_from, progress)
        self.assertEqual(ui.status_card_target, 0)

    def test_full_warning_opens_when_replacing_busy_card(self):
        ui = self.ui
        ui._handle_machine_status("crushing_busy")
        with patch("gui.time.monotonic", return_value=ui.status_card_started + .5):
            ui._animate_status_card()
        self.assertEqual(ui.status_card_progress, 1)
        ui._handle_machine_status("trash_full")
        self.assertEqual(ui.status_card_kind, "trash_full")
        self.assertEqual(ui.status_card_from, 0)
        with patch("gui.time.monotonic", return_value=ui.status_card_started + .225):
            ui._animate_status_card()
        self.assertAlmostEqual(ui.status_card_progress, .5)

    def test_startup_status_is_retained_for_ready_scene(self):
        ui = self.ui
        ui.screen_state = "startup"
        ui._handle_machine_status("crushing_busy")
        with patch("gui.time.monotonic", return_value=ui.status_card_started + .5):
            ui._animate_status_card()
        ui.canvas.itemconfigure.assert_not_called()
        ui.screen_state = "ready"
        ui._sync_status_card()
        self.assertEqual(ui.status_card_photo.size, (540, 960))

    def test_legacy_done_message_closes_busy_card(self):
        ui = self.ui
        ui._consume_serial_messages("crushing_busy\n")
        with patch("gui.time.monotonic", return_value=ui.status_card_started + .5):
            ui._animate_status_card()
        ui._consume_serial_messages("crushing_done\n")
        self.assertFalse(ui.crushing_busy)
        self.assertEqual(ui.status_card_target, 0)


if __name__ == "__main__":
    unittest.main()
