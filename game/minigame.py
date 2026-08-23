import configparser
import os
from datetime import datetime

from game.AnimationFramework import MinigameAnimationMixin
from game.AssetWorker import load_minigame_assets
from game.AudioManager import AudioPlayer
from game.gameflow import MinigameFlowMixin
from game.scenes import MinigameGameSceneMixin
from game.gamemanager import MinigameGameplayMixin
from game.mediaplayer import MinigameMediaMixin
from game.persistence import load_event_results, load_progress, save_progress
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
from game.state import MinigameStateMixin
from game.osu_chart import discover_osu_supported
from ui_framework import CanvasUIFramework, find_compiled_dir

class MinigameUI(
    MinigameStateMixin,
    MinigamePreloadMixin,
    MinigameFlowMixin,
    MinigameSceneMixin,
    MinigameGameSceneMixin,
    MinigameResultSceneMixin,
    MinigameGameplayMixin,
    MinigameMediaMixin,
    MinigameAnimationMixin,
    CanvasUIFramework,
):
    def __init__(self, config_path, fullscreen=True, progress_path=None):
        self.settings = self._load_settings(config_path)
        super().__init__("SMUSH MINIGAME", fullscreen=fullscreen)
        charts_root = os.path.join(self.base, self.settings["charts_root"])
        self.charts_by_mode, rejected = discover_osu_supported(charts_root, self.settings["event_chart_folders"])
        for path, reason in rejected:
            self._print(f"[ChartManager] chart skipped: {os.path.basename(path)} ({reason})")
        if not any(self.charts_by_mode.values()):
            self.root.destroy()
            raise RuntimeError(f"[ChartManager] No valid 2K or catch chart was found in {charts_root}")
        self.game_mode = "2k" if self.charts_by_mode["2k"] else "catch"
        self.mode_index = 0 if self.game_mode == "2k" else 1
        self.charts = self.charts_by_mode[self.game_mode]
        self.song_groups = group_charts_by_song(self.charts)
        self.progress_path = progress_path or os.path.join(self.base, self.settings["progress_file"])
        self.track_index = load_progress(self.progress_path, EVENT_TRACK_COUNT)
        self.track_scores, self.track_names = load_event_results(self.progress_path, EVENT_TRACK_COUNT)
        self._initialize_state()
        self.audio = AudioPlayer()
        self.root.bind("<KeyPress>", self._handle_key)
        self.root.after(0, self.show_preload)
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
        self.sources, self.bgm_root, self.sfx_root = load_minigame_assets(self.base)

    def _print(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [minigame] {message}")

    def post_serial(self, serial_io):
        self.event_queue.put(("serial", serial_io))

    def post_status(self, status):
        self.event_queue.put(("status", status))

    def close(self):
        self._close_select_video()
        self._close_game_video()
        self.audio.close()
        super().close()

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
