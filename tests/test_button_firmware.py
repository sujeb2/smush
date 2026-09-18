"""Run the actual input sketch against a host-side Arduino stub.

This checks button timing/ordering, not AVR compilation or electrical behavior.
"""
import pathlib
import shutil
import subprocess
import tempfile
import unittest


class ButtonFirmwareTests(unittest.TestCase):
    def test_immediate_press_bounce_release_and_independent_buttons(self):
        compiler = shutil.which("c++") or shutil.which("g++")
        if compiler is None:
            self.skipTest("C++ compiler unavailable for firmware simulation")
        sketch = pathlib.Path(__file__).resolve().parents[1] / "hardware/arduino/test_io/test_io.ino"
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
            (root / "test.cpp").write_text(r'''
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
using byte = unsigned char;
constexpr int LOW = 0, HIGH = 1, INPUT = 0, INPUT_PULLUP = 2, A5 = 19;
unsigned long clockMs = 0;
int pins[20];
unsigned long millis() { return clockMs; }
void pinMode(int, int) {}
int digitalRead(int pin) { return pins[pin]; }
int analogRead(int) { return 512; }
struct SerialStub {
  std::vector<std::string> messages;
  void begin(unsigned long) {}
  int available() { return 0; }
  char read() { return 0; }
  void println(const char *message) {
    if (strncmp(message, "POT:", 4) != 0) messages.emplace_back(message);
  }
} Serial;
#include "test_io.ino"
void step(unsigned long time) { clockMs = time; loop(); }
int main() {
  for (auto &pin : pins) pin = HIGH;
  setup(); Serial.messages.clear();
  pins[2] = LOW; step(1);
  assert(Serial.messages == std::vector<std::string>{"Forwarded"});
  pins[2] = HIGH; step(2); // Release bounce does not rearm.
  pins[2] = LOW; step(3);
  pins[3] = LOW; step(4); // Other buttons remain independent.
  assert(Serial.messages.size() == 2 && Serial.messages.back() == "Forwarded_2");
  pins[2] = HIGH; step(5); step(29);
  pins[2] = LOW; step(30); // Only 24 ms of stable release.
  assert(Serial.messages.size() == 2);
  pins[2] = HIGH; step(31); step(56);
  pins[2] = LOW; step(57);
  assert(Serial.messages.size() == 3 && Serial.messages.back() == "Forwarded");
  step(100); // Held buttons do not repeat.
  assert(Serial.messages.size() == 3);
  for (int pin = 4; pin <= 7; ++pin) pins[pin] = LOW;
  step(101);
  const std::vector<std::string> expected = {"Forwarded", "Forwarded_2", "Forwarded",
      "Forwarded_3", "Forwarded_4", "BTN1", "BTN2"};
  assert(Serial.messages == expected);
  setup(); Serial.messages.clear(); // Held during boot: no phantom press.
  step(102);
  assert(Serial.messages.empty());
}
''')
            executable = root / "firmware-test"
            subprocess.run([compiler, "-std=c++11", "-I", str(root), "-I", str(sketch.parent),
                            str(root / "test.cpp"), "-o", str(executable)],
                           check=True, capture_output=True, text=True)
            subprocess.run([str(executable)], check=True, capture_output=True, text=True)
