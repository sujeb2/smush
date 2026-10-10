#include <Adafruit_NeoPixel.h>
#include <TM1637Display.h>

const byte NEOPIXEL_PIN = 10;
const byte NEOPIXEL_COUNT = 4;
Adafruit_NeoPixel pixels(NEOPIXEL_COUNT, NEOPIXEL_PIN, NEO_GRB + NEO_KHZ800);
const unsigned long PIXEL_TIMEOUT_MS = 2000;
unsigned long lastPixelFrame = 0;
bool pixelsActive = false;

const byte TICKER_CLK = 8;
const byte TICKER_DIO = 9;
const byte TICKER_DIGITS = 4;
const unsigned int TICKER_BIT_DELAY_US = 10; 
const unsigned long TICKER_STEP_MS = 280;
const unsigned long TICKER_BLINK_MS = 500;
TM1637Display ticker(TICKER_CLK, TICKER_DIO, TICKER_BIT_DELAY_US);
char tickerText[49] = "";
byte tickerLength = 0;
bool tickerBlink = false;
unsigned long tickerStartedAt = 0;
uint8_t tickerFrame[TICKER_DIGITS] = {};

// Segments (bit 0 = A ... bit 6 = G) for ASCII 0x20-0x5F; lowercase folds to uppercase.
const uint8_t TICKER_FONT[64] PROGMEM = {
  0x00, 0x0A, 0x22, 0x00, 0x6D, 0x00, 0x00, 0x02, 0x39, 0x0F, 0x63, 0x40, 0x04, 0x40, 0x08, 0x52, //  !"#$%&'()*+,-./
  0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F, 0x09, 0x00, 0x58, 0x48, 0x4C, 0x53, // 0-9:;<=>?
  0x7B, 0x77, 0x7C, 0x39, 0x5E, 0x79, 0x71, 0x3D, 0x76, 0x30, 0x1E, 0x75, 0x38, 0x37, 0x54, 0x3F, // @A-O
  0x73, 0x67, 0x50, 0x6D, 0x78, 0x3E, 0x1C, 0x2A, 0x76, 0x6E, 0x5B, 0x39, 0x64, 0x0F, 0x23, 0x08, // P-Z[\]^_
};

uint8_t tickerGlyph(char c) {
  if (c >= 'a' && c <= 'z') c -= 'a' - 'A';
  if (c < 0x20 || c > 0x5F) return 0;
  return pgm_read_byte(TICKER_FONT + (c - 0x20));
}

void setTicker(const char *text, bool blink) {
  if (blink == tickerBlink && strcmp(text, tickerText) == 0) return; // Resends keep the scroll position.
  strncpy(tickerText, text, sizeof(tickerText) - 1);
  tickerText[sizeof(tickerText) - 1] = '\0';
  tickerLength = strlen(tickerText);
  tickerBlink = blink;
  tickerStartedAt = millis();
}

void updateTicker(unsigned long now) {
  uint8_t frame[TICKER_DIGITS] = {};
  const unsigned long elapsed = now - tickerStartedAt;
  if (tickerLength > TICKER_DIGITS) {
    const int offset = (elapsed / TICKER_STEP_MS) % (tickerLength + TICKER_DIGITS);
    for (byte i = 0; i < TICKER_DIGITS; ++i) {
      const int index = offset + i - TICKER_DIGITS;
      if (index >= 0 && index < tickerLength) frame[i] = tickerGlyph(tickerText[index]);
    }
  } else if (!tickerBlink || (elapsed / TICKER_BLINK_MS) % 2 == 0) {
    const byte start = (TICKER_DIGITS - tickerLength) / 2;
    for (byte i = 0; i < tickerLength; ++i) frame[start + i] = tickerGlyph(tickerText[i]);
  }
  if (memcmp(frame, tickerFrame, TICKER_DIGITS) == 0) return;
  memcpy(tickerFrame, frame, TICKER_DIGITS);
  ticker.setSegments(tickerFrame);
}

const unsigned long SERIAL_BAUD = 9600;
const unsigned long RELEASE_DEBOUNCE_MS = 25;
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
char serialCommand[64];
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
  if (strncmp(command, "TICK:", 5) == 0) {
    const char mode = command[5];
    if ((mode != 'S' && mode != 'B') || command[6] != ':') return;
    setTicker(command + 7, mode == 'B');
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
  pixels.begin();
  pixels.clear();
  pixels.show();
  ticker.setBrightness(7);
  ticker.setSegments(tickerFrame);
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
  updateTicker(now);
}
