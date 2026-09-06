import os
from collections import deque
from datetime import datetime


class AudioPlayer:
    HITSOUND_CHANNEL_COUNT = 32
    SFX_CHANNEL_COUNT = 16

    def __init__(self):
        self.available = False
        self.current_path = None
        self.sfx_cache = {}
        try:
            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            import pygame

            pygame.mixer.pre_init(44100, -16, 2, 512)
            pygame.mixer.init()
            pygame.mixer.set_num_channels(max(
                pygame.mixer.get_num_channels(),
                self.HITSOUND_CHANNEL_COUNT + self.SFX_CHANNEL_COUNT,
            ))
            pygame.mixer.set_reserved(self.HITSOUND_CHANNEL_COUNT)
            self.hitsound_channels = deque(
                pygame.mixer.Channel(index) for index in range(self.HITSOUND_CHANNEL_COUNT)
            )
            self.pygame = pygame
            self.available = True
            self._print("audio ready")
        except Exception as error:
            self.pygame = None
            self._print(f"audio unavailable: {error}")

    def _print(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [minigame] {message}")

    def play(self, path, loop=False, fade_ms=0, start_seconds=0.0, volume=1.0):
        self.stop()
        if not self.available or not os.path.isfile(path):
            if not os.path.isfile(path):
                self._print(f"audio file missing: {path}")
            return
        try:
            self.pygame.mixer.music.load(path)
            self.pygame.mixer.music.set_volume(min(1.0, max(0.0, float(volume))))
            self.pygame.mixer.music.play(
                -1 if loop else 0, max(0.0, float(start_seconds)), max(0, fade_ms),
            )
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

    def play_sfx(self, path, volume=1.0):
        if not self.available:
            return None
        try:
            if path not in self.sfx_cache:
                if not os.path.isfile(path):
                    self._print(f"sfx file missing: {path}")
                    return None
                self.sfx_cache[path] = self.pygame.mixer.Sound(path)
            sound = self.sfx_cache[path]
            is_hitsound = os.path.basename(path).casefold() == "hitsound.wav"
            if is_hitsound:
                channel = next(
                    (item for item in self.hitsound_channels if not item.get_busy()),
                    self.hitsound_channels[0],
                )
                channel.play(sound)
                self.hitsound_channels.remove(channel)
                self.hitsound_channels.append(channel)
            else:
                channel = sound.play()
            if channel is not None:
                channel.set_volume(min(1.0, max(0.0, float(volume))))
            if not is_hitsound:
                self._print(f"[AudioManager] playing sfx: {os.path.basename(path)}")
            return channel
        except Exception as error:
            self._print(f"[AudioManager] sfx playback failed: {error}")
            return None

    def set_music_volume(self, volume):
        if not self.available:
            return
        try:
            self.pygame.mixer.music.set_volume(min(1.0, max(0.0, float(volume))))
        except Exception:
            pass

    def preload_sfx(self, paths):
        if not self.available:
            return
        loaded = 0
        for path in paths:
            if path in self.sfx_cache or not os.path.isfile(path):
                continue
            try:
                self.sfx_cache[path] = self.pygame.mixer.Sound(path)
                loaded += 1
            except Exception as error:
                self._print(f"[AudioManager] sfx preload failed: {error}")
        self._print(f"[AudioManager] preloaded sfx: {loaded}")

    def is_playing(self):
        if not self.available:
            return False
        try:
            return bool(self.pygame.mixer.music.get_busy())
        except Exception:
            return False

    def position_seconds(self):
        if not self.available:
            return None
        try:
            position = self.pygame.mixer.music.get_pos()
            return position / 1000.0 if position >= 0 else None
        except Exception:
            return None

    def close(self):
        if not self.available:
            return
        try:
            self.pygame.mixer.music.stop()
            self.pygame.mixer.quit()
        except Exception:
            pass
