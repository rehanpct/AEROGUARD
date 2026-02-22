/*
 * ============================================================
 *  AeroGuard – ESP32 Telemetry Firmware
 *  Reads all sensors and POSTs JSON to Flask backend
 * ============================================================
 *
 *  Libraries required (install via Arduino Library Manager):
 *    - Adafruit BME280 (+ Adafruit Unified Sensor)
 *    - MPU6050 by Electronic Cats  (or I2Cdevlib MPU6050)
 *    - TinyGPS++ by Mikal Hart
 *    - ArduinoJson by Benoit Blanchon  (v6.x)
 *
 *  Board: "ESP32 Dev Module" (or your specific ESP32 board)
 *
 *  Pin Map
 *  ──────────────────────────────────────────────
 *  BME280        SDA=21  SCL=22   (I²C)
 *  MPU6050       SDA=21  SCL=22   (I²C, same bus)
 *  Ultrasonic    TRIG=5  ECHO=18
 *  LDR           GPIO34  (Analog – no pull-up needed on 34/35/36/39)
 *  Water sensor  GPIO35  (Analog)
 *  ACS712 / INA  GPIO32  (Analog current sensor)
 *  IR obstacle   GPIO14  (Digital, LOW = obstacle)
 *  PIR motion    GPIO27  (Digital, HIGH = motion)
 *  GPS (NEO-6M)  RX2=16  TX2=17  (UART2)
 *  ──────────────────────────────────────────────
 */

// ── Includes ──────────────────────────────────────────────────────────────────
#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <Adafruit_BME280.h>
#include <MPU6050.h>
#include <TinyGPS++.h>
#include <ArduinoJson.h>
#include <HardwareSerial.h>

// ── WiFi / Server Config ──────────────────────────────────────────────────────
const char* ssid       = "Rehan_iphone";
const char* password   = "Netvenotharalo";
const char* serverName = "http://172.20.10.2:5000/api/telemetry";

// How often to send telemetry (ms)
const unsigned long SEND_INTERVAL_MS = 2000;

// ── Pin Definitions ───────────────────────────────────────────────────────────
#define TRIG_PIN       5     // Ultrasonic trigger
#define ECHO_PIN       18    // Ultrasonic echo
#define LDR_PIN        34    // Analog LDR (light-dependent resistor)
#define WATER_PIN      35    // Analog water/rain sensor
#define CURRENT_PIN    32    // Analog current sensor (ACS712)
#define IR_PIN         14    // Digital IR obstacle sensor (LOW = obstacle)
#define PIR_PIN        27    // Digital PIR motion sensor (HIGH = motion)
#define GPS_RX_PIN     16    // GPS module TX → ESP32 RX
#define GPS_TX_PIN     17    // GPS module RX → ESP32 TX (usually unused)
#define GPS_BAUD       9600

// ── ACS712 Current Sensor Config ─────────────────────────────────────────────
// ACS712-05B: 185 mV/A, midpoint = 2.5V (1241 on 12-bit ADC at 3.3V ref)
// ACS712-20A: 100 mV/A  — change sensitivity accordingly
#define ACS_SENSITIVITY  0.185f   // V/A for ACS712-05B
#define ACS_MIDPOINT     2.5f     // Volts at zero current
#define ADC_VREF         3.3f
#define ADC_RESOLUTION   4095.0f

// ── Objects ───────────────────────────────────────────────────────────────────
Adafruit_BME280 bme;          // I2C @ 0x76 (or 0x77 if SDO=HIGH)
MPU6050         mpu;
TinyGPSPlus     gps;
HardwareSerial  gpsSerial(2); // UART2

// ── State ─────────────────────────────────────────────────────────────────────
unsigned long lastSendTime = 0;

// ── Setup ─────────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("\n╔══════════════════════════════╗");
    Serial.println("║  AeroGuard ESP32 Telemetry   ║");
    Serial.println("╚══════════════════════════════╝");

    // ── I²C ──────────────────────────────────────────────────────────────────
    Wire.begin(21, 22);

    // ── BME280 ───────────────────────────────────────────────────────────────
    if (!bme.begin(0x76)) {
        Serial.println("[BME280] Not found at 0x76, trying 0x77...");
        if (!bme.begin(0x77)) {
            Serial.println("[BME280] FAILED. Check wiring.");
        } else {
            Serial.println("[BME280] OK (0x77)");
        }
    } else {
        Serial.println("[BME280] OK (0x76)");
    }

    // ── MPU6050 ──────────────────────────────────────────────────────────────
    mpu.initialize();
    if (mpu.testConnection()) {
        Serial.println("[MPU6050] OK");
    } else {
        Serial.println("[MPU6050] FAILED. Check wiring.");
    }

    // ── GPIO ─────────────────────────────────────────────────────────────────
    pinMode(TRIG_PIN, OUTPUT);
    pinMode(ECHO_PIN, INPUT);
    pinMode(IR_PIN,   INPUT_PULLUP);
    pinMode(PIR_PIN,  INPUT);
    analogReadResolution(12);  // 12-bit ADC (0–4095)

    // ── GPS ──────────────────────────────────────────────────────────────────
    gpsSerial.begin(GPS_BAUD, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);
    Serial.println("[GPS] Serial2 started");

    // ── WiFi ─────────────────────────────────────────────────────────────────
    Serial.printf("[WiFi] Connecting to %s", ssid);
    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, password);
    int tries = 0;
    while (WiFi.status() != WL_CONNECTED && tries < 30) {
        delay(500);
        Serial.print(".");
        tries++;
    }
    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("\n[WiFi] Connected! IP: %s\n", WiFi.localIP().toString().c_str());
    } else {
        Serial.println("\n[WiFi] FAILED – will retry in loop.");
    }

    Serial.println("[INIT] Setup complete.\n");
}

// ── Sensor Reading Helpers ────────────────────────────────────────────────────

float readUltrasonic() {
    // Send 10µs trigger pulse
    digitalWrite(TRIG_PIN, LOW);
    delayMicroseconds(2);
    digitalWrite(TRIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(TRIG_PIN, LOW);

    // Measure echo duration (timeout = 30 ms → ~5 m max)
    long duration = pulseIn(ECHO_PIN, HIGH, 30000);
    if (duration == 0) return 999.0f;   // out of range
    return (duration * 0.0343f) / 2.0f; // cm
}

float readCurrent() {
    // Average 20 samples to reduce noise
    long sum = 0;
    for (int i = 0; i < 20; i++) {
        sum += analogRead(CURRENT_PIN);
        delayMicroseconds(50);
    }
    float avgADC  = sum / 20.0f;
    float voltage = (avgADC / ADC_RESOLUTION) * ADC_VREF;
    float current = (voltage - ACS_MIDPOINT) / ACS_SENSITIVITY;
    return fabsf(current);   // return magnitude
}

void readMPU(float &ax, float &ay, float &az,
             float &gx, float &gy, float &gz) {
    int16_t raw_ax, raw_ay, raw_az, raw_gx, raw_gy, raw_gz;
    mpu.getMotion6(&raw_ax, &raw_ay, &raw_az,
                   &raw_gx, &raw_gy, &raw_gz);
    // Scale: ±2g range → 16384 LSB/g, ±250°/s → 131 LSB/°/s
    const float ACCEL_SCALE = 9.81f / 16384.0f;   // → m/s²
    const float GYRO_SCALE  = 1.0f  / 131.0f;     // → °/s
    ax = raw_ax * ACCEL_SCALE;
    ay = raw_ay * ACCEL_SCALE;
    az = raw_az * ACCEL_SCALE;
    gx = raw_gx * GYRO_SCALE;
    gy = raw_gy * GYRO_SCALE;
    gz = raw_gz * GYRO_SCALE;
}

void drainGPS() {
    // Feed available GPS bytes to TinyGPS++ for up to 100 ms
    unsigned long start = millis();
    while (millis() - start < 100) {
        while (gpsSerial.available()) {
            gps.encode(gpsSerial.read());
        }
    }
}

// ── Send Telemetry ────────────────────────────────────────────────────────────

void sendTelemetry() {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[WiFi] Not connected – reconnecting...");
        WiFi.reconnect();
        return;
    }

    // ── Read all sensors ──────────────────────────────────────────────────────
    float temperature = bme.readTemperature();
    float humidity    = bme.readHumidity();
    float pressure    = bme.readPressure() / 100.0f;  // hPa

    float ax, ay, az, gx, gy, gz;
    readMPU(ax, ay, az, gx, gy, gz);

    float distance = readUltrasonic();
    int   ldr      = analogRead(LDR_PIN);
    int   water    = analogRead(WATER_PIN);
    float current  = readCurrent();
    int   ir       = (digitalRead(IR_PIN) == HIGH) ? 1 : 0;   // HIGH = obstacle detected
    int   pir      = (digitalRead(PIR_PIN) == HIGH) ? 1 : 0;  // HIGH = motion

    drainGPS();
    int   satellites = (int)gps.satellites.value();
    bool  gpsValid   = gps.location.isValid() && satellites > 0;
    float lat        = gpsValid ? (float)gps.location.lat() : 0.0f;
    float lon        = gpsValid ? (float)gps.location.lng() : 0.0f;

    // ── Build JSON ────────────────────────────────────────────────────────────
    StaticJsonDocument<512> doc;
    doc["temperature"] = round(temperature * 10) / 10.0;
    doc["humidity"]    = round(humidity    * 10) / 10.0;
    doc["pressure"]    = round(pressure    * 10) / 10.0;
    doc["accX"]        = round(ax * 1000) / 1000.0;
    doc["accY"]        = round(ay * 1000) / 1000.0;
    doc["accZ"]        = round(az * 1000) / 1000.0;
    doc["gyroX"]       = round(gx * 100)  / 100.0;
    doc["gyroY"]       = round(gy * 100)  / 100.0;
    doc["gyroZ"]       = round(gz * 100)  / 100.0;
    doc["distance"]    = round(distance   * 10) / 10.0;
    doc["ldr"]         = ldr;
    doc["water"]       = water;
    doc["current"]     = round(current    * 100) / 100.0;
    doc["ir"]          = ir;
    doc["pir"]         = pir;
    doc["satellites"]  = satellites;
    if (gpsValid) {
        doc["latitude"]  = lat;
        doc["longitude"] = lon;
    }
    // omit lat/lon when no fix → backend will apply Kerala fallback

    String jsonString;
    serializeJson(doc, jsonString);

    Serial.printf("[TX] %s\n", jsonString.c_str());

    // ── POST to backend ───────────────────────────────────────────────────────
    HTTPClient http;
    http.begin(serverName);
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(5000);

    int httpCode = http.POST(jsonString);

    if (httpCode > 0) {
        String response = http.getString();
        Serial.printf("[HTTP] %d\n", httpCode);
        // Parse response for local LED/buzzer feedback if needed
        StaticJsonDocument<512> resp;
        DeserializationError err = deserializeJson(resp, response);
        if (!err) {
            const char* riskLevel   = resp["risk_level"]   | "SAFE";
            const char* relayAction = resp["relay_action"] | "ALLOW";
            float       safetyScore = resp["safety_score"] | 100.0;
            Serial.printf("[RESULT] Risk=%s | Score=%.1f | Relay=%s\n",
                riskLevel, safetyScore, relayAction);
        }
    } else {
        Serial.printf("[HTTP] Error: %s\n", http.errorToString(httpCode).c_str());
    }

    http.end();
}

// ── Loop ──────────────────────────────────────────────────────────────────────
void loop() {
    // Feed GPS continuously between sends
    while (gpsSerial.available()) {
        gps.encode(gpsSerial.read());
    }

    unsigned long now = millis();
    if (now - lastSendTime >= SEND_INTERVAL_MS) {
        lastSendTime = now;
        sendTelemetry();
    }
}
