import copy
import os
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from game.led import SCENES, LedOutput, defaults, load, render_preview, sample, save
from game.led_runtime import LedRuntimeMixin
from moderngl_framework import ModernGLCanvas


class LedTests(unittest.TestCase):
    def test_timing_boundaries_loop_and_final_hold(self):
        animation = {"loop": True, "steps": [
            {"ms": 200, "leds": [True, False, False, False]},
            {"ms": 300, "leds": [False, True, True, False]},
        ]}
        self.assertEqual(sample(animation, .199), (True, False, False, False))
        self.assertEqual(sample(animation, .2), (False, True, True, False))
        self.assertEqual(sample(animation, .5), (True, False, False, False))
        animation["loop"] = False
        self.assertEqual(sample(animation, 100), (False, True, True, False))

    def test_save_roundtrip_and_invalid_edit_does_not_replace_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "led.json")
            data = defaults()
            data["scenes"]["game"]["steps"][0]["leds"] = [True] * 4
            save(path, data)
            self.assertEqual(load(path), data)
            invalid = copy.deepcopy(data)
            invalid["scenes"]["game"]["steps"][0]["ms"] = 0
            with self.assertRaises(ValueError):
                save(path, invalid)
            self.assertEqual(load(path), data)

    def test_output_deduplicates_and_turns_off_on_close(self):
        done = threading.Event()
        calls = []
        def send(index, enabled):
            calls.append((index, enabled))
            if index == 4:
                done.set()
        output = LedOutput(self.fail)
        serial = SimpleNamespace(set_switch_led=send)
        output.submit(serial, (True,) * 4)
        self.assertTrue(done.wait(1))
        output.submit(serial, (True,) * 4)
        output.close()
        self.assertEqual(calls, [(i, True) for i in range(1, 5)] + [(i, False) for i in range(1, 5)])
        self.assertFalse(output.thread.is_alive())

    def test_runtime_all_scenes_reload_and_demo_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = LedRuntimeMixin()
            runtime.root = SimpleNamespace(after=lambda *args: None)
            runtime.canvas = ModernGLCanvas.__new__(ModernGLCanvas)
            runtime.canvas.items = {}
            runtime.canvas.order = []
            runtime.canvas.next_item = 1
            runtime.running = True
            runtime.unrecoverable_error = False
            runtime.serial = Mock()
            runtime._print = self.fail
            runtime._x = runtime._y = lambda value: value
            runtime._initialize_leds(os.path.join(directory, "main.ini"), True)
            data = defaults()
            for animation in data["scenes"].values():
                animation["steps"][0]["leds"] = [True, False, True, False]
            save(runtime.led_path, data)
            for index, scene in enumerate(SCENES):
                runtime.scene, runtime.scene_started = scene, index
                runtime.canvas.delete("all")
                # The toggle works in every scene, not just gameplay.
                runtime._toggle_led_preview()
                runtime._tick_leds()
                self.assertEqual(runtime.led_scene_key, (scene, index))
                self.assertEqual(runtime.led_preview_state, (True, False, True, False))
                self.assertTrue(runtime.canvas.coords("led_preview"))
                runtime._toggle_led_preview()
                runtime._tick_leds()
                self.assertFalse(runtime.canvas.coords("led_preview"))
            # Keep the preview enabled across scene transitions and rebuilds.
            runtime._toggle_led_preview()
            for index, scene in enumerate(SCENES):
                runtime.scene, runtime.scene_started = scene, index
                runtime.canvas.delete("all")
                runtime._tick_leds()
                self.assertTrue(runtime.canvas.coords("led_preview"))
            runtime.scene = "game"
            runtime._tick_leds()
            self.assertEqual(runtime.led_preview_state, (True, False, True, False))
            self.assertTrue(runtime.canvas.coords("led_preview"))
            runtime.serial.set_switch_led.assert_not_called()
            # A scene rebuild must recreate the preview, even for the same LED state.
            runtime.canvas.delete("all")
            runtime._tick_leds()
            self.assertTrue(runtime.canvas.coords("led_preview"))
            runtime._toggle_led_preview()
            runtime._tick_leds()
            self.assertFalse(runtime.canvas.coords("led_preview"))
            runtime.demo_mode = False
            runtime._toggle_led_preview()
            self.assertFalse(runtime.led_preview_visible)
            output = Mock()
            runtime.led_output = output
            runtime._tick_leds()
            output.submit.assert_called_with(runtime.serial, (True, False, True, False))
            data["scenes"]["game"]["steps"][0]["leds"] = [False] * 4
            save(runtime.led_path, data)
            runtime.led_reload_at = 0
            runtime._tick_leds()
            output.submit.assert_called_with(runtime.serial, (False,) * 4)

    def test_preview_has_four_independent_lamps(self):
        off = render_preview((False,) * 4)
        for index in range(4):
            states = tuple(n == index for n in range(4))
            image = render_preview(states)
            for lamp in range(4):
                center = (60 + lamp * 120, 60)
                self.assertEqual(image.getpixel(center) == off.getpixel(center), lamp != index)
