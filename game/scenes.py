import math
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from game.rules import TEXT_SCALE
from ui_framework import DESIGN_HEIGHT, DESIGN_WIDTH


class MinigameGameSceneMixin:
    def _build_game(self): # game ui
        if self.game_mode == "catch":
            self._build_catch_game()
            return
        self.note_items = {}
        self.canvas.create_rectangle(
            self._x(0), self._y(0), self._x(DESIGN_WIDTH), self._y(DESIGN_HEIGHT),
            fill="#8d73aa", outline="", tags=("game",),
        )
        self._build_game_media()
        self._image("top_gradient", 0, 0, anchor="nw", tags=("game",))
        self._build_header()
        self._text_image(self.track.difficulty, 26, 95, 250, anchor="w", tags=("game",)) # beatmap diff need to change
        title_size = 47 if len(self.track.title) <= 20 else max(30, round(47 * 20 / len(self.track.title)))
        self._text_image(self.track.title.upper(), title_size, 95, 310, anchor="w", tags=("game",))
        self._text_image("SCORE", 26, 990, 250, anchor="e", tags=("game",))
        self.score_item = self._text_image(str(self.score), 58, 990, 312, anchor="e", tags=("game_score",))
        if self.game_mode == "4k":
            self.lane_origin_x = 173.0
            self.lane_width = 183.5
            self.judgement_line_y = 1850.0
            self.health_background_x = 952.0
            self.health_background_y = 1085.0
            self.health_fill_x = 970.0
            self.health_fill_y = 1819.0
            health_background_name = "health_bg_4k"
            self._image("main_layer_4k", self.lane_origin_x, 520, anchor="nw", tags=("game",))
            self.note_photos = tuple(self._asset_photo(f"note_4k_{lane % 2}") for lane in range(4))
            line_name = "line_4k"
        else:
            self.lane_origin_x = 290.0
            self.lane_width = 250.0
            self.judgement_line_y = 1560.0
            self.health_background_x = 835.0
            self.health_background_y = 655.0
            self.health_fill_x = 853.0
            self.health_fill_y = 1554.0
            health_background_name = "health_bg"
            self._image("main_layer", self.lane_origin_x, 520, anchor="nw", tags=("game",))
            self.note_photos = (self._asset_photo("note_0"), self._asset_photo("note_1"))
            line_name = "line"
        self._ensure_preloaded_gameplay_photos()
        self._build_lane_help()
        self.combo_item = self.canvas.create_image(self._x(540), self._y(790), anchor="center", tags=("game_combo",))
        if self.combo > 0:
            self.canvas.itemconfigure(self.combo_item, image=self._combo_photo(self.combo, 78))
        self.judgement_line_item = self._image(
            line_name, self.lane_origin_x, self.judgement_line_y, anchor="nw", tags=("game_line",),
        )
        self._image(
            health_background_name, self.health_background_x, self.health_background_y,
            anchor="nw", tags=("game",),
        )
        self.health_fill_item = self.canvas.create_image(
            self._x(self.health_fill_x), self._y(self.health_fill_y), anchor="s", tags=("game_health",),
        )
        self.judgement_item = self.canvas.create_image(self._x(540), self._y(1715), anchor="center", tags=("game_feedback",))
        self.judgement_frames = self.preloaded_judgement_frames
        self._update_health_image()

    def _build_game_information(self):
        self._build_game_media()
        self._image("top_gradient", 0, 0, anchor="nw", tags=("game",))
        self._build_header()
        self._text_image(self.track.difficulty, 26, 95, 250, anchor="w", tags=("game",)) # beatmap diff need to change
        title_size = 47 if len(self.track.title) <= 20 else max(30, round(47 * 20 / len(self.track.title)))
        self._text_image(self.track.title.upper(), title_size, 95, 310, anchor="w", tags=("game",))
        self._text_image("SCORE", 26, 990, 250, anchor="e", tags=("game",))
        self.score_item = self._text_image(str(self.score), 58, 990, 312, anchor="e", tags=("game_score",))

    def _build_catch_game(self):
        self.note_items = {}
        self.canvas.create_rectangle(
            self._x(0), self._y(0), self._x(DESIGN_WIDTH), self._y(DESIGN_HEIGHT),
            fill="#8d73aa", outline="", tags=("game",),
        )
        self._build_game_information()
        self.canvas.create_rectangle(
            self._x(40), self._y(470), self._x(1040), self._y(1900),
            fill="" if self.game_media_photo is not None else "#a77dd1",
            outline="#35bdff", width=max(2, round(5 * self.scale)), tags=("catch_playfield",),
        )
        particle_photo = self._asset_photo("catch_particle")
        self.canvas.create_image(
            self._x(540), self._y(500), image=particle_photo, anchor="n", tags=("catch_background",),
        )
        scroll_photo = self._asset_photo("catch_scroll")
        for y in (500, 1660):
            self.canvas.create_image(
                self._x(0), self._y(y), image=scroll_photo, anchor="nw", tags=("catch_background",),
            )
        self._image("catch_line", 40, 1850, anchor="nw", tags=("catch_line",))
        self.catcher_item = self._image("catcher", self.catcher_x, 1725, tags=("catch_catcher",))
        self._ensure_preloaded_gameplay_photos()
        self.catch_burst_frames = self.preloaded_catch_burst_frames
        self.catch_combo_item = self._text_image(
            "", 80, 90, 1725, anchor="w", tags=("catch_hud", "catch_combo"),
        )
        self._text_image("COMBO", 27, 92, 1805, anchor="w", tags=("catch_hud",))
        self._image("catch_health_bg", 269, 355, anchor="nw", tags=("game_health",))
        self.health_fill_x = 294.0
        self.health_fill_y = 405.0
        self.health_fill_item = self.canvas.create_image(
            self._x(self.health_fill_x), self._y(self.health_fill_y), anchor="w", tags=("game_health",),
        )
        self._update_health_image()
        #self.catch_score_item = self._text_image(
        #    str(self.score), 70, 985, 1745, anchor="e", tags=("catch_hud", "catch_score"),
        #)
        #self._text_image("SCORE", 27, 985, 1810, anchor="e", tags=("catch_hud",))

    def _combo_photo(self, combo, number_size):
        key = combo, number_size, round(self.scale, 5)
        if key in self.combo_photo_cache:
            return self.combo_photo_cache[key]
        image = Image.new("RGBA", (340, 190), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        label_font = ImageFont.truetype(self.novecento_demibold_font_path, round(29 * TEXT_SCALE))
        number_font = ImageFont.truetype(self.novecento_demibold_font_path, round(number_size * TEXT_SCALE))
        label_box = draw.textbbox((0, 0), "COMBO", font=label_font)
        number = str(combo)
        number_box = draw.textbbox((0, 0), number, font=number_font)
        draw.text(((340 - label_box[2] + label_box[0]) / 2, 8 - label_box[1]), "COMBO", font=label_font, fill="white")
        draw.text(((340 - number_box[2] + number_box[0]) / 2, 68 - number_box[1]), number, font=number_font, fill="white")
        self.combo_photo_cache[key] = self._scaled_photo(image)
        return self.combo_photo_cache[key]

    def _lane_help_animation_sources(self, name):
        if name in self.lane_help_source_frames:
            return self.lane_help_source_frames[name]
        source = self.sources[name]
        frames = []
        for index in range(18):
            progress = index / 17
            if progress < 0.18:
                opacity = progress / 0.18
            else:
                opacity = pow(max(0.0, 1 - (progress - 0.18) / 0.82), 1.35)
            rise = 0.7 + 0.3 * (1 - pow(1 - min(1.0, progress / 0.32), 3))
            height = max(1, round(source.height * rise))
            light = source.resize((source.width, height), Image.Resampling.BILINEAR)
            alpha = light.getchannel("A").point(lambda value, factor=opacity: round(value * factor))
            light.putalpha(alpha)
            frame = Image.new("RGBA", source.size, (0, 0, 0, 0))
            frame.alpha_composite(light, (0, source.height - height))
            frames.append(frame)
        self.lane_help_source_frames[name] = tuple(frames)
        return self.lane_help_source_frames[name]

    def _demonstration_overlay_sources(self, name):
        if name in self.demonstration_source_frames:
            return self.demonstration_source_frames[name]
        source = self.sources[name]
        width = round(source.width * 1.025)
        height = round(source.height * 1.025)
        frames = []
        for index in range(30):
            phase = index / 30 * math.tau
            opacity = 0.48 + 0.25 * (0.5 + 0.5 * math.sin(phase))
            scale = 0.985 + 0.025 * (0.5 + 0.5 * math.sin(phase - math.pi / 2))
            image = source.resize(
                (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
                Image.Resampling.LANCZOS,
            )
            alpha = image.getchannel("A").point(lambda value, factor=opacity: round(value * factor))
            image.putalpha(alpha)
            frame = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            frame.alpha_composite(image, ((width - image.width) // 2, (height - image.height) // 2))
            frames.append(frame)
        self.demonstration_source_frames[name] = tuple(frames)
        return self.demonstration_source_frames[name]

    def _build_lane_help(self):
        lane_count = 4 if self.game_mode == "4k" else 2
        mode = "4k" if lane_count == 4 else "2k"
        self.lane_help_items = []
        for lane in range(lane_count):
            name = f"lane_help_{mode}_{lane % 2}"
            frames = self.preloaded_lane_help_frames[name]
            item = self.canvas.create_image(
                self._x(self.lane_origin_x + lane * self.lane_width),
                self._y(self.judgement_line_y + 33), image=frames[0],
                anchor="sw", tags=("lane_help",),
            )
            self.lane_help_items.append((item, frames))

    def _build_demonstration_overlay(self):
        name = "demonstration_able" if self.coins_per_credit == 0 or self.credit_count > 0 else "demonstration_coin"
        self.demonstration_overlay_name = name
        self.demonstration_frames = self.preloaded_demonstration_frames[name]
        self.demonstration_frame_shown = 0
        self.demonstration_item = self.canvas.create_image(
            self._x(540), self._y(980), image=self.demonstration_frames[0],
            anchor="center", tags=("demonstration_overlay",),
        )

    def _result_wave_sources(self, name):
        if name in self.result_wave_source_frames:
            return self.result_wave_source_frames[name]
        source = self.sources[name]
        padding = 10
        frames = []
        for frame_index in range(30):
            frame = Image.new("RGBA", (source.width, source.height + padding * 2), (0, 0, 0, 0))
            phase = frame_index / 30 * math.tau
            for x in range(0, source.width, 4):
                right = min(source.width, x + 4)
                offset = round(4 * math.sin(x / source.width * math.tau * 1.35 + phase))
                frame.alpha_composite(source.crop((x, 0, right, source.height)), (x, padding + offset))
            frames.append(frame)
        self.result_wave_source_frames[name] = tuple(frames)
        return self.result_wave_source_frames[name]

    def _rank_reveal_sources(self, name):
        if name in self.rank_reveal_source_frames:
            return self.rank_reveal_source_frames[name]
        source = self.sources[name]
        width = round(source.width * 1.2) + 48
        height = round(source.height * 1.2) + 48
        frames = []
        for index in range(28):
            progress = index / 27
            if progress < 0.38:
                part = progress / 0.38
                eased = 1 - pow(1 - part, 3)
                scale = 0.3 + 0.86 * eased
                angle = -7 + 9 * eased
            elif progress < 0.64:
                part = (progress - 0.38) / 0.26
                eased = part * part * (3 - 2 * part)
                scale = 1.16 - 0.22 * eased
                angle = 2 - 3 * eased
            else:
                part = (progress - 0.64) / 0.36
                eased = part * part * (3 - 2 * part)
                scale = 0.94 + 0.06 * eased
                angle = -1 + eased
            opacity = min(1.0, progress / 0.12)
            rank = source.resize(
                (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
                Image.Resampling.LANCZOS,
            ).rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
            rank_alpha = rank.getchannel("A").point(lambda value, factor=opacity: round(value * factor))
            rank.putalpha(rank_alpha)
            frame = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            pulse = min(1.0, progress / 0.78)
            ring_alpha = round(92 * math.sin(pulse * math.pi))
            ring_width = round(70 + (width - 22) * pulse)
            ring_height = round(84 + (height - 24) * pulse)
            draw = ImageDraw.Draw(frame)
            draw.ellipse(
                (
                    (width - ring_width) // 2, (height - ring_height) // 2,
                    (width + ring_width) // 2, (height + ring_height) // 2,
                ),
                outline=(139, 240, 255, ring_alpha), width=3,
            )
            glow_alpha = rank.getchannel("A").filter(ImageFilter.GaussianBlur(11)).point(
                lambda value, factor=0.42 + 0.28 * math.sin(progress * math.pi): round(value * factor)
            )
            glow = Image.new("RGBA", rank.size, (137, 235, 255, 0))
            glow.putalpha(glow_alpha)
            position = ((width - rank.width) // 2, (height - rank.height) // 2)
            frame.alpha_composite(glow, position)
            frame.alpha_composite(rank, position)
            frames.append(frame)
        self.rank_reveal_source_frames[name] = tuple(frames)
        return self.rank_reveal_source_frames[name]

    def _result_morph_sources(self):
        if self.result_morph_source_frames:
            return self.result_morph_source_frames
        source = self.sources["select_bg"]
        frames = []
        for index in range(16):
            progress = index / 15
            eased = progress * progress * (3 - 2 * progress)
            width = round(954 + (1044 - 954) * eased)
            height = round(629 + (276 - 629) * eased)
            frame = source.resize((width, height), Image.Resampling.LANCZOS)
            opacity = min(1.0, 0.18 + progress * 1.35)
            alpha = frame.getchannel("A").point(lambda value, factor=opacity: round(value * factor))
            frame.putalpha(alpha)
            frames.append(frame)
        self.result_morph_source_frames = tuple(frames)
        return self.result_morph_source_frames

    def _create_result_select_morph(self):
        self.result_morph_frames = tuple(self._photo(frame) for frame in self._result_morph_sources())
        self.result_morph_frame_shown = 0
        self.result_morph_item = self.canvas.create_image(
            self._x(540), self._y(1344), image=self.result_morph_frames[0],
            anchor="center", tags=("result_morph",),
        )
        self.canvas.tag_raise(self.result_morph_item)

    def _judgement_animation_sources(self, name):
        if name in self.judgement_source_frames:
            return self.judgement_source_frames[name]
        source = self.sources[name]
        colors = {
            "perfect": (128, 244, 255),
            "good": (255, 225, 91),
            "bad": (255, 90, 232),
            "miss": (255, 92, 92),
        }
        frame_count = 24
        max_scale = 1.24
        width = round(source.width * max_scale) + 44
        height = round(source.height * max_scale) + 44
        frames = []
        for index in range(frame_count):
            progress = index / (frame_count - 1)
            if progress < 0.16:
                part = progress / 0.16
                scale = 0.58 + (1.22 - 0.58) * (1 - pow(1 - part, 3))
            elif progress < 0.34:
                part = (progress - 0.16) / 0.18
                scale = 1.22 + (0.94 - 1.22) * part
            elif progress < 0.50:
                part = (progress - 0.34) / 0.16
                scale = 0.94 + (1.06 - 0.94) * part
            elif progress < 0.68:
                part = (progress - 0.50) / 0.18
                scale = 1.06 + (1.0 - 1.06) * part
            else:
                scale = 1.0
            opacity = min(1.0, progress / 0.08)
            if progress > 0.76:
                opacity = max(0.0, 1.0 - (progress - 0.76) / 0.24)
            glow_strength = 0.62 + 0.26 * (0.5 + 0.5 * math.sin(progress * math.pi * 6))
            scaled_width = max(1, round(source.width * scale))
            scaled_height = max(1, round(source.height * scale))
            scaled = source.resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)
            scaled_alpha = scaled.getchannel("A").point(lambda value, factor=opacity: round(value * factor))
            scaled.putalpha(scaled_alpha)
            x = (width - scaled_width) // 2
            y = (height - scaled_height) // 2
            mask = Image.new("L", (width, height), 0)
            mask.paste(scaled_alpha, (x, y))
            glow_alpha = mask.filter(ImageFilter.GaussianBlur(7)).point(
                lambda value, factor=glow_strength: round(value * factor)
            )
            glow = Image.new("RGBA", (width, height), (*colors[name], 0))
            glow.putalpha(glow_alpha)
            frame = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            frame.alpha_composite(glow)
            frame.alpha_composite(scaled, (x, y))
            frames.append(frame)
        self.judgement_source_frames[name] = tuple(frames)
        return self.judgement_source_frames[name]
