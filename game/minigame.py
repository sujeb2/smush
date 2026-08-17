import configparser
import json
import math
import os
import queue
import time
from datetime import datetime

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageTk

from game.osu_chart import discover_osu_mania_2k
from ui_framework import CanvasUIFramework, DESIGN_HEIGHT, DESIGN_WIDTH, find_compiled_dir


MAX_SCORE = 9000
EVENT_TRACK_COUNT = 3
TEXT_SCALE = 1.18
PERFECT_WINDOW = 0.09
GOOD_WINDOW = 0.18
BAD_WINDOW = 0.30
HIT_WINDOW = 0.34
HOLD_TICK_INTERVAL = 0.25
JUDGEMENT_WEIGHT = {
    "perfect": 1.0,
    "good": 0.65,
    "bad": 0.25,
    "miss": 0.0,
}
HEALTH_CHANGE = {
    "perfect": 0.45,
    "good": 0.15,
    "bad": -3.0,
    "miss": -7.0,
}


def calculate_score(judgements, note_count):
    if note_count <= 0:
        return 0
    weighted = sum(JUDGEMENT_WEIGHT.get(judgement, 0.0) for judgement in judgements)
    return min(MAX_SCORE, max(0, round(MAX_SCORE * weighted / note_count)))


def is_clear(health):
    return health > 0 and health >= 5.0


def combo_after_judgement(combo, judgement):
    return 0 if judgement == "miss" else combo + 1


def hold_tick_times(note_time, end_time, interval=HOLD_TICK_INTERVAL):
    if end_time is None or end_time <= note_time or interval <= 0:
        return ()
    ticks = []
    tick = note_time + interval
    while tick <= end_time + 0.000001:
        ticks.append(round(tick, 6))
        tick += interval
    return tuple(ticks)


def group_charts_by_song(charts):
    grouped = {}
    order = []
    for chart in charts:
        key = chart.artist.casefold(), chart.title.casefold()
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(chart)
    return tuple(
        tuple(sorted(grouped[key], key=lambda chart: (chart.level, chart.difficulty.casefold(), chart.path.casefold())))
        for key in order
    )


def event_result_destination(track_index, cleared):
    if cleared and track_index < EVENT_TRACK_COUNT - 1:
        return "select", track_index + 1
    if cleared:
        return "total_result", 0
    return "ending", 0


def load_progress(path, track_count):
    if track_count <= 0:
        return 0
    try:
        with open(path, "r", encoding="utf-8") as file:
            value = int(json.load(file).get("track_index", 0))
        return value if 0 <= value < track_count else 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 0


def load_event_results(path, track_count):
    scores = [0] * max(0, track_count)
    names = [""] * max(0, track_count)
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        stored_scores = data.get("track_scores", [])
        stored_names = data.get("track_names", [])
        for index in range(min(track_count, len(stored_scores))):
            scores[index] = min(MAX_SCORE, max(0, int(stored_scores[index])))
        for index in range(min(track_count, len(stored_names))):
            names[index] = str(stored_names[index])
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return scores, names


def save_progress(path, track_index, track_count, track_scores=None, track_names=None):
    if track_count <= 0:
        return
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    try:
        with open(path, "r", encoding="utf-8") as file:
            payload = json.load(file)
        if not isinstance(payload, dict):
            payload = {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        payload = {}
    payload["track_index"] = track_index % track_count
    if track_scores is not None:
        payload["track_scores"] = [min(MAX_SCORE, max(0, int(value))) for value in track_scores[:track_count]]
    if track_names is not None:
        payload["track_names"] = [str(value) for value in track_names[:track_count]]
    temporary_path = f"{path}.tmp"
    with open(temporary_path, "w", encoding="utf-8") as file:
        json.dump(payload, file)
    os.replace(temporary_path, path)


class AudioPlayer:
    def __init__(self):
        self.available = False
        self.current_path = None
        self.sfx_cache = {}
        try:
            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            import pygame

            pygame.mixer.pre_init(44100, -16, 2, 512)
            pygame.mixer.init()
            self.pygame = pygame
            self.available = True
            self._print("audio ready")
        except Exception as error:
            self.pygame = None
            self._print(f"audio unavailable: {error}")

    def _print(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [minigame] {message}")

    def play(self, path, loop=False, fade_ms=0):
        self.stop()
        if not self.available or not os.path.isfile(path):
            if not os.path.isfile(path):
                self._print(f"audio file missing: {path}")
            return
        try:
            self.pygame.mixer.music.load(path)
            self.pygame.mixer.music.play(-1 if loop else 0, fade_ms=max(0, fade_ms))
            self.current_path = path
            self._print(f"[AudioManager] playing audio: {os.path.basename(path)}")
        except Exception as error:
            self._print(f"[AudioManager] audio playback failed: {error}")

    def stop(self, fade_ms=0):
        if not self.available:
            return
        try:
            if fade_ms > 0:
                self.pygame.mixer.music.fadeout(fade_ms)
            else:
                self.pygame.mixer.music.stop()
        except Exception:
            pass
        self.current_path = None

    def play_sfx(self, path):
        if not self.available or not os.path.isfile(path):
            if not os.path.isfile(path):
                self._print(f"sfx file missing: {path}")
            return
        try:
            if path not in self.sfx_cache:
                self.sfx_cache[path] = self.pygame.mixer.Sound(path)
            self.sfx_cache[path].play()
            self._print(f"[AudioManager] playing sfx: {os.path.basename(path)}")
        except Exception as error:
            self._print(f"[AudioManager] sfx playback failed: {error}")

    def is_playing(self):
        if not self.available:
            return False
        try:
            return bool(self.pygame.mixer.music.get_busy())
        except Exception:
            return False

    def close(self):
        if not self.available:
            return
        try:
            self.pygame.mixer.music.stop()
            self.pygame.mixer.quit()
        except Exception:
            pass


class MinigameUI(CanvasUIFramework):
    def __init__(self, config_path, fullscreen=True, progress_path=None):
        self.settings = self._load_settings(config_path)
        super().__init__("SMUSH MINIGAME", fullscreen=fullscreen)
        charts_root = os.path.join(self.base, self.settings["charts_root"])
        self.charts, rejected = discover_osu_mania_2k(charts_root, self.settings["event_chart_folders"])
        for path, reason in rejected:
            self._print(f"[ChartManager] chart skipped: {os.path.basename(path)} ({reason})")
        if not self.charts:
            self.root.destroy()
            raise RuntimeError(f"[ChartManager] No valid osu!mania 2K chart was found in {charts_root}")
        self.song_groups = group_charts_by_song(self.charts)
        self.progress_path = progress_path or os.path.join(self.base, self.settings["progress_file"])
        self.track_index = load_progress(self.progress_path, EVENT_TRACK_COUNT)
        self.track_scores, self.track_names = load_event_results(self.progress_path, EVENT_TRACK_COUNT)
        self.song_index = 0
        self.difficulty_index = 0
        self.selection_phase = "song"
        self.track = self.song_groups[0][0]
        self.scene = "title"
        self.scene_started = time.monotonic()
        self.animation_epoch = self.scene_started
        self.select_deadline = 0.0
        self.entry_deadline = 0.0
        self.entry_choice_deadline = 0.0
        self.warning_deadline = 0.0
        self.result_deadline = 0.0
        self.total_result_deadline = 0.0
        self.result_unlock_at = 0.0
        self.result_transition_target = None
        self.next_audio_deadline = 0.0
        self.next_audio_started = False
        self.ending_audio_deadline = 0.0
        self.ending_audio_started = False
        self.total_result_time_item = None
        self.total_result_time_shown = None
        self.total_result_value_item = None
        self.total_result_value_shown = None
        self.total_result_card_items = []
        self.total_result_cards_revealed = 0
        self.timer_sfx_value = None
        self.loading_phase = None
        self.loading_target = None
        self.loading_action = None
        self.loading_started = 0.0
        self.fade_started = None
        self.title_fade_started = None
        self.entry_title_fade_started = None
        self.result_fade_started = None
        self.ending_fade_in_started = None
        self.event_queue = queue.Queue()
        self.serial_buffer = ""
        self.serial_buffer_updated_at = 0.0
        self.scene_photos = []
        self.photo_cache = {}
        self.text_cache = {}
        self.scroll_items = []
        self.particle_item = None
        self.particle_base_y = 0
        self.score_item = None
        self.health_fill_item = None
        self.judgement_item = None
        self.result_time_item = None
        self.select_time_item = None
        self.select_time_shown = None
        self.entry_time_item = None
        self.entry_time_shown = None
        self.result_time_shown = None
        self.fade_item = None
        self.fade_photo_cache = {}
        self.game_started = None
        self.game_audio_job = None
        self.resolved_notes = set()
        self.judgements = []
        self.counts = {key: 0 for key in JUDGEMENT_WEIGHT}
        self.health = 100.0
        self.display_health = 100.0
        self.score = 0
        self.combo = 0
        self.max_combo = 0
        self.active_holds = {}
        self.combo_label_item = None
        self.combo_item = None
        self.combo_frame_shown = -1
        self.combo_photo_cache = {}
        self.combo_animation_started = None
        self.combo_frame_shown = -1
        self.health_animation_started = None
        self.health_animation_from = 100.0
        self.health_pulse_started = None
        self.health_change_direction = 0
        self.health_dynamic_photo = None
        self.health_visible_state = None
        self.feedback_until = 0.0
        self.feedback_started = 0.0
        self.feedback_frame_shown = -1
        self.last_feedback = ""
        self.feedback_visible = False
        self.judgement_source_frames = {}
        self.judgement_frames = {}
        self.game_finishing = False
        self.note_items = {}
        self.next_morph_items = []
        self.title_morph_logo_item = None
        self.title_morph_top_logo_item = None
        self.title_morph_press_item = None
        self.title_morph_logo_frames = ()
        self.title_morph_top_logo_frames = ()
        self.title_morph_press_frames = ()
        self.title_select_offset = 0.0
        self.title_entry_morph_started = None
        self.title_entry_logo_item = None
        self.title_entry_logo_frames = ()
        self.title_entry_logo_frame_shown = -1
        self.select_fade_in_started = None
        self.selection_scroll_started = None
        self.selection_old_offset = 0.0
        self.selection_new_offset = 0.0
        self.selection_old_x = 0.0
        self.selection_new_x = 0.0
        self.selection_scroll_swapped = False
        self.selection_heading_item = None
        self.selection_sweep_item = None
        self.select_morph_in_started = None
        self.select_morph_in_offset = 0.0
        self.down_button_item = None
        self.down_button_base_y = 1820.0
        self.entry_card_item = None
        self.entry_card_frames = ()
        self.entry_card_frame_shown = -1
        self.entry_card_source_frames = {}
        self.entry_cancel_source_frames = ()
        self.entry_choice = None
        self.entry_choice_started = 0.0
        self.warning_item = None
        self.warning_frames = ()
        self.warning_frame_shown = -1
        self.warning_source_frames = ()
        self.warning_select_source_frames = ()
        self.next_arrow_items = []
        self.next_arrow_frames = ()
        self.result_card_offset = 0.0
        self.result_banner_item = None
        self.result_banner_frames = ()
        self.result_banner_frame_shown = -1
        self.result_wave_source_frames = {}
        self.result_value_items = {}
        self.result_values_shown = {}
        self.judgement_frames = {}
        self.result_final_counts = {key: 0 for key in JUDGEMENT_WEIGHT}
        self.result_select_morph_started = None
        self.result_select_card_offset = 0.0
        self.result_morph_item = None
        self.result_morph_frames = ()
        self.result_morph_frame_shown = -1
        self.result_morph_source_frames = ()
        self.transition_phase = None
        self.transition_started = 0.0
        self.curtain_items = ()
        self.audio = AudioPlayer()
        self._load_assets()
        self.root.bind("<KeyPress>", self._handle_key)
        self.root.after(0, self.show_title)
        self.root.after(16, self._animate)
        self.root.after(25, self._poll_serial)

    def _load_settings(self, path):
        parser = configparser.ConfigParser()
        parser.read(path, encoding="utf-8")
        section = parser["MINIGAME"] if parser.has_section("MINIGAME") else {}
        folders = tuple(item.strip() for item in section.get("EventChartFolders", "").split(",") if item.strip())
        return {
            "mode": section.get("Mode", "EVENT").upper(),
            "progress_file": section.get("ProgressFile", "game/minigame_progress.json"),
            "charts_root": section.get("ChartsRoot", "game/charts"),
            "event_chart_folders": folders,
            "button_1": section.get("Button1Message", "Forwarded").lower(),
            "button_2": section.get("Button2Message", "Forwarded_2").lower(),
            "select_seconds": max(1, int(section.get("SelectSeconds", 60))),
            "result_seconds": max(1, int(section.get("ResultSeconds", 20))),
        }

    def _load_assets(self):
        image_root = os.path.join(self.base, "game", "imgs")
        paths = {
            "particle": ("generic", "bg_particle.png"),
            "top": ("generic", "generic_top_bg.png"),
            "logo": ("generic", "logo.png"),
            "title_logo": ("generic", "title_logo.png"),
            "network": ("generic", "network.png"),
            "scroll": ("generic", "scroll_bg_part.png"),
            "entry": ("generic", "entry.png"),
            "entry_cancel": ("generic", "entry_cancel.png"),
            "entry_guest": ("generic", "entry_guest.png"),
            "warning": ("generic", "warn.png"),
            "select_bg": ("music_select", "select_music_bg.png"),
            "select_icon": ("music_select", "select_icon.png"),
            "down_button": ("music_select", "down_bt.png"),
            "previous": ("music_select", "prev_music.png"),
            "next_arrow": ("music_select", "next_arrow.png"),
            "main_layer": ("game", "main_layer.png"),
            "note_0": ("game", "note1.png"),
            "note_1": ("game", "note2.png"),
            "line": ("game", "panjung.png"),
            "health": ("game", "health.png"),
            "health_bg": ("game", "health_bg.png"),
            "perfect": ("game", "perfect.png"),
            "good": ("game", "good.png"),
            "bad": ("game", "bad.png"),
            "miss": ("game", "miss.png"),
            "result_bg": ("result", "result_info_bg.png"),
            "result_down_button": ("result", "down_bt.png"),
            "total_result_layout": ("result", "total_result_layout.png"),
            "clear": ("result", "result_clear_text.png"),
            "failed": ("result", "result_failed_text.png"),
        }
        self.sources = {
            name: Image.open(os.path.join(image_root, *parts)).convert("RGBA")
            for name, parts in paths.items()
        }
        gradient = Image.new("RGBA", (1, 2))
        gradient.putpixel((0, 0), (115, 82, 166, 255))
        gradient.putpixel((0, 1), (198, 158, 244, 255))
        self.sources["top_gradient"] = gradient.resize((DESIGN_WIDTH, 520), Image.Resampling.BILINEAR)
        self.sources["next_arrow_left"] = self.sources["next_arrow"].transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        sweep = Image.new("RGBA", (150, self.sources["select_bg"].height), (255, 255, 255, 0))
        sweep_pixels = sweep.load()
        for x in range(sweep.width):
            distance = abs(x - sweep.width / 2) / (sweep.width / 2)
            alpha = round(105 * max(0.0, 1.0 - distance) ** 2)
            for y in range(sweep.height):
                sweep_pixels[x, y] = (248, 226, 255, alpha)
        self.sources["select_sweep"] = sweep
        self.bgm_root = os.path.join(self.base, "game", "bgm")
        self.sfx_root = os.path.join(self.bgm_root, "sfx")
        self.select_bgm = "entry.mp3"
        if not os.path.isfile(os.path.join(self.bgm_root, self.select_bgm)):
            self.select_bgm = os.path.join("finale", "music_select.mp3")

    def _print(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [minigame] {message}")

    def post_serial(self, serial_io):
        self.event_queue.put(("serial", serial_io))

    def post_status(self, status):
        self.event_queue.put(("status", status))

    def close(self):
        self.audio.close()
        super().close()

    def _handle_key(self, event):
        if event.keysym in ("Left", "a", "A", "space"):
            self.press_button(0)
        elif event.keysym in ("Right", "d", "D", "Return", "KP_Enter"):
            self.press_button(1)

    def press_button(self, lane):
        if (
            not self.running
            or self.transition_phase is not None
            or self.loading_phase is not None
            or self.entry_title_fade_started is not None
            or self.title_entry_morph_started is not None
        ):
            return
        if self.scene == "title":
            self._play_sfx("start.wav")
            self._play_sfx("ok.wav")
            self._start_title_entry_morph()
        elif self.scene == "entry":
            if self.entry_choice is not None:
                return
            if lane == 0:
                self._show_entry_choice("guest")
            else:
                self._show_entry_choice("cancel")
        elif self.scene == "select":
            if (
                self.select_fade_in_started is not None
                or self.select_morph_in_started is not None
                or self.selection_scroll_started is not None
            ):
                return
            if lane == 0:
                self._cycle_selection()
            elif self.selection_phase == "song":
                self._confirm_song()
            else:
                self._play_sfx("ok.wav")
                self.show_next()
        elif self.scene == "game":
            self._judge(lane)
        elif self.scene == "result":
            self.start_result_transition()
        elif self.scene == "total_result" and lane == 1:
            self.start_total_result_transition()

    def _reset_selection(self):
        self.song_index = 0
        self.difficulty_index = 0
        self.selection_phase = "song"
        self.track = self.song_groups[0][0]

    def _show_initial_select(self):
        if self.track_index == 0:
            self.track_scores = [0] * EVENT_TRACK_COUNT
            self.track_names = [""] * EVENT_TRACK_COUNT
            try:
                save_progress(
                    self.progress_path, self.track_index, EVENT_TRACK_COUNT, self.track_scores, self.track_names,
                )
            except OSError as error:
                self._print(f"progress save failed: {error}")
        self._reset_selection()
        self.show_select()

    def _start_warning_select_morph(self):
        if self.scene != "warning":
            return
        self._show_initial_select()
        self.select_morph_in_started = time.monotonic()
        self.select_morph_in_offset = 150.0
        self.canvas.move("select", 0, self.select_morph_in_offset * self.scale)
        self.warning_frames = tuple(self._photo(frame) for frame in self._warning_select_sources())
        self.warning_frame_shown = 0
        self.warning_item = self.canvas.create_image(
            self._x(540), self._y(1120), image=self.warning_frames[0], anchor="center", tags=("warning_select_morph",),
        )
        self.canvas.tag_raise(self.warning_item)
        self._print("warning to music select morph started")

    def _cycle_selection(self):
        self._play_sfx("cursor_select.wav")
        if self.selection_phase == "song":
            self.song_index = (self.song_index + 1) % len(self.song_groups)
            self.difficulty_index = 0
            self.track = self.song_groups[self.song_index][0]
            self._print(f"[ChartManager] song selected: {self.track.artist} - {self.track.title}")
        else:
            difficulties = self.song_groups[self.song_index]
            self.difficulty_index = (self.difficulty_index + 1) % len(difficulties)
            self.track = difficulties[self.difficulty_index]
            self._print(f"[ChartManager] difficulty selected: {self.track.difficulty}")
        self._refresh_selection_list()

    def _confirm_song(self):
        self._play_sfx("ok.wav")
        self.selection_phase = "difficulty"
        self.difficulty_index = 0
        self.track = self.song_groups[self.song_index][0]
        if self.selection_heading_item is not None:
            self.canvas.itemconfigure(self.selection_heading_item, image=self._text("DIFFICULTY SELECT", 54))
        self.canvas.delete("select_shell")
        self._build_selection_shell(("select", "select_shell"))
        self._refresh_selection_list()
        self._print(f"difficulty select visible, song: {self.track.title}")

    def _refresh_selection_list(self):
        self.canvas.delete("select_list")
        if self.selection_sweep_item is not None:
            self.canvas.delete(self.selection_sweep_item)
            self.selection_sweep_item = None
        self.selection_scroll_started = None
        self._build_selection_list(("select", "select_list", "select_dynamic"))

    def _start_selection_scroll(self):
        self.canvas.addtag_withtag("select_old", "select_list")
        self.canvas.dtag("select_old", "select_list")

    def _finish_selection_scroll_setup(self):
        self._build_selection_list(("select", "select_list", "select_dynamic", "select_new"))
        self.selection_scroll_started = time.monotonic()
        self.selection_old_offset = 0.0
        self.selection_new_offset = 180.0
        self.selection_old_x = 0.0
        self.selection_new_x = 250.0
        self.selection_scroll_swapped = False
        self.canvas.move(
            "select_new", self.selection_new_x * self.scale, self.selection_new_offset * self.scale,
        )
        self.canvas.itemconfigure("select_new", state="hidden")
        self._create_selection_sweep()

    def show_title(self, fade_in=False):
        self.scene = "title"
        self.entry_choice = None
        self.fade_started = None
        self.title_fade_started = None
        self.entry_title_fade_started = None
        self.result_fade_started = None
        self.ending_fade_in_started = None
        self.select_fade_in_started = None
        self.transition_phase = None
        self._build_scene()
        self.scene_started = time.monotonic()
        if fade_in:
            self._create_fade_overlay(1.0)
            self.title_fade_started = self.scene_started
        self.root.after(80, lambda: self._play_scene_audio("title", "title.mp3", loop=True, fade_ms=500))
        self._print(f"title visible, mode: {self.settings['mode']}, track: {self._track_key()}")

    def show_entry(self):
        self.scene = "entry"
        self.entry_choice = None
        self.entry_choice_started = 0.0
        self.entry_choice_deadline = 0.0
        self.entry_title_fade_started = None
        self.entry_deadline = time.monotonic() + 20.0
        self._build_scene()
        self.scene_started = time.monotonic()
        self.entry_deadline = self.scene_started + 20.0
        self.root.after(80, self._play_entry_audio)
        self.root.after(140, lambda: self._play_sfx("card_show.wav") if self.scene == "entry" else None)
        self._print("entry visible, guest play only")

    def _start_title_entry_morph(self):
        if self.scene != "title" or self.title_entry_morph_started is not None:
            return
        self.show_entry()
        source = self.sources["title_logo"]
        frames = []
        for index in range(32):
            progress = index / 31
            eased = progress * progress * (3 - 2 * progress)
            scale = 1.0 + 0.72 * eased
            width = max(1, round(source.width * scale))
            height = max(1, round(source.height * scale))
            frame = source.resize((width, height), Image.Resampling.BICUBIC)
            opacity = max(0.0, 1.0 - eased)
            alpha = frame.getchannel("A").point(lambda value, factor=opacity: round(value * factor))
            frame.putalpha(alpha)
            frames.append(self._photo(frame))
        self.title_entry_logo_frames = tuple(frames)
        self.title_entry_logo_frame_shown = 0
        self.title_entry_logo_item = self.canvas.create_image(
            self._x(540), self._y(1000), image=self.title_entry_logo_frames[0],
            anchor="center", tags=("title_entry_morph",),
        )
        self.title_entry_morph_started = time.monotonic()
        self.canvas.tag_raise(self.title_entry_logo_item)
        self._print("title to entry logo morph started")

    def _show_entry_choice(self, choice):
        if self.scene != "entry" or self.entry_choice is not None:
            return
        now = time.monotonic()
        self.entry_choice = choice
        self.entry_choice_started = now
        self.entry_choice_deadline = now + 3.0
        sources = self._entry_card_sources("entry_guest") if choice == "guest" else self._entry_cancel_sources()
        self.entry_card_frames = tuple(self._photo(frame) for frame in sources)
        self.entry_card_frame_shown = 0
        self.canvas.itemconfigure(self.entry_card_item, image=self.entry_card_frames[0])
        self.canvas.itemconfigure("entry_time", state="hidden")
        self.canvas.tag_raise(self.entry_card_item)
        self._play_sfx("ok.wav")
        self._play_sfx("card_show.wav")
        self._print(f"entry {choice} selected, confirmation: 3 seconds")

    def _play_entry_audio(self):
        if self.running and self.scene in ("entry", "warning"):
            self.audio.play(os.path.join(self.bgm_root, "entry.mp3"), loop=True, fade_ms=320)

    def _start_entry_title_transition(self):
        if self.scene != "entry" or self.entry_title_fade_started is not None:
            return
        self.entry_title_fade_started = time.monotonic()
        self.audio.stop(650)
        self._create_fade_overlay(0.0)
        self._print("entry to title fade started")

    def show_warning(self):
        if self.scene != "entry":
            return
        self.scene = "warning"
        self._build_scene()
        self.scene_started = time.monotonic()
        self.warning_deadline = self.scene_started + 3.0
        self.root.after(120, lambda: self._play_sfx("card_show.wav") if self.scene == "warning" else None)
        self._print("warning visible, duration: 3 seconds")

    def show_select(self):
        self.scene = "select"
        self.result_fade_started = None
        self.result_select_morph_started = None
        self.result_transition_target = None
        self.select_morph_in_started = None
        self.select_morph_in_offset = 0.0
        self.select_deadline = time.monotonic() + self.settings["select_seconds"]
        self.select_fade_in_started = None
        self._build_scene()
        self.scene_started = time.monotonic()
        self.select_deadline = self.scene_started + self.settings["select_seconds"]
        self.root.after(80, lambda: self._play_scene_audio("select", self.select_bgm, loop=True, fade_ms=300))
        self.root.after(140, lambda: self._play_sfx("card_show.wav") if self.scene == "select" else None)
        self._print(f"music select visible, songs: {len(self.song_groups)}, track: {self._track_key()}")

    def start_title_select_morph(self):
        if self.scene != "title":
            return
        self.audio.stop(420)
        self._reset_selection()
        self.scene = "title_select"
        self.select_deadline = time.monotonic() + self.settings["select_seconds"]
        self._build_scene()
        self.scene_started = time.monotonic()
        self._print("title to music select morph started")

    def show_next(self):
        self.scene = "next"
        self.next_audio_started = False
        self._build_scene()
        self.scene_started = time.monotonic()
        self.next_audio_deadline = self.scene_started + 5.1
        self.root.after(80, self._play_next_audio)
        self.root.after(180, lambda: self._play_sfx("card_show.wav") if self.scene == "next" else None)
        self._print(f"next music visible, chart: {os.path.basename(self.track.path)}")

    def _play_next_audio(self):
        if not self.running or self.scene != "next" or self.transition_phase is not None:
            return
        self.next_audio_started = True
        self.next_audio_deadline = time.monotonic() + 4.7
        self.audio.play(os.path.join(self.bgm_root, "next.mp3"), fade_ms=220)

    def _play_scene_audio(self, scene, filename, loop=False, fade_ms=0):
        if self.running and self.scene == scene and not (scene == "result" and self.result_fade_started is not None):
            self.audio.play(os.path.join(self.bgm_root, filename), loop=loop, fade_ms=fade_ms)

    def _play_sfx(self, filename):
        self.audio.play_sfx(os.path.join(self.sfx_root, filename))

    def _update_timer(self, item, remaining, shown_attribute, size=52):
        shown = getattr(self, shown_attribute)
        if item is not None and remaining != shown:
            self.canvas.itemconfigure(item, image=self._text(str(remaining), size))
            setattr(self, shown_attribute, remaining)
            if 0 < remaining <= 10 and remaining != self.timer_sfx_value:
                self.timer_sfx_value = remaining
                self._play_sfx("timer_count.wav")

    def _start_loading(self, target, action):
        if self.loading_phase is not None or self.entry_title_fade_started is not None:
            return
        self.loading_target = target
        self.loading_action = action
        self.loading_phase = "fading_out"
        self.loading_started = time.monotonic()
        self._create_fade_overlay(0.0)
        self._print(f"fade transition started: {self.scene} to {target}")

    def _animate_loading_transition(self, now):
        if self.loading_phase == "fading_out":
            progress = min(1.0, (now - self.loading_started) / 0.48)
            eased = progress * progress * (3 - 2 * progress)
            self._set_fade_opacity(eased)
            if progress >= 1.0:
                action = self.loading_action
                self.loading_action = None
                action()
                self._create_fade_overlay(1.0)
                self.loading_phase = "fading_in"
                self.loading_started = now
            return
        if self.loading_phase == "fading_in":
            progress = min(1.0, (now - self.loading_started) / 0.52)
            eased = progress * progress * (3 - 2 * progress)
            self._set_fade_opacity(1.0 - eased)
            if progress >= 1.0:
                self.canvas.delete(self.fade_item)
                self.fade_item = None
                self.loading_phase = None
                self.loading_target = None

    def _begin_game_transition(self):
        if self.loading_phase is not None or self.scene != "next":
            return
        self._start_loading("game", self._start_game_scene)
        self._print("music selected transition started")

    def _start_game_scene(self):
        self.audio.stop()
        self.scene = "game"
        self.scene_started = time.monotonic()
        pre_roll = 2.0 + self.track.audio_lead_in / 1000.0
        self.game_started = self.scene_started + pre_roll
        self.resolved_notes = set()
        self.judgements = []
        self.counts = {key: 0 for key in JUDGEMENT_WEIGHT}
        self.health = 100.0
        self.display_health = 100.0
        self.score = 0
        self.combo = 0
        self.max_combo = 0
        self.active_holds = {}
        self.combo_animation_started = None
        self.combo_frame_shown = -1
        self.health_animation_started = None
        self.health_animation_from = 100.0
        self.health_pulse_started = None
        self.health_change_direction = 0
        self.health_dynamic_photo = None
        self.health_visible_state = None
        self.feedback_until = 0.0
        self.last_feedback = ""
        self.feedback_visible = False
        self.game_finishing = False
        self.note_items = {}
        self._build_scene()
        delay = round(pre_roll * 1000)
        self.game_audio_job = self.root.after(delay, self._start_chart_audio)
        self._print(f"game loaded, notes: {len(self.track.notes)}, format: v{self.track.format_version}")

    def _start_chart_audio(self):
        self.game_audio_job = None
        if not self.running or self.scene != "game":
            return
        self.audio.play(self.track.audio_path, fade_ms=220)
        self._print(f"chart started: {os.path.basename(self.track.path)}")

    def show_result(self):
        if self.scene != "game":
            return
        for index in range(len(self.track.notes)):
            if index not in self.resolved_notes:
                self._resolve_note(index, "miss")
        self.audio.stop(250)
        self.scene = "result"
        self.result_fade_started = None
        self.score = calculate_score(self.judgements, len(self.track.notes))
        self.track_scores[self.track_index] = self.score
        self.track_names[self.track_index] = self.track.title
        self.result_final_counts = dict(self.counts)
        self.result_transition_target = None
        now = time.monotonic()
        self.result_unlock_at = now + 3.0
        duration = self.settings["result_seconds"] if is_clear(self.health) else 3.0
        self.result_deadline = now + duration
        self._build_scene()
        self.scene_started = time.monotonic()
        self.result_unlock_at = self.scene_started + 3.0
        duration = self.settings["result_seconds"] if is_clear(self.health) else 3.0
        self.result_deadline = self.scene_started + duration
        self._print(f"result loaded, score: {self.score}, health: {self.health:.1f}")
        result_bgm = "result_clear.mp3" if is_clear(self.health) else "result_fail.mp3"
        self.root.after(180, lambda: self._play_scene_audio("result", result_bgm, fade_ms=350))
        self.root.after(220, lambda: self._play_sfx("card_show.wav") if self.scene == "result" else None)

    def start_result_transition(self):
        if (
            self.scene != "result"
            or self.loading_phase is not None
            or time.monotonic() < self.result_unlock_at
        ):
            return
        self.result_transition_target, next_track = event_result_destination(self.track_index, is_clear(self.health))
        self.track_index = next_track
        try:
            save_progress(
                self.progress_path, self.track_index, EVENT_TRACK_COUNT, self.track_scores, self.track_names,
            )
        except OSError as error:
            self._print(f"progress save failed: {error}")
        self._play_sfx("ok.wav")
        if self.result_transition_target == "select":
            def show_next_select():
                self._reset_selection()
                self.show_select()

            self._start_loading("select", show_next_select)
            return
        if self.result_transition_target == "total_result":
            self._start_loading("total_result", self.show_total_result)
            return
        self._start_loading("ending", self.show_ending)

    def _finish_result_transition(self):
        if self.result_transition_target == "select":
            self._reset_selection()
            self.show_select()
            return
        if self.result_transition_target == "total_result":
            self.show_total_result()
            return
        self._reset_selection()
        self.show_ending()

    def show_total_result(self):
        self.scene = "total_result"
        self.total_result_deadline = time.monotonic() + 20.0
        self._build_scene()
        self.scene_started = time.monotonic()
        self.total_result_deadline = self.scene_started + 20.0
        self.root.after(80, lambda: self._play_scene_audio("total_result", "total_result.mp3", loop=True, fade_ms=300))
        self.root.after(180, lambda: self._play_sfx("card_show.wav") if self.scene == "total_result" else None)
        self._print(f"total result visible, total score: {sum(self.track_scores)}")

    def start_total_result_transition(self):
        if self.scene != "total_result" or self.loading_phase is not None:
            return
        self._play_sfx("ok.wav")
        self._start_loading("ending", self.show_ending)

    def show_ending(self, fade_in=False):
        if self.scene == "ending":
            return
        self.scene = "ending"
        self.ending_audio_deadline = time.monotonic() + 9.8
        self.ending_audio_started = False
        self.fade_started = None
        self.result_fade_started = None
        self.ending_fade_in_started = None
        self._build_scene()
        self.scene_started = time.monotonic()
        self.ending_audio_deadline = self.scene_started + 9.8
        self.root.after(80, self._play_ending_audio)
        self._print("ending visible")

    def _play_ending_audio(self):
        if not self.running or self.scene != "ending":
            return
        self.ending_audio_started = True
        self.audio.play(os.path.join(self.bgm_root, "game_over.mp3"), fade_ms=300)

    def _track_position(self):
        return self.track_index + 1

    def _track_key(self):
        position = self._track_position()
        if position == EVENT_TRACK_COUNT:
            return "FINAL"
        return str(position)

    def _build_scene(self):
        if not self.running:
            return
        self._prepare_scene()
        self.scene_photos = []
        self.scroll_items = []
        self.particle_item = None
        self.fade_item = None
        self.select_time_item = None
        self.entry_time_item = None
        self.result_time_item = None
        self.total_result_time_item = None
        self.select_time_shown = None
        self.entry_time_shown = None
        self.result_time_shown = None
        self.total_result_time_shown = None
        self.timer_sfx_value = None
        self.next_morph_items = []
        self.title_morph_logo_item = None
        self.title_morph_top_logo_item = None
        self.title_morph_press_item = None
        self.title_morph_logo_frames = ()
        self.title_morph_top_logo_frames = ()
        self.title_morph_press_frames = ()
        self.title_select_offset = 0.0
        self.title_entry_morph_started = None
        self.title_entry_logo_item = None
        self.title_entry_logo_frames = ()
        self.title_entry_logo_frame_shown = -1
        self.selection_scroll_started = None
        self.selection_old_offset = 0.0
        self.selection_new_offset = 0.0
        self.selection_old_x = 0.0
        self.selection_new_x = 0.0
        self.selection_scroll_swapped = False
        self.selection_heading_item = None
        self.selection_sweep_item = None
        self.select_morph_in_started = None
        self.select_morph_in_offset = 0.0
        self.down_button_item = None
        self.entry_card_item = None
        self.entry_card_frames = ()
        self.entry_card_frame_shown = -1
        self.warning_item = None
        self.warning_frames = ()
        self.warning_frame_shown = -1
        self.next_arrow_items = []
        self.result_value_items = {}
        self.result_values_shown = {}
        self.combo_label_item = None
        self.combo_item = None
        self.health_fill_item = None
        self.health_dynamic_photo = None
        self.health_visible_state = None
        self.result_banner_frames = ()
        self.result_banner_frame_shown = -1
        self.result_morph_item = None
        self.result_morph_frames = ()
        self.result_morph_frame_shown = -1
        self.total_result_card_items = []
        self.total_result_cards_revealed = 0
        self.total_result_value_item = None
        self.total_result_value_shown = None
        self.canvas.create_rectangle(
            self._x(0), self._y(0), self._x(DESIGN_WIDTH), self._y(DESIGN_HEIGHT),
            fill="#bd98e8", outline="",
        )
        if self.scene == "game":
            self._build_game()
            return
        self._image("top_gradient", 0, 0, anchor="nw", tags=("background",))
        self._build_common_background()
        if self.scene == "title":
            self._build_title()
        elif self.scene == "entry":
            self._build_entry()
        elif self.scene == "warning":
            self._build_warning()
        elif self.scene == "title_select":
            self._build_title_select_morph()
        elif self.scene == "select":
            self._build_select()
        elif self.scene == "next":
            self._build_next()
        elif self.scene == "result":
            self._build_result()
            if self.result_select_morph_started is not None:
                self.result_select_card_offset = 0.0
                self._create_result_select_morph()
        elif self.scene == "total_result":
            self._build_total_result()
        elif self.scene == "ending":
            self._build_ending()

    def _photo(self, source):
        photo = self._scaled_photo(source)
        self.scene_photos.append(photo)
        return photo

    def _asset_photo(self, name):
        key = name, round(self.scale, 5)
        if key not in self.photo_cache:
            self.photo_cache[key] = self._scaled_photo(self.sources[name])
        return self.photo_cache[key]

    def _text(self, text, size, color="white", align="center"):
        key = text, size, color, align, round(self.scale, 5)
        if key not in self.text_cache:
            self.text_cache[key] = self._text_photo(
                text,
                round(size * TEXT_SCALE),
                color=color,
                font_path=self.novecento_demibold_font_path,
                align=align,
            )
        return self.text_cache[key]

    def _image(self, name, x, y, anchor="center", tags=()):
        return self.canvas.create_image(
            self._x(x), self._y(y), image=self._asset_photo(name), anchor=anchor, tags=tags,
        )

    def _text_image(self, text, size, x, y, color="white", anchor="center", align="center", tags=()):
        return self.canvas.create_image(
            self._x(x), self._y(y), image=self._text(text, size, color, align), anchor=anchor, tags=tags,
        )

    def _build_common_background(self):
        self.particle_base_y = 420
        self.particle_item = self._image("particle", 540, self.particle_base_y, anchor="n", tags=("particle",))
        scroll_photo = self._asset_photo("scroll")
        for y in (520, 1510):
            for index in range(2):
                item = self.canvas.create_image(
                    self._x(index * self.sources["scroll"].width), self._y(y), image=scroll_photo,
                    anchor="nw", tags=("scroll",),
                )
                self.scroll_items.append((item, index, y))
        self._build_header()

    def _build_header(self):
        track_label = self._track_key()
        if track_label != "FINAL":
            track_label = f"TRACK {track_label}"
        labels = {
            "title": ("TWO", "BTN"),
            "entry": ("ENTRY", ""),
            "warning": ("", ""),
            "title_select": (track_label, "SELECT"),
            "select": (track_label, "SELECT"),
            "next": (track_label, "NEXT"),
            "game": (track_label, "GAME"),
            "result": (track_label, "RESULT"),
            "total_result": ("ENDING", "<3"),
            "ending": ("ENDING", "<3"),
        }
        first_label, second_label = labels[self.scene]
        self._image("top", 63, 112, anchor="nw", tags=("header",))
        self._text_image(first_label, 28, 183, 147, tags=("header",))
        self._text_image(second_label, 27, 423, 147, tags=("header",))
        self._text_image("VER 1.0-E", 22, 975, 34, anchor="ne", tags=("header",))
        self._image("network", 995, 18, anchor="ne", tags=("header",))
        self._text_image(
            f"{self.settings['mode']} MODE [{self._track_position()}/{EVENT_TRACK_COUNT}]",
            22, 1018, 74, anchor="ne", tags=("header",),
        )

    def _build_title(self):
        self._image("logo", 540, 270, tags=("title",))
        self._image("title_logo", 540, 1000, tags=("title",))
        self._text_image("PRESS EITHER BUTTON", 36, 540, 1300, tags=("title",))
        self._text_image("© sujeb2 2022-2026", 14, 540, 1880, tags=("title",))

    def _entry_card_sources(self, name="entry"):
        if name in self.entry_card_source_frames:
            return self.entry_card_source_frames[name]
        source = self.sources[name]
        frames = []
        for index in range(24):
            progress = index / 23
            eased = 1 - pow(1 - progress, 3)
            if progress < 0.78:
                width_scale = 0.06 + 1.02 * (1 - pow(1 - progress / 0.78, 3))
            else:
                width_scale = 1.08 + (1.0 - 1.08) * ((progress - 0.78) / 0.22)
            height_scale = 0.84 + 0.16 * eased
            width = max(1, round(source.width * width_scale))
            height = max(1, round(source.height * height_scale))
            frame = source.resize((width, height), Image.Resampling.LANCZOS)
            opacity = min(1.0, progress / 0.16)
            alpha = frame.getchannel("A").point(lambda value, factor=opacity: round(value * factor))
            frame.putalpha(alpha)
            frames.append(frame)
        self.entry_card_source_frames[name] = tuple(frames)
        return self.entry_card_source_frames[name]

    def _entry_cancel_sources(self):
        if self.entry_cancel_source_frames:
            return self.entry_cancel_source_frames
        source = self.sources["entry_cancel"]
        frames = []
        for index in range(24):
            progress = index / 23
            opacity = 0.78 + 0.22 * (0.5 + 0.5 * math.cos(progress * math.pi * 2))
            frame = source.copy()
            alpha = frame.getchannel("A").point(lambda value, factor=opacity: round(value * factor))
            frame.putalpha(alpha)
            frames.append(frame)
        self.entry_cancel_source_frames = tuple(frames)
        return self.entry_cancel_source_frames

    def _warning_sources(self):
        if self.warning_source_frames:
            return self.warning_source_frames
        source = self.sources["warning"]
        frames = []
        for index in range(24):
            progress = index / 23
            if progress < 0.72:
                scale = 0.68 + 0.38 * (1 - pow(1 - progress / 0.72, 3))
            else:
                scale = 1.06 + (1.0 - 1.06) * ((progress - 0.72) / 0.28)
            width = max(1, round(source.width * scale))
            height = max(1, round(source.height * scale))
            frame = source.resize((width, height), Image.Resampling.LANCZOS)
            opacity = min(1.0, progress / 0.18)
            alpha = frame.getchannel("A").point(lambda value, factor=opacity: round(value * factor))
            frame.putalpha(alpha)
            frames.append(frame)
        self.warning_source_frames = tuple(frames)
        return self.warning_source_frames

    def _warning_select_sources(self):
        if self.warning_select_source_frames:
            return self.warning_select_source_frames
        warning_source = self.sources["warning"]
        select_source = self.sources["select_bg"]
        frames = []
        for index in range(24):
            progress = index / 23
            eased = progress * progress * (3 - 2 * progress)
            width = round(warning_source.width + (select_source.width - warning_source.width) * eased)
            height = round(warning_source.height + (select_source.height - warning_source.height) * eased)
            warning_frame = warning_source.resize((width, height), Image.Resampling.LANCZOS)
            select_frame = select_source.resize((width, height), Image.Resampling.LANCZOS)
            frame = Image.blend(warning_frame, select_frame, eased)
            frames.append(frame)
        self.warning_select_source_frames = tuple(frames)
        return self.warning_select_source_frames

    def _build_entry(self):
        self._image("logo", 540, 270, tags=("entry",))
        self._text_image("ENTRY", 54, 70, 755, anchor="w", tags=("entry",))
        self._text_image("TIME LEFT", 18, 970, 725, tags=("entry", "entry_time"))
        remaining = max(0, int(self.entry_deadline - time.monotonic() + 0.999))
        self.entry_time_item = self._text_image(str(remaining), 52, 970, 780, tags=("entry_time",))
        self.entry_time_shown = remaining
        self.entry_card_frames = tuple(self._photo(frame) for frame in self._entry_card_sources())
        self.entry_card_item = self.canvas.create_image(
            self._x(540), self._y(1180), image=self.entry_card_frames[0], anchor="center", tags=("entry_card",),
        )

    def _build_warning(self):
        self._image("logo", 540, 270, tags=("warning",))
        self.warning_frames = tuple(self._photo(frame) for frame in self._warning_sources())
        self.warning_item = self.canvas.create_image(
            self._x(540), self._y(1120), image=self.warning_frames[0], anchor="center", tags=("warning_card",),
        )

    def _build_title_select_morph(self):
        logo_frames = []
        top_logo_frames = []
        press_frames = []
        background = (189, 152, 232)
        for index in range(12):
            progress = index / 11
            scale = 1.0 - 0.52 * progress
            source = self.sources["title_logo"]
            width = max(1, round(source.width * scale))
            height = max(1, round(source.height * scale))
            frame = source.resize((width, height), Image.Resampling.LANCZOS)
            alpha = frame.getchannel("A").point(lambda value, opacity=1.0 - progress: round(value * opacity))
            frame.putalpha(alpha)
            logo_frames.append(self._photo(frame))
            top_frame = self.sources["logo"].copy()
            top_alpha = top_frame.getchannel("A").point(lambda value, opacity=1.0 - progress: round(value * opacity))
            top_frame.putalpha(top_alpha)
            top_logo_frames.append(self._photo(top_frame))
            color = tuple(round(255 + (channel - 255) * progress) for channel in background)
            press_frames.append(self._text("PRESS EITHER BUTTON", 36, f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"))
        self.title_morph_logo_frames = tuple(logo_frames)
        self.title_morph_top_logo_frames = tuple(top_logo_frames)
        self.title_morph_press_frames = tuple(press_frames)
        self.title_morph_top_logo_item = self.canvas.create_image(
            self._x(540), self._y(270), image=top_logo_frames[0], anchor="center", tags=("title_morph",),
        )
        self.title_morph_logo_item = self.canvas.create_image(
            self._x(540), self._y(1000), image=logo_frames[0], anchor="center", tags=("title_morph",),
        )
        self.title_morph_press_item = self.canvas.create_image(
            self._x(540), self._y(1735), image=press_frames[0], anchor="center", tags=("title_morph",),
        )
        self._build_select()
        if self.select_time_item is not None:
            self.canvas.itemconfigure(self.select_time_item, state="hidden")
        self.title_select_offset = 1120.0
        self.canvas.move("select", self.title_select_offset * self.scale, 0)

    def _build_select(self):
        heading = "MUSIC SELECT" if self.selection_phase == "song" else "DIFFICULTY SELECT"
        self.selection_heading_item = self._text_image(heading, 54, 70, 755, anchor="w", tags=("select",))
        self._text_image("TIME LEFT", 18, 970, 725, tags=("select",))
        remaining = max(0, int(self.select_deadline - time.monotonic() + 0.999))
        self.select_time_item = self._text_image(str(remaining), 52, 970, 780, tags=("select_time",))
        self.select_time_shown = remaining
        self._build_selection_shell(("select", "select_shell"))
        self._build_selection_list(("select", "select_list", "select_dynamic"))

    def _build_selection_shell(self, tags):
        self._image("select_bg", 18, 1125, anchor="nw", tags=tags)
        self.down_button_item = self._image("down_button", 540, self.down_button_base_y, tags=tags)

    def _build_selection_list(self, tags):
        if self.selection_phase == "song":
            choices = tuple(group[0].title for group in self.song_groups)
            selected = self.song_index
        else:
            choices = tuple(chart.difficulty for chart in self.song_groups[self.song_index])
            selected = self.difficulty_index
        preview_positions = {
            -2: (850, 925),
            -1: (770, 1085),
            1: (770, 1500),
            2: (850, 1660),
        }
        visible_choices = {selected}
        for offset in (1, -1, 2, -2):
            choice_index = (selected + offset) % len(choices)
            if choice_index in visible_choices:
                continue
            visible_choices.add(choice_index)
            x, y = preview_positions[offset]
            label = choices[choice_index]
            self._image("previous", x, y, tags=tags)
            self._text_image(label.upper(), 27, x, y, color="#ead7fb", tags=tags)
        self._text_image(self.track.title.upper(), 40, 100, 1228, anchor="w", tags=tags)
        detail = self.track.artist if self.selection_phase == "song" else self.track.difficulty
        self._text_image(detail.upper(), 26, 100, 1295, anchor="w", tags=tags)
        self._text_image(str(self.track.level), 92, 930, 1230, tags=tags)
        self._text_image("LEVEL", 21, 930, 1305, tags=tags)

    def _create_selection_sweep(self):
        if self.selection_sweep_item is not None:
            self.canvas.delete(self.selection_sweep_item)
        self.selection_sweep_item = self.canvas.create_image(
            self._x(-150), self._y(1125), image=self._asset_photo("select_sweep"),
            anchor="nw", tags=("select_sweep",),
        )
        self.canvas.tag_raise(self.selection_sweep_item)

    def _build_next(self):
        next_item = self._text_image("NEXT", 54, 540, 900, tags=("next",))
        name_item = self._text_image(self.track.title, 56, 285, 1228, tags=("next_morph",))
        difficulty_item = self._text_image(self.track.difficulty, 33, 285, 1295, tags=("next_morph",))
        level_item = self._text_image(str(self.track.level), 108, 930, 1230, tags=("next_morph",))
        level_label_item = self._text_image("LEVEL", 23, 930, 1305, tags=("next_morph",))
        self.next_morph_items = [
            (name_item, (285, 1228), (540, 1160)),
            (difficulty_item, (285, 1295), (540, 1280)),
            (level_item, (930, 1230), (540, 1450)),
            (level_label_item, (930, 1305), (540, 1535)),
        ]
        self.canvas.coords(next_item, self._x(540), self._y(900))
        frames = []
        for name in ("next_arrow_left", "next_arrow"):
            source = self.sources[name]
            image_frames = []
            for opacity in tuple(0.3 + 0.7 * index / 7 for index in range(8)):
                frame = source.copy()
                alpha = frame.getchannel("A").point(lambda value, factor=opacity: round(value * factor))
                frame.putalpha(alpha)
                image_frames.append(self._photo(frame))
            frames.append(tuple(image_frames))
        self.next_arrow_frames = tuple(frames)
        left_item = self.canvas.create_image(self._x(365), self._y(900), image=frames[0][0], anchor="center", tags=("next",))
        right_item = self.canvas.create_image(self._x(715), self._y(900), image=frames[1][0], anchor="center", tags=("next",))
        self.next_arrow_items = [left_item, right_item]

    def _build_game(self):
        self.note_items = {}
        self.canvas.create_rectangle(
            self._x(0), self._y(0), self._x(DESIGN_WIDTH), self._y(DESIGN_HEIGHT),
            fill="#8d73aa", outline="", tags=("game",),
        )
        self._image("top_gradient", 0, 0, anchor="nw", tags=("game",))
        self._build_header()
        self._text_image("DIFFICULTY", 26, 95, 300, anchor="w", tags=("game",))
        title_size = 47 if len(self.track.title) <= 20 else max(30, round(47 * 20 / len(self.track.title)))
        self._text_image(self.track.title.upper(), title_size, 95, 360, anchor="w", tags=("game",))
        self._text_image("SCORE", 26, 1008, 300, anchor="e", tags=("game",))
        self.score_item = self._text_image(str(self.score), 58, 1008, 362, anchor="e", tags=("game_score",))
        self._image("main_layer", 290, 470, anchor="nw", tags=("game",))
        self.note_photos = (self._asset_photo("note_0"), self._asset_photo("note_1"))
        self.combo_item = self.canvas.create_image(self._x(540), self._y(790), anchor="center", tags=("game_combo",))
        if self.combo > 0:
            self.canvas.itemconfigure(self.combo_item, image=self._combo_photo(self.combo, 78))
        self.judgement_line_item = self._image("line", 290, 1560, anchor="nw", tags=("game_line",))
        self._image("health_bg", 835, 655, anchor="nw", tags=("game",))
        self.health_fill_item = self.canvas.create_image(self._x(853), self._y(1554), anchor="s", tags=("game_health",))
        self.judgement_item = self.canvas.create_image(self._x(540), self._y(1715), anchor="center", tags=("game_feedback",))
        self.judgement_frames = {
            name: tuple(self._photo(frame) for frame in self._judgement_animation_sources(name))
            for name in JUDGEMENT_WEIGHT
        }
        self._update_health_image()

    def _combo_photo(self, combo, number_size):
        key = combo, number_size, round(self.scale, 5)
        if key in self.combo_photo_cache:
            return self.combo_photo_cache[key]
        image = Image.new("RGBA", (340, 190), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        label_font = ImageFont.truetype(self.novecento_demibold_font_path, round(29 * TEXT_SCALE))
        number_font = ImageFont.truetype(self.novecento_demibold_font_path, round(number_size * TEXT_SCALE))
        label_box = draw.textbbox((0, 0), "COMBO", font=label_font)
        number = str(combo)
        number_box = draw.textbbox((0, 0), number, font=number_font)
        draw.text(((340 - label_box[2] + label_box[0]) / 2, 8 - label_box[1]), "COMBO", font=label_font, fill="white")
        draw.text(((340 - number_box[2] + number_box[0]) / 2, 68 - number_box[1]), number, font=number_font, fill="white")
        self.combo_photo_cache[key] = self._scaled_photo(image)
        return self.combo_photo_cache[key]

    def _result_wave_sources(self, name):
        if name in self.result_wave_source_frames:
            return self.result_wave_source_frames[name]
        source = self.sources[name]
        padding = 10
        frames = []
        for frame_index in range(30):
            frame = Image.new("RGBA", (source.width, source.height + padding * 2), (0, 0, 0, 0))
            phase = frame_index / 30 * math.tau
            for x in range(0, source.width, 4):
                right = min(source.width, x + 4)
                offset = round(4 * math.sin(x / source.width * math.tau * 1.35 + phase))
                frame.alpha_composite(source.crop((x, 0, right, source.height)), (x, padding + offset))
            frames.append(frame)
        self.result_wave_source_frames[name] = tuple(frames)
        return self.result_wave_source_frames[name]

    def _result_morph_sources(self):
        if self.result_morph_source_frames:
            return self.result_morph_source_frames
        source = self.sources["select_bg"]
        frames = []
        for index in range(16):
            progress = index / 15
            eased = progress * progress * (3 - 2 * progress)
            width = round(954 + (1044 - 954) * eased)
            height = round(629 + (276 - 629) * eased)
            frame = source.resize((width, height), Image.Resampling.LANCZOS)
            opacity = min(1.0, 0.18 + progress * 1.35)
            alpha = frame.getchannel("A").point(lambda value, factor=opacity: round(value * factor))
            frame.putalpha(alpha)
            frames.append(frame)
        self.result_morph_source_frames = tuple(frames)
        return self.result_morph_source_frames

    def _create_result_select_morph(self):
        self.result_morph_frames = tuple(self._photo(frame) for frame in self._result_morph_sources())
        self.result_morph_frame_shown = 0
        self.result_morph_item = self.canvas.create_image(
            self._x(540), self._y(1344), image=self.result_morph_frames[0],
            anchor="center", tags=("result_morph",),
        )
        self.canvas.tag_raise(self.result_morph_item)

    def _judgement_animation_sources(self, name):
        if name in self.judgement_source_frames:
            return self.judgement_source_frames[name]
        source = self.sources[name]
        colors = {
            "perfect": (128, 244, 255),
            "good": (255, 225, 91),
            "bad": (255, 90, 232),
            "miss": (255, 92, 92),
        }
        frame_count = 24
        max_scale = 1.24
        width = round(source.width * max_scale) + 44
        height = round(source.height * max_scale) + 44
        frames = []
        for index in range(frame_count):
            progress = index / (frame_count - 1)
            if progress < 0.16:
                part = progress / 0.16
                scale = 0.58 + (1.22 - 0.58) * (1 - pow(1 - part, 3))
            elif progress < 0.34:
                part = (progress - 0.16) / 0.18
                scale = 1.22 + (0.94 - 1.22) * part
            elif progress < 0.50:
                part = (progress - 0.34) / 0.16
                scale = 0.94 + (1.06 - 0.94) * part
            elif progress < 0.68:
                part = (progress - 0.50) / 0.18
                scale = 1.06 + (1.0 - 1.06) * part
            else:
                scale = 1.0
            opacity = min(1.0, progress / 0.08)
            if progress > 0.76:
                opacity = max(0.0, 1.0 - (progress - 0.76) / 0.24)
            glow_strength = 0.62 + 0.26 * (0.5 + 0.5 * math.sin(progress * math.pi * 6))
            scaled_width = max(1, round(source.width * scale))
            scaled_height = max(1, round(source.height * scale))
            scaled = source.resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)
            scaled_alpha = scaled.getchannel("A").point(lambda value, factor=opacity: round(value * factor))
            scaled.putalpha(scaled_alpha)
            x = (width - scaled_width) // 2
            y = (height - scaled_height) // 2
            mask = Image.new("L", (width, height), 0)
            mask.paste(scaled_alpha, (x, y))
            glow_alpha = mask.filter(ImageFilter.GaussianBlur(7)).point(
                lambda value, factor=glow_strength: round(value * factor)
            )
            glow = Image.new("RGBA", (width, height), (*colors[name], 0))
            glow.putalpha(glow_alpha)
            frame = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            frame.alpha_composite(glow)
            frame.alpha_composite(scaled, (x, y))
            frames.append(frame)
        self.judgement_source_frames[name] = tuple(frames)
        return self.judgement_source_frames[name]

    def _build_result(self):
        self._text_image("RESULT", 54, 70, 755, anchor="w", tags=("result",))
        self._text_image("TIME LEFT", 18, 970, 725, tags=("result",))
        remaining = max(0, int(self.result_deadline - time.monotonic() + 0.999))
        self.result_time_item = self._text_image(str(remaining), 52, 970, 780, tags=("result_time",))
        self.result_time_shown = remaining
        banner_name = "clear" if is_clear(self.health) else "failed"
        self.result_banner_frames = tuple(self._photo(frame) for frame in self._result_wave_sources(banner_name))
        self.result_banner_frame_shown = 0
        self.result_banner_item = self.canvas.create_image(
            self._x(540), self._y(840), image=self.result_banner_frames[0], anchor="center", tags=("result_banner",),
        )
        self.result_card_offset = 560.0
        offset = self.result_card_offset
        self._image("result_bg", 63, 1030 + offset, anchor="nw", tags=("result_card",))
        self._text_image(self.track.title, 46, 115, 1135 + offset, anchor="w", tags=("result_card",))
        self._text_image(self.track.difficulty, 27, 115, 1210 + offset, anchor="w", tags=("result_card",))
        self._text_image(str(self.track.level), 70, 948, 1135 + offset, tags=("result_card",))
        self._text_image("LEVEL", 19, 948, 1195 + offset, tags=("result_card",))
        labels = (("PERFECT", "#88f5ff"), ("GOOD", "#ffe35d"), ("BAD", "#ff68c7"), ("MISS", "#ff6262"))
        for index, (label, color) in enumerate(labels):
            y = 1320 + index * 58 + offset
            self._text_image(label, 29, 116, y, color=color, anchor="w", tags=("result_card",))
            item = self._text_image("0", 29, 470, y, anchor="e", tags=("result_card",))
            self.result_value_items[label.lower()] = item
            self.result_values_shown[label.lower()] = 0
        self._text_image("HEALTH", 23, 695, 1390 + offset, anchor="w", tags=("result_card",))
        self._text_image(f"{self.health:.0f}%", 38, 940, 1388 + offset, anchor="e", tags=("result_card",))
        self._text_image("SCORE", 25, 940, 1498 + offset, anchor="e", tags=("result_card",))
        self.result_value_items["score"] = self._text_image("0", 63, 940, 1560 + offset, anchor="e", tags=("result_card",))
        self.result_values_shown["score"] = 0

    def _build_total_result(self):
        self._text_image("TOTAL RESULT", 54, 70, 755, anchor="w", tags=("total_result",))
        self._text_image("TIME LEFT", 18, 970, 725, tags=("total_result",))
        remaining = max(0, int(self.total_result_deadline - time.monotonic() + 0.999))
        self.total_result_time_item = self._text_image(
            str(remaining), 52, 970, 780, tags=("total_result_time",),
        )
        self.total_result_time_shown = remaining
        self._image("total_result_layout", 540, 1240, tags=("total_result",))
        row_y = (1015, 1221, 1425)
        for index, y in enumerate(row_y):
            name = self.track_names[index] or "---"
            size = 35 if len(name) <= 24 else max(24, round(35 * 24 / len(name)))
            self._text_image(name.upper(), size, 170, y, anchor="w", tags=("total_result",))
            self._text_image(str(self.track_scores[index]), 42, 910, y, anchor="e", tags=("total_result",))
        self.total_result_value_item = self._text_image("0", 76, 540, 1635, tags=("total_result",))
        self.total_result_value_shown = 0
        self._image("result_down_button", 540, 1845, tags=("total_result",))

    def _build_ending(self):
        self._image("logo", 540, 270, tags=("ending",))
        self._text_image(f"GAME OVER\n\n\n\n\n\n\nSEE YOU NEXT TIME!", 41, 540, 940, tags=("ending",))
        self._image("title_logo", 540, 1260, tags=("ending",))

    def _fade_photo(self, opacity):
        level = min(32, max(0, round(opacity * 32)))
        key = round(self.scale, 5), level
        if key not in self.fade_photo_cache:
            width = max(1, round(DESIGN_WIDTH * self.scale))
            height = max(1, round(DESIGN_HEIGHT * self.scale))
            alpha = round(255 * level / 32)
            self.fade_photo_cache[key] = ImageTk.PhotoImage(Image.new("RGBA", (width, height), (0, 0, 0, alpha)))
        return self.fade_photo_cache[key]

    def _create_fade_overlay(self, opacity=0.0):
        self.fade_item = self.canvas.create_image(
            self._x(0), self._y(0), image=self._fade_photo(opacity), anchor="nw", tags=("fade",),
        )
        self.canvas.tag_raise(self.fade_item)

    def _set_fade_opacity(self, opacity):
        if self.fade_item is None:
            self._create_fade_overlay(opacity)
        else:
            self.canvas.itemconfigure(self.fade_item, image=self._fade_photo(opacity))
            self.canvas.tag_raise(self.fade_item)

    def _create_curtains(self, closed):
        if closed:
            top = (0, 0, DESIGN_WIDTH, DESIGN_HEIGHT / 2)
            bottom = (0, DESIGN_HEIGHT / 2, DESIGN_WIDTH, DESIGN_HEIGHT)
        else:
            top = (0, 0, DESIGN_WIDTH, 0)
            bottom = (0, DESIGN_HEIGHT, DESIGN_WIDTH, DESIGN_HEIGHT)
        self.curtain_items = (
            self.canvas.create_rectangle(*self._scaled_box(top), fill="#2d2439", outline="", tags=("curtain",)),
            self.canvas.create_rectangle(*self._scaled_box(bottom), fill="#2d2439", outline="", tags=("curtain",)),
        )
        self.canvas.tag_raise("curtain")

    def _scaled_box(self, box):
        return self._x(box[0]), self._y(box[1]), self._x(box[2]), self._y(box[3])

    def _judge(self, lane):
        if self.game_started is None:
            return
        elapsed = time.monotonic() - self.game_started
        candidates = [
            (abs(note.time - elapsed), index)
            for index, note in enumerate(self.track.notes)
            if index not in self.resolved_notes and note.lane == lane and abs(note.time - elapsed) <= HIT_WINDOW
        ]
        if not candidates:
            return
        difference, index = min(candidates)
        if difference <= PERFECT_WINDOW:
            judgement = "perfect"
        elif difference <= GOOD_WINDOW:
            judgement = "good"
        else:
            judgement = "bad"
        self._resolve_note(index, judgement)

    def _resolve_note(self, index, judgement):
        if index in self.resolved_notes:
            return
        self.resolved_notes.add(index)
        self.judgements.append(judgement)
        self.counts[judgement] += 1
        previous_health = self.health
        self.health = min(100.0, max(0.0, self.health + HEALTH_CHANGE[judgement]))
        self.score = calculate_score(self.judgements, len(self.track.notes))
        if judgement == "miss":
            self._break_combo()
        else:
            self._advance_combo()
            note = self.track.notes[index]
            ticks = tuple(tick for tick in hold_tick_times(note.time, note.end_time) if tick > time.monotonic() - self.game_started)
            if ticks:
                self.active_holds[index] = {"ticks": ticks, "next": 0, "end_time": note.end_time}
        self.last_feedback = judgement
        self.feedback_started = time.monotonic()
        self.feedback_until = self.feedback_started + 0.58
        self.feedback_frame_shown = 0
        if self.score_item is not None:
            self.canvas.itemconfigure(self.score_item, image=self._text(str(self.score), 58))
        self._start_health_animation(previous_health, self.health)
        if self.judgement_item is not None:
            self.canvas.itemconfigure(self.judgement_item, image=self.judgement_frames[self.last_feedback][0])
            self.feedback_visible = True

    def _advance_combo(self):
        self.combo = combo_after_judgement(self.combo, "perfect")
        self.max_combo = max(self.max_combo, self.combo)
        self.combo_animation_started = time.monotonic()
        self.combo_frame_shown = -1
        self.combo_photo_cache.clear()
        if self.combo_item is not None:
            self.canvas.itemconfigure(self.combo_item, image=self._combo_photo(self.combo, 70))

    def _break_combo(self):
        self.combo = 0
        self.combo_animation_started = None
        self.combo_frame_shown = -1
        self.combo_photo_cache.clear()
        if self.combo_item is not None:
            self.canvas.itemconfigure(self.combo_item, image="")

    def _animate_combo(self, now):
        if self.combo_item is None or self.combo <= 0:
            return
        if self.combo_animation_started is None:
            size = 78
            y = 790.0
        else:
            progress = min(1.0, (now - self.combo_animation_started) / 0.24)
            if progress < 0.34:
                part = progress / 0.34
                eased = part * part * (3 - 2 * part)
                size = round(70 + 14 * eased)
                y = 798 - 14 * eased
            elif progress < 0.7:
                part = (progress - 0.34) / 0.36
                eased = part * part * (3 - 2 * part)
                size = round(84 - 7 * eased)
                y = 784 + 7 * eased
            else:
                part = (progress - 0.7) / 0.3
                eased = part * part * (3 - 2 * part)
                size = round(77 + eased)
                y = 791 - eased
            if progress >= 1.0:
                self.combo_animation_started = None
        state = size, round(y, 1)
        if state == self.combo_frame_shown:
            return
        self.canvas.itemconfigure(self.combo_item, image=self._combo_photo(self.combo, size))
        self.canvas.coords(self.combo_item, self._x(540), self._y(y))
        self.combo_frame_shown = state

    def _start_health_animation(self, previous, current):
        self.health_animation_from = self.display_health
        self.health_animation_started = time.monotonic()
        self.health_pulse_started = self.health_animation_started
        self.health_change_direction = 1 if current > previous else -1 if current < previous else 0

    def _animate_health(self, now):
        if self.health_fill_item is None:
            return
        if self.health_animation_started is not None:
            progress = min(1.0, (now - self.health_animation_started) / 0.28)
            eased = progress * progress * (3 - 2 * progress)
            self.display_health = self.health_animation_from + (self.health - self.health_animation_from) * eased
            if progress >= 1.0:
                self.display_health = self.health
                self.health_animation_started = None
        pulse_progress = 1.0
        if self.health_pulse_started is not None:
            pulse_progress = min(1.0, (now - self.health_pulse_started) / 0.34)
            if pulse_progress >= 1.0:
                self.health_pulse_started = None
        pulse = math.sin(pulse_progress * math.pi) * (0.08 if self.health_change_direction >= 0 else 0.13)
        shake = 0.0
        if self.health_change_direction < 0 and pulse_progress < 1.0:
            shake = math.sin(pulse_progress * math.pi * 6) * 4 * (1 - pulse_progress)
        self._update_health_image(self.display_health, 1.0 + pulse, shake)

    def _update_health_image(self, value=None, width_scale=1.0, shake=0.0):
        if self.health_fill_item is None:
            return
        value = self.health if value is None else value
        state = round(value, 1), round(width_scale, 2)
        self.canvas.coords(self.health_fill_item, self._x(853 + shake), self._y(1554))
        if state == self.health_visible_state:
            return
        self.health_visible_state = state
        source = self.sources["health"]
        if value <= 0:
            self.canvas.itemconfigure(self.health_fill_item, image="")
            return
        visible_height = max(1, round(source.height * value / 100.0))
        crop = source.crop((0, source.height - visible_height, source.width, source.height))
        width = max(1, round(crop.width * width_scale))
        if width != crop.width:
            crop = crop.resize((width, crop.height), Image.Resampling.LANCZOS)
        self.health_dynamic_photo = self._scaled_photo(crop)
        self.canvas.itemconfigure(self.health_fill_item, image=self.health_dynamic_photo)

    def _update_hold_ticks(self, elapsed):
        for index, state in tuple(self.active_holds.items()):
            ticks = state["ticks"]
            while state["next"] < len(ticks) and elapsed >= ticks[state["next"]]:
                state["next"] += 1
                previous_health = self.health
                self.health = min(100.0, self.health + 0.08)
                self._advance_combo()
                self._start_health_animation(previous_health, self.health)
            if elapsed > state["end_time"] + BAD_WINDOW:
                self.active_holds.pop(index, None)

    def _update_feedback_image(self):
        if self.judgement_item is None or not self.feedback_visible:
            return
        now = time.monotonic()
        if now >= self.feedback_until:
            self.canvas.itemconfigure(self.judgement_item, image="")
            self.feedback_visible = False
            return
        frames = self.judgement_frames[self.last_feedback]
        progress = max(0.0, (now - self.feedback_started) / 0.58)
        frame = min(len(frames) - 1, int(progress * len(frames)))
        if frame != self.feedback_frame_shown:
            self.canvas.itemconfigure(self.judgement_item, image=frames[frame])
            self.feedback_frame_shown = frame

    def _update_game_frame(self, now):
        if self.scene != "game" or self.game_started is None:
            return
        elapsed = now - self.game_started
        self._update_hold_ticks(elapsed)
        for index, note in enumerate(self.track.notes):
            if index not in self.resolved_notes and elapsed > note.time + BAD_WINDOW:
                self._resolve_note(index, "miss")
        lead_time = 2.0
        start_y = 505
        hit_y = 1560
        visible_notes = set()
        for index, note in enumerate(self.track.notes):
            active_hold = index in self.active_holds
            if index in self.resolved_notes and not active_hold:
                continue
            time_until = note.time - elapsed
            tail_until = (note.end_time if note.end_time is not None else note.time) - elapsed
            if tail_until >= -BAD_WINDOW and time_until <= lead_time:
                visible_notes.add(index)
                y = hit_y if active_hold else min(hit_y, hit_y - time_until / lead_time * (hit_y - start_y))
                tail_y = min(hit_y, hit_y - tail_until / lead_time * (hit_y - start_y))
                x = 290 + note.lane * 250
                if index not in self.note_items:
                    body = None
                    tail = None
                    if note.end_time is not None and note.end_time > note.time:
                        body = self.canvas.create_rectangle(
                            self._x(x + 28), self._y(tail_y + 22), self._x(x + 222), self._y(y + 22),
                            fill="#145fda" if note.lane == 0 else "#d7d7dc", outline="", tags=("game_note",),
                        )
                        tail = self.canvas.create_image(
                            self._x(x), self._y(tail_y), image=self.note_photos[note.lane], anchor="nw", tags=("game_note",),
                        )
                    head = self.canvas.create_image(
                        self._x(x), self._y(y), image=self.note_photos[note.lane], anchor="nw", tags=("game_note",),
                    )
                    self.note_items[index] = {"body": body, "tail": tail, "head": head}
                else:
                    items = self.note_items[index]
                    self.canvas.coords(items["head"], self._x(x), self._y(y))
                    if items["body"] is not None:
                        self.canvas.coords(
                            items["body"], self._x(x + 28), self._y(tail_y + 22), self._x(x + 222), self._y(y + 22),
                        )
                        self.canvas.coords(items["tail"], self._x(x), self._y(tail_y))
        for index in tuple(self.note_items):
            if index not in visible_notes:
                for item in self.note_items.pop(index).values():
                    if item is not None:
                        self.canvas.delete(item)
        self.canvas.tag_raise("game_line")
        self.canvas.tag_raise("game_combo")
        self.canvas.tag_raise("game_feedback")
        self.canvas.tag_raise("game_health")
        self._animate_combo(now)
        self._animate_health(now)
        self._update_feedback_image()
        if not self.game_finishing and (self.health <= 0 or elapsed >= self.track.duration + 1.6):
            self.game_finishing = True
            self.audio.stop(180)
            self._start_loading("result", self.show_result)

    def _animate_common(self, now):
        elapsed = now - self.animation_epoch
        if self.particle_item is not None:
            y = self.particle_base_y + 13 * math.sin(elapsed * 0.8)
            self.canvas.coords(self.particle_item, self._x(540), self._y(y))
        if self.scroll_items:
            width = self.sources["scroll"].width
            offset = (elapsed * 72) % width
            for item, index, y in self.scroll_items:
                self.canvas.coords(item, self._x(index * width - offset), self._y(y))

    def _animate_title_select_morph(self, now):
        elapsed = now - self.scene_started
        progress = min(1.0, elapsed / 1.15)
        eased = progress * progress * (3 - 2 * progress)
        frame = min(11, round(progress * 11))
        if self.title_morph_logo_item is not None:
            x = 540 - 250 * eased
            y = 1000 - 245 * eased
            self.canvas.coords(self.title_morph_logo_item, self._x(x), self._y(y))
            self.canvas.itemconfigure(self.title_morph_logo_item, image=self.title_morph_logo_frames[frame])
        if self.title_morph_top_logo_item is not None:
            self.canvas.itemconfigure(self.title_morph_top_logo_item, image=self.title_morph_top_logo_frames[frame])
        if self.title_morph_press_item is not None:
            self.canvas.coords(self.title_morph_press_item, self._x(540), self._y(1735 + 100 * eased))
            self.canvas.itemconfigure(self.title_morph_press_item, image=self.title_morph_press_frames[frame])
        new_offset = 1120 * (1 - eased)
        delta = new_offset - self.title_select_offset
        if abs(delta) > 0.001:
            self.canvas.move("select", delta * self.scale, 0)
            self.title_select_offset = new_offset
        if progress >= 1.0:
            self.show_select()

    def _animate_entry(self, now):
        if self.entry_title_fade_started is not None:
            progress = min(1.0, (now - self.entry_title_fade_started) / 0.65)
            eased = progress * progress * (3 - 2 * progress)
            self._set_fade_opacity(eased)
            if progress >= 1.0:
                self.show_title(fade_in=True)
            return
        if self.entry_choice is not None:
            elapsed = now - self.entry_choice_started
            if self.entry_choice == "guest":
                progress = min(1.0, elapsed / 0.72)
                frame = min(len(self.entry_card_frames) - 1, round(progress * (len(self.entry_card_frames) - 1)))
            else:
                frame = int(elapsed * 24) % len(self.entry_card_frames)
            if frame != self.entry_card_frame_shown:
                self.canvas.itemconfigure(self.entry_card_item, image=self.entry_card_frames[frame])
                self.entry_card_frame_shown = frame
            if now >= self.entry_choice_deadline:
                if self.entry_choice == "guest":
                    self.show_warning()
                else:
                    self._start_entry_title_transition()
            return
        elapsed = now - self.scene_started
        progress = min(1.0, elapsed / 0.72)
        frame = min(len(self.entry_card_frames) - 1, round(progress * (len(self.entry_card_frames) - 1)))
        if frame != self.entry_card_frame_shown:
            self.canvas.itemconfigure(self.entry_card_item, image=self.entry_card_frames[frame])
            self.entry_card_frame_shown = frame
        remaining = max(0, int(self.entry_deadline - now + 0.999))
        self._update_timer(self.entry_time_item, remaining, "entry_time_shown")
        if now >= self.entry_deadline:
            self._start_entry_title_transition()

    def _animate_warning(self, now):
        elapsed = now - self.scene_started
        progress = min(1.0, elapsed / 0.48)
        frame = min(len(self.warning_frames) - 1, round(progress * (len(self.warning_frames) - 1)))
        if frame != self.warning_frame_shown:
            self.canvas.itemconfigure(self.warning_item, image=self.warning_frames[frame])
            self.warning_frame_shown = frame
        if now >= self.warning_deadline:
            self._start_warning_select_morph()

    def _animate_warning_select_morph(self, now):
        if self.select_morph_in_started is None:
            return
        progress = min(1.0, (now - self.select_morph_in_started) / 0.82)
        eased = progress * progress * (3 - 2 * progress)
        new_offset = 150.0 * (1 - eased)
        delta = new_offset - self.select_morph_in_offset
        if abs(delta) > 0.001:
            self.canvas.move("select", 0, delta * self.scale)
            self.select_morph_in_offset = new_offset
        frame = min(len(self.warning_frames) - 1, round(eased * (len(self.warning_frames) - 1)))
        if frame != self.warning_frame_shown:
            self.canvas.itemconfigure(self.warning_item, image=self.warning_frames[frame])
            self.warning_frame_shown = frame
        y = 1120 + (1263 - 1120) * eased
        self.canvas.coords(self.warning_item, self._x(540), self._y(y))
        self.canvas.tag_raise(self.warning_item)
        if progress >= 1.0:
            self.canvas.delete(self.warning_item)
            self.warning_item = None
            self.warning_frames = ()
            self.select_morph_in_started = None
            self.select_morph_in_offset = 0.0

    def _animate_next(self, now):
        elapsed = now - self.scene_started
        progress = min(1.0, elapsed / 0.72)
        eased = 1 - pow(1 - progress, 3)
        for item, start, end in self.next_morph_items:
            x = start[0] + (end[0] - start[0]) * eased
            y = start[1] + (end[1] - start[1]) * eased
            self.canvas.coords(item, self._x(x), self._y(y))
        if self.next_arrow_items:
            pulse = (elapsed * 12) % len(self.next_arrow_frames[0])
            frame = int(pulse)
            travel = 10 * math.sin(elapsed * 5.5)
            self.canvas.coords(self.next_arrow_items[0], self._x(365 - travel), self._y(900))
            self.canvas.coords(self.next_arrow_items[1], self._x(715 + travel), self._y(900))
            self.canvas.itemconfigure(self.next_arrow_items[0], image=self.next_arrow_frames[0][frame])
            self.canvas.itemconfigure(self.next_arrow_items[1], image=self.next_arrow_frames[1][frame])
        audio_finished = self.next_audio_started and self.audio.available and not self.audio.is_playing()
        if now >= self.next_audio_deadline or audio_finished:
            self._begin_game_transition()

    def _animate_transition(self, now):
        if self.transition_phase == "closing":
            progress = min(1.0, (now - self.transition_started) / 0.48)
            eased = progress * progress * (3 - 2 * progress)
            self.canvas.coords(self.curtain_items[0], *self._scaled_box((0, 0, DESIGN_WIDTH, 960 * eased)))
            self.canvas.coords(self.curtain_items[1], *self._scaled_box((0, 1920 - 960 * eased, DESIGN_WIDTH, 1920)))
            if progress >= 1.0:
                self._start_game_scene()
        elif self.transition_phase == "opening":
            progress = min(1.0, (now - self.transition_started) / 0.55)
            eased = progress * progress * (3 - 2 * progress)
            self.canvas.coords(self.curtain_items[0], *self._scaled_box((0, 0, DESIGN_WIDTH, 960 * (1 - eased))))
            self.canvas.coords(self.curtain_items[1], *self._scaled_box((0, 960 + 960 * eased, DESIGN_WIDTH, 1920)))
            if progress >= 1.0:
                self.canvas.delete("curtain")
                self.transition_phase = None

    def _animate_result(self, now):
        elapsed = now - self.scene_started
        progress = min(1.0, elapsed / 1.05)
        c1 = 1.70158
        c3 = c1 + 1
        shifted = progress - 1
        eased = 1 + c3 * shifted * shifted * shifted + c1 * shifted * shifted
        new_offset = 560 * (1 - eased)
        delta = new_offset - self.result_card_offset
        if abs(delta) > 0.001:
            self.canvas.move("result_card", 0, delta * self.scale)
            self.result_card_offset = new_offset
        if self.result_banner_item is not None:
            banner_frame = int(elapsed * 24) % len(self.result_banner_frames)
            if banner_frame != self.result_banner_frame_shown:
                self.canvas.itemconfigure(self.result_banner_item, image=self.result_banner_frames[banner_frame])
                self.result_banner_frame_shown = banner_frame
            banner_y = 840 + 85 * eased + 3 * math.sin(elapsed * 2.4)
            self.canvas.coords(self.result_banner_item, self._x(540), self._y(banner_y))
        count_progress = min(1.0, elapsed / 1.25)
        count_eased = 1 - pow(1 - count_progress, 3)
        final_values = {**self.result_final_counts, "score": self.score}
        for name, final_value in final_values.items():
            value = round(final_value * count_eased)
            if value != self.result_values_shown.get(name):
                size = 63 if name == "score" else 29
                self.canvas.itemconfigure(self.result_value_items[name], image=self._text(str(value), size))
                self.result_values_shown[name] = value
    def _animate_selection_scroll(self, now):
        if self.selection_scroll_started is None:
            return
        progress = min(1.0, (now - self.selection_scroll_started) / 0.52)
        sweep_eased = progress * progress * (3 - 2 * progress)
        if self.selection_sweep_item is not None:
            self.canvas.coords(self.selection_sweep_item, self._x(-150 + 1380 * sweep_eased), self._y(1125))
            self.canvas.tag_raise(self.selection_sweep_item)
        if progress < 0.48:
            part = progress / 0.48
            eased = 1 - pow(1 - part, 3)
            angle = eased * math.pi / 2
            old_x = 250.0 * math.sin(angle)
            old_offset = -180.0 * (1 - math.cos(angle))
            old_x_delta = old_x - self.selection_old_x
            old_delta = old_offset - self.selection_old_offset
            self.canvas.move("select_old", old_x_delta * self.scale, old_delta * self.scale)
            self.selection_old_x = old_x
            self.selection_old_offset = old_offset
            return
        if not self.selection_scroll_swapped:
            self.canvas.delete("select_old")
            self.canvas.itemconfigure("select_new", state="normal")
            self.selection_scroll_swapped = True
        part = (progress - 0.48) / 0.52
        eased = 1 - pow(1 - part, 3)
        angle = (1 - eased) * math.pi / 2
        new_x = 250.0 * math.sin(angle)
        new_offset = 180.0 * (1 - math.cos(angle))
        new_x_delta = new_x - self.selection_new_x
        new_delta = new_offset - self.selection_new_offset
        self.canvas.move("select_new", new_x_delta * self.scale, new_delta * self.scale)
        self.selection_new_x = new_x
        self.selection_new_offset = new_offset
        if progress >= 1.0:
            self.canvas.dtag("select_new", "select_new")
            self.selection_scroll_started = None
            if self.selection_sweep_item is not None:
                self.canvas.delete(self.selection_sweep_item)
                self.selection_sweep_item = None

    def _animate_total_result(self, now):
        elapsed = now - self.scene_started
        progress = min(1.0, elapsed / 1.35)
        eased = 1 - pow(1 - progress, 3)
        value = round(sum(self.track_scores) * eased)
        if value != self.total_result_value_shown:
            self.canvas.itemconfigure(self.total_result_value_item, image=self._text(f"{value:,}", 76))
            self.total_result_value_shown = value

    def _animate_ending(self, now):
        audio_finished = self.ending_audio_started and self.audio.available and not self.audio.is_playing()
        fallback_finished = now >= self.ending_audio_deadline
        if self.loading_phase is None and (audio_finished or fallback_finished):
            self._start_loading("title", self.show_title)

    def _animate_title_fade(self, now):
        if self.title_fade_started is None or self.fade_item is None:
            return
        progress = min(1.0, (now - self.title_fade_started) / 1.25)
        eased = progress * progress * (3 - 2 * progress)
        self._set_fade_opacity(1.0 - eased)
        if progress >= 1.0:
            self.canvas.delete(self.fade_item)
            self.fade_item = None
            self.title_fade_started = None

    def _animate_title_entry_morph(self, now):
        if self.title_entry_morph_started is None or self.title_entry_logo_item is None:
            return
        progress = min(1.0, (now - self.title_entry_morph_started) / 0.72)
        frame = min(len(self.title_entry_logo_frames) - 1, round(progress * (len(self.title_entry_logo_frames) - 1)))
        if frame != self.title_entry_logo_frame_shown:
            self.canvas.itemconfigure(self.title_entry_logo_item, image=self.title_entry_logo_frames[frame])
            self.title_entry_logo_frame_shown = frame
        self.canvas.tag_raise(self.title_entry_logo_item)
        if progress >= 1.0:
            self.canvas.delete(self.title_entry_logo_item)
            self.title_entry_logo_item = None
            self.title_entry_logo_frames = ()
            self.title_entry_morph_started = None

    def _animate(self):
        if not self.running:
            return
        now = time.monotonic()
        self._poll_events()
        if self.scene != "game":
            self._animate_common(now)
        if self.loading_phase is not None:
            self._animate_loading_transition(now)
            self.root.after(16, self._animate)
            return
        if self.transition_phase is not None:
            self._animate_transition(now)
        elif self.scene == "title":
            self._animate_title_fade(now)
        elif self.scene == "entry":
            self._animate_entry(now)
            self._animate_title_entry_morph(now)
        elif self.scene == "warning":
            self._animate_warning(now)
        elif self.scene == "title_select":
            self._animate_title_select_morph(now)
        elif self.scene == "select":
            self._animate_warning_select_morph(now)
            self._animate_selection_scroll(now)
            remaining = max(0, int(self.select_deadline - now + 0.999))
            self._update_timer(self.select_time_item, remaining, "select_time_shown")
            if now >= self.select_deadline:
                self.show_next()
        elif self.scene == "next":
            self._animate_next(now)
        elif self.scene == "game":
            self._update_game_frame(now)
        elif self.scene == "result":
            self._animate_result(now)
            remaining = max(0, int(self.result_deadline - now + 0.999))
            self._update_timer(self.result_time_item, remaining, "result_time_shown")
            if (
                now >= self.result_deadline
                and self.loading_phase is None
            ):
                self.start_result_transition()
        elif self.scene == "total_result":
            self._animate_total_result(now)
            remaining = max(0, int(self.total_result_deadline - now + 0.999))
            self._update_timer(self.total_result_time_item, remaining, "total_result_time_shown")
            if now >= self.total_result_deadline:
                self.start_total_result_transition()
        elif self.scene == "ending":
            self._animate_ending(now)
        self.root.after(16, self._animate)

    def _consume_serial(self, message):
        self.serial_buffer += message.lower().replace("\r", "").replace("\n", "")
        self.serial_buffer_updated_at = time.monotonic()
        self._drain_serial_buffer()

    def _drain_serial_buffer(self, force=False):
        commands = (self.settings["button_1"], self.settings["button_2"])
        while self.serial_buffer:
            matches = [(self.serial_buffer.find(command), index, command) for index, command in enumerate(commands)]
            matches = [match for match in matches if match[0] >= 0]
            if not matches:
                self.serial_buffer = self.serial_buffer[-max(len(command) for command in commands):]
                return
            position, lane, command = min(matches, key=lambda match: (match[0], -len(match[2])))
            end = position + len(command)
            longer_possible = any(candidate.startswith(command) and len(candidate) > len(command) for candidate in commands)
            if not force and end == len(self.serial_buffer) and longer_possible:
                return
            self.serial_buffer = self.serial_buffer[end:]
            self.press_button(lane)
        self.serial_buffer = self.serial_buffer[-256:]

    def _poll_events(self):
        try:
            while True:
                event = self.event_queue.get_nowait()
                if event[0] == "serial":
                    self.attach_serial(event[1])
                    self._print("serial input ready")
                elif event[0] == "status":
                    self._print(event[1])
        except queue.Empty:
            pass

    def _poll_serial(self):
        if not self.running:
            return
        if self.serial is not None:
            try:
                while self.serial.in_waiting > 0:
                    message = self.serial.read()
                    if message is not None:
                        self._consume_serial(message)
                if self.serial_buffer and time.monotonic() - self.serial_buffer_updated_at >= 0.05:
                    self._drain_serial_buffer(force=True)
            except Exception as error:
                self._print(f"serial read failed: {error}")
                failed_serial = self.serial
                self.serial = None
                try:
                    failed_serial.close()
                except Exception:
                    pass
        self.root.after(25, self._poll_serial)


def run_demo():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument("--progress-file")
    args = parser.parse_args()
    config_path = os.path.join(find_compiled_dir(), "files", "main_conf.ini")
    app = MinigameUI(config_path, fullscreen=not args.windowed, progress_path=args.progress_file)
    app.run()


if __name__ == "__main__":
    run_demo()
