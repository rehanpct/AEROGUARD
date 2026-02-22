"""
AeroGuard - Quick test script (no external test framework needed).
Run this AFTER starting the Flask server: python app.py

Usage:
    python test_backend.py
"""

import json
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:5000/api"


def req(method, path, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, method=method,
                                headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def section(title):
    print(f"\n{'─'*60}\n  {title}\n{'─'*60}")


def check(label, condition, detail=""):
    status = "✅ PASS" if condition else "❌ FAIL"
    print(f"  {status}  {label}")
    if not condition and detail:
        print(f"          {detail}")


# ── Test payloads ──────────────────────────────────────────────────────────────

SAFE_PAYLOAD = {
    "temperature": 25.0, "humidity": 55.0, "pressure": 1013.0,
    "ambient_light": 800.0, "wind_speed": 3.0, "rain_detected": False,
    "latitude": 13.15, "longitude": 77.48,   # inside GREEN test zone
    "altitude": 50.0, "satellites": 9, "hdop": 1.2,
    "battery_pct": 85.0, "voltage": 12.1, "signal_strength": 80,
    "vibration_x": 0.1, "vibration_y": 0.05, "vibration_z": 0.08,
    "charging_current": 2.0, "sensor_failure": False,
}

UNSAFE_RAIN_PAYLOAD = {**SAFE_PAYLOAD, "rain_detected": True}
UNSAFE_RED_ZONE     = {**SAFE_PAYLOAD, "latitude": 12.95, "longitude": 77.62}
UNSAFE_SENSOR_FAIL  = {**SAFE_PAYLOAD, "sensor_failure": True}
CAUTION_PAYLOAD     = {**SAFE_PAYLOAD, "battery_pct": 18.0, "hdop": 1.5}

if __name__ == "__main__":

    section("1. POST /telemetry – Safe conditions (GREEN zone)")
    status, body = req("POST", "/telemetry", SAFE_PAYLOAD)
    check("HTTP 201", status == 201, body)
    check("Zone is GREEN", body.get("zone", {}).get("zone") == "GREEN", body)
    check("Classification Safe", body.get("risk", {}).get("classification") == "Safe to Fly", body)
    check("Relay ALLOW", body.get("relay_action") == "ALLOW", body)

    section("2. POST /telemetry – Rain detected (Level-1 override)")
    status, body = req("POST", "/telemetry", UNSAFE_RAIN_PAYLOAD)
    check("HTTP 201", status == 201)
    check("Risk = 100", body.get("risk", {}).get("risk_index") == 100.0, body)
    check("Classification Unsafe", body.get("risk", {}).get("classification") == "Not Safe to Fly")
    check("Relay LOCK", body.get("relay_action") == "LOCK")
    check("RAIN_DETECTED in L1", "RAIN_DETECTED" in body.get("risk", {}).get("triggered_l1", []))

    section("3. POST /telemetry – RED zone (Level-1 override)")
    status, body = req("POST", "/telemetry", UNSAFE_RED_ZONE)
    check("HTTP 201", status == 201)
    check("Zone is RED", body.get("zone", {}).get("zone") == "RED")
    check("Relay LOCK", body.get("relay_action") == "LOCK")
    check("RED_ZONE in L1", "RED_ZONE" in body.get("risk", {}).get("triggered_l1", []))

    section("4. POST /telemetry – Sensor failure (Level-1 override)")
    status, body = req("POST", "/telemetry", UNSAFE_SENSOR_FAIL)
    check("HTTP 201", status == 201)
    check("Relay LOCK", body.get("relay_action") == "LOCK")
    check("SENSOR_FAILURE in L1", "SENSOR_FAILURE" in body.get("risk", {}).get("triggered_l1", []))

    section("5. POST /telemetry – Caution conditions")
    status, body = req("POST", "/telemetry", CAUTION_PAYLOAD)
    check("HTTP 201", status == 201)
    check("Not fully locked", body.get("relay_action") != "LOCK")

    section("6. GET /telemetry")
    status, body = req("GET", "/telemetry?limit=5")
    check("HTTP 200", status == 200)
    check("Has records", len(body.get("records", [])) > 0)

    section("7. GET /status")
    status, body = req("GET", "/status")
    check("HTTP 200", status == 200)
    check("Has risk_index", body.get("risk_index") is not None)
    check("Has gps block", "gps" in body)
    check("Has drone block", "drone" in body)

    section("8. GET /status/summary")
    status, body = req("GET", "/status/summary")
    check("HTTP 200", status == 200)
    check("Has avg_risk_24h", "avg_risk_24h" in body)

    section("9. GET /logs/events")
    status, body = req("GET", "/logs/events")
    check("HTTP 200", status == 200)
    check("Has events list", "events" in body)
    check("Events not empty", len(body.get("events", [])) > 0)

    section("10. GET /logs/risk")
    status, body = req("GET", "/logs/risk?hours=24")
    check("HTTP 200", status == 200)
    check("Has records", len(body.get("records", [])) > 0)

    section("11. POST + PATCH /logs/flights")
    status, body = req("POST", "/logs/flights", {"notes": "Test flight"})
    check("HTTP 201", status == 201)
    fid = body.get("flight_id")
    check("Got flight_id", fid is not None)

    status, body = req("PATCH", f"/logs/flights/{fid}", {
        "max_risk_index": 35.0, "classification": "Fly with Caution", "zone": "GREEN"
    })
    check("HTTP 200 close", status == 200)

    section("12. GET /logs/failures")
    status, body = req("GET", "/logs/failures")
    check("HTTP 200", status == 200)

    section("13. POST /ai_prediction")
    status, body = req("POST", "/ai_prediction", SAFE_PAYLOAD)
    check("HTTP 200", status == 200)
    check("Has risk_probability", "risk_probability" in body)
    check("risk_probability in [0,1]", 0 <= body.get("risk_probability", -1) <= 1)

    section("14. GET /ai_prediction/trend")
    status, body = req("GET", "/ai_prediction/trend?window=10")
    check("HTTP 200", status == 200)
    check("Has trend field", "trend" in body)
    check("Has predicted_next", "predicted_next" in body)

    section("15. GET /ai_prediction/vso")
    status, body = req("GET", "/ai_prediction/vso")
    check("HTTP 200", status == 200)
    check("Has advice list", isinstance(body.get("advice"), list))
    check("Has action", "action" in body)

    section("16. GET /zones")
    status, body = req("GET", "/zones")
    check("HTTP 200", status == 200)
    check("Has zones list", len(body.get("zones", [])) > 0)

    section("17. GET /zones/classify")
    status, body = req("GET", "/zones/classify?lat=13.15&lon=77.48")
    check("HTTP 200", status == 200)
    check("Zone GREEN", body.get("zone") == "GREEN")

    status, body = req("GET", "/zones/classify?lat=12.95&lon=77.62")
    check("RED zone classified", body.get("zone") == "RED")

    section("18. POST /zones (dynamic zone creation)")
    status, body = req("POST", "/zones", {
        "name": "Test Custom Zone",
        "color": "YELLOW",
        "polygon": [
            {"lat": 10.0, "lon": 76.0},
            {"lat": 10.0, "lon": 76.5},
            {"lat": 10.5, "lon": 76.5},
            {"lat": 10.5, "lon": 76.0},
        ],
        "reason": "Dynamically added via API",
    })
    check("HTTP 201", status == 201)
    check("Zone added", body.get("added") is True)

    print(f"\n{'═'*60}")
    print("  All tests complete.")
    print(f"{'═'*60}\n")
