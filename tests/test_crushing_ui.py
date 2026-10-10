import unittest
from collections import deque
from pathlib import Path
from unittest.mock import Mock, patch

import status_card
from gui import RecyclingUI
from particles import Fireworks, ParticleSystem, blend
from status_card import MachineCycle, StatusCard

BASE = Path(__file__).resolve().parents[1]


class Clock:
    def __init__(self, now=100.0):
        self.now = now

    def __call__(self):
        return self.now


def make_ui(clock):
    ui = RecyclingUI.__new__(RecyclingUI)
    ui.running = True
    ui.screen_state = "ready"
    ui.scale = 0.5
    ui.offset_x = ui.offset_y = 0
    ui.root, ui.canvas = Mock(), Mock()
    ui.serial_buffer = ""
    ui.serial_messages = ("obj_dropped1", "obj_dropped2", "forwarded", "forwarded_2")
    ui.serial_materials = {"obj_dropped1": "can", "obj_dropped2": "plastic_bottle",
                           "forwarded": "can", "forwarded_2": "plastic_bottle"}
    ui.trigger_recycle = Mock()
    ui._request_test_mode = Mock()
    ui.animating = False
    ui.pending_events = deque()
    ui.crushing_busy = ui.trash_full = False
    ui.font_path = str(BASE / "files/fonts/KERISKEDU_B.ttf")
    ui.cycle = MachineCycle(clock=clock)
    ui.status_card = StatusCard(ui, ui.cycle, str(BASE / "files/fonts/Cafe24Ssurround-v2.0.otf"))
    ui.status_card.build()
    return ui


class StatusCardTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        for target in ("PIL.ImageTk.PhotoImage",):
            patcher = patch(target, side_effect=lambda image: image)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(status_card.time, "monotonic", self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.ui = make_ui(self.clock)
        self.card = self.ui.status_card

    def frame_at(self, offset):
        self.clock.now = self.card.reveal_started + offset
        self.card._frame()

    def test_busy_opens_done_closes_card_with_intermediate_frames(self):
        ui, card = self.ui, self.card
        ui._consume_serial_messages("crushing_busy\n")
        self.assertEqual(card.kind, "crush")
        self.frame_at(.225)
        self.assertAlmostEqual(card.reveal, .5)
        self.frame_at(.5)
        self.assertEqual(card.reveal, 1)
        ui.canvas.itemconfigure.assert_any_call(card.items["card"], state="normal")
        ui._consume_serial_messages("crushing_done\n")
        self.frame_at(.225)
        self.assertAlmostEqual(card.reveal, .5)
        self.frame_at(.5)
        self.assertIsNone(card.kind)
        ui.canvas.itemconfigure.assert_called_with("status_card", state="hidden")

    def test_fragments_and_drop_messages_keep_serial_order(self):
        ui = self.ui
        for chunk in ("crush", "ing_busy\r\nFor", "warded_2\ncrushing_", "idle\ntrash_", "full\n"):
            ui._consume_serial_messages(chunk)
        self.assertFalse(ui.crushing_busy)
        self.assertTrue(ui.trash_full)
        self.assertEqual(self.card.kind, "trash_full")
        ui.trigger_recycle.assert_called_once_with("plastic_bottle")

    def test_full_warning_survives_idle_and_repeated_busy_messages(self):
        self.ui._consume_serial_messages("trash_full\ncrushing_busy\ncrushing_idle\ncrushing_busy\n")
        self.assertEqual(self.card.reveal_target, 1)
        self.assertEqual(self.card.kind, "trash_full")

    def test_idle_can_reverse_opening_without_jumping(self):
        ui, card = self.ui, self.card
        ui._handle_machine_status("crushing_busy")
        self.frame_at(.15)
        progress = card.reveal
        ui._handle_machine_status("crushing_idle")
        self.assertEqual(card.reveal, progress)
        self.assertEqual(card.reveal_from, progress)
        self.assertEqual(card.reveal_target, 0)

    def test_full_warning_reopens_when_replacing_busy_card(self):
        ui, card = self.ui, self.card
        ui._handle_machine_status("crushing_busy")
        self.frame_at(.5)
        self.assertEqual(card.reveal, 1)
        ui._handle_machine_status("trash_full")
        self.assertEqual(card.kind, "trash_full")
        self.assertEqual(card.reveal_from, 0)
        self.frame_at(.225)
        self.assertAlmostEqual(card.reveal, .5)

    def test_startup_status_is_retained_for_ready_scene(self):
        ui, card = self.ui, self.card
        ui.screen_state = "startup"
        ui.canvas.reset_mock()
        ui._handle_machine_status("crushing_busy")
        self.frame_at(.5)
        ui.canvas.itemconfigure.assert_not_called()
        ui.screen_state = "ready"
        card.build()
        ui._sync_status_card()
        ui.canvas.itemconfigure.assert_any_call(card.items["card"], state="normal")
        self.assertEqual(card.shown_text["title"][0], "압축하는 중")

    def test_phase_messages_drive_progress_through_fragments(self):
        ui, cycle = self.ui, self.ui.cycle
        ui._consume_serial_messages("obj_dropped1phase:con")
        ui.trigger_recycle.assert_called_once_with("can")
        self.assertEqual(cycle.phase, "convey")  # drop message starts the estimate right away
        ui._consume_serial_messages("vey:6500\r\nphase:crush:130")
        self.assertEqual(cycle.phase, "convey")  # number may still be arriving
        self.assertTrue(cycle.reported)
        ui._consume_serial_messages("00\r\ncrushing_busy\r\n")
        self.assertEqual((cycle.phase, cycle.total), ("crush", 13.0))
        self.assertTrue(ui.crushing_busy)
        self.clock.now += 6.5
        ui._consume_serial_messages("phase:crush:6500\r\n")  # heartbeat keeps the phase length
        self.assertEqual(cycle.total, 13.0)
        self.assertAlmostEqual(cycle.progress(), .5)
        ui._consume_serial_messages("phase:reset:500")
        ui._drain_serial_buffer(force=True)
        self.assertEqual(cycle.phase, "reset")
        ui._consume_serial_messages("crushing_done\r\nphase:idle:0\r\n")
        self.assertIsNone(cycle.phase)
        self.assertFalse(ui.crushing_busy)
        self.assertEqual(self.card.reveal_target, 0)

    def test_eta_counts_remaining_phases(self):
        ui, card = self.ui, self.card
        ui._handle_phase("convey", 6500)
        self.frame_at(.5)
        self.assertEqual(card.shown_text["eta"][0], "약 33초 남음")  # 6.5 + 13 + 13.15
        self.assertEqual(card.shown_text["title"][0], "운반하는 중")
        self.assertEqual(card.shown_text["label_convey"][2], status_card.AMBER)
        ui._handle_phase("reset", 2000)
        card._frame()
        self.assertEqual(card.shown_text["eta"][0], "약 2초 남음")
        self.assertEqual(card.shown_text["note"][2], status_card.GREEN)
        self.assertEqual(card.shown_text["label_crush"][2], status_card.GREEN)

    def test_drop_animation_defers_opening_card(self):
        ui, card = self.ui, self.card
        ui.animating = True
        ui._handle_phase("convey", 6500)
        self.assertFalse(card.visible)
        ui._complete_animation()
        self.assertEqual(card.kind, "convey")
        self.assertEqual(card.reveal_target, 1)


class MachineCycleTests(unittest.TestCase):
    def test_legacy_crush_estimates_reset_then_waits_for_done(self):
        clock = Clock()
        cycle = MachineCycle(clock=clock)
        cycle.legacy("crushing_busy")
        self.assertAlmostEqual(cycle.remaining(), 26.15)
        clock.now += 13.5
        self.assertTrue(cycle.tick())
        self.assertEqual(cycle.phase, "reset")
        self.assertAlmostEqual(cycle.progress(), .5 / 13.15)
        clock.now += 20
        self.assertFalse(cycle.tick())  # reset only ends on crushing_done
        self.assertEqual(cycle.progress(), 1.0)
        cycle.legacy("crushing_busy")  # repeated busy must not restart the estimate
        self.assertEqual(cycle.phase, "reset")
        cycle.legacy("crushing_done")
        self.assertIsNone(cycle.phase)

    def test_reported_phases_wait_for_firmware(self):
        clock = Clock()
        cycle = MachineCycle(clock=clock)
        cycle.report("crush", 1.0)
        clock.now += 5
        self.assertFalse(cycle.tick())
        self.assertEqual(cycle.phase, "crush")
        cycle.report("unknown", 0)
        self.assertIsNone(cycle.phase)


class ParticleTests(unittest.TestCase):
    def make_ui(self):
        ui = Mock()
        ui.scale = .5
        ui._x = ui._y = lambda value: value
        return ui

    def test_particles_fade_then_delete_their_canvas_items(self):
        ui = self.make_ui()
        system = ParticleSystem(ui, "#000000", "sparks")
        system.emit(0, 0, 100, 0, .5, 6, "#ffffff")
        self.assertTrue(system.update(.3))
        ui.canvas.create_line.assert_called_once()
        self.assertFalse(system.update(.3))
        ui.canvas.delete.assert_called_once_with(ui.canvas.create_line.return_value)

    def test_dormant_particles_wait_before_drawing(self):
        ui = self.make_ui()
        system = ParticleSystem(ui, "#000000", "sparks")
        system.emit(0, 0, 0, 0, .3, 6, "#ffffff").age = -.2
        system.update(.1)
        ui.canvas.create_line.assert_not_called()
        system.update(.15)
        ui.canvas.create_line.assert_called_once()

    def test_fireworks_rockets_burst_and_finish(self):
        ui = self.make_ui()
        fireworks = Fireworks(ui, "#a9e5fa")
        fireworks.launch(2)
        peak = 0
        for _ in range(200):
            fireworks.update(.05)
            peak = max(peak, len(fireworks.system.particles))
        self.assertGreater(peak, 60)  # both rockets exploded into sparks
        self.assertFalse(fireworks.active)

    def test_blend_moves_toward_background(self):
        self.assertEqual(blend("#ffffff", "#000000", 0), "#ffffff")
        self.assertEqual(blend("#ffffff", "#000000", 1), "#000000")
        self.assertEqual(blend("#ff0000", "#0000ff", .5), "#800080")


if __name__ == "__main__":
    unittest.main()
