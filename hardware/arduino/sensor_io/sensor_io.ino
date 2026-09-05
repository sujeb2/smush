
// conveyor
#define CONV_A1 2
#define CONV_A2 3
#define CONV_B1 4
#define CONV_B2 5

#define CONV_SPEED 55
#define CONV_FORWARD_FOR 5000

// force
#define MOTOR_STEP_A 7
#define MOTOR_STEP_B 8
#define MOTOR_PWM 9

#include <L298NX2.h>

L298NX2 conveyor(CONV_A1, CONV_A2, CONV_B1, CONV_B2);

unsigned long pressStartTime = 0;
unsigned long singlePressStartTime = 0;
const unsigned long requiredPressTime = 10000;
const unsigned long singlePressDelay = 120;
bool buttonPressed = false;
bool resetSent = false;
bool conveyorRunning = false;
byte pendingSwitch = 0;

void setup() {
  Serial.begin(9600);
  Serial.println("========= IO BOARD INIT =========");
  while(!Serial);
  conveyor.setSpeedA(CONV_SPEED);
  conveyor.setSpeedB(CONV_SPEED);

  pinMode(MOTOR_STEP_A, OUTPUT);
  pinMode(MOTOR_STEP_B, OUTPUT);
  pinMode(MOTOR_PWM, OUTPUT);

  Serial.println("read start");
}

void loop() {
  if(Serial.available()) {
    String read = Serial.readStringUntil('\n');
    if(!conveyorRunning && read.indexOf("obj1_detect") >= 0) { // expected obj1
      conveyor.reset();
      conveyorRunning = true;
      Serial.write("obj_dropped1");
    } else if(!conveyorRunning && read.indexOf("obj2_detect") >= 0) { // expected obj2
      conveyor.reset();
      conveyorRunning = true;
      Serial.write("obj_dropped2");
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