#include <Adafruit_NeoPixel.h>

const byte NEOPIXEL_PIN = 10;
const byte NEOPIXEL_COUNT = 4;
Adafruit_NeoPixel pixels(NEOPIXEL_COUNT, NEOPIXEL_PIN, NEO_GRB + NEO_KHZ800);
const unsigned long PIXEL_TIMEOUT_MS = 2000;
unsigned long lastPixelFrame = 0;
bool pixelsActive = false;

const unsigned long SERIAL_BAUD = 9600;
const unsigned long RELEASE_DEBOUNCE_MS = 25;
const byte CATCH_POT_PIN = A5;
const unsigned long POT_SAMPLE_MS = 5;
const unsigned long POT_SEND_MS = 20;
const unsigned long POT_REFRESH_MS = 250;
const int POT_DEADBAND = 4;
unsigned long lastPotSample = 0;
unsigned long lastPotSentAt = 0;
int lastPotValue = -1;
long filteredPotQ8 = -1;

void sendCatchPotentiometer(unsigned long now) {
  if (now - lastPotSample < POT_SAMPLE_MS) return;
  lastPotSample = now;
  int readings[5];
  for (byte i = 0; i < 5; ++i) {
    readings[i] = analogRead(CATCH_POT_PIN);
    for (byte j = i; j > 0 && readings[j] < readings[j - 1]; --j) {
      const int temporary = readings[j];
      readings[j] = readings[j - 1];
      readings[j - 1] = temporary;
    }
  }
  const long sampleQ8 = (long)readings[2] * 256;
  if (filteredPotQ8 < 0) filteredPotQ8 = sampleQ8;
  else filteredPotQ8 += (sampleQ8 - filteredPotQ8) / 4;
  int value = (filteredPotQ8 + 128) / 256;
  if (value <= POT_DEADBAND) value = 0;
  if (value >= 1023 - POT_DEADBAND) value = 1023;
  if (now - lastPotSentAt < POT_SEND_MS) return;
  const bool changed = lastPotValue < 0 || abs(value - lastPotValue) >= POT_DEADBAND;
  if (!changed && now - lastPotSentAt < POT_REFRESH_MS) return;
  if (!changed) value = lastPotValue;
  char frame[11];
  snprintf(frame, sizeof(frame), "POT:%04d;", value);
  Serial.println(frame);
  lastPotValue = value;
  lastPotSentAt = now;
}

const byte BUTTON_COUNT = 6;
const byte BUTTON_PINS[BUTTON_COUNT] = {2, 3, 4, 5, 6, 7};
const char *const BUTTON_MESSAGES[BUTTON_COUNT] = {
  "Forwarded",
  "Forwarded_2",
  "Forwarded_3",
  "Forwarded_4",
  "BTN1",
  "BTN2"
};

byte rawButtonMask = 0;
byte stableButtonMask = 0;
unsigned long rawChangedAt[BUTTON_COUNT] = {};
char serialCommand[40];
byte serialCommandLength = 0;
bool discardCommand = false;
unsigned long lastSerialByte = 0;

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
    for (byte i = 0; i < NEOPIXEL_COUNT; ++i) {
      pixels.setPixelColor(i, rgb[i * 3], rgb[i * 3 + 1], rgb[i * 3 + 2]);
    }
    pixels.show();
    lastPixelFrame = millis();
    pixelsActive = true;
    return;
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
  pinMode(CATCH_POT_PIN, INPUT);
  pixels.begin();
  pixels.clear();
  pixels.show();
  for (byte index = 0; index < BUTTON_COUNT; ++index) {
    pinMode(BUTTON_PINS[index], INPUT_PULLUP);
    rawChangedAt[index] = millis();
  }

  rawButtonMask = readButtonMask();
  stableButtonMask = rawButtonMask;
  Serial.println("READY:NEOPIXEL4:BTN6");
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

  for (byte index = 0; index < BUTTON_COUNT; ++index) {
    const byte bit = 1 << index;
    if ((sampledButtonMask ^ rawButtonMask) & bit) {
      rawButtonMask ^= bit;
      rawChangedAt[index] = now;
    }
    if ((rawButtonMask & bit) && !(stableButtonMask & bit)) {
      stableButtonMask |= bit;
      Serial.println(BUTTON_MESSAGES[index]);
    } else if (!(rawButtonMask & bit) && (stableButtonMask & bit)
               && now - rawChangedAt[index] >= RELEASE_DEBOUNCE_MS) {
      stableButtonMask &= ~bit;
    }
  }
  sendCatchPotentiometer(now);
}
