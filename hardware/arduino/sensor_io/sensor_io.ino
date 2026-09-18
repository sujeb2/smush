
// conveyor
#define CONV_A1 8
#define CONV_A2 9
#define CONV_B1 10
#define CONV_B2 11

#define CONV_SPEED 55
#define CONV_FORWARD_FOR 5000

// force
#define MOTOR_STEP_A 2
#define MOTOR_STEP_B 3
#define MOTOR_PWM 4

// debug
#define DEBUG_CLK 6
#define DEBUG_DIO 7
#define DEBUG_READY 0
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

void setup() {
  debugDisplay.setBrightness(3);
  debugDisplay.showNumberDec(8888, true);
  Serial.begin(9600);
  while(!Serial);
  sendDebugMessage("========= IO BOARD INIT =========", true);
  conveyor.setSpeedA(CONV_SPEED);
  conveyor.setSpeedB(CONV_SPEED);

  pinMode(MOTOR_STEP_A, OUTPUT);
  pinMode(MOTOR_STEP_B, OUTPUT);
  pinMode(MOTOR_PWM, OUTPUT);

  sendDebugMessage("read start", true);
}

void loop() {
  updateDebug();
  if(Serial.available()) {
    String read = Serial.readStringUntil('\n');
    showDebug(DEBUG_READ);
    if(!conveyorRunning && read.indexOf("obj1_detect") >= 0) { // expected obj1
      conveyor.reset();
      conveyorRunning = true;
      sendDebugMessage("obj_dropped1", false);
    } else if(!conveyorRunning && read.indexOf("obj2_detect") >= 0) { // expected obj2
      conveyor.reset();
      conveyorRunning = true;
      sendDebugMessage("obj_dropped2", false);
    } else if(read.indexOf("obj1_detect") >= 0 || read.indexOf("obj2_detect") >= 0) {
      showDebug(DEBUG_BUSY_ERROR);
    } else {
      showDebug(DEBUG_COMMAND_ERROR);
    }
  }

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
}
