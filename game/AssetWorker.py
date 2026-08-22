import os

from PIL import Image

from ui_framework import DESIGN_WIDTH


IMAGE_PATHS = {
    "particle": ("generic", "bg_particle.png"),
    "top": ("generic", "generic_top_bg.png"),
    "logo": ("generic", "logo.png"),
    "title_logo": ("generic", "title_logo.png"),
    "network": ("generic", "network.png"),
    "scroll": ("generic", "scroll_bg_part.png"),
    "entry": ("generic", "entry.png"),
    "entry_cancel": ("generic", "entry_cancel.png"),
    "entry_guest": ("generic", "entry_guest.png"),
    "warning": ("generic", "warn.png"),
    "gameengine": ("generic", "gameengine.png"),
    "produced": ("generic", "produced.png"),
    "epilepsywarning": ("generic", "epilepsywarning.png"),
    "notice": ("generic", "notice.png"),
    "thanksforplaying": ("generic", "thanksforplaying.png"),
    "select_bg": ("music_select", "select_music_bg.png"),
    "select_icon": ("music_select", "select_icon.png"),
    "down_button": ("music_select", "down_bt.png"),
    "previous": ("music_select", "prev_music.png"),
    "next_arrow": ("music_select", "next_arrow.png"),
    "mode_bg": ("mode_select", "mode_bg.png"),
    "mode_2k": ("mode_select", "mode_2k.png"),
    "mode_catch": ("mode_select", "mode_catch.png"),
    "mode_button": ("mode_select", "down_bt.png"),
    "main_layer": ("game", "main_layer.png"),
    "note_0": ("game", "note1.png"),
    "note_1": ("game", "note2.png"),
    "line": ("game", "panjung.png"),
    "health": ("game", "health.png"),
    "health_bg": ("game", "health_bg.png"),
    "perfect": ("game", "perfect.png"),
    "good": ("game", "good.png"),
    "bad": ("game", "bad.png"),
    "miss": ("game", "miss.png"),
    "catcher": ("game", "catch", "catch.png"),
    "catch_object": ("game", "catch", "object.png"),
    "result_bg": ("result", "result_info_bg.png"),
    "result_down_button": ("result", "down_bt.png"),
    "total_result_layout": ("result", "total_result_layout.png"),
    "clear": ("result", "result_clear_text.png"),
    "failed": ("result", "result_failed_text.png"),
}


def load_minigame_assets(base):
    image_root = os.path.join(base, "game", "imgs")
    sources = {
        name: Image.open(os.path.join(image_root, *parts)).convert("RGBA")
        for name, parts in IMAGE_PATHS.items()
    }
    sources["mode_catch"].thumbnail((360, 250), Image.Resampling.LANCZOS)
    sources["catcher"].thumbnail((280, 176), Image.Resampling.LANCZOS)
    sources["catch_object"].thumbnail((96, 96), Image.Resampling.LANCZOS)
    sources["catch_line"] = sources["line"].resize((1000, 33), Image.Resampling.LANCZOS)
    gradient = Image.new("RGBA", (1, 2))
    gradient.putpixel((0, 0), (115, 82, 166, 255))
    gradient.putpixel((0, 1), (198, 158, 244, 255))
    sources["top_gradient"] = gradient.resize((DESIGN_WIDTH, 520), Image.Resampling.BILINEAR)
    sources["next_arrow_left"] = sources["next_arrow"].transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    sweep_width = 150
    sweep_height = sources["select_bg"].height
    sweep_alpha = Image.new("L", (sweep_width, 1))
    sweep_alpha.putdata([
        round(105 * max(0.0, 1.0 - abs(x - sweep_width / 2) / (sweep_width / 2)) ** 2)
        for x in range(sweep_width)
    ])
    sweep = Image.new("RGBA", (sweep_width, sweep_height), (248, 226, 255, 0))
    sweep.putalpha(sweep_alpha.resize((sweep_width, sweep_height), Image.Resampling.NEAREST))
    sources["select_sweep"] = sweep
    for name in ("particle", "scroll"):
        dimmed = sources[name].copy()
        alpha = dimmed.getchannel("A").point(lambda value: round(value * 0.24))
        dimmed.putalpha(alpha)
        sources[f"catch_{name}"] = dimmed
    bgm_root = os.path.join(base, "game", "bgm")
    return sources, bgm_root, os.path.join(bgm_root, "sfx")
