// IC Tester Display Firmware - Arduino Mega 2560 R3
// Version 6.0 - TFT Control Deck with settings/diagnostics/monitor pages
// Serial protocol remains backward compatible with existing Python app.

#define DISPLAY_LCD1602 0
#define DISPLAY_TFT35   1
#define DISPLAY_BACKEND DISPLAY_TFT35

#if DISPLAY_BACKEND == DISPLAY_LCD1602
  #include <LiquidCrystal.h>
  LiquidCrystal lcd(8, 9, 4, 5, 6, 7);
#elif DISPLAY_BACKEND == DISPLAY_TFT35
  #include <MCUFRIEND_kbv.h>
  #include <Adafruit_GFX.h>
  #include <TouchScreen.h>
  #include <EEPROM.h>
  MCUFRIEND_kbv tft;
#else
  #error "Unsupported DISPLAY_BACKEND"
#endif

#include <Arduino.h>

const int LED_PIN = 13;
const int BUTTON_PIN = A0;

unsigned long lastDisplayTime = 0;
const unsigned long DISPLAY_TIMEOUT = 30000;
bool testInProgress = false;
unsigned long lastCommandMillis = 0;

#if DISPLAY_BACKEND == DISPLAY_TFT35
// ----- Colors -----
const uint16_t C_BLACK  = 0x0000;
const uint16_t C_WHITE  = 0xFFFF;
const uint16_t C_GREEN  = 0x07E0;
const uint16_t C_RED    = 0xF800;
const uint16_t C_YELLOW = 0xFFE0;
const uint16_t C_CYAN   = 0x07FF;
const uint16_t C_NAVY   = 0x0013;
const uint16_t C_PANEL  = 0x18E3;
const uint16_t C_MINT   = 0x7FFA;
const uint16_t C_GRAY   = 0x8410;
const uint16_t C_ORANGE = 0xFD20;

// ----- Allowed tester pins with TFT shield mounted -----
const int TFT_ALLOWED_PINS[] = {
  22,24,26,28,30,32,34,36,38,40,42,44,46,48,50,52,
  31,33,35,37,39,41,43,45,47,49,51,53
};
const int TFT_ALLOWED_PINS_COUNT = sizeof(TFT_ALLOWED_PINS) / sizeof(TFT_ALLOWED_PINS[0]);

// ----- Touch -----
const int XP = 8;
const int XM = A2;
const int YP = A3;
const int YM = 9;
TouchScreen ts(XP, YP, XM, YM, 300);

int TS_LEFT = 120;
int TS_RT = 920;
int TS_TOP = 70;
int TS_BOT = 900;
const int TOUCH_MINPRESSURE = 80;
const int TOUCH_MAXPRESSURE = 1000;
const unsigned long TOUCH_POLL_MS = 35;
const unsigned long TOUCH_DEBOUNCE_MS = 180;
unsigned long lastTouchCheck = 0;
unsigned long lastTouchTime = 0;
unsigned long touchCountWindowStart = 0;
unsigned int touchCountInWindow = 0;
unsigned int touchRateHz = 0;
int lastTouchX = -1;
int lastTouchY = -1;
int lastRawX = -1;
int lastRawY = -1;
int lastPressure = -1;

// ----- UI model -----
enum UiPage { PAGE_HOME = 0, PAGE_SETTINGS = 1, PAGE_DIAG = 2, PAGE_MONITOR = 3 };
enum UiMode { MODE_BASIC = 0, MODE_ADVANCED = 1 };

struct PersistedSettings {
  uint16_t magic;
  uint8_t version;
  uint8_t ui_mode;
  uint8_t brightness_level;
  uint8_t serial_verbosity;
  uint8_t io_guard_enabled;
  uint8_t playground_enabled;
  uint16_t ts_left;
  uint16_t ts_right;
  uint16_t ts_top;
  uint16_t ts_bottom;
  uint16_t checksum;
};

const uint16_t SETTINGS_MAGIC = 0xC0DE;
const uint8_t SETTINGS_VERSION = 1;
const int SETTINGS_EEPROM_ADDR = 0;

PersistedSettings settings;
PersistedSettings settingsShadow;

UiPage activePage = PAGE_HOME;
bool touchStreamEnabled = false;
String uiLine1 = "Awaiting GUI...";
String uiLine2 = "Connect via USB";
String uiStatus = "READY";
uint16_t uiStatusColor = C_GREEN;
int demoProgress = 0;
bool ledState = false;
int monitorPinIndex = 0;

struct Btn {
  int x;
  int y;
  int w;
  int h;
  uint16_t color;
  String label;
};

Btn btnPass  = {16, 200, 104, 44, C_GREEN,  "PASS"};
Btn btnFail  = {132, 200, 104, 44, C_RED,   "FAIL"};
Btn btnLed   = {248, 200, 104, 44, C_CYAN,  "LED"};
Btn btnPulse = {364, 200, 104, 44, C_YELLOW,"PULSE"};

Btn tabHome     = {8,   282, 114, 30, C_CYAN, "HOME"};
Btn tabSettings = {126, 282, 114, 30, C_CYAN, "SET"};
Btn tabDiag     = {244, 282, 114, 30, C_CYAN, "DIAG"};
Btn tabMonitor  = {362, 282, 110, 30, C_CYAN, "I/O"};

Btn setModeBtn   = {16, 182, 140, 36, C_MINT,  "MODE"};
Btn setVerbBtn   = {166,182, 140, 36, C_YELLOW,"VERB"};
Btn setGuardBtn  = {316,182, 152, 36, C_CYAN,  "I/O GUARD"};
Btn setBrightDn  = {16, 224, 52,  30, C_GRAY,  "-"};
Btn setBrightUp  = {76, 224, 52,  30, C_GRAY,  "+"};
Btn setCalDn     = {166,224, 52,  30, C_GRAY,  "-"};
Btn setCalUp     = {226,224, 52,  30, C_GRAY,  "+"};
Btn setSaveBtn   = {316,224, 72,  30, C_GREEN, "SAVE"};
Btn setRevertBtn = {396,224, 72,  30, C_RED,   "UNDO"};

Btn monPrevPin   = {16, 196, 52, 38, C_GRAY, "<"};
Btn monNextPin   = {76, 196, 52, 38, C_GRAY, ">"};
Btn monReadPin   = {142,196, 96, 38, C_CYAN, "READ"};
Btn monTogglePin = {248,196, 106,38, C_ORANGE, "TOGGLE"};
Btn monModePin   = {364,196, 104,38, C_MINT, "MODE"};

bool monitorPinOutputMode = false;
String lastEventText = "Boot";

#endif

// ----- Forward declarations -----
void initDisplay();
void clearDisplay();
void showTextLine(uint8_t line, String text);
void showText2Lines(String line1, String line2);
void showIdleScreen();
void processCommand(String command);
void handleDisplayCommand(String command);
void handleDisplay2LineCommand(String command);
void handleSetPin(String command);
void handleReadPin(String command);
void handleSetMultiplePins(String command);
void handleReadMultiplePins(String command);
bool isValidPin(int pin);
int readButton();

#if DISPLAY_BACKEND == DISPLAY_TFT35
uint16_t calcSettingsChecksum(const PersistedSettings &s);
void applyDefaultSettings();
void loadSettings();
void saveSettings();
void applySettingsToRuntime();
void emitEvent(String category, String type, String value);
void emitWarn(String message);
void emitSettingsChanged(String key, String value);
void emitDiagSnapshot();

void drawButton(Btn b, uint16_t textColor = C_BLACK, bool active = false);
void animateButtonPress(Btn b);
bool touchToScreenXY(int &sx, int &sy, int &rawX, int &rawY, int &pressure);
bool pointInButton(int px, int py, Btn b);
void renderMainUI();
void drawStatusChip(String label, uint16_t color);
void drawProgressBar(int percent, uint16_t color);
void drawMessagePanel(String line1, String line2);
void drawFooterTicker();
void renderActivePage();
void renderHomePage();
void renderSettingsPage();
void renderDiagnosticsPage();
void renderMonitorPage();
void drawTabs();
void handleTouchUI();
void touchNavigate(int x, int y);
void handleHomeTouch(int x, int y);
void handleSettingsTouch(int x, int y);
void handleDiagTouch(int x, int y, int rawX, int rawY, int pressure);
void handleMonitorTouch(int x, int y);
String pageName(UiPage p);
String modeName();
String verbosityName();
int freeRamEstimate();
#endif

void setup() {
  Serial.begin(9600);
  pinMode(LED_PIN, OUTPUT);
  lastCommandMillis = millis();

  initDisplay();

#if DISPLAY_BACKEND == DISPLAY_TFT35
  loadSettings();
  applySettingsToRuntime();
  settingsShadow = settings;
#endif

  showText2Lines("IC Tester v6.0", "Mega 2560 Ready");

  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(180);
    digitalWrite(LED_PIN, LOW);
    delay(180);
  }

  delay(1300);
  showText2Lines("Awaiting GUI...", "Connect via USB");
#if DISPLAY_BACKEND == DISPLAY_TFT35
  renderActivePage();
#endif

  Serial.println("READY");
}

void loop() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    if (command.length() > 0) {
      lastCommandMillis = millis();
      processCommand(command);
    }
  }

  if (!testInProgress && (millis() - lastDisplayTime > DISPLAY_TIMEOUT)) {
    showIdleScreen();
#if DISPLAY_BACKEND == DISPLAY_TFT35
    renderActivePage();
#endif
    lastDisplayTime = millis();
  }

#if DISPLAY_BACKEND == DISPLAY_TFT35
  if (settings.playground_enabled && millis() - lastTouchCheck >= TOUCH_POLL_MS) {
    lastTouchCheck = millis();
    handleTouchUI();
  }

  if (millis() - touchCountWindowStart >= 1000) {
    touchRateHz = touchCountInWindow;
    touchCountInWindow = 0;
    touchCountWindowStart = millis();
    if (touchStreamEnabled) {
      emitEvent("DIAG", "TOUCH_RATE", String(touchRateHz));
      emitEvent("DIAG", "SERIAL_OK", (millis() - lastCommandMillis < 2500) ? "1" : "0");
    }
  }
#endif
}

void processCommand(String command) {
  lastDisplayTime = millis();

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

  if (command.startsWith("DISPLAY,")) {
    handleDisplayCommand(command);
    return;
  }

  if (command.startsWith("DISPLAY_2LINE,")) {
    handleDisplay2LineCommand(command);
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

#if DISPLAY_BACKEND == DISPLAY_TFT35
  if (command == "PLAYGROUND,ON") {
    settings.playground_enabled = 1;
    renderActivePage();
    Serial.println("PLAYGROUND_OK,ON");
    emitSettingsChanged("playground_enabled", "1");
    return;
  }

  if (command == "PLAYGROUND,OFF") {
    settings.playground_enabled = 0;
    Serial.println("PLAYGROUND_OK,OFF");
    emitSettingsChanged("playground_enabled", "0");
    return;
  }

  if (command == "UI,HOME") {
    activePage = PAGE_HOME;
    renderActivePage();
    Serial.println("UI_OK,HOME");
    emitEvent("TOUCH", "PAGE", "HOME");
    return;
  }

  if (command.startsWith("UI,MODE,")) {
    String mode = command.substring(8);
    mode.trim();
    if (mode == "BASIC") settings.ui_mode = MODE_BASIC;
    else if (mode == "ADVANCED") settings.ui_mode = MODE_ADVANCED;
    else {
      Serial.println("ERROR:INVALID_MODE");
      return;
    }
    activePage = PAGE_HOME;
    renderActivePage();
    Serial.println("UI_OK,MODE");
    emitSettingsChanged("ui_mode", modeName());
    return;
  }

  if (command.startsWith("UI,PAGE,")) {
    String page = command.substring(8);
    page.trim();
    if (page == "HOME") activePage = PAGE_HOME;
    else if (page == "SETTINGS") activePage = PAGE_SETTINGS;
    else if (page == "DIAG" && settings.ui_mode == MODE_ADVANCED) activePage = PAGE_DIAG;
    else if (page == "MONITOR" && settings.ui_mode == MODE_ADVANCED) activePage = PAGE_MONITOR;
    else if (page == "DIAG" || page == "MONITOR") {
      Serial.println("ERROR:BASIC_MODE");
      return;
    }
    else {
      Serial.println("ERROR:INVALID_PAGE");
      return;
    }
    renderActivePage();
    Serial.println("UI_OK,PAGE");
    emitEvent("TOUCH", "PAGE", pageName(activePage));
    return;
  }

  if (command == "UI,GET,SETTINGS") {
    Serial.print("SETTINGS,");
    Serial.print("mode="); Serial.print(modeName());
    Serial.print(",brightness="); Serial.print(settings.brightness_level);
    Serial.print(",verbosity="); Serial.print(verbosityName());
    Serial.print(",io_guard="); Serial.print(settings.io_guard_enabled ? "1" : "0");
    Serial.print(",playground="); Serial.print(settings.playground_enabled ? "1" : "0");
    Serial.print(",ts=");
    Serial.print(settings.ts_left); Serial.print("/");
    Serial.print(settings.ts_right); Serial.print("/");
    Serial.print(settings.ts_top); Serial.print("/");
    Serial.println(settings.ts_bottom);
    return;
  }

  if (command.startsWith("UI,SET,")) {
    // UI,SET,<key>,<value>
    int first = command.indexOf(',', 7);
    if (first < 0) {
      Serial.println("ERROR:INVALID_UI_SET");
      return;
    }
    String key = command.substring(7, first);
    String value = command.substring(first + 1);
    key.trim();
    value.trim();

    bool ok = true;
    if (key == "brightness") {
      int v = value.toInt();
      if (v < 0 || v > 100) ok = false;
      else settings.brightness_level = (uint8_t)v;
    } else if (key == "verbosity") {
      int v = value.toInt();
      if (v < 0 || v > 2) ok = false;
      else settings.serial_verbosity = (uint8_t)v;
    } else if (key == "io_guard") {
      settings.io_guard_enabled = (value == "1" || value == "true") ? 1 : 0;
    } else if (key == "playground") {
      settings.playground_enabled = (value == "1" || value == "true") ? 1 : 0;
    } else if (key == "ui_mode") {
      if (value == "BASIC") settings.ui_mode = MODE_BASIC;
      else if (value == "ADVANCED") settings.ui_mode = MODE_ADVANCED;
      else ok = false;
    } else if (key == "ts_left") {
      settings.ts_left = (uint16_t)value.toInt();
    } else if (key == "ts_right") {
      settings.ts_right = (uint16_t)value.toInt();
    } else if (key == "ts_top") {
      settings.ts_top = (uint16_t)value.toInt();
    } else if (key == "ts_bottom") {
      settings.ts_bottom = (uint16_t)value.toInt();
    } else {
      ok = false;
    }

    if (!ok) {
      Serial.println("ERROR:INVALID_UI_SET");
      return;
    }

    applySettingsToRuntime();
    renderActivePage();
    Serial.println("UI_OK,SET");
    emitSettingsChanged(key, value);
    return;
  }

  if (command == "UI,SAVE") {
    saveSettings();
    settingsShadow = settings;
    Serial.println("UI_OK,SAVE");
    emitEvent("SETTING", "SAVED", "1");
    return;
  }

  if (command == "DIAG,GET") {
    emitDiagSnapshot();
    Serial.println("DIAG_OK");
    return;
  }

  if (command.startsWith("TOUCH,STREAM,")) {
    String mode = command.substring(13);
    mode.trim();
    touchStreamEnabled = (mode == "ON");
    Serial.print("TOUCH_STREAM_OK,");
    Serial.println(touchStreamEnabled ? "ON" : "OFF");
    return;
  }
#endif

  if (command == "CLEAR") {
    showText2Lines("Ready for Test", "Start from GUI");
    testInProgress = false;
    digitalWrite(LED_PIN, LOW);
    Serial.println("CLEAR_OK");
    return;
  }

  Serial.println("ERROR:UNKNOWN_COMMAND");
}

void handleDisplayCommand(String command) {
  int comma = command.indexOf(',');
  String message = command.substring(comma + 1);

  if (message == "PASS") {
    testInProgress = false;
#if DISPLAY_BACKEND == DISPLAY_TFT35
    uiStatus = "PASS";
    uiStatusColor = C_GREEN;
    demoProgress = 100;
#endif
    showText2Lines("* TEST PASSED *", "IC is GOOD!");

    for (int i = 0; i < 3; i++) {
      digitalWrite(LED_PIN, HIGH);
      delay(200);
      digitalWrite(LED_PIN, LOW);
      delay(200);
    }
  } else if (message == "FAIL") {
    testInProgress = false;
#if DISPLAY_BACKEND == DISPLAY_TFT35
    uiStatus = "FAIL";
    uiStatusColor = C_RED;
    demoProgress = 100;
#endif
    showText2Lines("* TEST FAILED *", "IC is BAD!");

    for (int i = 0; i < 10; i++) {
      digitalWrite(LED_PIN, HIGH);
      delay(50);
      digitalWrite(LED_PIN, LOW);
      delay(50);
    }
  } else if (message == "TESTING") {
    testInProgress = true;
#if DISPLAY_BACKEND == DISPLAY_TFT35
    uiStatus = "TESTING";
    uiStatusColor = C_ORANGE;
#endif
    showText2Lines("Testing IC...", "Please wait...");
    digitalWrite(LED_PIN, HIGH);
  } else if (message == "READY") {
    testInProgress = false;
#if DISPLAY_BACKEND == DISPLAY_TFT35
    uiStatus = "READY";
    uiStatusColor = C_GREEN;
#endif
    showText2Lines("Ready for Test", "Start from GUI");
    digitalWrite(LED_PIN, LOW);
  } else if (message == "CONNECTED") {
    testInProgress = false;
#if DISPLAY_BACKEND == DISPLAY_TFT35
    uiStatus = "CONNECTED";
    uiStatusColor = C_MINT;
#endif
    showText2Lines("GUI Connected!", "Select IC chip");
    digitalWrite(LED_PIN, LOW);
  } else if (message == "POWER_ERROR") {
    testInProgress = false;
#if DISPLAY_BACKEND == DISPLAY_TFT35
    uiStatus = "PWR ERROR";
    uiStatusColor = C_RED;
#endif
    showText2Lines("POWER ERROR!", "Check VCC/GND");
    for (int i = 0; i < 5; i++) {
      digitalWrite(LED_PIN, HIGH);
      delay(100);
      digitalWrite(LED_PIN, LOW);
      delay(100);
    }
  } else if (message == "PIN_ERROR") {
    testInProgress = false;
#if DISPLAY_BACKEND == DISPLAY_TFT35
    uiStatus = "PIN ERROR";
    uiStatusColor = C_RED;
#endif
    showText2Lines("PIN ERROR!", "Check wiring");
    for (int i = 0; i < 5; i++) {
      digitalWrite(LED_PIN, HIGH);
      delay(100);
      digitalWrite(LED_PIN, LOW);
      delay(100);
    }
  } else {
#if DISPLAY_BACKEND == DISPLAY_TFT35
    uiStatus = "INFO";
    uiStatusColor = C_CYAN;
#endif
    showText2Lines(message, "");
  }

#if DISPLAY_BACKEND == DISPLAY_TFT35
  renderActivePage();
#endif
  Serial.println("DISPLAY_OK");
}

void handleDisplay2LineCommand(String command) {
  int firstComma = command.indexOf(',');
  int secondComma = command.indexOf(',', firstComma + 1);
  if (secondComma < 0) {
    Serial.println("ERROR:INVALID_DISPLAY_2LINE");
    return;
  }

  String line1 = command.substring(firstComma + 1, secondComma);
  String line2 = command.substring(secondComma + 1);
  showText2Lines(line1, line2);
#if DISPLAY_BACKEND == DISPLAY_TFT35
  renderActivePage();
#endif
  Serial.println("DISPLAY_2LINE_OK");
}

void showIdleScreen() {
#if DISPLAY_BACKEND == DISPLAY_TFT35
  uiStatus = "READY";
  uiStatusColor = C_GREEN;
#endif
  showText2Lines("IC Tester v6.0", "Awaiting GUI...");
  digitalWrite(LED_PIN, LOW);
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

#if DISPLAY_BACKEND == DISPLAY_TFT35
  if (settings.io_guard_enabled && !isValidPin(pin)) {
    emitWarn("blocked pin " + String(pin));
  }
#endif

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

  while (idx < pinData.length()) {
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
  while (idx < pinData.length()) {
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
#if DISPLAY_BACKEND == DISPLAY_TFT35
  for (int i = 0; i < TFT_ALLOWED_PINS_COUNT; i++) {
    if (pin == TFT_ALLOWED_PINS[i]) return true;
  }
  return false;
#else
  if (pin >= 2 && pin <= 3) return true;
  if (pin >= 10 && pin <= 53) return true;
  if (pin >= 55 && pin <= 69) return true;
  return false;
#endif
}

int readButton() {
  int adc = analogRead(BUTTON_PIN);
  if (adc > 900) return -1;
  if (adc < 50) return 0;
  if (adc < 150) return 1;
  if (adc < 330) return 2;
  if (adc < 520) return 3;
  if (adc < 750) return 4;
  return -1;
}

void initDisplay() {
#if DISPLAY_BACKEND == DISPLAY_LCD1602
  lcd.begin(16, 2);
  lcd.clear();
#elif DISPLAY_BACKEND == DISPLAY_TFT35
  uint16_t id = tft.readID();
  if (id == 0xD3D3 || id == 0xFFFF || id == 0x0000) {
    id = 0x9486;
  }
  tft.begin(id);
  tft.setRotation(1);
  tft.fillScreen(C_BLACK);
  tft.setTextSize(2);
  tft.setTextWrap(false);
  pinMode(XM, OUTPUT);
  pinMode(YP, OUTPUT);
#endif
}

void clearDisplay() {
#if DISPLAY_BACKEND == DISPLAY_LCD1602
  lcd.clear();
#else
  tft.fillScreen(C_BLACK);
#endif
}

void showTextLine(uint8_t line, String text) {
#if DISPLAY_BACKEND == DISPLAY_LCD1602
  if (text.length() > 16) text = text.substring(0, 16);
  lcd.setCursor(0, line > 1 ? 1 : line);
  lcd.print("                ");
  lcd.setCursor(0, line > 1 ? 1 : line);
  lcd.print(text);
#else
  if (line == 0) uiLine1 = text;
  else uiLine2 = text;
#endif
}

void showText2Lines(String line1, String line2) {
#if DISPLAY_BACKEND == DISPLAY_LCD1602
  clearDisplay();
  showTextLine(0, line1);
  showTextLine(1, line2);
#else
  uiLine1 = line1;
  uiLine2 = line2;
#endif
}

#if DISPLAY_BACKEND == DISPLAY_TFT35
uint16_t calcSettingsChecksum(const PersistedSettings &s) {
  const uint8_t *p = (const uint8_t *)&s;
  uint16_t sum = 0;
  for (size_t i = 0; i < sizeof(PersistedSettings) - sizeof(uint16_t); i++) {
    sum = (uint16_t)(sum + p[i]);
  }
  return sum;
}

void applyDefaultSettings() {
  settings.magic = SETTINGS_MAGIC;
  settings.version = SETTINGS_VERSION;
  settings.ui_mode = MODE_BASIC;
  settings.brightness_level = 90;
  settings.serial_verbosity = 1;
  settings.io_guard_enabled = 1;
  settings.playground_enabled = 1;
  settings.ts_left = (uint16_t)TS_LEFT;
  settings.ts_right = (uint16_t)TS_RT;
  settings.ts_top = (uint16_t)TS_TOP;
  settings.ts_bottom = (uint16_t)TS_BOT;
  settings.checksum = calcSettingsChecksum(settings);
}

void loadSettings() {
  EEPROM.get(SETTINGS_EEPROM_ADDR, settings);
  bool valid = (settings.magic == SETTINGS_MAGIC) &&
               (settings.version == SETTINGS_VERSION) &&
               (settings.checksum == calcSettingsChecksum(settings));
  if (!valid) {
    applyDefaultSettings();
    saveSettings();
  }
}

void saveSettings() {
  settings.magic = SETTINGS_MAGIC;
  settings.version = SETTINGS_VERSION;
  settings.checksum = calcSettingsChecksum(settings);
  EEPROM.put(SETTINGS_EEPROM_ADDR, settings);
}

void applySettingsToRuntime() {
  TS_LEFT = settings.ts_left;
  TS_RT = settings.ts_right;
  TS_TOP = settings.ts_top;
  TS_BOT = settings.ts_bottom;
  if (settings.ui_mode > MODE_ADVANCED) settings.ui_mode = MODE_BASIC;
  if (settings.serial_verbosity > 2) settings.serial_verbosity = 1;
  if (settings.brightness_level > 100) settings.brightness_level = 100;
}

String pageName(UiPage p) {
  if (p == PAGE_HOME) return "HOME";
  if (p == PAGE_SETTINGS) return "SETTINGS";
  if (p == PAGE_DIAG) return "DIAG";
  return "MONITOR";
}

String modeName() {
  return settings.ui_mode == MODE_ADVANCED ? "ADVANCED" : "BASIC";
}

String verbosityName() {
  if (settings.serial_verbosity == 0) return "LOW";
  if (settings.serial_verbosity == 2) return "HIGH";
  return "MED";
}

void emitEvent(String category, String type, String value) {
  Serial.print("EVT,");
  Serial.print(category);
  Serial.print(",");
  Serial.print(type);
  Serial.print(",");
  Serial.println(value);
  lastEventText = category + "/" + type + ": " + value;
}

void emitWarn(String message) {
  Serial.print("EVT,WARN,");
  Serial.println(message);
  lastEventText = "WARN: " + message;
}

void emitSettingsChanged(String key, String value) {
  Serial.print("EVT,SETTING,CHANGED,");
  Serial.print(key);
  Serial.print(",");
  Serial.println(value);
  lastEventText = "SET " + key + "=" + value;
}

int freeRamEstimate() {
  extern int __heap_start, *__brkval;
  int v;
  return (int)&v - (__brkval == 0 ? (int)&__heap_start : (int)__brkval);
}

void emitDiagSnapshot() {
  emitEvent("DIAG", "TOUCH_RATE", String(touchRateHz));
  emitEvent("DIAG", "SERIAL_OK", (millis() - lastCommandMillis < 2500) ? "1" : "0");
  emitEvent("DIAG", "UPTIME_MS", String(millis()));
  emitEvent("DIAG", "FREE_RAM", String(freeRamEstimate()));
  emitEvent("DIAG", "IO_GUARD", settings.io_guard_enabled ? "1" : "0");
}

void drawButton(Btn b, uint16_t textColor, bool active) {
  uint16_t fill = active ? C_WHITE : b.color;
  uint16_t txt = active ? C_BLACK : textColor;
  tft.fillRoundRect(b.x + 2, b.y + 2, b.w, b.h, 8, C_BLACK);
  tft.fillRoundRect(b.x, b.y, b.w, b.h, 8, fill);
  tft.drawRoundRect(b.x, b.y, b.w, b.h, 8, C_WHITE);
  tft.setTextSize(2);
  tft.setTextColor(txt);
  int tx = b.x + (b.w / 2) - (b.label.length() * 6);
  int ty = b.y + 13;
  if (tx < b.x + 4) tx = b.x + 4;
  tft.setCursor(tx, ty);
  tft.print(b.label);
}

void animateButtonPress(Btn b) {
  tft.drawRoundRect(b.x - 1, b.y - 1, b.w + 2, b.h + 2, 8, C_WHITE);
  delay(35);
}

bool touchToScreenXY(int &sx, int &sy, int &rawX, int &rawY, int &pressure) {
  TSPoint p = ts.getPoint();
  pinMode(XM, OUTPUT);
  pinMode(YP, OUTPUT);

  pressure = p.z;
  rawX = p.x;
  rawY = p.y;

  if (p.z < TOUCH_MINPRESSURE || p.z > TOUCH_MAXPRESSURE) return false;

  // Most 3.5" MCUFRIEND shields in rotation(1) report X mirrored against
  // screen orientation unless this axis is inverted.
  sx = map(p.y, TS_BOT, TS_TOP, 0, 480);
  sy = map(p.x, TS_RT, TS_LEFT, 0, 320);

  if (sx < 0 || sx > 479 || sy < 0 || sy > 319) return false;
  return true;
}

bool pointInButton(int px, int py, Btn b) {
  return (px >= b.x && px < (b.x + b.w) && py >= b.y && py < (b.y + b.h));
}

void drawMessagePanel(String line1, String line2) {
  if (line1.length() > 36) line1 = line1.substring(0, 36);
  if (line2.length() > 36) line2 = line2.substring(0, 36);
  tft.fillRoundRect(12, 40, 456, 94, 8, C_PANEL);
  tft.drawRoundRect(12, 40, 456, 94, 8, C_CYAN);
  tft.setTextColor(C_WHITE);
  tft.setTextSize(2);
  tft.setCursor(24, 62);
  tft.print(line1);
  tft.setCursor(24, 94);
  tft.print(line2);
}

void drawStatusChip(String label, uint16_t color) {
  tft.fillRoundRect(14, 148, 150, 38, 7, color);
  tft.drawRoundRect(14, 148, 150, 38, 7, C_WHITE);
  tft.setTextColor(C_BLACK);
  tft.setTextSize(2);
  tft.setCursor(22, 160);
  tft.print(label);
}

void drawProgressBar(int percent, uint16_t color) {
  if (percent < 0) percent = 0;
  if (percent > 100) percent = 100;
  int x = 178;
  int y = 148;
  int w = 290;
  int h = 38;
  tft.drawRect(x, y, w, h, C_WHITE);
  tft.fillRect(x + 2, y + 2, w - 4, h - 4, C_PANEL);
  int fill = ((w - 4) * percent) / 100;
  if (fill > 0) tft.fillRect(x + 2, y + 2, fill, h - 4, color);
  tft.setTextSize(2);
  tft.setTextColor(C_BLACK);
  tft.setCursor(x + 8, y + 12);
  tft.print("PROGRESS");
  tft.setTextColor(C_WHITE);
  tft.setCursor(x + w - 56, y + 12);
  tft.print(percent);
  tft.print("%");
}

void drawFooterTicker() {
  tft.fillRect(0, 254, 480, 66, C_PANEL);
  tft.drawLine(0, 254, 479, 254, C_CYAN);
  tft.setTextColor(C_WHITE);
  tft.setTextSize(1);
  tft.setCursor(10, 266);
  String shortEvt = lastEventText;
  if (shortEvt.length() > 74) shortEvt = shortEvt.substring(0, 74);
  tft.print(shortEvt);
  tft.setCursor(10, 282);
  tft.print("Mode:");
  tft.print(modeName());
  tft.print(" | Guard:");
  tft.print(settings.io_guard_enabled ? "ON" : "OFF");
  tft.print(" | Touch:");
  tft.print(settings.playground_enabled ? "ON" : "OFF");
}

void drawTabs() {
  drawButton(tabHome, C_BLACK, activePage == PAGE_HOME);
  drawButton(tabSettings, C_BLACK, activePage == PAGE_SETTINGS);
  if (settings.ui_mode == MODE_ADVANCED) {
    drawButton(tabDiag, C_BLACK, activePage == PAGE_DIAG);
    drawButton(tabMonitor, C_BLACK, activePage == PAGE_MONITOR);
  } else {
    Btn diagDisabled = tabDiag;
    Btn monDisabled = tabMonitor;
    diagDisabled.color = C_GRAY;
    monDisabled.color = C_GRAY;
    drawButton(diagDisabled, C_WHITE, false);
    drawButton(monDisabled, C_WHITE, false);
  }
}

void renderMainUI() {
  tft.fillScreen(C_NAVY);
  tft.drawRect(0, 0, 480, 320, C_CYAN);
  tft.fillRect(0, 0, 480, 30, C_CYAN);
  tft.setCursor(10, 8);
  tft.setTextColor(C_BLACK);
  tft.setTextSize(2);
  tft.print("IC Tester Control Deck");
  tft.setTextSize(1);
  tft.setCursor(340, 10);
  tft.print("Mega TFT v6");
}

void renderHomePage() {
  drawMessagePanel(uiLine1, uiLine2);
  drawStatusChip(uiStatus, uiStatusColor);
  drawProgressBar(demoProgress, testInProgress ? C_YELLOW : C_CYAN);

  drawButton(btnPass);
  drawButton(btnFail, C_WHITE);
  drawButton(btnLed);
  drawButton(btnPulse);

  drawFooterTicker();
  drawTabs();
}

void renderSettingsPage() {
  drawMessagePanel("Settings", "Display / Touch / System");
  drawStatusChip("SETTINGS", C_MINT);
  drawProgressBar(settings.brightness_level, C_YELLOW);

  setModeBtn.label = "MODE:" + modeName();
  setVerbBtn.label = "VERB:" + verbosityName();
  setGuardBtn.label = String("GUARD:") + (settings.io_guard_enabled ? "ON" : "OFF");

  drawButton(setModeBtn);
  drawButton(setVerbBtn);
  drawButton(setGuardBtn);

  setBrightDn.label = "B-";
  setBrightUp.label = "B+";
  setCalDn.label = "T-";
  setCalUp.label = "T+";

  drawButton(setBrightDn, C_WHITE);
  drawButton(setBrightUp, C_WHITE);
  drawButton(setCalDn, C_WHITE);
  drawButton(setCalUp, C_WHITE);
  drawButton(setSaveBtn, C_BLACK);
  drawButton(setRevertBtn, C_WHITE);

  tft.setTextSize(1);
  tft.setTextColor(C_WHITE);
  tft.setCursor(16, 260);
  tft.print("SD: Not enabled | Sound: Not enabled | Save writes EEPROM");
  drawTabs();
}

void renderDiagnosticsPage() {
  drawMessagePanel("Diagnostics", "Live board and touch metrics");

  bool serialOk = (millis() - lastCommandMillis < 2500);
  drawStatusChip(serialOk ? "SERIAL OK" : "LINK LOST", serialOk ? C_GREEN : C_RED);
  drawProgressBar((int)touchRateHz, C_CYAN);

  tft.setTextColor(C_WHITE);
  tft.setTextSize(2);
  tft.setCursor(18, 198);
  tft.print("Touch Hz:"); tft.print(touchRateHz);
  tft.setCursor(18, 220);
  tft.print("Uptime s:"); tft.print((unsigned long)(millis() / 1000UL));

  tft.setTextSize(1);
  tft.setCursor(250, 198);
  tft.print("Free RAM:"); tft.print(freeRamEstimate());
  tft.setCursor(250, 214);
  tft.print("Verbosity:"); tft.print(verbosityName());
  tft.setCursor(250, 230);
  tft.print("IO Guard:"); tft.print(settings.io_guard_enabled ? "ON" : "OFF");
  tft.setCursor(250, 246);
  tft.print("Touch XY:");
  tft.print(lastTouchX);
  tft.print("/");
  tft.print(lastTouchY);
  tft.setCursor(250, 260);
  tft.print("Raw:");
  tft.print(lastRawX);
  tft.print("/");
  tft.print(lastRawY);
  tft.print(" P:");
  tft.print(lastPressure);

  drawFooterTicker();
  drawTabs();
}

void renderMonitorPage() {
  drawMessagePanel("I/O Monitor", "Safe pin inspection/control");

  int currentPin = TFT_ALLOWED_PINS[monitorPinIndex];
  drawStatusChip(String("PIN ") + String(currentPin), C_CYAN);

  int value = digitalRead(currentPin);
  drawProgressBar(value == HIGH ? 100 : 0, value == HIGH ? C_GREEN : C_GRAY);

  monModePin.label = monitorPinOutputMode ? "OUT" : "IN";
  drawButton(monPrevPin, C_WHITE);
  drawButton(monNextPin, C_WHITE);
  drawButton(monReadPin);
  drawButton(monTogglePin, C_BLACK);
  drawButton(monModePin);

  tft.setTextSize(1);
  tft.setTextColor(C_WHITE);
  tft.setCursor(16, 260);
  tft.print("Guard blocks invalid pins and unsafe writes during tests.");
  drawTabs();
}

void renderActivePage() {
  renderMainUI();
  if (settings.ui_mode == MODE_BASIC &&
      activePage != PAGE_HOME &&
      activePage != PAGE_SETTINGS) {
    activePage = PAGE_HOME;
  }

  if (activePage == PAGE_HOME) renderHomePage();
  else if (activePage == PAGE_SETTINGS) renderSettingsPage();
  else if (activePage == PAGE_DIAG) renderDiagnosticsPage();
  else renderMonitorPage();
}

void touchNavigate(int x, int y) {
  UiPage prev = activePage;
  if (pointInButton(x, y, tabHome)) {
    activePage = PAGE_HOME;
  } else if (pointInButton(x, y, tabSettings)) {
    activePage = PAGE_SETTINGS;
  } else if (settings.ui_mode == MODE_ADVANCED && pointInButton(x, y, tabDiag)) {
    activePage = PAGE_DIAG;
  } else if (settings.ui_mode == MODE_ADVANCED && pointInButton(x, y, tabMonitor)) {
    activePage = PAGE_MONITOR;
  }

  if (activePage != prev) {
    emitEvent("TOUCH", "PAGE", pageName(activePage));
    renderActivePage();
  }
}

void handleHomeTouch(int x, int y) {
  if (pointInButton(x, y, btnPass)) {
    animateButtonPress(btnPass);
    demoProgress = 100;
    testInProgress = false;
    uiStatus = "PASS";
    uiStatusColor = C_GREEN;
    showText2Lines("* TOUCH PASS *", "UI Demo GOOD");
    emitEvent("TOUCH", "ACTION", "PASS");
    renderActivePage();
    return;
  }
  if (pointInButton(x, y, btnFail)) {
    animateButtonPress(btnFail);
    demoProgress = 100;
    testInProgress = false;
    uiStatus = "FAIL";
    uiStatusColor = C_RED;
    showText2Lines("* TOUCH FAIL *", "UI Demo BAD");
    emitEvent("TOUCH", "ACTION", "FAIL");
    renderActivePage();
    return;
  }
  if (pointInButton(x, y, btnLed)) {
    animateButtonPress(btnLed);
    ledState = !ledState;
    digitalWrite(LED_PIN, ledState ? HIGH : LOW);
    uiStatus = ledState ? "LED ON" : "LED OFF";
    uiStatusColor = C_MINT;
    showText2Lines("LED Toggled", ledState ? "ON" : "OFF");
    emitEvent("TOUCH", "ACTION", ledState ? "LED_ON" : "LED_OFF");
    renderActivePage();
    return;
  }
  if (pointInButton(x, y, btnPulse)) {
    animateButtonPress(btnPulse);
    testInProgress = true;
    uiStatus = "TESTING";
    uiStatusColor = C_ORANGE;
    showText2Lines("Pulse Demo", "Animating...");
    renderActivePage();
    for (int p = 0; p <= 100; p += 10) {
      demoProgress = p;
      drawProgressBar(demoProgress, C_YELLOW);
      delay(55);
    }
    testInProgress = false;
    uiStatus = "READY";
    uiStatusColor = C_GREEN;
    emitEvent("TOUCH", "ACTION", "PULSE");
    renderActivePage();
  }
}

void handleSettingsTouch(int x, int y) {
  if (pointInButton(x, y, setModeBtn)) {
    settings.ui_mode = (settings.ui_mode == MODE_BASIC) ? MODE_ADVANCED : MODE_BASIC;
    applySettingsToRuntime();
    emitSettingsChanged("ui_mode", modeName());
    renderActivePage();
    return;
  }
  if (pointInButton(x, y, setVerbBtn)) {
    settings.serial_verbosity = (settings.serial_verbosity + 1) % 3;
    emitSettingsChanged("serial_verbosity", verbosityName());
    renderActivePage();
    return;
  }
  if (pointInButton(x, y, setGuardBtn)) {
    settings.io_guard_enabled = settings.io_guard_enabled ? 0 : 1;
    emitSettingsChanged("io_guard_enabled", settings.io_guard_enabled ? "1" : "0");
    renderActivePage();
    return;
  }
  if (pointInButton(x, y, setBrightDn)) {
    if (settings.brightness_level >= 5) settings.brightness_level -= 5;
    emitSettingsChanged("brightness_level", String(settings.brightness_level));
    renderActivePage();
    return;
  }
  if (pointInButton(x, y, setBrightUp)) {
    if (settings.brightness_level <= 95) settings.brightness_level += 5;
    emitSettingsChanged("brightness_level", String(settings.brightness_level));
    renderActivePage();
    return;
  }
  if (pointInButton(x, y, setCalDn)) {
    settings.ts_left = settings.ts_left > 10 ? settings.ts_left - 10 : settings.ts_left;
    settings.ts_top = settings.ts_top > 10 ? settings.ts_top - 10 : settings.ts_top;
    applySettingsToRuntime();
    emitSettingsChanged("touch_cal", "-10");
    renderActivePage();
    return;
  }
  if (pointInButton(x, y, setCalUp)) {
    settings.ts_left += 10;
    settings.ts_top += 10;
    applySettingsToRuntime();
    emitSettingsChanged("touch_cal", "+10");
    renderActivePage();
    return;
  }
  if (pointInButton(x, y, setSaveBtn)) {
    saveSettings();
    settingsShadow = settings;
    emitEvent("SETTING", "SAVED", "1");
    renderActivePage();
    return;
  }
  if (pointInButton(x, y, setRevertBtn)) {
    settings = settingsShadow;
    applySettingsToRuntime();
    emitEvent("SETTING", "REVERT", "1");
    renderActivePage();
    return;
  }
}

void handleDiagTouch(int x, int y, int rawX, int rawY, int pressure) {
  (void)x;
  (void)y;
  emitEvent("DIAG", "TOUCH_RAW", String(rawX) + "/" + String(rawY) + "/" + String(pressure));
  emitDiagSnapshot();
  renderActivePage();
}

void handleMonitorTouch(int x, int y) {
  int currentPin = TFT_ALLOWED_PINS[monitorPinIndex];

  if (pointInButton(x, y, monPrevPin)) {
    if (monitorPinIndex > 0) monitorPinIndex--;
    emitEvent("TOUCH", "ACTION", "MON_PREV");
    renderActivePage();
    return;
  }
  if (pointInButton(x, y, monNextPin)) {
    if (monitorPinIndex < TFT_ALLOWED_PINS_COUNT - 1) monitorPinIndex++;
    emitEvent("TOUCH", "ACTION", "MON_NEXT");
    renderActivePage();
    return;
  }
  if (pointInButton(x, y, monModePin)) {
    monitorPinOutputMode = !monitorPinOutputMode;
    pinMode(currentPin, monitorPinOutputMode ? OUTPUT : INPUT);
    emitEvent("TOUCH", "ACTION", monitorPinOutputMode ? "MON_MODE_OUT" : "MON_MODE_IN");
    renderActivePage();
    return;
  }
  if (pointInButton(x, y, monReadPin)) {
    pinMode(currentPin, INPUT);
    int st = digitalRead(currentPin);
    emitEvent("TOUCH", "ACTION", String("MON_READ_") + (st == HIGH ? "HIGH" : "LOW"));
    renderActivePage();
    return;
  }
  if (pointInButton(x, y, monTogglePin)) {
    if (testInProgress) {
      emitWarn("monitor blocked while testing");
      return;
    }
    if (settings.io_guard_enabled && !monitorPinOutputMode) {
      emitWarn("set mode OUT first");
      return;
    }
    pinMode(currentPin, OUTPUT);
    int st = digitalRead(currentPin);
    digitalWrite(currentPin, st == HIGH ? LOW : HIGH);
    emitEvent("TOUCH", "ACTION", String("MON_TOGGLE_PIN_") + String(currentPin));
    renderActivePage();
    return;
  }
}

void handleTouchUI() {
  int x = 0, y = 0, rx = 0, ry = 0, pz = 0;
  if (!touchToScreenXY(x, y, rx, ry, pz)) return;
  if (millis() - lastTouchTime < TOUCH_DEBOUNCE_MS) return;
  lastTouchTime = millis();
  touchCountInWindow++;
  lastTouchX = x;
  lastTouchY = y;
  lastRawX = rx;
  lastRawY = ry;
  lastPressure = pz;

  touchNavigate(x, y);

  if (activePage == PAGE_HOME) handleHomeTouch(x, y);
  else if (activePage == PAGE_SETTINGS) handleSettingsTouch(x, y);
  else if (activePage == PAGE_DIAG) handleDiagTouch(x, y, rx, ry, pz);
  else handleMonitorTouch(x, y);
}
#endif
