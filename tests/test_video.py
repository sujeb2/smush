import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image

from game.video import VideoFrames
from moderngl_framework import ModernGLCanvas


class VideoTests(unittest.TestCase):
    def test_slow_decoder_does_not_block_requests_or_close(self):
        entered, unblock = threading.Event(), threading.Event()
        capture = Mock()
        capture.get.return_value = 30.0

        def slow_grab():
            entered.set()
            unblock.wait(2)
            return True

        capture.grab.side_effect = slow_grab
        capture.retrieve.return_value = (False, None)
        cv2 = SimpleNamespace(VideoCapture=lambda path: capture, CAP_PROP_FPS=1, CAP_PROP_POS_FRAMES=2)
        with patch.dict("sys.modules", {"cv2": cv2}):
            worker = VideoFrames("test.mp4", lambda frame: frame)
            try:
                worker.request(0)
                self.assertTrue(entered.wait(1))
                worker.request(1)
                worker.request(2)
                self.assertEqual(worker.target, 2)
                self.assertIsNone(worker.take())
                worker.release()
                self.assertTrue(worker.thread.is_alive())
            finally:
                unblock.set()
                worker.release()
                worker.thread.join(2)
            self.assertFalse(worker.thread.is_alive())
            capture.release.assert_called_once()

    def test_video_frames_reuse_one_gpu_texture(self):
        import weakref

        canvas = ModernGLCanvas.__new__(ModernGLCanvas)
        canvas.render_count = 1
        source = Image.new("RGBA", (10, 10))
        texture = Mock()
        canvas.items = {1: SimpleNamespace(image=source)}
        canvas.textures = {id(source): (weakref.ref(source), texture, 0)}
        for _ in range(50):
            frame = Image.new("RGBA", (10, 10))
            canvas.update_video_frame(1, frame, frame.tobytes())
            self.assertEqual(len(canvas.textures), 1)
            self.assertIs(canvas.items[1].image, frame)
        self.assertEqual(texture.write.call_count, 50)
        texture.release.assert_not_called()
