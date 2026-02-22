"""
AeroGuard - /api/ai_prediction
Integrates the real trained ML models:
  - rain_regressor.pkl   → rain probability
  - lgbm_model.joblib    → safety score (0–100)

Falls back to rule-based analytics if lightgbm is not installed.

Endpoints
─────────
POST /api/ai_prediction              On-demand prediction (no DB write)
GET  /api/ai_prediction/trend        Risk trend + linear regression
GET  /api/ai_prediction/vso          Virtual Safety Officer advice
POST /api/ai_prediction/explain      LLM explanation (requires Ollama)
GET  /api/ai_prediction/ml_status    Model health check
"""

from flask import Blueprint, request, jsonify
from database import get_db
from engine import (
    evaluate_risk, classify_zone, SensorData,
    run_ml_pipeline, models_available, get_load_error,
)
import json
import statistics
import requests as http_requests

ai_bp = Blueprint("ai_prediction", __name__)

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"


# ── 1. On-demand ML + Rule prediction ─────────────────────────────────────────

@ai_bp.route("/ai_prediction", methods=["POST"])
def predict():
    """
    Run both the ML pipeline and rule engine on a telemetry payload.
    Nothing is saved to the database — useful for pre-flight dry runs.
    """
    payload = request.get_json(force=True, silent=True)
    if not payload:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    lat = payload.get("latitude")
    lon = payload.get("longitude")
    zone_result = {"zone": "YELLOW", "zone_name": "Unknown", "reason": "No GPS", "hard_lock": False}
    if lat is not None and lon is not None:
        zone_result = classify_zone(float(lat), float(lon))

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
    rule_result = evaluate_risk(sd)
    ml_result   = run_ml_pipeline({**payload, "zone": zone_result["zone"]})

    # Combined decision: rule hard-lock always wins, then ML, then rule fallback
    if rule_result["hard_lock"]:
        final_decision = "Not Safe to Fly"
        final_source   = "rule_engine_override"
    elif ml_result["ml_classification"] is not None:
        final_decision = ml_result["ml_classification"]
        final_source   = "ml_model"
    else:
        final_decision = rule_result["classification"]
        final_source   = "rule_engine_fallback"

    return jsonify({
        "zone":             zone_result,
        "rule_engine":      rule_result,
        "ml":               ml_result,
        "final_decision":   final_decision,
        "final_source":     final_source,
        "relay_action":     "LOCK" if rule_result["hard_lock"] or final_decision == "Not Safe to Fly" else "ALLOW",
        "rain_probability": ml_result["rain_probability"],
        "safety_score":     ml_result["safety_score"],
        "ml_classification":ml_result["ml_classification"],
    }), 200


# ── 2. Model health check ──────────────────────────────────────────────────────

@ai_bp.route("/ai_prediction/ml_status", methods=["GET"])
def ml_status():
    """Returns whether the ML models loaded successfully."""
    return jsonify({
        "ml_available": models_available(),
        "load_error":   get_load_error(),
        "models": {
            "rain_regressor": "rain_regressor.pkl",
            "safety_model":   "lgbm_model.joblib",
        },
        "install_hint": "pip install lightgbm" if not models_available() else None,
    }), 200


# ── 3. Trend Analysis ──────────────────────────────────────────────────────────

@ai_bp.route("/ai_prediction/trend", methods=["GET"])
def trend_analysis():
    """Linear regression over recent risk scores to predict the next value."""
    window = min(int(request.args.get("window", 20)), 100)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT risk_index, timestamp FROM risk_scores ORDER BY id DESC LIMIT ?",
            (window,)
        ).fetchall()

        if not rows:
            return jsonify({"error": "No risk data available yet"}), 404

        scores     = [float(r["risk_index"]) for r in rows]
        scores_asc = list(reversed(scores))
        n          = len(scores_asc)
        avg        = round(statistics.mean(scores), 2)
        stdev      = round(statistics.stdev(scores) if n > 1 else 0.0, 2)

        if n >= 2:
            x_mean    = (n - 1) / 2.0
            y_mean    = statistics.mean(scores_asc)
            num       = sum((i - x_mean) * (scores_asc[i] - y_mean) for i in range(n))
            den       = sum((i - x_mean) ** 2 for i in range(n))
            slope     = num / den if den != 0 else 0.0
            intercept = y_mean - slope * x_mean
            predicted_next = round(max(0.0, min(100.0, intercept + slope * n)), 2)
        else:
            slope, predicted_next = 0.0, scores[0]

        if   slope >  1.5: trend = "RISING_FAST"
        elif slope >  0.3: trend = "RISING"
        elif slope < -1.5: trend = "FALLING_FAST"
        elif slope < -0.3: trend = "FALLING"
        else:              trend = "STABLE"

        return jsonify({
            "window":              window,
            "data_points":         n,
            "moving_average":      avg,
            "std_deviation":       stdev,
            "slope":               round(slope, 4),
            "trend":               trend,
            "predicted_next":      predicted_next,
            "high_risk_frequency": round(sum(1 for s in scores if s > 60) / len(scores), 3),
            "scores_series":       scores_asc,
        }), 200
    finally:
        conn.close()


# ── 4. Virtual Safety Officer ─────────────────────────────────────────────────

@ai_bp.route("/ai_prediction/vso", methods=["GET"])
def virtual_safety_officer():
    """Prioritised natural-language advice from the latest DB record."""
    conn = get_db()
    try:
        latest = conn.execute("""
            SELECT s.*, r.risk_index, r.classification,
                   r.level1_triggered, r.level2_triggered, r.level3_triggered
            FROM sensor_history s
            LEFT JOIN risk_scores r ON r.sensor_id = s.id
            ORDER BY s.id DESC LIMIT 1
        """).fetchone()

        if not latest:
            return jsonify({
                "vso_status": "STANDBY",
                "advice":     ["No telemetry received. Awaiting sensor data."],
                "action":     "WAIT",
            }), 200

        row = dict(latest)
        l1  = json.loads(row.get("level1_triggered") or "[]")
        l2  = json.loads(row.get("level2_triggered") or "[]")
        l3  = json.loads(row.get("level3_triggered") or "[]")
        zone           = row.get("zone", "YELLOW")
        risk_index     = row.get("risk_index", 0) or 0
        classification = row.get("classification", "Unknown")

        # Re-run ML on latest snapshot
        snap = {k: row.get(k) for k in (
            "temperature","humidity","pressure","ambient_light","hdop","satellites",
            "battery_pct","voltage","signal_strength","vibration_x","vibration_y",
            "vibration_z","charging_current",
        )}
        snap["rain_detected"]  = bool(row.get("rain_detected"))
        snap["sensor_failure"] = False
        snap["zone"]           = zone
        ml_result = run_ml_pipeline(snap)

        advice = []
        action = "ALLOW"

        if l1:
            action = "LOCK"
            if "RED_ZONE"       in l1: advice.append("CRITICAL: RED restricted zone – flight prohibited.")
            if "RAIN_DETECTED"  in l1: advice.append("CRITICAL: Rain detected – do not fly, moisture risk.")
            if "SENSOR_FAILURE" in l1: advice.append("CRITICAL: Sensor failure – system cannot guarantee safety.")
        elif l2:
            action = "LOCK"
            l2_map = {
                "HDOP_BAD":          "GPS accuracy too poor for safe navigation. Wait for a better fix.",
                "LOW_SATELLITES":    "Insufficient satellite coverage. Move to an open area.",
                "BATTERY_CRITICAL":  "Battery critically low. Charge before launch.",
                "VIBRATION_SPIKE":   "Severe vibration spike – inspect propellers and motor mounts.",
                "SIGNAL_CRITICAL":   "Control signal critically weak – risk of losing the drone.",
                "CHARGING_UNSTABLE": "Charging current unstable – check power supply.",
                "WIND_DANGER":       "Wind dangerously high – ground all operations.",
            }
            for rule in l2:
                for key, msg in l2_map.items():
                    if key in rule: advice.append(msg)
        elif l3:
            action = "CAUTION"
            l3_map = {
                "BATTERY_LOW":   "Battery below 20% – plan a shorter flight or recharge.",
                "WIND_CAUTION":  "Elevated wind – maintain close visual range.",
                "HDOP_CAUTION":  "Moderate GPS accuracy – avoid GPS-dependent flight modes.",
                "YELLOW_ZONE":   "YELLOW caution zone – verify authorisation.",
                "HUMIDITY_HIGH": "High humidity – inspect electronics after landing.",
                "TEMP_HIGH":     "High temperature – monitor battery temps.",
                "SIGNAL_WEAK":   "Weak signal – stay within 100m line-of-sight.",
            }
            for rule in l3:
                for key, msg in l3_map.items():
                    if key in rule: advice.append(msg)
        else:
            advice.append("All systems nominal. Conditions are safe for flight.")

        # ML overlay
        if ml_result["ml_classification"] and ml_result["ml_classification"] != "Safe to Fly" and not l1:
            note = (
                f"ML model flags: {ml_result['ml_classification']} "
                f"(safety score {ml_result['safety_score']:.1f}/100, "
                f"rain probability {ml_result['rain_probability']:.0%})."
            )
            advice.insert(0, note)
            if action == "ALLOW":
                action = "CAUTION"

        return jsonify({
            "vso_status":      classification,
            "risk_index":      round(risk_index, 2),
            "action":          action,
            "zone":            zone,
            "advice":          advice,
            "ml": {
                "available":        ml_result["ml_available"],
                "safety_score":     ml_result["safety_score"],
                "rain_probability": ml_result["rain_probability"],
                "classification":   ml_result["ml_classification"],
            },
            "triggered_rules": {"l1": l1, "l2": l2, "l3": l3},
        }), 200
    finally:
        conn.close()


# ── 5. LLM Explanation via Ollama ─────────────────────────────────────────────

@ai_bp.route("/ai_prediction/explain", methods=["POST"])
def generate_explanation():
    """
    Sends sensor context + ML scores to a local Ollama LLM for a
    natural-language safety briefing.

    Requires Ollama running locally:
        ollama serve
        ollama pull llama3

    Request body: same schema as POST /api/telemetry
    Optional: safety_score, rain_probability, decision (if already computed)
    """
    payload = request.get_json(force=True, silent=True)
    if not payload:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    rain_prob    = payload.get("rain_probability")
    safety_score = payload.get("safety_score")
    decision     = payload.get("decision")

    if rain_prob is None or safety_score is None:
        lat      = payload.get("latitude")
        lon      = payload.get("longitude")
        zone_str = "YELLOW"
        if lat and lon:
            zone_str = classify_zone(float(lat), float(lon)).get("zone", "YELLOW")
        ml      = run_ml_pipeline({**payload, "zone": zone_str})
        rain_prob    = ml["rain_probability"]
        safety_score = ml["safety_score"]
        decision     = ml["ml_classification"] or "Unknown"

    prompt = f"""
You are an AI UAV Safety Officer.

Sensor Data:
  Zone:             {payload.get('zone', payload.get('zone_encoded', 'N/A'))}
  HDOP:             {payload.get('hdop', 'N/A')}
  Satellites:       {payload.get('satellites', 'N/A')}
  Temperature:      {payload.get('temperature', 'N/A')} °C
  Humidity:         {payload.get('humidity', 'N/A')} %
  Rain Detected:    {payload.get('rain_detected', False)}
  Rain Probability: {rain_prob:.2%}
  Vibration RMS:    {payload.get('vibration_rms', 'N/A')}
  Sensor Fault:     {payload.get('sensor_failure', False)}
  Telemetry Loss:   {payload.get('telemetry_loss', False)}

Predicted Safety Score: {safety_score if safety_score is not None else 'unavailable'}
Final Decision:         {decision}

Explain clearly:
1. Why this decision was made.
2. Key risk contributors.
3. Any abnormal sensor values.
4. Operational recommendation.
5. Two-line summary.

Keep the response under 200 words.
"""

    try:
        resp = http_requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0.2}},
            timeout=30,
        )
        resp.raise_for_status()
        explanation   = resp.json().get("response", "").strip()
        llm_available = True
    except Exception as e:
        explanation = (
            f"LLM unavailable ({e}). "
            f"Decision: {decision}. Safety score: {safety_score}. "
            f"Rain probability: {rain_prob:.0%}. "
            "Run `ollama serve` and `ollama pull llama3` to enable full explanations."
        )
        llm_available = False

    return jsonify({
        "decision":         decision,
        "safety_score":     safety_score,
        "rain_probability": rain_prob,
        "explanation":      explanation,
        "llm_available":    llm_available,
    }), 200
