
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

#define TEST_UP_SW 11
#define TEST_DOWN_SW 12
#define TEST_UP_SW_LED 13
#define TEST_DOWN_SW_LED 14

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

  pinMode(TEST_UP_SW, INPUT_PULLUP);
  pinMode(TEST_DOWN_SW, INPUT_PULLUP);
  pinMode(TEST_UP_SW_LED, OUTPUT);
  pinMode(TEST_DOWN_SW_LED, OUTPUT);

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

    switch(read) {
      case read.contains('blink'):
        break;
      case read.contains('both_blink'):
        break;
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
      sw_both_led_blink(TEST_UP_SW_LED, TEST_DOWN_SW_LED, 3, 1000)
      Serial.write("RESET");
      resetSent = true;
    }
  } else if(buttonPressed) {
    if(!upPressed && !downPressed) {
      if(!resetSent) {
        sw_both_led_blink(TEST_UP_SW_LED, TEST_DOWN_SW_LED, 4, 100)
        Serial.write("test_back");
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
      Serial.write("test_up");
    } else if(pendingSwitch == 2 && downPressed) {
      Serial.write("test_down");
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

void sw_led_blink(int pin, int sec, int dy) {
  unsigned long startTime = millis();
  while (millis() - startTime < sec*1000) {
    digitalWrite(pin, HIGH);
    delay(dy);
    digitalWrite(pin, LOW);
    delay(dy);
  }
  delay(500);
}

void sw_both_led_blink(int pin, int pin2,int sec, int dy) {
  unsigned long startTime = millis();
  while (millis() - startTime < sec*1000) {
    digitalWrite(pin, HIGH);
    digitalWrite(pin2, HIGH);
    delay(dy);
    digitalWrite(pin, LOW);
    digitalWrite(pin2, LOW);
    delay(dy);
  }
  delay(500);
}