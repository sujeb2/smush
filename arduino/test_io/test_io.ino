const unsigned long SERIAL_BAUD = 9600;
const unsigned long DEBOUNCE_MS = 25;

const byte BUTTON_COUNT = 4;
const byte BUTTON_PINS[BUTTON_COUNT] = {2, 3, 4, 5};
const char *const BUTTON_MESSAGES[BUTTON_COUNT] = {
  "Forwarded",
  "Forwarded_2",
  "Forwarded_3",
  "Forwarded_4"
};

byte rawButtonMask = 0;
byte stableButtonMask = 0;
unsigned long rawChangedAt = 0;

byte readButtonMask() {
  byte mask = 0;
  for (byte index = 0; index < BUTTON_COUNT; ++index) {
    if (digitalRead(BUTTON_PINS[index]) == LOW) {
      mask |= (1 << index);
    }
  }

  return mask;
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  for (byte index = 0; index < BUTTON_COUNT; ++index) {
    pinMode(BUTTON_PINS[index], INPUT_PULLUP);
  }

  rawButtonMask = readButtonMask();
  stableButtonMask = rawButtonMask;
  rawChangedAt = millis();
}

void loop() {
  const unsigned long now = millis();
  const byte sampledButtonMask = readButtonMask();

  if (sampledButtonMask != rawButtonMask) {
    rawButtonMask = sampledButtonMask;
    rawChangedAt = now;
  }

  if (
    rawButtonMask != stableButtonMask
    && now - rawChangedAt >= DEBOUNCE_MS
  ) {
    const byte newlyPressed = rawButtonMask & ~stableButtonMask;
    stableButtonMask = rawButtonMask;

    for (byte index = 0; index < BUTTON_COUNT; ++index) {
      if (newlyPressed & (1 << index)) {
        Serial.println(BUTTON_MESSAGES[index]);
      }
    }
  }
}
