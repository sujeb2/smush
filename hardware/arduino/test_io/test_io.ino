#include <Adafruit_NeoPixel.h>

const byte NEOPIXEL_PIN = 10;
const byte NEOPIXEL_COUNT = 4;
Adafruit_NeoPixel pixels(NEOPIXEL_COUNT, NEOPIXEL_PIN, NEO_GRB + NEO_KHZ800);
const unsigned long PIXEL_TIMEOUT_MS = 2000;
unsigned long lastPixelFrame = 0;
bool pixelsActive = false;

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
char serialCommand[40];
byte serialCommandLength = 0;
bool discardCommand = false;
unsigned long lastSerialByte = 0;

void setButtonLed(byte index, bool enabled) {
  digitalWrite(
    BUTTON_LED_PINS[index],
    enabled ? LED_ON_LEVEL : LED_OFF_LEVEL
  );
}

int hexDigit(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  return -1;
}

void handleSerialCommand(const char *command) {
  if (strncmp(command, "LED", 3) == 0) {
    if (strlen(command) != 29 || command[4] != ':') return;
    const int mask = hexDigit(command[3]);
    if (mask < 0) return;
    byte rgb[12];
    for (byte i = 0; i < 12; ++i) {
      int hi = hexDigit(command[5 + i * 2]);
      int lo = hexDigit(command[6 + i * 2]);
      if (hi < 0 || lo < 0) return;
      rgb[i] = (hi << 4) | lo;
    }
    for (byte i = 0; i < BUTTON_COUNT; ++i) {
      setButtonLed(i, mask & (1 << i));
      pixels.setPixelColor(i, rgb[i * 3], rgb[i * 3 + 1], rgb[i * 3 + 2]);
    }
    pixels.show();
    lastPixelFrame = millis();
    pixelsActive = true;
    return;
  }
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
  if (serialCommandLength && millis() - lastSerialByte > 250) {
    serialCommandLength = 0;
    discardCommand = true;
  }
  while (Serial.available() > 0) {
    const char incoming = Serial.read();
    lastSerialByte = millis();
    if (incoming == '\r') {
      continue;
    }
    if (incoming == '\n') {
      serialCommand[serialCommandLength] = '\0';
      if (!discardCommand && serialCommandLength > 0) {
        handleSerialCommand(serialCommand);
      }
      serialCommandLength = 0;
      discardCommand = false;
      continue;
    }
    if (discardCommand) continue;
    if (serialCommandLength < sizeof(serialCommand) - 1) {
      serialCommand[serialCommandLength++] = incoming;
    } else {
      serialCommandLength = 0;
      discardCommand = true;
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
  pixels.begin();
  pixels.clear();
  pixels.show();
  for (byte index = 0; index < BUTTON_COUNT; ++index) {
    pinMode(BUTTON_PINS[index], INPUT_PULLUP);
    pinMode(BUTTON_LED_PINS[index], OUTPUT);
    setButtonLed(index, false);
  }

  rawButtonMask = readButtonMask();
  stableButtonMask = rawButtonMask;
  rawChangedAt = millis();
  Serial.println("READY:NEOPIXEL4");
}

void loop() {
  readSerialCommands();

  const unsigned long now = millis();
  if (pixelsActive && now - lastPixelFrame >= PIXEL_TIMEOUT_MS) {
    pixels.clear();
    pixels.show();
    pixelsActive = false;
  }
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
