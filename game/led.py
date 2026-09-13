"""Scene LED timelines shared by the editor, hardware output and preview."""

import json
import os
import tempfile
import threading
import time

from PIL import Image, ImageDraw
from game import neopixel

SCENES = (
    "preload", "ci", "title", "entry", "warning", "mode_select",
    "title_select", "select", "next", "game", "demonstration", "result",
    "total_result", "ending",
)


def defaults():
    return {"version": 1, "neopixel": {"enabled": False, "preview_bpm": 120}, "scenes": {
        scene: {"loop": True, "steps": [{"ms": 500, "leds": [False] * 4}],
                "neopixel": neopixel.defaults(scene)}
        for scene in SCENES
    }}


def validate(data):
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("Unsupported LED animation file version")
    scenes = data.get("scenes")
    pixels = data.setdefault("neopixel", {"enabled": False, "preview_bpm": 120})
    if (not isinstance(pixels, dict) or type(pixels.get("enabled")) is not bool
            or not neopixel.number(pixels.get("preview_bpm"), 20, 400)):
        raise ValueError("NeoPixel needs enabled true/false and preview_bpm 20–400")
    if not isinstance(scenes, dict) or set(scenes) != set(SCENES):
        raise ValueError("The LED file must contain every minigame scene")
    for name, animation in scenes.items():
        if not isinstance(animation, dict) or type(animation.get("loop")) is not bool:
            raise ValueError(f"{name}: loop must be true or false")
        neopixel.validate(animation.setdefault("neopixel", neopixel.defaults(name)))
        steps = animation.get("steps")
        if not isinstance(steps, list) or not 1 <= len(steps) <= 1000:
            raise ValueError(f"{name}: use 1 to 1000 steps")
        for step in steps:
            if not isinstance(step, dict):
                raise ValueError(f"{name}: invalid step")
            ms, leds = step.get("ms"), step.get("leds")
            if type(ms) is not int or not 100 <= ms <= 60000:
                raise ValueError(f"{name}: step duration must be 100–60000 ms")
            if not isinstance(leds, list) or len(leds) != 4 or any(type(v) is not bool for v in leds):
                raise ValueError(f"{name}: each step needs four ON/OFF values")
    return data


def load(path):
    try:
        with open(path, encoding="utf-8") as source:
            return validate(json.load(source))
    except FileNotFoundError:
        return defaults()


def save(path, data):
    validate(data)
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory, delete=False) as output:
            temporary = output.name
            json.dump(data, output, indent=2)
            output.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def sample(animation, seconds):
    """Return four switches; non-looping timelines hold their final state."""
    elapsed = max(0, seconds * 1000)
    duration = sum(step["ms"] for step in animation["steps"])
    if animation["loop"]:
        elapsed %= duration
    for step in animation["steps"]:
        if elapsed < step["ms"]:
            return tuple(step["leds"])
        elapsed -= step["ms"]
    return tuple(animation["steps"][-1]["leds"])


def render_preview(states):
    image = Image.new("RGBA", (480, 140), (16, 21, 32, 245))
    draw = ImageDraw.Draw(image)
    colors = ((70, 170, 255), (245, 245, 255), (70, 170, 255), (245, 245, 255))
    for index, (on, color) in enumerate(zip(states, colors)):
        x = 60 + index * 120
        if on:
            draw.ellipse((x - 46, 16, x + 46, 108), fill=(*color, 55))
        draw.ellipse((x - 34, 28, x + 34, 96), fill=(*color, 255) if on else (40, 49, 65, 255),
                     outline=(110, 130, 155), width=2)
        draw.text((x - 24, 114), f"SW{index + 1} {'ON' if on else 'OFF'}", fill="white")
    return image


class LedOutput:
    def __init__(self, report):
        self.report = report
        self.condition = threading.Condition()
        self.pending = None
        self.closing = False
        self.thread = threading.Thread(target=self._run, daemon=True, name="smush-led-output")
        self.thread.start()

    def submit(self, serial, states, pixels=None):
        with self.condition:
            self.pending = serial, states, pixels
            self.condition.notify()

    def close(self):
        with self.condition:
            self.closing = True
            self.condition.notify()
        self.thread.join(timeout=0.2)

    def _run(self):
        connection, previous, failed = None, None, None
        previous_pixels, sent_at = None, 0.0
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.pending is not None or self.closing)
                if self.closing:
                    target, states, pixels = connection, (False,) * 4, (neopixel.BLACK if previous_pixels is not None else None)
                    if target is None and self.pending is not None:
                        target = self.pending[0]
                        pixels = neopixel.BLACK if self.pending[2] is not None else None
                else:
                    target, states, pixels = self.pending
                self.pending = None
                closing = self.closing
            if target is not connection:
                connection, previous, previous_pixels = target, None, None
            if target is not None and target is not failed:
                try:
                    if pixels is not None or previous_pixels is not None:
                        frame = pixels if pixels is not None else neopixel.BLACK
                        if states != previous or frame != previous_pixels or time.monotonic() - sent_at >= .5 or closing:
                            target.set_led_frame(states, frame)
                            sent_at = time.monotonic()
                    else:
                        for index, enabled in enumerate(states):
                            if previous is None or enabled != previous[index]:
                                target.set_switch_led(index + 1, enabled)
                    previous = states
                    previous_pixels = pixels
                except Exception as error:
                    failed = target
                    self.report(f"LED output unavailable: {error}")
            if closing:
                return
