import copy
import os
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from game import neopixel
from game.led import LedOutput, defaults, load, save, validate
from game.led_runtime import LedRuntimeMixin
from serial_arduino import SerialIO


class GrooveTests(unittest.TestCase):
    def setUp(self):
        self.settings = neopixel.defaults("game")
        self.settings.update(brightness=1, pulse_fraction=1, high_health=False,
                             colors=["#FF0000"] * 4)

    def sample(self, seconds, points=((1, 500), (3, 250)), **kwargs):
        return neopixel.sample(self.settings, seconds, points, **kwargs)

    def test_audio_offset_beats_decay_and_tempo_change(self):
        self.assertEqual(self.sample(.999), neopixel.BLACK)
        self.assertEqual(self.sample(1), ((255, 0, 0),) * 4)
        self.assertEqual(self.sample(1.25), ((128, 0, 0),) * 4)
        self.assertEqual(self.sample(1.5), self.sample(1))
        self.assertEqual(self.sample(3.125), ((128, 0, 0),) * 4)
        self.assertEqual(self.sample(3.25), self.sample(3))
        # Seek backwards and sample after skipped frames: no accumulated drift.
        self.assertEqual(self.sample(3003.25), self.sample(3))
        self.assertEqual(self.sample(1.25), ((128, 0, 0),) * 4)

    def test_reference_speed_is_period_multiplier_and_offset_delays(self):
        self.settings["speed"] = 2
        self.assertEqual(self.sample(1.5), ((128, 0, 0),) * 4)
        self.assertEqual(self.sample(2), self.sample(1))
        self.settings["offset_ms"] = 100
        self.assertEqual(self.sample(1.05), neopixel.BLACK)
        self.assertEqual(self.sample(1.1), ((255, 0, 0),) * 4)

    def test_right_side_alternate_requires_health_strictly_above_85(self):
        self.settings["high_health"] = True
        self.settings["right_colors"] = ["#00FF00", "#0000FF"]
        self.assertEqual(self.sample(1, health=85), ((255, 0, 0),) * 4)
        self.assertEqual(self.sample(1, health=85.01),
                         ((255, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255)))

    def test_modes_brightness_and_preview_bpm(self):
        self.settings["brightness"] = .2
        self.assertEqual(self.sample(0, ()), ((51, 0, 0),) * 4)
        self.assertEqual(self.sample(.25, (), fallback_bpm=240), self.sample(0, ()))
        self.settings["mode"] = "off"
        self.assertEqual(self.sample(0, ()), neopixel.BLACK)
        self.settings["mode"] = "solid"
        self.assertEqual(self.sample(-3), ((51, 0, 0),) * 4)

    def test_title_defaults_scroll_rainbow_at_full_brightness(self):
        settings = neopixel.defaults("title")
        neopixel.validate(settings)
        first = neopixel.sample(settings, 0)
        shifted = neopixel.sample(settings, .5)
        self.assertEqual(shifted, first[-1:] + first[:-1])
        self.assertNotEqual(neopixel.sample(settings, .25), first)
        self.assertEqual(neopixel.sample(settings, 2), first)
        for seconds in (0, .25, 1, 123):
            pixels = neopixel.sample(settings, seconds, health=100)
            self.assertTrue(all(max(pixel) == 255 for pixel in pixels))
            self.assertEqual(pixels, neopixel.sample(settings, seconds, health=0))
        settings["speed"] = 2
        self.assertEqual(neopixel.sample(settings, 1), shifted)
        settings["brightness"] = .2
        self.assertTrue(all(max(pixel) == 51 for pixel in neopixel.sample(settings, .25)))

    def test_old_timelines_migrate_without_enabling_new_hardware(self):
        old = defaults()
        del old["neopixel"]
        for scene in old["scenes"].values():
            del scene["neopixel"]
        validate(old)
        self.assertFalse(old["neopixel"]["enabled"])
        self.assertEqual(old["scenes"]["game"]["neopixel"]["mode"], "beat")
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "led.json")
            old["neopixel"]["enabled"] = True
            save(path, old)
            self.assertEqual(load(path), old)
            for key, value in (("speed", 0), ("brightness", float("nan")),
                               ("pulse_fraction", 0), ("colors", ["#GG0000"] * 4)):
                bad = copy.deepcopy(old)
                bad["scenes"]["game"]["neopixel"][key] = value
                with self.assertRaises(ValueError):
                    save(path, bad)
                self.assertEqual(load(path), old)


class SelectionBeatTests(unittest.TestCase):
    def setUp(self):
        self.runtime = LedRuntimeMixin()
        r = self.runtime
        r.root, r.canvas, r.audio, r.serial = Mock(), Mock(), Mock(), Mock()
        r._initialize_leds("/private/tmp/smush-test-led-config/main.ini", False)
        r.led_reload_at = float("inf")
        r.led_data["neopixel"]["enabled"] = True
        r.led_output = Mock()
        r.running, r.unrecoverable_error = True, False
        r.scene, r.scene_started, r.health = "select", 0, 0
        r.track = SimpleNamespace(audio_path="song-a", preview_time=10000,
                                 tempo_points=((0, 500), (10, 300), (12, 250)))
        r._preview_start_seconds = lambda track: max(0, track.preview_time / 1000)
        r.select_preview_started = False
        r.select_preview_started_at = 100
        r.audio.current_path = "song-a"
        r.audio.is_playing.return_value = True
        settings = r.led_data["scenes"]["select"]["neopixel"]
        settings.update(mode="beat", brightness=1, pulse_fraction=1,
                        high_health=False, colors=["#FF0000"] * 4)

    def test_preview_clock_offset_and_tempo_changes(self):
        r = self.runtime
        r.select_preview_started = True
        r.audio.position_seconds.return_value = 2.125
        seconds, points = r._led_song_preview_timing(102.125)
        self.assertEqual(seconds, 12.125)
        self.assertEqual(points, r.track.tempo_points)
        with patch("game.led_runtime.time.monotonic", return_value=102.125):
            r._tick_leds()
        self.assertEqual(r.led_output.submit.call_args.args[2], ((128, 0, 0),) * 4)
        r.audio.position_seconds.return_value = None
        self.assertEqual(r._led_song_preview_timing(102.125)[0], 12.125)

    def test_selection_change_updates_tempo_before_preview_starts(self):
        r = self.runtime
        for now, expected in ((100, 255), (100.15, 127)):
            with patch("game.led_runtime.time.monotonic", return_value=now):
                r._tick_leds()
            # Float subtraction can round an exact half-level to either byte.
            pixel = r.led_output.submit.call_args.args[2][0]
            self.assertLessEqual(abs(pixel[0] - expected), 1)
        r.track = SimpleNamespace(audio_path="song-b", preview_time=10000,
                                 tempo_points=((0, 1000),))
        with patch("game.led_runtime.time.monotonic", return_value=101):
            r._tick_leds()
        self.assertEqual(r.led_output.submit.call_args.args[2], ((255, 0, 0),) * 4)
        with patch("game.led_runtime.time.monotonic", return_value=101.5):
            r._tick_leds()
        self.assertEqual(r.led_output.submit.call_args.args[2], ((128, 0, 0),) * 4)
        r.audio.position_seconds.assert_not_called()

    def test_next_screen_continues_preview_and_missing_timing_falls_back(self):
        r = self.runtime
        r.scene = "next"
        r.audio.position_seconds.return_value = 1.5
        self.assertEqual(r._led_song_preview_timing(110), (11.5, r.track.tempo_points))
        r.scene = "title_select"
        r.track = SimpleNamespace(audio_path="untimed", preview_time=-1, tempo_points=())
        self.assertEqual(r._led_song_preview_timing(120), (0, ()))
        self.assertEqual(r._led_song_preview_timing(120.25), (.25, ()))

    def test_non_beat_menu_effects_keep_configured_menu_timing(self):
        r = self.runtime
        r.led_data["scenes"]["select"]["neopixel"]["mode"] = "rainbow"
        r._led_song_preview_timing = Mock(side_effect=AssertionError("unexpected song clock"))
        r._tick_leds()
        r._led_song_preview_timing.assert_not_called()


class PixelOutputTests(unittest.TestCase):
    def test_frame_wire_format_and_validation(self):
        with patch("serial_arduino.serial.Serial") as port:
            serial = SerialIO("test", 9600, 1)
            pixels = ((255, 0, 0), (0, 255, 0), (0, 0, 255), (1, 2, 3))
            serial.set_led_frame((True, False, True, False), pixels)
            port.return_value.write.assert_called_once_with(b"LED0:FF000000FF000000FF010203\n")
            with self.assertRaises(ValueError):
                serial.set_led_frame((False,) * 4, ((256, 0, 0),) * 4)

    def test_worker_sends_atomic_pixels_then_black_on_close(self):
        done = threading.Event()
        serial = Mock()
        serial.set_led_frame.side_effect = lambda *args: done.set()
        output = LedOutput(self.fail)
        pixels = ((20, 40, 60),) * 4
        output.submit(serial, (True,) * 4, pixels)
        self.assertTrue(done.wait(1))
        output.close()
        self.assertFalse(output.thread.is_alive())
        self.assertEqual(serial.set_led_frame.call_args_list,
                         [unittest.mock.call((False,) * 4, pixels),
                          unittest.mock.call((False,) * 4, neopixel.BLACK)])
        serial.set_switch_led.assert_not_called()

    def test_disabling_pixels_clears_them_without_button_commands(self):
        sent = threading.Event()
        serial = Mock()
        serial.set_led_frame.side_effect = lambda *args: sent.set()
        serial.set_switch_led.side_effect = lambda *args: sent.set()
        output = LedOutput(self.fail)
        try:
            output.submit(serial, (False,) * 4, ((12, 34, 56),) * 4)
            self.assertTrue(sent.wait(1))
            sent.clear()
            output.submit(serial, (False,) * 4)
            self.assertTrue(sent.wait(1))
            serial.set_led_frame.assert_called_with((False,) * 4, neopixel.BLACK)
            sent.clear()
            output.submit(serial, (True, False, False, False))
            output.close()
            serial.set_switch_led.assert_not_called()
        finally:
            output.close()

    def test_unchanged_pixels_are_refreshed_for_firmware_watchdog(self):
        sent = threading.Event()
        serial = Mock()
        serial.set_led_frame.side_effect = lambda *args: sent.set()
        with patch("game.led.time.monotonic", side_effect=[10, 10.5, 10.5, 11, 11]):
            output = LedOutput(self.fail)
            try:
                output.submit(serial, (False,) * 4, neopixel.BLACK)
                self.assertTrue(sent.wait(1))
                sent.clear()
                output.submit(serial, (False,) * 4, neopixel.BLACK)
                self.assertTrue(sent.wait(1))
                self.assertEqual(serial.set_led_frame.call_count, 2)
            finally:
                output.close()

    def test_runtime_uses_song_clock_and_turns_pixels_off_in_other_scenes(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = LedRuntimeMixin()
            runtime.root = Mock()
            runtime.canvas = Mock()
            runtime.running, runtime.unrecoverable_error = True, False
            runtime.serial = Mock()
            runtime._print = self.fail
            runtime._initialize_leds(os.path.join(directory, "main.ini"), False)
            runtime.led_data["neopixel"]["enabled"] = True
            runtime.led_reload_at = float("inf")
            runtime.led_output = Mock()
            runtime.scene, runtime.scene_started = "game", 0
            runtime.track = SimpleNamespace(tempo_points=((2, 500),))
            runtime.health = 100
            runtime._game_elapsed = Mock(return_value=2)
            runtime._tick_leds()
            expected = neopixel.sample(runtime.led_data["scenes"]["game"]["neopixel"], 2, ((2, 500),), 100)
            runtime.led_output.submit.assert_called_with(runtime.serial, (False,) * 4, expected)
            runtime.scene = "result"
            runtime._tick_leds()
            runtime.led_output.submit.assert_called_with(runtime.serial, (False,) * 4, neopixel.BLACK)
            runtime._game_elapsed.assert_called_once()
