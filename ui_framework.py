import glob
import math
import os
import sys
import textwrap
import traceback
import tkinter as tk

from PIL import Image, ImageDraw, ImageFont, ImageTk


DESIGN_WIDTH = 1080
DESIGN_HEIGHT = 1920
UNRECOVERABLE_IMAGE_WIDTH = 900


def load_svg_image(path):
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame

    surface = pygame.image.load(path)
    return Image.frombytes("RGBA", surface.get_size(), pygame.image.tobytes(surface, "RGBA"))


def enlarge_unrecoverable_image(source, target_width=UNRECOVERABLE_IMAGE_WIDTH):
    scale = target_width / source.width
    target_height = max(1, round(source.height * scale))
    return source.resize((target_width, target_height), Image.Resampling.LANCZOS)


def format_console_log(code, detail, width=72, max_lines=8):
    lines = ["CONSOLE LOG", f"[{str(code).strip() or 'UNRECOVERABLE_ERROR'}]"]
    detail_lines = []
    for line in str(detail).strip().splitlines() or ("No additional details were provided.",):
        detail_lines.extend(textwrap.wrap(line, width=width) or ("",))
    available = max(1, max_lines - len(lines))
    if len(detail_lines) > available:
        detail_lines = ["...", *detail_lines[-(available - 1):]] if available > 1 else ["..."]
    return "\n".join((*lines, *detail_lines))


def persist_unrecoverable_error(base, code, detail):
    try:
        from startup_health import mark_unrecoverable_error

        mark_unrecoverable_error(base, code, detail)
    except Exception as error:
        print(f"[startup health] cannot save unrecoverable-error marker: {error}", file=sys.stderr)


def find_compiled_dir():
    if "__compiled__" in globals() or getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


class CanvasUIFramework:
    def __init__(self, title, fullscreen=True, windowed_geometry="540x960"):
        self.base = find_compiled_dir()
        self.running = True
        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.resize_job = None
        self.serial = None
        self.unrecoverable_error = False
        self.unrecoverable_code = ""
        self.unrecoverable_detail = ""
        self.root = tk.Tk()
        self.root.title(title)
        self.root.configure(bg="black")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.report_callback_exception = self._report_callback_exception
        if fullscreen:
            self.root.attributes("-fullscreen", True)
        else:
            self.root.geometry(windowed_geometry)
            self.root.minsize(360, 640)
        self.canvas = tk.Canvas(self.root, highlightthickness=0, bg="black")
        self.canvas.pack(fill="both", expand=True)
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
        self.root.bind("<Escape>", lambda event: self.close())
        self.canvas.bind("<Configure>", self._schedule_scene)

    def run(self):
        self.root.mainloop()

    def close(self):
        if not self.running:
            return
        self.running = False
        if self.serial is not None:
            self.serial.close()
        self.root.destroy()

    def attach_serial(self, serial_io):
        self.serial = serial_io

    def _schedule_scene(self, event):
        if event.width < 2 or event.height < 2:
            return
        if self.unrecoverable_error:
            self._draw_unrecoverable_error()
            return
        if self.resize_job is not None:
            self.root.after_cancel(self.resize_job)
        self.resize_job = self.root.after(120, self._build_scene)

    def _prepare_scene(self):
        self.resize_job = None
        width = max(self.canvas.winfo_width(), 1)
        height = max(self.canvas.winfo_height(), 1)
        self.scale = min(width / DESIGN_WIDTH, height / DESIGN_HEIGHT)
        self.offset_x = (width - DESIGN_WIDTH * self.scale) / 2
        self.offset_y = (height - DESIGN_HEIGHT * self.scale) / 2
        self.canvas.delete("all")

    def _report_callback_exception(self, exception_type, exception, exception_traceback):
        detail = "".join(traceback.format_exception(exception_type, exception, exception_traceback))
        print(detail, file=sys.stderr, end="")
        self.show_unrecoverable_error(exception_type.__name__.upper(), detail)

    def show_unrecoverable_error(self, code, detail):
        if not self.running:
            return
        self.unrecoverable_error = True
        self.unrecoverable_code = str(code)
        self.unrecoverable_detail = str(detail)
        persist_unrecoverable_error(self.base, code, detail)
        try:
            for job in self.root.tk.call("after", "info"):
                self.root.after_cancel(job)
        except tk.TclError:
            pass
        self.resize_job = None
        print(f"ERROR HAS OCCURRED!!\nCode: {code}\nDetail: {detail}")
        self._draw_unrecoverable_error()

    def _draw_unrecoverable_error(self):
        self._prepare_scene()
        self.canvas.create_rectangle(
            self._x(0), self._y(0), self._x(DESIGN_WIDTH), self._y(DESIGN_HEIGHT),
            fill="black", outline="", tags="unrecoverable_error",
        )
        source = enlarge_unrecoverable_image(
            load_svg_image(os.path.join(self.base, "files", "img", "unrecoverable_system_error.svg")),
        )
        self.unrecoverable_error_photo = self._scaled_photo(source)
        self.unrecoverable_console_photo = self._text_photo(
            format_console_log(self.unrecoverable_code, self.unrecoverable_detail),
            25,
            font_path=self.novecento_font_path,
            align="left",
        )
        self.canvas.create_image(
            self._x(DESIGN_WIDTH / 2), self._y(DESIGN_HEIGHT / 2),
            image=self.unrecoverable_error_photo, anchor="center", tags="unrecoverable_error",
        )
        self.canvas.create_image(
            self._x(72), self._y(1510), image=self.unrecoverable_console_photo,
            anchor="nw", tags="unrecoverable_error",
        )
        self.canvas.tag_raise("unrecoverable_error")

    def _find_font(self, patterns, extra_directories=()):
        directories = (os.path.join(self.base, "files", "fonts"), *extra_directories)
        for directory in directories:
            for pattern in patterns:
                matches = sorted(glob.glob(os.path.join(directory, pattern)))
                if matches:
                    return matches[0]
        return self.font_path

    def _scaled_photo(self, source):
        width = max(1, round(source.width * self.scale))
        height = max(1, round(source.height * self.scale))
        return ImageTk.PhotoImage(source.resize((width, height), Image.Resampling.LANCZOS))

    def _text_photo(self, text, size, color="white", font_path=None, align="center"):
        scaled_size = max(1, round(size * self.scale))
        font = ImageFont.truetype(font_path or self.font_path, scaled_size)
        if not text:
            return ImageTk.PhotoImage(Image.new("RGBA", (1, 1), (0, 0, 0, 0)))
        probe = ImageDraw.Draw(Image.new("RGBA", (1, 1), (0, 0, 0, 0)))
        spacing = max(4, round(16 * self.scale))
        box = probe.multiline_textbbox((0, 0), text, font=font, spacing=spacing, align=align)
        padding = max(4, math.ceil(8 * self.scale))
        width = max(1, math.ceil(box[2] - box[0]) + padding * 2)
        height = max(1, math.ceil(box[3] - box[1]) + padding * 2)
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.multiline_text(
            (padding - box[0], padding - box[1]),
            text,
            font=font,
            fill=color,
            spacing=spacing,
            align=align,
        )
        return ImageTk.PhotoImage(image)

    def _x(self, value):
        return self.offset_x + value * self.scale

    def _y(self, value):
        return self.offset_y + value * self.scale


class UnrecoverableErrorUI(CanvasUIFramework):
    def __init__(self, code, detail, fullscreen=True):
        super().__init__("SMUSH ERROR", fullscreen=fullscreen)
        self.root.after(0, lambda: self.show_unrecoverable_error(code, detail))
