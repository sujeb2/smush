
// conveyor
#define CONV_A1 8
#define CONV_A2 9
#define CONV_B1 10
#define CONV_B2 11

#define CONV_SPEED 55
#define CONV_FORWARD_FOR 5000

#define MOTOR_STEP_A 4
#define MOTOR_STEP_B 3
#define MOTOR_PWM 5
#define MOTOR_SPEED 255
#define MOTOR_FORWARD_FOR 500UL
#define MOTOR_BRAKE_FOR 250UL

// debug
#define DEBUG_CLK 6
#define DEBUG_DIO 7
#define DEBUG_READY 115
#define DEBUG_READ 1001
#define DEBUG_SENT 1002
#define DEBUG_COMMAND_ERROR 9001
#define DEBUG_BUSY_ERROR 9002
#define DEBUG_SEND_ERROR 9003

#include <L298NX2.h>
#include <TM1637Display.h>

L298NX2 conveyor(CONV_A1, CONV_A2, CONV_B1, CONV_B2);
TM1637Display debugDisplay(DEBUG_CLK, DEBUG_DIO);
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
void crusher_stop();

void updateCrusher() {
  if(crusherRunning && millis() - crusherStartedAt >= MOTOR_FORWARD_FOR) {
    crusher_stop();
  }
}

void handleCommand(const char *command) {
  const bool object1 = strstr(command, "obj1_detect") != NULL;
  const bool object2 = strstr(command, "obj2_detect") != NULL;
  showDebug(DEBUG_READ);
  if(!object1 && !object2) {
    showDebug(DEBUG_COMMAND_ERROR);
    return;
  }
  if(conveyorRunning || crusherRunning ||
     millis() - crusherStoppedAt < MOTOR_BRAKE_FOR) {
    showDebug(DEBUG_BUSY_ERROR);
    return;
  }

  conveyor.reset();
  conveyorRunning = true;
  crusher_forward(MOTOR_SPEED);
  crusherStartedAt = millis();
  crusherRunning = true;
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
  pinMode(MOTOR_STEP_A, OUTPUT);
  pinMode(MOTOR_STEP_B, OUTPUT);
  pinMode(MOTOR_PWM, OUTPUT);
  crusher_stop();

  debugDisplay.setBrightness(3);
  debugDisplay.showNumberDec(8888, true);
  Serial.begin(9600);
  while(!Serial);
  sendDebugMessage("========= IO BOARD INIT =========", true);
  conveyor.setSpeedA(CONV_SPEED);
  conveyor.setSpeedB(CONV_SPEED);

  sendDebugMessage("read start", true);
}

void loop() {
  updateCrusher();
  updateDebug();
  readCommands();

  if(conveyorRunning) {
    conveyor.forwardFor(CONV_FORWARD_FOR);
    if(!conveyor.isMovingA() && !conveyor.isMovingB()) {
      conveyorRunning = false;
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
