import configparser
import os
import sys
from datetime import datetime

from game.AnimationFramework import MinigameAnimationMixin
from game.AssetWorker import load_minigame_assets
from game.AudioManager import AudioPlayer
from game.led_runtime import LedRuntimeMixin
from game.gameflow import MinigameFlowMixin
from game.scenes import MinigameGameSceneMixin
from game.gamemanager import MinigameGameplayMixin
from game.mediaplayer import MinigameMediaMixin
from game.persistence import load_event_results, load_event_ranks, load_progress, load_seen_tutorials, save_progress
from game.PreloadManager import MinigamePreloadMixin
from game.rules import (
    BAD_WINDOW,
    CI_CREDITS_SECONDS,
    CI_NOTICE_SECONDS,
    CI_WARNING_SECONDS,
    EVENT_TRACK_COUNT,
    GOOD_WINDOW,
    HEALTH_CHANGE,
    HIT_WINDOW,
    HOLD_TICK_INTERVAL,
    JUDGEMENT_WEIGHT,
    MAX_SCORE,
    PERFECT_WINDOW,
    TEXT_SCALE,
    calculate_catch_score,
    calculate_score,
    combo_after_judgement,
    event_result_destination,
    group_charts_by_song,
    hold_tick_times,
    is_clear,
    smooth_progress,
)
from game.result_scene import MinigameResultSceneMixin
from game.scenemanager import MinigameSceneMixin
from game.settings import MinigameSettingsMixin
from game.state import MinigameStateMixin
from game.osu_chart import discover_osu_supported
from startup_health import clear_previous_error, previous_error_details
from ui_framework import find_compiled_dir
from moderngl_framework import ModernGLUIFramework

class MinigameUI(
    LedRuntimeMixin,
    MinigameStateMixin,
    MinigameSettingsMixin,
    MinigamePreloadMixin,
    MinigameFlowMixin,
    MinigameSceneMixin,
    MinigameGameSceneMixin,
    MinigameResultSceneMixin,
    MinigameGameplayMixin,
    MinigameMediaMixin,
    MinigameAnimationMixin,
    ModernGLUIFramework,
):
    def __init__(self, config_path, fullscreen=True, progress_path=None, test_mode_callback=None, demo_mode=False,
                 station=1, session_dir=None, monitor_geometry=None, borderless=True):
        self.settings = self._load_settings(config_path)
        super().__init__("SMUSH MINIGAME", fullscreen=fullscreen)
        self.station = station
        self.session_dir = session_dir
        self.two_player = session_dir is not None
        if self.two_player:
            self.root.title(f"SMUSH MINIGAME - PLAYER {station}")
        self.rival_scores = (0, 0)
        if monitor_geometry is not None:
            self.root.geometry(monitor_geometry)
            if borderless:
                self.root.overrideredirect(True)
        charts_root = os.path.join(self.base, self.settings["charts_root"])
        self.charts_by_mode, rejected = discover_osu_supported(
            charts_root, self.settings["event_chart_folders"], excluded_folders=("extrastage",),
        )
        self.extra_charts_by_mode, extra_rejected = discover_osu_supported(
            os.path.join(charts_root, "extrastage"), allow_extra=True,
        )
        rejected += extra_rejected
        for path, reason in rejected:
            self._print(f"[ChartManager] chart skipped: {os.path.basename(path)} ({reason})")
        if not any(self.charts_by_mode.values()):
            self.root.destroy()
            raise RuntimeError(f"[ChartManager] No valid 4K or catch chart was found in {charts_root}")
        self.game_mode = next(mode for mode in ("4k", "catch") if self.charts_by_mode[mode])
        self.mode_index = ("4k", "catch").index(self.game_mode)
        self.charts = self.charts_by_mode[self.game_mode]
        self.song_groups = group_charts_by_song(self.charts)
        self.progress_path = progress_path or os.path.join(self.base, self.settings["progress_file"])
        self.track_index = load_progress(self.progress_path, EVENT_TRACK_COUNT)
        self.track_scores, self.track_names = load_event_results(self.progress_path, EVENT_TRACK_COUNT)
        self.track_ranks = load_event_ranks(self.progress_path, EVENT_TRACK_COUNT)
        self.seen_tutorials = load_seen_tutorials(self.progress_path)
        self.extra_stage_active = False
        self.extra_challenge_prompt = False
        self.test_mode_callback = test_mode_callback
        self.coins_per_credit = self.settings["coins_per_credit"]
        self.coin_count = max(0, self.settings["initial_coin_count"])
        self.credit_count = max(0, self.settings["initial_credit_count"])
        if self.coins_per_credit > 0:
            earned, self.coin_count = divmod(self.coin_count, self.coins_per_credit)
            self.credit_count += earned
        self._initialize_state()
        self._initialize_leds(config_path, demo_mode)
        self.recovery_startup = previous_error_details(self.base) is not None
        self.audio = AudioPlayer()
        self.root.bind("<KeyPress>", self._handle_key)
        self.root.after(0, self.show_preload)
        self.root.after(16, self._animate)

    def poll_input(self):
        # Called before scheduled animation/judgement jobs on every frame.
        self._poll_serial()

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
            "button_3": section.get("Button3Message", "Forwarded_3").lower(),
            "button_4": section.get("Button4Message", "Forwarded_4").lower(),
            "coin_message": section.get("CoinMessage", "coin").lower(),
            "coins_per_credit": max(0, int(section.get("CoinsPerCredit", 0))),
            "initial_coin_count": max(0, int(section.get("InitialCoinCount", 0))),
            "initial_credit_count": max(0, int(section.get("InitialCreditCount", 0))),
            "select_seconds": max(1, int(section.get("SelectSeconds", 60))),
            "result_seconds": max(1, int(section.get("ResultSeconds", 20))),
            "arrangement": "NONE",
            "gauge": "GROOVE",
            "scroll_speed": min(3.0, max(0.5, float(section.get("ScrollSpeed", 1.30)))),
        }

    def _load_assets(self):
        self.sources, self.bgm_root, self.sfx_root = load_minigame_assets(self.base)
        self.voice_root = os.path.join(self.bgm_root, "voice")

    def _print(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [minigame] {message}")

    def post_serial(self, serial_io):
        self.event_queue.put(("serial", serial_io))

    def post_status(self, status):
        self.event_queue.put(("status", status))

    def post_serial_failure(self, detail):
        self.event_queue.put(("serial_failure", str(detail)))

    def show_unrecoverable_error(self, code, detail):
        if self.unrecoverable_error:
            return
        self._close_select_video()
        self._close_game_video()
        self.audio.stop()
        super().show_unrecoverable_error(code, detail)

    def close(self):
        if self.two_player:
            self._clear_join_marker()
            try:
                os.unlink(os.path.join(self.session_dir, f"score_{self.station}"))
            except FileNotFoundError:
                pass
        self._close_leds()
        self._close_select_video()
        self._close_game_video()
        self.audio.close()
        super().close()

MINIGAME_PROCESS_FLAG = "--minigame-process"


def minigame_command(*arguments):
    """Command that runs run_demo() in a new process, from source or a frozen build."""
    if "__compiled__" in globals() or getattr(sys, "frozen", False):
        # A frozen executable cannot run `-m`; main.py routes this flag to run_demo().
        return [sys.executable, MINIGAME_PROCESS_FLAG, *arguments]
    return [sys.executable, "-m", "game.minigame", *arguments]


def run_demo():
    import argparse
    import subprocess
    import tempfile
    parser = argparse.ArgumentParser()
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--progress-file")
    parser.add_argument("--players", type=int, choices=(1, 2), default=2)
    parser.add_argument("--station", type=int, choices=(1, 2), default=1)
    parser.add_argument("--session-dir")
    parser.add_argument("--monitor-geometry")
    parser.add_argument("--serial-port")
    args = parser.parse_args()
    windowed = args.windowed or (args.players == 2 and not args.fullscreen)
    if args.players == 2 and args.session_dir is None:
        from game.displays import connected_monitors, station_geometries
        monitors = connected_monitors()
        if not monitors and windowed:
            import tkinter as tk
            probe = tk.Tk()
            probe.withdraw()
            monitors = [(0, 0, probe.winfo_screenwidth(), probe.winfo_screenheight())]
            probe.destroy()
        try:
            geometries = station_geometries(monitors, windowed=windowed)
        except ValueError as error:
            raise SystemExit(str(error)) from error
        with tempfile.TemporaryDirectory(prefix="smush-2p-") as session_dir:
            children = []
            for station, geometry in enumerate(geometries, 1):
                command = minigame_command("--station", str(station),
                                           "--session-dir", session_dir, "--monitor-geometry", geometry)
                if windowed:
                    command.append("--windowed")
                else:
                    command.append("--fullscreen")
                if args.progress_file:
                    command.extend(("--progress-file", args.progress_file))
                port = os.environ.get(f"SMUSH_PLAYER_{station}_PORT")
                if port:
                    command.extend(("--serial-port", port))
                children.append(subprocess.Popen(command, cwd=find_compiled_dir()))
            try:
                for child in children:
                    child.wait()
            finally:
                for child in children:
                    if child.poll() is None:
                        child.terminate()
        return
    config_path = os.path.join(find_compiled_dir(), "files", "main_conf.ini")
    progress_path = args.progress_file
    if args.session_dir:
        if progress_path is None:
            progress_config = configparser.ConfigParser()
            progress_config.read(config_path, encoding="utf-8")
            progress_path = os.path.join(
                find_compiled_dir(), progress_config.get("MINIGAME", "ProgressFile", fallback="game/minigame_progress.json"),
            )
        base_progress = progress_path
        stem, extension = os.path.splitext(base_progress)
        progress_path = f"{stem}_p{args.station}{extension}"
    app = MinigameUI(config_path, fullscreen=not windowed and args.monitor_geometry is None,
                     progress_path=progress_path, demo_mode=args.serial_port is None,
                     station=args.station, session_dir=args.session_dir, monitor_geometry=args.monitor_geometry,
                     borderless=not windowed)
    if args.serial_port:
        from serial_arduino import SerialIO
        import threading
        def connect():
            try:
                serial_config = configparser.ConfigParser()
                serial_config.read(config_path, encoding="utf-8")
                app.post_serial(SerialIO(
                    args.serial_port,
                    serial_config.getint("SERIAL", "SerialBaudrate", fallback=115200),
                    serial_config.getint("SERIAL", "SerialTimeout", fallback=1),
                ))
            except Exception as error:
                app.post_serial_failure(error)
        threading.Thread(target=connect, daemon=True).start()
    app.run()


if __name__ == "__main__":
    run_demo()
