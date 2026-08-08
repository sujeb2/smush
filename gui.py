import argparse
import configparser
import math
import os
import random
import sys
import time
import tkinter as tk
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageTk


DESIGN_WIDTH = 1080
DESIGN_HEIGHT = 1920


def find_compiled_dir():
    if "__compiled__" in globals():
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.dirname(os.path.abspath(__file__))


def should_celebrate(previous_count, current_count):
    return current_count % 5 == 0 or len(str(current_count)) > len(str(previous_count))


class RecyclingUI:
    def __init__(self, serial_io=None, initial_count=0, fullscreen=True, serial_message="Forwarded", count_file=None):
        self.timestamp = datetime.now().strftime("%H:%M:%S")
        print(f'[{self.timestamp}] [UI] UI init start.')
        self.base = find_compiled_dir()
        self.serial = serial_io
        self.count = initial_count
        self.serial_message = serial_message.lower()
        self.serial_buffer = ""
        self.count_file = count_file
        self.running = True
        self.animating = False
        self.pending_events = 0
        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.resize_job = None
        self.settle_job = None
        self.feedback_job = None
        self.firework_job = None
        self.drop_job = None
        self.drop_start = 0.0
        self.drop_duration = 0.9
        self.drop_frame = 0
        self.drop_sequence = 0
        self.firework_particles = []
        self.root = tk.Tk()
        self.root.title("SMUSH")
        self.root.configure(bg="black")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        if fullscreen:
            self.root.attributes("-fullscreen", True)
        else:
            self.root.geometry("540x960")
            self.root.minsize(360, 640)
        self.canvas = tk.Canvas(self.root, highlightthickness=0, bg="black")
        self.canvas.pack(fill="both", expand=True)
        self.font_path = os.path.join(self.base, "files", "fonts", "KERISKEDU_B.ttf")
        self.ground_source = Image.open(os.path.join(self.base, "files", "img", "ground_layer.png")).convert("RGBA")
        self.trash_source = Image.open(os.path.join(self.base, "files", "img", "trash_can.png")).convert("RGBA")
        self.cans_source = Image.open(os.path.join(self.base, "files", "img", "cans.png")).convert("RGBA")
        self.single_can_source = self.cans_source.crop((10, 8, 156, 184))
        self.root.bind("<Escape>", lambda event: self.close())
        self.root.bind("<space>", lambda event: self.trigger_recycle())
        self.root.bind("<Return>", lambda event: self.trigger_recycle())
        self.root.bind("f", lambda event: self.start_fireworks())
        self.canvas.bind("<Configure>", self._schedule_scene)
        self.root.after(0, self._build_scene)
        self.root.after(50, self._poll_serial)

    def run(self):
        self.root.mainloop()

    def close(self):
        if not self.running:
            return
        self.running = False
        if self.serial is not None:
            self.serial.close()
        self.root.destroy()

    def trigger_recycle(self):
        if not self.running:
            return
        if self.animating:
            self.pending_events += 1
            return
        self.animating = True
        self.drop_start = time.monotonic()
        self.drop_sequence += 1
        self.drop_frame = self.drop_sequence % len(self.drop_photos)
        self.canvas.itemconfigure(self.drop_id, image=self.drop_photos[self.drop_frame], state="normal")
        self.canvas.coords(self.drop_id, self._x(540), self._y(-140))
        self.canvas.tag_raise(self.drop_id)
        self.canvas.tag_lower(self.drop_id, self.trash_id)
        self._animate_drop()

    def _schedule_scene(self, event):
        if event.width < 2 or event.height < 2:
            return
        if self.resize_job is not None:
            self.root.after_cancel(self.resize_job)
        self.resize_job = self.root.after(120, self._build_scene)

    def _build_scene(self):
        if not self.running:
            return
        self.resize_job = None
        width = max(self.canvas.winfo_width(), 1)
        height = max(self.canvas.winfo_height(), 1)
        self.scale = min(width / DESIGN_WIDTH, height / DESIGN_HEIGHT)
        self.offset_x = (width - DESIGN_WIDTH * self.scale) / 2
        self.offset_y = (height - DESIGN_HEIGHT * self.scale) / 2
        self.canvas.delete("all")
        self.firework_particles.clear()
        self.firework_job = None
        self.canvas.create_rectangle(
            self._x(0),
            self._y(0),
            self._x(DESIGN_WIDTH),
            self._y(DESIGN_HEIGHT),
            fill="#a9e5fa",
            outline="",
            tags="background",
        )
        self.ground_photo = self._scaled_photo(self.ground_source)
        self.cans_photo = self._scaled_photo(self.cans_source)
        self.trash_photo = self._scaled_photo(self.trash_source)
        self.ground_id = self.canvas.create_image(self._x(540), self._y(1114), image=self.ground_photo, anchor="n", tags="ground")
        self.cans_id = self.canvas.create_image(self._x(540), self._y(972), image=self.cans_photo, anchor="n", tags="cans")
        self.trash_id = self.canvas.create_image(self._x(540), self._y(965), image=self.trash_photo, anchor="n", tags="trash")
        self.logo_photo = self._text_photo("SMUSH V1.0", 26)
        self.title_photo = self._text_photo("현재 재활용된 개수", 52)
        self.count_photo = self._text_photo(str(self.count), 158)
        self.feedback_photo = self._text_photo("", 42)
        self.logo_id = self.canvas.create_image(self._x(38), self._y(36), image=self.logo_photo, anchor="nw", tags="text")
        self.title_id = self.canvas.create_image(self._x(540), self._y(470), image=self.title_photo, anchor="n", tags="text")
        self.count_id = self.canvas.create_image(self._x(540), self._y(548), image=self.count_photo, anchor="n", tags="text")
        self.feedback_id = self.canvas.create_image(self._x(540), self._y(760), image=self.feedback_photo, anchor="n", tags="text")
        self.drop_photos = self._make_drop_photos()
        self.drop_id = self.canvas.create_image(self._x(540), self._y(-140), image=self.drop_photos[0], anchor="center", state="hidden", tags="drop")

    def _scaled_photo(self, source):
        width = max(1, round(source.width * self.scale))
        height = max(1, round(source.height * self.scale))
        return ImageTk.PhotoImage(source.resize((width, height), Image.Resampling.LANCZOS))

    def _make_drop_photos(self):
        photos = []
        for angle in (0, 12, 22, 12, 0, -12, -22, -12):
            rotated = self.single_can_source.rotate(angle, Image.Resampling.BICUBIC, expand=True)
            target_width = max(1, round(rotated.width * self.scale * 0.9))
            target_height = max(1, round(rotated.height * self.scale * 0.9))
            photos.append(ImageTk.PhotoImage(rotated.resize((target_width, target_height), Image.Resampling.LANCZOS)))
        return photos

    def _text_photo(self, text, size, color="white"):
        scaled_size = max(1, round(size * self.scale))
        font = ImageFont.truetype(self.font_path, scaled_size)
        if not text:
            return ImageTk.PhotoImage(Image.new("RGBA", (1, 1), (0, 0, 0, 0)))
        box = font.getbbox(text, stroke_width=max(1, round(self.scale)))
        width = max(1, box[2] - box[0] + round(12 * self.scale))
        height = max(1, box[3] - box[1] + round(12 * self.scale))
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.text(
            (width / 2, height / 2),
            text,
            font=font,
            fill=color,
            anchor="mm",
            stroke_width=max(1, round(self.scale)),
            stroke_fill=color,
        )
        return ImageTk.PhotoImage(image)

    def _animate_drop(self):
        if not self.running or not self.animating:
            return
        progress = min(1.0, (time.monotonic() - self.drop_start) / self.drop_duration)
        eased = progress * progress
        y = -140 + (916 + 140) * eased
        sway = math.sin(progress * math.pi * 3) * 42
        frame = int(progress * (len(self.drop_photos) - 1))
        self.canvas.itemconfigure(self.drop_id, image=self.drop_photos[frame])
        self.canvas.coords(self.drop_id, self._x(540 + sway), self._y(y))
        if progress < 1.0:
            self.drop_job = self.root.after(16, self._animate_drop)
            return
        self.canvas.itemconfigure(self.drop_id, state="hidden")
        self._finish_recycle()

    def _finish_recycle(self):
        previous_count = self.count
        self.count += 1
        self._save_count()
        self.count_photo = self._text_photo(str(self.count), 158)
        self.canvas.itemconfigure(self.count_id, image=self.count_photo)
        self._show_feedback("캔 1개가 재활용됐어요")
        self._lift_cans()
        if should_celebrate(previous_count, self.count):
            self.start_fireworks()
        self.root.after(420, self._complete_animation)

    def _complete_animation(self):
        self.animating = False
        if self.pending_events > 0:
            self.pending_events -= 1
            self.trigger_recycle()

    def _show_feedback(self, message):
        if self.feedback_job is not None:
            self.root.after_cancel(self.feedback_job)
        self.feedback_photo = self._text_photo(message, 42)
        self.canvas.itemconfigure(self.feedback_id, image=self.feedback_photo)
        self.feedback_job = self.root.after(2200, self._clear_feedback)

    def _clear_feedback(self):
        self.feedback_job = None
        self.feedback_photo = self._text_photo("", 42)
        self.canvas.itemconfigure(self.feedback_id, image=self.feedback_photo)

    def _lift_cans(self):
        if self.settle_job is not None:
            self.root.after_cancel(self.settle_job)
        self._animate_cans(972, 880, time.monotonic(), 0.28, False)
        self.settle_job = self.root.after(1800, lambda: self._animate_cans(880, 972, time.monotonic(), 0.48, True))

    def _animate_cans(self, start_y, end_y, started, duration, settling):
        if not self.running:
            return
        progress = min(1.0, (time.monotonic() - started) / duration)
        eased = 1 - pow(1 - progress, 3) if not settling else progress * progress
        y = start_y + (end_y - start_y) * eased
        self.canvas.coords(self.cans_id, self._x(540), self._y(y))
        if progress < 1.0:
            self.root.after(16, lambda: self._animate_cans(start_y, end_y, started, duration, settling))
        elif settling:
            self.settle_job = None

    def start_fireworks(self):
        colors = ("#ffffff", "#ff5f56", "#ffbd2e", "#27c7f7", "#246bec", "#f57c18")
        for burst_index in range(5):
            center_x = random.randint(130, 950)
            center_y = random.randint(230, 1050)
            color = colors[(self.count + burst_index) % len(colors)]
            for particle_index in range(14):
                angle = math.tau * particle_index / 14 + random.uniform(-0.08, 0.08)
                speed = random.uniform(5.0, 9.0) * self.scale
                item = self.canvas.create_oval(0, 0, 0, 0, fill=color, outline="", tags="fireworks")
                self.canvas.tag_lower(item, self.ground_id)
                self.firework_particles.append(
                    {
                        "item": item,
                        "x": self._x(center_x),
                        "y": self._y(center_y),
                        "vx": math.cos(angle) * speed,
                        "vy": math.sin(angle) * speed,
                        "life": random.randint(30, 45),
                    }
                )
        if self.firework_job is None:
            self._animate_fireworks()

    def _animate_fireworks(self):
        alive = []
        radius = max(2, 6 * self.scale)
        for particle in self.firework_particles:
            particle["x"] += particle["vx"]
            particle["y"] += particle["vy"]
            particle["vy"] += 0.18 * self.scale
            particle["vx"] *= 0.985
            particle["life"] -= 1
            if particle["life"] <= 0:
                self.canvas.delete(particle["item"])
                continue
            fade = particle["life"] / 45
            particle_radius = max(1, radius * fade)
            self.canvas.coords(
                particle["item"],
                particle["x"] - particle_radius,
                particle["y"] - particle_radius,
                particle["x"] + particle_radius,
                particle["y"] + particle_radius,
            )
            alive.append(particle)
        self.firework_particles = alive
        if alive and self.running:
            self.firework_job = self.root.after(33, self._animate_fireworks)
        else:
            self.firework_job = None

    def _poll_serial(self):
        if not self.running:
            return
        if self.serial is not None:
            try:
                while self.serial.in_waiting > 0:
                    message = self.serial.read()
                    if message is None:
                        continue
                    self.serial_buffer += message.lower()
                    while self.serial_message in self.serial_buffer:
                        position = self.serial_buffer.index(self.serial_message)
                        self.serial_buffer = self.serial_buffer[position + len(self.serial_message):]
                        self.trigger_recycle()
                    self.serial_buffer = self.serial_buffer[-256:]
            except Exception as error:
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"[{timestamp}] [UI] serial read failed: {error}")
        self.root.after(50, self._poll_serial)

    def _save_count(self):
        if self.count_file is None:
            return
        temp_file = f"{self.count_file}.tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as file:
                file.write(str(self.count))
            os.replace(temp_file, self.count_file)
        except OSError as error:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] [UI] count save failed: {error}")

    def _x(self, value):
        return self.offset_x + value * self.scale

    def _y(self, value):
        return self.offset_y + value * self.scale


def _load_config():
    config = configparser.ConfigParser()
    config.read(os.path.join(find_compiled_dir(), "files", "main_conf.ini"), encoding="utf-8")
    return config


def _load_saved_count(path, fallback):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return int(file.read().strip())
    except (OSError, ValueError):
        return fallback


def run_demo():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument("--count", type=int)
    parser.add_argument("--port")
    args = parser.parse_args()
    config = _load_config()
    ui_config = config["UI"]
    initial_count = args.count if args.count is not None else ui_config.getint("InitialCount", fallback=0)
    count_file = os.path.join(find_compiled_dir(), ui_config.get("CountFile", fallback="files/recycle_count.txt"))
    serial_io = None
    if not args.demo:
        from serial_arduino import SerialIO

        port = args.port or config["SERIAL"]["SerialPort"]
        serial_io = SerialIO(port, config["SERIAL"]["SerialBaudrate"], config["SERIAL"].getint("SerialTimeout"))
        initial_count = _load_saved_count(count_file, initial_count)
    app = RecyclingUI(
        serial_io=serial_io,
        initial_count=initial_count,
        fullscreen=not args.windowed,
        serial_message=ui_config.get("SerialMessage", fallback="Forwarded"),
        count_file=None if args.demo else count_file,
    )
    app.run()


if __name__ == "__main__":
    run_demo()
