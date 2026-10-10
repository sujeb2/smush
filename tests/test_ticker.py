import pathlib
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import re

from game.ticker import FONT, TickerRuntimeMixin, render_preview, song_label, ticker_frame, ticker_message, ticker_text
from serial_arduino import SerialIO


def track(title="19ZZ", artist="Frums", title_ascii="", artist_ascii=""):
    return SimpleNamespace(title=title, artist=artist, title_ascii=title_ascii, artist_ascii=artist_ascii)


def app(scene, **values):
    return SimpleNamespace(scene=scene, track=values.pop("track", track()), unrecoverable_error=None, **values)


class TickerTextTests(unittest.TestCase):
    def test_text_is_folded_to_the_firmware_font(self):
        self.assertEqual(ticker_text("  Hello,\tworld~ "), "HELLO, WORLD")
        self.assertEqual(ticker_text("x" * 80), "X" * 48)

    def test_song_label_prefers_romanised_metadata(self):
        self.assertEqual(song_label(track("夜に駆ける", "YOASOBI", "Yoru ni Kakeru")), "YORU NI KAKERU / YOASOBI")
        self.assertEqual(song_label(track("夜に駆ける", "ヨアソビ")), "NOW PLAYING")

    def test_scene_messages(self):
        self.assertEqual(ticker_message(app("preload")), ("LOAD", True))
        self.assertEqual(ticker_message(app("title", coins_per_credit=1, credit_count=0)),
                         ("WELCOME TO SMUSH CITRADE INSERT COIN", False))
        self.assertEqual(ticker_message(app("select")), ("19ZZ / FRUMS", False))
        self.assertEqual(ticker_message(app("next", track_index=1)), ("STAGE 2 19ZZ / FRUMS", False))
        self.assertEqual(ticker_message(app("next", track_index=2, extra_stage_active=True)),
                         ("EXTRA STAGE 19ZZ / FRUMS", False))
        self.assertEqual(ticker_message(app("result", rank="AA", score=987654)),
                         ("RANK AA SCORE 987654", False))
        failed = app("game")
        failed.unrecoverable_error = True
        self.assertEqual(ticker_message(failed), ("ERR", True))

    def test_serial_command(self):
        with patch("serial_arduino.serial.Serial") as serial_class:
            port = serial_class.return_value
            port.is_open = True
            serial_io = SerialIO("TEST", 9600, timeout=1)
            serial_io.set_ticker("LOAD", blink=True)
            port.write.assert_called_once_with(b"TICK:B:LOAD\n")
            with self.assertRaises(ValueError):
                serial_io.set_ticker("夜")


class TickerPreviewTests(unittest.TestCase):
    def test_font_matches_firmware(self):
        sketch = pathlib.Path(__file__).resolve().parents[1] / "hardware/arduino/boardio/boardio.ino"
        table = re.search(r"TICKER_FONT\[64\] PROGMEM = \{(.*?)\};", sketch.read_text(), re.S).group(1)
        self.assertEqual(tuple(int(value, 16) for value in re.findall(r"0x[0-9A-F]{2}", table)), FONT)

    def test_frames_follow_firmware_timing(self):
        self.assertEqual(ticker_frame("HI", False, 0), (0, 0x76, 0x30, 0))
        self.assertEqual(ticker_frame("ABCDE", False, 0), (0, 0, 0, 0))
        self.assertEqual(ticker_frame("ABCDE", False, 0.28), (0, 0, 0, 0x77))
        self.assertEqual(ticker_frame("abcde", False, 0.28 * 5), (0x7C, 0x39, 0x5E, 0x79))
        self.assertEqual(ticker_frame("ERR", True, 0.2), (0x79, 0x50, 0x50, 0))
        self.assertEqual(ticker_frame("ERR", True, 0.7), (0, 0, 0, 0))

    def test_preview_lights_only_requested_segments(self):
        image = render_preview((0x01, 0x40, 0, 0x7F))
        lit = (255, 48, 32, 255)
        self.assertEqual(image.getpixel((48 + 36, 14)), lit)  # digit 1, segment A
        self.assertNotEqual(image.getpixel((48 + 36, 74)), lit)  # digit 1, segment G
        self.assertEqual(image.getpixel((156 + 36, 74)), lit)  # digit 2, segment G
        self.assertNotEqual(image.getpixel((264 + 36, 74)), lit)  # digit 3 is blank

    def test_demo_preview_follows_led_toggle_and_keeps_scroll_on_resend(self):
        class Runtime(TickerRuntimeMixin):
            pass

        runtime = Runtime()
        runtime.root, runtime.canvas = Mock(), Mock()
        runtime.canvas.coords.return_value = [540, 570]
        runtime._x = runtime._y = lambda value: value
        runtime.running, runtime.unrecoverable_error = True, None
        runtime.demo_mode, runtime.serial, runtime.led_preview_visible = True, None, False
        runtime.scene, runtime.track = "title", track()
        with patch("game.ticker.time.monotonic", return_value=100.0):
            runtime._initialize_ticker()
            runtime._tick_ticker()
        runtime.canvas.create_image.assert_not_called()
        runtime.led_preview_visible = True
        with patch("game.ticker.time.monotonic", return_value=100.28):
            runtime._tick_ticker()
        self.assertEqual(runtime.ticker_preview_frame, (0, 0, 0, FONT[ord("W") - 0x20]))
        runtime.canvas.create_image.assert_called_once()
        self.assertEqual(runtime.canvas.create_image.call_args.kwargs["tags"], ("ticker_preview",))
        with patch("game.ticker.time.monotonic", return_value=100.29):
            runtime._tick_ticker()  # Same frame: no redraw.
        runtime.canvas.create_image.assert_called_once()
        runtime.led_preview_visible = False
        runtime._tick_ticker()
        runtime.canvas.delete.assert_called_with("ticker_preview")
        self.assertIsNone(runtime.ticker_preview_frame)


class BoardIOTickerFirmwareTests(unittest.TestCase):
    def test_scroll_center_blink_and_resend(self):
        compiler = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
        if compiler is None:
            self.skipTest("C++ compiler unavailable for firmware simulation")
        sketch = pathlib.Path(__file__).resolve().parents[1] / "hardware/arduino/boardio/boardio.ino"
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "Adafruit_NeoPixel.h").write_text(r'''
#pragma once
#define NEO_GRB 0
#define NEO_KHZ800 0
class Adafruit_NeoPixel {
public:
  Adafruit_NeoPixel(int, int, int) {}
  void begin() {} void clear() {} void show() {}
  void setPixelColor(int, int, int, int) {}
};
''')
            (root / "TM1637Display.h").write_text(r'''
#pragma once
#include <cstdint>
#include <cstring>
struct TM1637Display {
  uint8_t shown[4] = {}; int writes = 0;
  TM1637Display(int, int, unsigned int) {}
  void setBrightness(int) {}
  void setSegments(const uint8_t *s) { memcpy(shown, s, 4); ++writes; }
};
''')
            (root / "test.cpp").write_text(r'''
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
using byte = unsigned char;
#define PROGMEM
#define pgm_read_byte(address) (*(address))
constexpr int LOW = 0, HIGH = 1, INPUT = 0, INPUT_PULLUP = 2, A5 = 19;
unsigned long clockMs = 0;
int pins[20];
unsigned long millis() { return clockMs; }
void pinMode(int, int) {}
int digitalRead(int pin) { return pins[pin]; }
struct SerialStub {
  std::string input; std::vector<std::string> messages;
  void begin(unsigned long) {}
  int available() { return input.size(); }
  char read() { char c = input.front(); input.erase(0, 1); return c; }
  void println(const char *m) { messages.emplace_back(m); }
} Serial;
#include "boardio.ino"
void step(unsigned long time, const std::string &input = "") { clockMs = time; Serial.input += input; loop(); }
bool shows(uint8_t a, uint8_t b, uint8_t c, uint8_t d) {
  const uint8_t expected[4] = {a, b, c, d};
  return memcmp(ticker.shown, expected, 4) == 0;
}
int main() {
  for (auto &pin : pins) pin = HIGH;
  setup();
  step(1000, "TICK:S:HI\n");
  assert(shows(0, 0x76, 0x30, 0)); // Centered: H I
  step(1000, "TICK:S:ABCDE\n");
  assert(shows(0, 0, 0, 0)); // Long text starts off-screen.
  step(1280); assert(shows(0, 0, 0, 0x77)); // A enters from the right.
  step(1000 + 280 * 4); assert(shows(0x77, 0x7C, 0x39, 0x5E));
  step(1000 + 280 * 5); assert(shows(0x7C, 0x39, 0x5E, 0x79));
  const int writes = ticker.writes;
  step(1000 + 280 * 5 + 10, "TICK:S:abcde\n"); // Lowercase is a different string: restarts.
  assert(shows(0, 0, 0, 0));
  step(2410 + 280 * 4, "TICK:S:abcde\n"); // Identical resend keeps scrolling position.
  assert(ticker.writes > writes && shows(0x77, 0x7C, 0x39, 0x5E));
  step(4000, "TICK:B:ERR\n"); assert(shows(0x79, 0x50, 0x50, 0));
  step(4500); assert(shows(0, 0, 0, 0));
  step(5000); assert(shows(0x79, 0x50, 0x50, 0));
  step(5100, "TICK:X:BAD\n"); assert(shows(0x79, 0x50, 0x50, 0)); // Unknown mode is ignored.
  pins[2] = LOW; step(5200); // Buttons still report while the ticker runs.
  assert(Serial.messages.back() == "Forwarded");
}
''')
            executable = root / "firmware-test"
            subprocess.run([compiler, "-std=c++11", "-I", str(root), "-I", str(sketch.parent),
                            str(root / "test.cpp"), "-o", str(executable)],
                           check=True, capture_output=True, text=True)
            result = subprocess.run([str(executable)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
