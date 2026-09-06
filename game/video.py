import math
import threading

from PIL import Image


class VideoFrames:
    def __init__(self, path, transform):
        self.path = path
        self.transform = transform
        self.condition = threading.Condition()
        self.target = None
        self.ready = None
        self.closed = False
        self.error = None
        self.thread = threading.Thread(target=self._run, daemon=True, name="smush-bga")
        self.thread.start()

    def request(self, seconds):
        with self.condition:
            self.target = max(0.0, seconds)
            self.condition.notify()

    def take(self):
        with self.condition:
            frame, self.ready = self.ready, None
            return frame

    def release(self):
        with self.condition:
            self.closed = True
            self.ready = None
            self.condition.notify()

    def _run(self):
        capture = None
        try:
            import cv2

            capture = cv2.VideoCapture(self.path)
            if not capture.isOpened():
                raise RuntimeError(f"cannot open {self.path}")
            fps = capture.get(cv2.CAP_PROP_FPS)
            if not math.isfinite(fps) or fps <= 0:
                fps = 30.0
            index = -1
            while True:
                with self.condition:
                    self.condition.wait_for(lambda: self.closed or self.target is not None)
                    if self.closed:
                        return
                    seconds, self.target = self.target, None
                target_index = int(seconds * fps)
                if target_index == index:
                    continue
                if target_index < index or target_index - index > max(1, int(fps)):
                    capture.set(cv2.CAP_PROP_POS_FRAMES, target_index)
                    index = target_index - 1
                success = False
                while index < target_index:
                    if self.closed:
                        return
                    success = capture.grab()
                    if not success:
                        break
                    index += 1
                if not success:
                    continue
                success, frame = capture.retrieve()
                if not success:
                    continue
                source = self.transform(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
                pixels = source.tobytes()
                with self.condition:
                    if self.closed:
                        return
                    self.ready = (source, pixels)
        except Exception as error:
            self.error = str(error)
        finally:
            if capture is not None:
                capture.release()
