import time

from PIL import Image, ImageDraw, ImageFont

from game.rules import is_clear
from ui_framework import DESIGN_HEIGHT, DESIGN_WIDTH

EXTRA_CHALLENGE_BAND_HEIGHT = 450
# The prompt rises this far (design px) while it fades in over the dimmed result.
EXTRA_CHALLENGE_SLIDE = 160.0


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
        accuracy = f"{self.accuracy:.2f}".rstrip("0").rstrip(".")
        self._text_image(
            f"ACCURACY: {accuracy}%", 23, 116, 1540 + offset, anchor="w", tags=("result_card",),
        )
        self.result_rank_frames = tuple(
            self._photo(frame) for frame in self._rank_reveal_sources(f"rank_{self.rank.lower()}")
        )
        self.result_rank_frame_shown = 0
        self.result_rank_item = self.canvas.create_image(
            self._x(820), self._y(1350 + offset), image=self.result_rank_frames[0],
            anchor="center", tags=("result_card", "result_rank"),
        )
        self._text_image("SCORE", 25, 940, 1498 + offset, anchor="e", tags=("result_card",))
        self.result_value_items["score"] = self._text_image("0", 63, 940, 1560 + offset, anchor="e", tags=("result_card",))
        self.result_values_shown["score"] = 0
        if getattr(self, "extra_challenge_prompt", False):
            self._build_extra_challenge_prompt()

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

    def _play_card_source(self):
        source = self.sources["playcard"].copy()
        draw = ImageDraw.Draw(source)
        # Guest entry is currently the only entry mode. Profile integrations can
        # supply these fields without baking identity text into the artwork.
        values = (getattr(self, "player_name", "GUEST"),
                  getattr(self, "player_id", "XXXX-XXXX"),
                  getattr(self, "total_play_count", 0))
        for value, y in zip(values, (100, 180, 262)):
            text = str(value)
            size = 34
            font = ImageFont.truetype(self.display_font_path, size)
            while draw.textlength(text, font=font) > 360 and size > 12:
                size -= 1
                font = ImageFont.truetype(self.display_font_path, size)
            draw.text((786, y), text, font=font, fill="white", anchor="rm")
        return source

    def _build_game_ended(self):
        self._image("logo", 540, 270, tags=("game_ended",))
        self._text_image("GAME ENDED", 54, 70, 755, anchor="w", tags=("game_ended",))
        self._text_image("TIME LEFT", 18, 970, 725, tags=("game_ended",))
        remaining = max(0, int(self.game_ended_deadline - time.monotonic() + 0.999))
        self.game_ended_time_item = self._text_image(str(remaining), 52, 970, 780)
        self.game_ended_time_shown = remaining
        # Reuse the entry card's opening motion, with the values composited so
        # they unfold with the card. Rebuild for the current player each time.
        self.sources["active_playcard"] = self._play_card_source()
        self.entry_card_source_frames.pop("active_playcard", None)
        self.play_card_frames = tuple(self._photo(frame) for frame in
                                     self._entry_card_sources("active_playcard"))
        self.play_card_frame_shown = 0
        self.play_card_item = self.canvas.create_image(
            self._x(540), self._y(1290), image=self.play_card_frames[0],
            tags=("game_ended",),
        )
        saved = Image.new("RGBA", (240, 42))
        ImageDraw.Draw(saved).text(
            (120, 21), "데이터 저장됨", anchor="mm", fill="#69c83b",
            font=ImageFont.truetype(self.display_font_path, 20),
        )
        frames = []
        for index in range(17):
            frame = saved.copy()
            frame.putalpha(saved.getchannel("A").point(lambda a, i=index: round(a * (1 - i / 16))))
            frames.append(self._photo(frame))
        self.play_card_saved_frames = tuple(frames)
        self.play_card_saved_item = self.canvas.create_image(
            self._x(540), self._y(1645), image=frames[0], state="hidden", tags=("game_ended"),
        )
        self._image("result_down_button", 540, 1845, tags=("game_ended",))

    def _extra_challenge_band_source(self):
        """Dark information band in the HOW TO PLAY style, with the BT1/BT2 chips of music select."""
        if "extra_challenge_band" in self.sources:
            return self.sources["extra_challenge_band"]
        width, height = DESIGN_WIDTH, EXTRA_CHALLENGE_BAND_HEIGHT
        band = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(band)
        for y in range(height):
            # Solid through the middle, feathered at both edges so it floats over the dimmed result.
            edge = min(1.0, y / 48, (height - 1 - y) / 48)
            shade = round(30 * y / height)
            draw.line((0, y, width, y), fill=(shade, shade, shade, round(235 * edge)))
        title_font = ImageFont.truetype(self.novecento_demibold_font_path, 39)
        text_font = ImageFont.truetype(self.display_font_path, 32)
        label_font = ImageFont.truetype(self.display_font_path, 26)
        chip_font = ImageFont.truetype(self.novecento_demibold_font_path, 38)
        draw.text((68, 82), "SPECIAL CHALLENGE", font=title_font, fill="white", anchor="lm")
        draw.text((540, 168), "스페셜 챌린지를 도전할 수 있습니다.", font=text_font, fill="white", anchor="mm")
        draw.text((540, 213), "EXTRA STAGE에 도전하시겠습니까?", font=text_font, fill="white", anchor="mm")
        # Same colours as the music select BT1/BT2 buttons (music_select/down_bt.png).
        chips = (
            (380, "BT1", "시도하기", (166, 229, 255), (214, 239, 250), (38, 50, 56)),
            (700, "BT2", "취소", (1, 255, 128), (107, 255, 181), (13, 60, 37)),
        )
        chip_width, chip_top, chip_bottom = 206, 318, 402
        for center, button, label, top_color, bottom_color, ink in chips:
            draw.text((center, 286), label, font=label_font, fill="white", anchor="mm")
            gradient = Image.new("RGBA", (chip_width, chip_bottom - chip_top))
            for y in range(gradient.height):
                mix = y / max(1, gradient.height - 1)
                color = tuple(round(a + (b - a) * mix) for a, b in zip(top_color, bottom_color))
                ImageDraw.Draw(gradient).line((0, y, chip_width, y), fill=(*color, 255))
            mask = Image.new("L", gradient.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, *gradient.size), radius=28, fill=255)
            left = center - chip_width // 2
            band.paste(gradient, (left, chip_top), mask)
            draw.text((center, (chip_top + chip_bottom) / 2), button, font=chip_font, fill=ink, anchor="mm")
        self.sources["extra_challenge_band"] = band
        return band

    def _build_extra_challenge_prompt(self):
        self.extra_challenge_dim_item = self.canvas.create_rectangle(
            self._x(0), self._y(0), self._x(DESIGN_WIDTH), self._y(DESIGN_HEIGHT),
            fill="#000000", outline="", tags=("extra_challenge_dim",),
        )
        self.canvas.itemconfigure(self.extra_challenge_dim_item, opacity=0.0)
        self.extra_challenge_band_item = self.canvas.create_image(
            self._x(DESIGN_WIDTH / 2), self._y(DESIGN_HEIGHT / 2 + self.extra_challenge_offset),
            image=self._scaled_photo(self._extra_challenge_band_source()), anchor="center",
            tags=("extra_challenge",),
        )
        self.canvas.itemconfigure(self.extra_challenge_band_item, opacity=0.0)

    def _animate_extra_challenge_prompt(self, now):
        if not getattr(self, "extra_challenge_prompt", False) or now < self.result_unlock_at:
            return
        if self.extra_challenge_started is None and getattr(self, "two_player", False) and self._flow_synced():
            # Both stations offer the challenge if either player qualified.
            if not self._joint_result()[1]:
                self.extra_challenge_prompt = False
                return
        if self.extra_challenge_started is None:
            self.extra_challenge_started = now
            self._play_sfx("information.wav")
        progress = min(1.0, (now - self.extra_challenge_started) / 0.5)
        eased = 1.0 - (1.0 - progress) ** 3
        offset = EXTRA_CHALLENGE_SLIDE * (1.0 - progress) ** 3
        self.canvas.move("extra_challenge", 0, (offset - self.extra_challenge_offset) * self.scale)
        self.extra_challenge_offset = offset
        self.canvas.itemconfigure("extra_challenge_dim", opacity=0.55 * eased)
        self.canvas.itemconfigure("extra_challenge", opacity=eased)
        self.canvas.tag_raise("extra_challenge_dim")
        self.canvas.tag_raise("extra_challenge")

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
            self.fade_photo_cache[key] = Image.new("RGBA", (width, height), (0, 0, 0, alpha))
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
