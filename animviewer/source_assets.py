import os
from pathlib import Path

import pygame
from PIL import Image

from game.AssetWorker import load_minigame_assets
from game.gamemanager import MinigameGameplayMixin
from game.mediaplayer import MinigameMediaMixin
from game.osu_chart import OsuChartError, parse_osu_catch, parse_osu_mania
from game.scenemanager import MinigameSceneMixin
from game.scenes import MinigameGameSceneMixin


class ProductionFrameFactory(
    MinigameSceneMixin,
    MinigameGameSceneMixin,
    MinigameGameplayMixin,
    MinigameMediaMixin,
):
    def __init__(self, sources, font_path):
        self.sources = sources
        self.novecento_demibold_font_path = font_path
        self.entry_card_source_frames = {}
        self.entry_cancel_source_frames = ()
        self.warning_source_frames = ()
        self.warning_select_source_frames = ()
        self.warning_mode_source_frames = ()
        self.result_wave_source_frames = {}
        self.rank_reveal_source_frames = {}
        self.result_morph_source_frames = ()
        self.judgement_source_frames = {}
        self.catch_burst_source_frames = ()


class ProductionAssets:
    def __init__(self, project_root, font_path):
        self.project_root = project_root
        self.sources, _, _ = load_minigame_assets(project_root)
        image_root = os.path.join(project_root, "files", "img")
        for name in ("ground_layer", "trash_can", "cans", "can", "plastic_bottle", "update_layer", "error_layer"):
            self.sources[name] = Image.open(os.path.join(image_root, f"{name}.png")).convert("RGBA")
        self.factory = ProductionFrameFactory(self.sources, font_path)
        self.surface_cache = {}
        self.scaled_cache = {}
        self.sequence_cache = {}
        self.video_cache = {}
        self.video_chart = None
        for chart_path in Path(project_root, "game", "charts").rglob("*.osu"):
            chart = None
            for parser in (parse_osu_mania, parse_osu_catch):
                try:
                    chart = parser(str(chart_path))
                    break
                except OsuChartError:
                    continue
            if chart is not None and chart.video_path:
                self.video_chart = chart
                break
        self.video_path = Path(self.video_chart.video_path) if self.video_chart else next(
            Path(project_root, "game", "charts").rglob("*.mp4"), None,
        )
        self.background_path = next(Path(project_root, "game", "charts").rglob("*.jpg"), None)

    def _surface(self, image):
        key = id(image)
        cached = self.surface_cache.get(key)
        if cached is None or cached[0] is not image:
            rgba = image.convert("RGBA")
            cached = image, pygame.image.fromstring(rgba.tobytes(), rgba.size, "RGBA")
            self.surface_cache[key] = cached
        return cached[1]

    def image(self, name):
        return self._surface(self.sources[name])

    def scaled(self, name, size=None, scale=None):
        source = self.image(name)
        if size is None:
            size = (
                max(1, round(source.get_width() * scale)),
                max(1, round(source.get_height() * scale)),
            )
        key = name, tuple(size)
        if key not in self.scaled_cache:
            self.scaled_cache[key] = pygame.transform.smoothscale(source, size)
        return self.scaled_cache[key]

    def fitted(self, name, maximum_size):
        source = self.image(name)
        scale = min(maximum_size[0] / source.get_width(), maximum_size[1] / source.get_height())
        return self.scaled(name, scale=scale)

    def sequence(self, name):
        if name in self.sequence_cache:
            return self.sequence_cache[name]
        methods = {
            "entry": lambda: self.factory._entry_card_sources("entry"),
            "entry_guest": lambda: self.factory._entry_card_sources("entry_guest"),
            "entry_cancel": self.factory._entry_cancel_sources,
            "warning": self.factory._warning_sources,
            "warning_select": self.factory._warning_select_sources,
            "warning_mode": self.factory._warning_mode_sources,
            "clear": lambda: self.factory._result_wave_sources("clear"),
            "failed": lambda: self.factory._result_wave_sources("failed"),
            "result_morph": self.factory._result_morph_sources,
            "rank_s": lambda: self.factory._rank_reveal_sources("rank_s"),
            "perfect": lambda: self.factory._judgement_animation_sources("perfect"),
            "good": lambda: self.factory._judgement_animation_sources("good"),
            "bad": lambda: self.factory._judgement_animation_sources("bad"),
            "miss": lambda: self.factory._judgement_animation_sources("miss"),
            "catch_burst": self.factory._catch_burst_sources,
        }
        self.sequence_cache[name] = tuple(self._surface(frame) for frame in methods[name]())
        return self.sequence_cache[name]

    def video_frame(self, seconds, game=False):
        if self.video_path is None:
            return self.background_frame(game)
        frame_rate = 18 if game else 30
        video_seconds = seconds
        if not game and self.video_chart is not None:
            preview_seconds = max(0.0, self.video_chart.preview_time / 1000.0) if self.video_chart.preview_time >= 0 else 0.0
            video_seconds = max(0.0, preview_seconds + seconds - self.video_chart.video_start_time / 1000.0)
        frame_index = max(0, round(video_seconds * frame_rate))
        key = game, frame_index
        if key in self.video_cache:
            return self.video_cache[key]
        try:
            import cv2

            video = cv2.VideoCapture(str(self.video_path))
            video.set(cv2.CAP_PROP_POS_MSEC, frame_index / frame_rate * 1000)
            success, frame = video.read()
            video.release()
            if not success:
                return self.background_frame(game)
            image = Image.fromarray(frame[:, :, ::-1])
            if game:
                image = self.factory._game_media_source(image)
            else:
                image = self.factory._selection_media_image(image, True)
            self.video_cache[key] = self._surface(image)
            return self.video_cache[key]
        except Exception:
            return self.background_frame(game)

    def background_frame(self, game=False):
        key = "background_game" if game else "background_select"
        if key in self.video_cache:
            return self.video_cache[key]
        if self.background_path is None:
            return None
        with Image.open(self.background_path) as source:
            image = self.factory._game_media_source(source) if game else self.factory._selection_media_image(source, False)
        self.video_cache[key] = self._surface(image)
        return self.video_cache[key]
