from bisect import bisect_right
from colorsys import hsv_to_rgb
import math

BLACK = ((0, 0, 0),) * 4


def defaults(scene):
    return {
        "mode": "rainbow" if scene == "title" else "beat" if scene in ("game", "demonstration") else "off",
        "speed": 1.0, "brightness": 1.0 if scene == "title" else 0.15, "pulse_fraction": 0.65,
        "offset_ms": 0.0, "high_health": scene != "title",
        "colors": (["#FF0000", "#FFFF00", "#00FF00", "#0000FF"] if scene == "title"
                   else ["#46AAFF", "#FFFFFF", "#46AAFF", "#FFFFFF"]),
        "right_colors": ["#FFAA00", "#FF4400"],
    }


def number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def validate(settings):
    if not isinstance(settings, dict) or settings.get("mode") not in ("off", "solid", "beat", "rainbow"):
        raise ValueError("led mode must be off, solid, beat, or rainbow")
    for key, low, high in (("speed", .25, 8), ("brightness", 0, 1),
                           ("pulse_fraction", .05, 1), ("offset_ms", -2000, 2000)):
        if not number(settings.get(key), low, high):
            raise ValueError(f"key {key} must be {low}–{high}")
    if type(settings.get("high_health")) is not bool:
        raise ValueError("high_health must be true or false")
    for key, count in (("colors", 4), ("right_colors", 2)):
        colors = settings.get(key)
        if not isinstance(colors, list) or len(colors) != count:
            raise ValueError(f"NeoPixel {key} needs {count} colors")
        for color in colors:
            if (not isinstance(color, str) or len(color) != 7 or color[0] != "#"
                    or any(c not in "0123456789abcdefABCDEF" for c in color[1:])):
                raise ValueError("colors must use RGB hex range!!")


def sample(settings, seconds, tempo_points=(), health=0, fallback_bpm=120):
    if settings["mode"] == "off":
        return BLACK
    intensity = settings["brightness"]
    if settings["mode"] in ("beat", "rainbow"):
        seconds -= settings["offset_ms"] / 1000
        if tempo_points:
            index = bisect_right(tempo_points, (seconds, float("inf"))) - 1
            if index < 0:
                return BLACK
            origin, beat_ms = tempo_points[index]
        else:
            origin, beat_ms = 0, 60000 / fallback_bpm
        if seconds < origin:
            return BLACK
        period = beat_ms / 1000 * settings["speed"]
        if settings["mode"] == "rainbow":
            hue = ((seconds - origin) / (4 * period)) % 1
            return tuple(tuple(round(channel * 255) for channel in
                               hsv_to_rgb((index / 4 - hue) % 1, 1, intensity))
                         for index in range(4))
        phase = ((seconds - origin) / period) % 1
        intensity *= max(0, 1 - phase / settings["pulse_fraction"])
    colors = list(settings["colors"])
    if settings["high_health"] and health > 85:
        colors[2:] = settings["right_colors"]
    return tuple(tuple(round(int(color[i:i + 2], 16) * intensity) for i in (1, 3, 5))
                 for color in colors)


def render_preview(pixels):
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (480, 110), (16, 21, 32, 255))
    draw = ImageDraw.Draw(image)
    for index, color in enumerate(pixels):
        x = 60 + index * 120
        draw.ellipse((x - 30, 12, x + 30, 72), fill=(*color, 255), outline="#6E829B", width=2)
        draw.text((x - 12, 86), f"NP{index + 1}", fill="white")
    return image
