#include <Servo.h>

const byte SERVO_PIN = 9;
const unsigned long SERIAL_BAUD = 9600;
const byte RIGHT_ANGLE = 0;
const byte LEFT_ANGLE = 90;
const bool BLOCK_INVERT = false;
const unsigned long MOVE_SETTLE_MS = 500;

enum BlockSide : byte { SIDE_RIGHT, SIDE_LEFT };

Servo blocker;
BlockSide currentSide = SIDE_RIGHT;
bool moving = false;
unsigned long movedAt = 0;
char serialCommand[32];
byte serialCommandLength = 0;
bool discardCommand = false;

const char *sideName(BlockSide side) {
  return side == SIDE_LEFT ? "LEFT" : "RIGHT";
}

byte sideAngle(BlockSide side) {
  const bool left = (side == SIDE_LEFT) != BLOCK_INVERT;
  return left ? LEFT_ANGLE : RIGHT_ANGLE;
}

void moveBlocker(BlockSide side) {
  currentSide = side;
  blocker.write(sideAngle(side));
  moving = true;
  movedAt = millis();
  Serial.print("BLOCK_START:");
  Serial.println(sideName(side));
}

void updateBlocker() {
  if (moving && millis() - movedAt >= MOVE_SETTLE_MS) {
    moving = false;
    Serial.print("BLOCK_DONE:");
    Serial.println(sideName(currentSide));
  }
}

void handleSerialCommand(const char *command) {
  if (strcmp(command, "BLOCK:LEFT") == 0) moveBlocker(SIDE_LEFT);
  else if (strcmp(command, "BLOCK:RIGHT") == 0) moveBlocker(SIDE_RIGHT);
  else if (strcmp(command, "BLOCK:PING") == 0) Serial.println("PONG:BLOCKER");
  else Serial.println("BLOCK_ERROR");
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
      serialCommand[serialCommandLength++] = incoming >= 'a' && incoming <= 'z' ? incoming - ('a' - 'A') : incoming;
    } else {
      serialCommandLength = 0;
      discardCommand = true;
    }
  }
}

void setup() {
  blocker.write(sideAngle(SIDE_RIGHT));
  blocker.attach(SERVO_PIN);
  Serial.begin(SERIAL_BAUD);
  Serial.println("READY:BLOCKER");
}

void loop() {
  readSerialCommands();
  updateBlocker();
}
