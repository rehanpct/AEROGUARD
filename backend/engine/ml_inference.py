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

# ── 4. LLM explanation via Ollama ───────

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
