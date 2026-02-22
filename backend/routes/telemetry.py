"""
AeroGuard - Telemetry Routes
/api/telemetry  POST  – ingest Arduino sensor payload
/api/telemetry  GET   – retrieve historical records
"""

from __future__ import annotations
import math
import datetime
import logging
from flask import Blueprint, request, jsonify

from database import get_db
from engine import evaluate_risk, classify_zone, run_ml_pipeline
from engine.risk_engine import SensorData

log = logging.getLogger(__name__)
telemetry_bp = Blueprint("telemetry", __name__)

from constants import GPS_FALLBACK_LAT as FALLBACK_LAT, GPS_FALLBACK_LON as FALLBACK_LON, GPS_FALLBACK_NAME as FALLBACK_NAME


def _safe_float(d: dict, key: str, default=None):
    v = d.get(key, default)
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _safe_int(d: dict, key: str, default=None):
    v = d.get(key, default)
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _build_ml_input(payload: dict, zone: str) -> dict:
    """Build flat dict expected by ml_engine from Arduino payload."""
    return {
        "temperature":   payload.get("temperature", 25.0),
        "humidity":      payload.get("humidity", 55.0),
        "pressure":      payload.get("pressure", 1013.0),
        "rain_detected": bool(payload.get("water", 0) > 100),
        "latitude":      payload.get("latitude", FALLBACK_LAT),
        "longitude":     payload.get("longitude", FALLBACK_LON),
        "altitude":      payload.get("altitude", 0.0),
        "satellites":    payload.get("satellites", 0),
        "hdop":          payload.get("hdop", 1.0),
        "battery_pct":   payload.get("battery_pct", 100.0),
        "voltage":       payload.get("voltage", 12.0),
        "signal_strength": payload.get("signal_strength", 100),
        "vibration_x":   payload.get("accX", 0.0),
        "vibration_y":   payload.get("accY", 0.0),
        "vibration_z":   payload.get("accZ", 9.8),   # ~gravity at rest
        "charging_current": payload.get("current", 0.0),
        "sensor_failure": payload.get("sensor_failure", False),
        "ambient_light": payload.get("ldr", 500),
        "wind_speed":    payload.get("wind_speed", 0.0),
        "zone":          zone,
    }


# ── POST /api/telemetry ────────────────────────────────────────────────────────

@telemetry_bp.route("/telemetry", methods=["POST"])
def ingest_telemetry():
    """
    Accept Arduino sensor JSON, evaluate risk, store to DB, return results.

    Arduino field mapping
    ─────────────────────
    accX/Y/Z  → acc_x/y/z   (m/s²)
    gyroX/Y/Z → gyro_x/y/z  (°/s)
    ldr       → ldr          (0-1023)
    water     → water        (0-1023)
    current   → current_a    (A)
    ir        → ir           (0/1)
    pir       → pir          (0/1)
    distance  → distance     (cm)
    """
    payload = request.get_json(force=True, silent=True) or {}

    # ── Validate / default sensor fields ──────────────────────────────────────
    temp     = _safe_float(payload, "temperature", 25.0)
    hum      = _safe_float(payload, "humidity",    55.0)
    pres     = _safe_float(payload, "pressure",    1013.0)
    acc_x    = _safe_float(payload, "accX",        0.0)
    acc_y    = _safe_float(payload, "accY",        0.0)
    acc_z    = _safe_float(payload, "accZ",        9.8)   # ~gravity at rest
    gyro_x   = _safe_float(payload, "gyroX",       0.0)
    gyro_y   = _safe_float(payload, "gyroY",       0.0)
    gyro_z   = _safe_float(payload, "gyroZ",       0.0)
    distance = _safe_float(payload, "distance",    999.0)
    ldr      = _safe_int  (payload, "ldr",         512)
    water    = _safe_int  (payload, "water",       0)
    current  = _safe_float(payload, "current",     0.0)
    ir       = _safe_int  (payload, "ir",          0)
    pir      = _safe_int  (payload, "pir",         0)
    sats     = _safe_int  (payload, "satellites",  0)

    # Clamp ranges for safety
    temp     = max(-50.0, min(80.0,    temp))
    hum      = max(0.0,   min(100.0,   hum))
    pres     = max(800.0, min(1100.0,  pres))
    current  = max(0.0,   min(30.0,    current))
    water    = max(0,     min(1023,     water))
    ldr      = max(0,     min(1023,     ldr))

    # ── GPS with fallback ──────────────────────────────────────────────────────
    raw_lat = _safe_float(payload, "latitude",  None)
    raw_lon = _safe_float(payload, "longitude", None)
    using_fallback_gps = (raw_lat is None or raw_lon is None or sats == 0)
    lat  = raw_lat  if not using_fallback_gps else FALLBACK_LAT
    lon  = raw_lon  if not using_fallback_gps else FALLBACK_LON
    loc_name = FALLBACK_NAME if using_fallback_gps else "Live GPS"
    hdop     = _safe_float(payload, "hdop",     1.0)
    altitude = _safe_float(payload, "altitude", 0.0)

    # ── Legacy fields (still supported) ───────────────────────────────────────
    bat_pct   = _safe_float(payload, "battery_pct",     None)
    voltage   = _safe_float(payload, "voltage",         None)
    signal    = _safe_int  (payload, "signal_strength", None)
    rain_bool = payload.get("rain_detected", None)

    # ── Zone classification ────────────────────────────────────────────────────
    zone_result = classify_zone(lat, lon)
    zone_color  = zone_result["zone"]

    # ── Build SensorData ───────────────────────────────────────────────────────
    sd = SensorData(
        temperature=temp,    humidity=hum,   pressure=pres,
        rain_detected=rain_bool,
        latitude=lat,        longitude=lon,  altitude=altitude,
        satellites=sats,     hdop=hdop,
        acc_x=acc_x,         acc_y=acc_y,    acc_z=acc_z,
        gyro_x=gyro_x,       gyro_y=gyro_y,  gyro_z=gyro_z,
        distance=distance,
        ldr=ldr,
        water=water,
        current_a=current,
        ir=ir,
        pir=pir,
        battery_pct=bat_pct,
        voltage=voltage,
        signal_strength=signal,
        charging_current=current,           # mirror for legacy compat
        zone=zone_color,
        sensor_failure=bool(payload.get("sensor_failure", False)),
    )

    # ── Evaluate rule-based risk ───────────────────────────────────────────────
    risk = evaluate_risk(sd)

    # ── ML pipeline (secondary, non-blocking) ─────────────────────────────────
    try:
        ml_input = _build_ml_input(payload, zone_color)
        ml_result = run_ml_pipeline(ml_input)
    except Exception as e:
        log.warning("ML pipeline failed: %s", e)
        ml_result = {"safety_score": risk["safety_score"], "rain_probability": 0.1, "decision": risk["classification"]}

    rain_prob = ml_result.get("rain_probability", 0.1)

    # ── Persist to database ───────────────────────────────────────────────────
    conn = get_db()
    ts   = datetime.datetime.utcnow().isoformat()
    try:
        c = conn.cursor()

        # sensor_history
        c.execute("""
            INSERT INTO sensor_history (
                timestamp,
                temperature, humidity, pressure, ambient_light,
                rain_detected,
                latitude, longitude, altitude, satellites, hdop,
                location_name, using_fallback_gps,
                battery_pct, voltage, signal_strength,
                acc_x, acc_y, acc_z,
                gyro_x, gyro_y, gyro_z, tilt_angle,
                distance, ldr, water, current_a, ir, pir,
                charging_current,
                zone
            ) VALUES (
                ?,
                ?,?,?,?,
                ?,
                ?,?,?,?,?,
                ?,?,
                ?,?,?,
                ?,?,?,
                ?,?,?,?,
                ?,?,?,?,?,?,
                ?,
                ?
            )
        """, (
            ts,
            temp, hum, pres, ldr,            # ambient_light ← ldr
            1 if rain_bool else 0,
            lat, lon, altitude, sats, hdop,
            loc_name, 1 if using_fallback_gps else 0,
            bat_pct, voltage, signal,
            acc_x, acc_y, acc_z,
            gyro_x, gyro_y, gyro_z, risk["tilt_angle"],
            distance, ldr, water, current, ir, pir,
            current,                         # charging_current = current
            zone_color,
        ))
        sensor_id = c.lastrowid

        # risk_scores
        c.execute("""
            INSERT INTO risk_scores (
                timestamp, risk_index, risk_level, classification,
                safety_score, level1_triggered, level2_triggered,
                level3_triggered, sensor_id
            ) VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            ts,
            risk["risk_index"],
            risk["risk_level"],
            risk["classification"],
            risk["safety_score"],
            ", ".join(risk["triggered_l1"]),
            ", ".join(risk["triggered_l2"]),
            ", ".join(risk["triggered_l3"]),
            sensor_id,
        ))

        # events — only if abnormal
        if risk["triggered_l1"]:
            c.execute("INSERT INTO events (timestamp,event_type,severity,description,sensor_id) VALUES (?,?,?,?,?)",
                (ts, "RISK_L1", "CRITICAL", f"UNSAFE: {', '.join(risk['triggered_l1'])}", sensor_id))
        elif risk["triggered_l2"]:
            c.execute("INSERT INTO events (timestamp,event_type,severity,description,sensor_id) VALUES (?,?,?,?,?)",
                (ts, "RISK_L2", "WARNING", f"CAUTION: {', '.join(risk['triggered_l2'])}", sensor_id))

        conn.commit()
    except Exception as e:
        conn.rollback()
        log.error("DB write error: %s", e)
        sensor_id = None
    finally:
        conn.close()

    # ── Build response ────────────────────────────────────────────────────────
    return jsonify({
        # Identifiers
        "sensor_id":  sensor_id,
        "timestamp":  ts,

        # Top-level aliases requested by user
        "risk_level":       risk["risk_level"],
        "safety_score":     risk["safety_score"],
        "zone_status":      zone_color,
        "rain_probability": round(rain_prob, 4),

        # Full blocks
        "zone":   zone_result,
        "risk":   risk,
        "ml":     ml_result,

        # Relay action
        "relay_action": "LOCK" if risk["hard_lock"] else "ALLOW",

        # GPS info
        "gps": {
            "latitude":         lat,
            "longitude":        lon,
            "altitude":         altitude,
            "satellites":       sats,
            "hdop":             hdop,
            "using_fallback":   using_fallback_gps,
            "location_name":    loc_name,
        },
    }), 201


# ── GET /api/telemetry ────────────────────────────────────────────────────────

@telemetry_bp.route("/telemetry", methods=["GET"])
def get_telemetry():
    """Return recent telemetry records."""
    limit  = min(int(request.args.get("limit", 50)), 500)
    offset = int(request.args.get("offset", 0))

    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT * FROM sensor_history
            ORDER BY id DESC LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()
        return jsonify({"records": [dict(r) for r in rows], "limit": limit, "offset": offset})
    finally:
        conn.close()
