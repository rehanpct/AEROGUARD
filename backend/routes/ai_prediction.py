"""
AeroGuard - AI Prediction Routes
/api/ai_prediction        POST  – on-demand prediction
/api/ai_prediction/trend  GET   – risk trend analysis
/api/ai_prediction/vso    GET   – Virtual Safety Officer advice
/api/ai_prediction/status GET   – ML model status
"""

from __future__ import annotations
import logging
from flask import Blueprint, request, jsonify

from database import get_db
from engine import evaluate_risk, classify_zone, run_ml_pipeline, models_available, get_load_error
from engine.risk_engine import SensorData

log = logging.getLogger(__name__)
ai_bp = Blueprint("ai_prediction", __name__)

from constants import GPS_FALLBACK_LAT as FALLBACK_LAT, GPS_FALLBACK_LON as FALLBACK_LON



def _safe_float(d, k, default=None):
    v = d.get(k, default)
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _safe_int(d, k, default=None):
    v = d.get(k, default)
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _build_sensor_data(payload: dict, zone: str) -> SensorData:
    """Build SensorData from either Arduino or legacy payload format."""
    # Support both Arduino field names and legacy field names
    acc_x = _safe_float(payload, "accX") or _safe_float(payload, "vibration_x", 0.0)
    acc_y = _safe_float(payload, "accY") or _safe_float(payload, "vibration_y", 0.0)
    acc_z = _safe_float(payload, "accZ") or _safe_float(payload, "vibration_z", 9.8)

    return SensorData(
        temperature=   _safe_float(payload, "temperature", 25.0),
        humidity=      _safe_float(payload, "humidity",    55.0),
        pressure=      _safe_float(payload, "pressure",    1013.0),
        rain_detected= payload.get("rain_detected") or ((_safe_int(payload, "water", 0) or 0) > 100),
        latitude=      _safe_float(payload, "latitude",   FALLBACK_LAT),
        longitude=     _safe_float(payload, "longitude",  FALLBACK_LON),
        altitude=      _safe_float(payload, "altitude",   0.0),
        satellites=    _safe_int(payload, "satellites",   0),
        hdop=          _safe_float(payload, "hdop",       1.0),
        acc_x=acc_x,   acc_y=acc_y, acc_z=acc_z,
        gyro_x=        _safe_float(payload, "gyroX", 0.0),
        gyro_y=        _safe_float(payload, "gyroY", 0.0),
        gyro_z=        _safe_float(payload, "gyroZ", 0.0),
        distance=      _safe_float(payload, "distance", 999.0),
        ldr=           _safe_int(payload, "ldr", 512),
        water=         _safe_int(payload, "water", 0),
        current_a=     _safe_float(payload, "current", None) or _safe_float(payload, "charging_current", 0.0),
        ir=            _safe_int(payload, "ir",  0),
        pir=           _safe_int(payload, "pir", 0),
        battery_pct=   _safe_float(payload, "battery_pct",     None),
        voltage=       _safe_float(payload, "voltage",         None),
        signal_strength= _safe_int(payload, "signal_strength", None),
        zone=          zone,
        sensor_failure= bool(payload.get("sensor_failure", False)),
    )


# ── POST /api/ai_prediction ────────────────────────────────────────────────────

@ai_bp.route("/ai_prediction", methods=["POST"])
def predict():
    payload = request.get_json(force=True, silent=True) or {}

    lat = _safe_float(payload, "latitude",  FALLBACK_LAT)
    lon = _safe_float(payload, "longitude", FALLBACK_LON)
    zone_result = classify_zone(lat, lon)
    zone_color  = zone_result["zone"]

    sd = _build_sensor_data(payload, zone_color)
    rule_result = evaluate_risk(sd)

    ml_input = {
        "temperature":   sd.temperature or 25.0,
        "humidity":      sd.humidity    or 55.0,
        "pressure":      sd.pressure    or 1013.0,
        "rain_detected": bool(sd.rain_detected),
        "latitude":      lat, "longitude": lon,
        "altitude":      sd.altitude or 0.0,
        "satellites":    sd.satellites or 0,
        "hdop":          sd.hdop or 1.0,
        "battery_pct":   sd.battery_pct or 100.0,
        "voltage":       sd.voltage or 12.0,
        "signal_strength": sd.signal_strength or 100,
        "vibration_x":   sd.acc_x or 0.0,
        "vibration_y":   sd.acc_y or 0.0,
        "vibration_z":   sd.acc_z or 9.8,
        "charging_current": sd.current_a or 0.0,
        "sensor_failure": sd.sensor_failure,
        "ambient_light": sd.ldr or 512,
        "wind_speed":    0.0,
        "zone":          zone_color,
    }

    try:
        ml_result = run_ml_pipeline(ml_input)
    except Exception as e:
        log.warning("ML pipeline error: %s", e)
        ml_result = {"safety_score": rule_result["safety_score"], "rain_probability": 0.1}

    # Final decision: L1 rule always wins, then ML
    final_decision = rule_result["classification"]
    if not rule_result["hard_lock"] and ml_result.get("ml_classification"):
        final_decision = ml_result["ml_classification"]

    return jsonify({
        "zone":        zone_result,
        "rule_engine": rule_result,
        "ml":          ml_result,
        "final_decision": final_decision,
        "risk_level":  rule_result["risk_level"],
        "safety_score": rule_result["safety_score"],
        "rain_probability": ml_result.get("rain_probability", 0.1),
        "relay_action": "LOCK" if rule_result["hard_lock"] else "ALLOW",
        "risk_probability": rule_result["risk_index"] / 100.0,
    }), 200


# ── GET /api/ai_prediction/trend ──────────────────────────────────────────────

@ai_bp.route("/ai_prediction/trend", methods=["GET"])
def trend():
    window = min(int(request.args.get("window", 20)), 200)
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT risk_index FROM risk_scores
            ORDER BY id DESC LIMIT ?
        """, (window,)).fetchall()
        values = [r["risk_index"] for r in rows][::-1]
        if len(values) < 2:
            return jsonify({"trend": "stable", "predicted_next": 0, "values": values})

        delta = values[-1] - values[0]
        trend_label = "rising" if delta > 5 else "falling" if delta < -5 else "stable"
        predicted = min(100, max(0, values[-1] + delta / len(values)))
        return jsonify({"trend": trend_label, "predicted_next": round(predicted, 2), "values": values})
    finally:
        conn.close()


# ── GET /api/ai_prediction/vso ────────────────────────────────────────────────

@ai_bp.route("/ai_prediction/vso", methods=["GET"])
def vso():
    conn = get_db()
    try:
        sensor = conn.execute("SELECT * FROM sensor_history ORDER BY id DESC LIMIT 1").fetchone()
        risk   = conn.execute("SELECT * FROM risk_scores   ORDER BY id DESC LIMIT 1").fetchone()
        if not sensor or not risk:
            return jsonify({"advice": ["No data available yet."], "action": "WAIT", "confidence": 0})

        s = dict(sensor)
        r = dict(risk)
        l1 = [x for x in (r.get("level1_triggered") or "").split(", ") if x]
        l2 = [x for x in (r.get("level2_triggered") or "").split(", ") if x]

        advice = []
        if l1:
            advice.append(f"CRITICAL: {l1[0]} – flight is blocked.")
        for t in l1[1:]:
            advice.append(f"Also: {t}")
        for t in l2[:3]:
            advice.append(f"Caution: {t}")
        if not advice:
            advice.append("All systems nominal. Pre-flight conditions acceptable.")

        action = "ABORT" if l1 else ("CAUTION" if l2 else "PROCEED")
        return jsonify({
            "advice":     advice,
            "action":     action,
            "risk_level": r.get("risk_level", "SAFE"),
            "confidence": 95 if l1 else (80 if l2 else 97),
        })
    finally:
        conn.close()


# ── GET /api/ai_prediction/status ─────────────────────────────────────────────

@ai_bp.route("/ai_prediction/status", methods=["GET"])
def ml_status():
    return jsonify({
        "models_available": models_available(),
        "load_error":       get_load_error(),
    })