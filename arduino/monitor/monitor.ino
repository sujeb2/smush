
// conveyor
#define CONV_A1 2
#define CONV_A2 3
#define CONV_B1 4
#define CONV_B2 5

#define CONV_SPEEDA 55
#define CONV_SPEEDB 55

// serial
#define SERIAL_BAUD 9600

#include <libLM2575.h>
#include <L298NX2.h>
#include <string>
#include <vector>
#include <sstream>

L298NX2 conveyor(CONV_A1, CONV_A2, CONV_B1, CONV_B2);
conveyor.setSpeedA(CONV_SPEEDA);
conveyor.setSpeedB(CONV_SPEEDB);

void setup() {
  Serial.begin(SERIAL_BAUD);
  while(!Serial);
  Serial.println("Serial Read start")
}

void loop() {
  if(Serial.available()) {
    String read = Serial.readStringUntil('\n');
    if(read.find("obj_detect1")) { // expected obj1
      int index = read.find("obj_detect1");

    } else if(read.find("obj_detect2")) { // expected obj2
      int index = read.find("obj_detect2");
      
    }
  }

}

void splitLine(string str) {

}
