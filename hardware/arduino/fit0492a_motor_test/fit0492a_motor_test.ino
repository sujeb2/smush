// motor test only code
const byte IN1_PIN = 5;
const byte IN2_PIN = 4;
const byte PWM_PIN = 6;

const byte TEST_PWM = 180;
const unsigned long RUN_MS = 2000;
const unsigned long STOP_MS = 2000;

void stopMotor() {
  analogWrite(PWM_PIN, 0);
  digitalWrite(IN1_PIN, LOW);
  digitalWrite(IN2_PIN, LOW);
}

void setup() {
  digitalWrite(IN1_PIN, LOW);
  digitalWrite(IN2_PIN, LOW);
  digitalWrite(PWM_PIN, LOW);
  pinMode(IN1_PIN, OUTPUT);
  pinMode(IN2_PIN, OUTPUT);
  pinMode(PWM_PIN, OUTPUT);
  stopMotor();
  Serial.begin(9600);
  Serial.println(F("motor test will start in: 3s"));
  delay(3000);
}

void loop() {
  Serial.println(F("Forward"));
  digitalWrite(IN1_PIN, HIGH);
  digitalWrite(IN2_PIN, LOW);
  analogWrite(PWM_PIN, TEST_PWM);
  delay(RUN_MS);

  stopMotor();
  Serial.println(F("Stop"));
  delay(STOP_MS);

  Serial.println(F("Reverse"));
  digitalWrite(IN1_PIN, LOW);
  digitalWrite(IN2_PIN, HIGH);
  analogWrite(PWM_PIN, TEST_PWM);
  delay(RUN_MS);

  stopMotor();
  Serial.println(F("Stop"));
  delay(STOP_MS);
}
