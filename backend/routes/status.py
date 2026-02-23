"""
AeroGuard - Status Routes
/api/status         GET – current system status (used by frontend polling)
/api/status/summary GET – 24h aggregated analytics
"""

from __future__ import annotations
import logging
from flask import Blueprint, request, jsonify
from database import get_db
from constants import GPS_FALLBACK_LAT as FALLBACK_LAT, GPS_FALLBACK_LON as FALLBACK_LON, GPS_FALLBACK_NAME as FALLBACK_NAME
from engine.ml_inference import generate_explanation_llm, compute_rain_probability, safety_decision


log = logging.getLogger(__name__)
status_bp = Blueprint("status", __name__)


# ── GET /api/status ────────────────────────────────────────────────────────────

@status_bp.route("/status", methods=["GET"])
def get_status():
    """
    Return the most recent telemetry snapshot plus latest risk assessment.
    Used by the frontend every 2 seconds.

    Response includes:
      - risk_index, risk_level, classification, safety_score, hard_lock
      - zone_status, zone_name, relay_action
      - rain_probability
      - gps block (with fallback flag)
      - environment block
      - sensors block  (ALL Arduino fields + tilt_angle)
      - drone block    (legacy battery/voltage/signal)
      - triggered rules
    """
    conn = get_db()
    try:
        # Latest sensor reading
        row = conn.execute("""
            SELECT * FROM sensor_history ORDER BY id DESC LIMIT 1
        """).fetchone()

        # Latest risk assessment
        risk_row = conn.execute("""
            SELECT * FROM risk_scores ORDER BY id DESC LIMIT 1
        """).fetchone()

        if row is None:
            # Generate a default explanation with safe values
            _default_sensor = {
                "zone_encoded": 0, "hdop": 1.0, "satellites": 8,
                "temperature": 25.0, "humidity": 55.0, "pressure": 1013.0,
                "light_level": 500, "rain_detected": 0, "vibration_rms": 0.0,
                "vibration_trend": 0.0, "tilt_angle": 0.0, "sensor_fault_flag": 0,
                "telemetry_loss": 0, "charge_current": 1.5, "current_variation": 0.0,
                "dock_voltage": 14.4, "charging_state": 1,
            }
            _default_expl = generate_explanation_llm(_default_sensor, 0.0, 20.0, "Safe")
            return jsonify({
                "status": "NO_DATA",
                "message": "No telemetry received yet. Waiting for Arduino...",
                "risk_level":   "SAFE",
                "risk_index":   0,
                "safety_score": 100,
                "zone_status":  "GREEN",
                "gps": {
                    "latitude":       FALLBACK_LAT,
                    "longitude":      FALLBACK_LON,
                    "using_fallback": True,
                    "location_name":  FALLBACK_NAME,
                    "satellites": 0, "hdop": 0.0, "altitude": 0.0,
                },
                "sensors": {},
                "environment": {},
                "drone": {},
                "rain_probability": 0.0,
                "relay_action": "ALLOW",
                "ml_explanation": _default_expl,
                "ml_decision": "Safe",
            })

        s = dict(row)
        r = dict(risk_row) if risk_row else {}

        # Derive values with safe defaults
        risk_index   = r.get("risk_index",     0.0)
        risk_level   = r.get("risk_level",     "SAFE")
        safety_score = r.get("safety_score",   100.0)
        classification = r.get("classification", "Safe to Fly")
        hard_lock    = bool(r.get("level1_triggered", ""))

        zone_color   = s.get("zone", "GREEN") or "GREEN"
        using_fb     = bool(s.get("using_fallback_gps", 1))
        loc_name     = s.get("location_name") or (FALLBACK_NAME if using_fb else "Live GPS")

        # Rain probability – compute via ML model (temperature + humidity)
        humidity = s.get("humidity") or 55.0
        temperature = s.get("temperature") or 25.0
        water = s.get("water") or 0
        try:
            rain_prob = compute_rain_probability(temperature, humidity)
        except Exception:
            rain_prob = round(min(1.0, (humidity / 100) * 0.4 + (water / 1023) * 0.6), 4)

        # ML explanation – build sensor dict from latest row
        _ml_score = r.get("safety_score") or 20.0
        _ml_decision_str = safety_decision(float(_ml_score))
        _sensor_for_ml = {
            "zone_encoded":      {"GREEN": 0, "YELLOW": 1, "RED": 2}.get(str(s.get("zone", "GREEN")).upper(), 1),
            "hdop":             s.get("hdop") or 1.0,
            "satellites":       s.get("satellites") or 8,
            "temperature":      temperature,
            "humidity":         humidity,
            "pressure":         s.get("pressure") or 1013.0,
            "light_level":      int(s.get("ldr") or 500),
            "rain_detected":    1 if s.get("rain_detected") else 0,
            "vibration_rms":    float(((s.get("acc_x") or 0)**2 + (s.get("acc_y") or 0)**2 + (s.get("acc_z") or 0)**2)**0.5),
            "vibration_trend":  0.0,
            "tilt_angle":       s.get("tilt_angle") or 0.0,
            "sensor_fault_flag": 1 if s.get("sensor_failure") else 0,
            "telemetry_loss":   0,
            "charge_current":   s.get("charging_current") or 1.5,
            "current_variation": 0.0,
            "dock_voltage":     s.get("voltage") or 14.4,
            "charging_state":   1,
        }
        try:
            ml_explanation = generate_explanation_llm(_sensor_for_ml, rain_prob, float(_ml_score), _ml_decision_str)
        except Exception as e:
            log.warning("ML explanation error: %s", e)
            ml_explanation = "ML explanation unavailable."

        return jsonify({
            # ── Top-level risk ────────────────────────────────────────────────
            "risk_index":    round(risk_index, 2),
            "risk_level":    risk_level,                # SAFE | CAUTION | UNSAFE
            "classification": classification,
            "safety_score":  round(safety_score or 100, 2),
            "hard_lock":     hard_lock,
            "rain_probability": rain_prob,

            # ── Zone ──────────────────────────────────────────────────────────
            "zone_status":  zone_color,
            "zone_name":    "",                         # populated by zone engine on ingest
            "relay_action": "LOCK" if hard_lock else "ALLOW",

            # ── Timestamp ────────────────────────────────────────────────────
            "timestamp": s.get("timestamp", ""),

            # ── GPS block ─────────────────────────────────────────────────────
            "gps": {
                "latitude":       s.get("latitude",   FALLBACK_LAT),
                "longitude":      s.get("longitude",  FALLBACK_LON),
                "altitude":       s.get("altitude",   0.0),
                "satellites":     s.get("satellites", 0),
                "hdop":           s.get("hdop",       0.0),
                "using_fallback": using_fb,
                "location_name":  loc_name,
            },

            # ── Environment (atmospheric sensors) ─────────────────────────────
            "environment": {
                "temperature": s.get("temperature"),
                "humidity":    s.get("humidity"),
                "pressure":    s.get("pressure"),
                "ldr":         s.get("ldr"),            # light level (0-1023)
                "rain_detected": bool(s.get("rain_detected")),
            },

            # ── ALL Arduino sensor readings ────────────────────────────────────
            "sensors": {
                # IMU
                "acc_x":       s.get("acc_x",   0.0),
                "acc_y":       s.get("acc_y",   0.0),
                "acc_z":       s.get("acc_z",   9.8),
                "gyro_x":      s.get("gyro_x",  0.0),
                "gyro_y":      s.get("gyro_y",  0.0),
                "gyro_z":      s.get("gyro_z",  0.0),
                "tilt_angle":  s.get("tilt_angle", 0.0),

                # Ultrasonic
                "distance":    s.get("distance", 999.0),

                # Light & presence
                "ldr":         s.get("ldr",   512),
                "ir":          s.get("ir",    0),
                "pir":         s.get("pir",   0),

                # Water / rain
                "water":       s.get("water", 0),

                # Electrical
                "current_a":   s.get("current_a",  0.0),
                "charging_current": s.get("charging_current", 0.0),
            },

            # ── Legacy drone block (battery, signal) ──────────────────────────
            "drone": {
                "battery_pct":     s.get("battery_pct"),
                "voltage":         s.get("voltage"),
                "signal_strength": s.get("signal_strength"),
                "charging_current": s.get("charging_current"),
            },

            # ── Triggered rules breakdown ─────────────────────────────────────
            "triggered_l1": [x for x in (r.get("level1_triggered") or "").split(", ") if x],
            "triggered_l2": [x for x in (r.get("level2_triggered") or "").split(", ") if x],
            "triggered_l3": [x for x in (r.get("level3_triggered") or "").split(", ") if x],

            # ── ML Engine output ──────────────────────────────────────────────
            "ml_explanation": ml_explanation,
            "ml_decision":    _ml_decision_str,
        })

    finally:
        conn.close()


# ── GET /api/status/summary ────────────────────────────────────────────────────

@status_bp.route("/status/summary", methods=["GET"])
def get_summary():
    """24-hour aggregated analytics."""
    conn = get_db()
    try:
        hours = int(request.args.get("hours", 24))
        cutoff = f"datetime('now', '-{hours} hours')"

        stats = conn.execute(f"""
            SELECT
                COUNT(*)            AS total_records,
                AVG(risk_index)     AS avg_risk_24h,
                MAX(risk_index)     AS max_risk_24h,
                MIN(risk_index)     AS min_risk_24h,
                AVG(safety_score)   AS avg_safety_score
            FROM risk_scores
            WHERE timestamp > {cutoff}
        """).fetchone()

        zone_dist = conn.execute(f"""
            SELECT zone, COUNT(*) AS cnt
            FROM sensor_history
            WHERE timestamp > {cutoff} AND zone IS NOT NULL
            GROUP BY zone
        """).fetchall()

        return jsonify({
            "hours":          hours,
            "avg_risk_24h":   round(stats["avg_risk_24h"]   or 0, 2),
            "max_risk_24h":   round(stats["max_risk_24h"]   or 0, 2),
            "min_risk_24h":   round(stats["min_risk_24h"]   or 0, 2),
            "avg_safety_score": round(stats["avg_safety_score"] or 100, 2),
            "total_records":  stats["total_records"] or 0,
            "zone_distribution": {r["zone"]: r["cnt"] for r in zone_dist},
        })
    finally:
        conn.close()
