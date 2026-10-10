import argparse
import configparser
import math
import os
import queue
import re
import threading
import time
from collections import deque
from datetime import datetime

from PIL import Image, ImageTk

from particles import Fireworks
from status_card import DEFAULT_DURATIONS, PHASES, MachineCycle, StatusCard
from dependency_updater import DependencyUpdateError, load_requirements, requirement_name, update_dependencies
from ui_framework import CanvasUIFramework, DESIGN_HEIGHT, DESIGN_WIDTH, find_compiled_dir


PHASE_MESSAGE = re.compile(r"phase:([a-z]+):(\d+)")
PHASE_PARTIAL = re.compile(r"phase:[a-z]*(:\d*)?")


def should_celebrate(previous_count, current_count):
    return current_count % 5 == 0 or len(str(current_count)) > len(str(previous_count))


class RecyclingUI(CanvasUIFramework):
    def __init__(self, serial_io=None, initial_count=0, fullscreen=True, serial_message="Forwarded", count_file=None, test_mode_callback=None):
        self.timestamp = datetime.now().strftime("%H:%M:%S")
        print(f'[{self.timestamp}] [UI] UI init start.')
        super().__init__("SMUSH", fullscreen=fullscreen)
        self.serial = serial_io
        self.count = initial_count
        if isinstance(serial_message, str):
            serial_message = serial_message.split(",")
        self.serial_messages = tuple(message.strip().lower() for message in serial_message if message.strip())
        self.serial_materials = {
            message: "plastic_bottle" if message.endswith("_2") else "can"
            for message in self.serial_messages
        }
        self.serial_buffer = ""
        self.serial_buffer_updated_at = 0.0
        self.test_mode_callback = test_mode_callback
        self.entering_test_mode = False
        self.count_file = count_file
        self.screen_state = "update"
        self.update_progress = 0
        self.update_status = "CHECKING DEPENDENCIES"
        self.startup_text = "startup..."
        self.error_code = ""
        self.error_detail = ""
        self.event_queue = queue.Queue()
        self.animating = False
        self.pending_events = deque()
        self.current_drop_type = "can"
        self.settle_job = None
        self.feedback_job = None
        self.firework_job = None
        self.drop_job = None
        self.drop_start = 0.0
        self.drop_duration = 0.9
        self.drop_frame = 0
        self.drop_sequence = 0
        self.fireworks = None
        self.firework_frame_at = 0.0
        self.crushing_busy = False
        self.trash_full = False
        self.card_font_path = os.path.join(self.base, "files", "fonts", "Cafe24Ssurround-v2.0.otf")
        self.cycle = MachineCycle()
        self.status_card = StatusCard(self, self.cycle, self.card_font_path)
        self.ground_source = Image.open(os.path.join(self.base, "files", "img", "ground_layer.png")).convert("RGBA")
        self.trash_source = Image.open(os.path.join(self.base, "files", "img", "trash_can.png")).convert("RGBA")
        self.cans_source = Image.open(os.path.join(self.base, "files", "img", "cans.png")).convert("RGBA")
        self.update_source = Image.open(os.path.join(self.base, "files", "img", "update_layer.png")).convert("RGBA")
        self.drop_sources = {
            "can": Image.open(os.path.join(self.base, "files", "img", "can.png")).convert("RGBA"),
            "plastic_bottle": Image.open(os.path.join(self.base, "files", "img", "plastic_bottle.png")).convert("RGBA"),
        }
        self.root.bind("<space>", lambda event: self.trigger_recycle("can"))
        self.root.bind("<Return>", lambda event: self.trigger_recycle("plastic_bottle"))
        self.root.bind("<KeyPress-minus>", lambda event: self._request_test_mode())
        self.root.bind("f", lambda event: self.start_fireworks())
        self.root.bind("c", lambda event: self._simulate_cycle())
        self.root.bind("t", lambda event: self._handle_machine_status("trash_full"))
        self.root.after(0, self._build_scene)
        self.root.after(50, self._poll_serial)
        self.root.after(50, self._poll_events)

    def post_startup(self, message):
        self.event_queue.put(("startup", message))

    def post_update(self, progress, status):
        self.event_queue.put(("update", progress, status))

    def post_serial(self, serial_io):
        self.event_queue.put(("serial", serial_io))

    def post_ready(self):
        self.event_queue.put(("ready",))

    def post_error(self, code, detail):
        self.event_queue.put(("error", code, detail))

    def _request_test_mode(self):
        if self.entering_test_mode:
            return
        self.entering_test_mode = True
        if self.test_mode_callback is not None:
            self.test_mode_callback()

    def show_startup(self, message):
        if self.screen_state == "error":
            return
        self.screen_state = "startup"
        self.startup_text = message
        self._build_scene()

    def show_update(self, progress, status):
        if self.screen_state == "error":
            return
        self.screen_state = "update"
        self.update_progress = max(0, min(100, round(progress)))
        self.update_status = status
        self._build_scene()

    def show_ready(self):
        if self.screen_state == "error":
            return
        self.screen_state = "ready"
        self._build_scene()

    def show_error(self, code, detail):
        if self.unrecoverable_error:
            return
        self.screen_state = "error"
        self.error_code = code
        self.error_detail = detail
        self.animating = False
        self.pending_events.clear()
        self.show_unrecoverable_error(code, detail)

    def trigger_recycle(self, material="can"):
        if not self.running or self.screen_state != "ready":
            return
        if material not in self.drop_sources:
            material = "can"
        if self.animating:
            self.pending_events.append(material)
            return
        self.animating = True
        self.current_drop_type = material
        self.drop_start = time.monotonic()
        self.drop_sequence += 1
        drop_photos = self.drop_photos[self.current_drop_type]
        self.drop_frame = self.drop_sequence % len(drop_photos)
        self.canvas.itemconfigure(self.drop_id, image=drop_photos[self.drop_frame], state="normal")
        self.canvas.coords(self.drop_id, self._x(540), self._y(-140))
        self.canvas.tag_raise(self.drop_id)
        self.canvas.tag_lower(self.drop_id, self.trash_id)
        self._animate_drop()

    def _build_scene(self):
        if not self.running:
            return
        self._prepare_scene()
        self.status_card.destroy()
        if self.firework_job is not None:
            self.root.after_cancel(self.firework_job)
        self.firework_job = None
        self.fireworks = None
        if self.screen_state == "update":
            self._build_update_scene()
            return
        if self.screen_state == "startup":
            self._build_startup_scene()
            return
        if self.screen_state == "error":
            self._build_error_scene()
            return
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
        self.title_photo = self._text_photo("현재 재활용된 개수", 52)
        self.count_photo = self._text_photo(str(self.count), 158)
        self.feedback_photo = self._text_photo("", 42)
        self.title_id = self.canvas.create_image(self._x(540), self._y(470), image=self.title_photo, anchor="n", tags="text")
        self.count_id = self.canvas.create_image(self._x(540), self._y(548), image=self.count_photo, anchor="n", tags="text")
        self.feedback_id = self.canvas.create_image(self._x(540), self._y(760), image=self.feedback_photo, anchor="n", tags="text")
        self.drop_photos = {
            material: self._make_drop_photos(source)
            for material, source in self.drop_sources.items()
        }
        self.drop_id = self.canvas.create_image(self._x(540), self._y(-140), image=self.drop_photos["can"][0], anchor="center", state="hidden", tags="drop")
        self.fireworks = Fireworks(self, "#a9e5fa", below=self.ground_id)
        self.status_card.build()
        self._sync_status_card()

    def _handle_machine_status(self, command):
        if command == "trash_full":
            self.trash_full = True
        else:
            self.cycle.legacy(command)
        self.crushing_busy = self.cycle.phase in ("crush", "reset")
        self._sync_status_card()

    def _handle_phase(self, name, remaining_ms):
        self.cycle.report(name, remaining_ms / 1000)
        self.crushing_busy = self.cycle.phase in ("crush", "reset")
        self._sync_status_card()

    def _sync_status_card(self):
        # A full bin warning persists across crushing transitions.
        desired = "trash_full" if self.trash_full else self.cycle.phase
        if desired in PHASES and self.animating and not self.status_card.visible:
            desired = None  # let the drop animation finish before covering the scene
        self.status_card.set_kind(desired)

    def _simulate_cycle(self, speed=3.0):
        delay = 0.0
        for name in (*PHASES, "idle"):
            duration = DEFAULT_DURATIONS.get(name, 0.0) / speed
            self.root.after(round(delay * 1000), lambda name=name, ms=round(duration * 1000): self._handle_phase(name, ms))
            delay += duration

    def _build_startup_scene(self):
        self.canvas.create_rectangle(
            self._x(0),
            self._y(0),
            self._x(DESIGN_WIDTH),
            self._y(DESIGN_HEIGHT),
            fill="#080808",
            outline="",
            tags="startup",
        )
        self.startup_logo_photo = self._text_photo("smush v1.0", 42, font_path=self.novecento_font_path, align="left")
        self.startup_lines_photo = self._text_photo(self.startup_text, 31, font_path=self.novecento_font_path, align="left")
        self.canvas.create_image(self._x(48), self._y(58), image=self.startup_logo_photo, anchor="nw", tags="startup")
        self.canvas.create_image(self._x(48), self._y(155), image=self.startup_lines_photo, anchor="nw", tags="startup")

    def _build_update_scene(self):
        self.update_photo = self._scaled_photo(self.update_source)
        self.canvas.create_image(self._x(540), self._y(0), image=self.update_photo, anchor="n", tags="update")
        fill_width = 304 * self.update_progress / 100
        self.canvas.create_rectangle(
            self._x(370),
            self._y(1148),
            self._x(370 + fill_width),
            self._y(1182),
            fill="#28C68D",
            outline="",
            tags="update",
        )
        self.update_status_photo = self._text_photo(self.update_status, 42, font_path=self.novecento_demibold_font_path)
        self.update_count_photo = self._text_photo(f"{self.update_progress}/100", 25, font_path=self.novecento_font_path)
        self.update_percent_photo = self._text_photo(f"{self.update_progress}%", 25, font_path=self.novecento_font_path)
        self.canvas.create_image(self._x(540), self._y(960), image=self.update_status_photo, anchor="center", tags="update")
        self.canvas.create_image(self._x(446), self._y(1200), image=self.update_count_photo, anchor="n", tags="update")
        self.canvas.create_image(self._x(598), self._y(1200), image=self.update_percent_photo, anchor="n", tags="update")

    def _build_error_scene(self):
        self._draw_unrecoverable_error()

    def _make_drop_photos(self, source):
        photos = []
        for angle in (0, 12, 22, 12, 0, -12, -22, -12):
            rotated = source.rotate(angle, Image.Resampling.BICUBIC, expand=True)
            target_width = max(1, round(rotated.width * self.scale))
            target_height = max(1, round(rotated.height * self.scale))
            photos.append(ImageTk.PhotoImage(rotated.resize((target_width, target_height), Image.Resampling.LANCZOS)))
        return photos

    def _animate_drop(self):
        if not self.running or not self.animating:
            return
        progress = min(1.0, (time.monotonic() - self.drop_start) / self.drop_duration)
        eased = progress * progress
        y = -140 + (916 + 140) * eased
        sway = math.sin(progress * math.pi * 3) * 42
        drop_photos = self.drop_photos[self.current_drop_type]
        frame = int(progress * (len(drop_photos) - 1))
        self.canvas.itemconfigure(self.drop_id, image=drop_photos[frame])
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
        feedback = "페트병 1개가 재활용됐어요" if self.current_drop_type == "plastic_bottle" else "캔 1개가 재활용됐어요"
        self._show_feedback(feedback)
        self._lift_cans()
        if should_celebrate(previous_count, self.count):
            self.start_fireworks()
        self._complete_animation()

    def _complete_animation(self):
        self.animating = False
        self._sync_status_card()
        if self.pending_events:
            self.trigger_recycle(self.pending_events.popleft())

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
        if self.fireworks is None:
            return
        self.fireworks.launch(5, seed_index=self.count)
        if self.firework_job is None:
            self.firework_frame_at = time.monotonic()
            self._animate_fireworks()

    def _animate_fireworks(self):
        self.firework_job = None
        if not self.running or self.fireworks is None:
            return
        now = time.monotonic()
        dt = min(0.05, now - self.firework_frame_at)
        self.firework_frame_at = now
        if self.fireworks.update(dt):
            self.firework_job = self.root.after(16, self._animate_fireworks)

    def _poll_events(self):
        if not self.running:
            return
        try:
            while True:
                event = self.event_queue.get_nowait()
                if event[0] == "update":
                    self.show_update(event[1], event[2])
                elif event[0] == "startup":
                    self.show_startup(event[1])
                elif event[0] == "serial":
                    self.attach_serial(event[1])
                elif event[0] == "ready":
                    self.show_ready()
                elif event[0] == "error":
                    self.show_error(event[1].upper(), event[2].upper())
        except queue.Empty:
            pass
        if self.unrecoverable_error:
            return
        self.root.after(50, self._poll_events)

    def _consume_serial_messages(self, message):
        self.serial_buffer += message.lower()
        self.serial_buffer_updated_at = time.monotonic()
        if any(command in self.serial_buffer for command in ("test_up", "test_down", "test_back")):
            self.serial_buffer = ""
            self._request_test_mode()
            return
        self._drain_serial_buffer()

    def _drain_serial_buffer(self, force=False):
        commands = (*self.serial_messages, "crushing_busy", "crushing_idle", "crushing_done", "trash_full", "phase:")
        while True:
            matches = []
            for serial_message in commands:
                position = self.serial_buffer.find(serial_message)
                if position >= 0:
                    matches.append((position, serial_message))
            if not matches:
                break
            position, serial_message = min(matches, key=lambda match: (match[0], -len(match[1])))
            if serial_message == "phase:":
                # phase:<name>:<remaining ms> carries a number, so it needs its own parsing.
                match = PHASE_MESSAGE.match(self.serial_buffer, position)
                complete = match is not None and (force or match.end() < len(self.serial_buffer))
                if not complete:
                    if not force and PHASE_PARTIAL.fullmatch(self.serial_buffer, position):
                        break
                    self.serial_buffer = self.serial_buffer[position + len(serial_message):]
                    continue
                self.serial_buffer = self.serial_buffer[match.end():]
                self._handle_phase(match.group(1), int(match.group(2)))
                continue
            message_end = position + len(serial_message)
            longer_message_possible = any(
                candidate.startswith(serial_message) and len(candidate) > len(serial_message)
                for candidate in commands
            )
            if not force and message_end == len(self.serial_buffer) and longer_message_possible:
                break
            self.serial_buffer = self.serial_buffer[position + len(serial_message):]
            if serial_message in ("crushing_busy", "crushing_idle", "crushing_done", "trash_full"):
                self._handle_machine_status(serial_message)
            else:
                self.trigger_recycle(self.serial_materials[serial_message])
                self._handle_machine_status("dropped")
        self.serial_buffer = self.serial_buffer[-256:]

    def _poll_serial(self):
        if not self.running:
            return
        if self.serial is not None:
            try:
                while self.serial.in_waiting > 0:
                    message = self.serial.read()
                    if message is None:
                        continue
                    self._consume_serial_messages(message)
                if self.serial_buffer and time.monotonic() - self.serial_buffer_updated_at >= 0.05:
                    self._drain_serial_buffer(force=True)
            except Exception as error:
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"[{timestamp}] [UI] serial read failed: {error}")
                failed_serial = self.serial
                self.serial = None
                try:
                    failed_serial.close()
                except Exception:
                    pass
                self.show_error("ARDUINO_CONNECTION_LOST", "CANNOT COMMUNICATE WITH ARDUINO.\nCHECK USB CABLE AND RESTART THE PROGRAM.")
        if not self.unrecoverable_error:
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
    parser.add_argument("--simulate-error", choices=("dependency", "arduino", "webcam", "runtime"))
    parser.add_argument("--skip-update", action="store_true")
    args = parser.parse_args()
    config = _load_config()
    ui_config = config["UI"]
    initial_count = args.count if args.count is not None else ui_config.getint("InitialCount", fallback=0)
    count_file = os.path.join(find_compiled_dir(), ui_config.get("CountFile", fallback="files/recycle_count.txt"))
    if not args.demo:
        initial_count = _load_saved_count(count_file, initial_count)
    app = RecyclingUI(
        initial_count=initial_count,
        fullscreen=not args.windowed,
        serial_message=ui_config.get("SerialMessage", fallback="Forwarded"),
        count_file=None if args.demo else count_file,
    )

    def initialize():
        try:
            update_config = config["UPDATE"]
            if args.skip_update or not update_config.getboolean("Enabled", fallback=True):
                app.post_update(100, "UPDATE SKIPPED")
                time.sleep(0.4)
            elif args.demo:
                requirements = load_requirements(os.path.join(find_compiled_dir(), "requirements.txt"))
                total = max(1, len(requirements))
                app.post_update(0, "CHECKING DEPENDENCIES")
                for index, requirement in enumerate(requirements):
                    if args.simulate_error == "dependency" and index == max(1, total // 2):
                        raise DependencyUpdateError(f"{requirement_name(requirement)} update failed")
                    app.post_update(round(index / total * 100), f"UPDATING {requirement_name(requirement).upper()}")
                    time.sleep(0.1)
                    app.post_update(round((index + 1) / total * 100), f"{requirement_name(requirement).upper()} UPDATED")
                app.post_update(100, "UPDATE COMPLETE")
                time.sleep(0.4)
            else:
                update_dependencies(
                    os.path.join(find_compiled_dir(), "requirements.txt"),
                    app.post_update,
                    timeout=update_config.getint("Timeout", fallback=900),
                )
                time.sleep(0.4)
        except Exception as error:
            app.post_error(
                "DEPENDENCY_UPDATE_FAILED",
                f"CANNOT UPDATE REQUIRED DEPENDENCIES.\nCHECK NETWORK CONNECTION AND PYTHON PERMISSIONS.\n{error}",
            )
            return
        app.post_startup("Initializing SMUSH interface...")
        time.sleep(1.2)
        if args.simulate_error == "arduino":
            app.post_error("ARDUINO_CONNECTION_LOST", f"CANNOT COMMUNICATE WITH ARDUINO.\nCHECK USB CABLE AND RESTART THE PROGRAM.")
            return
        if args.simulate_error == "webcam":
            app.post_error("WEBCAM_NOT_FOUND", f"CANNOT FIND COMPATIBLE WEBCAM.\nCHECK CONNECTION AND RESTART THE PROGRAM.")
            return
        if args.simulate_error == "runtime":
            app.post_error("RUNTIME_FAILURE", f"UNEXPECTED ERROR HAS OCCURRED.\nCHECK ALL OF THE COMPONENTS CONNECTION\nCHECK INSTRUCTIONS FOR MORE INFORMATION.\nMORE INFORMATION IS PROVIDED IN THE CONSOLE, PLEASE RESTART THE MACHINE.")
            return
        if not args.demo:
            from serial_arduino import SerialIO

            port = args.port or config["SERIAL"]["SerialPort"]
            try:
                serial_io = SerialIO(port, config["SERIAL"]["SerialBaudrate"], config["SERIAL"].getint("SerialTimeout"))
            except Exception as error:
                app.post_error("ARDUINO_NOT_FOUND", f"CANNOT OPEN PORT IN {port}.\nIS THE PORT IS USED BY ANOTHER PROCESS?\n{error}")
                return
            app.post_serial(serial_io)
        app.post_ready()

    app.root.after(100, lambda: threading.Thread(target=initialize, daemon=True, name="smush-ui-initializer").start())
    app.run()


if __name__ == "__main__":
    run_demo()
