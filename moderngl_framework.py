import glob
import heapq
import math
import os
import sys
import time
import traceback
import weakref
from array import array
from dataclasses import dataclass, field
from types import SimpleNamespace

from PIL import Image, ImageColor, ImageDraw, ImageFont

from ui_framework import (
    DESIGN_HEIGHT,
    DESIGN_WIDTH,
    enlarge_unrecoverable_image,
    find_compiled_dir,
    format_console_log,
    load_svg_image,
    persist_unrecoverable_error,
)


_VERTEX_SHADER = """
#version 330
in vec2 in_position;
in vec2 in_uv;
uniform vec4 rect;
uniform vec2 viewport;
uniform float layout_scale;
uniform vec2 layout_offset;
out vec2 uv;
void main() {
    vec2 design_pixel = rect.xy + in_position * rect.zw;
    vec2 pixel = layout_offset + design_pixel * layout_scale;
    vec2 ndc = vec2(pixel.x / viewport.x * 2.0 - 1.0, 1.0 - pixel.y / viewport.y * 2.0);
    gl_Position = vec4(ndc, 0.0, 1.0);
    uv = in_uv;
}
"""

_FRAGMENT_SHADER = """
#version 330
uniform sampler2D image_texture;
uniform vec4 tint;
in vec2 uv;
out vec4 fragment_color;
void main() {
    fragment_color = texture(image_texture, uv) * tint;
}
"""


def _tags(value):
    if not value:
        return set()
    if isinstance(value, str):
        return {value}
    return set(value)


def _rgba(value):
    if not value:
        return (0.0, 0.0, 0.0, 0.0)
    rgb = ImageColor.getrgb(value)
    if len(rgb) == 3:
        rgb = (*rgb, 255)
    return tuple(channel / 255.0 for channel in rgb)


class FrameRateCounter:
    def __init__(self, refresh_seconds=0.5):
        self.refresh_seconds = refresh_seconds
        self.last_frame_at = None
        self.window_started_at = None
        self.total_started_at = None
        self.window_frames = 0
        self.total_frames = 0
        self.current = 0.0
        self.minimum = None
        self.maximum = 0.0
        self.average = 0.0

    def update(self, now=None):
        now = time.perf_counter() if now is None else now
        if self.last_frame_at is None:
            self.last_frame_at = now
            self.window_started_at = now
            self.total_started_at = now
            return False
        if now <= self.last_frame_at:
            return False
        self.last_frame_at = now
        self.window_frames += 1
        self.total_frames += 1
        total_elapsed = now - self.total_started_at
        self.average = self.total_frames / total_elapsed
        window_elapsed = now - self.window_started_at
        if window_elapsed < self.refresh_seconds:
            return False
        self.current = self.window_frames / window_elapsed
        self.minimum = self.current if self.minimum is None else min(self.minimum, self.current)
        self.maximum = max(self.maximum, self.current)
        self.window_frames = 0
        self.window_started_at = now
        return True

    def text(self):
        if self.minimum is None:
            return "FPS --.-   MIN --.-   MAX --.-   AVG --.-"
        return (
            f"FPS {self.current:.1f}   MIN {self.minimum:.1f}   "
            f"MAX {self.maximum:.1f}   AVG {self.average:.1f}"
        )


@dataclass
class _CanvasItem:
    kind: str
    coords: list
    tags: set = field(default_factory=set)
    image: object = None
    anchor: str = "center"
    fill: str = ""
    outline: str = ""
    width: float = 1.0
    state: str = "normal"


class ModernGLCanvas:
    def __init__(self, context, width, height, moderngl_module):
        self.context = context
        self.moderngl = moderngl_module
        self.width = max(1, width)
        self.height = max(1, height)
        self.layout_scale = 1.0
        self.layout_offset_x = 0.0
        self.layout_offset_y = 0.0
        self.items = {}
        self.order = []
        self.next_item = 1
        self.textures = {}
        self.render_count = 0
        self.fps_overlay = None
        self.program = context.program(vertex_shader=_VERTEX_SHADER, fragment_shader=_FRAGMENT_SHADER)
        vertices = array("f", (
            0, 0, 0, 0,  1, 0, 1, 0,  1, 1, 1, 1,
            0, 0, 0, 0,  1, 1, 1, 1,  0, 1, 0, 1,
        ))
        self.buffer = context.buffer(vertices.tobytes())
        self.vertex_array = context.vertex_array(
            self.program, [(self.buffer, "2f 2f", "in_position", "in_uv")],
        )
        self.white_image = Image.new("RGBA", (1, 1), "white")
        self._update_layout()

    def pack(self, **_kwargs):
        return None

    def bind(self, *_args, **_kwargs):
        return None

    def winfo_width(self):
        return self.width

    def winfo_height(self):
        return self.height

    def resize(self, width, height):
        self.width = max(1, width)
        self.height = max(1, height)
        self._update_layout()

    def _update_layout(self):
        self.layout_scale = min(self.width / DESIGN_WIDTH, self.height / DESIGN_HEIGHT)
        self.layout_offset_x = (self.width - DESIGN_WIDTH * self.layout_scale) / 2
        self.layout_offset_y = (self.height - DESIGN_HEIGHT * self.layout_scale) / 2

    def _create(self, item):
        item_id = self.next_item
        self.next_item += 1
        self.items[item_id] = item
        self.order.append(item_id)
        return item_id

    def create_image(self, x, y, image=None, anchor="center", tags=()):
        return self._create(_CanvasItem("image", [x, y], _tags(tags), image=image, anchor=anchor))

    def create_rectangle(self, x1, y1, x2, y2, fill="", outline="", width=1, tags=()):
        return self._create(_CanvasItem(
            "rectangle", [x1, y1, x2, y2], _tags(tags), fill=fill, outline=outline, width=width,
        ))

    def _matching(self, target):
        if target == "all":
            return list(self.order)
        if isinstance(target, int):
            return [target] if target in self.items else []
        return [item_id for item_id in self.order if target in self.items[item_id].tags]

    def delete(self, target):
        for item_id in self._matching(target):
            self.items.pop(item_id, None)
            if item_id in self.order:
                self.order.remove(item_id)

    def coords(self, target, *coords):
        matches = self._matching(target)
        if not coords:
            return tuple(self.items[matches[0]].coords) if matches else ()
        for item_id in matches:
            self.items[item_id].coords = list(coords)

    def move(self, target, dx, dy):
        for item_id in self._matching(target):
            values = self.items[item_id].coords
            for index in range(0, len(values), 2):
                values[index] += dx
                values[index + 1] += dy

    def itemconfigure(self, target, **options):
        for item_id in self._matching(target):
            item = self.items[item_id]
            for name, value in options.items():
                if hasattr(item, name):
                    setattr(item, name, value)

    itemconfig = itemconfigure

    def tag_raise(self, target):
        matches = self._matching(target)
        if not matches:
            return
        match_set = set(matches)
        self.order = [item_id for item_id in self.order if item_id not in match_set] + matches

    def addtag_withtag(self, new_tag, target):
        for item_id in self._matching(target):
            self.items[item_id].tags.add(new_tag)

    def dtag(self, target, tag):
        for item_id in self._matching(target):
            self.items[item_id].tags.discard(tag)

    def update_video_frame(self, item_id, source, pixels):
        item = self.items.get(item_id)
        if item is None:
            return
        previous = item.image
        cached = self.textures.get(id(previous))
        if cached is not None and cached[0]() is previous and previous.size == source.size:
            cached[1].write(pixels)
            self.textures.pop(id(previous))
            self.textures[id(source)] = (weakref.ref(source), cached[1], self.render_count)
        item.image = source

    def _texture(self, source):
        key = id(source)
        cached = self.textures.get(key)
        if cached is not None and cached[0]() is source:
            self.textures[key] = (cached[0], cached[1], self.render_count)
            return cached[1]
        if cached is not None:
            cached[1].release()
        image = source.convert("RGBA") if source.mode != "RGBA" else source
        texture = self.context.texture(image.size, 4, image.tobytes())
        texture.filter = (self.moderngl.LINEAR, self.moderngl.LINEAR)
        texture.repeat_x = False
        texture.repeat_y = False
        self.textures[key] = (weakref.ref(source), texture, self.render_count)
        return texture

    def _draw_quad(self, x, y, width, height, source, tint):
        if width <= 0 or height <= 0 or tint[3] <= 0:
            return
        self.program["rect"].value = (float(x), float(y), float(width), float(height))
        self.program["viewport"].value = (float(self.width), float(self.height))
        self.program["layout_scale"].value = float(self.layout_scale)
        self.program["layout_offset"].value = (
            float(self.layout_offset_x), float(self.layout_offset_y),
        )
        self.program["tint"].value = tint
        self._texture(source).use(0)
        self.vertex_array.render(self.moderngl.TRIANGLES)

    @staticmethod
    def _image_origin(x, y, width, height, anchor):
        anchor = (anchor or "center").lower()
        if anchor in ("center", "n", "s"):
            x -= width / 2
        elif anchor in ("e", "ne", "se"):
            x -= width
        if anchor in ("center", "e", "w"):
            y -= height / 2
        elif anchor in ("s", "se", "sw"):
            y -= height
        return x, y

    def _render_item(self, item):
        if item.state == "hidden":
            return
        if item.kind == "image":
            if not isinstance(item.image, Image.Image):
                return
            x, y = self._image_origin(
                item.coords[0], item.coords[1], item.image.width, item.image.height, item.anchor,
            )
            self._draw_quad(x, y, item.image.width, item.image.height, item.image, (1, 1, 1, 1))
            return
        x1, y1, x2, y2 = item.coords
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        width = right - left
        height = bottom - top
        if item.fill:
            self._draw_quad(left, top, width, height, self.white_image, _rgba(item.fill))
        if item.outline and item.width > 0:
            line = min(float(item.width), width / 2, height / 2)
            color = _rgba(item.outline)
            self._draw_quad(left, top, width, line, self.white_image, color)
            self._draw_quad(left, bottom - line, width, line, self.white_image, color)
            self._draw_quad(left, top + line, line, max(0, height - 2 * line), self.white_image, color)
            self._draw_quad(right - line, top + line, line, max(0, height - 2 * line), self.white_image, color)

    def update_fps_overlay(self, text, font_path):
        font = ImageFont.truetype(font_path, 16)
        probe = ImageDraw.Draw(Image.new("RGBA", (1, 1), (0, 0, 0, 0)))
        box = probe.textbbox((0, 0), text, font=font)
        width = box[2] - box[0] + 20
        height = box[3] - box[1] + 12
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=7, fill=(28, 20, 42, 178))
        draw.text((10 - box[0], 6 - box[1]), text, font=font, fill="white")
        self.fps_overlay = image

    def render(self):
        self.render_count += 1
        self.context.viewport = (0, 0, self.width, self.height)
        self.context.clear(0.0, 0.0, 0.0, 1.0)
        for item_id in tuple(self.order):
            item = self.items.get(item_id)
            if item is not None:
                self._render_item(item)
        if self.fps_overlay is not None:
            self._draw_quad(
                63, 70, self.fps_overlay.width, self.fps_overlay.height,
                self.fps_overlay, (1, 1, 1, 1),
            )
        if self.render_count % 120 == 0:
            for key, (source_ref, texture, last_used) in tuple(self.textures.items()):
                if source_ref() is None and self.render_count - last_used >= 120:
                    texture.release()
                    self.textures.pop(key, None)

    def release(self):
        for _, texture, _ in self.textures.values():
            texture.release()
        self.textures.clear()
        self.vertex_array.release()
        self.buffer.release()
        self.program.release()


class PygameRoot:
    def __init__(self, framework, pygame_module):
        self.framework = framework
        self.pygame = pygame_module
        self.bindings = {}
        self.jobs = []
        self.cancelled = set()
        self.next_job = 1

    def bind(self, sequence, callback):
        self.bindings[sequence] = callback

    def after(self, milliseconds, callback):
        job = self.next_job
        self.next_job += 1
        heapq.heappush(self.jobs, (time.monotonic() + milliseconds / 1000.0, job, callback))
        return job

    def after_cancel(self, job):
        self.cancelled.add(job)

    def cancel_all_jobs(self):
        self.jobs.clear()
        self.cancelled.clear()

    def destroy(self):
        self.framework.running = False

    def title(self, value):
        self.pygame.display.set_caption(value)

    def configure(self, **_kwargs):
        return None

    def protocol(self, *_args):
        return None

    def attributes(self, *_args):
        return None

    def geometry(self, *_args):
        return None

    def minsize(self, *_args):
        return None

    @staticmethod
    def _keysym(pygame_module, event):
        aliases = {
            pygame_module.K_LEFT: "Left",
            pygame_module.K_RIGHT: "Right",
            pygame_module.K_UP: "Up",
            pygame_module.K_DOWN: "Down",
            pygame_module.K_RETURN: "Return",
            pygame_module.K_KP_ENTER: "KP_Enter",
            pygame_module.K_SPACE: "space",
            pygame_module.K_ESCAPE: "Escape",
            pygame_module.K_MINUS: "minus",
            pygame_module.K_KP_MINUS: "KP_Subtract",
        }
        return aliases.get(event.key, event.unicode or pygame_module.key.name(event.key))

    def _run_jobs(self):
        now = time.monotonic()
        while self.jobs and self.jobs[0][0] <= now:
            _, job, callback = heapq.heappop(self.jobs)
            if job in self.cancelled:
                self.cancelled.discard(job)
                continue
            callback()
            if not self.framework.running:
                break

    def mainloop(self):
        clock = self.pygame.time.Clock()
        fps_counter = self.framework.fps_counter
        try:
            while self.framework.running:
                try:
                    for event in self.pygame.event.get():
                        if event.type == self.pygame.QUIT:
                            self.framework.close()
                        elif event.type == self.pygame.KEYDOWN:
                            keysym = self._keysym(self.pygame, event)
                            if keysym == "Escape":
                                callback = self.bindings.get("<Escape>")
                                if callback is not None:
                                    callback(SimpleNamespace(keysym=keysym))
                                continue
                            callback = self.bindings.get("<KeyPress>")
                            if callback is not None:
                                callback(SimpleNamespace(keysym=keysym))
                    self._run_jobs()
                    if not self.framework.running:
                        break
                    self.framework.canvas.render()
                    self.pygame.display.flip()
                    if fps_counter.update() and not self.framework.unrecoverable_error:
                        self.framework.canvas.update_fps_overlay(
                            fps_counter.text(), self.framework.novecento_demibold_font_path,
                        )
                    clock.tick(60)
                except Exception as error:
                    detail = traceback.format_exc()
                    print(detail, file=sys.stderr, end="")
                    self.framework.show_unrecoverable_error(type(error).__name__.upper(), detail)
        finally:
            self.framework._shutdown_display()


class ModernGLUIFramework:
    """GPU renderer used by the minigame; the service/test UIs remain Tkinter."""

    def __init__(self, title, fullscreen=True, windowed_geometry="540x960"):
        try:
            import moderngl
            import pygame
        except ImportError as error:
            raise RuntimeError("The minigame renderer requires pygame and moderngl.") from error
        self.base = find_compiled_dir()
        self.running = True
        self.scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.resize_job = None
        self.serial = None
        self.unrecoverable_error = False
        self.unrecoverable_code = ""
        self.unrecoverable_detail = ""
        self.pygame = pygame
        self.moderngl = moderngl
        self.fps_counter = FrameRateCounter()
        if os.name == "nt":
            try:
                import ctypes

                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except (AttributeError, OSError):
                pass
        pygame.display.init()
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
        pygame.display.gl_set_attribute(pygame.GL_DOUBLEBUFFER, 1)
        flags = pygame.OPENGL | pygame.DOUBLEBUF
        if fullscreen:
            flags |= pygame.FULLSCREEN
            size = (0, 0)
        else:
            width, height = (int(value) for value in windowed_geometry.split("x", 1))
            size = (width, height)
        surface = pygame.display.set_mode(size, flags, vsync=1)
        context = moderngl.create_context(require=330)
        surface_width, surface_height = surface.get_size()
        framebuffer_width, framebuffer_height = context.screen.size
        width = framebuffer_width or surface_width
        height = framebuffer_height or surface_height
        context.enable(moderngl.BLEND)
        context.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self.canvas = ModernGLCanvas(context, width, height, moderngl)
        self.root = PygameRoot(self, pygame)
        self.root.title(title)
        self.root.bind("<Escape>", lambda _event: self.close())
        self.font_path = os.path.join(self.base, "files", "fonts", "KERISKEDU_B.ttf")
        font_directories = (os.path.join(os.path.expanduser("~"), "Library", "Fonts"),)
        self.novecento_font_path = self._find_font(
            ("Novecentosanswide-Normal.otf", "NovecentoSansWide-Normal.otf", "*Novecento*Normal*"),
            font_directories,
        )
        self.novecento_demibold_font_path = self._find_font(
            ("Novecentosanswide-DemiBold.otf", "NovecentoSansWide-DemiBold.otf", "*Novecento*DemiBold*"),
            font_directories,
        )
        self.display_font_path = self._find_font(
            ("*A2Z*", "*에이투지체-4Regular.ttf", "*에이투지체-4Regular.ttf"),
            font_directories,
        )
        self.canvas.update_fps_overlay(self.fps_counter.text(), self.novecento_demibold_font_path)
        self._prepare_scene()

    def run(self):
        self.root.mainloop()

    def close(self):
        if not self.running:
            return
        self.running = False
        if self.serial is not None:
            self.serial.close()

    def _shutdown_display(self):
        if self.canvas is not None:
            self.canvas.release()
        self.pygame.display.quit()

    def attach_serial(self, serial_io):
        self.serial = serial_io

    def show_unrecoverable_error(self, code, detail):
        """Stop all scene callbacks and leave only the fatal-error UI active."""
        if not self.running:
            return
        self.unrecoverable_error = True
        self.unrecoverable_code = str(code)
        self.unrecoverable_detail = str(detail)
        persist_unrecoverable_error(self.base, code, detail)
        self.root.cancel_all_jobs()
        self.canvas.fps_overlay = None
        self._draw_unrecoverable_error()

    def _draw_unrecoverable_error(self):
        self._prepare_scene()
        self.canvas.create_rectangle(
            self._x(0), self._y(0), self._x(DESIGN_WIDTH), self._y(DESIGN_HEIGHT),
            fill="black", outline="", tags=("unrecoverable_error",),
        )
        source = enlarge_unrecoverable_image(
            load_svg_image(os.path.join(self.base, "files", "img", "unrecoverable_system_error.svg")),
        )
        console = self._text_photo(
            format_console_log(self.unrecoverable_code, self.unrecoverable_detail),
            25,
            font_path=self.novecento_font_path,
            align="left",
        )
        self.canvas.create_image(
            self._x(DESIGN_WIDTH / 2), self._y(DESIGN_HEIGHT / 2),
            image=source, anchor="center", tags=("unrecoverable_error",),
        )
        self.canvas.create_image(
            self._x(72), self._y(1510), image=console,
            anchor="nw", tags=("unrecoverable_error",),
        )

    def _prepare_scene(self):
        self.resize_job = None
        # Scene code, source images, generated text, and animation deltas all
        # share the original 1080x1920 design coordinate system.  The canvas
        # applies the only output scale in the vertex shader so high-DPI
        # framebuffers cannot scale positions and assets differently.
        self.scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.canvas.delete("all")

    def _find_font(self, patterns, extra_directories=()):
        directories = (os.path.join(self.base, "files", "fonts"), *extra_directories)
        for directory in directories:
            for pattern in patterns:
                matches = sorted(glob.glob(os.path.join(directory, pattern)))
                if matches:
                    return matches[0]
        return self.font_path

    def _scaled_photo(self, source):
        return source

    def _text_photo(self, text, size, color="white", font_path=None, align="center"):
        scaled_size = max(1, round(size * self.scale))
        font = ImageFont.truetype(font_path or self.font_path, scaled_size)
        if not text:
            return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        probe = ImageDraw.Draw(Image.new("RGBA", (1, 1), (0, 0, 0, 0)))
        spacing = max(4, round(16 * self.scale))
        box = probe.multiline_textbbox((0, 0), text, font=font, spacing=spacing, align=align)
        padding = max(4, math.ceil(8 * self.scale))
        width = max(1, math.ceil(box[2] - box[0]) + padding * 2)
        height = max(1, math.ceil(box[3] - box[1]) + padding * 2)
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.multiline_text(
            (padding - box[0], padding - box[1]), text, font=font, fill=color,
            spacing=spacing, align=align,
        )
        return image

    def _x(self, value):
        return self.offset_x + value * self.scale

    def _y(self, value):
        return self.offset_y + value * self.scale
