#include <avr/wdt.h>
// Clear a watchdog reset early so the board cannot get stuck rebooting.
void disableWatchdogOnBoot() __attribute__((used, naked, section(".init3")));
void disableWatchdogOnBoot() {
  MCUSR = 0;
  wdt_disable();
}

const byte MATRIX_COUNT = 4;
const byte MATRIX_PINS[MATRIX_COUNT][3] = {
  {2, 3, 4},
  {5, 6, 7},
  {8, 9, 10},
  {11, 12, 13},
};
// Per module, in MATRIX_PINS order. Send TICK:CAL to check: each module shows its number upright,
// with a dot in its top-left corner.
const byte MATRIX_ROTATION[MATRIX_COUNT] = {1, 1, 1, 1}; // Quarter turns clockwise.
const bool MATRIX_MIRROR[MATRIX_COUNT] = {false, false, false, false};
const byte MATRIX_BIT_DELAY_US = 1; // Raise if a module shows stray dots on long wires.
const byte MATRIX_INTENSITY = 2;
const byte TICKER_WIDTH = MATRIX_COUNT * 8;
const byte GLYPH_WIDTH = 5;
const byte GLYPH_PITCH = GLYPH_WIDTH + 1;
const unsigned long TICKER_STEP_MS = 50;
const unsigned long TICKER_BLINK_MS = 500;
const unsigned long SERIAL_BAUD = 9600;
const unsigned long POWER_SETTLE_MS = 250;
const unsigned long MATRIX_REFRESH_MS = 1000;
const unsigned long ROW_REFRESH_MS = 25;
const byte MAX7219_NOOP = 0x00;
const byte MAX7219_DIGIT0 = 0x01;
const byte MAX7219_DECODE = 0x09;
const byte MAX7219_INTENSITY = 0x0A;
const byte MAX7219_SCAN_LIMIT = 0x0B;
const byte MAX7219_SHUTDOWN = 0x0C;
const byte MAX7219_DISPLAY_TEST = 0x0F;

const uint8_t TICKER_FONT[64 * GLYPH_WIDTH] PROGMEM = {
  0x00, 0x00, 0x00, 0x00, 0x00,  0x00, 0x00, 0x5F, 0x00, 0x00,  0x00, 0x07, 0x00, 0x07, 0x00,  0x14, 0x7F, 0x14, 0x7F, 0x14, //  !"#
  0x24, 0x2A, 0x7F, 0x2A, 0x12,  0x23, 0x13, 0x08, 0x64, 0x62,  0x36, 0x49, 0x55, 0x22, 0x50,  0x00, 0x05, 0x03, 0x00, 0x00, // $%&'
  0x00, 0x1C, 0x22, 0x41, 0x00,  0x00, 0x41, 0x22, 0x1C, 0x00,  0x08, 0x2A, 0x1C, 0x2A, 0x08,  0x08, 0x08, 0x3E, 0x08, 0x08, // ()*+
  0x00, 0x50, 0x30, 0x00, 0x00,  0x08, 0x08, 0x08, 0x08, 0x08,  0x00, 0x60, 0x60, 0x00, 0x00,  0x20, 0x10, 0x08, 0x04, 0x02, // ,-./
  0x3E, 0x51, 0x49, 0x45, 0x3E,  0x00, 0x42, 0x7F, 0x40, 0x00,  0x42, 0x61, 0x51, 0x49, 0x46,  0x21, 0x41, 0x45, 0x4B, 0x31, // 0123
  0x18, 0x14, 0x12, 0x7F, 0x10,  0x27, 0x45, 0x45, 0x45, 0x39,  0x3C, 0x4A, 0x49, 0x49, 0x30,  0x01, 0x71, 0x09, 0x05, 0x03, // 4567
  0x36, 0x49, 0x49, 0x49, 0x36,  0x06, 0x49, 0x49, 0x29, 0x1E,  0x00, 0x36, 0x36, 0x00, 0x00,  0x00, 0x56, 0x36, 0x00, 0x00, // 89:;
  0x08, 0x14, 0x22, 0x41, 0x00,  0x14, 0x14, 0x14, 0x14, 0x14,  0x00, 0x41, 0x22, 0x14, 0x08,  0x02, 0x01, 0x51, 0x09, 0x06, // <=>?
  0x32, 0x49, 0x79, 0x41, 0x3E,  0x7E, 0x11, 0x11, 0x11, 0x7E,  0x7F, 0x49, 0x49, 0x49, 0x36,  0x3E, 0x41, 0x41, 0x41, 0x22, // @ABC
  0x7F, 0x41, 0x41, 0x22, 0x1C,  0x7F, 0x49, 0x49, 0x49, 0x41,  0x7F, 0x09, 0x09, 0x01, 0x01,  0x3E, 0x41, 0x41, 0x51, 0x32, // DEFG
  0x7F, 0x08, 0x08, 0x08, 0x7F,  0x00, 0x41, 0x7F, 0x41, 0x00,  0x20, 0x40, 0x41, 0x3F, 0x01,  0x7F, 0x08, 0x14, 0x22, 0x41, // HIJK
  0x7F, 0x40, 0x40, 0x40, 0x40,  0x7F, 0x02, 0x04, 0x02, 0x7F,  0x7F, 0x04, 0x08, 0x10, 0x7F,  0x3E, 0x41, 0x41, 0x41, 0x3E, // LMNO
  0x7F, 0x09, 0x09, 0x09, 0x06,  0x3E, 0x41, 0x51, 0x21, 0x5E,  0x7F, 0x09, 0x19, 0x29, 0x46,  0x46, 0x49, 0x49, 0x49, 0x31, // PQRS
  0x01, 0x01, 0x7F, 0x01, 0x01,  0x3F, 0x40, 0x40, 0x40, 0x3F,  0x1F, 0x20, 0x40, 0x20, 0x1F,  0x7F, 0x20, 0x18, 0x20, 0x7F, // TUVW
  0x63, 0x14, 0x08, 0x14, 0x63,  0x03, 0x04, 0x78, 0x04, 0x03,  0x61, 0x51, 0x49, 0x45, 0x43,  0x00, 0x7F, 0x41, 0x41, 0x00, // XYZ[
  0x02, 0x04, 0x08, 0x10, 0x20,  0x00, 0x41, 0x41, 0x7F, 0x00,  0x04, 0x02, 0x01, 0x02, 0x04,  0x40, 0x40, 0x40, 0x40, 0x40, // \]^_
};

char tickerText[49] = "";
int tickerWidth = -1;
bool tickerBlink = false;
bool calibrating = false;
volatile uint8_t *pinPort[MATRIX_COUNT][3];
uint8_t pinMask[MATRIX_COUNT][3];
unsigned long matrixRefreshedAt = 0;
unsigned long rowsRefreshedAt = 0;
byte refreshModule = 0;
unsigned long tickerStartedAt = 0;
uint8_t shownRows[MATRIX_COUNT][8] = {};
char serialCommand[64];
byte serialCommandLength = 0;
bool discardCommand = false;

// Direct port writes: a full redraw takes ~3 ms instead of ~20 ms with digitalWrite.
void setPin(byte module, byte pin, bool high) {
  if (high) *pinPort[module][pin] |= pinMask[module][pin];
  else *pinPort[module][pin] &= ~pinMask[module][pin];
}

void matrixShift(byte module, byte value) {
  for (byte bit = 0x80; bit; bit >>= 1) {
    setPin(module, 2, value & bit);
    delayMicroseconds(MATRIX_BIT_DELAY_US);
    setPin(module, 0, true);
    delayMicroseconds(MATRIX_BIT_DELAY_US);
    setPin(module, 0, false);
  }
}

void matrixWrite(byte module, byte address, byte value) {
  setPin(module, 1, false);
  matrixShift(module, address);
  matrixShift(module, value);
  delayMicroseconds(MATRIX_BIT_DELAY_US);
  setPin(module, 1, true);
  // The MAX7219 keeps shifting while CS is high; park a no-op so a noise pulse on CS latches nothing.
  matrixShift(module, MAX7219_NOOP);
  matrixShift(module, 0);
}

uint8_t textColumn(int x) {
  if (x < 0 || x >= tickerWidth || x % GLYPH_PITCH == GLYPH_WIDTH) return 0;
  char c = tickerText[x / GLYPH_PITCH];
  if (c >= 'a' && c <= 'z') c -= 'a' - 'A';
  if (c < 0x20 || c > 0x5F) return 0;
  return pgm_read_byte(TICKER_FONT + (c - 0x20) * GLYPH_WIDTH + x % GLYPH_PITCH);
}

void setTicker(const char *text, bool blink) {
  if (calibrating) {
    calibrating = false;
    tickerText[0] = '\0'; // Force the new text to be shown.
  }
  if (blink == tickerBlink && strcmp(text, tickerText) == 0) return;
  strncpy(tickerText, text, sizeof(tickerText) - 1);
  tickerText[sizeof(tickerText) - 1] = '\0';
  tickerWidth = (int)strlen(tickerText) * GLYPH_PITCH - 1;
  tickerBlink = blink;
  tickerStartedAt = millis();
}

void updateTicker(unsigned long now) {
  uint8_t columns[TICKER_WIDTH] = {};
  const unsigned long elapsed = now - tickerStartedAt;
  if (calibrating) {
    for (byte module = 0; module < MATRIX_COUNT; ++module) {
      columns[module * 8] = 0x01; // Top-left corner dot.
      for (byte x = 0; x < GLYPH_WIDTH; ++x) {
        columns[module * 8 + 2 + x] = pgm_read_byte(TICKER_FONT + ('1' + module - 0x20) * GLYPH_WIDTH + x) << 1;
      }
    }
  } else if (tickerWidth > TICKER_WIDTH) {
    const int offset = (elapsed / TICKER_STEP_MS) % (tickerWidth + TICKER_WIDTH);
    for (byte x = 0; x < TICKER_WIDTH; ++x) columns[x] = textColumn(x + offset - TICKER_WIDTH);
  } else if (!tickerBlink || (elapsed / TICKER_BLINK_MS) % 2 == 0) {
    const int start = (TICKER_WIDTH - tickerWidth) / 2;
    for (byte x = 0; x < TICKER_WIDTH; ++x) columns[x] = textColumn(x - start);
  }
  for (byte module = 0; module < MATRIX_COUNT; ++module) {
    for (byte digit = 0; digit < 8; ++digit) {
      byte value = 0;
      for (byte bit = 0; bit < 8; ++bit) {
        byte row = digit, column = 7 - bit;
        for (byte turn = 0; turn < MATRIX_ROTATION[module] % 4; ++turn) {
          const byte previous = row;
          row = column;
          column = 7 - previous;
        }
        if (MATRIX_MIRROR[module]) column = 7 - column;
        if (columns[module * 8 + column] >> row & 1) value |= 1 << bit;
      }
      if (value == shownRows[module][digit]) continue;
      shownRows[module][digit] = value;
      matrixWrite(module, MAX7219_DIGIT0 + digit, value);
    }
  }
}

void handleSerialCommand(const char *command) {
  if (strcmp(command, "TICK:PING") == 0) {
    Serial.println("PONG:TICKER");
    return;
  }
  if (strcmp(command, "TICK:RESET") == 0) {
    Serial.println("RESETTING:TICKER");
    Serial.flush();
    wdt_enable(WDTO_15MS);
    while (true) {}
  }
  if (strcmp(command, "TICK:CAL") == 0) {
    calibrating = true;
    return;
  }
  if (strncmp(command, "TICK:", 5) != 0) return;
  const char mode = command[5];
  if ((mode != 'S' && mode != 'B') || command[6] != ':') return;
  setTicker(command + 7, mode == 'B');
}

void readSerialCommands() {
  while (Serial.available() > 0) {
    const char incoming = Serial.read();
    if (incoming == '\r') continue;
    if (incoming == '\n') {
      serialCommand[serialCommandLength] = '\0';
      if (!discardCommand && serialCommandLength > 0) handleSerialCommand(serialCommand);
      serialCommandLength = 0;
      discardCommand = false;
    } else if (discardCommand) {
      continue;
    } else if (serialCommandLength < sizeof(serialCommand) - 1) {
      serialCommand[serialCommandLength++] = incoming;
    } else {
      serialCommandLength = 0;
      discardCommand = true;
    }
  }
}

void configureMatrix(byte module) {
  matrixWrite(module, MAX7219_DISPLAY_TEST, 0);
  matrixWrite(module, MAX7219_DECODE, 0);
  matrixWrite(module, MAX7219_SCAN_LIMIT, 7);
  matrixWrite(module, MAX7219_INTENSITY, MATRIX_INTENSITY);
  for (byte digit = 0; digit < 8; ++digit) matrixWrite(module, MAX7219_DIGIT0 + digit, shownRows[module][digit]);
  matrixWrite(module, MAX7219_SHUTDOWN, 1);
}

void setup() {
  for (byte module = 0; module < MATRIX_COUNT; ++module) {
    for (byte pin = 0; pin < 3; ++pin) {
      pinPort[module][pin] = portOutputRegister(digitalPinToPort(MATRIX_PINS[module][pin]));
      pinMask[module][pin] = digitalPinToBitMask(MATRIX_PINS[module][pin]);
    }
    digitalWrite(MATRIX_PINS[module][1], HIGH);
    digitalWrite(MATRIX_PINS[module][0], LOW);
    for (byte pin = 0; pin < 3; ++pin) pinMode(MATRIX_PINS[module][pin], OUTPUT);
  }
  delay(POWER_SETTLE_MS);
  for (byte module = 0; module < MATRIX_COUNT; ++module) {
    matrixWrite(module, MAX7219_SHUTDOWN, 0);
    configureMatrix(module);
  }
  matrixRefreshedAt = rowsRefreshedAt = millis();
  Serial.begin(SERIAL_BAUD);
  Serial.println("READY:TICKER");
  wdt_enable(WDTO_2S); // A hung sketch reboots itself.
}

void loop() {
  wdt_reset();
  readSerialCommands();
  const unsigned long now = millis();
  if (now - matrixRefreshedAt >= MATRIX_REFRESH_MS) {
    for (byte module = 0; module < MATRIX_COUNT; ++module) configureMatrix(module);
    matrixRefreshedAt = rowsRefreshedAt = now;
  } else if (now - rowsRefreshedAt >= ROW_REFRESH_MS) {
    for (byte digit = 0; digit < 8; ++digit) {
      matrixWrite(refreshModule, MAX7219_DIGIT0 + digit, shownRows[refreshModule][digit]);
    }
    refreshModule = (refreshModule + 1) % MATRIX_COUNT;
    rowsRefreshedAt = now;
  }
  updateTicker(now);
}
