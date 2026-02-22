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

_RAIN_MODEL_PATH     = os.path.join(_BASE, "rain_regressor.pkl")
_SAFETY_MODEL_PATH   = os.path.join(_BASE, "uav_safety_regressor.pkl")
_SAFETY_FEATURES_PATH = os.path.join(_BASE, "safety_features.pkl")

# ── Lazy-loaded singletons (loaded once on first call) ────────────────────────
_rain_model    = None
_safety_model  = None
_safety_features: list[str] | None = None


def _load_models():
    global _rain_model, _safety_model, _safety_features
    if _rain_model is None:
        _rain_model    = joblib.load(_RAIN_MODEL_PATH)
        _safety_model  = joblib.load(_SAFETY_MODEL_PATH)
        _safety_features = joblib.load(_SAFETY_FEATURES_PATH)


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
    Mirrors the reference script exactly.
    """
    _load_models()
    df = pd.DataFrame([[temperature, humidity]], columns=["temperature", "humidity"])
    predicted_precip = _rain_model.predict(df)[0]
    predicted_precip = max(predicted_precip, 0.0)
    rain_probability = 1.0 / (1.0 + np.exp(-predicted_precip / 5.0))
    return float(rain_probability)


# ── 2. Safety Score ───────────────────────────────────────────────────────────

def compute_safety_score(sensor_data: dict, rain_probability: float) -> float:
    """
    Predict the UAV safety score (0-100) from sensor features.
    sensor_data must contain all fields expected by safety_features.pkl.
    rain_probability is injected as 'chance_of_rain'.
    """
    _load_models()
    data = dict(sensor_data)
    data["chance_of_rain"] = rain_probability
    df_input = pd.DataFrame([data])

    # Ensure correct column order and only required features
    df_input = df_input.reindex(columns=_safety_features, fill_value=0)
    score = _safety_model.predict(df_input)[0]
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


# ── 4. Feature explanation (no LLM required) ─────────────────────────────────

def generate_explanation(sensor_data: dict, rain_probability: float,
                          score: float, decision: str) -> str:
    """
    Rule-based natural-language explanation of the ML output.
    Replaces the Ollama/llama3 call from the reference script so the backend
    works without a running LLM server.

    If you DO have Ollama running locally, call generate_explanation_llm()
    instead and it will use the original prompt.
    """
    lines = [
        f"UAV Safety Assessment — Decision: {decision} (score: {score:.1f}/100)",
        "",
        "Risk Factors:",
    ]

    risks = []
    cautions = []

    z = int(sensor_data.get("zone_encoded", 1))
    zone_name = {0: "GREEN (permitted)", 1: "YELLOW (caution)", 2: "RED (restricted)"}.get(z, "Unknown")
    if z == 2:
        risks.append(f"Zone is RED (restricted) — flight is prohibited.")
    elif z == 1:
        cautions.append(f"Zone is YELLOW — authorisation may be required.")

    if sensor_data.get("sensor_fault_flag", 0):
        risks.append("Sensor fault detected — system integrity compromised.")

    if sensor_data.get("telemetry_loss", 0):
        risks.append("Telemetry loss reported — loss of situational awareness.")

    hdop = sensor_data.get("hdop", 1.0)
    if hdop > 5.0:
        risks.append(f"HDOP={hdop:.1f} — GPS accuracy very poor.")
    elif hdop > 2.0:
        cautions.append(f"HDOP={hdop:.1f} — GPS accuracy moderate.")

    sats = sensor_data.get("satellites", 8)
    if sats < 4:
        risks.append(f"Only {sats} satellites — insufficient for safe navigation.")
    elif sats < 6:
        cautions.append(f"{sats} satellites — marginal coverage.")

    vib = sensor_data.get("vibration_rms", 0.0)
    if vib > 3.0:
        risks.append(f"Vibration RMS={vib:.2f} — severe mechanical abnormality.")
    elif vib > 1.5:
        cautions.append(f"Vibration RMS={vib:.2f} — elevated, monitor during flight.")

    rain_pct = rain_probability * 100
    if rain_pct > 70:
        risks.append(f"Rain probability {rain_pct:.0f}% — high precipitation risk.")
    elif rain_pct > 40:
        cautions.append(f"Rain probability {rain_pct:.0f}% — monitor conditions.")

    temp = sensor_data.get("temperature", 25.0)
    if temp > 45:
        risks.append(f"Temperature {temp}°C — overheating risk to electronics.")
    elif temp < -5:
        risks.append(f"Temperature {temp}°C — battery performance severely degraded.")

    cv = sensor_data.get("current_variation", 0.0)
    if cv > 0.8:
        cautions.append(f"Charging current variation {cv:.2f}A — power supply unstable.")

    tilt = sensor_data.get("tilt_angle", 0.0)
    if tilt > 30:
        risks.append(f"Tilt angle {tilt:.1f}° — drone not level, check placement.")

    for r in risks:
        lines.append(f"  ⚠ CRITICAL: {r}")
    for c in cautions:
        lines.append(f"  ⚡ CAUTION:  {c}")

    if not risks and not cautions:
        lines.append("  ✓ No significant risk factors detected.")

    lines += [
        "",
        "Operational Recommendation:",
    ]
    if decision == "Not Safe":
        lines.append("  Do NOT launch. Resolve all critical issues before attempting flight.")
    elif decision == "Caution":
        lines.append("  Proceed with heightened awareness. Monitor all flagged parameters continuously.")
        lines.append("  Consider postponing until conditions improve.")
    else:
        lines.append("  Conditions are acceptable. Conduct normal pre-flight checklist and proceed.")

    lines += [
        "",
        f"Summary: ML safety score {score:.1f}/100 in zone {zone_name}.",
        f"Decision '{decision}' based on {'critical fault(s)' if risks else 'marginal condition(s)' if cautions else 'nominal readings'}.",
    ]

    return "\n".join(lines)


# ── 4b. Optional: LLM explanation via Ollama (reference script version) ───────

def generate_explanation_llm(sensor_data: dict, rain_probability: float,
                              score: float, decision: str,
                              ollama_url: str = "http://localhost:11434/api/generate",
                              model: str = "llama3") -> str:
    """
    Calls a local Ollama server for a natural-language explanation.
    Falls back to generate_explanation() if the server is unreachable.
    """
    import requests as _requests
    prompt = f"""
You are an AI UAV Safety Officer.
Sensor Data:
Zone: {sensor_data['zone_encoded']}
HDOP: {sensor_data['hdop']}
Satellites: {sensor_data['satellites']}
Temperature: {sensor_data['temperature']} °C
Humidity: {sensor_data['humidity']} %
Rain Probability: {rain_probability}
Vibration RMS: {sensor_data['vibration_rms']}
Sensor Fault: {sensor_data['sensor_fault_flag']}
Telemetry Loss: {sensor_data['telemetry_loss']}
Predicted Safety Score: {score}
Final Decision: {decision}
Explain clearly:
1. Why this decision was made.
2. Key risk contributors.
3. Any abnormal sensor values.
4. Operational recommendation.
5. Two-line summary.
"""
    try:
        resp = _requests.post(
            ollama_url,
            json={"model": model, "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.2}},
            timeout=30,
        )
        return resp.json()["response"]
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
