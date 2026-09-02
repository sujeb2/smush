import glob
import os
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image

from game.rules import JUDGEMENT_WEIGHT
from startup_health import check_disk, check_runtime_files, clear_previous_error


PRELOAD_STAGES = (
    ("DISK CHECK", "CHECK DISK..."),
    ("FILE INTEGRITY", "CHECK APPLICATION FILES..."),
    ("GRAPHIC ASSETS", "LOAD ASSETS..."),
    ("ANIMATION CACHE", "LOAD ANIMATION CACHE..."),
    ("CHART MEDIA", "LOAD VIDOES..."),
    ("FILE CACHE", "WARMING UP CHART CACHE..."),
    ("GAMEPLAY RENDERER", "PREPARING RENDERER..."),
)
PRELOAD_MESSAGE_STAGE = {message: name for name, message in PRELOAD_STAGES}
PRELOAD_STAGE_MESSAGE = {name: message for name, message in PRELOAD_STAGES}


class MinigamePreloadMixin:
    def show_preload(self, next_action=None):
        if self.preload_complete:
            (next_action or self.show_ci)()
            return
        self.preload_next_action = next_action or self.show_ci
        self.scene = "preload"
        self._build_scene()
        if self.preload_started:
            return
        self.preload_started = True
        self.preload_started_at = time.monotonic()
        self.root.after(60, self._start_preload_worker)
        self._print("preload screen visible")

    def _build_preload_scene(self):
        self.canvas.create_rectangle(
            self._x(0), self._y(0), self._x(1080), self._y(1920),
            fill="#020403", outline="", tags=("preload",),
        )
        self._preload_text("SDM-K-A-20260823", 23, 48, 58, "#cbd2ce")
        self._preload_text("smush STARTUP", 30, 48, 108, "#58ef92")
        #self.canvas.create_rectangle(
        #    self._x(48), self._y(166), self._x(1032), self._y(168),
        #    fill="#173c29", outline="", tags=("preload",),
        #)
        self.preload_status_items = {}
        self.preload_status_photos = {}
        for index, (name, _) in enumerate(PRELOAD_STAGES):
            y = 220 + index * 64
            self._preload_text(name, 25, 48, y, "#e5e9e6")
            status, color = self._preload_status_visual(name)
            item, photo = self._preload_text(status, 25, 650, y, color)
            self.preload_status_items[name] = item
            self.preload_status_photos[name] = photo
        self.canvas.create_rectangle(
            self._x(48), self._y(1704), self._x(1032), self._y(1706),
            fill="#173c29", outline="", tags=("preload",),
        )
        elapsed = max(0, round((time.monotonic() - self.preload_started_at) * 1000)) if self.preload_started_at else 0
        self.preload_elapsed_item, self.preload_elapsed_photo = self._preload_text(
            f"ELAPSED TIME - {elapsed:05d}", 23, 48, 1735, "#e5e9e6",
        )
        footer = "INITIALIZATION FAILED" if self.preload_error else "PLEASE WAIT FOR BOOT"
        footer_color = "#ff6767" if self.preload_error else "#58ef92"
        self.preload_footer_item, self.preload_footer_photo = self._preload_text(
            footer, 23, 48, 1782, footer_color,
        )
        self._preload_text("WINDOWS 10 EMBEDDED SYSTEM BOOT SEQUENCE", 20, 48, 1829, "#87908b")
        #self.preload_cursor_item = self.canvas.create_rectangle(
        #    self._x(48), self._y(1881), self._x(61), self._y(1900),
        #    fill="#58ef92", outline="", tags=("preload",),
        #)

    def _preload_text(self, text, size, x, y, color, anchor="nw"):
        photo = self._text_photo(
            text, size, color=color, font_path=self.novecento_font_path, align="left",
        )
        self.scene_photos.append(photo)
        item = self.canvas.create_image(
            self._x(x), self._y(y), image=photo, anchor=anchor, tags=("preload",),
        )
        return item, photo

    def _preload_status_visual(self, name):
        status = self.preload_stage_states.get(name, "----")
        if status == "OK":
            return "OK", "#58ef92"
        if status == "ERROR":
            return "ERROR", "#ff6767"
        if status == "CHECKING":
            dots = "." * (self.preload_visual_tick % 4)
            return f"CHECKING{dots}", "#e5e9e6"
        if status == "SKIPPED":
            return "SKIPPED", "#87908b"
        return "----", "#68726c"

    def _animate_preload(self, now):
        if now < self.preload_next_visual_update:
            return
        self.preload_next_visual_update = now + 0.2
        self.preload_visual_tick += 1
        checking = tuple(
            name for name, status in self.preload_stage_states.items()
            if status == "CHECKING" and name in self.preload_status_items
        )
        for name in checking:
            text, color = self._preload_status_visual(name)
            photo = self._text_photo(
                text, 25, color=color, font_path=self.novecento_font_path, align="left",
            )
            self.preload_status_photos[name] = photo
            self.canvas.itemconfigure(self.preload_status_items[name], image=photo)
        if self.preload_started_at and self.preload_elapsed_item is not None:
            elapsed = max(0, round((now - self.preload_started_at) * 1000))
            self.preload_elapsed_photo = self._text_photo(
                f"ELAPSED TIME - {elapsed:05d}", 23, color="#e5e9e6",
                font_path=self.novecento_font_path, align="left",
            )
            self.canvas.itemconfigure(self.preload_elapsed_item, image=self.preload_elapsed_photo)
        if self.preload_cursor_item is not None:
            self.canvas.itemconfigure(
                self.preload_cursor_item,
                state="normal" if self.preload_visual_tick % 4 < 3 else "hidden",
            )

    def _start_preload_worker(self):
        worker = threading.Thread(target=self._run_preload, daemon=True, name="smush-minigame-preloader")
        worker.start()

    def _post_preload_stage(self, name, status):
        self.event_queue.put(("preload_stage", name, status))

    def _run_preload(self):
        try:
            self._run_preload_action("DISK CHECK", lambda: check_disk(self.base))
            if self.recovery_startup:
                self._run_preload_action("FILE INTEGRITY", lambda: check_runtime_files(self.base))
            else:
                self._post_preload_stage("FILE INTEGRITY", "SKIPPED")
            self._run_preload_action("GRAPHIC ASSETS", self._load_assets)
            actions = (
                ("ANIMATION CACHE", self._preload_entry_animation_sources),
                ("ANIMATION CACHE", self._preload_warning_animation_sources),
                ("ANIMATION CACHE", self._preload_result_animation_sources),
                ("ANIMATION CACHE", self._preload_gameplay_animation_sources),
                ("CHART MEDIA", self._preload_chart_media),
                ("FILE CACHE", self._warm_preload_audio_files),
            )
            remaining = Counter(name for name, _ in actions)
            for name in remaining:
                self._post_preload_stage(name, "CHECKING")
            workers = min(4, len(actions), max(2, os.cpu_count() or 2))
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="smush-preload") as executor:
                futures = {executor.submit(action): name for name, action in actions}
                for future in as_completed(futures):
                    name = futures[future]
                    try:
                        future.result()
                    except Exception:
                        self._post_preload_stage(name, "ERROR")
                        raise
                    remaining[name] -= 1
                    if remaining[name] == 0:
                        self._post_preload_stage(name, "OK")
            self.event_queue.put(("preload_ready",))
        except Exception as error:
            self.event_queue.put(("preload_error", str(error)))

    def _run_preload_action(self, name, action):
        self._post_preload_stage(name, "CHECKING")
        try:
            action()
        except Exception:
            self._post_preload_stage(name, "ERROR")
            raise
        self._post_preload_stage(name, "OK")

    def _preload_animation_sources(self):
        self._preload_entry_animation_sources()
        self._preload_warning_animation_sources()
        self._preload_result_animation_sources()
        self._preload_gameplay_animation_sources()

    def _preload_entry_animation_sources(self):
        self._entry_card_sources("entry")
        self._entry_card_sources("entry_guest")
        self._entry_cancel_sources()

    def _preload_warning_animation_sources(self):
        self._warning_sources()
        self._warning_select_sources()
        self._warning_mode_sources()

    def _preload_result_animation_sources(self):
        self._result_morph_sources()
        for name in ("clear", "failed"):
            self._result_wave_sources(name)
        for rank in ("x", "s", "a", "b", "c", "d"):
            self._rank_reveal_sources(f"rank_{rank}")

    def _preload_gameplay_animation_sources(self):
        self._catch_burst_sources()
        for name in JUDGEMENT_WEIGHT:
            self._judgement_animation_sources(name)
        for name in ("lane_help_2k_0", "lane_help_2k_1", "lane_help_4k_0", "lane_help_4k_1"):
            self._lane_help_animation_sources(name)
        for name in ("demonstration_able", "demonstration_coin"):
            self._demonstration_overlay_sources(name)

    def _preload_chart_media(self):
        charts = tuple({chart.path: chart for mode in self.charts_by_mode.values() for chart in mode}.values())
        for chart in charts:
            if chart.background_path and chart.background_path not in self.chart_preview_sources:
                try:
                    with Image.open(chart.background_path) as image:
                        source = image.convert("RGB")
                    self.chart_preview_sources[chart.background_path] = source
                    self.chart_game_sources[chart.background_path] = self._game_media_source(source)
                except OSError as error:
                    self._print(f"beatmap background unavailable: {error}")
            if chart.video_path and chart.video_path not in self.chart_video_first_frames:
                self._preload_chart_video(chart.video_path)

    def _preload_chart_video(self, path):
        try:
            import cv2

            video = cv2.VideoCapture(path)
            if not video.isOpened():
                video.release()
                return
            fps = video.get(cv2.CAP_PROP_FPS)
            success, frame = video.read()
            video.release()
            if not success:
                return
            source = Image.fromarray(frame[:, :, ::-1])
            self.chart_preview_sources[path] = source
            self.chart_video_first_frames[path] = self._game_media_source(source)
            self.chart_video_fps[path] = fps if fps and fps > 0 else 30.0
        except Exception as error:
            self._print(f"beatmap video unavailable: {error}")

    def _warm_preload_files(self):
        chart_files = {
            path
            for mode in self.charts_by_mode.values()
            for chart in mode
            for path in (chart.audio_path, chart.video_path, chart.background_path)
            if path
        }
        bundled_files = set(glob.glob(os.path.join(self.bgm_root, "**", "*"), recursive=True))
        bundled_files.update(glob.glob(os.path.join(self.sfx_root, "*")))
        for path in chart_files | bundled_files:
            if not os.path.isfile(path):
                continue
            try:
                with open(path, "rb") as file:
                    file.read(262144)
            except OSError as error:
                self._print(f"preload file unavailable: {error}")

    def _warm_preload_audio_files(self):
        self._warm_preload_files()
        preload_paths = glob.glob(os.path.join(self.sfx_root, "*.wav"))
        preload_paths.extend(glob.glob(os.path.join(self.sfx_root, "*.mp3")))
        preload_paths.extend(glob.glob(os.path.join(self.voice_root, "*.mp3")))
        preload_paths.append(os.path.join(self.bgm_root, "next.mp3"))
        self.audio.preload_sfx(preload_paths)

    def _refresh_preload_stage(self, name):
        if self.scene != "preload" or name not in self.preload_status_items:
            return
        text, color = self._preload_status_visual(name)
        photo = self._text_photo(
            text, 25, color=color, font_path=self.novecento_font_path, align="left",
        )
        self.preload_status_photos[name] = photo
        self.canvas.itemconfigure(self.preload_status_items[name], image=photo)

    def _set_preload_stage(self, name, status, announce=False):
        self.preload_stage_states[name] = status
        if status == "CHECKING":
            self.preload_active_stage = name
        elif self.preload_active_stage == name:
            self.preload_active_stage = next(
                (stage for stage, value in self.preload_stage_states.items() if value == "CHECKING"), None,
            )
        self._refresh_preload_stage(name)
        if announce:
            self._print(PRELOAD_STAGE_MESSAGE.get(name, name))

    def _update_preload_status(self, message):
        if not self.preload_status_lines or self.preload_status_lines[-1] != message:
            self.preload_status_lines.append(message)
        next_stage = PRELOAD_MESSAGE_STAGE.get(message)
        if next_stage is not None:
            self._set_preload_stage(next_stage, "CHECKING")
        elif message == "Initialization complete.":
            for name, _ in PRELOAD_STAGES:
                if self.preload_stage_states.get(name) == "SKIPPED":
                    continue
                self._set_preload_stage(name, "OK")
            self.preload_active_stage = None
        self._print(message)

    def _finish_preload(self):
        if self.preload_renderer_started:
            return
        self.preload_renderer_started = True
        self._set_preload_stage("GAMEPLAY RENDERER", "CHECKING", announce=True)
        self.preloaded_judgement_frames = {name: [] for name in JUDGEMENT_WEIGHT}
        self.preloaded_catch_burst_frames = []
        self.preloaded_lane_help_frames = {
            name: [] for name in ("lane_help_2k_0", "lane_help_2k_1", "lane_help_4k_0", "lane_help_4k_1")
        }
        self.preloaded_demonstration_frames = {
            name: [] for name in ("demonstration_able", "demonstration_coin")
        }
        self.preload_render_tasks = [
            ("asset", name, source)
            for name, source in self.sources.items()
        ]
        self.preload_render_tasks.extend(
            ("judgement", name, frame)
            for name in JUDGEMENT_WEIGHT
            for frame in self._judgement_animation_sources(name)
        )
        self.preload_render_tasks.extend(
            ("catch", None, frame)
            for frame in self._catch_burst_sources()
        )
        self.preload_render_tasks.extend(
            ("lane_help", name, frame)
            for name in self.preloaded_lane_help_frames
            for frame in self._lane_help_animation_sources(name)
        )
        self.preload_render_tasks.extend(
            ("demonstration", name, frame)
            for name in self.preloaded_demonstration_frames
            for frame in self._demonstration_overlay_sources(name)
        )
        self.preload_render_index = 0
        self.root.after(1, self._finish_preload_batch)

    def _finish_preload_batch(self):
        if not self.running or self.scene != "preload":
            return
        deadline = time.perf_counter() + 0.007
        try:
            while self.preload_render_index < len(self.preload_render_tasks):
                kind, name, source = self.preload_render_tasks[self.preload_render_index]
                if kind == "asset":
                    key = name, round(self.scale, 5)
                    if key not in self.photo_cache:
                        self.photo_cache[key] = self._scaled_photo(source)
                elif kind == "judgement":
                    self.preloaded_judgement_frames[name].append(self._scaled_photo(source))
                elif kind == "catch":
                    self.preloaded_catch_burst_frames.append(self._scaled_photo(source))
                elif kind == "lane_help":
                    self.preloaded_lane_help_frames[name].append(self._scaled_photo(source))
                else:
                    self.preloaded_demonstration_frames[name].append(self._scaled_photo(source))
                self.preload_render_index += 1
                if time.perf_counter() >= deadline:
                    self.root.after(1, self._finish_preload_batch)
                    return
        except Exception as error:
            self._set_preload_stage("GAMEPLAY RENDERER", "ERROR")
            self._fail_preload(str(error))
            return
        self.preloaded_judgement_frames = {
            name: tuple(frames) for name, frames in self.preloaded_judgement_frames.items()
        }
        self.preloaded_catch_burst_frames = tuple(self.preloaded_catch_burst_frames)
        self.preloaded_lane_help_frames = {
            name: tuple(frames) for name, frames in self.preloaded_lane_help_frames.items()
        }
        self.preloaded_demonstration_frames = {
            name: tuple(frames) for name, frames in self.preloaded_demonstration_frames.items()
        }
        self.preloaded_gameplay_scale = round(self.scale, 5)
        self.preload_render_tasks = []
        self._set_preload_stage("GAMEPLAY RENDERER", "OK")
        clear_previous_error(self.base)
        self.recovery_startup = False
        self.preload_complete = True
        elapsed = time.monotonic() - self.preload_started_at
        self._update_preload_status("Initialization complete.")
        self._print(f"preload complete: {elapsed:.2f} seconds")
        action = self.preload_next_action or self.show_ci
        self.preload_next_action = None
        self.root.after(360, action)

    def _ensure_preloaded_gameplay_photos(self):
        scale = round(self.scale, 5)
        if self.preloaded_gameplay_scale == scale and self.preloaded_judgement_frames:
            return
        self.preloaded_judgement_frames = {
            name: tuple(self._scaled_photo(frame) for frame in self._judgement_animation_sources(name))
            for name in JUDGEMENT_WEIGHT
        }
        self.preloaded_catch_burst_frames = tuple(
            self._scaled_photo(frame) for frame in self._catch_burst_sources()
        )
        self.preloaded_lane_help_frames = {
            name: tuple(self._scaled_photo(frame) for frame in self._lane_help_animation_sources(name))
            for name in ("lane_help_2k_0", "lane_help_2k_1", "lane_help_4k_0", "lane_help_4k_1")
        }
        self.preloaded_demonstration_frames = {
            name: tuple(self._scaled_photo(frame) for frame in self._demonstration_overlay_sources(name))
            for name in ("demonstration_able", "demonstration_coin")
        }
        self.preloaded_gameplay_scale = scale

    def _fail_preload(self, message):
        self.preload_error = message
        if "ERROR" not in self.preload_stage_states.values() and self.preload_active_stage:
            self._set_preload_stage(self.preload_active_stage, "ERROR")
        if self.scene == "preload":
            self._build_scene()
        self._print(f"INITIALIZATION FAILED: {message}")
