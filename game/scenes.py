import math
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from game.rules import JUDGEMENT_WEIGHT, TEXT_SCALE
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
        self._image("top_gradient", 0, 0, anchor="nw", tags=("game",))
        self._build_header()
        self._text_image(self.track.difficulty, 26, 95, 250, anchor="w", tags=("game",)) # beatmap diff need to change
        title_size = 47 if len(self.track.title) <= 20 else max(30, round(47 * 20 / len(self.track.title)))
        self._text_image(self.track.title.upper(), title_size, 95, 310, anchor="w", tags=("game",))
        self._text_image("SCORE", 26, 990, 250, anchor="e", tags=("game",))
        self.score_item = self._text_image(str(self.score), 58, 990, 312, anchor="e", tags=("game_score",))
        self._image("main_layer", 290, 470, anchor="nw", tags=("game",))
        self.note_photos = (self._asset_photo("note_0"), self._asset_photo("note_1"))
        self.combo_item = self.canvas.create_image(self._x(540), self._y(790), anchor="center", tags=("game_combo",))
        if self.combo > 0:
            self.canvas.itemconfigure(self.combo_item, image=self._combo_photo(self.combo, 78))
        self.judgement_line_item = self._image("line", 290, 1560, anchor="nw", tags=("game_line",))
        self._image("health_bg", 835, 655, anchor="nw", tags=("game",))
        self.health_fill_item = self.canvas.create_image(self._x(853), self._y(1554), anchor="s", tags=("game_health",))
        self.judgement_item = self.canvas.create_image(self._x(540), self._y(1715), anchor="center", tags=("game_feedback",))
        self.judgement_frames = {
            name: tuple(self._photo(frame) for frame in self._judgement_animation_sources(name))
            for name in JUDGEMENT_WEIGHT
        }
        self._update_health_image()

    def _build_game_information(self):
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
            fill="#a77dd1", outline="#35bdff", width=max(2, round(5 * self.scale)), tags=("catch_playfield",),
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
        self.catch_burst_frames = tuple(self._photo(frame) for frame in self._catch_burst_sources())
        self.catch_combo_item = self._text_image(
            "", 80, 90, 1725, anchor="w", tags=("catch_hud", "catch_combo"),
        )
        self._text_image("COMBO", 27, 92, 1805, anchor="w", tags=("catch_hud",))
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
