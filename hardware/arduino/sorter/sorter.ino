
const byte STEPPER_PINS[4] = {2, 3, 4, 5};
const unsigned long SERIAL_BAUD = 9600;
const long STEPS_PER_REV = 4096;
const long SORT_STEPS = STEPS_PER_REV / 8;
const bool SORT_INVERT = false;
const unsigned int STEP_INTERVAL_US = 1200; 
const unsigned long SORT_HOLD_MS = 1500; 

const byte HALF_STEPS[8][4] = {
  {HIGH, LOW,  LOW,  LOW},
  {HIGH, HIGH, LOW,  LOW},
  {LOW,  HIGH, LOW,  LOW},
  {LOW,  HIGH, HIGH, LOW},
  {LOW,  LOW,  HIGH, LOW},
  {LOW,  LOW,  HIGH, HIGH},
  {LOW,  LOW,  LOW,  HIGH},
  {HIGH, LOW,  LOW,  HIGH},
};

enum SortSide : byte { SIDE_NONE, SIDE_CAN, SIDE_PLASTIC };
enum SorterState : byte { SORTER_IDLE, SORTER_OPENING, SORTER_HOLDING, SORTER_CLOSING };

long gatePosition = 0;
long gateTarget = 0;
byte stepPhase = 0;
unsigned long lastStepAt = 0;
unsigned long holdStartedAt = 0;
SorterState sorterState = SORTER_IDLE;
SortSide activeSide = SIDE_NONE;
char serialCommand[32];
byte serialCommandLength = 0;
bool discardCommand = false;

const char *sideName(SortSide side) {
  return side == SIDE_CAN ? "CAN" : side == SIDE_PLASTIC ? "PLASTIC" : "HOME";
}

void writePhase() {
  for (byte i = 0; i < 4; ++i) digitalWrite(STEPPER_PINS[i], HALF_STEPS[stepPhase][i]);
}

void releaseStepper() {
  for (byte i = 0; i < 4; ++i) digitalWrite(STEPPER_PINS[i], LOW);
}

bool stepTowardTarget() {
  if (gatePosition == gateTarget) return true;
  const unsigned long now = micros();
  if (now - lastStepAt < STEP_INTERVAL_US) return false;
  lastStepAt = now;
  const bool forward = gateTarget > gatePosition;
  stepPhase = (stepPhase + (forward ? 1 : 7)) & 7;
  gatePosition += forward ? 1 : -1;
  writePhase();
  return gatePosition == gateTarget;
}

void moveGate(long target) {
  gateTarget = target;
  lastStepAt = micros() - STEP_INTERVAL_US;
  writePhase();
}

void startSort(SortSide side) {
  if (sorterState != SORTER_IDLE) {
    Serial.println("SORT_BUSY");
    return;
  }
  const long direction = (side == SIDE_CAN) != SORT_INVERT ? -1 : 1;
  activeSide = side;
  sorterState = SORTER_OPENING;
  moveGate(direction * SORT_STEPS);
  Serial.print("SORT_START:");
  Serial.println(sideName(side));
}

void returnHome() {
  sorterState = SORTER_CLOSING;
  moveGate(0);
}

void updateSorter() {
  switch (sorterState) {
    case SORTER_OPENING:
      if (stepTowardTarget()) {
        holdStartedAt = millis();
        sorterState = SORTER_HOLDING;
      }
      break;
    case SORTER_HOLDING:
      if (millis() - holdStartedAt >= SORT_HOLD_MS) returnHome();
      break;
    case SORTER_CLOSING:
      if (stepTowardTarget()) {
        releaseStepper();
        sorterState = SORTER_IDLE;
        Serial.print("SORT_DONE:");
        Serial.println(sideName(activeSide));
        activeSide = SIDE_NONE;
      }
      break;
    default: break;
  }
}

void handleSerialCommand(const char *command) {
  if (strcmp(command, "SORT:CAN") == 0) startSort(SIDE_CAN);
  else if (strcmp(command, "SORT:PLASTIC") == 0) startSort(SIDE_PLASTIC);
  else if (strcmp(command, "SORT:HOME") == 0) returnHome();
  else Serial.println("SORT_ERROR");
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
  for (byte i = 0; i < 4; ++i) {
    digitalWrite(STEPPER_PINS[i], LOW);
    pinMode(STEPPER_PINS[i], OUTPUT);
  }
  Serial.begin(SERIAL_BAUD);
  Serial.println("READY:SORTER");
}

void loop() {
  readSerialCommands();
  updateSorter();
}
