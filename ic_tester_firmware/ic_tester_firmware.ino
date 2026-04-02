// IC Tester Firmware - Arduino Mega 2560 R3
// Version 9.0 - Enhanced with timing, stability analysis, direct port I/O,
// and analog voltage measurement.
//
// Architectural overview:
// - The Python GUI sends one line-oriented command at a time over serial.
// - This firmware parses the command, validates pins, performs the hardware
//   action locally on the board, then prints a compact response line.
// - Time-sensitive work stays in firmware because microsecond-scale sampling
//   and propagation timing are not practical from Python over USB serial.
//
// No display hardware required. Controlled entirely via serial from Python GUI.

#include <Arduino.h>

#define FIRMWARE_VERSION "9.0"

// TTL voltage thresholds (ADC values, 10-bit: 0-1023 = 0V-5V)
// Valid LOW:  0V - 0.8V  = ADC 0-163
// Undefined:  0.8V - 2.0V = ADC 164-409
// Valid HIGH: 2.0V - 5.0V = ADC 410-1023
#define TTL_LOW_MAX_ADC   163
#define TTL_HIGH_MIN_ADC  410
#define ADC_TO_MV(adc) ((unsigned long)(adc) * 5000UL / 1023UL)

const int LED_PIN = 13;
bool ledState = false;
bool testInProgress = false;

// ----- Forward declarations -----
void processCommand(String command);
void handleSetPin(String command);
void handleReadPin(String command);
void handleSetMultiplePins(String command);
void handleReadMultiplePins(String command);
void handleRapidSample(String command);
void handleTimedRead(String command);
void handleSetAndTime(String command);
void handleAnalogRead(String command);
void handleAnalogReadPins(String command);
void handleAnalogRapidSample(String command);
bool isValidPin(int pin);
bool isAnalogPin(int pin);

void setup() {
  Serial.begin(9600);
  pinMode(LED_PIN, OUTPUT);

  // Boot LED blink gives a visible sign that the board reset completed and also
  // consumes a short startup delay before the host begins talking to us.
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(150);
    digitalWrite(LED_PIN, LOW);
    delay(150);
  }

  // `READY` is the host-side handshake anchor used during connection.
  Serial.println("READY");
}

void loop() {
  // The protocol is intentionally simple: each command is one newline-delimited
  // string, handled synchronously, then answered with one response line.
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    if (command.length() > 0) {
      processCommand(command);
    }
  }
}

void processCommand(String command) {
  // Dispatch the incoming command to the matching handler. The explicit
  // if/return structure keeps the protocol easy to read and extend in class.
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

  if (command.startsWith("RAPID_SAMPLE,")) {
    handleRapidSample(command);
    return;
  }

  if (command.startsWith("TIMED_READ,")) {
    handleTimedRead(command);
    return;
  }

  if (command.startsWith("SET_AND_TIME,")) {
    handleSetAndTime(command);
    return;
  }

  if (command == "STATUS") {
    Serial.println("STATUS_OK,MEGA2560,READY");
    return;
  }

  if (command == "VERSION") {
    Serial.print("VERSION,");
    Serial.println(FIRMWARE_VERSION);
    return;
  }

  if (command.startsWith("ANALOG_READ_PINS,")) {
    handleAnalogReadPins(command);
    return;
  }

  if (command.startsWith("ANALOG_RAPID_SAMPLE,")) {
    handleAnalogRapidSample(command);
    return;
  }

  if (command.startsWith("ANALOG_READ,")) {
    handleAnalogRead(command);
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
  // Format: SET_PIN,<pin>,<HIGH|LOW>
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
  // Format: READ_PIN,<pin>
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
  // Format: SET_PINS,<pin>:<state>,<pin>:<state>,...
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

// RAPID_SAMPLE,pin,count - Take N rapid consecutive reads of a pin for stability analysis.
// Uses direct digitalRead in tight loop for maximum speed (~4us per sample on Mega).
// Returns: RAPID_SAMPLE_OK,pin,highCount,lowCount,totalMicros
void handleRapidSample(String command) {
  int c1 = command.indexOf(',');
  int c2 = command.indexOf(',', c1 + 1);
  if (c2 < 0) {
    Serial.println("ERROR:INVALID_RAPID_SAMPLE");
    return;
  }

  int pin = command.substring(c1 + 1, c2).toInt();
  int count = command.substring(c2 + 1).toInt();

  if (!isValidPin(pin)) {
    Serial.println("ERROR:INVALID_PIN");
    return;
  }
  if (count < 1) count = 1;
  if (count > 500) count = 500;

  pinMode(pin, INPUT);
  unsigned int highCount = 0;
  unsigned int lowCount = 0;

  unsigned long t0 = micros();
  for (int i = 0; i < count; i++) {
    if (digitalRead(pin) == HIGH) {
      highCount++;
    } else {
      lowCount++;
    }
  }
  unsigned long elapsed = micros() - t0;

  Serial.print("RAPID_SAMPLE_OK,");
  Serial.print(pin);
  Serial.print(",");
  Serial.print(highCount);
  Serial.print(",");
  Serial.print(lowCount);
  Serial.print(",");
  Serial.println(elapsed);
}

// TIMED_READ,pin,intervalUs,count - Read a pin at fixed intervals for waveform capture.
// Returns: TIMED_READ_OK,pin,samples (H/L string),totalMicros
void handleTimedRead(String command) {
  int c1 = command.indexOf(',');
  int c2 = command.indexOf(',', c1 + 1);
  int c3 = command.indexOf(',', c2 + 1);
  if (c3 < 0) {
    Serial.println("ERROR:INVALID_TIMED_READ");
    return;
  }

  int pin = command.substring(c1 + 1, c2).toInt();
  unsigned int intervalUs = command.substring(c2 + 1, c3).toInt();
  int count = command.substring(c3 + 1).toInt();

  if (!isValidPin(pin)) {
    Serial.println("ERROR:INVALID_PIN");
    return;
  }
  if (count < 1) count = 1;
  if (count > 200) count = 200;
  if (intervalUs < 4) intervalUs = 4;

  pinMode(pin, INPUT);
  char samples[201];

  unsigned long t0 = micros();
  for (int i = 0; i < count; i++) {
    samples[i] = (digitalRead(pin) == HIGH) ? 'H' : 'L';
    if (intervalUs > 4) {
      delayMicroseconds(intervalUs - 4);
    }
  }
  unsigned long elapsed = micros() - t0;
  samples[count] = '\0';

  Serial.print("TIMED_READ_OK,");
  Serial.print(pin);
  Serial.print(",");
  Serial.print(samples);
  Serial.print(",");
  Serial.println(elapsed);
}

// SET_AND_TIME,setPin,setState,readPin - Set an input pin and measure propagation delay
// until the output pin changes state. Returns delay in microseconds.
// Returns: SET_AND_TIME_OK,setPin,readPin,prevState,newState,delayMicros
//     or:  SET_AND_TIME_OK,setPin,readPin,state,TIMEOUT,timeoutMicros
void handleSetAndTime(String command) {
  int c1 = command.indexOf(',');
  int c2 = command.indexOf(',', c1 + 1);
  int c3 = command.indexOf(',', c2 + 1);
  int c4 = command.indexOf(',', c3 + 1);
  if (c3 < 0) {
    Serial.println("ERROR:INVALID_SET_AND_TIME");
    return;
  }

  int setPin = command.substring(c1 + 1, c2).toInt();
  String setState = command.substring(c2 + 1, c3);
  int readPin;
  if (c4 > 0) {
    readPin = command.substring(c3 + 1, c4).toInt();
  } else {
    readPin = command.substring(c3 + 1).toInt();
  }

  if (!isValidPin(setPin) || !isValidPin(readPin)) {
    Serial.println("ERROR:INVALID_PIN");
    return;
  }

  // Read the output pin state before the input change
  pinMode(readPin, INPUT);
  int prevState = digitalRead(readPin);

  // Set the input pin and immediately start timing
  pinMode(setPin, OUTPUT);
  unsigned long t0 = micros();
  if (setState == "HIGH") {
    digitalWrite(setPin, HIGH);
  } else {
    digitalWrite(setPin, LOW);
  }

  // Poll the output pin for state change (timeout after 10ms = 10000us)
  const unsigned long TIMEOUT_US = 10000;
  unsigned long elapsed = 0;
  int newState = prevState;
  while (elapsed < TIMEOUT_US) {
    newState = digitalRead(readPin);
    elapsed = micros() - t0;
    if (newState != prevState) break;
  }

  Serial.print("SET_AND_TIME_OK,");
  Serial.print(setPin);
  Serial.print(",");
  Serial.print(readPin);
  Serial.print(",");
  Serial.print(prevState == HIGH ? "HIGH" : "LOW");
  Serial.print(",");
  if (newState != prevState) {
    Serial.print(newState == HIGH ? "HIGH" : "LOW");
    Serial.print(",");
    Serial.println(elapsed);
  } else {
    Serial.print("TIMEOUT,");
    Serial.println(elapsed);
  }
}

// ===== Analog Voltage Measurement Commands =====

// ANALOG_READ,pin - Read analog voltage on a single pin.
// Pin must be an analog-capable pin (A0-A15 = digital 54-69).
// Returns: ANALOG_READ_OK,pin,rawADC,millivolts,zone
// Zone: LOW, UNDEFINED, HIGH (based on TTL thresholds)
void handleAnalogRead(String command) {
  int comma = command.indexOf(',');
  int pin = command.substring(comma + 1).toInt();

  if (!isAnalogPin(pin)) {
    Serial.println("ERROR:NOT_ANALOG_PIN");
    return;
  }

  pinMode(pin, INPUT);
  int raw = analogRead(pin - 54);  // analogRead uses channel 0-15
  unsigned int mv = ADC_TO_MV(raw);

  Serial.print("ANALOG_READ_OK,");
  Serial.print(pin);
  Serial.print(",");
  Serial.print(raw);
  Serial.print(",");
  Serial.print(mv);
  Serial.print(",");
  if (raw <= TTL_LOW_MAX_ADC) {
    Serial.println("LOW");
  } else if (raw >= TTL_HIGH_MIN_ADC) {
    Serial.println("HIGH");
  } else {
    Serial.println("UNDEFINED");
  }
}

// ANALOG_READ_PINS,pin1,pin2,... - Batch analog read on multiple pins.
// Returns: ANALOG_READ_PINS_OK,pin1:raw:mv:zone,pin2:raw:mv:zone,...
void handleAnalogReadPins(String command) {
  int startIdx = command.indexOf(',') + 1;
  String pinData = command.substring(startIdx);

  Serial.print("ANALOG_READ_PINS_OK,");

  int idx = 0;
  bool first = true;
  while (idx < (int)pinData.length()) {
    int commaIdx = pinData.indexOf(',', idx);
    if (commaIdx == -1) commaIdx = pinData.length();

    int pin = pinData.substring(idx, commaIdx).toInt();
    if (isAnalogPin(pin)) {
      pinMode(pin, INPUT);
      int raw = analogRead(pin - 54);
      unsigned int mv = ADC_TO_MV(raw);

      if (!first) Serial.print(",");
      Serial.print(pin);
      Serial.print(":");
      Serial.print(raw);
      Serial.print(":");
      Serial.print(mv);
      Serial.print(":");
      if (raw <= TTL_LOW_MAX_ADC) {
        Serial.print("LOW");
      } else if (raw >= TTL_HIGH_MIN_ADC) {
        Serial.print("HIGH");
      } else {
        Serial.print("UNDEFINED");
      }
      first = false;
    }
    idx = commaIdx + 1;
  }
  Serial.println();
}

// ANALOG_RAPID_SAMPLE,pin,count - Take N rapid analog reads for voltage distribution.
// Returns: ANALOG_RAPID_SAMPLE_OK,pin,count,min,max,avg,belowLow,inUndefined,aboveHigh,totalMicros
void handleAnalogRapidSample(String command) {
  int c1 = command.indexOf(',');
  int c2 = command.indexOf(',', c1 + 1);
  if (c2 < 0) {
    Serial.println("ERROR:INVALID_ANALOG_RAPID_SAMPLE");
    return;
  }

  int pin = command.substring(c1 + 1, c2).toInt();
  int count = command.substring(c2 + 1).toInt();

  if (!isAnalogPin(pin)) {
    Serial.println("ERROR:NOT_ANALOG_PIN");
    return;
  }
  if (count < 1) count = 1;
  if (count > 500) count = 500;

  pinMode(pin, INPUT);
  int channel = pin - 54;

  unsigned int minVal = 1023;
  unsigned int maxVal = 0;
  unsigned long sum = 0;
  unsigned int belowLow = 0;
  unsigned int inUndefined = 0;
  unsigned int aboveHigh = 0;

  unsigned long t0 = micros();
  for (int i = 0; i < count; i++) {
    int raw = analogRead(channel);
    if (raw < (int)minVal) minVal = raw;
    if (raw > (int)maxVal) maxVal = raw;
    sum += raw;
    if (raw <= TTL_LOW_MAX_ADC) {
      belowLow++;
    } else if (raw >= TTL_HIGH_MIN_ADC) {
      aboveHigh++;
    } else {
      inUndefined++;
    }
  }
  unsigned long elapsed = micros() - t0;
  unsigned int avg = sum / count;

  Serial.print("ANALOG_RAPID_SAMPLE_OK,");
  Serial.print(pin);
  Serial.print(",");
  Serial.print(count);
  Serial.print(",");
  Serial.print(minVal);
  Serial.print(",");
  Serial.print(maxVal);
  Serial.print(",");
  Serial.print(avg);
  Serial.print(",");
  Serial.print(belowLow);
  Serial.print(",");
  Serial.print(inUndefined);
  Serial.print(",");
  Serial.print(aboveHigh);
  Serial.print(",");
  Serial.println(elapsed);
}

bool isValidPin(int pin) {
  // Mega 2560: digital pins 2-53, analog A1-A15 (55-69)
  // Pin 0,1 reserved for Serial. A0 (54) skipped.
  if (pin >= 2 && pin <= 53) return true;
  if (pin >= 55 && pin <= 69) return true;
  return false;
}

bool isAnalogPin(int pin) {
  // Analog pins A0-A15 = digital pins 54-69
  return (pin >= 54 && pin <= 69);
}
