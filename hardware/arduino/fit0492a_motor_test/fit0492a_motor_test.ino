const byte IN2_PIN = 3;
const byte IN1_PIN = 4;
const byte PWM_PIN = 5;

const byte TEST_PWM = 255; // range 0–255
const unsigned long JOG_MS = 1500; 
const unsigned long BRAKE_MS = 100; 

bool moving = false;
unsigned long startedAt = 0;
unsigned long stoppedAt = 0;

void stopMotor() {
  analogWrite(PWM_PIN, 0);
  digitalWrite(IN1_PIN, LOW);
  digitalWrite(IN2_PIN, LOW);
  moving = false;
  stoppedAt = millis();
}

void startJog(bool forward) { // reject command
  if (moving || millis() - stoppedAt < BRAKE_MS) {
    Serial.println(F("Wait until stopped, then send again."));
    return;
  }

  digitalWrite(IN1_PIN, forward ? HIGH : LOW);
  digitalWrite(IN2_PIN, forward ? LOW : HIGH);
  analogWrite(PWM_PIN, TEST_PWM);

  startedAt = millis();
  moving = true;
  Serial.println(forward ? F("Forward") : F("Reverse"));
}

void setup() {
  pinMode(IN1_PIN, OUTPUT);
  pinMode(IN2_PIN, OUTPUT);
  pinMode(PWM_PIN, OUTPUT);
  stopMotor();

  Serial.begin(9600);
  Serial.println(F("f = forward, r = reverse, s = stop"));
}

void loop() {
  if (moving && millis() - startedAt >= JOG_MS) {
    stopMotor();
    Serial.println(F("timed stop"));
  }

  if (Serial.available() > 0) {
    char command = Serial.read();

    switch (command) {
      case 'f':
      case 'F':
        startJog(true);
        break;

      case 'r':
      case 'R':
        startJog(false);
        break;

      case 's':
      case 'S':
        stopMotor();
        Serial.println(F("stop"));
        break;
    }
  }
}