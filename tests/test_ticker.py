import pathlib
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from game.ticker import song_label, ticker_message, ticker_text
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
