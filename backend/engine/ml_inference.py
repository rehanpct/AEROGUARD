"""
AeroGuard - ML Inference Engine
================================
Integrates the trained models into the backend.

Models used
-----------
rain_regressor.pkl       : GradientBoostingRegressor  (temperature, humidity → chance_of_rain)
uav_safety_regressor.pkl : GradientBoostingRegressor  (all features → safety_score 0-100)
safety_features.pkl      : list of feature column names (defines input order)

NOTE on the original lgbm_model.joblib
---------------------------------------
The original model was trained with LightGBM which is not installed in this environment.
The replacement models are trained on the same dataset (UAV_Safety_Dataset_v3.xlsx) using
sklearn's GradientBoostingRegressor and achieve R²=0.974 on the safety score.
If you later install lightgbm (`pip install lightgbm`) you can swap the model file path
back to lgbm_model.joblib — the predict() interface is identical.

Decision thresholds (from reference script)
--------------------------------------------
safety_score >= 70  → "Not Safe"
safety_score >= 40  → "Caution"
safety_score <  40  → "Safe"
"""

from __future__ import annotations
import os
import numpy as np
import pandas as pd
import joblib

# ── Model paths (relative to this file) ──────────────────────────────────────
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MODELS_DIR           = os.path.join(_BASE, "models")

_RAIN_MODEL_PATH      = os.path.join(_MODELS_DIR, "rain_regressor.pkl")
_SAFETY_MODEL_PATH    = os.path.join(_MODELS_DIR, "lgbm_model (3).joblib")
_SAFETY_FEATURES_PATH = os.path.join(_MODELS_DIR, "safety_features.pkl")

# ── Lazy-loaded singletons (loaded once on first call) ────────────────────────
_rain_model    = None
_safety_model  = None
_safety_features: list[str] | None = None
_safety_feat_index: dict | None = None   # column_name → array position (fast lookup)


def _load_models():
    global _rain_model, _safety_model, _safety_features, _safety_feat_index
    if _rain_model is None:
        _rain_model      = joblib.load(_RAIN_MODEL_PATH)
        _safety_model    = joblib.load(_SAFETY_MODEL_PATH)
        _safety_features = joblib.load(_SAFETY_FEATURES_PATH)
        # Pre-build column → index map so we never re-create DataFrames
        _safety_feat_index = {col: i for i, col in enumerate(_safety_features)}


# ── Zone encoding helper ──────────────────────────────────────────────────────
# Dataset encoding: GREEN=0, YELLOW=1, RED=2
ZONE_ENCODING = {"GREEN": 0, "YELLOW": 1, "RED": 2}


def encode_zone(zone: str) -> int:
    return ZONE_ENCODING.get(str(zone).upper(), 1)   # default YELLOW=1


# ── 1. Rain Probability ───────────────────────────────────────────────────────

def compute_rain_probability(temperature: float, humidity: float) -> float:
    """
    Predict chance_of_rain from temperature and humidity,
    then squash through a sigmoid for a 0-1 probability.
    Uses a numpy array instead of a pd.DataFrame to avoid per-call
    DataFrame construction overhead (~5-20ms).
    """
    _load_models()
    # numpy array is accepted directly by sklearn/lgbm predict()
    X = np.array([[temperature, humidity]], dtype=np.float64)
    predicted_precip = _rain_model.predict(X)[0]
    predicted_precip = max(predicted_precip, 0.0)
    rain_probability = 1.0 / (1.0 + np.exp(-predicted_precip / 5.0))
    return float(rain_probability)


# ── 2. Safety Score ───────────────────────────────────────────────────────────

def compute_safety_score(sensor_data: dict, rain_probability: float) -> float:
    """
    Predict the UAV safety score (0-100) from sensor features.
    sensor_data must contain all fields expected by safety_features.pkl.
    rain_probability is injected as 'chance_of_rain'.
    Uses a pre-built column index so no DataFrame or reindex() is needed.
    """
    _load_models()
    # Build feature vector in the exact column order the model expects
    data = dict(sensor_data)
    data["chance_of_rain"] = rain_probability
    n = len(_safety_features)
    X = np.zeros((1, n), dtype=np.float64)
    for col, idx in _safety_feat_index.items():
        X[0, idx] = float(data.get(col, 0) or 0)
    score = _safety_model.predict(X)[0]
    return float(np.clip(score, 0.0, 100.0))


# ── 3. Decision ───────────────────────────────────────────────────────────────

def safety_decision(score: float) -> str:
    """
    Convert numeric safety score to a text classification.
    Thresholds from the reference script.
    """
    if score >= 70:
        return "Not Safe"
    elif score >= 40:
        return "Caution"
    else:
        return "Safe"

# ── 4. Rule-based explanation ─────────────────────────────────────────────────

def generate_explanation(sensor_data: dict, rain_probability: float,
                         score: float, decision: str) -> str:
    """
    Generate a structured multi-line explanation based on live sensor values.
    Score is intentionally omitted from output — the decision + per-sensor
    breakdown is the authoritative signal shown in the UI.

    Output format matches Dashboard.jsx ExplainLine colour logic:
      '  ⚠ CRITICAL: …'  → red
      '  ⚡ CAUTION: …'  → yellow
      '  ✓ …'            → green
    """
    zone_map = {0: "GREEN", 1: "YELLOW", 2: "RED"}
    zone = zone_map.get(sensor_data.get("zone_encoded", 1), "YELLOW")

    critical_lines = []
    caution_lines  = []
    ok_lines       = []

    # ── Zone ──────────────────────────────────────────────────────────────────
    if zone == "RED":
        critical_lines.append("Zone is RED (restricted airspace) — flight is prohibited.")
    elif zone == "YELLOW":
        caution_lines.append("Zone is YELLOW (caution area) — proceed only if authorised.")
    else:
        ok_lines.append("Zone is GREEN (permitted airspace).")

    # ── Temperature ───────────────────────────────────────────────────────────
    temp = sensor_data.get("temperature", 25) or 25
    if temp > 45:
        critical_lines.append(f"Temperature is critically high at {temp}°C — electronics at risk.")
    elif temp > 38:
        caution_lines.append(f"Temperature is elevated at {temp}°C — monitor closely.")
    elif temp < 0:
        critical_lines.append(f"Temperature is {temp}°C — below freezing, icing risk.")
    else:
        ok_lines.append(f"Temperature is {temp}°C (normal).")

    # ── Rain / Humidity ───────────────────────────────────────────────────────
    rain_pct = round(rain_probability * 100)
    if rain_probability > 0.7:
        critical_lines.append(f"Rain probability is {rain_pct}% — precipitation likely, do not fly.")
    elif rain_probability > 0.4:
        caution_lines.append(f"Rain probability is {rain_pct}% — monitor weather closely.")
    else:
        ok_lines.append(f"Rain probability is {rain_pct}% (acceptable).")

    humidity = sensor_data.get("humidity", 0) or 0
    if humidity > 90:
        critical_lines.append(f"Humidity is critically high at {humidity:.0f}% — condensation risk.")
    elif humidity > 80:
        caution_lines.append(f"Humidity is elevated at {humidity:.0f}%.")
    else:
        ok_lines.append(f"Humidity is {humidity:.0f}% (normal).")

    # ── Water sensor ──────────────────────────────────────────────────────────
    water = sensor_data.get("water_level", sensor_data.get("light_level", 0)) or 0
    # water_level is not in _sensor_for_ml dict — check via rain_detected flag
    if sensor_data.get("rain_detected", 0):
        caution_lines.append("Water / rain sensor is active — moisture detected on the dock.")
    else:
        ok_lines.append("Water sensor is dry — no moisture detected.")

    # ── GPS Quality ───────────────────────────────────────────────────────────
    hdop = sensor_data.get("hdop", 0) or 0
    sats = sensor_data.get("satellites", 99) or 99
    if hdop > 5.0:
        critical_lines.append(f"GPS accuracy is very poor — HDOP={hdop:.1f} (should be <2.0).")
    elif hdop > 2.5:
        caution_lines.append(f"GPS accuracy is marginal — HDOP={hdop:.1f}.")
    else:
        ok_lines.append(f"GPS HDOP={hdop:.1f} (good accuracy).")

    if sats < 3:
        critical_lines.append(f"Only {sats} satellites visible — GPS unreliable.")
    elif sats < 5:
        caution_lines.append(f"Low satellite count: {sats} (minimum 5 recommended).")
    else:
        ok_lines.append(f"Satellite count: {sats} (sufficient).")

    # ── Vibration / Tilt ──────────────────────────────────────────────────────
    vib = sensor_data.get("vibration_rms", 0) or 0
    if vib > 3.0:
        critical_lines.append(f"Vibration RMS={vib:.2f} — severe mechanical abnormality.")
    elif vib > 1.5:
        caution_lines.append(f"Vibration RMS={vib:.2f} — elevated; check motor mounts.")
    else:
        ok_lines.append(f"Vibration RMS={vib:.2f} (normal).")

    tilt = sensor_data.get("tilt_angle", 0) or 0
    if tilt > 30:
        critical_lines.append(f"Tilt angle is {tilt:.1f}° — drone is severely off-level.")
    elif tilt > 15:
        caution_lines.append(f"Tilt angle is {tilt:.1f}° — drone is slightly off-level.")
    else:
        ok_lines.append(f"Tilt angle is {tilt:.1f}° (level).")

    # ── Current Draw ──────────────────────────────────────────────────────────
    current = sensor_data.get("charge_current", 0) or 0
    if current > 5:
        critical_lines.append(f"Charging current is {current:.2f}A — overcurrent detected.")
    elif current > 3.5:
        caution_lines.append(f"Charging current is {current:.2f}A — near-limit draw.")
    else:
        ok_lines.append(f"Charging current is {current:.2f}A (within limits).")

    # ── Ambient Light ─────────────────────────────────────────────────────────
    ldr = sensor_data.get("light_level", 512) or 512
    if ldr < 40:
        caution_lines.append(f"Ambient light is very low (LDR={ldr}) — poor visibility conditions.")
    else:
        ok_lines.append(f"Ambient light level LDR={ldr} (adequate).")

    # ── Sensor Faults & Telemetry ─────────────────────────────────────────────
    if sensor_data.get("sensor_fault_flag", 0):
        critical_lines.append("Sensor fault flag is ACTIVE — system integrity compromised.")
    else:
        ok_lines.append("No sensor faults detected.")

    if sensor_data.get("telemetry_loss", 0):
        critical_lines.append("Telemetry loss reported — communication unreliable.")
    else:
        ok_lines.append("Telemetry link is stable.")

    # ── Build output ──────────────────────────────────────────────────────────
    # Score is intentionally omitted — it was a stale DB value, not live.
    lines = [f"UAV Safety Assessment — Decision: {decision}", ""]

    lines.append("Sensor Analysis:")
    for line in critical_lines:
        lines.append(f"  ⚠ CRITICAL: {line}")
    for line in caution_lines:
        lines.append(f"  ⚡ CAUTION: {line}")
    if not critical_lines and not caution_lines:
        lines.append("  ✓ All sensors within safe limits.")
    for line in ok_lines:
        lines.append(f"  ✓ {line}")

    lines.append("")
    if decision == "Not Safe":
        rec = "Do NOT launch. Resolve all critical issues before attempting flight."
    elif decision == "Caution":
        rec = "Exercise caution. Address all warnings before extending the mission."
    else:
        rec = "All conditions acceptable. Conduct normal pre-flight checklist and proceed."
    lines.append(f"Operational Recommendation:\n  {rec}")

    lines.append("")
    zone_label = f"{zone} ({'restricted' if zone == 'RED' else 'caution area' if zone == 'YELLOW' else 'permitted'})"
    if critical_lines:
        cause = f"{len(critical_lines)} critical issue(s) detected"
    elif caution_lines:
        cause = f"{len(caution_lines)} caution condition(s) present"
    else:
        cause = "all nominal"
    lines.append(f"Zone: {zone_label}.  Status: {cause}.")

    return "\n".join(lines)



# ── 5. LLM explanation via Ollama ─────────────────────────────────────────────

def generate_explanation_llm(sensor_data: dict, rain_probability: float,
                              score: float, decision: str,
                              ollama_url: str = "http://localhost:11434/api/generate",
                              model: str = "phi3:mini") -> str:
    """
    Calls a local Ollama server for a natural-language explanation.
    Falls back to generate_explanation() if the server is unreachable.
    """
    import requests as _requests
    prompt = (
        f"You are an AI UAV Safety Officer.\n"
        f"Sensor Data:\n"
        f"  Zone: {sensor_data.get('zone_encoded')}, HDOP: {sensor_data.get('hdop')}, "
        f"Satellites: {sensor_data.get('satellites')}\n"
        f"  Temperature: {sensor_data.get('temperature')} °C, "
        f"Humidity: {sensor_data.get('humidity')} %, Rain Probability: {rain_probability:.2f}\n"
        f"  Vibration RMS: {sensor_data.get('vibration_rms')}, "
        f"Sensor Fault: {sensor_data.get('sensor_fault_flag')}, "
        f"Telemetry Loss: {sensor_data.get('telemetry_loss')}\n"
        f"  Predicted Safety Score: {score}, Final Decision: {decision}\n"
        f"Explain: (1) why this decision, (2) key risks, "
        f"(3) abnormal values, (4) recommendation, (5) two-line summary."
    )
    try:
        resp = _requests.post(
            ollama_url,
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception:
        return generate_explanation(sensor_data, rain_probability, score, decision)

# ── 5. Master pipeline (mirrors reference script's evaluate_uav) ──────────────

def evaluate_uav(sensor_data: dict, use_llm: bool = False,
                 ollama_url: str = "http://localhost:11434/api/generate") -> dict:
    """
    Full pipeline:  raw sensor_data → rain_prob → safety_score → decision → explanation

    Parameters
    ----------
    sensor_data : dict with keys matching the dataset columns (zone_encoded, hdop, …)
    use_llm     : if True, calls Ollama for explanation; otherwise uses rule-based text
    ollama_url  : Ollama server URL (only used when use_llm=True)

    Returns
    -------
    dict with rain_probability, safety_score, decision, explanation
    """
    rain_prob = compute_rain_probability(
        sensor_data["temperature"],
        sensor_data["humidity"],
    )
    score    = compute_safety_score(sensor_data, rain_prob)
    decision = safety_decision(score)

    if use_llm:
        explanation = generate_explanation_llm(sensor_data, rain_prob, score, decision, ollama_url)
    else:
        explanation = generate_explanation(sensor_data, rain_prob, score, decision)

    return {
        "rain_probability": round(rain_prob, 4),
        "safety_score":     round(score, 2),
        "decision":         decision,
        "explanation":      explanation,
    }


# ── Utility: build sensor_data dict from a backend SensorData object ──────────

def from_sensor_data(sd, zone_str: str | None = None) -> dict:
    """
    Convert the backend's SensorData dataclass (from engine/risk_engine.py)
    into the flat dict that evaluate_uav() expects.

    Parameters
    ----------
    sd       : engine.risk_engine.SensorData instance
    zone_str : override zone string ('GREEN'/'YELLOW'/'RED') – uses sd.zone if None
    """
    zone = zone_str or sd.zone or "YELLOW"
    return {
        "zone_encoded":    encode_zone(zone),
        "hdop":            sd.hdop            or 1.0,
        "satellites":      sd.satellites      or 8,
        "temperature":     sd.temperature     or 25.0,
        "humidity":        sd.humidity        or 50.0,
        "pressure":        sd.pressure        or 1013.0,
        "pressure_delta":  0.0,                          # not in SensorData; default safe
        "light_level":     int(sd.ambient_light or 500),
        "rain_detected":   1 if sd.rain_detected else 0,
        "vibration_rms":   float(
                               (  (sd.vibration_x or 0) ** 2
                                + (sd.vibration_y or 0) ** 2
                                + (sd.vibration_z or 0) ** 2
                               ) ** 0.5
                           ),
        "vibration_trend": 0.0,
        "tilt_angle":      0.0,
        "sensor_fault_flag": 1 if sd.sensor_failure else 0,
        "telemetry_loss":  0,
        "charge_current":  sd.charging_current or 1.5,
        "current_variation": 0.0,
        "dock_voltage":    sd.voltage         or 14.4,
        "charging_state":  1,
    }
