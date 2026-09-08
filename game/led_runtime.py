import os
import time

from game.led import LedOutput, defaults, load, render_preview, sample


class LedRuntimeMixin:
    def _initialize_leds(self, config_path, demo_mode):
        self.demo_mode = demo_mode
        self.led_path = os.path.join(os.path.dirname(os.path.abspath(config_path)), "led_animations.json")
        self.led_data = defaults()
        self.led_stamp = None
        self.led_reload_at = 0.0
        self.led_scene_key = None
        self.led_started = time.monotonic()
        self.led_preview_visible = False
        self.led_preview_state = None
        self.led_output = None
        self.root.after(0, self._tick_leds)

    def _toggle_led_preview(self):
        if self.demo_mode:
            self.led_preview_visible = not self.led_preview_visible
            self.led_preview_state = None
            self.canvas.delete("led_preview")

    def _tick_leds(self):
        if not self.running or self.unrecoverable_error:
            self._close_leds()
            return
        now = time.monotonic()
        if now >= self.led_reload_at:
            self.led_reload_at = now + 1.0
            try:
                stamp = os.stat(self.led_path).st_mtime_ns if os.path.exists(self.led_path) else 0
                if stamp != self.led_stamp:
                    data = load(self.led_path)
                    self.led_data, self.led_stamp = data, stamp
            except (OSError, ValueError) as error:
                self._print(f"LED animation reload failed: {error}")
        key = (self.scene, self.scene_started)
        if key != self.led_scene_key:
            self.led_scene_key, self.led_started = key, now
        animation = self.led_data["scenes"].get(self.scene)
        states = sample(animation, now - self.led_started) if animation else (False,) * 4
        if not self.demo_mode and self.serial is not None:
            if self.led_output is None:
                self.led_output = LedOutput(self._print)
            self.led_output.submit(self.serial, states)
        show = self.demo_mode and self.led_preview_visible
        if show: # scene clear
            if states != self.led_preview_state or not self.canvas.coords("led_preview"):
                self.canvas.delete("led_preview")
                self.led_preview_photo = render_preview(states)
                self.canvas.create_image(self._x(540), self._y(420), image=self.led_preview_photo,
                                         anchor="center", tags=("led_preview",))
                self.led_preview_state = states
            self.canvas.tag_raise("led_preview")
        else:
            self.canvas.delete("led_preview")
            self.led_preview_state = None
        self.root.after(50, self._tick_leds)

    def _close_leds(self):
        if getattr(self, "led_output", None) is not None:
            self.led_output.close()
            self.led_output = None
