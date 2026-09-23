"""Exercise sensor firmware timing with host-side Arduino/library stubs."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest


class SensorIOFirmwareTests(unittest.TestCase):
    def test_drop_jogs_and_serial_cannot_delay_stop(self):
        compiler = shutil.which("c++") or shutil.which("g++")
        if compiler is None:
            self.skipTest("C++ compiler unavailable for firmware simulation")
        sketch = pathlib.Path(__file__).resolve().parents[1] / "hardware/arduino/sensor_io"
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "L298NX2.h").write_text(r'''
#pragma once
class L298NX2 {
  unsigned long start = 0;
  bool started = false, moving = false;
public:
  L298NX2(int, int, int, int) {}
  void setSpeedA(int) {} void setSpeedB(int) {}
  void reset() { started = false; moving = false; }
  void forwardFor(unsigned long duration) {
    if(!started) { start = millis(); started = true; }
    moving = millis() - start < duration;
  }
  bool isMovingA() { return moving; }
  bool isMovingB() { return moving; }
};
''')
            (root / "TM1637Display.h").write_text(r'''
#pragma once
class TM1637Display {
public:
  TM1637Display(int, int) {}
  void setBrightness(int) {} void showNumberDec(int, bool) {}
};
''')
            (root / "test.cpp").write_text(r'''
#include <cassert>
#include <cstring>
#include <string>
#include <vector>
using byte = unsigned char;
constexpr int LOW = 0, HIGH = 1, OUTPUT = 1;
unsigned long clockMs = 0;
int pins[20] = {}, modes[20] = {};
unsigned long millis() { return clockMs; }
void pinMode(int pin, int mode) { modes[pin] = mode; }
void digitalWrite(int pin, int value) { pins[pin] = value; }
void analogWrite(int pin, int value) { pins[pin] = value; }
struct SerialStub {
  std::string input;
  std::vector<std::string> messages;
  void begin(int) {}
  explicit operator bool() const { return true; }
  int available() { return input.size(); }
  char read() { char value = input.front(); input.erase(0, 1); return value; }
  size_t write(const char *s) { messages.emplace_back(s); return strlen(s); }
  size_t println(const char *s) { messages.emplace_back(s); return strlen(s) + 2; }
} Serial;
#include "sensor_io.ino"
void step(unsigned long time, const std::string &input = "") {
  clockMs = time; Serial.input += input; loop();
}
void assertStopped() {
  assert(pins[3] == LOW && pins[4] == LOW && pins[5] == 0);
  assert(!crusherRunning);
}
void assertForward() {
  assert(pins[3] == LOW && pins[4] == HIGH && pins[5] == 255);
  assert(crusherRunning);
}
int main() {
  setup(); Serial.messages.clear(); assertStopped();
  assert(modes[2] == 0 && modes[3] == OUTPUT && modes[4] == OUTPUT && modes[5] == OUTPUT);
  step(250, "obj1_detect\n"); assertForward();
  assert(Serial.messages == std::vector<std::string>{"obj_dropped1"});
  step(300, "obj2_detect\n"); // Busy input cannot retrigger or extend movement.
  assert(Serial.messages.size() == 1);
  step(749, "obj2_"); assertForward(); // Incomplete serial command.
  step(750); assertStopped(); // Still stops at exactly 500 ms.
  assert(conveyorRunning);
  step(800, "detect\n"); assertStopped();
  assert(Serial.messages.size() == 1);
  step(5250); assert(!conveyorRunning);
  step(5251, "obj2_detect\r\n"); assertForward();
  assert(Serial.messages.size() == 2 && Serial.messages.back() == "obj_dropped2");
  step(5751); assertStopped();
  step(10251); assert(!conveyorRunning);
  step(10252, std::string(80, 'x') + "obj1_detect\n");
  assertStopped(); assert(Serial.messages.size() == 2);
  step(10253, "invalid\n"); assertStopped();
  step(10254, "obj1_detect"); assertStopped();
  step(10255, "\n"); assertForward(); // Recovers after oversized/invalid input.
  assert(Serial.messages.size() == 3);
  step(10755); assertStopped();
}
''')
            executable = root / "sensor-test"
            subprocess.run(
                [compiler, "-std=c++11", "-I", str(root), "-I", str(sketch),
                 str(root / "test.cpp"), "-o", str(executable)],
                check=True, capture_output=True, text=True,
            )
            subprocess.run([str(executable)], check=True, capture_output=True, text=True)
