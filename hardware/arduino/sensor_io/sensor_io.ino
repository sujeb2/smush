#if defined(__AVR__)
#include <avr/wdt.h>
void disableWatchdogOnBoot() __attribute__((used, naked, section(".init3")));
void disableWatchdogOnBoot() {
  MCUSR = 0;
  wdt_disable();
}
#elif defined(ARDUINO)
#error "soft reset requires a classic AVR Arduino (for example, Uno R3)."
#endif

#define CONV_A1 8
#define CONV_A2 9
#define CONV_B1 10
#define CONV_B2 11

#define CONV_ENABLE_A 12
#define CONV_ENABLE_B 13
#define CONV_STEPS_PER_SECOND 300UL // check down information for range
#define CONV_HALF_STEP true
#define CONV_START_STEPS_PER_SECOND 50UL
#define CONV_RAMP_MS 1000UL
#define CONV_REVERSE true
#define CONV_FORWARD_FOR 6500UL

#if CONV_STEPS_PER_SECOND == 0 || CONV_STEPS_PER_SECOND > 500000UL || CONV_START_STEPS_PER_SECOND == 0 || CONV_START_STEPS_PER_SECOND > 500000UL
#error "Target and startup rates must be between 1 and 500000 full steps/s."
#endif

const unsigned long CONV_SUBSTEPS = CONV_HALF_STEP ? 2UL : 1UL;

#define MOTOR_STEP_A 4
#define MOTOR_STEP_B 3
#define MOTOR_PWM 5
#define MOTOR_SPEED 255
#define MOTOR_RUNNING_FOR 13000UL
#define MOTOR_RESET_TIME 3000UL
#define MOTOR_BRAKE_FOR 150UL

// debug
#define DEBUG_CLK 6
#define DEBUG_DIO 7
#define DEBUG_READY 1001
#define DEBUG_READ 1101
#define DEBUG_SENT 1102
#define DEBUG_COMMAND_ERROR 1103
#define DEBUG_BUSY_ERROR 1201
#define DEBUG_SEND_ERROR 1202
#define DEBUG_MOTOR_INIT 2001

#include "ConveyorStepper.h"
#include <TM1637Display.h>

enum CrusherPhase { IDLE, CONVEYING, BUSY, PAUSED, RESETING, INITIALIZING };

ConveyorStepper conveyor(CONV_A1, CONV_A2, CONV_B1, CONV_B2,
                         CONV_ENABLE_A, CONV_ENABLE_B,
                         1000000UL / (CONV_STEPS_PER_SECOND * CONV_SUBSTEPS),
                         CONV_HALF_STEP,
                         1000000UL / (CONV_START_STEPS_PER_SECOND * CONV_SUBSTEPS),
                         CONV_RAMP_MS);
TM1637Display debugDisplay(DEBUG_CLK, DEBUG_DIO);
CrusherPhase motor_phase = IDLE;
int debugCode = DEBUG_READY;
int pendingDebugCode = DEBUG_READY;
unsigned long debugStartTime = 0;

void showDebug(int code) {
  if(debugCode >= DEBUG_COMMAND_ERROR && code < DEBUG_COMMAND_ERROR) return;
  if(debugCode == DEBUG_READ && code == DEBUG_SENT) {
    pendingDebugCode = code;
    return;
  }
  debugCode = code;
  pendingDebugCode = DEBUG_READY;
  debugStartTime = millis();
  debugDisplay.showNumberDec(code, true);
}

void updateDebug() {
  if(debugCode == DEBUG_READY) return;
  const unsigned long holdTime = debugCode >= DEBUG_COMMAND_ERROR ? 2000 : 400;
  if(millis() - debugStartTime < holdTime) return;
  const int nextCode = pendingDebugCode;
  debugCode = DEBUG_READY;
  showDebug(nextCode);
}

void sendDebugMessage(const char *message, bool newline) {
  const size_t expected = strlen(message) + (newline ? 2 : 0);
  const size_t sent = newline ? Serial.println(message) : Serial.write(message);
  showDebug(sent == expected ? DEBUG_SENT : DEBUG_SEND_ERROR);
}

unsigned long pressStartTime = 0;
unsigned long singlePressStartTime = 0;
const unsigned long requiredPressTime = 10000;
const unsigned long singlePressDelay = 120;
bool buttonPressed = false;
bool resetSent = false;
bool conveyorRunning = false;
byte pendingSwitch = 0;
bool crusherRunning = false;
unsigned long crusherStartedAt = 0;
unsigned long crusherStoppedAt = 0;
char commandBuffer[64];
byte commandLength = 0;
bool commandOverflow = false;

void crusher_forward(int Speed);
void crusher_backward(int Speed);
void crusher_stop();

void softwareReset() {
  crusher_stop();
  motor_phase = IDLE;
  conveyor.stop();
  conveyorRunning = false;
  sendDebugMessage("resetting", true);
  Serial.flush();
#if defined(__AVR__)
  noInterrupts();
  wdt_reset();
  wdt_enable(WDTO_15MS);
  while(true) {}
#endif
}

void updateCrusher() {
  const unsigned long curtime = millis();

  switch (motor_phase) { // cruser status
    case BUSY: // crusher running
      sendDebugMessage("crushing_busy", true);
      if(curtime - crusherStartedAt >= MOTOR_RUNNING_FOR) {
        crusher_stop();
        motor_phase = PAUSED;
      }
      break;
    case PAUSED: // wait pause
      if (curtime - crusherStoppedAt >= MOTOR_BRAKE_FOR) {
        crusher_backward(MOTOR_SPEED);
        crusherStartedAt = millis();
        crusherRunning = true;
        motor_phase = RESETING;
      }
      break;
    case INITIALIZING:
    case RESETING:
    showDebug(DEBUG_BUSY_ERROR);
      if (curtime - crusherStartedAt >=
          (motor_phase == INITIALIZING ? MOTOR_RESET_TIME : MOTOR_RUNNING_FOR)) {
        crusher_stop();
        motor_phase = IDLE;
        showDebug(DEBUG_READY);
        sendDebugMessage("crushing_done", true);
      }
      break;
    default: break;
  }
}

void handleCommand(const char *command) {
  if(strcmp(command, "reset_soft") == 0) { // soft reset
    softwareReset();
    return;
  }
  const bool object1 = strstr(command, "obj1_detect") != NULL;
  const bool object2 = strstr(command, "obj2_detect") != NULL;
  showDebug(DEBUG_READ);
  if(!object1 && !object2) {
    showDebug(DEBUG_COMMAND_ERROR);
    return;
  }

  if (conveyorRunning || crusherRunning || motor_phase != IDLE ||
      millis() - crusherStoppedAt < MOTOR_BRAKE_FOR) { // motor, conv check
    showDebug(DEBUG_BUSY_ERROR);
    return;
  }

  conveyor.start(CONV_FORWARD_FOR, CONV_REVERSE);
  conveyorRunning = true;
  motor_phase = CONVEYING;
  sendDebugMessage(object1 ? "obj_dropped1" : "obj_dropped2", false);
}

void readCommands() {
  const int available = Serial.available();
  for(int i = 0; i < available; ++i) {
    updateCrusher();
    const char value = Serial.read();
    if(value == '\n') {
      commandBuffer[commandLength] = '\0';
      if(commandOverflow) showDebug(DEBUG_COMMAND_ERROR);
      else if(commandLength > 0) handleCommand(commandBuffer);
      commandLength = 0;
      commandOverflow = false;
    } else if(value != '\r') {
      if(commandLength < sizeof(commandBuffer) - 1 && !commandOverflow) {
        commandBuffer[commandLength++] = value;
      } else {
        commandOverflow = true;
      }
    }
  }
}

void setup() {
  conveyor.begin();
  pinMode(MOTOR_STEP_A, OUTPUT);
  pinMode(MOTOR_STEP_B, OUTPUT);
  pinMode(MOTOR_PWM, OUTPUT);
  crusher_stop();

  debugDisplay.setBrightness(7);
  debugDisplay.showNumberDec(8888, true);
  Serial.begin(9600);
  while(!Serial);
  sendDebugMessage("\n\n========= IO BOARD INIT =========\n", true);
  debugDisplay.showNumberDec(DEBUG_MOTOR_INIT, true);
  crusher_backward(MOTOR_SPEED);
  crusherStartedAt = millis();
  crusherRunning = true;
  motor_phase = INITIALIZING;

  sendDebugMessage("read start", true);
}

void loop() {
  updateCrusher();
  updateDebug();
  readCommands();

  if(conveyorRunning) {
    conveyor.update();
    if(!conveyor.isMoving()) {
      conveyorRunning = false;
      if(motor_phase == CONVEYING) {
        crusher_forward(MOTOR_SPEED);
        crusherStartedAt = millis();
        crusherRunning = true;
        motor_phase = BUSY;
      }
    }
  }
}

void crusher_forward(int Speed) {
  digitalWrite(MOTOR_STEP_A,HIGH);
  digitalWrite(MOTOR_STEP_B,LOW);
  analogWrite(MOTOR_PWM,Speed);
}

void crusher_backward(int Speed) {
  digitalWrite(MOTOR_STEP_A,LOW);
  digitalWrite(MOTOR_STEP_B,HIGH);
  analogWrite(MOTOR_PWM,Speed);
}

void crusher_stop(){
  digitalWrite(MOTOR_STEP_A,LOW);
  digitalWrite(MOTOR_STEP_B,LOW);
  analogWrite(MOTOR_PWM,0);
  crusherRunning = false;
  crusherStoppedAt = millis();
}
