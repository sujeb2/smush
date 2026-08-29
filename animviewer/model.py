import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Keyframe:
    time: float
    name: str


@dataclass(frozen=True)
class AnimationSpec:
    group: str
    name: str
    duration: float
    fps: int
    style: str
    keyframes: tuple
    variant: str = ""

    @property
    def last_frame(self):
        return max(0, round(self.duration * self.fps) - 1)


class PlaybackController:
    def __init__(self):
        self.animation = None
        self.state = "stopped"
        self.current_time = 0.0
        self.updated_at = None

    def select(self, animation):
        self.animation = animation
        self.stop()

    def play(self, now=None):
        if self.animation is None:
            return
        if self.current_time >= self.animation.duration:
            self.current_time = 0.0
        self.state = "playing"
        self.updated_at = time.perf_counter() if now is None else now

    def pause(self, now=None):
        self.update(now)
        if self.animation is not None:
            self.state = "paused"
        self.updated_at = None

    def toggle(self, now=None):
        if self.state == "playing":
            self.pause(now)
        else:
            self.play(now)

    def stop(self):
        self.state = "stopped"
        self.current_time = 0.0
        self.updated_at = None

    def update(self, now=None):
        if self.animation is None or self.state != "playing":
            return
        now = time.perf_counter() if now is None else now
        if self.updated_at is None:
            self.updated_at = now
            return
        self.current_time += max(0.0, now - self.updated_at)
        self.updated_at = now
        if self.current_time >= self.animation.duration:
            self.current_time = self.animation.duration
            self.state = "paused"
            self.updated_at = None

    def seek(self, seconds, now=None):
        if self.animation is None:
            return
        self.current_time = min(self.animation.duration, max(0.0, seconds))
        if self.state == "playing":
            self.updated_at = time.perf_counter() if now is None else now

    def seek_frame(self, frame, now=None):
        if self.animation is not None:
            self.seek(frame / self.animation.fps, now)

    @property
    def current_frame(self):
        if self.animation is None:
            return 0
        return min(self.animation.last_frame, int(self.current_time * self.animation.fps))

    @property
    def active_keyframe(self):
        if self.animation is None or not self.animation.keyframes:
            return None
        active = self.animation.keyframes[0]
        for keyframe in self.animation.keyframes:
            if keyframe.time > self.current_time:
                break
            active = keyframe
        return active
