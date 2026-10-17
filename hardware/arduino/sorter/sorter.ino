
const byte STEPPER_PINS[4] = {2, 3, 4, 5};
const unsigned long SERIAL_BAUD = 9600;
const long STEPS_PER_REV = 4096;
const long SORT_STEPS = STEPS_PER_REV / 8;
const bool SORT_INVERT = false;
// 1200 us stalled the 28BYJ-48 under the gate's load; 2000 us trades ~0.4 s for torque.
const unsigned int STEP_INTERVAL_US = 2000;
// The gate opens when the item is dropped and holds through the crush cycle
// (~52 s) until the PC sends SORT:RELEASE after crushing_done.
const unsigned long SORT_MAX_HOLD_MS = 90000;
const unsigned long SORT_ARRIVE_TIMEOUT_MS = 5000;
const unsigned long SORT_RELEASE_MIN_MS = 1500;
const unsigned long SORT_SETTLE_MS = 300;
const byte SENSOR_TRIG[2] = {6, 8};
const byte SENSOR_ECHO[2] = {7, 9};
const unsigned long ECHO_TIMEOUT_US = 25000;
const unsigned int ARRIVE_DELTA_CM = 3;
const byte ARRIVE_SAMPLES = 2;
const unsigned long SENSOR_INTERVAL_MS = 60;

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
unsigned int baselineCm = 0;
byte arriveCount = 0;
bool arrived = false;
unsigned long arrivedAt = 0;
bool released = false;
unsigned long releasedAt = 0;
unsigned long sensorReadAt = 0;
char serialCommand[32];
byte serialCommandLength = 0;
bool discardCommand = false;

const char *sideName(SortSide side) {
  return side == SIDE_CAN ? "CAN" : side == SIDE_PLASTIC ? "PLASTIC" : "HOME";
}

byte sensorIndex(SortSide side) {
  return side == SIDE_CAN ? 0 : 1;
}

unsigned int readDistanceCm(byte sensor) {
  digitalWrite(SENSOR_TRIG[sensor], LOW);
  delayMicroseconds(2);
  digitalWrite(SENSOR_TRIG[sensor], HIGH);
  delayMicroseconds(10);
  digitalWrite(SENSOR_TRIG[sensor], LOW);
  const unsigned long echoUs = pulseIn(SENSOR_ECHO[sensor], HIGH, ECHO_TIMEOUT_US);
  return echoUs == 0 ? ECHO_TIMEOUT_US / 58 : echoUs / 58;
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
  baselineCm = readDistanceCm(sensorIndex(side));
  arriveCount = 0;
  arrived = false;
  released = false;
  sorterState = SORTER_OPENING;
  moveGate(direction * SORT_STEPS);
  Serial.print("SORT_START:");
  Serial.println(sideName(side));
}

void returnHome() {
  sorterState = SORTER_CLOSING;
  moveGate(0);
}

void releaseSort() {
  // Crushing is done: wait for the item (if it has not fallen yet), then close.
  if (sorterState == SORTER_OPENING || sorterState == SORTER_HOLDING) {
    released = true;
    releasedAt = millis();
  }
  Serial.print("SORT_RELEASE:");
  Serial.println(sideName(activeSide));
}

void commandHome() {
  // Ack like SORT:<side> so the PC's tracked send sees a reply.
  Serial.println("SORT_START:HOME");
  returnHome();
}

void updateSorter() {
  switch (sorterState) {
    case SORTER_OPENING:
      if (stepTowardTarget()) {
        holdStartedAt = millis();
        sorterState = SORTER_HOLDING;
      }
      break;
    case SORTER_HOLDING: {
      const unsigned long now = millis();
      if (!released && now - holdStartedAt >= SORT_MAX_HOLD_MS) {
        Serial.print("SORT_TIMEOUT:");
        Serial.println(sideName(activeSide));
        returnHome();
        break;
      }
      if (released) {
        const unsigned long sinceRelease = now - releasedAt;
        if (arrived && sinceRelease >= SORT_RELEASE_MIN_MS && now - arrivedAt >= SORT_SETTLE_MS) {
          returnHome();
          break;
        }
        if (!arrived && sinceRelease >= SORT_ARRIVE_TIMEOUT_MS) {
          Serial.print("SORT_MISSED:");
          Serial.println(sideName(activeSide));
          returnHome();
          break;
        }
      }
      if (!arrived && now - sensorReadAt >= SENSOR_INTERVAL_MS) {
        sensorReadAt = millis();
        const unsigned int distance = readDistanceCm(sensorIndex(activeSide));
        arriveCount = distance + ARRIVE_DELTA_CM <= baselineCm ? arriveCount + 1 : 0;
        if (arriveCount >= ARRIVE_SAMPLES) {
          arrived = true;
          arrivedAt = millis();
          Serial.print("SORT_ARRIVED:");
          Serial.println(sideName(activeSide));
        }
      }
      break;
    }
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
  else if (strcmp(command, "SORT:RELEASE") == 0) releaseSort();
  else if (strcmp(command, "SORT:HOME") == 0) commandHome();
  else if (strcmp(command, "SORT:PING") == 0) Serial.println("PONG:SORTER");
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
  for (byte i = 0; i < 2; ++i) {
    digitalWrite(SENSOR_TRIG[i], LOW);
    pinMode(SENSOR_TRIG[i], OUTPUT);
    pinMode(SENSOR_ECHO[i], INPUT);
  }
  Serial.begin(SERIAL_BAUD);
  Serial.println("READY:SORTER");
}

void loop() {
  readSerialCommands();
  updateSorter();
}
