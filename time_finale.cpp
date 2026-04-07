#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Arduino.h>
#include <Adafruit_PWMServoDriver.h>

// ── Configuration ────────────────────────────────────────────────────
const char* ssid     = "Vodafon-C47560720";          // WiFi SSID
const char* password = "YYAK4NYpPkmtpYY3";          // WiFi password
const char* SERVER   = "http://192.168.1.185:8077";  // <-- IP del tuo server

const unsigned long POLL_INTERVAL_MS = 30000;  // poll ogni 30 secondi

// ── Hardware ─────────────────────────────────────────────────────────
Adafruit_PWMServoDriver pwmH = Adafruit_PWMServoDriver(0x40);
Adafruit_PWMServoDriver pwmM = Adafruit_PWMServoDriver(0x41);

// ── Servo positions (aggiornate dal server al boot e quando cambiano) ─
int segmentHOn[14]  = {100,310,300,300,100,130, 95, 100,300,300,300,100,110,120};
int segmentHOff[14] = {300,100,100,100,300,320,300, 300,100,100,100,300,300,300};
int segmentMOn[14]  = { 90,310,300,300,100,100, 80, 100,310,300,300, 90,100,130};
int segmentMOff[14] = {300,100,100,100,300,300,300, 300,100,100,100,300,320,300};

int digits[10][7] = {
  {1,1,1,1,1,1,0},{0,1,1,0,0,0,0},{1,1,0,1,1,0,1},{1,1,1,1,0,0,1},
  {0,1,1,0,0,1,1},{1,0,1,1,0,1,1},{1,0,1,1,1,1,1},{1,1,1,0,0,0,0},
  {1,1,1,1,1,1,1},{1,1,1,1,0,1,1}
};

// ── Display state ────────────────────────────────────────────────────
int hourTens    = 0,  hourUnits    = 0;
int minuteTens  = 0,  minuteUnits  = 0;
int prevHourTens   = 8, prevHourUnits   = 8;
int prevMinuteTens = 8, prevMinuteUnits = 8;

int midOffset   = 150;
int time_delay  = 100;
int time_delay2 = 20;

// ── Runtime state ────────────────────────────────────────────────────
int  lastConfigVersion = -1;
unsigned long lastPoll = 0;

// ── Forward declarations ──────────────────────────────────────────────
void updateDisplay();
void updateMid();
void ensureWiFi();
void fetchServoConfig();
void fetchClockData();
void doAlarmAnimation();

// ═════════════════════════════════════════════════════════════════════
void setup() {
  pinMode(2, OUTPUT);
  digitalWrite(2, HIGH);   // LED on during boot

  Serial.begin(115200);
  delay(500);
  
  Serial.println("\n\n========== WallClock BOOT ==========");
  Serial.printf("SSID: %s | Server: %s\n", ssid, SERVER);

  // Init PCA9685 boards
  Serial.println("[BOOT] Initializing PCA9685 boards (0x40, 0x41)...");
  pwmH.begin();
  pwmH.setPWMFreq(50);
  pwmH.setOscillatorFrequency(27000000);
  pwmM.begin();
  pwmM.setPWMFreq(50);
  pwmM.setOscillatorFrequency(27000000);
  Serial.println("[BOOT] ✓ PCA9685 init done");

  // All segments off
  Serial.println("[BOOT] Setting all segments to OFF...");
  for (int i = 0; i < 14; i++) {
    pwmH.setPWM(i, 0, segmentHOff[i]); delay(10);
    pwmM.setPWM(i, 0, segmentMOff[i]); delay(10);
  }
  Serial.println("[BOOT] ✓ All segments OFF");

  // Connect WiFi and get initial data
  Serial.println("[BOOT] Fetching WiFi connection...");
  ensureWiFi();
  Serial.println("[BOOT] Fetching initial clock data (servo config included)...");
  fetchClockData();
  Serial.println("[BOOT] ═══ BOOT COMPLETE ═══\n");
  lastPoll = millis();
}

// ═════════════════════════════════════════════════════════════════════
void loop() {
  unsigned long elapsed = millis() - lastPoll;
  if (elapsed >= POLL_INTERVAL_MS) {
    Serial.printf("\n[POLL] Elapsed %lums — fetching new data...\n", elapsed);
    ensureWiFi();
    fetchClockData();
    lastPoll = millis();
  }
  delay(500);
}

// ─── WiFi ─────────────────────────────────────────────────────────────
void ensureWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[WiFi] ✓ Already connected (RSSI: %d dBm)\n", WiFi.RSSI());
    return;
  }

  Serial.printf("[WiFi] Disconnected, reconnecting to '%s'", ssid);
  WiFi.disconnect(true);
  WiFi.mode(WIFI_STA);
  delay(100);
  WiFi.begin(ssid, password);
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) {
    delay(500);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf(" ✓ OK (IP: %s, RSSI: %d dBm)\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
    digitalWrite(2, LOW);   // LED off = connected
  } else {
    Serial.println(" ✗ FAILED");
    digitalWrite(2, HIGH);  // LED on = error
  }
}

// ─── Fetch servo config from server ───────────────────────────────────
void fetchServoConfig() {
  Serial.print(String("[servo-config] Fetching from ") + SERVER + "/api/servo-config...");
  
  HTTPClient http;
  http.begin(String(SERVER) + "/api/servo-config");
  http.setTimeout(5000);
  int code = http.GET();

  if (code != 200) {
    Serial.printf(" ✗ HTTP %d\n", code);
    http.end();
    return;
  }

  String body = http.getString();
  http.end();

  JsonDocument doc;
  if (deserializeJson(doc, body)) {
    Serial.println(" ✗ JSON parse error");
    return;
  }

  // Parse configurazione
  for (int i = 0; i < 14; i++) {
    segmentHOn[i]  = doc["h_on"][i].as<int>();
    segmentHOff[i] = doc["h_off"][i].as<int>();
    segmentMOn[i]  = doc["m_on"][i].as<int>();
    segmentMOff[i] = doc["m_off"][i].as<int>();
  }
  midOffset   = doc["mid_offset"].as<int>();
  time_delay  = doc["time_delay"].as<int>();
  time_delay2 = doc["time_delay2"].as<int>();

  Serial.printf(" ✓ OK\n");
  Serial.printf("[servo-config]   mid_offset=%d  time_delay=%d  time_delay2=%d\n",
                midOffset, time_delay, time_delay2);
}

// ─── Fetch clock data and update display if needed ────────────────────
void fetchClockData() {
  Serial.print(String("[clock] Fetching from ") + SERVER + "/api/clock...");
  
  HTTPClient http;
  http.begin(String(SERVER) + "/api/clock");
  http.setTimeout(5000);
  int code = http.GET();

  if (code != 200) {
    Serial.printf(" ✗ HTTP %d\n", code);
    http.end();
    return;
  }

  String body = http.getString();
  http.end();

  JsonDocument doc;
  if (deserializeJson(doc, body)) {
    Serial.println(" ✗ JSON parse error");
    return;
  }

  Serial.println(" ✓ OK");

  // Refresh servo config if version changed
  int configVer = doc["config_version"].as<int>();
  if (configVer != lastConfigVersion) {
    Serial.printf("[clock] Config version changed: %d → %d, fetching new servo config...\n", 
                  lastConfigVersion, configVer);
    fetchServoConfig();
    lastConfigVersion = configVer;
  }

  bool active = doc["active"].as<bool>();
  if (!active) {
    Serial.println("[clock] ⚠️  INACTIVE — skipping display update");
    return;
  }

  String mode = doc["mode"].as<String>();

  if (mode == "alarm_ringing") {
    Serial.println("[clock] 🔔 ALARM_RINGING mode — running 88:88 ↔ 00:00 animation");
    doAlarmAnimation();
    return;
  }

  int newHour   = doc["hour"].as<int>();
  int newMinute = doc["minute"].as<int>();

  int newHT = newHour   / 10;
  int newHU = newHour   % 10;
  int newMT = newMinute / 10;
  int newMU = newMinute % 10;

  // Debug: mostra se l'ora è cambiata
  if (newHT != prevHourTens   || newHU != prevHourUnits ||
      newMT != prevMinuteTens || newMU != prevMinuteUnits) {

    Serial.printf("[clock] Time changed: %02d:%02d → %02d:%02d (mode=%s)\n",
                  prevHourTens*10 + prevHourUnits, prevMinuteTens*10 + prevMinuteUnits,
                  newHour, newMinute, mode.c_str());
    Serial.printf("[clock] Digit breakdown: HT=%d HU=%d MT=%d MU=%d\n",
                  newHT, newHU, newMT, newMU);

    hourTens    = newHT;
    hourUnits   = newHU;
    minuteTens  = newMT;
    minuteUnits = newMU;

    Serial.println("[clock] Calling updateDisplay()...");
    updateDisplay();
    Serial.println("[clock] ✓ updateDisplay() complete");

    prevHourTens    = hourTens;
    prevHourUnits   = hourUnits;
    prevMinuteTens  = minuteTens;
    prevMinuteUnits = minuteUnits;
  } else {
    Serial.printf("[clock] No change: %02d:%02d\n", newHour, newMinute);
  }
}

// ─── Alarm animation: 88:88 ↔ 00:00 loop ─────────────────────────────
void doAlarmAnimation() {
  Serial.println("[alarm] Starting 88:88 ↔ 00:00 animation (5 cycles)...");
  
  for (int rep = 0; rep < 5; rep++) {
    Serial.printf("[alarm] Cycle %d/5: 88:88\n", rep + 1);
    hourTens    = 8; hourUnits    = 8;
    minuteTens  = 8; minuteUnits  = 8;
    updateDisplay();
    prevHourTens = 8; prevHourUnits = 8;
    prevMinuteTens = 8; prevMinuteUnits = 8;
    delay(700);

    Serial.printf("[alarm] Cycle %d/5: 00:00\n", rep + 1);
    hourTens    = 0; hourUnits    = 0;
    minuteTens  = 0; minuteUnits  = 0;
    updateDisplay();
    prevHourTens = 0; prevHourUnits = 0;
    prevMinuteTens = 0; prevMinuteUnits = 0;
    delay(700);
  }
  
  Serial.println("[alarm] ✓ Animation complete");
}

// ═════════════════════════════════════════════════════════════════════
// Servo movement code – unchanged from original
// ═════════════════════════════════════════════════════════════════════

void updateDisplay() {
  Serial.printf("[display] Updating segments for %d%d:%d%d\n",
                hourTens, hourUnits, minuteTens, minuteUnits);
  
  updateMid();

  for (int i = 0; i <= 5; i++) {
    // Hour tens (channels 7-12)
    if (digits[hourTens][i] == 1)
      pwmH.setPWM(i + 7, 0, segmentHOn[i + 7]);
    else
      pwmH.setPWM(i + 7, 0, segmentHOff[i + 7]);
    delay(time_delay2);

    // Hour units (channels 0-5)
    if (digits[hourUnits][i] == 1)
      pwmH.setPWM(i, 0, segmentHOn[i]);
    else
      pwmH.setPWM(i, 0, segmentHOff[i]);
    delay(time_delay2);

    // Minute tens (channels 7-12)
    if (digits[minuteTens][i] == 1)
      pwmM.setPWM(i + 7, 0, segmentMOn[i + 7]);
    else
      pwmM.setPWM(i + 7, 0, segmentMOff[i + 7]);
    delay(time_delay2);

    // Minute units (channels 0-5)
    if (digits[minuteUnits][i] == 1)
      pwmM.setPWM(i, 0, segmentMOn[i]);
    else
      pwmM.setPWM(i, 0, segmentMOff[i]);
    delay(time_delay2);
  }
}

void updateMid() {
  // Move adjacent segments for Minute units
  if (digits[minuteUnits][6] != digits[prevMinuteUnits][6]) {
    if (digits[prevMinuteUnits][1] == 1)
      pwmM.setPWM(1, 0, segmentMOn[1] - midOffset);
    if (digits[prevMinuteUnits][5] == 1)
      pwmM.setPWM(5, 0, segmentMOn[5] + midOffset);
  }
  delay(time_delay);
  if (digits[minuteUnits][6] == 1)
    pwmM.setPWM(6, 0, segmentMOn[6]);
  else
    pwmM.setPWM(6, 0, segmentMOff[6]);

  // Move adjacent segments for Minute tens
  if (digits[minuteTens][6] != digits[prevMinuteTens][6]) {
    if (digits[prevMinuteTens][1] == 1)
      pwmM.setPWM(8, 0, segmentMOn[8] - midOffset);
    if (digits[prevMinuteTens][5] == 1)
      pwmM.setPWM(12, 0, segmentMOn[12] + midOffset);
  }
  delay(time_delay);
  if (digits[minuteTens][6] == 1)
    pwmM.setPWM(13, 0, segmentMOn[13]);
  else
    pwmM.setPWM(13, 0, segmentMOff[13]);

  // Move adjacent segments for Hour units
  if (digits[hourUnits][6] != digits[prevHourUnits][6]) {
    if (digits[prevHourUnits][1] == 1)
      pwmH.setPWM(1, 0, segmentHOn[1] - midOffset);
    if (digits[prevHourUnits][5] == 1)
      pwmH.setPWM(5, 0, segmentHOn[5] + midOffset);
  }
  delay(time_delay);
  if (digits[hourUnits][6] == 1)
    pwmH.setPWM(6, 0, segmentHOn[6]);
  else
    pwmH.setPWM(6, 0, segmentHOff[6]);

  // Move adjacent segments for Hour tens
  if (digits[hourTens][6] != digits[prevHourTens][6]) {
    if (digits[prevHourTens][1] == 1)
      pwmH.setPWM(8, 0, segmentHOn[8] - midOffset);
    if (digits[prevHourTens][5] == 1)
      pwmH.setPWM(12, 0, segmentHOn[12] + midOffset);
  }
  delay(time_delay);
  if (digits[hourTens][6] == 1)
    pwmH.setPWM(13, 0, segmentHOn[13]);
  else
    pwmH.setPWM(13, 0, segmentHOff[13]);
  delay(time_delay);
}
