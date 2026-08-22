import glob
import math
import os
import sys
import tkinter as tk

from PIL import Image, ImageDraw, ImageFont, ImageTk


DESIGN_WIDTH = 1080
DESIGN_HEIGHT = 1920


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
        self.root = tk.Tk()
        self.root.title(title)
        self.root.configure(bg="black")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
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
