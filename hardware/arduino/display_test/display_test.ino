#include <TM1637Display.h>

// debug
#define DEBUG_CLK 6
#define DEBUG_DIO 7

TM1637Display debugDisplay(DEBUG_CLK, DEBUG_DIO);

void setup() {
  debugDisplay.setBrightness(7, true);
}

void loop() {
  // all segments
  const uint8_t segments[] = {0xff, 0xff, 0xff, 0xff};
  debugDisplay.setSegments(segments);
  delay(2000);

  // digit order
  debugDisplay.showNumberDec(1234, true);
  delay(2000);
}
