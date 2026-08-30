import math

import pygame

from animviewer.model import AnimationSpec, Keyframe
from animviewer.text import SurfaceFont


WHITE = (245, 245, 245)
GRAY = (143, 143, 143)
DARK_GRAY = (55, 55, 55)
BLACK = (8, 8, 8)
GREEN = (47, 213, 75)


def _keys(duration, *entries):
    return tuple(Keyframe(duration * position, name) for position, name in entries)


CATALOG = (
    AnimationSpec("SMUSH UI", "Recycle Item Drop", .90, 60, "drop", _keys(.90, (0, "ENTER"), (.72, "APPROACH"), (1, "IMPACT"))),
    AnimationSpec("SMUSH UI", "Can Stack Lift", .28, 60, "lift", _keys(.28, (0, "REST"), (1, "LIFT")), "lift"),
    AnimationSpec("SMUSH UI", "Can Stack Settle", .48, 60, "lift", _keys(.48, (0, "LIFTED"), (1, "SETTLED")), "settle"),
    AnimationSpec("SMUSH UI", "Celebration Fireworks", 1.50, 30, "fireworks", _keys(1.50, (0, "IGNITE"), (.35, "BURST"), (1, "FADE"))),
    AnimationSpec("MINIGAME", "Ambient Particle Float", 7.85, 60, "float", _keys(7.85, (0, "BASE"), (.25, "CREST"), (.75, "TROUGH"), (1, "LOOP"))),
    AnimationSpec("MINIGAME", "Scrollable Background Loop", 83.29, 60, "scroll", _keys(83.29, (0, "START"), (.5, "MIDPOINT"), (1, "LOOP"))),
    AnimationSpec("MINIGAME", "Preload Status Pulse", 1.00, 5, "status", _keys(1.00, (0, "CHECKING"), (.75, "ELLIPSIS"), (1, "LOOP"))),
    AnimationSpec("MINIGAME", "CI Epilepsy Warning Reveal", .52, 60, "reveal", _keys(.52, (0, "HIDDEN"), (1, "VISIBLE")), "epilepsywarning"),
    AnimationSpec("MINIGAME", "CI Notice Reveal", .52, 60, "reveal", _keys(.52, (0, "HIDDEN"), (1, "VISIBLE")), "notice"),
    AnimationSpec("MINIGAME", "CI Credits Reveal", .52, 60, "reveal", _keys(.52, (0, "HIDDEN"), (1, "VISIBLE")), "credits"),
    AnimationSpec("MINIGAME", "Title To Entry Logo Morph", .72, 60, "logo_morph", _keys(.72, (0, "TITLE"), (.72, "EXPAND"), (1, "ENTRY"))),
    AnimationSpec("MINIGAME", "Entry Card Open", .72, 60, "card", _keys(.72, (0, "CLOSED"), (.78, "OVERSHOOT"), (1, "OPEN")), "ENTRY"),
    AnimationSpec("MINIGAME", "Guest Card Open", .72, 60, "card", _keys(.72, (0, "CLOSED"), (.78, "OVERSHOOT"), (1, "OPEN")), "GUEST PLAY"),
    AnimationSpec("MINIGAME", "Cancel Entry Blink", 1.00, 24, "blink", _keys(1.00, (0, "VISIBLE"), (.25, "DIM"), (.5, "VISIBLE"), (.75, "DIM"), (1, "VISIBLE")), "CANCEL ENTRY"),
    AnimationSpec("MINIGAME", "Warning Card Reveal", .48, 60, "card", _keys(.48, (0, "CLOSED"), (1, "OPEN")), "WARNING"),
    AnimationSpec("MINIGAME", "Warning To Mode Select Morph", .82, 60, "vertical_morph", _keys(.82, (0, "WARNING"), (.55, "MORPH"), (1, "MODE SELECT")), "MODE SELECT"),
    AnimationSpec("MINIGAME", "Warning To Music Select Morph", .82, 60, "vertical_morph", _keys(.82, (0, "WARNING"), (.55, "MORPH"), (1, "MUSIC SELECT")), "MUSIC SELECT"),
    AnimationSpec("MINIGAME", "Mode Icon Morph", .58, 60, "icon", _keys(.58, (0, "OLD MODE"), (.42, "SWAP"), (1, "NEW MODE"))),
    AnimationSpec("MINIGAME", "Title To Music Select Morph", 1.15, 60, "horizontal_morph", _keys(1.15, (0, "TITLE"), (.5, "CROSS"), (1, "SELECT"))),
    AnimationSpec("MINIGAME", "Next Arrow Pulse", 1.14, 60, "arrows", _keys(1.14, (0, "REST"), (.25, "OUT"), (.75, "IN"), (1, "LOOP"))),
    AnimationSpec("MINIGAME", "Music To Game Curtain", 1.03, 60, "curtain", _keys(1.03, (0, "OPEN"), (.47, "CLOSED"), (1, "OPEN"))),
    AnimationSpec("MINIGAME", "Scene Fade Out And In", 1.00, 60, "fade", _keys(1.00, (0, "VISIBLE"), (.48, "BLACK"), (1, "VISIBLE"))),
    AnimationSpec("MINIGAME", "Beatmap Preview Fade", .36, 60, "preview", _keys(.36, (0, "HIDDEN"), (1, "VISIBLE"))),
    AnimationSpec("MINIGAME", "Song Select BGA Playback", 2.00, 30, "bga", _keys(2.00, (0, "FRAME 0"), (.5, "FRAME 30"), (1, "FRAME 60")), "select"),
    AnimationSpec("MINIGAME", "Gameplay BGA Playback", 2.00, 18, "bga", _keys(2.00, (0, "FRAME 0"), (.5, "FRAME 18"), (1, "FRAME 36")), "game"),
    AnimationSpec("MINIGAME", "2K Note Travel", 1.54, 60, "note", _keys(1.54, (0, "SPAWN"), (.88, "APPROACH"), (1, "JUDGE")), "2K"),
    AnimationSpec("MINIGAME", "4K Note Travel", 1.54, 60, "note", _keys(1.54, (0, "SPAWN"), (.88, "APPROACH"), (1, "JUDGE")), "4K"),
    AnimationSpec("MINIGAME", "Hold Note Travel", 1.54, 60, "note", _keys(1.54, (0, "SPAWN"), (.62, "HOLD START"), (1, "HOLD END")), "HOLD"),
    AnimationSpec("MINIGAME", "Lane Input Help", .30, 60, "lane_help", _keys(.30, (0, "INPUT"), (.18, "FLASH"), (1, "FADE"))),
    AnimationSpec("MINIGAME", "Demonstration Overlay Pulse", 1.50, 20, "demonstration", _keys(1.50, (0, "BASE"), (.25, "BRIGHT"), (.75, "DIM"), (1, "LOOP"))),
    AnimationSpec("MINIGAME", "Catch Object Fall", 1.27, 60, "catch_fall", _keys(1.27, (0, "SPAWN"), (.88, "APPROACH"), (1, "CATCH"))),
    AnimationSpec("MINIGAME", "Result Card Reveal", 1.05, 60, "result", _keys(1.05, (0, "BELOW"), (.72, "OVERSHOOT"), (1, "SETTLE"))),
    AnimationSpec("MINIGAME", "Result Rank Reveal", .72, 60, "rank", _keys(.72, (0, "HIDDEN"), (.38, "POP"), (.64, "REBOUND"), (1, "SETTLE"))),
    AnimationSpec("MINIGAME", "Result Clear Wave", 1.25, 30, "wave", _keys(1.25, (0, "FLAT"), (.25, "CREST"), (.75, "TROUGH"), (1, "LOOP")), "CLEAR"),
    AnimationSpec("MINIGAME", "Result Failed Wave", 1.25, 30, "wave", _keys(1.25, (0, "FLAT"), (.25, "CREST"), (.75, "TROUGH"), (1, "LOOP")), "FAILED"),
    AnimationSpec("MINIGAME", "Result Value Count", 1.25, 60, "count", _keys(1.25, (0, "ZERO"), (.7, "DECELERATE"), (1, "FINAL")), "9000"),
    AnimationSpec("MINIGAME", "Total Score Count", 1.35, 60, "count", _keys(1.35, (0, "ZERO"), (.82, "DECELERATE"), (1, "ADDED")), "27000"),
    AnimationSpec("MINIGAME", "Ending Logo Reveal", 2.40, 60, "ending", _keys(2.40, (0, "EMPTY"), (.32, "ACCENT"), (.64, "LOGO"), (1, "THANKS"))),
    AnimationSpec("MINIGAME", "Catcher Momentum", .70, 60, "catcher", _keys(.70, (0, "INPUT"), (.25, "ACCELERATE"), (1, "FRICTION"))),
    AnimationSpec("MINIGAME", "Catch Burst", .42, 60, "burst", _keys(.42, (0, "CATCH"), (.32, "EXPLODE"), (1, "FADE"))),
    AnimationSpec("MINIGAME", "Catch Combo Bounce", .28, 60, "combo", _keys(.28, (0, "REST"), (.5, "POP"), (1, "SETTLE")), "x125"),
    AnimationSpec("MINIGAME", "2K Combo Bounce", .24, 60, "combo", _keys(.24, (0, "REST"), (.34, "POP"), (1, "SETTLE")), "125 COMBO"),
    AnimationSpec("MINIGAME", "Health Gain", .28, 60, "health", _keys(.28, (0, "OLD"), (.55, "PULSE"), (1, "NEW")), "gain"),
    AnimationSpec("MINIGAME", "Health Loss", .28, 60, "health", _keys(.28, (0, "OLD"), (.55, "PULSE"), (1, "NEW")), "loss"),
    AnimationSpec("MINIGAME", "Perfect Judgement", .58, 60, "judgement", _keys(.58, (0, "HIDDEN"), (.16, "POP"), (.68, "SETTLE"), (1, "FADE")), "perfect"),
    AnimationSpec("MINIGAME", "Good Judgement", .58, 60, "judgement", _keys(.58, (0, "HIDDEN"), (.16, "POP"), (.68, "SETTLE"), (1, "FADE")), "good"),
    AnimationSpec("MINIGAME", "Bad Judgement", .58, 60, "judgement", _keys(.58, (0, "HIDDEN"), (.16, "POP"), (.68, "SETTLE"), (1, "FADE")), "bad"),
    AnimationSpec("MINIGAME", "Miss Judgement", .58, 60, "judgement", _keys(.58, (0, "HIDDEN"), (.16, "POP"), (.68, "SETTLE"), (1, "FADE")), "miss"),
)


def _smooth(progress):
    progress = min(1.0, max(0.0, progress))
    return progress * progress * (3 - 2 * progress)


def _out(progress):
    progress = min(1.0, max(0.0, progress))
    return 1 - pow(1 - progress, 3)


def _back(progress):
    c1 = 1.70158
    c3 = c1 + 1
    shifted = min(1.0, max(0.0, progress)) - 1
    return 1 + c3 * shifted ** 3 + c1 * shifted ** 2


class PreviewRenderer:
    def __init__(self, font_path, assets):
        self.font = SurfaceFont(font_path, 30)
        self.small = SurfaceFont(font_path, 20)
        self.large = SurfaceFont(font_path, 82)
        self.assets = assets

    def _asset_center(self, surface, name, center, maximum_size=None, alpha=255):
        image = self.assets.fitted(name, maximum_size) if maximum_size else self.assets.image(name)
        if alpha != 255:
            image = image.copy()
            image.set_alpha(alpha)
        surface.blit(image, image.get_rect(center=center))

    def _sequence_center(self, surface, name, progress, center, maximum_size=None):
        frames = self.assets.sequence(name)
        frame = frames[min(len(frames) - 1, round(progress * (len(frames) - 1)))]
        if maximum_size:
            scale = min(maximum_size[0] / frame.get_width(), maximum_size[1] / frame.get_height())
            frame = pygame.transform.smoothscale(
                frame,
                (max(1, round(frame.get_width() * scale)), max(1, round(frame.get_height() * scale))),
            )
        surface.blit(frame, frame.get_rect(center=center))

    def _ui_stage(self, surface, area, cans_y, item=None, item_position=None, angle=0):
        stage = pygame.Surface((338, 600), pygame.SRCALPHA)
        stage.fill((169, 229, 250))
        factor = 600 / 1920
        ground = self.assets.scaled("ground_layer", scale=factor)
        cans = self.assets.scaled("cans", scale=factor)
        trash = self.assets.scaled("trash_can", scale=factor)
        stage.blit(ground, ground.get_rect(midtop=(169, round(1114 * factor))))
        stage.blit(cans, cans.get_rect(midtop=(169, round(cans_y * factor))))
        if item is not None:
            source = self.assets.scaled(item, scale=factor)
            source = pygame.transform.rotate(source, angle)
            stage.blit(source, source.get_rect(center=(round(item_position[0] * factor), round(item_position[1] * factor))))
        stage.blit(trash, trash.get_rect(midtop=(169, round(965 * factor))))
        pygame.draw.rect(stage, WHITE, stage.get_rect(), 2)
        rect = stage.get_rect(center=area.center)
        surface.blit(stage, rect)
        return rect

    def _text(self, surface, value, font, position, color=WHITE, center=True):
        image = font.render(value, True, color)
        rect = image.get_rect(center=position) if center else image.get_rect(topleft=position)
        surface.blit(image, rect)

    def _card(self, surface, rect, alpha=255, label=""):
        layer = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(layer, (*DARK_GRAY, alpha), layer.get_rect(), border_radius=18)
        pygame.draw.rect(layer, (*WHITE, alpha), layer.get_rect(), 3, border_radius=18)
        if label:
            text = self.font.render(label, True, (*WHITE, alpha))
            layer.blit(text, text.get_rect(center=layer.get_rect().center))
        surface.blit(layer, rect)

    def draw(self, surface, spec, elapsed, area):
        progress = 0.0 if spec.duration <= 0 else min(1.0, elapsed / spec.duration)
        self._text(surface, spec.group, self.small, (area.left + 18, area.top + 4), GRAY, False)
        self._text(surface, spec.name, self.font, (area.left + 18, area.top + 32), WHITE, False)
        stage = pygame.Rect(area.left + 20, area.top + 82, area.width - 40, area.height - 100)
        method = getattr(self, f"_draw_{spec.style}")
        method(surface, stage, progress, spec)

    def _draw_drop(self, surface, area, progress, spec):
        eased = progress * progress
        y = -140 + (916 + 140) * eased
        x = 540 + math.sin(progress * math.pi * 3) * 42
        angle = (12, 22, 12, 0, -12, -22, -12, 0)[min(7, int(progress * 7))]
        self._ui_stage(surface, area, 972, "can", (x, y), angle)

    def _draw_lift(self, surface, area, progress, spec):
        eased = _out(progress) if spec.variant == "lift" else progress * progress
        start, end = ((972, 880) if spec.variant == "lift" else (880, 972))
        y = start + (end - start) * eased
        self._ui_stage(surface, area, y)

    def _draw_fireworks(self, surface, area, progress, spec):
        stage_rect = self._ui_stage(surface, area, 972)
        colors = (WHITE, (255, 95, 86), (255, 189, 46), (39, 199, 247), (36, 107, 236), (245, 124, 24))
        for burst in range(4):
            local = min(1.0, max(0.0, progress * 1.6 - burst * .16))
            cx = stage_rect.left + stage_rect.width * (.2 + burst * .2)
            cy = stage_rect.top + stage_rect.height * (.25 + .10 * math.sin(burst))
            for particle in range(14):
                angle = math.tau * particle / 14 + burst * .3
                distance = 65 * _out(local)
                alpha = max(0, round(255 * (1 - local)))
                layer = pygame.Surface((12, 12), pygame.SRCALPHA)
                pygame.draw.circle(layer, (*colors[(burst + particle) % len(colors)], alpha), (6, 6), 4)
                surface.blit(layer, (cx + math.cos(angle) * distance - 6, cy + math.sin(angle) * distance - 6))

    def _draw_float(self, surface, area, progress, spec):
        image = self.assets.fitted("particle", (area.width - 80, area.height - 100))
        y = area.centery + 13 * math.sin(progress * math.tau)
        surface.blit(image, image.get_rect(center=(area.centerx, round(y))))

    def _draw_scroll(self, surface, area, progress, spec):
        source = self.assets.image("scroll")
        scale = min(1.0, (area.height - 180) / source.get_height())
        image = self.assets.scaled("scroll", (round(source.get_width() * scale), round(source.get_height() * scale)))
        offset = progress * image.get_width()
        viewport = pygame.Surface((area.width - 40, image.get_height()), pygame.SRCALPHA)
        viewport.blit(image, (-round(offset), 0))
        viewport.blit(image, (round(image.get_width() - offset), 0))
        surface.blit(viewport, viewport.get_rect(center=area.center))

    def _draw_status(self, surface, area, progress, spec):
        dots = "." * min(3, int(progress * 4))
        lines = ("GRAPHIC ASSETS                 OK", "ANIMATION CACHE        CHECKING" + dots, "CHART MEDIA                    ----")
        for index, line in enumerate(lines):
            self._text(surface, line, self.font, (area.left + 120, area.top + 100 + index * 75), GREEN if index == 0 else WHITE, False)

    def _draw_reveal(self, surface, area, progress, spec):
        alpha = round(255 * _smooth(progress))
        scale = .975 + .025 * _smooth(progress)
        if spec.variant == "credits":
            produced = self.assets.fitted("produced", (180, 180))
            engine = self.assets.fitted("gameengine", (440, 170))
            for image, y in ((produced, area.centery - 80), (engine, area.centery + 95)):
                frame = pygame.transform.smoothscale(image, (round(image.get_width() * scale), round(image.get_height() * scale)))
                frame.set_alpha(alpha)
                surface.blit(frame, frame.get_rect(center=(area.centerx, round(y + 18 * (1 - progress)))))
            return
        image = self.assets.fitted(spec.variant, (area.width - 180, area.height - 150))
        image = pygame.transform.smoothscale(image, (round(image.get_width() * scale), round(image.get_height() * scale)))
        image.set_alpha(alpha)
        surface.blit(image, image.get_rect(center=(area.centerx, round(area.centery + 18 * (1 - progress)))))

    def _draw_logo_morph(self, surface, area, progress, spec):
        eased = _smooth(progress)
        scale = 1 + 1.15 * eased
        alpha = round(255 * (1 - eased))
        image = self.assets.fitted("title_logo", (570, 230))
        image = pygame.transform.smoothscale(image, (round(image.get_width() * scale), round(image.get_height() * scale)))
        image.set_alpha(alpha)
        surface.blit(image, image.get_rect(center=area.center))

    def _draw_card(self, surface, area, progress, spec):
        name = "warning" if spec.variant == "WARNING" else "entry_guest" if spec.variant == "GUEST PLAY" else "entry"
        self._sequence_center(surface, name, progress, area.center, (area.width - 160, area.height - 120))

    def _draw_blink(self, surface, area, progress, spec):
        self._sequence_center(surface, "entry_cancel", progress, area.center, (area.width - 160, area.height - 120))

    def _draw_vertical_morph(self, surface, area, progress, spec):
        name = "warning_mode" if spec.variant == "MODE SELECT" else "warning_select"
        y = area.centery - 80 + 115 * _smooth(progress)
        self._sequence_center(surface, name, progress, (area.centerx, round(y)), (area.width - 100, area.height - 100))

    def _draw_icon(self, surface, area, progress, spec):
        self._asset_center(surface, "mode_bg", area.center, (area.width - 80, 260), 155)
        eased = _smooth(progress)
        old = self.assets.fitted("mode_2k", (560, 250))
        new = self.assets.fitted("mode_4k", (560, 250))
        old_scale = 1 - .18 * eased
        old = pygame.transform.smoothscale(old, (round(old.get_width() * old_scale), round(old.get_height() * old_scale)))
        old.set_alpha(round(255 * max(0.0, 1 - progress / .62)))
        if progress < .72:
            scale = .62 + .45 * _out(progress / .72)
        else:
            scale = 1.07 + (1 - 1.07) * ((progress - .72) / .28)
        new = pygame.transform.smoothscale(new, (round(new.get_width() * scale), round(new.get_height() * scale)))
        new.set_alpha(round(255 * min(1.0, max(0.0, (progress - .08) / .48))))
        surface.blit(old, old.get_rect(center=area.center))
        surface.blit(new, new.get_rect(center=area.center))

    def _draw_horizontal_morph(self, surface, area, progress, spec):
        eased = _smooth(progress)
        logo = self.assets.fitted("title_logo", (570, 230))
        scale = 1 - .52 * progress
        logo = pygame.transform.smoothscale(logo, (round(logo.get_width() * scale), round(logo.get_height() * scale)))
        logo.set_alpha(round(255 * (1 - progress)))
        surface.blit(logo, logo.get_rect(center=(round(area.centerx - 250 * eased), round(area.centery - 170 * eased))))
        select = self.assets.fitted("select_bg", (720, 240))
        select = select.copy()
        select.set_alpha(round(255 * eased))
        x = area.right - round((select.get_width() + 50) * eased)
        surface.blit(select, (x, area.centery - select.get_height() // 2))

    def _draw_arrows(self, surface, area, progress, spec):
        travel = 24 * math.sin(progress * math.tau)
        left = self.assets.fitted("next_arrow_left", (144, 52))
        right = self.assets.fitted("next_arrow", (144, 52))
        surface.blit(left, left.get_rect(center=(round(area.centerx - 245 - travel), area.centery)))
        self._text(surface, "NEXT", self.large, area.center)
        surface.blit(right, right.get_rect(center=(round(area.centerx + 245 + travel), area.centery)))

    def _draw_curtain(self, surface, area, progress, spec):
        layer = self.assets.fitted("main_layer", (300, area.height - 30))
        surface.blit(layer, layer.get_rect(center=area.center))
        phase = progress / .47 if progress < .47 else (1 - progress) / .53
        amount = _smooth(min(1.0, max(0.0, phase)))
        height = round(area.height / 2 * amount)
        pygame.draw.rect(surface, (45, 36, 57), (area.left, area.top, area.width, height))
        pygame.draw.rect(surface, (45, 36, 57), (area.left, area.bottom - height, area.width, height))

    def _draw_fade(self, surface, area, progress, spec):
        opacity = _smooth(progress / .48) if progress < .48 else _smooth((1 - progress) / .52)
        self._asset_center(surface, "logo", area.center, (600, 220))
        layer = pygame.Surface(area.size, pygame.SRCALPHA)
        layer.fill((0, 0, 0, round(255 * opacity)))
        surface.blit(layer, area)

    def _draw_preview(self, surface, area, progress, spec):
        alpha = round(255 * _smooth(progress))
        frame = self.assets.video_frame(progress * spec.duration)
        if frame is not None:
            frame = pygame.transform.smoothscale(frame, (510, 450))
            frame.set_alpha(alpha)
            surface.blit(frame, frame.get_rect(center=area.center))

    def _draw_bga(self, surface, area, progress, spec):
        game = spec.variant == "game"
        frame = self.assets.video_frame(progress * spec.duration, game)
        if frame is None:
            return
        maximum = (900, area.height - 40) if game else (510, 450)
        scale = min(maximum[0] / frame.get_width(), maximum[1] / frame.get_height())
        frame = pygame.transform.smoothscale(frame, (round(frame.get_width() * scale), round(frame.get_height() * scale)))
        surface.blit(frame, frame.get_rect(center=area.center))

    def _draw_note(self, surface, area, progress, spec):
        lanes = 4 if spec.variant == "4K" else 2
        layer_name = "main_layer_4k" if lanes == 4 else "main_layer"
        layer = self.assets.fitted(layer_name, (area.width - 200, area.height - 20))
        playfield = layer.get_rect(center=area.center)
        surface.blit(layer, playfield)
        lane_width = playfield.width / lanes
        start_y = playfield.top + round((505 - 470) / 1450 * playfield.height)
        production_hit_y = 1850 if lanes == 4 else 1560
        judgement_y = playfield.top + round((production_hit_y - 470) / 1450 * playfield.height)
        line_name = "line_4k" if lanes == 4 else "line"
        line = self.assets.scaled(line_name, (playfield.width, max(4, round(33 / 1450 * playfield.height))))
        surface.blit(line, (playfield.left, judgement_y))
        note_y = start_y + (judgement_y - start_y) * progress
        note_name = "note_4k_0" if lanes == 4 else "note_0"
        note = self.assets.scaled(note_name, (round(lane_width), max(8, round(45 / 1450 * playfield.height))))
        if spec.variant == "HOLD":
            tail_y = max(start_y, note_y - playfield.height * .38)
            pygame.draw.rect(
                surface, (20, 95, 218),
                (playfield.left + lane_width * .112, tail_y + note.get_height() / 2, lane_width * .776, note_y - tail_y),
            )
            surface.blit(note, (playfield.left, round(tail_y)))
            surface.blit(note, (playfield.left, round(note_y)))
        else:
            for lane in range(lanes):
                if lane % 2 == 0 or lanes == 2:
                    name = f"note_4k_{lane % 2}" if lanes == 4 else f"note_{lane % 2}"
                    lane_note = self.assets.scaled(name, (round(lane_width), note.get_height()))
                    surface.blit(lane_note, (round(playfield.left + lane * lane_width), round(note_y)))

    def _draw_lane_help(self, surface, area, progress, spec):
        layer = self.assets.fitted("main_layer", (300, area.height - 20))
        playfield = layer.get_rect(center=area.center)
        surface.blit(layer, playfield)
        line_y = playfield.top + round((1560 - 470) / 1450 * playfield.height)
        line = self.assets.scaled("line", (playfield.width, max(4, round(33 / 1450 * playfield.height))))
        surface.blit(line, (playfield.left, line_y))
        frames = self.assets.sequence("lane_help_2k_0")
        frame = frames[min(len(frames) - 1, round(progress * (len(frames) - 1)))]
        lane_width = playfield.width // 2
        scale = lane_width / frame.get_width()
        frame = pygame.transform.smoothscale(
            frame, (lane_width, max(1, round(frame.get_height() * scale))),
        )
        surface.blit(frame, frame.get_rect(bottomleft=(playfield.left, line_y + 8)))

    def _draw_demonstration(self, surface, area, progress, spec):
        frame = self.assets.video_frame(progress * spec.duration, True)
        if frame is not None:
            maximum = (700, area.height - 20)
            scale = min(maximum[0] / frame.get_width(), maximum[1] / frame.get_height())
            frame = pygame.transform.smoothscale(
                frame, (round(frame.get_width() * scale), round(frame.get_height() * scale)),
            )
            surface.blit(frame, frame.get_rect(center=area.center))
        frames = self.assets.sequence("demonstration_able")
        overlay = frames[min(len(frames) - 1, round(progress * (len(frames) - 1)))]
        overlay = pygame.transform.smoothscale(
            overlay, (min(area.width - 100, overlay.get_width()), min(150, overlay.get_height())),
        )
        surface.blit(overlay, overlay.get_rect(center=area.center))

    def _draw_catch_fall(self, surface, area, progress, spec):
        field = pygame.Rect(0, 0, 620, area.height - 20)
        field.center = area.center
        particle = self.assets.fitted("catch_particle", field.size).copy()
        particle.set_alpha(95)
        surface.blit(particle, particle.get_rect(center=field.center))
        line_y = field.bottom - 52
        line = self.assets.scaled("catch_line", (field.width, 20))
        surface.blit(line, (field.left, line_y))
        catcher = self.assets.fitted("catcher", (175, 110))
        surface.blit(catcher, catcher.get_rect(midbottom=(field.centerx, line_y + 3)))
        item = self.assets.fitted("catch_object", (62, 62))
        x = field.centerx + 170 * math.sin(progress * math.pi * .8)
        y = field.top + 20 + (line_y - field.top - 50) * progress
        surface.blit(item, item.get_rect(center=(round(x), round(y))))

    def _draw_result(self, surface, area, progress, spec):
        eased = _back(progress)
        card = self.assets.fitted("result_bg", (760, area.height - 40))
        y = area.bottom + card.get_height() / 2 - (area.height / 2 + card.get_height() / 2) * eased
        surface.blit(card, card.get_rect(center=(area.centerx, round(y))))
        rank_progress = min(1.0, max(0.0, (progress * spec.duration - .62) / .72))
        frames = self.assets.sequence("rank_s")
        rank = frames[min(len(frames) - 1, round(rank_progress * (len(frames) - 1)))]
        scale = min(150 / rank.get_width(), 180 / rank.get_height())
        rank = pygame.transform.smoothscale(rank, (round(rank.get_width() * scale), round(rank.get_height() * scale)))
        surface.blit(rank, rank.get_rect(center=(area.centerx + 190, round(y + 35))))

    def _draw_rank(self, surface, area, progress, spec):
        card = self.assets.fitted("result_bg", (760, area.height - 40))
        card.set_alpha(175)
        surface.blit(card, card.get_rect(center=area.center))
        self._sequence_center(surface, "rank_s", progress, area.center, (280, 330))

    def _draw_wave(self, surface, area, progress, spec):
        name = spec.variant.lower()
        self._sequence_center(surface, name, progress, area.center, (area.width - 100, 180))

    def _draw_count(self, surface, area, progress, spec):
        value = round(int(spec.variant) * _out(progress))
        background_name = "total_result_layout" if spec.variant == "27000" else "result_bg"
        self._asset_center(surface, background_name, area.center, (760, area.height - 30), 190)
        self._text(surface, f"{value:,}", self.large, (area.centerx, area.centery + 70))

    def _draw_ending(self, surface, area, progress, spec):
        logo_progress = _smooth(min(1.0, max(0.0, (progress * spec.duration - .18) / .92)))
        thanks_progress = _smooth(min(1.0, max(0.0, (progress * spec.duration - .82) / .78)))
        logo_scale = .78 + .22 * logo_progress + .025 * math.sin(logo_progress * math.pi)
        logo = self.assets.fitted("title_logo", (560, 230))
        logo = pygame.transform.smoothscale(logo, (round(logo.get_width() * logo_scale), round(logo.get_height() * logo_scale)))
        logo.set_alpha(round(255 * logo_progress))
        surface.blit(logo, logo.get_rect(center=(area.centerx, round(area.centery - 80 - 40 * logo_progress))))
        thanks = self.assets.fitted("thanksforplaying", (650, 70)).copy()
        thanks.set_alpha(round(255 * thanks_progress))
        surface.blit(thanks, thanks.get_rect(center=(area.centerx, round(area.centery + 110 - 34 * thanks_progress))))

    def _draw_catcher(self, surface, area, progress, spec):
        velocity_curve = 1 - math.exp(-7 * progress)
        friction = math.exp(-2.8 * progress)
        x = area.left + 160 + (area.width - 320) * velocity_curve * friction
        line = self.assets.scaled("catch_line", (area.width - 160, 22))
        surface.blit(line, line.get_rect(center=(area.centerx, area.centery + 130)))
        catcher = self.assets.fitted("catcher", (210, 135))
        surface.blit(catcher, catcher.get_rect(midbottom=(round(x), area.centery + 132)))

    def _draw_burst(self, surface, area, progress, spec):
        self._asset_center(surface, "catch_object", area.center, (96, 96))
        self._sequence_center(surface, "catch_burst", progress, area.center, (260, 260))

    def _draw_combo(self, surface, area, progress, spec):
        catch = spec.variant.startswith("X")
        if catch:
            line = self.assets.scaled("catch_line", (area.width - 200, 22))
            surface.blit(line, line.get_rect(center=(area.centerx, area.centery + 145)))
            catcher = self.assets.fitted("catcher", (210, 135))
            surface.blit(catcher, catcher.get_rect(midbottom=(area.centerx + 260, area.centery + 147)))
            bounce = math.sin(progress * math.pi) * 22
            size_scale = (80 + math.sin(progress * math.pi) * 12) / 80
            center = (area.centerx - 260, round(area.centery - bounce))
            image = self.large.render(spec.variant, True, WHITE)
            image = pygame.transform.smoothscale(image, (round(image.get_width() * size_scale), round(image.get_height() * size_scale)))
            surface.blit(image, image.get_rect(center=center))
            return
        layer = self.assets.fitted("main_layer", (250, area.height - 30))
        surface.blit(layer, layer.get_rect(center=area.center))
        if progress < .34:
            eased = _smooth(progress / .34)
            scale = (70 + 14 * eased) / 78
            y = area.centery - 14 * eased
        elif progress < .70:
            eased = _smooth((progress - .34) / .36)
            scale = (84 - 7 * eased) / 78
            y = area.centery - 14 + 7 * eased
        else:
            eased = _smooth((progress - .70) / .30)
            scale = (77 + eased) / 78
            y = area.centery - 7 - eased
        image = self.large.render("125", True, WHITE)
        image = pygame.transform.smoothscale(image, (round(image.get_width() * scale), round(image.get_height() * scale)))
        self._text(surface, "COMBO", self.font, (area.centerx, round(y - 68)))
        surface.blit(image, image.get_rect(center=(area.centerx, round(y + 20))))

    def _draw_health(self, surface, area, progress, spec):
        start, end = ((45, 86) if spec.variant == "gain" else (86, 34))
        value = start + (end - start) * _smooth(progress)
        pulse = math.sin(progress * math.pi) * (.08 if spec.variant == "gain" else .13)
        shake = math.sin(progress * math.pi * 6) * 4 * (1 - progress) if spec.variant == "loss" else 0
        background = self.assets.fitted("health_bg", (42, 520))
        health = self.assets.fitted("health", (42, 520))
        visible_height = max(1, round(health.get_height() * value / 100))
        fill = health.subsurface((0, health.get_height() - visible_height, health.get_width(), visible_height)).copy()
        fill = pygame.transform.smoothscale(fill, (max(1, round(fill.get_width() * (1 + pulse))), fill.get_height()))
        center_x = round(area.centerx + shake)
        surface.blit(background, background.get_rect(center=area.center))
        surface.blit(fill, fill.get_rect(midbottom=(center_x, area.centery + background.get_height() // 2)))

    def _draw_judgement(self, surface, area, progress, spec):
        layer = self.assets.fitted("main_layer", (250, area.height - 30))
        surface.blit(layer, layer.get_rect(center=area.center))
        self._sequence_center(surface, spec.variant, progress, area.center, (520, 160))
