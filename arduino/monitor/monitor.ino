
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

#include <L298NX2.h>
#include <string>
#include <vector>
#include <sstream>

L298NX2 conveyor(CONV_A1, CONV_A2, CONV_B1, CONV_B2);

conveyor.setSpeedA(CONV_SPEED);
conveyor.setSpeedB(CONV_SPEED);

void setup() {
  Serial.begin(SERIAL_BAUD);
  while(!Serial);
  pinMode(MOTOR_STEP_A, OUTPUT);
  pinMode(MOTOR_STEP_B, OUTPUT);
  pinMode(MOTOR_PWM, OUTPUT);

  Serial.println("Serial Read start")
}

void loop() {
  if(Serial.available()) {
    String read = Serial.readStringUntil('\n');
    if(read.find("obj_detect1")) { // expected obj1
      conveyor.forwardFor(CONV_FORWARD_FOR);
      Serial.write("Forwarded");
    } else if(read.find("obj_detect2")) { // expected obj2
      conveyor.forwardFor(CONV_FORWARD_FOR);
      Serial.write("Forwarded");
    }
  }
}

void crusher_forward(int Speed) {
     digitalWrite(IN1,HIGH);
     digitalWrite(IN2,LOW);
     analogWrite(PWM,Speed);
}

void crusher_backward(int Speed) {
     digitalWrite(IN1,LOW);
     digitalWrite(IN2,HIGH);
     analogWrite(PWM,Speed);
}

void crusher_stop(){
     digitalWrite(IN1,LOW);
     digitalWrite(IN2,LOW);
}
