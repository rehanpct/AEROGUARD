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
    """Build flat dict expected by ml_engine from Arduino payload.
    All sensor fields are included so the dict is available for future
    model retraining. Unknown features are ignored by the current model
    via reindex(fill_value=0) in ml_inference.py.
    """
    return {
        # ─ Atmospheric (model-trained) ─
        "temperature":      payload.get("temperature", 25.0),
        "humidity":         payload.get("humidity", 55.0),
        "pressure":         payload.get("pressure", 1013.0),
        "rain_detected":    bool(payload.get("water", 0) > 100),
        # ─ GPS (model-trained) ─
        "latitude":         payload.get("latitude", FALLBACK_LAT),
        "longitude":        payload.get("longitude", FALLBACK_LON),
        "altitude":         payload.get("altitude", 0.0),
        "satellites":       payload.get("satellites", 0),
        "hdop":             payload.get("hdop", 1.0),
        # ─ Power / legacy (model-trained) ─
        "battery_pct":      payload.get("battery_pct", 100.0),
        "voltage":          payload.get("voltage", 12.0),
        "signal_strength":  payload.get("signal_strength", 100),
        "charging_current": payload.get("current", 0.0),
        "sensor_failure":   payload.get("sensor_failure", False),
        "wind_speed":       payload.get("wind_speed", 0.0),
        # ─ IMU (model-trained) ─
        "vibration_x":      payload.get("accX", 0.0),
        "vibration_y":      payload.get("accY", 0.0),
        "vibration_z":      payload.get("accZ", 9.8),
        # ─ Arduino sensors (passed for future retraining; not yet in model) ─
        "ambient_light":    payload.get("ldr", 500),
        "ldr":              payload.get("ldr", 500),
        "ir":               payload.get("ir", 1),     # ACTIVE-LOW: 0=obstacle
        "pir":              payload.get("pir", 0),
        "distance":         payload.get("distance", 999.0),
        "water":            payload.get("water", 0),
        "current_a":        payload.get("current", 0.0),
        "zone":             zone,
    }


# ── POST /api/telemetry ────────────────────────────────────────────────────────

@telemetry_bp.route("/telemetry", methods=["POST"])
def ingest_telemetry():

    payload = request.get_json(force=True, silent=True) or {}

    # ── Validate / default sensor fields ──────────────────────────────────────
    temp     = _safe_float(payload, "temperature", 25.0)
    hum      = _safe_float(payload, "humidity",    55.0)
    pres     = _safe_float(payload, "pressure",    1013.0)
    acc_x    = _safe_float(payload, "accX",        0.0)
    acc_y    = _safe_float(payload, "accY",        0.0)
    acc_z    = _safe_float(payload, "accZ",        9.8)
    gyro_x   = _safe_float(payload, "gyroX",       0.0)
    gyro_y   = _safe_float(payload, "gyroY",       0.0)
    gyro_z   = _safe_float(payload, "gyroZ",       0.0)
    distance = _safe_float(payload, "distance",    999.0)
    ldr      = _safe_int  (payload, "ldr",         512)
    water    = _safe_int  (payload, "water",       0)
    current  = _safe_float(payload, "current",     0.0)
    ir       = _safe_int  (payload, "ir",          1)  # ACTIVE-LOW: default=1 (clear)
    pir      = _safe_int  (payload, "pir",         0)
    sats     = _safe_int  (payload, "satellites",  0)

    # Clamp ranges for safety
    temp     = max(-50.0, min(80.0,    temp))
    hum      = max(0.0,   min(100.0,   hum))
    pres     = max(800.0, min(1100.0,  pres))
    current  = max(-30.0, min(30.0,    current))   # ✔ FIXED
    water    = max(0,     min(1023,     water))
    ldr      = max(0,     min(1023,     ldr))

    # ── GPS with fallback ──────────────────────────────────────────────────────
    raw_lat = _safe_float(payload, "latitude",  None)
    raw_lon = _safe_float(payload, "longitude", None)

    using_fallback_gps = (raw_lat is None or raw_lon is None)   # ✔ FIXED
    lat  = raw_lat  if not using_fallback_gps else FALLBACK_LAT
    lon  = raw_lon  if not using_fallback_gps else FALLBACK_LON
    loc_name = FALLBACK_NAME if using_fallback_gps else "Live GPS"

    hdop     = _safe_float(payload, "hdop",     1.0)
    altitude = _safe_float(payload, "altitude", 0.0)

    # ── Legacy fields ─────────────────────────────────────────────────────────
    bat_pct   = _safe_float(payload, "battery_pct",     None)
    voltage   = _safe_float(payload, "voltage",         None)
    signal    = _safe_int  (payload, "signal_strength", None)

    rain_bool = bool(water > 100)   # ✔ FIXED

    # ── Zone classification ────────────────────────────────────────────────────
    zone_result = classify_zone(lat, lon)
    zone_color  = zone_result["zone"]

    # ── Build SensorData ───────────────────────────────────────────────────────
    sd = SensorData(
        temperature=temp, humidity=hum, pressure=pres,
        rain_detected=rain_bool,
        latitude=lat, longitude=lon, altitude=altitude,
        satellites=sats, hdop=hdop,
        acc_x=acc_x, acc_y=acc_y, acc_z=acc_z,
        gyro_x=gyro_x, gyro_y=gyro_y, gyro_z=gyro_z,
        distance=distance,
        ldr=ldr,
        water=water,
        current_a=current,
        ir=ir,
        pir=pir,
        battery_pct=bat_pct,
        voltage=voltage,
        signal_strength=signal,
        charging_current=current,
        zone=zone_color,
        sensor_failure=bool(payload.get("sensor_failure", False)),
    )

    # ── Evaluate rule-based risk ───────────────────────────────────────────────
    risk = evaluate_risk(sd)

    # ── ML pipeline ───────────────────────────────────────────────────────────
    try:
        ml_input = _build_ml_input(payload, zone_color)
        ml_result = run_ml_pipeline(ml_input)
    except Exception as e:
        log.warning("ML pipeline failed: %s", e)
        ml_result = {
            "safety_score": risk["safety_score"],
            "rain_probability": 0.1,
            "decision": risk["classification"]
        }

    rain_prob = ml_result.get("rain_probability", 0.1)

    # ── Derive risk_index from ML safety_score ─────────────────────────────────
    # ml_engine.run_ml_pipeline() returns the raw model prediction as "safety_score"
    # (higher = more dangerous: >=70 Not Safe, >=40 Caution, <40 Safe).
    # This raw value is used as risk_index (0–100). At line 235 it is inverted
    # before being stored in the DB, so the stored "safety_score" column always
    # means higher = safer (consistent with the UI and status.py conventions).
    ml_safety_raw  = ml_result.get("safety_score") or risk["safety_score"]
    ml_risk_index  = float(min(100.0, max(0.0, ml_safety_raw)))

    # ── Sensor bonus layer ─────────────────────────────────────────────────
    # The trained ML model doesn't include ir/pir/distance/water/ldr.
    # These are added as direct contributions so ALL sensors influence risk.
    sensor_bonus = 0.0

    valid_dist = (distance is not None and distance > 0)
    obstacle   = (ir == 0)   # ACTIVE-LOW: ir=0 means obstacle

    # GPS cold-start: satellites=0 means no fix at all – always a baseline risk
    if sats == 0:
        sensor_bonus += 10    # no GPS fix – minimum penalty
    elif sats < 4 and hdop > 1.0:
        sensor_bonus += 5     # marginal fix

    # Proximity sensors
    if obstacle and valid_dist and distance < 15:
        sensor_bonus += 15    # obstacle AND close distance
    elif obstacle and valid_dist:
        sensor_bonus += 5     # obstacle detected, moderate distance

    if pir == 1:
        sensor_bonus += 5     # motion near dock

    # Water / moisture
    if water > 300:
        sensor_bonus += 20    # dangerously wet
    elif water > 120:
        sensor_bonus += 10    # damp / moisture present

    # Ambient light overexposure (optical sensor impairment)
    if ldr > 3000:
        sensor_bonus += 5

    ml_risk_index = min(100.0, ml_risk_index + sensor_bonus)

    # Rule engine hard_lock always overrides (safety critical)
    if risk["hard_lock"]:
        ml_risk_index = max(ml_risk_index, 60.0)

    # Classify using existing frontend bands: >=60 UNSAFE, >=30 CAUTION, else SAFE
    if ml_risk_index >= 60:
        ml_risk_level     = "UNSAFE"
        ml_classification = "Not Safe to Fly"
    elif ml_risk_index >= 30:
        ml_risk_level     = "CAUTION"
        ml_classification = "Fly with Caution"
    else:
        ml_risk_level     = "SAFE"
        ml_classification = "Safe to Fly"

    ml_safety_score = round(100.0 - ml_risk_index, 2)  # invert: higher = safer for UI

    # ── Persist to database ───────────────────────────────────────────────────
    conn = get_db()
    ts   = datetime.datetime.utcnow().isoformat()
    try:
        c = conn.cursor()

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
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            )
        """, (
            ts,
            temp, hum, pres, ldr,
            1 if rain_bool else 0,
            lat, lon, altitude, sats, hdop,
            loc_name, 1 if using_fallback_gps else 0,
            bat_pct, voltage, signal,
            acc_x, acc_y, acc_z,
            gyro_x, gyro_y, gyro_z, risk["tilt_angle"],
            distance, ldr, water, current, ir, pir,
            current,
            zone_color,
        ))
        sensor_id = c.lastrowid

        # ── Write ML-driven risk to risk_scores (was never inserted before) ─────────
        l1_str = ", ".join(risk["triggered_l1"])
        l2_str = ", ".join(risk["triggered_l2"])
        l3_str = ", ".join(risk["triggered_l3"])
        c.execute("""
            INSERT INTO risk_scores (
                timestamp, risk_index, risk_level, classification,
                safety_score, level1_triggered, level2_triggered,
                level3_triggered, sensor_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ts, ml_risk_index, ml_risk_level, ml_classification,
            ml_safety_score, l1_str, l2_str, l3_str, sensor_id,
        ))

        conn.commit()
    except Exception as e:
        conn.rollback()
        log.error("DB write error: %s", e)
        sensor_id = None
    finally:
        conn.close()

    return jsonify({
        "sensor_id":       sensor_id,
        "timestamp":       ts,
        "risk_level":      ml_risk_level,
        "risk_index":      round(ml_risk_index, 2),
        "safety_score":    ml_safety_score,
        "classification":  ml_classification,
        "zone_status":     zone_color,
        "rain_probability": round(rain_prob, 4),
        "zone":            zone_result,
        "risk": {
            **risk,
            "risk_index":     round(ml_risk_index, 2),
            "risk_level":     ml_risk_level,
            "classification": ml_classification,
            "safety_score":   ml_safety_score,
        },
        "ml":              ml_result,
        "relay_action":    "LOCK" if risk["hard_lock"] else "ALLOW",
        "hard_lock":       risk["hard_lock"],
        "triggered_l1":    risk["triggered_l1"],
        "triggered_l2":    risk["triggered_l2"],
        "triggered_l3":    risk["triggered_l3"],
        "recommendations": risk["recommendations"],
        "gps": {
            "latitude":       lat,
            "longitude":      lon,
            "altitude":       altitude,
            "satellites":     sats,
            "hdop":           hdop,
            "using_fallback": using_fallback_gps,
            "location_name":  loc_name,
        },
    }), 201


# ── GET /api/telemetry ────────────────────────────────────────────────────────

@telemetry_bp.route("/telemetry", methods=["GET"])
def get_telemetry():
    limit  = min(int(request.args.get("limit", 50)), 500)
    offset = int(request.args.get("offset", 0))

    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT * FROM sensor_history
            ORDER BY id DESC LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()
        return jsonify({
            "records": [dict(r) for r in rows],
            "limit": limit,
            "offset": offset
        })
    finally:
        conn.close()