import math
import os
import time

from PIL import Image, ImageDraw, ImageFont

from game.rules import EVENT_TRACK_COUNT, TEXT_SCALE
from ui_framework import DESIGN_HEIGHT, DESIGN_WIDTH

TEXT_CACHE_LIMIT = 512

# Music select wheel: resting neighbour slots (±1, ±2) plus off-screen slots (±3) that cards
# rotate in from, and the centre card (0) that the selected song turns into.
SELECTION_WHEEL_REACH = 3
SELECTION_WHEEL_SECONDS = 0.32
_SELECTION_WHEEL_POINTS = {
    -3: (1050, 850), -2: (950, 925), -1: (850, 1000), 0: (560, 1248),
    1: (850, 1497), 2: (950, 1660), 3: (1050, 1823),
}


def _selection_wheel_point(offset):
    """Position on a smooth (Catmull-Rom) arc through the wheel slots, for a fractional slot."""
    reach = SELECTION_WHEEL_REACH
    offset = min(reach, max(-reach, offset))
    index = min(reach - 1, math.floor(offset))
    t = offset - index
    p0, p1, p2, p3 = (_SELECTION_WHEEL_POINTS[min(reach, max(-reach, slot))]
                      for slot in (index - 1, index, index + 1, index + 2))
    return tuple(
        0.5 * (2 * b + (c - a) * t + (2 * a - 5 * b + 4 * c - d) * t * t + (3 * b - a - 3 * c + d) * t ** 3)
        for a, b, c, d in zip(p0, p1, p2, p3)
    )


def _selection_wheel_opacity(offset):
    """Cards fade as they turn into the centre card and as they leave past the outer slots."""
    distance = abs(offset)
    return min(1.0, distance) * min(1.0, max(0.0, SELECTION_WHEEL_REACH - distance))

def _is_japanese_title(title):
    return any(
        "\u3040" <= character <= "\u30ff" or "\u3400" <= character <= "\u9fff"
        or "\uff65" <= character <= "\uff9f"
        for character in title
    )


def _extra_stage_levels(charts, selected=None):
    """Place available charts under the template's EASY, NORMAL, HARD labels."""
    slots = [None, None, None]
    remaining = []
    for chart in charts:
        name = chart.difficulty.casefold()
        if any(word in name for word in ("easy", "beginner", "novice")):
            slot = 0
        elif any(word in name for word in ("normal", "standard")):
            slot = 1
        elif any(word in name for word in ("hard", "another", "expert", "insane")):
            slot = 2
        else:
            remaining.append(chart)
            continue
        if slots[slot] is None or chart is selected or (slots[slot] is not selected and chart.level > slots[slot].level):
            slots[slot] = chart
    remaining = sorted(remaining, key=lambda item: item.level)[-3:]
    free_slots = [index for index, chart in enumerate(slots) if chart is None]
    for index, chart in zip(free_slots[-len(remaining):], remaining):
        slots[index] = chart
    return slots


class MinigameSceneMixin:
    def _build_scene(self):
        if not self.running:
            return
        if self.scene not in ("select", "title_select"):
            self._close_select_video()
        if self.scene not in ("game", "demonstration"):
            self._close_game_video()
        self._prepare_scene()
        self.scene_photos = []
        self.scroll_items = []
        self.particle_item = None
        self.fade_item = None
        self.select_time_item = None
        self.select_media_item = None
        self.mode_time_item = None
        self.entry_time_item = None
        self.result_time_item = None
        self.total_result_time_item = None
        self.select_time_shown = None
        self.mode_time_shown = None
        self.entry_time_shown = None
        self.result_time_shown = None
        self.total_result_time_shown = None
        self.timer_sfx_value = None
        self.next_morph_items = []
        self.title_morph_logo_item = None
        self.title_morph_top_logo_item = None
        self.title_morph_press_item = None
        self.title_morph_logo_frames = ()
        self.title_morph_top_logo_frames = ()
        self.title_morph_press_frames = ()
        self.title_select_offset = 0.0
        self.title_entry_morph_started = None
        self.title_entry_logo_item = None
        self.title_entry_logo_frames = ()
        self.title_entry_logo_frame_shown = -1
        self.selection_scroll_started = None
        self.selection_card_swapped = True
        self.selection_preview_items = []
        self.selection_card_bg_item = None
        self.selection_heading_item = None
        self.selection_sweep_item = None
        self.scroll_speed_warning_item = None
        self.scroll_speed_warning_offset = 0.0
        self.select_morph_in_started = None
        self.select_morph_in_offset = 0.0
        self.down_button_item = None
        self.entry_card_item = None
        self.entry_card_frames = ()
        self.entry_card_frame_shown = -1
        self.warning_item = None
        self.warning_frames = ()
        self.warning_frame_shown = -1
        self.mode_icon_item = None
        self.mode_icon_frames = ()
        self.mode_icon_frame_shown = -1
        self.mode_icon_animation_started = None
        self.mode_morph_in_started = None
        self.mode_morph_in_offset = 0.0
        self.mode_description_item = None
        self.next_arrow_items = []
        self.result_value_items = {}
        self.result_values_shown = {}
        self.combo_label_item = None
        self.combo_item = None
        self.catch_combo_item = None
        self.catch_score_item = None
        self.catcher_item = None
        self.catch_bursts = []
        self.catch_burst_frames = ()
        self.lane_help_items = []
        self.lane_help_started = {}
        self.lane_help_frame_shown = {}
        self.demonstration_item = None
        self.demonstration_frames = ()
        self.demonstration_frame_shown = -1
        self.demonstration_overlay_name = None
        self.health_fill_item = None
        self.health_dynamic_photo = None
        self.health_visible_state = None
        self.result_banner_frames = ()
        self.result_banner_frame_shown = -1
        self.result_rank_item = None
        self.result_rank_frames = ()
        self.result_rank_frame_shown = -1
        self.result_morph_item = None
        self.result_morph_frames = ()
        self.result_morph_frame_shown = -1
        self.total_result_card_items = []
        self.total_result_cards_revealed = 0
        self.total_result_value_item = None
        self.total_result_value_shown = None
        self.ci_items = {}
        self.ci_motion_state = {}
        self.ending_logo_item = None
        self.ending_thanks_item = None
        self.ending_accent_item = None
        self.ending_motion_state = {}
        self.game_media_item = None
        self.credit_item = None
        if self.scene == "preload":
            self._build_preload_scene()
            return
        self.canvas.create_rectangle(
            self._x(0), self._y(0), self._x(DESIGN_WIDTH), self._y(DESIGN_HEIGHT),
            fill="#bd98e8", outline="",
        )
        if self.scene in ("game", "demonstration"):
            self._build_game()
            if self.scene == "demonstration":
                self._build_demonstration_overlay()
            elif getattr(self, "how_to_play_mode", None) is not None:
                self._build_how_to_play()
            return
        if self.scene == "select" and getattr(self, "extra_stage_active", False):
            self._build_select()
            return
        self._image("top_gradient", 0, 0, anchor="nw", tags=("background",))
        if self.scene == "ci":
            self._build_header()
            self._build_ci()
            return
        self._build_common_background()
        if self.scene == "title":
            self._build_title()
        elif self.scene == "entry":
            self._build_entry()
        elif self.scene == "warning":
            self._build_warning()
        elif self.scene == "mode_select":
            self._build_mode_select()
        elif self.scene == "title_select":
            self._build_title_select_morph()
        elif self.scene == "select":
            self._build_select()
        elif self.scene == "next":
            self._build_next()
        elif self.scene == "result":
            self._build_result()
            if self.result_select_morph_started is not None:
                self.result_select_card_offset = 0.0
                self._create_result_select_morph()
        elif self.scene == "total_result":
            self._build_total_result()
        elif self.scene == "game_ended":
            self._build_game_ended()
        elif self.scene == "ending":
            self._build_ending()

    def _photo(self, source):
        photo = self._scaled_photo(source)
        self.scene_photos.append(photo)
        return photo

    def _asset_photo(self, name):
        key = name, round(self.scale, 5)
        if key not in self.photo_cache:
            self.photo_cache[key] = self._scaled_photo(self.sources[name])
        return self.photo_cache[key]

    def _text(self, text, size, color="white", align="center"):
        key = text, size, color, align, round(self.scale, 5)
        photo = self.text_cache.get(key)
        if photo is not None:
            self.text_cache.move_to_end(key)
            return photo
        photo = self._text_photo(
            text,
            round(size * TEXT_SCALE),
            color=color,
            font_path=self.novecento_demibold_font_path,
            align=align,
        )
        self.text_cache[key] = photo
        # Score and combo text changes every hit; bound the cache so evicted
        # images (and their GPU textures) can be released.
        while len(self.text_cache) > TEXT_CACHE_LIMIT:
            self.text_cache.popitem(last=False)
        return photo

    def _image(self, name, x, y, anchor="center", tags=()):
        return self.canvas.create_image(
            self._x(x), self._y(y), image=self._asset_photo(name), anchor=anchor, tags=tags,
        )

    def _text_image(self, text, size, x, y, color="white", anchor="center", align="center", tags=()):
        return self.canvas.create_image(
            self._x(x), self._y(y), image=self._text(text, size, color, align), anchor=anchor, tags=tags,
        )

    def _build_common_background(self):
        self.particle_base_y = 420
        self.particle_item = self._image("particle", 540, self.particle_base_y, anchor="n", tags=("particle",))
        scroll_photo = self._asset_photo("scroll")
        for y in (520, 1510):
            for index in range(2):
                item = self.canvas.create_image(
                    self._x(index * self.sources["scroll"].width), self._y(y), image=scroll_photo,
                    anchor="nw", tags=("scroll",),
                )
                self.scroll_items.append((item, index, y))
        self._build_header()

    def _build_header(self):
        track_label = self._track_key()
        if track_label != "FINAL":
            track_label = f"TRACK {track_label}"
        labels = {
            "title": ("TWO", "BTN"),
            "ci": ("TWO", "BTN"),
            "entry": ("ENTRY", ""),
            "warning": ("", ""),
            "mode_select": ("MODE", "SELECT"),
            "title_select": (track_label, "SELECT"),
            "select": (track_label, "SELECT"),
            "next": (track_label, "NEXT"),
            "game": (track_label, "GAME"),
            "demonstration": (track_label, "GAME"),
            "result": (track_label, "RESULT"),
            "total_result": ("ENDING", "<3"),
            "game_ended": ("ENDING", "<3"),
            "ending": ("ENDING", "<3"),
        }
        first_label, second_label = labels[self.scene]
        self._image("top", 63, 112, anchor="nw", tags=("header",))
        self._text_image(first_label, 28, 183, 147, tags=("header",))
        self._text_image(second_label, 27, 423, 147, tags=("header",))
        self._text_image("VER 1.0-E", 22, 975, 34, anchor="ne", tags=("header",))
        self._image("network", 1020, 28, anchor="ne", tags=("header",))
        self._text_image(
            (f"{self.settings['mode']} MODE [EXTRA]" if getattr(self, "extra_stage_active", False)
             else f"{self.settings['mode']} MODE [{self._track_position()}/{EVENT_TRACK_COUNT}]"),
            22, 1018, 74, anchor="ne", tags=("header",),
        )
        self.credit_item = self._text_image(
            self._credit_status_text(), 20, 63, 34, anchor="nw", tags=("header", "credit_status"),
        )

    def _credit_status_text(self):
        if self.coins_per_credit == 0:
            return "FREEPLAY"
        return f"{self.coin_count}/{self.coins_per_credit} CREDIT {self.credit_count}"

    def _refresh_credit_status(self):
        if self.credit_item is not None:
            self.canvas.itemconfigure(self.credit_item, image=self._text(self._credit_status_text(), 20))

    def _build_title(self):
        self._image("logo", 540, 270, tags=("title",))
        self._image("title_logo", 540, 1000, tags=("title",))
        self._text_image("PRESS ANY BUTTON", 36, 540, 1300, tags=("title",))
        self.serial_failure_item = None
        if self.serial_connection_failed:
            self._show_serial_failure()
        self._text_image("© sujeb2 2022-2026", 14, 540, 1880, tags=("title",))

    def _build_ci(self):
        self._image("logo", 540, 270, tags=("ci",))
        self.canvas.create_rectangle(
            self._x(0), self._y(440), self._x(DESIGN_WIDTH), self._y(DESIGN_HEIGHT),
            fill="black", outline="", tags=("ci",),
        )
        positions = {
            "epilepsywarning": (540, 1080),
            "notice": (540, 1080),
            "produced": (540, 1035),
            "gameengine": (540, 1305),
        }
        for name, (x, y) in positions.items():
            self.ci_items[name] = self.canvas.create_image(
                self._x(x), self._y(y), image="", anchor="center", tags=("ci",),
            )

    def _entry_card_sources(self, name="entry"):
        if name in self.entry_card_source_frames:
            return self.entry_card_source_frames[name]
        source = self.sources[name]
        frames = []
        for index in range(24):
            progress = index / 23
            eased = 1 - pow(1 - progress, 3)
            if progress < 0.78:
                width_scale = 0.06 + 1.02 * (1 - pow(1 - progress / 0.78, 3))
            else:
                width_scale = 1.08 + (1.0 - 1.08) * ((progress - 0.78) / 0.22)
            height_scale = 0.84 + 0.16 * eased
            width = max(1, round(source.width * width_scale))
            height = max(1, round(source.height * height_scale))
            frame = source.resize((width, height), Image.Resampling.LANCZOS)
            opacity = min(1.0, progress / 0.16)
            alpha = frame.getchannel("A").point(lambda value, factor=opacity: round(value * factor))
            frame.putalpha(alpha)
            frames.append(frame)
        self.entry_card_source_frames[name] = tuple(frames)
        return self.entry_card_source_frames[name]

    def _entry_cancel_sources(self):
        if self.entry_cancel_source_frames:
            return self.entry_cancel_source_frames
        source = self.sources["entry_cancel"]
        frames = []
        for index in range(24):
            progress = index / 23
            opacity = 0.78 + 0.22 * (0.5 + 0.5 * math.cos(progress * math.pi * 2))
            frame = source.copy()
            alpha = frame.getchannel("A").point(lambda value, factor=opacity: round(value * factor))
            frame.putalpha(alpha)
            frames.append(frame)
        self.entry_cancel_source_frames = tuple(frames)
        return self.entry_cancel_source_frames

    def _warning_sources(self):
        if self.warning_source_frames:
            return self.warning_source_frames
        source = self.sources["warning"]
        frames = []
        for index in range(24):
            progress = index / 23
            if progress < 0.72:
                scale = 0.68 + 0.38 * (1 - pow(1 - progress / 0.72, 3))
            else:
                scale = 1.06 + (1.0 - 1.06) * ((progress - 0.72) / 0.28)
            width = max(1, round(source.width * scale))
            height = max(1, round(source.height * scale))
            frame = source.resize((width, height), Image.Resampling.LANCZOS)
            opacity = min(1.0, progress / 0.18)
            alpha = frame.getchannel("A").point(lambda value, factor=opacity: round(value * factor))
            frame.putalpha(alpha)
            frames.append(frame)
        self.warning_source_frames = tuple(frames)
        return self.warning_source_frames

    def _warning_select_sources(self):
        if self.warning_select_source_frames:
            return self.warning_select_source_frames
        warning_source = self.sources["warning"]
        select_source = self.sources["select_bg"]
        frames = []
        for index in range(24):
            progress = index / 23
            eased = progress * progress * (3 - 2 * progress)
            width = round(warning_source.width + (select_source.width - warning_source.width) * eased)
            height = round(warning_source.height + (select_source.height - warning_source.height) * eased)
            warning_frame = warning_source.resize((width, height), Image.Resampling.LANCZOS)
            select_frame = select_source.resize((width, height), Image.Resampling.LANCZOS)
            frame = Image.blend(warning_frame, select_frame, eased)
            frames.append(frame)
        self.warning_select_source_frames = tuple(frames)
        return self.warning_select_source_frames

    def _warning_mode_sources(self):
        if self.warning_mode_source_frames:
            return self.warning_mode_source_frames
        warning_source = self.sources["warning"]
        mode_source = self.sources["mode_bg"]
        frames = []
        for index in range(30):
            progress = index / 29
            eased = progress * progress * (3 - 2 * progress)
            width = round(warning_source.width + (mode_source.width - warning_source.width) * eased)
            height = round(warning_source.height + (mode_source.height - warning_source.height) * eased)
            warning_frame = warning_source.resize((width, height), Image.Resampling.LANCZOS)
            mode_frame = mode_source.resize((width, height), Image.Resampling.LANCZOS)
            frames.append(Image.blend(warning_frame, mode_frame, eased))
        self.warning_mode_source_frames = tuple(frames)
        return self.warning_mode_source_frames

    def _build_entry(self):
        self._image("logo", 540, 270, tags=("entry",))
        self._text_image("ENTRY", 54, 70, 755, anchor="w", tags=("entry",))
        if not getattr(self, "two_player", False):
            self._text_image("TIME LEFT", 18, 970, 725, tags=("entry", "entry_time"))
            remaining = max(0, int(self.entry_deadline - time.monotonic() + 0.999))
            self.entry_time_item = self._text_image(str(remaining), 52, 970, 780, tags=("entry_time",))
            self.entry_time_shown = remaining
        self.entry_card_frames = tuple(self._photo(frame) for frame in self._entry_card_sources())
        self.entry_card_item = self.canvas.create_image(
            self._x(540), self._y(1180), image=self.entry_card_frames[0], anchor="center", tags=("entry_card",),
        )
        if getattr(self, "two_player", False):
            self.entry_waiting_visible = False
            joined = self._asset_photo("rival_joined")
            self.entry_joined_items = (
                self.canvas.create_image(self._x(440), self._y(1030), image=joined, state="hidden", tags=("entry_joined",)),
                self.canvas.create_image(self._x(640), self._y(1030), image=joined, state="hidden", tags=("entry_joined",)),
            )
            self._refresh_entry_joined()

    def _build_warning(self):
        self._image("logo", 540, 270, tags=("warning",))
        self.warning_frames = tuple(self._photo(frame) for frame in self._warning_sources())
        self.warning_item = self.canvas.create_image(
            self._x(540), self._y(1120), image=self.warning_frames[0], anchor="center", tags=("warning_card",),
        )

    def _mode_description_photo(self):
        text = (
            "네 개의 버튼과 레인을 이용하여서 노트를 처리하는 모드"
            if self.mode_index == 0
            else "떨어지는 물건을 받아 처리하는 모드"
        )
        photo = self._text_photo(
            text, round(27 * TEXT_SCALE), color="white", font_path=self.display_font_path, align="center",
        )
        self.scene_photos.append(photo)
        return photo

    def _update_mode_description(self):
        if self.mode_description_item is not None:
            self.canvas.itemconfigure(self.mode_description_item, image=self._mode_description_photo())

    def _build_mode_select(self):
        self._image("logo", 540, 270, tags=("mode_select",))
        self._text_image("MODE SELECT", 54, 70, 755, anchor="w", tags=("mode_select",))
        self._text_image("TIME LEFT", 18, 970, 725, tags=("mode_select",))
        remaining = max(0, int(self.mode_select_deadline - time.monotonic() + 0.999))
        self.mode_time_item = self._text_image(str(remaining), 52, 970, 780, tags=("mode_select",))
        self.mode_time_shown = remaining
        self._image("mode_bg", 0, 1015, anchor="nw", tags=("mode_select",))
        icon_name = f"mode_{('4k', 'catch')[self.mode_index]}"
        self.mode_icon_item = self._image(icon_name, 540, 1160, tags=("mode_select", "mode_icon"))
        self._text_image("MODE DESCRIPTION", 29, 540, 1425, tags=("mode_select",))
        self.mode_description_item = self.canvas.create_image(
            self._x(540), self._y(1490), image=self._mode_description_photo(), tags=("mode_select",),
        )
        self._image("mode_button", 540, 1845, tags=("mode_select",))

    def _build_title_select_morph(self):
        logo_frames = []
        top_logo_frames = []
        press_frames = []
        background = (189, 152, 232)
        for index in range(12):
            progress = index / 11
            scale = 1.0 - 0.52 * progress
            source = self.sources["title_logo"]
            width = max(1, round(source.width * scale))
            height = max(1, round(source.height * scale))
            frame = source.resize((width, height), Image.Resampling.LANCZOS)
            alpha = frame.getchannel("A").point(lambda value, opacity=1.0 - progress: round(value * opacity))
            frame.putalpha(alpha)
            logo_frames.append(self._photo(frame))
            top_frame = self.sources["logo"].copy()
            top_alpha = top_frame.getchannel("A").point(lambda value, opacity=1.0 - progress: round(value * opacity))
            top_frame.putalpha(top_alpha)
            top_logo_frames.append(self._photo(top_frame))
            color = tuple(round(255 + (channel - 255) * progress) for channel in background)
            press_frames.append(self._text("PRESS EITHER BUTTON", 36, f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"))
        self.title_morph_logo_frames = tuple(logo_frames)
        self.title_morph_top_logo_frames = tuple(top_logo_frames)
        self.title_morph_press_frames = tuple(press_frames)
        self.title_morph_top_logo_item = self.canvas.create_image(
            self._x(540), self._y(270), image=top_logo_frames[0], anchor="center", tags=("title_morph",),
        )
        self.title_morph_logo_item = self.canvas.create_image(
            self._x(540), self._y(1000), image=logo_frames[0], anchor="center", tags=("title_morph",),
        )
        self.title_morph_press_item = self.canvas.create_image(
            self._x(540), self._y(1735), image=press_frames[0], anchor="center", tags=("title_morph",),
        )
        self._build_select()
        if self.select_time_item is not None:
            self.canvas.itemconfigure(self.select_time_item, state="hidden")
        self.title_select_offset = 1120.0
        self.canvas.move("select", self.title_select_offset * self.scale, 0)

    def _build_select(self):
        if getattr(self, "extra_stage_active", False):
            self._build_extra_select()
            return
        heading = "MUSIC SELECT" if self.selection_phase == "song" else "DIFFICULTY SELECT"
        self.selection_heading_item = self._text_image(heading, 54, 70, 755, anchor="w", tags=("select",))
        self._text_image("TIME LEFT", 18, 970, 725, tags=("select", "select_time"))
        remaining = max(0, int(self.select_deadline - time.monotonic() + 0.999))
        self.select_time_item = self._text_image(str(remaining), 52, 970, 780, tags=("select_time",))
        self.select_time_shown = remaining
        self._build_selection_shell(("select", "select_shell"))
        self._build_selection_list(("select", "select_list", "select_dynamic"))
        self._image("tooltip_setting", 70, 835, anchor="nw", tags=("select",))
        if getattr(self, "settings_phase", None) is not None:
            self._build_settings_overlay()

    def _extra_stage_text(self, value, size, x, y, *, font_path, color="white", tracking=0,
                          tags=("select", "select_list")):
        font = ImageFont.truetype(font_path, size)
        width = sum(font.getlength(character) for character in value) + tracking * max(0, len(value) - 1)
        if width > 950:
            factor = 950 / width
            size = max(12, int(size * factor))
            tracking *= factor
            font = ImageFont.truetype(font_path, size)
            width = sum(font.getlength(character) for character in value) + tracking * max(0, len(value) - 1)
        box = font.getbbox(value)
        source = Image.new("RGBA", (math.ceil(width) + 16, box[3] - box[1] + 16))
        draw = ImageDraw.Draw(source)
        cursor = 8
        for character in value:
            draw.text((cursor, 8 - box[1]), character, font=font, fill=color)
            cursor += font.getlength(character) + tracking
        photo = self._scaled_photo(source)
        self.scene_photos.append(photo)
        return self.canvas.create_image(
            self._x(x), self._y(y), image=photo, anchor="center",
            tags=tags,
        )

    def _build_extra_select(self):
        self._image("extra_stage_background", 0, 0, anchor="nw", tags=("select",))
        self._prepare_select_media(self.track, reset_video=True)
        self.select_media_item = self.canvas.create_image(
            self._x(0), self._y(0), image=self.select_media_photo or "",
            anchor="nw", tags=("select", "extra_stage_media"),
        )
        self._image("extra_stage_ui", 0, 0, anchor="nw", tags=("select",))
        self._image("extra_stage_header", 540, 132, tags=("select",))
        self._text_image("TIME LEFT", 16, 955, 80, tags=("select", "select_time"))
        remaining = max(0, min(30, math.ceil(self.select_deadline - time.monotonic())))
        self.select_time_item = self._text_image(str(remaining), 64, 955, 145, tags=("select_time",))
        self.select_time_shown = remaining
        self._image("extra_stage_settings_hint", 540, 202, tags=("select",))
        self._image("extra_stage_footer", 540, 1840, tags=("select",))
        self._build_selection_list(("select", "select_list"))
        if getattr(self, "settings_phase", None) is not None:
            self._build_settings_overlay()

    def _build_extra_selection_list(self):
        self._prepare_select_media(self.track)
        font_root = os.path.join(self.base, "files", "fonts")
        ginza = os.path.join(font_root, "GinzaNarrow-Medium.otf")
        japanese_title = _is_japanese_title(self.track.title)
        title_font = os.path.join(font_root, "nagino.otf") if japanese_title else ginza
        self._extra_stage_text(self.track.artist.upper(), 50, 540, 1385, font_path=ginza, tracking=14)
        title = self.track.title if japanese_title else self.track.title.upper()
        self._extra_stage_text(title, 100, 540, 1500, font_path=title_font, tracking=0 if japanese_title else 24)
        slots = _extra_stage_levels(self.song_groups[self.song_index], selected=self.track)
        for x, name, color, chart in zip((180, 540, 900), ("easy", "normal", "hard"),
                                        ("#80ff84", "#ffdb80", "#ff8084"), slots):
            selected = chart is self.track
            label = self.sources[f"extra_stage_{name}"]
            if selected or chart is None:
                tinted = Image.new("RGBA", label.size, "white" if selected else "#786d86")
                tinted.putalpha(label.getchannel("A"))
                label = tinted
            self.canvas.create_image(self._x(x), self._y(1745), image=self._photo(label),
                                     tags=("select", "select_list"))
            if chart is not None:
                self._extra_stage_text(str(chart.level), 88, x, 1665,
                                       font_path=self.novecento_demibold_font_path,
                                       color=color if selected else "white", tracking=10)

    def _build_selection_shell(self, tags):
        self.selection_card_bg_item = self._image("select_bg", 32, 1110, anchor="nw", tags=tags)
        self.down_button_item = self._image("down_button", 540, self.down_button_base_y, tags=tags)

    def _selection_choices(self):
        if self.selection_phase == "song":
            return tuple(group[0].title for group in self.song_groups), self.song_index
        return tuple(chart.difficulty for chart in self.song_groups[self.song_index]), self.difficulty_index

    def _build_selection_list(self, tags):
        if getattr(self, "extra_stage_active", False):
            self._build_extra_selection_list()
            return
        self._build_selection_previews(tags)
        self._build_selection_card(tags)

    def _build_selection_previews(self, tags, direction=0):
        """Neighbour cards on the wheel; with a direction they start one slot back for the rotation."""
        choices, selected = self._selection_choices()
        entries = {}
        # Nearest slots first (+1 before -1) so short lists that repeat a choice keep the copy
        # the resting layout always showed.
        reach = range(-SELECTION_WHEEL_REACH, SELECTION_WHEEL_REACH + 1)
        for offset in sorted(reach, key=lambda value: (abs(value), value < 0)):
            choice_index = (selected + offset) % len(choices)
            start = offset + direction
            if choice_index in entries or min(abs(start), abs(offset)) > 2:
                continue
            # At rest the selection is the centre card; while turning it travels in from its old slot.
            if choice_index == selected and not (direction and offset == 0):
                continue
            entries[choice_index] = (start, offset)
        self.selection_preview_items = []
        self.selection_choice_count = len(choices)
        # Same stacking as the resting layout: outer cards above inner ones.
        for choice_index, (start, end) in sorted(entries.items(), key=lambda entry: abs(entry[1][1])):
            x, y = _selection_wheel_point(start)
            card = self._image("previous", x, y, tags=(*tags, "select_preview"))
            label = self._text_image(choices[choice_index].upper(), 27, x, y + self._selection_label_shift(start),
                                     color="#ead7fb", tags=(*tags, "select_preview"))
            self.selection_preview_items.append((card, label, start, end))
        if direction:
            self._place_selection_previews(0.0)
        # Neighbour cards are rebuilt after the centre card, so lift its overlays back above them.
        self.canvas.tag_raise("select_overlay")

    def _selection_label_shift(self, offset):
        """The -2 card covers the top of the -1 card; keep the -1 name in the strip still visible."""
        if getattr(self, "selection_choice_count", 0) < 5:
            return 0.0
        half_height = self.sources["previous"].height / 2
        visible_top = _SELECTION_WHEEL_POINTS[-2][1] + half_height
        visible_bottom = _SELECTION_WHEEL_POINTS[-1][1] + half_height
        shift = (visible_top + visible_bottom) / 2 - _SELECTION_WHEEL_POINTS[-1][1]
        return shift * max(0.0, 1.0 - abs(offset + 1))

    def _place_selection_previews(self, progress):
        # Cards squash mid-step as if the wheel turns them past the viewer.
        squash = 1.0 - 0.32 * math.sin(math.pi * progress)
        for card, label, start, end in self.selection_preview_items:
            offset = start + (end - start) * progress
            x, y = _selection_wheel_point(offset)
            opacity = _selection_wheel_opacity(offset)
            self.canvas.coords(card, self._x(x), self._y(y))
            self.canvas.coords(label, self._x(x), self._y(y + self._selection_label_shift(offset)))
            for item in (card, label):
                self.canvas.itemconfigure(item, scale_y=squash, opacity=opacity)

    def _build_selection_card(self, tags):
        tags = (*tags, "select_card")
        self._prepare_select_media(self.track)
        has_media = self.select_media_photo is not None
        if has_media:
            # The frame is 170x150; still images fill only its centred 150x150 square.
            art_left, art_right = (90, 260) if self.select_video is not None else (100, 250)
            self.canvas.create_rectangle(
                self._x(art_left - 8), self._y(1167), self._x(art_right + 8), self._y(1333),
                fill="#5b416f", outline="", tags=tags,
            )
            self.select_media_item = self.canvas.create_image(
                self._x(90), self._y(1175), image=self.select_media_photo, anchor="nw", tags=tags,
            )
        title_size = 38 if len(self.track.title) <= 20 else max(25, round(38 * 20 / len(self.track.title)))
        detail = self.track.artist if self.selection_phase == "song" else self.track.difficulty
        if has_media:
            self._text_image(self.track.title.upper(), title_size, 290, 1200, anchor="nw", tags=tags)
            self._text_image(detail.upper(), 26, 290, 1265, anchor="nw", tags=tags)
        else:
            self._text_image(self.track.title.upper(), title_size, 100, 1288, anchor="w", tags=tags)
            self._text_image(detail.upper(), 26, 100, 1295, anchor="w", tags=tags)
        self._text_image(str(self.track.level), 92, 930, 1230, tags=tags)
        self._text_image("LEVEL", 21, 930, 1305, tags=tags)
        self.scroll_speed_warning_item = None
        self.scroll_speed_warning_offset = 0.0
        if self.track.has_scroll_speed_changes:
            self.scroll_speed_warning_item = self._image(
                "scrollspeed_warn", 115, 1440, anchor="nw", tags=(*tags, "select_overlay"),
            )


    def _create_selection_sweep(self):
        if self.selection_sweep_item is not None:
            self.canvas.delete(self.selection_sweep_item)
        self.selection_sweep_item = self.canvas.create_image(
            self._x(-150), self._y(1125), image=self._asset_photo("select_sweep"),
            anchor="nw", tags=("select_sweep",),
        )
        self.canvas.tag_raise(self.selection_sweep_item)

    def _build_next(self):
        if getattr(self, "extra_stage_active", False):
            self._image("extra_mode_warning", 540, 1235, tags=("next",))
            self._text_image(self.track.creator, 26, 540, 1635, tags=("next",))
        next_item = self._text_image("NEXT", 54, 540, 900, tags=("next",))
        name_item = self._text_image(self.track.title, 56, 285, 1228, tags=("next_morph",))
        difficulty_item = self._text_image(self.track.difficulty, 33, 285, 1295, tags=("next_morph",))
        level_item = self._text_image(str(self.track.level), 108, 930, 1230, tags=("next_morph",))
        level_label_item = self._text_image("LEVEL", 23, 930, 1305, tags=("next_morph",))
        self.next_morph_items = [
            (name_item, (285, 1228), (540, 1160)),
            (difficulty_item, (285, 1295), (540, 1280)),
            (level_item, (930, 1230), (540, 1450)),
            (level_label_item, (930, 1305), (540, 1535)),
        ]
        self.canvas.coords(next_item, self._x(540), self._y(900))
        frames = []
        for name in ("next_arrow_left", "next_arrow"):
            source = self.sources[name]
            image_frames = []
            for opacity in tuple(0.3 + 0.7 * index / 7 for index in range(8)):
                frame = source.copy()
                alpha = frame.getchannel("A").point(lambda value, factor=opacity: round(value * factor))
                frame.putalpha(alpha)
                image_frames.append(self._photo(frame))
            frames.append(tuple(image_frames))
        self.next_arrow_frames = tuple(frames)
        left_item = self.canvas.create_image(self._x(365), self._y(900), image=frames[0][0], anchor="center", tags=("next",))
        right_item = self.canvas.create_image(self._x(715), self._y(900), image=frames[1][0], anchor="center", tags=("next",))
        self.next_arrow_items = [left_item, right_item]
