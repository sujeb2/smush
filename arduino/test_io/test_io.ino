const unsigned long SERIAL_BAUD = 9600;
const unsigned long DEBOUNCE_MS = 25;

const byte BUTTON_COUNT = 4;
const byte BUTTON_PINS[BUTTON_COUNT] = {2, 3, 4, 5};
const byte BUTTON_LED_PINS[BUTTON_COUNT] = {6, 7, 8, 9};
const byte LED_ON_LEVEL = HIGH;
const byte LED_OFF_LEVEL = LOW;
const char *const BUTTON_MESSAGES[BUTTON_COUNT] = {
  "Forwarded",
  "Forwarded_2",
  "Forwarded_3",
  "Forwarded_4"
};

byte rawButtonMask = 0;
byte stableButtonMask = 0;
unsigned long rawChangedAt = 0;
char serialCommand[16];
byte serialCommandLength = 0;

void setButtonLed(byte index, bool enabled) {
  digitalWrite(
    BUTTON_LED_PINS[index],
    enabled ? LED_ON_LEVEL : LED_OFF_LEVEL
  );
}

void handleSerialCommand(const char *command) {
  for (byte index = 0; index < BUTTON_COUNT; ++index) {
    char expectedOn[7];
    char expectedOff[8];
    snprintf(expectedOn, sizeof(expectedOn), "SW%u_ON", index + 1);
    snprintf(expectedOff, sizeof(expectedOff), "SW%u_OFF", index + 1);

    if (strcmp(command, expectedOn) == 0) {
      setButtonLed(index, true);
      return;
    }
    if (strcmp(command, expectedOff) == 0) {
      setButtonLed(index, false);
      return;
    }
  }
}

void readSerialCommands() {
  while (Serial.available() > 0) {
    const char incoming = Serial.read();
    if (incoming == '\r') {
      continue;
    }
    if (incoming == '\n') {
      serialCommand[serialCommandLength] = '\0';
      if (serialCommandLength > 0) {
        handleSerialCommand(serialCommand);
      }
      serialCommandLength = 0;
      continue;
    }
    if (serialCommandLength < sizeof(serialCommand) - 1) {
      serialCommand[serialCommandLength++] = incoming;
    } else {
      serialCommandLength = 0;
    }
  }
}

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
    pinMode(BUTTON_LED_PINS[index], OUTPUT);
    setButtonLed(index, false);
  }

  rawButtonMask = readButtonMask();
  stableButtonMask = rawButtonMask;
  rawChangedAt = millis();
}

void loop() {
  readSerialCommands();

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
