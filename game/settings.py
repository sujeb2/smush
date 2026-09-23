import random
import time
from dataclasses import replace

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from game.rules import smooth_progress


def arrange_chart(chart, arrangement, rng=None):
    if arrangement == "NONE":
        return chart
    rng = rng or random
    if chart.mode == 2:
        positions = sorted({note.x for note in chart.notes})
        shuffled = positions.copy()
        rng.shuffle(shuffled)
        mapping = dict(zip(positions, shuffled))
        notes = tuple(replace(note, x=512 - note.x if arrangement == "MIRROR" else mapping[note.x])
                      for note in chart.notes)
    else:
        lanes = [4, 0, 1, 2, 3, 5] if chart.circle_size == 6 else list(range(int(chart.circle_size)))
        shuffled = lanes[::-1] if arrangement == "MIRROR" else rng.sample(lanes, len(lanes))
        mapping = dict(zip(lanes, shuffled))
        notes = tuple(replace(note, lane=mapping[note.lane]) for note in chart.notes)
    return replace(chart, notes=notes)


class MinigameSettingsMixin:
    def _press_selection_key(self, key):
        if (not self.running or self.scene != "select" or self.loading_phase is not None
                or self.transition_phase is not None or self.select_fade_in_started is not None
                or self.select_morph_in_started is not None or self.selection_scroll_started is not None):
            return
        phase = getattr(self, "settings_phase", None)
        if phase is None:
            if key == 0:
                self._open_settings()
            return
        if phase != "open":
            return
        now = time.monotonic()
        if key == 0:
            self.settings_cursor_from = self._settings_cursor_y(now)
            self.settings_row = (self.settings_row + 1) % 3
            self.settings_cursor_started = now
            self._play_sfx("cursor_select.wav")
        elif key in (1, 2):
            direction = -1 if key == 1 else 1
            if self.settings_row == 0:
                self.settings["scroll_speed"] = round(min(3.0, max(
                    0.5, self.settings["scroll_speed"] + direction * 0.1,
                )), 1)
            else:
                name, values = (("arrangement", ("NONE", "RANDOM", "MIRROR")) if self.settings_row == 1
                                else ("gauge", ("GROOVE", "HARD")))
                self.settings[name] = values[(values.index(self.settings[name]) + direction) % len(values)]
            self.settings_card_dirty = True
            self._play_sfx("cursor_select.wav")
        elif key == 3:
            self.settings_phase = "closing"
            self.settings_animation_started = now
            self._play_sfx("ok.wav")
            self._print(f"settings saved, scroll: {self.settings['scroll_speed']:.1f}, "
                        f"arrangement: {self.settings['arrangement']}, gauge: {self.settings['gauge']}")

    def _open_settings(self):
        self.settings_phase = "opening"
        self.settings_animation_started = time.monotonic()
        self.settings_row = 0
        self.settings_cursor_from = 402.0
        self.settings_cursor_started = self.settings_animation_started
        self._build_settings_overlay()
        self.settings_animation_started = time.monotonic()
        self._animate_settings(self.settings_animation_started)
        self._play_sfx("card_show.wav")
        self._print("[AnimationManager] music select settings opening")

    def _build_settings_overlay(self):
        self.canvas.delete("settings")
        self.canvas.itemconfigure("select_time", state="hidden")
        try:
            background = self.canvas.snapshot().resize((270, 480), Image.Resampling.LANCZOS)
        finally:
            self.canvas.itemconfigure("select_time", state="normal")
        self.settings_background = background.filter(ImageFilter.GaussianBlur(3)).resize(
            (1080, 1920), Image.Resampling.BILINEAR,
        )
        self.canvas.create_image(0, 0, image=self.settings_background, anchor="nw", tags=("settings",))
        self.settings_panel_item = self.canvas.create_image(
            540, 1175, image=self.sources["setting_popup"], tags=("settings",),
        )
        self.settings_cursor_item = self.canvas.create_image(
            0, 1175, image=self.sources["selected_option"], anchor="nw", tags=("settings",),
        )
        self.settings_card_item = self.canvas.create_image(540, 1175, tags=("settings",))
        self.settings_card_dirty = True
        self._animate_settings(time.monotonic())

    def _settings_cursor_y(self, now):
        target = (402.0, 517.0, 632.0)[self.settings_row]
        progress = smooth_progress((now - self.settings_cursor_started) / 0.18)
        return self.settings_cursor_from + (target - self.settings_cursor_from) * progress

    def _settings_card_source(self):
        card = Image.new("RGBA", self.sources["setting_popup"].size, (0, 0, 0, 0))
        card.alpha_composite(self.sources["option_text"], (52, 416))
        draw = ImageDraw.Draw(card)
        font = ImageFont.truetype(self.novecento_demibold_font_path, 36)
        values = (f"x{self.settings['scroll_speed']:.1f}", self.settings['arrangement'], self.settings['gauge'])
        for value, y in zip(values, (454, 569, 684)):
            draw.text((1005, y), value, font=font, fill="white", anchor="rm")
        return card

    def _animate_settings(self, now):
        progress = min(1.0, max(0.0, (now - self.settings_animation_started) / 0.42))
        progress = progress ** 3 * (progress * (progress * 6 - 15) + 10)
        if self.settings_phase == "opening" and progress >= 1.0:
            self.settings_phase = "open"
        elif self.settings_phase == "closing" and progress >= 1.0:
            self._clear_settings_overlay()
            self._print("[AnimationManager] music select settings closed")
            return
        if self.settings_card_dirty:
            self.settings_card = self._settings_card_source()
            self.canvas.itemconfigure(self.settings_card_item, image=self.settings_card)
            self.settings_card_dirty = False
        openness = 1.0 if self.settings_phase == "open" else (
            1.0 - progress if self.settings_phase == "closing" else progress
        )
        self.canvas.itemconfigure(self.settings_panel_item, scale_y=openness)
        self.canvas.itemconfigure(self.settings_card_item, scale_y=openness)
        self.canvas.itemconfigure(self.settings_cursor_item, scale_y=openness)
        self.canvas.coords(self.settings_cursor_item, 0,
                           1175 + (self._settings_cursor_y(now) - 725) * openness)
        self.canvas.tag_raise("settings")
        self.canvas.tag_raise("select_time")

    def _clear_settings_overlay(self):
        self.canvas.delete("settings")
        self.settings_phase = None
        self.settings_background = None
        self.settings_card = None
