import time

from PIL import Image, ImageTk

from game.rules import is_clear
from ui_framework import DESIGN_HEIGHT, DESIGN_WIDTH


class MinigameResultSceneMixin:
    def _build_result(self):
        self._text_image("RESULT", 54, 70, 755, anchor="w", tags=("result",))
        self._text_image("TIME LEFT", 18, 970, 725, tags=("result",))
        remaining = max(0, int(self.result_deadline - time.monotonic() + 0.999))
        self.result_time_item = self._text_image(str(remaining), 52, 970, 780, tags=("result_time",))
        self.result_time_shown = remaining
        banner_name = "clear" if is_clear(self.health) else "failed"
        self.result_banner_frames = tuple(self._photo(frame) for frame in self._result_wave_sources(banner_name))
        self.result_banner_frame_shown = 0
        self.result_banner_item = self.canvas.create_image(
            self._x(540), self._y(840), image=self.result_banner_frames[0], anchor="center", tags=("result_banner",),
        )
        self.result_card_offset = 560.0
        offset = self.result_card_offset
        self._image("result_bg", 63, 1030 + offset, anchor="nw", tags=("result_card",))
        self._text_image(self.track.title, 46, 115, 1135 + offset, anchor="w", tags=("result_card",))
        self._text_image(self.track.difficulty, 27, 115, 1210 + offset, anchor="w", tags=("result_card",))
        self._text_image(str(self.track.level), 70, 948, 1135 + offset, tags=("result_card",))
        self._text_image("LEVEL", 19, 948, 1195 + offset, tags=("result_card",))
        labels = (
            (("CATCH", "#88f5ff"), ("MISS", "#ff6262"))
            if self.game_mode == "catch"
            else (("PERFECT", "#88f5ff"), ("GOOD", "#ffe35d"), ("BAD", "#ff68c7"), ("MISS", "#ff6262"))
        )
        for index, (label, color) in enumerate(labels):
            y = 1320 + index * 58 + offset
            self._text_image(label, 29, 116, y, color=color, anchor="w", tags=("result_card",))
            item = self._text_image("0", 29, 470, y, anchor="e", tags=("result_card",))
            self.result_value_items[label.lower()] = item
            self.result_values_shown[label.lower()] = 0
        self._text_image("HEALTH", 23, 695, 1390 + offset, anchor="w", tags=("result_card",))
        self._text_image(f"{self.health:.0f}%", 38, 940, 1388 + offset, anchor="e", tags=("result_card",))
        self._text_image("SCORE", 25, 940, 1498 + offset, anchor="e", tags=("result_card",))
        self.result_value_items["score"] = self._text_image("0", 63, 940, 1560 + offset, anchor="e", tags=("result_card",))
        self.result_values_shown["score"] = 0

    def _build_total_result(self):
        self._text_image("TOTAL RESULT", 54, 70, 755, anchor="w", tags=("total_result",))
        self._text_image("TIME LEFT", 18, 970, 725, tags=("total_result",))
        remaining = max(0, int(self.total_result_deadline - time.monotonic() + 0.999))
        self.total_result_time_item = self._text_image(
            str(remaining), 52, 970, 780, tags=("total_result_time",),
        )
        self.total_result_time_shown = remaining
        self._image("total_result_layout", 540, 1240, tags=("total_result",))
        row_y = (1015, 1221, 1425)
        for index, y in enumerate(row_y):
            name = self.track_names[index] or "---"
            size = 35 if len(name) <= 24 else max(24, round(35 * 24 / len(name)))
            self._text_image(name.upper(), size, 170, y, anchor="w", tags=("total_result",))
            self._text_image(str(self.track_scores[index]), 42, 910, y, anchor="e", tags=("total_result",))
        self.total_result_value_item = self._text_image("0", 76, 540, 1635, tags=("total_result",))
        self.total_result_value_shown = 0
        self._image("result_down_button", 540, 1845, tags=("total_result",))

    def _build_ending(self):
        self._image("logo", 540, 270, tags=("ending",))
        self.ending_accent_item = self.canvas.create_rectangle(
            self._x(540), self._y(1082), self._x(540), self._y(1090),
            fill="#8cefff", outline="", tags=("ending",),
        )
        self.ending_logo_item = self.canvas.create_image(
            self._x(540), self._y(1010), image="", anchor="center", tags=("ending",),
        )
        self.ending_thanks_item = self.canvas.create_image(
            self._x(540), self._y(1190), image="", anchor="center", tags=("ending",),
        )

    def _motion_photo(self, name, opacity, scale):
        opacity_level = min(32, max(0, round(opacity * 32)))
        scale_level = min(48, max(24, round(scale * 32)))
        key = name, opacity_level, scale_level, round(self.scale, 5)
        if key not in self.motion_photo_cache:
            source = self.sources[name]
            factor = scale_level / 32
            width = max(1, round(source.width * factor))
            height = max(1, round(source.height * factor))
            frame = source.resize((width, height), Image.Resampling.LANCZOS)
            alpha_factor = opacity_level / 32
            alpha = frame.getchannel("A").point(
                lambda value, multiplier=alpha_factor: round(value * multiplier)
            )
            frame.putalpha(alpha)
            self.motion_photo_cache[key] = self._scaled_photo(frame)
        return self.motion_photo_cache[key]

    def _set_motion_item(self, item, name, opacity, scale, state_store):
        state = min(32, max(0, round(opacity * 32))), min(48, max(24, round(scale * 32)))
        if state_store.get(name) == state:
            return
        self.canvas.itemconfigure(item, image=self._motion_photo(name, opacity, scale))
        state_store[name] = state

    def _fade_photo(self, opacity):
        level = min(32, max(0, round(opacity * 32)))
        key = round(self.scale, 5), level
        if key not in self.fade_photo_cache:
            width = max(1, round(DESIGN_WIDTH * self.scale))
            height = max(1, round(DESIGN_HEIGHT * self.scale))
            alpha = round(255 * level / 32)
            self.fade_photo_cache[key] = ImageTk.PhotoImage(Image.new("RGBA", (width, height), (0, 0, 0, alpha)))
        return self.fade_photo_cache[key]

    def _create_fade_overlay(self, opacity=0.0):
        self.fade_item = self.canvas.create_image(
            self._x(0), self._y(0), image=self._fade_photo(opacity), anchor="nw", tags=("fade",),
        )
        self.canvas.tag_raise(self.fade_item)

    def _set_fade_opacity(self, opacity):
        if self.fade_item is None:
            self._create_fade_overlay(opacity)
        else:
            self.canvas.itemconfigure(self.fade_item, image=self._fade_photo(opacity))
            self.canvas.tag_raise(self.fade_item)

    def _create_curtains(self, closed):
        if closed:
            top = (0, 0, DESIGN_WIDTH, DESIGN_HEIGHT / 2)
            bottom = (0, DESIGN_HEIGHT / 2, DESIGN_WIDTH, DESIGN_HEIGHT)
        else:
            top = (0, 0, DESIGN_WIDTH, 0)
            bottom = (0, DESIGN_HEIGHT, DESIGN_WIDTH, DESIGN_HEIGHT)
        self.curtain_items = (
            self.canvas.create_rectangle(*self._scaled_box(top), fill="#2d2439", outline="", tags=("curtain",)),
            self.canvas.create_rectangle(*self._scaled_box(bottom), fill="#2d2439", outline="", tags=("curtain",)),
        )
        self.canvas.tag_raise("curtain")

    def _scaled_box(self, box):
        return self._x(box[0]), self._y(box[1]), self._x(box[2]), self._y(box[3])
