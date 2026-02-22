"""
AeroGuard - /api/telemetry
POST : Ingest new telemetry from ESP32 / simulator
GET  : Retrieve latest N telemetry records
"""

from flask import Blueprint, request, jsonify
from database import get_db
from engine import evaluate_risk, classify_zone, SensorData, run_ml_pipeline
import json

telemetry_bp = Blueprint("telemetry", __name__)


def _get_prev_charging_current(conn) -> float | None:
    """Fetch the most recent charging_current from sensor_history."""
    row = conn.execute(
        "SELECT charging_current FROM sensor_history ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return float(row["charging_current"]) if row and row["charging_current"] is not None else None


@telemetry_bp.route("/telemetry", methods=["POST"])
def ingest_telemetry():
    """
    Accepts JSON telemetry payload from the ESP32 ground station.

    Expected JSON fields (all optional, but at least GPS required for zone check):
        temperature, humidity, pressure, ambient_light, wind_speed, rain_detected,
        latitude, longitude, altitude, satellites, hdop,
        battery_pct, voltage, signal_strength,
        vibration_x, vibration_y, vibration_z,
        charging_current,
        sensor_failure  (bool, default false)
    """
    payload = request.get_json(force=True, silent=True)
    if not payload:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    conn = get_db()
    try:
        # ── Zone Classification ───────────────────────────────────────────────
        lat = payload.get("latitude")
        lon = payload.get("longitude")
        zone_result = {"zone": "YELLOW", "zone_name": "Unknown", "reason": "No GPS fix", "hard_lock": False}
        if lat is not None and lon is not None:
            zone_result = classify_zone(float(lat), float(lon))

        # ── Build SensorData ─────────────────────────────────────────────────
        sd = SensorData(
            temperature      = payload.get("temperature"),
            humidity         = payload.get("humidity"),
            pressure         = payload.get("pressure"),
            ambient_light    = payload.get("ambient_light"),
            wind_speed       = payload.get("wind_speed"),
            rain_detected    = bool(payload["rain_detected"]) if "rain_detected" in payload else None,
            latitude         = lat,
            longitude        = lon,
            altitude         = payload.get("altitude"),
            satellites       = payload.get("satellites"),
            hdop             = payload.get("hdop"),
            battery_pct      = payload.get("battery_pct"),
            voltage          = payload.get("voltage"),
            signal_strength  = payload.get("signal_strength"),
            vibration_x      = payload.get("vibration_x"),
            vibration_y      = payload.get("vibration_y"),
            vibration_z      = payload.get("vibration_z"),
            charging_current = payload.get("charging_current"),
            zone             = zone_result["zone"],
            sensor_failure   = bool(payload.get("sensor_failure", False)),
        )

        prev_current = _get_prev_charging_current(conn)

        # ── Risk Assessment ───────────────────────────────────────────────────
        risk = evaluate_risk(sd, prev_charging_current=prev_current)

        # ── ML Pipeline (runs in parallel with rule engine) ───────────────────
        ml_result = run_ml_pipeline({**payload, "zone": zone_result["zone"]})

        # ── Persist Sensor Record ─────────────────────────────────────────────
        cursor = conn.execute("""
            INSERT INTO sensor_history
                (temperature, humidity, pressure, ambient_light, wind_speed, rain_detected,
                 latitude, longitude, altitude, satellites, hdop,
                 battery_pct, voltage, signal_strength,
                 vibration_x, vibration_y, vibration_z, charging_current, zone)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            sd.temperature, sd.humidity, sd.pressure, sd.ambient_light, sd.wind_speed,
            1 if sd.rain_detected else 0,
            sd.latitude, sd.longitude, sd.altitude, sd.satellites, sd.hdop,
            sd.battery_pct, sd.voltage, sd.signal_strength,
            sd.vibration_x, sd.vibration_y, sd.vibration_z, sd.charging_current,
            sd.zone,
        ))
        sensor_id = cursor.lastrowid

        # ── Persist Risk Score ────────────────────────────────────────────────
        conn.execute("""
            INSERT INTO risk_scores
                (risk_index, classification, level1_triggered, level2_triggered, level3_triggered, sensor_id)
            VALUES (?,?,?,?,?,?)
        """, (
            risk["risk_index"],
            risk["classification"],
            json.dumps(risk["triggered_l1"]),
            json.dumps(risk["triggered_l2"]),
            json.dumps(risk["triggered_l3"]),
            sensor_id,
        ))

        # ── Auto-Log Critical Events ──────────────────────────────────────────
        if risk["hard_lock"]:
            severity = "CRITICAL"
            event_type = "LOCK"
            desc = "Hard lock triggered: " + ", ".join(risk["triggered_l1"])
        elif risk["classification"] == "Fly with Caution":
            severity = "WARNING"
            event_type = "CAUTION"
            desc = "Caution conditions detected"
        else:
            severity = "INFO"
            event_type = "CLEAR"
            desc = "All systems nominal"

        conn.execute("""
            INSERT INTO events (event_type, severity, description, sensor_id)
            VALUES (?,?,?,?)
        """, (event_type, severity, desc, sensor_id))

        conn.commit()

        return jsonify({
            "sensor_id":    sensor_id,
            "zone":         zone_result,
            "risk":         risk,
            "ml":           ml_result,
            "relay_action": "LOCK" if risk["hard_lock"] else "ALLOW",
        }), 201

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@telemetry_bp.route("/telemetry", methods=["GET"])
def get_telemetry():
    """
    Retrieve the latest telemetry records.

    Query params:
        limit  : int, default 50
        offset : int, default 0
    """
    limit  = min(int(request.args.get("limit",  50)), 500)
    offset = int(request.args.get("offset", 0))

    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT s.*, r.risk_index, r.classification,
                   r.level1_triggered, r.level2_triggered, r.level3_triggered
            FROM sensor_history s
            LEFT JOIN risk_scores r ON r.sensor_id = s.id
            ORDER BY s.id DESC
            LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()

        records = []
        for row in rows:
            d = dict(row)
            for key in ("level1_triggered", "level2_triggered", "level3_triggered"):
                if d.get(key):
                    d[key] = json.loads(d[key])
            records.append(d)

        total = conn.execute("SELECT COUNT(*) FROM sensor_history").fetchone()[0]

        return jsonify({
            "total":   total,
            "limit":   limit,
            "offset":  offset,
            "records": records,
        }), 200

    finally:
        conn.close()
