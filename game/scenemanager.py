import math
import time

from PIL import Image

from game.rules import EVENT_TRACK_COUNT, TEXT_SCALE
from ui_framework import DESIGN_HEIGHT, DESIGN_WIDTH

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
        self.selection_old_offset = 0.0
        self.selection_new_offset = 0.0
        self.selection_old_x = 0.0
        self.selection_new_x = 0.0
        self.selection_scroll_swapped = False
        self.selection_heading_item = None
        self.selection_sweep_item = None
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
        if key not in self.text_cache:
            self.text_cache[key] = self._text_photo(
                text,
                round(size * TEXT_SCALE),
                color=color,
                font_path=self.novecento_demibold_font_path,
                align=align,
            )
        return self.text_cache[key]

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
            "ending": ("ENDING", "<3"),
        }
        first_label, second_label = labels[self.scene]
        self._image("top", 63, 112, anchor="nw", tags=("header",))
        self._text_image(first_label, 28, 183, 147, tags=("header",))
        self._text_image(second_label, 27, 423, 147, tags=("header",))
        self._text_image("VER 1.0-E", 22, 975, 34, anchor="ne", tags=("header",))
        self._image("network", 995, 18, anchor="ne", tags=("header",))
        self._text_image(
            f"{self.settings['mode']} MODE [{self._track_position()}/{EVENT_TRACK_COUNT}]",
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
        self._text_image("PRESS EITHER BUTTON", 36, 540, 1300, tags=("title",))
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
        self._text_image("TIME LEFT", 18, 970, 725, tags=("entry", "entry_time"))
        remaining = max(0, int(self.entry_deadline - time.monotonic() + 0.999))
        self.entry_time_item = self._text_image(str(remaining), 52, 970, 780, tags=("entry_time",))
        self.entry_time_shown = remaining
        self.entry_card_frames = tuple(self._photo(frame) for frame in self._entry_card_sources())
        self.entry_card_item = self.canvas.create_image(
            self._x(540), self._y(1180), image=self.entry_card_frames[0], anchor="center", tags=("entry_card",),
        )

    def _build_warning(self):
        self._image("logo", 540, 270, tags=("warning",))
        self.warning_frames = tuple(self._photo(frame) for frame in self._warning_sources())
        self.warning_item = self.canvas.create_image(
            self._x(540), self._y(1120), image=self.warning_frames[0], anchor="center", tags=("warning_card",),
        )

    def _mode_description_photo(self):
        text = (
            "두 개의 버튼을 이용하여서 노트를 처리하는 모드"
            if self.mode_index == 0
            else "네 개의 버튼과 레인을 이용하여서 노트를 처리하는 모드"
            if self.mode_index == 1
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
        icon_name = f"mode_{('2k', '4k', 'catch')[self.mode_index]}"
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
        heading = "MUSIC SELECT" if self.selection_phase == "song" else "DIFFICULTY SELECT"
        self.selection_heading_item = self._text_image(heading, 54, 70, 755, anchor="w", tags=("select",))
        self._text_image("TIME LEFT", 18, 970, 725, tags=("select",))
        remaining = max(0, int(self.select_deadline - time.monotonic() + 0.999))
        self.select_time_item = self._text_image(str(remaining), 52, 970, 780, tags=("select_time",))
        self.select_time_shown = remaining
        self._build_selection_shell(("select", "select_shell"))
        self._build_selection_list(("select", "select_list", "select_dynamic"))

    def _build_selection_shell(self, tags):
        self._image("select_bg", 32, 1110, anchor="nw", tags=tags)
        self.down_button_item = self._image("down_button", 540, self.down_button_base_y, tags=tags)

    def _build_selection_list(self, tags):
        if self.selection_phase == "song":
            choices = tuple(group[0].title for group in self.song_groups)
            selected = self.song_index
        else:
            choices = tuple(chart.difficulty for chart in self.song_groups[self.song_index])
            selected = self.difficulty_index
        preview_positions = {
            -2: (950, 925),
            -1: (850, 1000),
            1: (850, 1497),
            2: (950, 1660),
        }
        visible_choices = {selected}
        for offset in (1, -1, 2, -2):
            choice_index = (selected + offset) % len(choices)
            if choice_index in visible_choices:
                continue
            visible_choices.add(choice_index)
            x, y = preview_positions[offset]
            label = choices[choice_index]
            self._image("previous", x, y, tags=tags)
            self._text_image(label.upper(), 27, x, y, color="#ead7fb", tags=tags)
        self._prepare_select_media(self.track)
        has_media = self.select_media_photo is not None
        if has_media:
            self.canvas.create_rectangle(
                self._x(82), self._y(1152), self._x(268), self._y(1278),
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

    def _create_selection_sweep(self):
        if self.selection_sweep_item is not None:
            self.canvas.delete(self.selection_sweep_item)
        self.selection_sweep_item = self.canvas.create_image(
            self._x(-150), self._y(1125), image=self._asset_photo("select_sweep"),
            anchor="nw", tags=("select_sweep",),
        )
        self.canvas.tag_raise(self.selection_sweep_item)

    def _build_next(self):
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
