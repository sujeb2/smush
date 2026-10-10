import math
import random
import time

from PIL import Image, ImageDraw, ImageTk

from particles import ParticleSystem, blend

PHASES = ("convey", "crush", "reset")
PHASE_LABELS = {"convey": "운반", "crush": "압축", "reset": "복귀"}
# Matches sensor_io.ino: CONV_FORWARD_FOR, MOTOR_RUNNING_FOR, MOTOR_BRAKE_FOR + MOTOR_RUNNING_FOR.
DEFAULT_DURATIONS = {"convey": 6.5, "crush": 13.0, "reset": 13.15}
TITLES = {
    "convey": "운반하는 중",
    "crush": "압축하는 중",
    "reset": "원위치로 돌아가는 중",
    "trash_full": "쓰레기통이 꽉 찼어요",
}

CARD = "#2b2b2e"
AMBER = "#ffb020"
GREEN = "#28c68d"
RED = "#ff5a52"
RED_LIGHT = "#ff9a8f"
GRAY = "#56565c"
BELT = "#4a4a52"
BELT_DASH = "#80808a"
MUTED = "#b2b2ba"
CAN = "#d2d6dc"
CAN_BAND = "#a0a4ac"

CARD_BOX = (60, 780, 1020, 1480)
ICON_X = 540
BASE_Y = 980
CAN_HEIGHT = 150
CAN_FLAT = 55
RAISED_PLATE = BASE_Y - CAN_HEIGHT - 18
BAR_LEFT, BAR_RIGHT, BAR_Y, BAR_GAP = 150, 930, 1150, 14
SLIDE_DISTANCE = 160
OVERLAY_ALPHAS = (30, 60, 90, 120)


def ease_in_out(t):
    return (1.0 - math.cos(math.pi * max(0.0, min(1.0, t)))) / 2.0


def ease_out_cubic(t):
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def ease_out_bounce(t):
    t = max(0.0, min(1.0, t))
    if t < 1 / 2.75:
        return 7.5625 * t * t
    if t < 2 / 2.75:
        t -= 1.5 / 2.75
        return 7.5625 * t * t + 0.75
    if t < 2.5 / 2.75:
        t -= 2.25 / 2.75
        return 7.5625 * t * t + 0.9375
    t -= 2.625 / 2.75
    return 7.5625 * t * t + 0.984375


class MachineCycle:
    """Tracks the conveyor -> crush -> reset cycle and how far along each phase is.

    New firmware reports `phase:<name>:<remaining ms>` on every transition and once a
    second. Older firmware only says `crushing_busy` / `crushing_done`, so the cycle is
    then estimated from the default durations.
    """

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.phase = None
        self.ends_at = 0.0
        self.total = 1.0
        self.durations = dict(DEFAULT_DURATIONS)
        self.reported = False

    def report(self, name, remaining):
        self.reported = True
        if name not in PHASES:
            self.phase = None
            return
        remaining = max(0.0, remaining)
        if name != self.phase:
            self.phase = name
            self.total = max(remaining, 0.001)
            self.durations[name] = self.total
        self.ends_at = self.clock() + remaining

    def legacy(self, command):
        if command == "dropped" and self.phase is None:
            self._start("convey")
        elif command == "crushing_busy" and self.phase not in ("crush", "reset"):
            self._start("crush")
        elif command in ("crushing_idle", "crushing_done"):
            self.phase = None

    def tick(self):
        """Advances estimated phases; reported phases wait for the firmware instead."""
        if self.phase is None or self.reported or self.clock() < self.ends_at:
            return False
        following = {"convey": "crush", "crush": "reset"}.get(self.phase)
        if following is None:
            return False
        self._start(following, self.ends_at)
        return True

    def progress(self):
        if self.phase is None:
            return 0.0
        return 1.0 - max(0.0, min(1.0, (self.ends_at - self.clock()) / self.total))

    def remaining(self):
        if self.phase is None:
            return 0.0
        later = PHASES[PHASES.index(self.phase) + 1:]
        return max(0.0, self.ends_at - self.clock()) + sum(self.durations[name] for name in later)

    def _start(self, name, started=None):
        self.phase = name
        self.total = self.durations[name]
        self.ends_at = (self.clock() if started is None else started) + self.total


class StatusCard:
    """Slide-up card over the counter scene for crusher phases and the full-bin warning."""

    def __init__(self, ui, cycle, font_path):
        self.ui = ui
        self.cycle = cycle
        self.font_path = font_path
        self.kind = None
        self.target_kind = None
        self.reveal = 0.0
        self.reveal_from = 0.0
        self.reveal_target = 0.0
        self.reveal_started = 0.0
        self.reveal_duration = 0.45
        self.job = None
        self.items = {}
        self.text_cache = {}
        self.shown_text = {}
        self.sparks = None
        self.spark_budget = 0.0
        self.last_frame = 0.0
        self.anim_started = 0.0
        self.built = False

    @property
    def visible(self):
        return self.kind is not None and self.reveal > 0.0

    def build(self):
        """Creates canvas items for the current scale; call after the scene is rebuilt."""
        ui = self.ui
        canvas = ui.canvas
        self.text_cache.clear()
        self.shown_text.clear()
        self.items = {}
        x0, y0 = ui._x(0), ui._y(0)
        width = max(1, round(1080 * ui.scale))
        height = max(1, round(1920 * ui.scale))
        self.overlay_photos = [ImageTk.PhotoImage(Image.new("RGBA", (width, height), (0, 0, 0, alpha)))
                               for alpha in OVERLAY_ALPHAS]
        self.items["overlay"] = canvas.create_image(x0, y0, image=self.overlay_photos[0], anchor="nw",
                                                    state="hidden", tags=("status_card",))
        self.card_photo = ImageTk.PhotoImage(self._card_image())
        self.items["card"] = canvas.create_image(0, 0, image=self.card_photo, anchor="nw",
                                                 state="hidden", tags=("status_card",))

        def shape(name, factory, group, *args, **kwargs):
            points = (0, 0, 0, 0, 0, 0) if factory == canvas.create_polygon else (0, 0, 0, 0)
            self.items[name] = factory(*points, *args, state="hidden", tags=("status_card", group), **kwargs)

        line, rect, poly = canvas.create_line, canvas.create_rectangle, canvas.create_polygon
        # Cycle card: conveyor belt, press and can.
        shape("belt", line, "cycle", fill=BELT, capstyle="round")
        for index in range(6):
            shape(f"belt_dash{index}", line, "cycle", fill=BELT_DASH, capstyle="round")
        shape("base", rect, "cycle", fill=GRAY, outline="")
        shape("can", rect, "cycle", fill=CAN, outline="")
        shape("can_band1", line, "cycle", fill=CAN_BAND)
        shape("can_band2", line, "cycle", fill=CAN_BAND)
        shape("arm", rect, "cycle", fill=AMBER, outline="")
        shape("plate", line, "cycle", fill=AMBER, capstyle="round")
        shape("impact_left", line, "cycle", fill=AMBER, capstyle="round")
        shape("impact_right", line, "cycle", fill=AMBER, capstyle="round")
        for index, name in enumerate(PHASES):
            shape(f"track_{name}", line, "cycle", fill=GRAY, capstyle="round")
            shape(f"fill_{name}", line, "cycle", fill=AMBER, capstyle="round")
            shape(f"check_{name}", line, "cycle", fill=GREEN, capstyle="round", joinstyle="round")
        # Full-bin card: bin with a bouncing lid, and a pulsing pill.
        shape("bin_item0", rect, "full", fill=CAN, outline="")
        shape("bin_item1", rect, "full", fill=CAN, outline="")
        shape("bin_item2", rect, "full", fill=CAN, outline="")
        shape("bin_body", poly, "full", fill="", outline=RED, joinstyle="round")
        shape("bin_lid", poly, "full", fill=RED, outline="")
        shape("pill", line, "full", fill=RED, capstyle="round")
        for name in ("title", "eta", "note", "label_convey", "label_crush", "label_reset", "pill_text"):
            self.items[name] = canvas.create_image(0, 0, anchor="center", state="hidden", tags=("status_card",))
        self.sparks = ParticleSystem(ui, CARD, ("status_card", "sparks"))
        self.built = True
        self._render()

    def set_kind(self, kind):
        """Shows the card for kind (a phase or "trash_full"), or hides it for None."""
        family = lambda value: None if value is None else "full" if value == "trash_full" else "cycle"
        if kind is None:
            self._animate_reveal(0.0)
            return
        restart = family(kind) != family(self.kind)
        if restart:
            self.reveal = 0.0  # a different card opens fresh instead of morphing
            self.anim_started = time.monotonic()
            if self.sparks is not None:
                self.sparks.clear()
        self.kind = kind
        self._animate_reveal(1.0, restart)

    def destroy(self):
        if self.job is not None:
            self.ui.root.after_cancel(self.job)
            self.job = None
        self.built = False

    def _animate_reveal(self, target, restart=False):
        if not restart and target == self.reveal_target and (self.job is not None or self.reveal == target):
            self._render()
            return
        self.reveal_target = target
        self.reveal_from = self.reveal
        self.reveal_started = time.monotonic()
        self._schedule(immediate=True)

    def _schedule(self, immediate=False):
        if self.job is not None:
            self.ui.root.after_cancel(self.job)
            self.job = None
        if immediate:
            self._frame()
        else:
            self.job = self.ui.root.after(16, self._frame)

    def _frame(self):
        self.job = None
        if not self.ui.running:
            return
        now = time.monotonic()
        dt = min(0.05, max(0.0, now - self.last_frame)) if self.last_frame else 0.016
        self.last_frame = now
        elapsed = min(1.0, (now - self.reveal_started) / self.reveal_duration)
        self.reveal = self.reveal_from + (self.reveal_target - self.reveal_from) * ease_in_out(elapsed)
        if elapsed >= 1.0 and self.reveal_target == 0.0:
            self.kind = None
            if self.sparks is not None:
                self.sparks.clear()
        self.cycle.tick()
        if self.kind in PHASES and self.cycle.phase in PHASES:
            self.kind = self.cycle.phase
        self._render(now, dt)
        if self.kind is not None or elapsed < 1.0:
            # The full-bin card can stay up for hours, so it animates at a lower rate.
            delay = 33 if self.kind == "trash_full" and elapsed >= 1.0 else 16
            self.job = self.ui.root.after(delay, self._frame)

    # Drawing -----------------------------------------------------------------

    def _card_image(self):
        scale = self.ui.scale
        x0, y0, x1, y1 = CARD_BOX
        size = (max(1, round((x1 - x0) * scale)), max(1, round((y1 - y0) * scale)))
        image = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(image).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=round(44 * scale),
                                                fill=CARD)
        return image

    def _text(self, name, text, size, color, x, y, slide):
        canvas = self.ui.canvas
        key = (text, size, color)
        if self.shown_text.get(name) != key:
            photo = self.text_cache.get(key)
            if photo is None:
                photo = self.ui._text_photo(text, size, color=color, font_path=self.font_path)
                self.text_cache[key] = photo
            canvas.itemconfigure(self.items[name], image=photo)
            self.shown_text[name] = key
        canvas.coords(self.items[name], self.ui._x(x), self.ui._y(y + slide))
        canvas.itemconfigure(self.items[name], state="normal")

    def _line(self, name, points, width, slide, color=None):
        ui = self.ui
        coords = [ui._x(value) if index % 2 == 0 else ui._y(value + slide) for index, value in enumerate(points)]
        ui.canvas.coords(self.items[name], *coords)
        options = {"width": max(1.0, width * ui.scale), "state": "normal"}
        if color is not None:
            options["fill"] = color
        ui.canvas.itemconfigure(self.items[name], **options)

    def _box(self, name, x0, y0, x1, y1, slide, color=None):
        ui = self.ui
        ui.canvas.coords(self.items[name], ui._x(x0), ui._y(y0 + slide), ui._x(x1), ui._y(y1 + slide))
        options = {"state": "normal"}
        if color is not None:
            options["fill"] = color
        ui.canvas.itemconfigure(self.items[name], **options)

    def _hide(self, *names):
        for name in names:
            self.ui.canvas.itemconfigure(self.items[name], state="hidden")

    def _render(self, now=None, dt=0.0):
        if not self.built or self.ui.screen_state != "ready":
            return
        canvas = self.ui.canvas
        if self.kind is None or self.reveal <= 0.0:
            canvas.itemconfigure("status_card", state="hidden")
            return
        now = time.monotonic() if now is None else now
        eased = ease_out_cubic(self.reveal)
        slide = (1.0 - eased) * SLIDE_DISTANCE
        level = min(len(self.overlay_photos), max(1, round(eased * len(self.overlay_photos))))
        canvas.itemconfigure(self.items["overlay"], image=self.overlay_photos[level - 1], state="normal")
        canvas.coords(self.items["card"], self.ui._x(CARD_BOX[0]), self.ui._y(CARD_BOX[1] + slide))
        canvas.itemconfigure(self.items["card"], state="normal")
        if self.kind == "trash_full":
            canvas.itemconfigure("cycle", state="hidden")
            self._hide("eta", "label_convey", "label_crush", "label_reset")
            self._render_full(now, slide, dt)
        else:
            canvas.itemconfigure("full", state="hidden")
            self._hide("pill_text")
            self._render_cycle(now, slide, dt)
        canvas.tag_raise("status_card")

    def _render_cycle(self, now, slide, dt):
        phase = self.kind
        finished = self.cycle.phase is None  # card is closing after the cycle ended
        progress = self.cycle.progress() if self.cycle.phase == phase else 1.0
        t = now - self.anim_started
        self._render_press(phase, progress, t, slide, dt)
        self._render_bar(len(PHASES) if finished else PHASES.index(phase), progress, slide)
        self._text("title", TITLES[phase], 64, "white", 540, 1080, slide)
        seconds = math.ceil(self.cycle.remaining()) if self.cycle.phase == phase else 0
        if finished:
            self._text("eta", "완료됐어요", 40, GREEN, 540, 1302, slide)
        else:
            self._text("eta", f"약 {seconds}초 남음" if seconds > 0 else "거의 다 됐어요", 40, MUTED, 540, 1302, slide)
        if phase == "reset":
            self._text("note", "곧 다시 사용할 수 있어요", 38, GREEN, 540, 1390, slide)
        else:
            self._text("note", "압축 중에는 캔·페트병을 넣지 마세요", 38, RED, 540, 1390, slide)

    def _render_press(self, phase, progress, t, slide, dt):
        accent = GREEN if phase == "reset" else AMBER
        can_x, can_height, shake = 0.0, CAN_HEIGHT, 0.0
        can_visible = True
        if phase == "convey":
            # Can rides the belt in from the left and bobs on the rollers.
            can_x = -150 * (1.0 - ease_in_out(progress))
            plate_bottom = RAISED_PLATE
            bob = math.sin(t * 14) * 2.5 if progress < 1.0 else 0.0
            self._line("belt", (ICON_X - 170, BASE_Y + 6, ICON_X + 170, BASE_Y + 6), 18, slide)
            offset = (t * 90) % 56
            for index in range(6):
                x = ICON_X - 160 + offset + index * 56
                if x > ICON_X + 160:
                    x -= 6 * 56
                self._line(f"belt_dash{index}", (x, BASE_Y + 6, x + 14, BASE_Y + 6), 6, slide)
            self._hide("base")
        else:
            bob = 0.0
            self._hide("belt", *(f"belt_dash{index}" for index in range(6)))
            self._box("base", ICON_X - 120, BASE_Y, ICON_X + 120, BASE_Y + 10, slide)
            if phase == "crush":
                squash = ease_in_out(progress)
                can_height = CAN_HEIGHT - (CAN_HEIGHT - CAN_FLAT) * squash
                approach = 18 * max(0.0, 1.0 - progress * 10)
                plate_bottom = BASE_Y - can_height - approach
                shake = math.sin(t * 55) * 2.5 if progress < 1.0 else 0.0
                self._emit_sparks(plate_bottom, dt, slide)
            else:
                # Press lifts back up while the flattened can slides off the base.
                rise = ease_in_out(progress)
                plate_bottom = BASE_Y - CAN_FLAT - (BASE_Y - CAN_FLAT - RAISED_PLATE) * rise
                can_height = CAN_FLAT
                slide_off = ease_in_out(min(1.0, progress / 0.4))
                can_x = 190 * slide_off
                can_visible = slide_off < 1.0
        if can_visible:
            left, right = ICON_X - 48 + can_x, ICON_X + 48 + can_x
            top = BASE_Y - can_height + bob
            self._box("can", left, top, right, BASE_Y + bob, slide)
            for index in (1, 2):
                y = top + can_height * index / 3
                self._line(f"can_band{index}", (left, y, right, y), 4, slide)
        else:
            self._hide("can", "can_band1", "can_band2")
        arm_top = CARD_BOX[1] + 24
        plate_y = plate_bottom - 11
        self._box("arm", ICON_X - 8 + shake, arm_top, ICON_X + 8 + shake, max(arm_top, plate_y), slide, accent)
        self._line("plate", (ICON_X - 90 + shake, plate_y, ICON_X + 90 + shake, plate_y), 22, slide, accent)
        if phase == "crush" and progress < 1.0:
            pulse = 0.6 + 0.4 * math.sin(t * 18)
            for name, direction in (("impact_left", -1), ("impact_right", 1)):
                x = ICON_X + direction * 112
                self._line(name, (x, plate_bottom + 8, x - direction * 12 * pulse, plate_bottom + 8 + 34 * pulse),
                           6, slide)
        else:
            self._hide("impact_left", "impact_right")
        if self.sparks is not None:
            self.sparks.update(dt)

    def _emit_sparks(self, plate_bottom, dt, slide):
        if self.sparks is None or dt <= 0:
            return
        self.spark_budget += dt * 22
        while self.spark_budget >= 1.0:
            self.spark_budget -= 1.0
            direction = random.choice((-1, 1))
            self.sparks.emit(ICON_X + direction * random.uniform(40, 60), plate_bottom + 4 + slide,
                             direction * random.uniform(90, 230), -random.uniform(60, 190),
                             random.uniform(0.3, 0.55), random.uniform(4, 6),
                             random.choice((AMBER, "#ffe08a", "#ffffff")), gravity=700, drag=1.2)

    def _render_bar(self, current, progress, slide):
        total = sum(self.cycle.durations[name] for name in PHASES)
        width = BAR_RIGHT - BAR_LEFT - BAR_GAP * (len(PHASES) - 1)
        radius = 11
        x = BAR_LEFT
        for index, name in enumerate(PHASES):
            segment = width * self.cycle.durations[name] / total
            left, right = x + radius, x + segment - radius
            self._line(f"track_{name}", (left, BAR_Y, right, BAR_Y), 22, slide)
            if index < current or (index == current and progress > 0):
                fraction = 1.0 if index < current else progress
                color = GREEN if index < current else AMBER
                end = left + max(0.001, (right - left) * fraction)
                self._line(f"fill_{name}", (left, BAR_Y, end, BAR_Y), 22, slide, color)
            else:
                self._hide(f"fill_{name}")
            color = GREEN if index < current else AMBER if index == current else MUTED
            center = x + segment / 2
            self._text(f"label_{name}", PHASE_LABELS[name], 36, color, center, BAR_Y + 62, slide)
            if index < current:
                cx, cy = center - 62, BAR_Y + 62
                self._line(f"check_{name}", (cx - 10, cy, cx - 2, cy + 9, cx + 12, cy - 9), 6, slide)
            else:
                self._hide(f"check_{name}")
            x += segment + BAR_GAP

    def _render_full(self, now, slide, dt):
        t = now - self.anim_started
        cx, cy = ICON_X, 920
        cycle_time = t % 1.8
        lift = 0.0
        tilt = 0.0
        if cycle_time < 0.25:
            lift = ease_out_cubic(cycle_time / 0.25)
        elif cycle_time < 0.85:
            lift = 1.0 - ease_out_bounce((cycle_time - 0.25) / 0.6)
        tilt = lift * math.radians(-12)
        if self.sparks is not None and dt > 0 and 0.18 <= cycle_time < 0.18 + dt:
            for _ in range(5):  # scraps pop out each time the lid flips up
                self.sparks.emit(cx + random.uniform(-50, 50), cy - 90 + slide, random.uniform(-140, 140),
                                 -random.uniform(220, 380), random.uniform(0.5, 0.8), random.uniform(7, 10),
                                 random.choice((CAN, "#9fd3ff", AMBER)), gravity=900, drag=0.8)
        for index in range(3):
            y = cy + 80 - index * 45
            self._box(f"bin_item{index}", cx - 60, y - 30, cx + 60, y, slide)
        self._polygon("bin_body", ((cx - 80, cy - 70), (cx + 80, cy - 70), (cx + 70, cy + 110), (cx - 70, cy + 110)),
                      slide, outline_width=10)
        hinge_x, hinge_y = cx - 100, cy - 70 - lift * 26
        corners = ((cx - 100, cy - 100), (cx + 100, cy - 100), (cx + 100, cy - 70), (cx - 100, cy - 70))
        rotated = []
        for x, y in corners:
            dx, dy = x - (cx - 100), y - (cy - 70)
            rotated.append((hinge_x + dx * math.cos(tilt) - dy * math.sin(tilt),
                            hinge_y + dx * math.sin(tilt) + dy * math.cos(tilt)))
        self._polygon("bin_lid", rotated, slide)
        pulse = (math.sin(t * math.tau * 0.9) + 1.0) / 2.0
        self._line("pill", (350, 1320, 730, 1320), 100, slide, blend(RED, RED_LIGHT, pulse * 0.55))
        self._text("title", TITLES["trash_full"], 64, "white", 540, 1100, slide)
        self._text("note", "더 이상 캔·페트병을 받을 수 없어요", 40, MUTED, 540, 1190, slide)
        self._text("pill_text", "관리자에게 알려 주세요", 38, "white", 540, 1320, slide)
        if self.sparks is not None:
            self.sparks.update(dt)

    def _polygon(self, name, points, slide, outline_width=None):
        ui = self.ui
        coords = []
        for x, y in points:
            coords.extend((ui._x(x), ui._y(y + slide)))
        ui.canvas.coords(self.items[name], *coords)
        options = {"state": "normal"}
        if outline_width is not None:
            options["width"] = max(1.0, outline_width * ui.scale)
        ui.canvas.itemconfigure(self.items[name], **options)
