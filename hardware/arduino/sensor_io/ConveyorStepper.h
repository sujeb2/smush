#pragma once
#include <Arduino.h>

class ConveyorStepper {
public:
  ConveyorStepper(byte in1, byte in2, byte in3, byte in4,
                  byte enableA, byte enableB, unsigned long stepIntervalUs,
                  bool halfStep = false, unsigned long startIntervalUs = 0,
                  unsigned long rampMs = 0)
      : enableA_(enableA), enableB_(enableB), intervalUs_(stepIntervalUs),
        startIntervalUs_(startIntervalUs > stepIntervalUs ? startIntervalUs : stepIntervalUs),
        rampMs_(rampMs), halfStep_(halfStep) {
    pins_[0] = in1; pins_[1] = in2; pins_[2] = in3; pins_[3] = in4;
  }

  void begin() {
    digitalWrite(enableA_, LOW);
    digitalWrite(enableB_, LOW);
    pinMode(enableA_, OUTPUT);
    pinMode(enableB_, OUTPUT);
    for(byte i = 0; i < 4; ++i) {
      digitalWrite(pins_[i], LOW);
      pinMode(pins_[i], OUTPUT);
    }
    stop();
  }

  void start(unsigned long durationMs, bool reverse = false) {
    if(moving_) return;
    if(durationMs == 0 || intervalUs_ == 0) { stop(); return; }
    durationMs_ = durationMs;
    reverse_ = reverse;
    startedAtMs_ = millis();
    lastStepUs_ = micros();
    moving_ = true;
    writePhase();
  }

  void update() {
    if(!moving_) return;
    const uint32_t elapsedMs = uint32_t(uint32_t(millis()) - startedAtMs_);
    if(elapsedMs >= durationMs_) {
      stop();
      return;
    }
    const uint32_t now = micros();
    uint32_t interval = intervalUs_;
    if(rampMs_ != 0 && elapsedMs < rampMs_) {
      interval = startIntervalUs_ - uint32_t(
        uint64_t(startIntervalUs_ - intervalUs_) * elapsedMs / rampMs_);
    }
    if(uint32_t(now - lastStepUs_) < interval) return;
    lastStepUs_ = now;
    const byte lastPhase = halfStep_ ? 7 : 3;
    phase_ = (phase_ + (reverse_ ? lastPhase : 1)) & lastPhase;
    writePhase();
  }

  void stop() {
    digitalWrite(enableA_, LOW);
    digitalWrite(enableB_, LOW);
    for(byte i = 0; i < 4; ++i) digitalWrite(pins_[i], LOW);
    moving_ = false;
  }

  bool isMoving() const { return moving_; }

private:
  void writePhase() {
    static const byte phases[4][4] = {
      {HIGH, LOW, HIGH, LOW}, {LOW, HIGH, HIGH, LOW},
      {LOW, HIGH, LOW, HIGH}, {HIGH, LOW, LOW, HIGH}
    };
    static const byte halfPhases[8][4] = {
      {HIGH, LOW, HIGH, LOW}, {LOW, LOW, HIGH, LOW},
      {LOW, HIGH, HIGH, LOW}, {LOW, HIGH, LOW, LOW},
      {LOW, HIGH, LOW, HIGH}, {LOW, LOW, LOW, HIGH},
      {HIGH, LOW, LOW, HIGH}, {HIGH, LOW, LOW, LOW}
    };
    const byte *values = halfStep_ ? halfPhases[phase_] : phases[phase_];
    digitalWrite(enableA_, LOW);
    digitalWrite(enableB_, LOW);
    for(byte i = 0; i < 4; ++i) digitalWrite(pins_[i], values[i]);
    digitalWrite(enableA_, values[0] != values[1] ? HIGH : LOW);
    digitalWrite(enableB_, values[2] != values[3] ? HIGH : LOW);
  }

  byte pins_[4];
  byte enableA_, enableB_, phase_ = 0;
  uint32_t intervalUs_, durationMs_ = 0, startedAtMs_ = 0, lastStepUs_ = 0;
  uint32_t startIntervalUs_, rampMs_;
  bool halfStep_, moving_ = false, reverse_ = false;
};
