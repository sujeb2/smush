import argparse
import os
import time
from datetime import datetime

import pygame
from PIL import Image

from animviewer.animations import BLACK, CATALOG, DARK_GRAY, GRAY, GREEN, WHITE, PreviewRenderer
from animviewer.model import PlaybackController
from animviewer.source_assets import ProductionAssets
from animviewer.text import SurfaceFont


DESIGN_WIDTH = 1920
DESIGN_HEIGHT = 1080
TITLE_POSITION = (91, 82)
SIDEBAR_POSITION = (89, 164)
VIEWER_POSITION = (519, 164)
SIDEBAR_VIEW = pygame.Rect(108, 188, 385, 825)
PREVIEW_AREA = pygame.Rect(550, 205, 1295, 665)
TIMELINE_RECT = pygame.Rect(630, 936, 1168, 50)
PLAY_RECT = pygame.Rect(548, 928, 56, 62)
STOP_RECT = pygame.Rect(608, 947, 24, 24)


def format_time(seconds):
    seconds = max(0.0, seconds)
    minutes = int(seconds // 60)
    return f"{minutes}:{seconds % 60:05.2f}"


class AnimationViewer:
    def __init__(self, fullscreen=False, window_size=(1280, 720)):
        pygame.display.init()
        flags = pygame.RESIZABLE
        if fullscreen:
            flags |= pygame.FULLSCREEN
            window_size = (0, 0)
        self.window = pygame.display.set_mode(window_size, flags)
        pygame.display.set_caption("SMUSH ANIMATION VIEWER")
        self.running = True
        self.clock = pygame.time.Clock()
        self.base = os.path.dirname(os.path.abspath(__file__))
        self.assets_path = os.path.join(self.base, "assets")
        self.assets = self._load_assets()
        self.font_path = os.path.join(self.assets_path, "Novecentosanswide-DemiBold.otf")
        self.font = SurfaceFont(self.font_path, 18)
        self.small_font = SurfaceFont(self.font_path, 15)
        self.sidebar_font = SurfaceFont(self.font_path, 17)
        self.sidebar_group_font = SurfaceFont(self.font_path, 15)
        self.production_assets = ProductionAssets(os.path.dirname(self.base), self.font_path)
        self.renderer = PreviewRenderer(self.font_path, self.production_assets)
        self.player = PlaybackController()
        self.selected_index = None
        self.sidebar_scroll = 0
        self.sidebar_content_height = 0
        self.sidebar_items = []
        self.preview_failed = False
        self.frame = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT), pygame.SRCALPHA)
        self.chrome = self._build_chrome()
        self.fps = 0.0
        self.fps_updated_at = 0.0
        self._print(f"animation viewer visible, animations: {len(CATALOG)}")

    def _print(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [animviewer] {message}")

    def _load_assets(self):
        names = (
            "bg", "title", "sidebar_bg", "viewer_back",
            "no_animation_selected", "animation_not_found",
        )
        assets = {}
        for name in names:
            with Image.open(os.path.join(self.assets_path, f"{name}.png")) as source:
                image = source.convert("RGBA")
            assets[name] = pygame.image.fromstring(image.tobytes(), image.size, "RGBA")
        return assets

    def _build_chrome(self):
        chrome = self.assets["bg"].copy()
        chrome.blit(self.assets["title"], TITLE_POSITION)
        chrome.blit(self.assets["sidebar_bg"], SIDEBAR_POSITION)
        chrome.blit(self.assets["viewer_back"], VIEWER_POSITION)
        return chrome

    def _blit_center(self, source, center, alpha=255):
        if alpha != 255:
            source = source.copy()
            source.set_alpha(alpha)
        self.frame.blit(source, source.get_rect(center=center))

    def _draw_text(self, value, font, position, color=WHITE, anchor="topleft"):
        image = font.render(value, True, color)
        rect = image.get_rect()
        setattr(rect, anchor, position)
        self.frame.blit(image, rect)

    def _sidebar_layout(self):
        rows = []
        y = 12
        group = None
        for index, animation in enumerate(CATALOG):
            if animation.group != group:
                if group is not None:
                    y += 12
                rows.append(("group", animation.group, None, y, 28))
                y += 28
                group = animation.group
            rows.append(("animation", animation.name, index, y, 39))
            y += 39
        self.sidebar_content_height = y + 12
        return rows

    def _draw_sidebar(self):
        panel = pygame.Surface(SIDEBAR_VIEW.size, pygame.SRCALPHA)
        self.sidebar_items = []
        rows = self._sidebar_layout()
        max_scroll = max(0, self.sidebar_content_height - SIDEBAR_VIEW.height)
        self.sidebar_scroll = min(max_scroll, max(0, self.sidebar_scroll))
        for kind, label, index, y, height in rows:
            local_y = y - self.sidebar_scroll
            if local_y + height < 0 or local_y > SIDEBAR_VIEW.height:
                continue
            if kind == "group":
                image = self.sidebar_group_font.render(label, True, GRAY)
                panel.blit(image, (14, local_y + 5))
                pygame.draw.line(panel, DARK_GRAY, (14, local_y + 25), (365, local_y + 25), 1)
                continue
            rect = pygame.Rect(6, local_y, 371, height - 3)
            if index == self.selected_index:
                pygame.draw.rect(panel, DARK_GRAY, rect, border_radius=7)
                pygame.draw.rect(panel, GREEN, (rect.left, rect.top, 4, rect.height), border_radius=2)
            color = WHITE if index == self.selected_index else GRAY
            image = self.sidebar_font.render(label, True, color)
            if image.get_width() > 338:
                ratio = 338 / image.get_width()
                image = pygame.transform.smoothscale(image, (338, max(1, round(image.get_height() * ratio))))
            panel.blit(image, image.get_rect(midleft=(20, local_y + (height - 3) / 2)))
            self.sidebar_items.append((pygame.Rect(SIDEBAR_VIEW.left + rect.left, SIDEBAR_VIEW.top + rect.top, rect.width, rect.height), index))
        if max_scroll:
            track = pygame.Rect(panel.get_width() - 7, 10, 3, panel.get_height() - 20)
            thumb_height = max(42, round(track.height * panel.get_height() / self.sidebar_content_height))
            thumb_y = track.top + round((track.height - thumb_height) * self.sidebar_scroll / max_scroll)
            pygame.draw.rect(panel, DARK_GRAY, track, border_radius=2)
            pygame.draw.rect(panel, GRAY, (track.left, thumb_y, track.width, thumb_height), border_radius=2)
        self.frame.blit(panel, SIDEBAR_VIEW)

    def _draw_empty_preview(self):
        self._blit_center(self.assets["no_animation_selected"], (1197, 585), 150)

    def _draw_failed_preview(self):
        self._blit_center(self.assets["animation_not_found"], (1197, 585), 150)

    def _draw_preview(self):
        if self.player.animation is None:
            self._draw_empty_preview()
            return
        if self.preview_failed:
            self._draw_failed_preview()
            return
        try:
            self.renderer.draw(self.frame, self.player.animation, self.player.current_time, PREVIEW_AREA)
        except Exception as error:
            self.preview_failed = True
            self._print(f"animation preview failed: {error}")
            self._draw_failed_preview()

    def _draw_stats(self):
        current_frame = self.player.current_frame
        last_frame = self.player.animation.last_frame if self.player.animation is not None else 0
        lines = (
            f"FPS: {round(self.fps)}",
            f"CURRENT FRAME: {current_frame}",
            f"LAST FRAME: {last_frame}",
        )
        for index, line in enumerate(lines):
            self._draw_text(line, self.small_font, (1838, 198 + index * 27), WHITE, "topright")

    def _draw_transport(self):
        duration = self.player.animation.duration if self.player.animation is not None else 0.0
        progress = self.player.current_time / duration if duration else 0.0
        self._draw_text(
            f"{format_time(self.player.current_time)} / {format_time(duration)}",
            self.small_font, (630, 902), WHITE,
        )
        keyframe = self.player.active_keyframe
        if keyframe is not None:
            self._draw_text(f"KEYFRAME: {keyframe.name}", self.small_font, (1798, 902), GRAY, "topright")
        pygame.draw.rect(self.frame, BLACK, TIMELINE_RECT, border_radius=7)
        if progress > 0:
            progress_rect = pygame.Rect(TIMELINE_RECT.left, TIMELINE_RECT.top, round(TIMELINE_RECT.width * progress), TIMELINE_RECT.height)
            pygame.draw.rect(self.frame, GREEN, progress_rect, border_radius=7)
        if self.player.animation is not None:
            for marker in self.player.animation.keyframes:
                x = TIMELINE_RECT.left + round(TIMELINE_RECT.width * marker.time / duration)
                active = marker.time <= self.player.current_time
                color = WHITE if active else GRAY
                points = ((x, TIMELINE_RECT.top + 7), (x + 6, TIMELINE_RECT.top + 13), (x, TIMELINE_RECT.top + 19), (x - 6, TIMELINE_RECT.top + 13))
                pygame.draw.polygon(self.frame, color, points)
        if self.player.state == "playing":
            pygame.draw.rect(self.frame, GREEN, (558, 941, 12, 39), border_radius=3)
            pygame.draw.rect(self.frame, GREEN, (579, 941, 12, 39), border_radius=3)
        else:
            pygame.draw.polygon(self.frame, GREEN, ((562, 938), (562, 984), (601, 961)))
        pygame.draw.rect(self.frame, GRAY if self.player.animation is None else WHITE, STOP_RECT, border_radius=3)

    def _draw(self):
        self.frame.blit(self.chrome, (0, 0))
        self._draw_sidebar()
        self._draw_preview()
        self._draw_stats()
        self._draw_transport()

    def _present(self):
        window_width, window_height = self.window.get_size()
        scale = min(window_width / DESIGN_WIDTH, window_height / DESIGN_HEIGHT)
        width = max(1, round(DESIGN_WIDTH * scale))
        height = max(1, round(DESIGN_HEIGHT * scale))
        output = pygame.transform.smoothscale(self.frame, (width, height))
        self.window.fill(BLACK)
        self.window.blit(output, ((window_width - width) // 2, (window_height - height) // 2))
        pygame.display.flip()

    def _design_position(self, position):
        window_width, window_height = self.window.get_size()
        scale = min(window_width / DESIGN_WIDTH, window_height / DESIGN_HEIGHT)
        offset_x = (window_width - DESIGN_WIDTH * scale) / 2
        offset_y = (window_height - DESIGN_HEIGHT * scale) / 2
        return (position[0] - offset_x) / scale, (position[1] - offset_y) / scale

    def _select(self, index):
        if index < 0 or index >= len(CATALOG):
            return
        self.selected_index = index
        self.preview_failed = False
        self.player.select(CATALOG[index])
        self._print(f"animation selected: {CATALOG[index].group} - {CATALOG[index].name}")

    def _handle_click(self, event):
        position = self._design_position(event.pos)
        if event.button == 1:
            for rect, index in self.sidebar_items:
                if rect.collidepoint(position):
                    self._select(index)
                    return
            if PLAY_RECT.collidepoint(position):
                self.player.toggle()
                return
            if STOP_RECT.inflate(12, 12).collidepoint(position):
                self.player.stop()
                return
            if TIMELINE_RECT.collidepoint(position) and self.player.animation is not None:
                progress = (position[0] - TIMELINE_RECT.left) / TIMELINE_RECT.width
                self.player.seek(progress * self.player.animation.duration)

    def _handle_key(self, event):
        if event.key == pygame.K_ESCAPE:
            self.running = False
        elif event.key == pygame.K_SPACE:
            self.player.toggle()
        elif event.key in (pygame.K_s, pygame.K_HOME):
            self.player.stop()
        elif event.key == pygame.K_END and self.player.animation is not None:
            self.player.seek(self.player.animation.duration)
        elif event.key == pygame.K_LEFT:
            self.player.pause()
            self.player.seek_frame(self.player.current_frame - 1)
        elif event.key == pygame.K_RIGHT:
            self.player.pause()
            self.player.seek_frame(self.player.current_frame + 1)
        elif event.key == pygame.K_UP and self.selected_index is not None:
            self._select(max(0, self.selected_index - 1))
        elif event.key == pygame.K_DOWN:
            self._select(0 if self.selected_index is None else min(len(CATALOG) - 1, self.selected_index + 1))

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self._handle_key(event)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self._handle_click(event)
            elif event.type == pygame.MOUSEWHEEL:
                position = self._design_position(pygame.mouse.get_pos())
                if SIDEBAR_VIEW.collidepoint(position):
                    self.sidebar_scroll -= event.y * 78

    def run(self):
        try:
            while self.running:
                self._handle_events()
                self.player.update()
                now = time.perf_counter()
                if now - self.fps_updated_at >= .25:
                    self.fps = self.clock.get_fps()
                    self.fps_updated_at = now
                self._draw()
                self._present()
                self.clock.tick(60)
        finally:
            pygame.quit()


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()
    app = AnimationViewer(fullscreen=args.fullscreen, window_size=(max(640, args.width), max(360, args.height)))
    app.run()
