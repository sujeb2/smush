import os
import time

from PIL import Image, ImageEnhance, ImageOps

from ui_framework import DESIGN_HEIGHT, DESIGN_WIDTH


class MinigameMediaMixin:
    def _track_preview_key(self, track):
        return track.audio_path, track.preview_time, track.video_path, track.background_path

    def _preview_start_seconds(self, track):
        return max(0.0, track.preview_time / 1000.0) if track.preview_time >= 0 else 0.0

    def _schedule_select_preview(self, delay):
        if self.scene != "select":
            return
        self.audio.stop(180)
        self.select_preview_started = False
        self.select_preview_started_at = 0.0
        self.select_preview_deadline = time.monotonic() + delay
        self.select_preview_key = self._track_preview_key(self.track)
        self._prepare_select_media(self.track, reset_video=True)

    def _play_track_preview(self):
        if not self.running or self.scene != "select" or self.select_preview_key != self._track_preview_key(self.track):
            return
        self.select_preview_started = True
        self.audio.play(
            self.track.audio_path, fade_ms=260, start_seconds=self._preview_start_seconds(self.track),
        )
        self.select_preview_started_at = time.monotonic()
        self._seek_select_video(self.track)
        self.select_video_next_frame = self.select_preview_started_at + self.select_video_frame_interval
        self._print(
            f"song preview started: {os.path.basename(self.track.audio_path)} at {max(0, self.track.preview_time)}ms"
        )

    def _selection_media_image(self, image, video):
        image = image.convert("RGB")
        if video:
            image.thumbnail((170, 150), Image.Resampling.LANCZOS)
            frame = Image.new("RGBA", (170, 150), (20, 16, 28, 255))
            frame.paste(image.convert("RGBA"), ((170 - image.width) // 2, (150 - image.height) // 2))
            return frame
        square = ImageOps.fit(image, (150, 150), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        frame = Image.new("RGBA", (170, 150), (0, 0, 0, 0))
        frame.paste(square.convert("RGBA"), (10, 0))
        return frame

    def _set_select_media_frame(self, image, video):
        self.select_media_photo = self._scaled_photo(self._selection_media_image(image, video))
        if self.select_media_item is not None:
            self.canvas.itemconfigure(self.select_media_item, image=self.select_media_photo)

    def _close_select_video(self):
        if self.select_video is not None:
            try:
                self.select_video.release()
            except Exception:
                pass
        self.select_video = None
        self.select_video_cv2 = None

    def _seek_select_video(self, track):
        if self.select_video is None or self.select_video_cv2 is None:
            return False
        offset = max(0, round(self._preview_start_seconds(track) * 1000) - track.video_start_time)
        self.select_video.set(self.select_video_cv2.CAP_PROP_POS_MSEC, offset)
        success, frame = self.select_video.read()
        if success:
            self._set_select_media_frame(Image.fromarray(frame[:, :, ::-1]), True)
        return success

    def _prepare_select_media(self, track, reset_video=False):
        path = track.video_path or track.background_path
        if not path:
            self._close_select_video()
            self.select_media_path = None
            self.select_media_photo = None
            if self.select_media_item is not None:
                self.canvas.itemconfigure(self.select_media_item, image="")
            return
        if path == self.select_media_path and not reset_video and self.select_media_photo is not None:
            return
        self._close_select_video()
        self.select_media_path = path
        self.select_media_photo = None
        if track.video_path:
            try:
                import cv2

                video = cv2.VideoCapture(track.video_path)
                if video.isOpened():
                    self.select_video = video
                    self.select_video_cv2 = cv2
                    fps = video.get(cv2.CAP_PROP_FPS)
                    self.select_video_frame_interval = 1.0 / fps if fps and fps > 0 else 1 / 30
                    if self._seek_select_video(track):
                        return
                    self._close_select_video()
                video.release()
            except Exception as error:
                self._print(f"beatmap video unavailable: {error}")
        fallback = track.background_path
        if fallback:
            cached = self.chart_preview_sources.get(fallback)
            if cached is not None:
                self._set_select_media_frame(cached, False)
                return
            try:
                with Image.open(fallback) as image:
                    self._set_select_media_frame(image.copy(), False)
                return
            except OSError as error:
                self._print(f"beatmap background unavailable: {error}")
        self.select_media_photo = None

    def _animate_select_media(self, now):
        if self.select_video is None or self.select_video_cv2 is None or now < self.select_preview_deadline:
            return
        if now < self.select_video_next_frame:
            return
        audio_elapsed = self.audio.position_seconds()
        if audio_elapsed is None:
            audio_elapsed = max(0.0, now - self.select_preview_started_at)
        desired_position = max(
            0.0,
            (self._preview_start_seconds(self.track) + audio_elapsed) * 1000 - self.track.video_start_time,
        )
        current_position = self.select_video.get(self.select_video_cv2.CAP_PROP_POS_MSEC)
        tolerance = max(80.0, self.select_video_frame_interval * 2000)
        if abs(current_position - desired_position) > tolerance:
            self.select_video.set(self.select_video_cv2.CAP_PROP_POS_MSEC, desired_position)
        success, frame = self.select_video.read()
        if success:
            self._set_select_media_frame(Image.fromarray(frame[:, :, ::-1]), True)
        self.select_video_next_frame += self.select_video_frame_interval
        if self.select_video_next_frame < now:
            self.select_video_next_frame = now + self.select_video_frame_interval

    def _animate_select_preview(self, now):
        if not self.select_preview_started and now >= self.select_preview_deadline:
            self._play_track_preview()
        elif (
            self.select_preview_started
            and self.audio.available
            and now - self.select_preview_started_at >= 0.75
            and not self.audio.is_playing()
        ):
            self._play_track_preview()
        self._animate_select_media(now)

    def _game_media_source(self, image):
        frame = ImageOps.fit(
            image.convert("RGB"), (DESIGN_WIDTH - 80, DESIGN_HEIGHT - 490),
            method=Image.Resampling.BILINEAR, centering=(0.5, 0.5),
        )
        return ImageEnhance.Brightness(frame).enhance(0.52).convert("RGBA")

    def _set_game_media_source(self, source):
        self.game_media_photo = self._scaled_photo(source)
        if self.game_media_item is not None:
            self.canvas.itemconfigure(self.game_media_item, image=self.game_media_photo)

    def _close_game_video(self):
        if self.game_video is not None:
            try:
                self.game_video.release()
            except Exception:
                pass
        self.game_video = None
        self.game_video_cv2 = None

    def _prepare_game_media(self, track):
        self._close_game_video()
        self.game_media_path = track.video_path or track.background_path
        self.game_media_photo = None
        fallback = self.chart_game_sources.get(track.background_path)
        first_frame = self.chart_video_first_frames.get(track.video_path)
        initial_source = fallback if fallback is not None else first_frame
        if initial_source is not None:
            self._set_game_media_source(initial_source)
        if not track.video_path:
            return
        try:
            import cv2

            video = cv2.VideoCapture(track.video_path)
            if not video.isOpened():
                video.release()
                return
            fps = self.chart_video_fps.get(track.video_path) or video.get(cv2.CAP_PROP_FPS) or 30.0
            self.game_video = video
            self.game_video_cv2 = cv2
            self.game_video_frame_interval = 1.0 / min(18.0, max(1.0, fps))
            self.game_video_next_frame = 0.0
        except Exception as error:
            self._print(f"beatmap video unavailable: {error}")

    def _build_game_media(self):
        if self.game_media_photo is None:
            return
        self.game_media_item = self.canvas.create_image(
            self._x(40), self._y(470), image=self.game_media_photo, anchor="nw", tags=("game_bga",),
        )

    def _animate_game_media(self, now):
        if self.game_video is None or self.game_video_cv2 is None or self.game_media_item is None:
            return
        elapsed = self._game_elapsed()
        video_elapsed = elapsed - self.track.video_start_time / 1000.0
        if video_elapsed < 0 or now < self.game_video_next_frame:
            return
        desired_position = video_elapsed * 1000
        current_position = self.game_video.get(self.game_video_cv2.CAP_PROP_POS_MSEC)
        tolerance = max(90.0, self.game_video_frame_interval * 2200)
        if abs(current_position - desired_position) > tolerance:
            self.game_video.set(self.game_video_cv2.CAP_PROP_POS_MSEC, desired_position)
        success, frame = self.game_video.read()
        if success:
            self._set_game_media_source(self._game_media_source(Image.fromarray(frame[:, :, ::-1])))
        self.game_video_next_frame = now + self.game_video_frame_interval
