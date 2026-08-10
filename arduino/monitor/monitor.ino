
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

// serial
#define SERIAL_BAUD 9600

#define TEST_UP_SW 11
#define TEST_DOWN_SW 12

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
  Serial.begin(SERIAL_BAUD);
  while(!Serial);
  conveyor.setSpeedA(CONV_SPEED);
  conveyor.setSpeedB(CONV_SPEED);

  pinMode(MOTOR_STEP_A, OUTPUT);
  pinMode(MOTOR_STEP_B, OUTPUT);
  pinMode(MOTOR_PWM, OUTPUT);
  pinMode(TEST_UP_SW, INPUT_PULLUP);
  pinMode(TEST_DOWN_SW, INPUT_PULLUP);

  Serial.println("read start");
}

void loop() {
  if(Serial.available()) {
    String read = Serial.readStringUntil('\n');
    if(!conveyorRunning && read.indexOf("obj1_detect") >= 0) { // expected obj1
      conveyor.reset();
      conveyorRunning = true;
      Serial.write("Forwarded");
    } else if(!conveyorRunning && read.indexOf("obj2_detect") >= 0) { // expected obj2
      conveyor.reset();
      conveyorRunning = true;
      Serial.write("Forwarded_2");
    }
  }

  if(conveyorRunning) {
    conveyor.forwardFor(CONV_FORWARD_FOR);
    if(!conveyor.isMovingA() && !conveyor.isMovingB()) {
      conveyorRunning = false;
    }
  }
  bool upPressed = digitalRead(TEST_UP_SW) == LOW;
  bool downPressed = digitalRead(TEST_DOWN_SW) == LOW;

  if(upPressed && downPressed) {
    if(!buttonPressed) {
      pressStartTime = millis();
      buttonPressed = true;
      resetSent = false;
      pendingSwitch = 0;
    }
    if(!resetSent && millis() - pressStartTime >= requiredPressTime) {
      Serial.println("RESET");
      resetSent = true;
    }
  } else if(buttonPressed) {
    if(!upPressed && !downPressed) {
      if(!resetSent) {
        Serial.println("test_back");
      }
      buttonPressed = false;
      resetSent = false;
    }
  } else if(!upPressed && !downPressed) {
    pendingSwitch = 0;
  } else if(pendingSwitch == 0) {
    pendingSwitch = upPressed ? 1 : 2;
    singlePressStartTime = millis();
  } else if(pendingSwitch != 3 && millis() - singlePressStartTime >= singlePressDelay) {
    if(pendingSwitch == 1 && upPressed) {
      Serial.println("test_up");
    } else if(pendingSwitch == 2 && downPressed) {
      Serial.println("test_down");
    }
    pendingSwitch = 3;
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
