// IC Tester Firmware - Arduino Mega 2560 R3
// Version 7.0 - Headless serial-only IC testing firmware
// No display hardware required. Controlled entirely via serial from Python GUI.

#include <Arduino.h>

const int LED_PIN = 13;
bool ledState = false;
bool testInProgress = false;

// ----- Forward declarations -----
void processCommand(String command);
void handleSetPin(String command);
void handleReadPin(String command);
void handleSetMultiplePins(String command);
void handleReadMultiplePins(String command);
bool isValidPin(int pin);

void setup() {
  Serial.begin(9600);
  pinMode(LED_PIN, OUTPUT);

  // Boot LED blink
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(150);
    digitalWrite(LED_PIN, LOW);
    delay(150);
  }

  Serial.println("READY");
}

void loop() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    if (command.length() > 0) {
      processCommand(command);
    }
  }
}

void processCommand(String command) {
  if (command == "PING") {
    Serial.println("PONG");
    return;
  }

  if (command == "LED_ON") {
    digitalWrite(LED_PIN, HIGH);
    ledState = true;
    Serial.println("LED_ON_OK");
    return;
  }

  if (command == "LED_OFF") {
    digitalWrite(LED_PIN, LOW);
    ledState = false;
    Serial.println("LED_OFF_OK");
    return;
  }

  if (command.startsWith("SET_PIN,")) {
    handleSetPin(command);
    return;
  }

  if (command.startsWith("READ_PIN,")) {
    handleReadPin(command);
    return;
  }

  if (command.startsWith("SET_PINS,")) {
    handleSetMultiplePins(command);
    return;
  }

  if (command.startsWith("READ_PINS,")) {
    handleReadMultiplePins(command);
    return;
  }

  if (command == "STATUS") {
    Serial.println("STATUS_OK,MEGA2560,READY");
    return;
  }

  if (command == "CLEAR") {
    testInProgress = false;
    digitalWrite(LED_PIN, LOW);
    Serial.println("CLEAR_OK");
    return;
  }

  Serial.println("ERROR:UNKNOWN_COMMAND");
}

void handleSetPin(String command) {
  int firstComma = command.indexOf(',');
  int secondComma = command.indexOf(',', firstComma + 1);
  if (secondComma < 0) {
    Serial.println("ERROR:INVALID_SET_PIN");
    return;
  }

  int pin = command.substring(firstComma + 1, secondComma).toInt();
  String state = command.substring(secondComma + 1);

  if (!isValidPin(pin)) {
    Serial.println("ERROR:INVALID_PIN");
    return;
  }

  pinMode(pin, OUTPUT);
  if (state == "HIGH") {
    digitalWrite(pin, HIGH);
    Serial.print("SET_PIN_OK,");
    Serial.print(pin);
    Serial.println(",HIGH");
  } else if (state == "LOW") {
    digitalWrite(pin, LOW);
    Serial.print("SET_PIN_OK,");
    Serial.print(pin);
    Serial.println(",LOW");
  } else {
    Serial.println("ERROR:INVALID_STATE");
  }
}

void handleReadPin(String command) {
  int comma = command.indexOf(',');
  int pin = command.substring(comma + 1).toInt();

  if (!isValidPin(pin)) {
    Serial.println("ERROR:INVALID_PIN");
    return;
  }

  pinMode(pin, INPUT);
  int state = digitalRead(pin);

  Serial.print("READ_PIN_OK,");
  Serial.print(pin);
  Serial.print(",");
  Serial.println(state == HIGH ? "HIGH" : "LOW");
}

void handleSetMultiplePins(String command) {
  int startIdx = command.indexOf(',') + 1;
  String pinData = command.substring(startIdx);
  int setCount = 0;
  int idx = 0;

  while (idx < (int)pinData.length()) {
    int colonIdx = pinData.indexOf(':', idx);
    int commaIdx = pinData.indexOf(',', idx);
    if (colonIdx == -1) break;
    if (commaIdx == -1) commaIdx = pinData.length();

    int pin = pinData.substring(idx, colonIdx).toInt();
    String state = pinData.substring(colonIdx + 1, commaIdx);

    if (isValidPin(pin)) {
      pinMode(pin, OUTPUT);
      if (state == "HIGH") {
        digitalWrite(pin, HIGH);
        setCount++;
      } else if (state == "LOW") {
        digitalWrite(pin, LOW);
        setCount++;
      }
    }

    idx = commaIdx + 1;
  }

  Serial.print("SET_PINS_OK,");
  Serial.println(setCount);
}

void handleReadMultiplePins(String command) {
  int startIdx = command.indexOf(',') + 1;
  String pinData = command.substring(startIdx);

  Serial.print("READ_PINS_OK,");

  int idx = 0;
  bool first = true;
  while (idx < (int)pinData.length()) {
    int commaIdx = pinData.indexOf(',', idx);
    if (commaIdx == -1) commaIdx = pinData.length();

    int pin = pinData.substring(idx, commaIdx).toInt();
    if (isValidPin(pin)) {
      pinMode(pin, INPUT);
      int state = digitalRead(pin);
      if (!first) Serial.print(",");
      Serial.print(pin);
      Serial.print(":");
      Serial.print(state == HIGH ? "HIGH" : "LOW");
      first = false;
    }
    idx = commaIdx + 1;
  }

  Serial.println();
}

bool isValidPin(int pin) {
  // Mega 2560: digital pins 2-53, analog A1-A15 (55-69)
  // Pin 0,1 reserved for Serial. A0 (54) skipped.
  if (pin >= 2 && pin <= 53) return true;
  if (pin >= 55 && pin <= 69) return true;
  return false;
}
