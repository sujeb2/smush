import pathlib
import shutil
import subprocess
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import re

from game.ticker import (FONT, TickerRuntimeMixin, render_preview, song_label, ticker_frame, ticker_message,
                         ticker_port, ticker_text)
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


SKETCH = pathlib.Path(__file__).resolve().parents[1] / "hardware/arduino/ticker/ticker.ino"


def columns(text):
    return tuple(FONT[(ord(c) - 0x20) * 5 + i] if i < 5 else 0 for c in text for i in range(6))[:-1]


class TickerPreviewTests(unittest.TestCase):
    def test_font_matches_firmware(self):
        table = re.search(r"TICKER_FONT\[64 \* GLYPH_WIDTH\] PROGMEM = \{(.*?)\};", SKETCH.read_text(), re.S).group(1)
        self.assertEqual(tuple(int(value, 16) for value in re.findall(r"0x[0-9A-F]{2}", table)), FONT)

    def test_frames_center_scroll_and_blink(self):
        self.assertEqual(ticker_frame("HI", False, 0), (0,) * 10 + columns("HI") + (0,) * 11)
        self.assertEqual(ticker_frame("SMUSH", False, 0), (0,) * 1 + columns("SMUSH") + (0,) * 2)
        self.assertEqual(ticker_frame("WELCOME", False, 0), (0,) * 32)
        self.assertEqual(ticker_frame("welcome", False, 0.035), (0,) * 31 + columns("W")[:1])
        self.assertEqual(ticker_frame("WELCOME", False, 0.035 * 32), columns("WELCOME")[:32])
        self.assertEqual(ticker_frame("WELCOME", False, 0.035 * (41 + 32)), (0,) * 32)
        self.assertEqual(ticker_frame("ERR", True, 0.7), (0,) * 32)
        self.assertEqual(ticker_frame("", False, 0), (0,) * 32)

    def test_preview_lights_only_requested_dots(self):
        image = render_preview((0x01,) + (0,) * 7 + (0x80,) + (0,) * 23)
        lit = (255, 48, 32, 255)
        self.assertEqual(image.getpixel((21, 19)), lit)  # column 0, top row
        self.assertNotEqual(image.getpixel((21, 32)), lit)  # column 0, second row
        self.assertEqual(image.getpixel((16 + 8 * 13 + 8 + 5, 14 + 7 * 13 + 5)), lit)  # module 2, bottom row
        self.assertNotEqual(image.getpixel((16 + 13 + 5, 19)), lit)

    def runtime(self):
        class Runtime(TickerRuntimeMixin):
            pass

        runtime = Runtime()
        runtime.root, runtime.canvas = Mock(), Mock()
        runtime.canvas.coords.return_value = [540, 570]
        runtime._x = runtime._y = lambda value: value
        runtime._print = Mock()
        runtime.running, runtime.unrecoverable_error = True, None
        runtime.demo_mode, runtime.led_preview_visible, runtime.station = True, False, 1
        runtime.scene, runtime.track = "title", track()
        return runtime

    def test_demo_preview_follows_led_toggle_and_keeps_scroll_on_resend(self):
        runtime = self.runtime()
        with patch("game.ticker.time.monotonic", return_value=100.0):
            runtime._initialize_ticker("missing.ini")
            runtime._tick_ticker()
        runtime.canvas.create_image.assert_not_called()
        runtime.led_preview_visible = True
        with patch("game.ticker.time.monotonic", return_value=100.035):
            runtime._tick_ticker()
        self.assertEqual(runtime.ticker_preview_frame, (0,) * 31 + columns("W")[:1])
        runtime.canvas.create_image.assert_called_once()
        self.assertEqual(runtime.canvas.create_image.call_args.kwargs["tags"], ("ticker_preview",))
        with patch("game.ticker.time.monotonic", return_value=100.036):
            runtime._tick_ticker()  # Same frame: no redraw.
        runtime.canvas.create_image.assert_called_once()
        runtime.led_preview_visible = False
        runtime._tick_ticker()
        runtime.canvas.delete.assert_called_with("ticker_preview")
        self.assertIsNone(runtime.ticker_preview_frame)

    def test_ticker_port_from_environment_or_config_and_only_station_one_connects(self):
        with tempfile.TemporaryDirectory() as directory:
            config = pathlib.Path(directory) / "main.ini"
            config.write_text("[SERIAL]\nTickerPort = COM9\nSerialBaudrate = 9600\n")
            with patch.dict("os.environ", {}, clear=True):
                self.assertEqual(ticker_port(config), "COM9")
            with patch.dict("os.environ", {"SMUSH_TICKER_PORT": "COM7"}):
                self.assertEqual(ticker_port(config), "COM7")
            for demo_mode, station, connects in ((False, 1, True), (False, 2, False), (True, 1, False)):
                runtime = self.runtime()
                runtime.demo_mode, runtime.station = demo_mode, station
                with patch.dict("os.environ", {}, clear=True), patch("serial_arduino.SerialIO") as serial_io:
                    runtime._initialize_ticker(config)
                    for thread in threading.enumerate():
                        if thread.name == "smush-ticker-serial":
                            thread.join(1)
                self.assertEqual(serial_io.called, connects)
                if connects:
                    serial_io.assert_called_once_with("COM9", 9600, 1)
                    self.assertIs(runtime.ticker_serial, serial_io.return_value)


class TickerFirmwareTests(unittest.TestCase):
    def test_matrix_output_matches_preview(self):
        compiler = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
        if compiler is None:
            self.skipTest("C++ compiler unavailable for firmware simulation")
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "test.cpp").write_text(r"""
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>
using byte = unsigned char;
#define PROGMEM
#define pgm_read_byte(address) (*(address))
constexpr int LOW = 0, HIGH = 1, OUTPUT = 1, MSBFIRST = 1;
unsigned long clockMs = 0;
int pins[20] = {}, modes[20] = {};
uint16_t shifted[20] = {}; // Keyed by DIN pin.
uint8_t registers[4][16] = {};
int writes = 0;
unsigned long millis() { return clockMs; }
void delay(unsigned long ms) { clockMs += ms; }
void pinMode(int pin, int mode) { modes[pin] = mode; }
void delayMicroseconds(unsigned int) {}
void digitalWrite(int pin, int value);
struct SerialStub {
  std::string input; std::vector<std::string> messages;
  void begin(unsigned long) {}
  int available() { return input.size(); }
  char read() { char c = input.front(); input.erase(0, 1); return c; }
  void println(const char *m) { messages.emplace_back(m); }
} Serial;
#include "ticker.ino"
void digitalWrite(int pin, int value) {
  for (byte m = 0; m < MATRIX_COUNT; ++m) {
    if (MATRIX_PINS[m][0] == pin && value == HIGH && pins[pin] == LOW) {
      const int din = MATRIX_PINS[m][2];
      shifted[din] = shifted[din] << 1 | pins[din]; // MAX7219 samples DIN on the rising CLK edge.
    }
    if (MATRIX_PINS[m][1] == pin && value == HIGH && pins[pin] == LOW) {
      const uint16_t word = shifted[MATRIX_PINS[m][2]];
      registers[m][word >> 8 & 0x0F] = word & 0xFF;
      ++writes;
    }
  }
  pins[pin] = value;
}
int decodedColumn(byte x) {
  int column = 0;
  for (byte digit = 0; digit < 8; ++digit) {
    for (byte bit = 0; bit < 8; ++bit) {
      byte row = digit, physical = 7 - bit;
      for (byte turn = 0; turn < MATRIX_ROTATION % 4; ++turn) {
        const byte previous = row;
        row = physical;
        physical = 7 - previous;
      }
      if (MATRIX_MIRROR) physical = 7 - physical;
      if (physical == x % 8 && registers[x / 8][1 + digit] >> bit & 1) column |= 1 << row;
    }
  }
  return column;
}
int main() {
  setup();
  loop();
  const uint8_t one[8] = {0x00, 0x00, 0x42, 0x7F, 0x40, 0x00, 0x00, 0x00}; // Boot test: module 1 shows "1".
  for (byte x = 0; x < 8; ++x) if (decodedColumn(x) != one[x]) return 5;
  for (byte m = 0; m < MATRIX_COUNT; ++m) {
    for (byte p = 0; p < 3; ++p) if (modes[MATRIX_PINS[m][p]] != OUTPUT) return 2;
    if (registers[m][0x0C] != 1 || registers[m][0x0B] != 7 || registers[m][0x09] != 0) return 3;
  }
  std::string line;
  while (std::getline(std::cin, line)) {
    const size_t space = line.find(' ');
    clockMs = std::stoul(line.substr(0, space));
    if (space != std::string::npos) Serial.input += line.substr(space + 1) + "\n";
    loop();
    std::printf("%d", writes);
    for (byte x = 0; x < 32; ++x) {
      std::printf(" %02X", decodedColumn(x));
    }
    std::printf("\n");
  }
  for (byte m = 0; m < MATRIX_COUNT; ++m) if (shifted[MATRIX_PINS[m][2]] != 0) return 7; // No-op parked.
  registers[1][5] ^= 0xFF; // Stray dots from a noise pulse.
  for (byte i = 0; i < MATRIX_COUNT; ++i) { clockMs += 25; loop(); }
  if (registers[1][5] != shownRows[1][4]) return 8;
  registers[2][0x0F] = 1; registers[2][0x0C] = 0; registers[2][3] = 0xFF; // Glitched module.
  clockMs += 1000; loop();
  if (registers[2][0x0F] != 0 || registers[2][0x0C] != 1 || registers[2][3] != shownRows[2][2]) return 6;
  return Serial.messages == std::vector<std::string>{"READY:TICKER"} ? 0 : 4;
}
""")
            executable = root / "firmware-test"
            subprocess.run([compiler, "-std=c++11", "-I", str(SKETCH.parent), str(root / "test.cpp"),
                            "-o", str(executable)], check=True, capture_output=True, text=True)
            script = [
                (1000, "TICK:S:HI", "HI", False, 0),
                (1200, "", "HI", False, 0.2),
                (2000, "TICK:S:WELCOME TO SMUSH", "WELCOME TO SMUSH", False, 0),
                (2035, "", "WELCOME TO SMUSH", False, 0.035),
                (2700, "", "WELCOME TO SMUSH", False, 0.7),
                (3000, "TICK:S:WELCOME TO SMUSH", "WELCOME TO SMUSH", False, 1.0),  # Resend keeps position.
                (3100, "TICK:B:ERR", "ERR", True, 0),
                (3700, "", "ERR", True, 0.6),
                (4100, "", "ERR", True, 1.0),
                (4200, "TICK:X:BAD", "ERR", True, 1.1),
                (4300, "TICK:S:" + "A" * 80, "ERR", True, 1.2),  # Oversized command is discarded.
            ]
            stdin = "".join(f"{time} {command}\n" if command else f"{time}\n" for time, command, *_ in script)
            result = subprocess.run([str(executable)], input=stdin, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = result.stdout.splitlines()
            for (time, command, text, blink, elapsed), line in zip(script, lines):
                shown = tuple(int(value, 16) for value in line.split()[1:])
                self.assertEqual(shown, ticker_frame(text, blink, elapsed), (time, command))


if __name__ == "__main__":
    unittest.main()
