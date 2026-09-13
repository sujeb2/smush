import os
import time
from bisect import bisect_right

from game.led import LedOutput, defaults, load, render_preview, sample
from game import neopixel


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
        self.led_preview_track = None
        self.led_preview_started = self.led_started
        self.root.after(0, self._tick_leds)

    def _led_song_preview_timing(self, now):
        track = self.track
        if track is not self.led_preview_track:
            self.led_preview_track = track
            self.led_preview_started = now
        points = track.tempo_points
        offset = self._preview_start_seconds(track)
        preview_ready = self.scene == "next" or (
            self.scene == "select" and self.select_preview_started)
        if preview_ready and self.audio.current_path == track.audio_path and self.audio.is_playing():
            position = self.audio.position_seconds()
            if position is None and self.scene == "select":
                position = max(0.0, now - self.select_preview_started_at)
            if position is not None:
                return offset + position, points
        if points:
            index = max(0, bisect_right(points, (offset, float("inf"))) - 1)
            points = ((0.0, points[index][1]),)
        return now - self.led_preview_started, points

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
        pixels = None
        if self.led_data["neopixel"]["enabled"]:
            seconds, points = now - self.led_started, ()
            if self.scene in ("game", "demonstration"):
                seconds = self._game_elapsed()
                points = self.track.tempo_points
            elif (animation and animation["neopixel"]["mode"] == "beat"
                  and self.scene in ("title_select", "select", "next")):
                seconds, points = self._led_song_preview_timing(now)
            pixels = neopixel.sample(animation["neopixel"], seconds, points,
                                     getattr(self, "health", 0), self.led_data["neopixel"]["preview_bpm"]) if animation else neopixel.BLACK
        if not self.demo_mode and self.serial is not None:
            if self.led_output is None:
                self.led_output = LedOutput(self._print)
            if pixels is None:
                self.led_output.submit(self.serial, states)
            else:
                self.led_output.submit(self.serial, states, pixels)
        show = self.demo_mode and self.led_preview_visible
        if show: # scene clear
            preview_state = (states, pixels) if pixels is not None else states
            if preview_state != self.led_preview_state or not self.canvas.coords("led_preview"):
                self.canvas.delete("led_preview")
                self.led_preview_photo = render_preview(states)
                self.canvas.create_image(self._x(540), self._y(420), image=self.led_preview_photo,
                                         anchor="center", tags=("led_preview",))
                if pixels is not None:
                    self.canvas.create_image(self._x(540), self._y(550), image=neopixel.render_preview(pixels),
                                             anchor="center", tags=("led_preview",))
                self.led_preview_state = preview_state
            self.canvas.tag_raise("led_preview")
        else:
            self.canvas.delete("led_preview")
            self.led_preview_state = None
        self.root.after(50, self._tick_leds)

    def _close_leds(self):
        if getattr(self, "led_output", None) is not None:
            self.led_output.close()
            self.led_output = None
