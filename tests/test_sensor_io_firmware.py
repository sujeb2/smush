"""Exercise sensor firmware timing with host-side Arduino/library stubs."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest


class SensorIOFirmwareTests(unittest.TestCase):
    def test_crusher_cycle_and_serial_soft_reset(self):
        compiler = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
        if compiler is None:
            self.skipTest("C++ compiler unavailable for firmware simulation")
        sketch = pathlib.Path(__file__).resolve().parents[1] / "hardware/arduino/sensor_io"
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "avr").mkdir()
            (root / "avr/wdt.h").write_text(r'''
#pragma once
constexpr int WDTO_15MS = 15;
int MCUSR = 8;
bool watchdogDisabled = false;
void wdt_disable() { watchdogDisabled = true; }
void wdt_reset() {}
void wdt_enable(int timeout) {
  assert(timeout == WDTO_15MS);
  throw ResetRequested{}; // Model a reset without hanging the host process.
}
''')
            (root / "Arduino.h").write_text(r'''
#pragma once
#include <cstdint>
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
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
using byte = unsigned char;
constexpr int LOW = 0, HIGH = 1, OUTPUT = 1;
unsigned long clockMs = 0;
uint32_t clockUs = 0;
int pins[20] = {}, modes[20] = {};
struct ResetRequested {};
bool interruptsDisabled = false, serialFlushed = false;
void noInterrupts() { interruptsDisabled = true; }
unsigned long millis() { return clockMs; }
unsigned long micros() { return clockUs; }
void pinMode(int pin, int mode) { modes[pin] = mode; }
void digitalWrite(int pin, int value) { pins[pin] = value; }
void analogWrite(int pin, int value) { pins[pin] = value; }
struct SerialStub {
  std::string input;
  std::vector<std::string> messages;
  void begin(int) {}
  void flush() { serialFlushed = true; }
  explicit operator bool() const { return true; }
  int available() { return input.size(); }
  char read() { char value = input.front(); input.erase(0, 1); return value; }
  size_t write(const char *s) { messages.emplace_back(s); return strlen(s); }
  size_t println(const char *s) { messages.emplace_back(s); return strlen(s) + 2; }
} Serial;
// Exercise the AVR reset path with simulated watchdog APIs. The real .init3
// startup attributes do not apply to a desktop executable.
#define __AVR__ 1
#define __attribute__(attributes)
#include "sensor_io.ino"
#undef __attribute__
#undef __AVR__
void step(unsigned long time, const std::string &input = "") {
  clockMs = time; clockUs = uint32_t(time * 1000UL);
  Serial.input += input; loop();
}
void assertCoilsOff() {
  for(int pin = 8; pin <= 13; ++pin) assert(pins[pin] == LOW);
}
void assertPhase(int a1, int a2, int b1, int b2) {
  assert(pins[8] == a1 && pins[9] == a2);
  assert(pins[10] == b1 && pins[11] == b2);
  assert(pins[12] == HIGH && pins[13] == HIGH);
}
void assertStopped() {
  assert(pins[3] == LOW && pins[4] == LOW && pins[5] == 0);
  assert(!crusherRunning);
}
void assertForward() {
  assert(pins[3] == LOW && pins[4] == HIGH && pins[5] == 255);
  assert(crusherRunning);
}
void assertBackward() {
  assert(pins[3] == HIGH && pins[4] == LOW && pins[5] == 255);
  assert(crusherRunning);
}
void boot() {
  clockMs = 0; clockUs = 0;
  motor_phase = IDLE;
  conveyorRunning = crusherRunning = false;
  commandLength = 0;
  commandOverflow = false;
  debugCode = pendingDebugCode = DEBUG_READY;
  interruptsDisabled = serialFlushed = false;
  Serial.input.clear(); Serial.messages.clear();
  conveyor.stop();
  setup();
  Serial.messages.clear();
}
using Messages = std::vector<std::string>;
Messages take() { Messages taken; taken.swap(Serial.messages); return taken; }
int main() {
  // Exercise the real stepper controller, not a motor-library stub.
  ConveyorStepper testMotor(8, 9, 10, 11, 12, 13, 10000UL);
  testMotor.begin(); assertCoilsOff();
  for(int pin = 8; pin <= 13; ++pin) assert(modes[pin] == OUTPUT);
  testMotor.start(100); assertPhase(HIGH, LOW, HIGH, LOW);
  clockUs = 9999; testMotor.update(); assertPhase(HIGH, LOW, HIGH, LOW);
  clockUs = 10000; testMotor.update(); assertPhase(LOW, HIGH, HIGH, LOW);
  clockUs = 20000; testMotor.update(); assertPhase(LOW, HIGH, LOW, HIGH);
  clockUs = 30000; testMotor.update(); assertPhase(HIGH, LOW, LOW, HIGH);
  clockUs = 40000; testMotor.update(); assertPhase(HIGH, LOW, HIGH, LOW);
  clockMs = 50; testMotor.start(1000); // Must not extend the deadline.
  clockMs = 100; testMotor.update(); assertCoilsOff(); assert(!testMotor.isMoving());
  testMotor.start(100, true); assertPhase(HIGH, LOW, HIGH, LOW);
  clockUs += 10000; testMotor.update(); assertPhase(HIGH, LOW, LOW, HIGH);
  clockUs += 10000; testMotor.update(); assertPhase(LOW, HIGH, LOW, HIGH);
  testMotor.stop(); assertCoilsOff();
  testMotor.start(0); assertCoilsOff(); assert(!testMotor.isMoving());

  // Late updates emit one step, rather than a burst; micros() may wrap.
  clockMs = 0; clockUs = UINT32_MAX - 4999;
  testMotor.start(100);
  clockUs = 4999; testMotor.update(); assertPhase(LOW, HIGH, LOW, HIGH);
  clockUs = 5000; testMotor.update(); assertPhase(HIGH, LOW, LOW, HIGH);
  clockUs = 100000; testMotor.update(); assertPhase(HIGH, LOW, HIGH, LOW);
  testMotor.update(); assertPhase(HIGH, LOW, HIGH, LOW);
  testMotor.stop();
  clockMs = UINT32_MAX - 49; testMotor.start(100);
  clockMs = 49; testMotor.update(); assert(testMotor.isMoving());
  clockMs = 50; testMotor.update(); assertCoilsOff();

  clockMs = 0; clockUs = 0;
  ConveyorStepper halfMotor(8, 9, 10, 11, 12, 13, 10000UL, true, 50000UL, 1000UL);
  halfMotor.begin(); halfMotor.start(5000);
  assertPhase(HIGH, LOW, HIGH, LOW);
  clockUs = 49999; halfMotor.update(); assertPhase(HIGH, LOW, HIGH, LOW);
  clockUs = 50000; halfMotor.update(); // First half step releases coil A.
  assert(pins[8] == LOW && pins[9] == LOW && pins[12] == LOW);
  assert(pins[10] == HIGH && pins[11] == LOW && pins[13] == HIGH);
  clockMs = 1000; clockUs = 60000; halfMotor.update();
  assertPhase(LOW, HIGH, HIGH, LOW); // Target interval after ramp.
  clockUs = 70000; halfMotor.update();
  assert(pins[8] == LOW && pins[9] == HIGH && pins[12] == HIGH);
  assert(pins[10] == LOW && pins[11] == LOW && pins[13] == LOW);
  clockUs = 80000; halfMotor.update(); assertPhase(LOW, HIGH, LOW, HIGH);
  clockUs = 90000; halfMotor.update();
  assert(pins[8] == LOW && pins[9] == LOW && pins[12] == LOW);
  assert(pins[10] == LOW && pins[11] == HIGH && pins[13] == HIGH);
  clockUs = 100000; halfMotor.update(); assertPhase(HIGH, LOW, LOW, HIGH);
  clockUs = 110000; halfMotor.update();
  assert(pins[8] == HIGH && pins[9] == LOW && pins[12] == HIGH);
  assert(pins[10] == LOW && pins[11] == LOW && pins[13] == LOW);
  clockUs = 120000; halfMotor.update(); assertPhase(HIGH, LOW, HIGH, LOW);
  halfMotor.stop(); assertCoilsOff();
  halfMotor.start(5000, true); clockUs = 170000; halfMotor.update();
  assert(pins[8] == HIGH && pins[9] == LOW && pins[12] == HIGH);
  assert(pins[10] == LOW && pins[11] == LOW && pins[13] == LOW);
  halfMotor.stop(); halfMotor.start(5);
  clockMs += 5; halfMotor.update(); assertCoilsOff(); // Stop during ramp.

  clockMs = 0; clockUs = 0;
  ConveyorStepper rampMotor(8, 9, 10, 11, 12, 13, 10000UL, false, 50000UL, 1000UL);
  rampMotor.begin(); rampMotor.start(5000);
  clockMs = 500; clockUs = 29999; rampMotor.update();
  assertPhase(HIGH, LOW, HIGH, LOW);
  clockUs = 30000; rampMotor.update(); assertPhase(LOW, HIGH, HIGH, LOW);
  clockMs = 1000; clockUs = 39999; rampMotor.update(); assertPhase(LOW, HIGH, HIGH, LOW);
  clockUs = 40000; rampMotor.update(); assertPhase(LOW, HIGH, LOW, HIGH);
  rampMotor.stop(); assertCoilsOff();

  disableWatchdogOnBoot();
  assert(MCUSR == 0 && watchdogDisabled);
  boot(); assertBackward();
  assert(modes[2] == 0 && modes[3] == OUTPUT && modes[4] == OUTPUT && modes[5] == OUTPUT);
  step(MOTOR_RESET_TIME - 1, "obj1_detect\n"); assertBackward();
  assert(Serial.messages.empty()); // Boot reset reports nothing until it finishes.
  step(MOTOR_RESET_TIME); assertStopped();
  assert(motor_phase == IDLE);
  assert(take() == (Messages{"crushing_done", "phase:idle:0"}));
  step(MOTOR_RESET_TIME + MOTOR_BRAKE_FOR - 1, "obj1_detect\n");
  assertStopped(); assert(Serial.messages.empty());
  const unsigned long start = MOTOR_RESET_TIME + MOTOR_BRAKE_FOR;
  step(start, "obj1_detect\n"); assertStopped();
  assert(motor_phase == CONVEYING && conveyorRunning);
  assert(conveyor.isMoving());
  assert(take() == (Messages{"obj_dropped1", "phase:convey:6500"}));
  step(start + 50, "obj2_detect\n"); // Busy input cannot extend movement.
  assertStopped(); assert(Serial.messages.empty());
  step(start + 1000); assert(take() == (Messages{"phase:convey:5500"})); // Heartbeat.
  step(start + 1500); assert(Serial.messages.empty()); // At most once a second.
  const unsigned long crushing = start + CONV_FORWARD_FOR;
  step(crushing - 1, "obj2_"); assertStopped();
  assert(conveyorRunning && motor_phase == CONVEYING);
  take();
  step(crushing); assertForward();
  assert(!conveyorRunning && !conveyor.isMoving()); assertCoilsOff();
  assert(motor_phase == BUSY && crusherStartedAt == crushing);
  assert(take() == (Messages{"phase:crush:13000", "crushing_busy"}));
  step(crushing + 1, "detect\n"); assertForward();
  assert(Serial.messages.empty()); // No longer floods crushing_busy every loop.
  step(crushing + 1000); assert(take() == (Messages{"phase:crush:12000", "crushing_busy"}));
  const unsigned long pause = crushing + MOTOR_RUNNING_FOR;
  step(pause - 1, "obj2_"); assertForward();
  take();
  step(pause); assertStopped();
  assert(motor_phase == PAUSED);
  assert(take() == (Messages{"phase:reset:13150"}));
  assert(!conveyorRunning);
  step(pause + MOTOR_BRAKE_FOR - 1, "detect\n"); assertStopped();
  assert(Serial.messages.empty());
  const unsigned long returning = pause + MOTOR_BRAKE_FOR;
  step(returning, "obj2_detect\n"); assertBackward();
  assert(motor_phase == RESETING && Serial.messages.empty()); // Brake and return are one phase.
  step(returning + MOTOR_RUNNING_FOR - 1); assertBackward();
  assert(take() == (Messages{"phase:reset:1"}));
  step(returning + MOTOR_RUNNING_FOR); assertStopped();
  assert(motor_phase == IDLE);
  assert(take() == (Messages{"crushing_done", "phase:idle:0"}));
  step(clockMs + 5000); assert(Serial.messages.empty()); // Idle sends no heartbeat.
  const unsigned long second = clockMs + MOTOR_BRAKE_FOR;
  step(second, "obj2_detect\r\n"); assertStopped();
  assert(conveyorRunning && motor_phase == CONVEYING);
  assert(take() == (Messages{"obj_dropped2", "phase:convey:6500"}));
  const unsigned long secondCrushing = second + CONV_FORWARD_FOR;
  step(secondCrushing); assertForward(); assert(!conveyorRunning);
  step(secondCrushing + MOTOR_RUNNING_FOR); assertStopped();
  step(secondCrushing + MOTOR_RUNNING_FOR + MOTOR_BRAKE_FOR); assertBackward();
  step(secondCrushing + 2 * MOTOR_RUNNING_FOR + MOTOR_BRAKE_FOR); assertStopped();
  step(clockMs + MOTOR_BRAKE_FOR); // Wait before accepting another detection.
  take();
  step(clockMs + 1, std::string(80, 'x') + "obj1_detect\n");
  assertStopped(); assert(Serial.messages.empty());
  step(clockMs + 1, "invalid\nreset\nreset_soft_extra\n"); assertStopped();
  assert(!interruptsDisabled);
  step(clockMs + 1, "obj1_detect"); assertStopped();
  step(clockMs + 1, "\n"); assertStopped(); // Recovers after invalid input.
  assert(conveyorRunning && motor_phase == CONVEYING);
  assert(take() == (Messages{"obj_dropped1", "phase:convey:6500"}));

  // Reset bypasses the busy guard in every phase, and stops every actuator
  // before the watchdog fires. A queued detection must never start a motor.
  const CrusherPhase phases[] = {INITIALIZING, IDLE, CONVEYING, BUSY, PAUSED, RESETING};
  for(CrusherPhase phase : phases) {
    boot();
    if(phase != INITIALIZING) { // Finish the boot reset, then wait out the brake.
      step(MOTOR_RESET_TIME); step(MOTOR_RESET_TIME + MOTOR_BRAKE_FOR);
    }
    if(phase == CONVEYING || phase == BUSY || phase == PAUSED || phase == RESETING)
      step(clockMs, "obj1_detect\n");
    if(phase == BUSY || phase == PAUSED || phase == RESETING)
      step(clockMs + CONV_FORWARD_FOR);
    if(phase == PAUSED || phase == RESETING) step(clockMs + MOTOR_RUNNING_FOR);
    if(phase == RESETING) step(clockMs + MOTOR_BRAKE_FOR);
    assert(motor_phase == phase);
    step(clockMs, "reset_");
    assert(motor_phase == phase && !interruptsDisabled);
    bool resetTriggered = false;
    try {
      step(clockMs, "soft\r\nobj1_detect\n");
    } catch(const ResetRequested &) {
      resetTriggered = true;
    }
    assert(resetTriggered && interruptsDisabled && serialFlushed);
    assertStopped(); assert(motor_phase == IDLE);
    assert(!conveyorRunning && !conveyor.isMoving()); assertCoilsOff();
    assert(Serial.messages.back() == "resetting");
    assert(Serial.input == "obj1_detect\n");
  }
}
''')
            executable = root / "sensor-test"
            subprocess.run(
                [compiler, "-std=c++11", "-I", str(root), "-I", str(sketch),
                 str(root / "test.cpp"), "-o", str(executable)],
                check=True, capture_output=True, text=True,
            )
            subprocess.run([str(executable)], check=True, capture_output=True, text=True)
