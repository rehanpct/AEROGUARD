#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <Adafruit_BME280.h>
#include <Adafruit_MPU6050.h>
#include <TinyGPS++.h>

// ---------------- WIFI CONFIG ----------------
const char* ssid = "Rehan_iphone";
const char* password = "Netvenotharalo";
const char* serverName = "http://172.20.10.2:5000/api/telemetry";

// ---------------- PIN DEFINITIONS ----------------

// I2C
#define SDA_PIN 21
#define SCL_PIN 22

// Ultrasonic
#define TRIG 26
#define ECHO 27

// Digital Sensors
#define IR_PIN 25
#define PIR_PIN 14

// Analog Sensors
#define LDR_PIN 34
#define WATER_PIN 35
#define ACS_PIN 36

// Outputs
#define RELAY_PIN 33
#define BUZZER_PIN 32
#define LED_GREEN 18
#define LED_YELLOW 19
#define LED_RED 23

// GPS
TinyGPSPlus gps;
HardwareSerial gpsSerial(2);

// I2C Devices
Adafruit_BME280 bme;
Adafruit_MPU6050 mpu;

// ACS Calibration
float zeroOffset = 2.00;
float sensitivity = 0.185;

// ---------------- FUNCTIONS ----------------

int readWaterAverage() {
  long sum = 0;
  for (int i = 0; i < 20; i++) {
    sum += analogRead(WATER_PIN);
    delay(3);
  }
  return sum / 20;
}

float readUltrasonic() {
  digitalWrite(TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG, LOW);

  long duration = pulseIn(ECHO, HIGH, 30000);
  if (duration == 0) return -1;
  return duration * 0.034 / 2;
}

float readCurrent() {
  int raw = analogRead(ACS_PIN);
  float voltage = raw * (3.3 / 4095.0);
  return (voltage - zeroOffset) / sensitivity;
}

// ---------------- SETUP ----------------

void setup() {

  Serial.begin(115200);

  // WiFi
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi Connected");
    Serial.print("ESP32 IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nWiFi Failed (will retry in loop)");
  }

  Wire.begin(SDA_PIN, SCL_PIN);

  if (!bme.begin(0x77)) {
    Serial.println("BME280 NOT DETECTED");
  }

  if (!mpu.begin()) {
    Serial.println("MPU6050 NOT DETECTED");
  }

  gpsSerial.begin(9600, SERIAL_8N1, 16, 17);

  pinMode(TRIG, OUTPUT);
  pinMode(ECHO, INPUT);
  pinMode(IR_PIN, INPUT);
  pinMode(PIR_PIN, INPUT);

  pinMode(RELAY_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_YELLOW, OUTPUT);
  pinMode(LED_RED, OUTPUT);

  digitalWrite(RELAY_PIN, LOW);
}

// ---------------- LOOP ----------------

// Non-blocking 2-second send gate (replaces delay(2000))
static unsigned long lastSendTime = 0;
const unsigned long SEND_INTERVAL = 2000;

void loop() {

  // -------- SENSOR READINGS --------
  float temperature = bme.readTemperature();
  float humidity = bme.readHumidity();
  float pressure = bme.readPressure() / 100.0F;

  if (isnan(temperature)) temperature = 0;
  if (isnan(humidity)) humidity = 0;
  if (isnan(pressure)) pressure = 0;

  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);

  float accX = a.acceleration.x;
  float accY = a.acceleration.y;
  float accZ = a.acceleration.z;
  float gyroX = g.gyro.x;
  float gyroY = g.gyro.y;
  float gyroZ = g.gyro.z;

  // ----- REAL TILT -----
  float tilt = atan2(accX, accZ) * 180.0 / PI;
  tilt = abs(tilt);

  // -------- GPS READ --------
  while (gpsSerial.available()) {
    gps.encode(gpsSerial.read());
  }

  double latitude = 0;
  double longitude = 0;
  float hdop = 0;
  int satellites = 0;

  if (gps.location.isValid()) {
    latitude = gps.location.lat();
    longitude = gps.location.lng();
  }

  if (gps.hdop.isValid()) {
    hdop = gps.hdop.hdop();
  }

  if (gps.satellites.isValid()) {
    satellites = gps.satellites.value();
  }

  float distance = readUltrasonic();
  int ir = digitalRead(IR_PIN);
  int pir = digitalRead(PIR_PIN);
  int ldr = analogRead(LDR_PIN);
  int water = readWaterAverage();
  float current = readCurrent();

  // -------- RISK LOGIC --------
  bool unsafe = false;
  bool caution = false;

  if (water > 300) unsafe = true;      // was 2000 – aligns with backend WATER_UNSAFE
  if (tilt > 10) unsafe = true;         // was 15 – aligns with backend TILT_UNSAFE
  if (abs(current) > 2.5) unsafe = true; // was 3.0A – triggers sooner

  if (gps.satellites.isValid() && satellites < 3) caution = true;
  if (hdop > 3.5) caution = true;

  if (distance > 0 && distance < 15) caution = true;  // was 10cm – wider proximity zone
  if (ldr > 3000) caution = true;
  if (pir == HIGH) caution = true;

  // IR ACTIVE LOW
  if (ir == LOW) caution = true;

  if (unsafe) {
    digitalWrite(LED_RED, HIGH);
    digitalWrite(LED_GREEN, LOW);
    digitalWrite(LED_YELLOW, LOW);
    digitalWrite(RELAY_PIN, HIGH);
    tone(BUZZER_PIN, 2000);
  }
  else if (caution) {
    digitalWrite(LED_YELLOW, HIGH);
    digitalWrite(LED_GREEN, LOW);
    digitalWrite(LED_RED, LOW);
    digitalWrite(RELAY_PIN, LOW);
    noTone(BUZZER_PIN);
  }
  else {
    digitalWrite(LED_GREEN, HIGH);
    digitalWrite(LED_YELLOW, LOW);
    digitalWrite(LED_RED, LOW);
    digitalWrite(RELAY_PIN, LOW);
    noTone(BUZZER_PIN);
  }

  // -------- SEND TO BACKEND --------
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi Lost. Reconnecting...");
    WiFi.reconnect();
    delay(1000);
    return;
  }

  HTTPClient http;
  http.begin(serverName);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(1500);  // reduced from 5000ms to prevent long stalls

  String json = "{";
  json += "\"temperature\":" + String(temperature,2) + ",";
  json += "\"humidity\":" + String(humidity,2) + ",";
  json += "\"pressure\":" + String(pressure,2) + ",";
  json += "\"accX\":" + String(accX,2) + ",";
  json += "\"accY\":" + String(accY,2) + ",";
  json += "\"accZ\":" + String(accZ,2) + ",";
  json += "\"gyroX\":" + String(gyroX,2) + ",";
  json += "\"gyroY\":" + String(gyroY,2) + ",";
  json += "\"gyroZ\":" + String(gyroZ,2) + ",";
  json += "\"distance\":" + String(distance,2) + ",";
  json += "\"ldr\":" + String(ldr) + ",";
  json += "\"water\":" + String(water) + ",";
  json += "\"current\":" + String(current,2) + ",";
  json += "\"ir\":" + String(ir) + ",";
  json += "\"pir\":" + String(pir) + ",";
  json += "\"satellites\":" + String(satellites) + ",";
  json += "\"hdop\":" + String(hdop,2) + ",";
  json += "\"latitude\":" + String(latitude,6) + ",";
  json += "\"longitude\":" + String(longitude,6);
  json += "}";

  Serial.println("Sending JSON:");
  Serial.println(json);

  int httpResponseCode = http.POST(json);

  if (httpResponseCode > 0) {
    Serial.print("HTTP Response Code: ");
    Serial.println(httpResponseCode);

    String response = http.getString();
    if (response.length() > 0) {
      Serial.print("Backend Response: ");
      Serial.println(response);
    }
  } else {
    Serial.print("HTTP Error: ");
    Serial.println(http.errorToString(httpResponseCode));
  }

  http.end();

  // Non-blocking timing gate: wait until SEND_INTERVAL ms have elapsed
  // since the last send before executing the loop body again.
  while (millis() - lastSendTime < SEND_INTERVAL) {
    yield();  // allow WiFi stack to run while waiting
  }
  lastSendTime = millis();
}