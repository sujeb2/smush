import math
import random

FADE_STEPS = 8


def hex_to_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[index:index + 2], 16) for index in (0, 2, 4))


def blend(color, background, amount):
    """Mixes color toward background; amount 0 keeps color, 1 is background."""
    source, target = hex_to_rgb(color), hex_to_rgb(background)
    return "#" + "".join(f"{round(s + (t - s) * amount):02x}" for s, t in zip(source, target))


class Particle:
    __slots__ = ("x", "y", "px", "py", "vx", "vy", "age", "life", "size", "color", "gravity", "drag",
                 "twinkle", "on_expire", "item", "fade_step", "visible")

    def __init__(self, x, y, vx, vy, life, size, color, gravity, drag, twinkle, on_expire):
        self.x = self.px = x
        self.y = self.py = y
        self.vx, self.vy = vx, vy
        self.age = 0.0
        self.life = life
        self.size = size
        self.color = color
        self.gravity = gravity
        self.drag = drag
        self.twinkle = twinkle
        self.on_expire = on_expire
        self.item = None
        self.fade_step = -1
        self.visible = True


class ParticleSystem:
    """Streak particles in design coordinates, drawn as round-capped canvas lines.

    Tk has no alpha for vector items, so particles fade by blending toward the
    background color; colors are quantized so itemconfigure runs only a few times
    per particle instead of every frame.
    """

    def __init__(self, ui, background, tag, below=None):
        self.ui = ui
        self.background = background
        self.tag = tag
        self.below = below
        self.particles = []

    def emit(self, x, y, vx, vy, life, size, color, gravity=0.0, drag=0.0, twinkle=False, on_expire=None):
        particle = Particle(x, y, vx, vy, life, size, color, gravity, drag, twinkle, on_expire)
        self.particles.append(particle)
        return particle

    def burst(self, x, y, count, speed, colors, life=(0.9, 1.4), size=(5, 8), gravity=180.0, drag=2.2,
              twinkle=0.0, spread=math.tau, direction=0.0):
        for index in range(count):
            angle = direction + spread * (index / count - 0.5 if spread < math.tau else index / count)
            angle += random.uniform(-0.09, 0.09)
            velocity = speed * random.uniform(0.55, 1.0)
            self.emit(x, y, math.cos(angle) * velocity, math.sin(angle) * velocity,
                      random.uniform(*life), random.uniform(*size), random.choice(colors),
                      gravity=gravity, drag=drag, twinkle=random.random() < twinkle)

    def update(self, dt):
        alive = []
        spawned = []
        for particle in self.particles:
            particle.age += dt
            if particle.age < 0:  # scheduled to appear later
                alive.append(particle)
                continue
            if particle.age >= particle.life:
                self._delete(particle)
                if particle.on_expire is not None:
                    spawned.append(particle)
                continue
            damping = math.exp(-particle.drag * dt)
            particle.vx *= damping
            particle.vy = particle.vy * damping + particle.gravity * dt
            particle.px, particle.py = particle.x, particle.y
            particle.x += particle.vx * dt
            particle.y += particle.vy * dt
            self._draw(particle)
            alive.append(particle)
        self.particles = alive
        for particle in spawned:
            particle.on_expire(particle)
        return bool(self.particles)

    def clear(self):
        for particle in self.particles:
            self._delete(particle)
        self.particles = []

    def _draw(self, particle):
        ui = self.ui
        remaining = 1.0 - particle.age / particle.life
        # Streak length follows speed, so fast sparks read as motion and slow ones as dots.
        tail = min(0.05, 0.016 + 0.0002 * math.hypot(particle.vx, particle.vy))
        coords = (ui._x(particle.x - particle.vx * tail), ui._y(particle.y - particle.vy * tail),
                  ui._x(particle.x), ui._y(particle.y))
        width = max(1.0, particle.size * ui.scale * (0.35 + 0.65 * remaining))
        if particle.item is None:
            particle.item = ui.canvas.create_line(*coords, width=width, fill=particle.color,
                                                  capstyle="round", tags=self.tag)
            if self.below is not None:
                ui.canvas.tag_lower(particle.item, self.below)
        else:
            ui.canvas.coords(particle.item, *coords)
            ui.canvas.itemconfigure(particle.item, width=width)
        fade_step = min(FADE_STEPS - 1, int((1.0 - remaining) ** 2 * FADE_STEPS))
        if fade_step != particle.fade_step:
            particle.fade_step = fade_step
            ui.canvas.itemconfigure(particle.item, fill=blend(particle.color, self.background, fade_step / FADE_STEPS))
        if particle.twinkle and remaining < 0.6:
            visible = random.random() < 0.55
            if visible != particle.visible:
                particle.visible = visible
                ui.canvas.itemconfigure(particle.item, state="normal" if visible else "hidden")

    def _delete(self, particle):
        if particle.item is not None:
            self.ui.canvas.delete(particle.item)
            particle.item = None


class Fireworks:
    """Rockets rise out of the bin, then burst into drag-slowed, twinkling sparks."""

    COLORS = (("#ffffff", "#ffbd2e"), ("#ff5f56", "#ffd1cc"), ("#27c7f7", "#ffffff"),
              ("#246bec", "#9fd3ff"), ("#f57c18", "#ffe08a"), ("#28c68d", "#d5ffe9"))

    def __init__(self, ui, background, below=None):
        self.ui = ui
        self.system = ParticleSystem(ui, background, "fireworks", below)
        self.pending = []

    @property
    def active(self):
        return bool(self.system.particles or self.pending)

    def launch(self, count, seed_index=0, delay_step=0.22):
        for index in range(count):
            palette = self.COLORS[(seed_index + index) % len(self.COLORS)]
            self.pending.append([index * delay_step, palette])

    def update(self, dt):
        for entry in list(self.pending):
            entry[0] -= dt
            if entry[0] <= 0:
                self.pending.remove(entry)
                self._fire(entry[1])
        return self.system.update(dt) or bool(self.pending)

    def clear(self):
        self.pending.clear()
        self.system.clear()

    def _fire(self, palette):
        start_x = random.uniform(430, 650)
        target_x = random.uniform(150, 930)
        target_y = random.uniform(240, 720)
        rise = 0.75
        gravity = 260.0
        vy = (target_y - 960 - 0.5 * gravity * rise * rise) / rise
        vx = (target_x - start_x) / rise

        def explode(rocket):
            self._explode(rocket.x, rocket.y, palette)

        rocket = self.system.emit(start_x, 960, vx, vy, rise, 12, palette[0], gravity=gravity, on_expire=explode)
        rocket.drag = 0.0
        self._trail(rocket, palette)

    def _trail(self, rocket, palette):
        # Embers shed along the rocket path; scheduled as short-lived children.
        for step in range(8):
            t = rocket.life * step / 8
            x = rocket.x + rocket.vx * t
            y = rocket.y + rocket.vy * t + 0.5 * rocket.gravity * t * t
            ember = self.system.emit(x, y, random.uniform(-20, 20), random.uniform(10, 50), 0.0,
                                     6, palette[1], gravity=120, drag=1.5)
            ember.age = -t  # stays dormant until the rocket passes this point
            ember.life = 0.35

    def _explode(self, x, y, palette):
        flash = self.system.emit(x, y, 0, 0, 0.16, 70, "#ffffff")
        flash.drag = 0
        self.system.burst(x, y, 44, 760, palette, life=(1.1, 1.7), size=(9, 13), gravity=170, drag=2.1,
                          twinkle=0.4)
        self.system.burst(x, y, 18, 330, (palette[1],), life=(0.7, 1.0), size=(6, 9), gravity=120, drag=2.6)
