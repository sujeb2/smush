import os
from PIL import Image, ImageChops, ImageDraw, ImageFont
from ui_framework import DESIGN_HEIGHT, DESIGN_WIDTH

IMAGE_PATHS = {
    "particle": ("generic", "bg_particle.png"),
    "top": ("generic", "generic_top_bg.png"),
    "logo": ("generic", "logo.png"),
    "title_logo": ("generic", "title_logo.png"),
    "network": ("generic", "network.png"),
    "scroll": ("generic", "scroll_bg_part.png"),
    "playcard": ("generic", "playcard.png"),
    "entry": ("generic", "entry", "entry.png"),
    "entry_cancel": ("generic", "entry", "entry_cancel.png"),
    "entry_guest": ("generic", "entry", "entry_guest.png"),
    "entry_waiting": ("generic", "entry", "entry_waiting.png"),
    "rival_joined": ("generic", "entry", "rival", "rival_joined.png"),
    "rival_1st": ("game", "rival", "rival_1st.png"),
    "rival_2nd": ("game", "rival", "rival_2nd.png"),
    "warning": ("generic", "warn.png"),
    "information": ("generic", "information.png"),
    "gameengine": ("generic", "gameengine.png"),
    "produced": ("generic", "produced.png"),
    "epilepsywarning": ("generic", "epilepsywarning.png"),
    "notice": ("generic", "notice.png"),
    "thanksforplaying": ("generic", "thanksforplaying.png"),
    "fail_io": ("generic", "fail_io.png"),
    "demonstration_able": ("generic", "demo", "demonstration_abletostart.png"),
    "demonstration_coin": ("generic", "demo", "demonstration_insertcoin.png"),
    "option_text": ("music_select", "setting", "option_text.png"),
    "setting_popup": ("music_select", "setting", "setting_popup.png"),
    "selected_option": ("music_select", "setting", "selected_option.png"),
    "tooltip_setting": ("music_select", "tooltip_setting.png"),
    "select_bg": ("music_select", "select_music_bg.png"),
    "select_icon": ("music_select", "select_icon.png"),
    "scrollspeed_warn": ("music_select", "scrollspeed_warn.png"),
    "down_button": ("music_select", "down_bt.png"),
    "previous": ("music_select", "prev_music.png"),
    "next_arrow": ("music_select", "next_arrow.png"),
    "extra_mode_warning": ("music_select", "extra_mode_warning.png"),
    "extra_stage_ui": ("music_select", "extra_stage_ui.png"),
    "main_layer_4k_extra": ("game", "4k_extra", "main_layer.png"),
    "note_extra_0": ("game", "4k_extra", "sidenote_1.png"),
    "note_extra_1": ("game", "4k_extra", "sidenote_2.png"),
    "lane_help_extra_0": ("game", "4k_extra", "sidenote_1_help.png"),
    "lane_help_extra_1": ("game", "4k_extra", "sidenote_2_help.png"),
    "mode_bg": ("mode_select", "mode_bg.png"),
    "mode_4k": ("mode_select", "mode_4k.png"),
    "mode_catch": ("mode_select", "mode_catch.png"),
    "mode_button": ("mode_select", "down_bt.png"),
    "main_layer": ("game", "main_layer.png"),
    "main_layer_4k": ("game", "4k", "main_layer.png"),
    "note_0": ("game", "note1.png"),
    "note_1": ("game", "note2.png"),
    "note_4k_0": ("game", "4k", "4k_note1.png"),
    "note_4k_1": ("game", "4k", "4k_note2.png"),
    "lane_help_2k_0": ("game", "lane1_help.png"),
    "lane_help_2k_1": ("game", "lane2_help.png"),
    "lane_help_4k_0": ("game", "4k", "lane1_help.png"),
    "lane_help_4k_1": ("game", "4k", "lane2_help.png"),
    "how_to_play_4k": ("game", "howtoplay", "4k.png"),
    "how_to_play_extra": ("game", "howtoplay", "extra.png"),
    "line": ("game", "panjung.png"),
    "health": ("game", "health.png"),
    "health_bg": ("game", "health_bg.png"),
    "perfect": ("game", "perfect.png"),
    "good": ("game", "good.png"),
    "bad": ("game", "bad.png"),
    "miss": ("game", "miss.png"),
    "catcher": ("game", "catch", "catch.png"),
    "catch_object": ("game", "catch", "object.png"),
    "catch_health": ("game", "catch", "health_bar.png"),
    "catch_health_bg": ("game", "catch", "health_bg.png"),
    "result_bg": ("result", "result_info_bg.png"),
    "result_down_button": ("result", "down_bt.png"),
    "total_result_layout": ("result", "total_result_layout.png"),
    "clear": ("result", "result_clear_text.png"),
    "failed": ("result", "result_failed_text.png"),
    "rank_x": ("result", "rank", "Ranking-X@2x.png"),
    "rank_s": ("result", "rank", "Ranking-S@2x.png"),
    "rank_a": ("result", "rank", "Ranking-A@2x.png"),
    "rank_b": ("result", "rank", "Ranking-B@2x.png"),
    "rank_c": ("result", "rank", "Ranking-C@2x.png"),
    "rank_d": ("result", "rank", "Ranking-D@2x.png"),
}


def _remove_edge_outline(source, border_width=12):
    image = source.copy().convert("RGBA")
    alpha = image.getchannel("A")
    top_pixels = [x for x in range(image.width) if alpha.getpixel((x, 0))]
    radius = top_pixels[0] if top_pixels else min(image.height // 4, 60)
    fill = image.getpixel((image.width // 2, image.height // 2))
    cleaned = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(cleaned)
    draw.rounded_rectangle(
        (0, 0, image.width + radius, image.height - 1), radius=radius, fill=fill,
    )
    inner_mask = Image.new("L", image.size, 0)
    mask_draw = ImageDraw.Draw(inner_mask)
    mask_draw.rounded_rectangle(
        (
            border_width,
            border_width,
            image.width - border_width - 1,
            image.height - border_width - 1,
        ),
        radius=max(1, radius - border_width),
        fill=255,
    )
    cleaned.paste(image, (0, 0), inner_mask)
    return cleaned


def _fit_mode_icon(source):
    visible_alpha = source.getchannel("A").point(lambda value: 255 if value > 4 else 0)
    bounds = visible_alpha.getbbox()
    image = source.crop(bounds) if bounds is not None else source.copy()
    image.thumbnail((560, 230), Image.Resampling.LANCZOS)
    frame = Image.new("RGBA", (600, 250), (0, 0, 0, 0))
    frame.alpha_composite(image, ((frame.width - image.width) // 2, (frame.height - image.height) // 2))
    return frame


def _extra_stage_lettering(template, box):
    label = template.crop(box)
    red, green, blue, alpha = label.split()
    ink = ImageChops.lighter(ImageChops.lighter(red, green), blue).point(lambda value: 255 if value > 80 else 0)
    label.putalpha(ImageChops.multiply(alpha, ink))
    return label.crop(label.getchannel("A").getbbox())


def load_minigame_assets(base):
    image_root = os.path.join(base, "game", "imgs")
    sources = {
        name: Image.open(os.path.join(image_root, *parts)).convert("RGBA")
        for name, parts in IMAGE_PATHS.items()
    }
    sources["select_bg"] = _remove_edge_outline(sources["select_bg"])
    # Reflow the template for the taller display without stretching its lettering.
    template = sources["extra_stage_ui"]
    sources["extra_stage_header"] = _extra_stage_lettering(template, (0, 0, 1080, 130))
    sources["extra_stage_settings_hint"] = _extra_stage_lettering(template, (0, 130, 1080, 180))
    sources["extra_stage_footer"] = _extra_stage_lettering(template, (0, 1355, 1080, 1425))
    for index, name in enumerate(("easy", "normal", "hard")):
        sources[f"extra_stage_{name}"] = _extra_stage_lettering(
            template, (index * 360, 1280, (index + 1) * 360, 1350),
        )
    shade = Image.new("RGBA", (1, DESIGN_HEIGHT))
    for y in range(DESIGN_HEIGHT):
        opacity = round(240 * max(0, min(1, (y / DESIGN_HEIGHT * 1450 - 1140) / 310)))
        shade.putpixel((0, y), (0, 0, 0, opacity))
    sources["extra_stage_ui"] = shade.resize((DESIGN_WIDTH, DESIGN_HEIGHT))
    extra_background = Image.new("RGBA", (1, DESIGN_HEIGHT))
    for y in range(DESIGN_HEIGHT):
        progress = y / (DESIGN_HEIGHT - 1)
        extra_background.putpixel((0, y), tuple(
            round(start + (end - start) * progress)
            for start, end in zip((102, 74, 152, 255), (190, 148, 236, 255))
        ))
    sources["extra_stage_background"] = extra_background.resize((DESIGN_WIDTH, DESIGN_HEIGHT))
    sources["previous"] = _remove_edge_outline(sources["previous"])
    for name in ("mode_4k", "mode_catch"):
        sources[name] = _fit_mode_icon(sources[name])
    #mode_4k = Image.new("RGBA", (360, 250), (0, 0, 0, 0))
    #draw = ImageDraw.Draw(mode_4k)
    #for lane in range(4):
    #    left = 42 + lane * 68
    #    draw.rounded_rectangle((left, 28, left + 58, 205), radius=10, fill=(51, 38, 73, 235), outline=(198, 158, 244, 255), width=4)
    #font_path = os.path.join(base, "files", "fonts", "Novecentosanswide-DemiBold.otf")
    #try:
    #    font = ImageFont.truetype(font_path, 48)
    #except OSError:
    #    font = ImageFont.load_default()
    #draw.text((180, 120), "4K", font=font, fill=(136, 245, 255, 255), anchor="mm")
    sources["catcher"].thumbnail((280, 176), Image.Resampling.LANCZOS)
    sources["catch_object"].thumbnail((96, 96), Image.Resampling.LANCZOS)
    sources["catch_line"] = sources["line"].resize((1000, 33), Image.Resampling.LANCZOS)
    sources["line_4k"] = sources["line"].resize((734, 33), Image.Resampling.LANCZOS)
    sources["line_4k_extra"] = sources["line"].resize((1080, 33), Image.Resampling.LANCZOS)
    center = sources["main_layer_4k_extra"]
    extra_field = Image.new("RGBA", (1080, center.height))
    extra_field.alpha_composite(center.crop((0, 0, 169, center.height)), (0, 0))
    extra_field.alpha_composite(center, (169, 0))
    extra_field.alpha_composite(center.crop((579, 0, 745, center.height)), (914, 0))
    sources["main_layer_4k_extra"] = extra_field
    sources["health_4k"] = sources["health"].resize((sources["health"].width, 734), Image.Resampling.LANCZOS)
    sources["health_bg_4k"] = sources["health_bg"].resize((sources["health_bg"].width, 734), Image.Resampling.LANCZOS)
    for rank in ("x", "s", "a", "b", "c", "d"):
        sources[f"rank_{rank}"].thumbnail((190, 220), Image.Resampling.LANCZOS)
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
