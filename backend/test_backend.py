"""
AeroGuard - Integration Test Suite (Arduino sensor schema)
Run AFTER starting the Flask backend:  python app.py

Usage:
    python test_backend.py

Tests all endpoints with the Arduino JSON sensor format.
"""

import json, urllib.request, urllib.error

BASE = "http://127.0.0.1:5000/api"

# ── Arduino sensor payloads ────────────────────────────────────────────────────

# Normal safe conditions, GPS inside GREEN zone
SAFE_PAYLOAD = {
    "temperature": 27.5,  "humidity": 60.0,    "pressure": 1013.0,
    "accX": 0.05,         "accY": -0.02,        "accZ": 9.81,
    "gyroX": 0.5,         "gyroY": -0.3,        "gyroZ": 0.2,
    "distance": 120.0,    "ldr": 680,            "water": 10,
    "current": 1.8,       "ir": 0,               "pir": 0,
    "satellites": 9,      "latitude": 13.15,     "longitude": 77.48,
}

# Water sensor unsafe (> 500)
UNSAFE_WATER = {**SAFE_PAYLOAD, "water": 720, "latitude": 13.15, "longitude": 77.48}

# Overcurrent (> 5 A)
UNSAFE_CURRENT = {**SAFE_PAYLOAD, "current": 6.2}

# Extreme tilt (> 30°): set acc xy large, az small → tilt > 30°
UNSAFE_TILT = {**SAFE_PAYLOAD, "accX": 6.0, "accY": 4.0, "accZ": 1.0}

# No GPS (missing lat/lon) → should use Kerala fallback
NO_GPS = {k: v for k, v in SAFE_PAYLOAD.items() if k not in ("latitude", "longitude")}
NO_GPS["satellites"] = 0

# Dark + PIR + low satellites → CAUTION
CAUTION_PAYLOAD = {**SAFE_PAYLOAD, "ldr": 40, "pir": 1, "satellites": 2}

# Red zone location
RED_ZONE_PAYLOAD = {**SAFE_PAYLOAD, "latitude": 12.95, "longitude": 77.62}

# ── Helpers ───────────────────────────────────────────────────────────────────

def req(method, path, body=None):
    url  = BASE + path
    data = json.dumps(body).encode() if body else None
    r    = urllib.request.Request(url, data=data, method=method,
                                   headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")

def section(title):
    print(f"\n{'─'*62}\n  {title}\n{'─'*62}")

def check(label, condition, detail=""):
    status = "✅ PASS" if condition else "❌ FAIL"
    print(f"  {status}  {label}")
    if not condition and detail:
        print(f"         ↳ {detail}")

# ── Tests ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":

    section("1. POST /telemetry – Safe Arduino payload (GREEN zone)")
    s, b = req("POST", "/telemetry", SAFE_PAYLOAD)
    check("HTTP 201",             s == 201, b)
    check("risk_level returned",  "risk_level" in b, b)
    check("safety_score returned","safety_score" in b, b)
    check("zone_status returned", "zone_status" in b, b)
    check("rain_probability",     "rain_probability" in b, b)
    check("timestamp returned",   "timestamp" in b, b)
    check("gps block present",    "gps" in b, b)
    check("Zone is GREEN",        b.get("zone_status") == "GREEN", b)
    check("risk_level SAFE",      b.get("risk_level") == "SAFE", b)
    check("Relay ALLOW",          b.get("relay_action") == "ALLOW", b)

    section("2. POST /telemetry – Water sensor unsafe (water=720)")
    s, b = req("POST", "/telemetry", UNSAFE_WATER)
    check("HTTP 201",             s == 201, b)
    check("risk_level UNSAFE",    b.get("risk_level") == "UNSAFE", b)
    check("Relay LOCK",           b.get("relay_action") == "LOCK", b)
    check("safety_score near 0",  (b.get("safety_score") or 100) < 5, b)

    section("3. POST /telemetry – Overcurrent (current=6.2 A)")
    s, b = req("POST", "/telemetry", UNSAFE_CURRENT)
    check("HTTP 201",             s == 201, b)
    check("risk_level UNSAFE",    b.get("risk_level") == "UNSAFE", b)
    check("Relay LOCK",           b.get("relay_action") == "LOCK", b)

    section("4. POST /telemetry – Extreme tilt")
    s, b = req("POST", "/telemetry", UNSAFE_TILT)
    check("HTTP 201",             s == 201, b)
    check("risk_level UNSAFE",    b.get("risk_level") == "UNSAFE", b)
    check("Relay LOCK",           b.get("relay_action") == "LOCK", b)

    section("5. POST /telemetry – No GPS (Kerala fallback)")
    s, b = req("POST", "/telemetry", NO_GPS)
    check("HTTP 201",             s == 201, b)
    gps = b.get("gps", {})
    check("using_fallback=True",  gps.get("using_fallback") is True, gps)
    check("Lat = 10.8505",        abs(gps.get("latitude", 0) - 10.8505) < 0.01, gps)

    section("6. POST /telemetry – CAUTION (dark + PIR + low sats)")
    s, b = req("POST", "/telemetry", CAUTION_PAYLOAD)
    check("HTTP 201",             s == 201, b)
    check("risk_level CAUTION",   b.get("risk_level") == "CAUTION", b)
    check("Relay ALLOW",          b.get("relay_action") == "ALLOW", b)

    section("7. POST /telemetry – RED zone hard lock")
    s, b = req("POST", "/telemetry", RED_ZONE_PAYLOAD)
    check("HTTP 201",             s == 201, b)
    check("zone_status RED",      b.get("zone_status") == "RED", b)
    check("Relay LOCK",           b.get("relay_action") == "LOCK", b)

    section("8. GET /telemetry – History")
    s, b = req("GET", "/telemetry?limit=10")
    check("HTTP 200",             s == 200, b)
    check("Has records",          len(b.get("records", [])) > 0, b)

    section("9. GET /status – Full sensor snapshot")
    s, b = req("GET", "/status")
    check("HTTP 200",             s == 200, b)
    check("Has risk_level",       "risk_level" in b, b)
    check("Has safety_score",     "safety_score" in b, b)
    check("Has zone_status",      "zone_status" in b, b)
    check("Has rain_probability", "rain_probability" in b, b)
    check("Has sensors block",    "sensors" in b, b)
    check("Has gps block",        "gps" in b, b)
    # Verify sensors block has IMU fields
    sensors = b.get("sensors", {})
    check("sensors.acc_x exists",  "acc_x"  in sensors, sensors)
    check("sensors.gyro_x exists", "gyro_x" in sensors, sensors)
    check("sensors.distance",      "distance" in sensors, sensors)
    check("sensors.ldr",           "ldr"    in sensors, sensors)
    check("sensors.water",         "water"  in sensors, sensors)
    check("sensors.current_a",     "current_a" in sensors, sensors)
    check("sensors.ir",            "ir"     in sensors, sensors)
    check("sensors.pir",           "pir"    in sensors, sensors)
    check("sensors.tilt_angle",    "tilt_angle" in sensors, sensors)
    check("gps.using_fallback key","using_fallback" in b.get("gps", {}), b.get("gps"))

    section("10. GET /status/summary")
    s, b = req("GET", "/status/summary")
    check("HTTP 200",             s == 200, b)
    check("Has avg_risk_24h",     "avg_risk_24h" in b, b)

    section("11. GET /logs/events")
    s, b = req("GET", "/logs/events")
    check("HTTP 200",             s == 200, b)
    check("Has events key",       "events" in b, b)

    section("12. GET /logs/risk")
    s, b = req("GET", "/logs/risk?hours=1")
    check("HTTP 200",             s == 200, b)
    check("Has records",          "records" in b, b)

    section("13. POST /ai_prediction – Arduino payload")
    s, b = req("POST", "/ai_prediction", SAFE_PAYLOAD)
    check("HTTP 200",             s == 200, b)
    check("Has risk_level",       "risk_level" in b, b)
    check("Has safety_score",     "safety_score" in b, b)
    check("Has rain_probability", "rain_probability" in b, b)
    check("Has risk_probability", "risk_probability" in b, b)
    check("risk_prob in [0,1]",   0 <= b.get("risk_probability", -1) <= 1, b)

    section("14. GET /ai_prediction/trend")
    s, b = req("GET", "/ai_prediction/trend?window=10")
    check("HTTP 200",             s == 200, b)
    check("Has trend",            "trend" in b, b)
    check("Has predicted_next",   "predicted_next" in b, b)

    section("15. GET /ai_prediction/vso")
    s, b = req("GET", "/ai_prediction/vso")
    check("HTTP 200",             s == 200, b)
    check("Has advice",           isinstance(b.get("advice"), list), b)
    check("Has action",           "action" in b, b)

    section("16. GET /zones + /zones/classify")
    s, b = req("GET", "/zones")
    check("HTTP 200",             s == 200, b)
    check("Has zones",            len(b.get("zones", [])) > 0, b)

    s, b = req("GET", "/zones/classify?lat=13.15&lon=77.48")
    check("GREEN zone",           b.get("zone") == "GREEN", b)

    s, b = req("GET", "/zones/classify?lat=12.95&lon=77.62")
    check("RED zone",             b.get("zone") == "RED", b)

    print(f"\n{'═'*62}")
    print("  Integration test complete.")
    print(f"{'═'*62}\n")
