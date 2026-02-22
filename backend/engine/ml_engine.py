"""
AeroGuard - ML Inference Engine
Wraps the two trained models:
  - rain_regressor.pkl     : predicts precipitation → sigmoid → rain probability
  - lgbm_model.joblib      : predicts safety score (0–100)

Both models require `lightgbm` to be installed:
    pip install lightgbm

If lightgbm is not installed, the engine falls back gracefully to the
rule-based risk engine so the rest of the backend keeps working.

Safety score interpretation (from training data):
    score >= 70   →  Not Safe to Fly
    score >= 40   →  Fly with Caution
    score  < 40   →  Safe to Fly

Feature order expected by lgbm_model (18 features, matches dataset columns
minus 'chance_of_rain' and 'safety_score'):
    zone_encoded, hdop, satellites, temperature, humidity, pressure,
    pressure_delta, light_level, rain_detected, vibration_rms,
    vibration_trend, tilt_angle, sensor_fault_flag, telemetry_loss,
    charge_current, current_variation, dock_voltage, charging_state

The rain model expects: [temperature, humidity]
"""

from __future__ import annotations
import os
import math
import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Model paths ───────────────────────────────────────────────────────────────
# engine/ → backend/ → models/
_BACKEND_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAIN_MODEL_PATH   = os.path.join(_BACKEND_DIR, "models", "rain_regressor.pkl")
SAFETY_MODEL_PATH = os.path.join(_BACKEND_DIR, "models", "lgbm_model.joblib")

# ── Feature list the safety model was trained on ──────────────────────────────
# Order must match training. 'rain_probability' (chance_of_rain) is appended
# last as it is derived from the rain model at inference time.
SAFETY_FEATURES = [
    "zone_encoded",
    "hdop",
    "satellites",
    "temperature",
    "humidity",
    "pressure",
    "pressure_delta",
    "light_level",
    "rain_detected",
    "vibration_rms",
    "vibration_trend",
    "tilt_angle",
    "sensor_fault_flag",
    "telemetry_loss",
    "charge_current",
    "current_variation",
    "dock_voltage",
    "charging_state",
    "chance_of_rain",   # appended after rain model inference
]


# ── Lazy model loading ─────────────────────────────────────────────────────────
_rain_model   = None
_safety_model = None
_models_loaded = False
_load_error: Optional[str] = None


def _load_models():
    """Attempt to load both models once. Sets _load_error on failure."""
    global _rain_model, _safety_model, _models_loaded, _load_error
    if _models_loaded:
        return

    try:
        import joblib
        _rain_model   = joblib.load(RAIN_MODEL_PATH)
        _safety_model = joblib.load(SAFETY_MODEL_PATH)
        _models_loaded = True
        logger.info("[ML Engine] Both models loaded successfully.")
    except ModuleNotFoundError as e:
        _load_error = f"Missing dependency: {e}. Run `pip install lightgbm`."
        logger.warning(f"[ML Engine] {_load_error}")
        _models_loaded = True   # don't retry on every request
    except FileNotFoundError as e:
        _load_error = f"Model file not found: {e}"
        logger.warning(f"[ML Engine] {_load_error}")
        _models_loaded = True
    except Exception as e:
        _load_error = str(e)
        logger.warning(f"[ML Engine] Failed to load models: {e}")
        _models_loaded = True


def models_available() -> bool:
    _load_models()
    return _rain_model is not None and _safety_model is not None


def get_load_error() -> Optional[str]:
    _load_models()
    return _load_error


# ── Rain Probability ──────────────────────────────────────────────────────────

def compute_rain_probability(temperature: float, humidity: float) -> float:
    """
    Predict rain probability using the rain regression model.
    Returns a float in [0, 1].
    Falls back to a simple heuristic if the model is unavailable.
    """
    _load_models()
    if _rain_model is not None:
        predicted_precip = _rain_model.predict([[temperature, humidity]])[0]
        predicted_precip = max(float(predicted_precip), 0.0)
        # Sigmoid mapping: precip → probability
        rain_prob = 1.0 / (1.0 + math.exp(-predicted_precip / 5.0))
        return round(float(rain_prob), 4)

    # ── Fallback heuristic ────────────────────────────────────────────────────
    # High humidity + low temperature historically correlates with precipitation
    base = (humidity - 50.0) / 100.0          # 0 at 50%, 0.5 at 100%
    temp_factor = max(0.0, (25.0 - temperature) / 50.0)
    return round(min(1.0, max(0.0, base + temp_factor)), 4)


# ── Safety Score ──────────────────────────────────────────────────────────────

def compute_safety_score(sensor_data: dict, rain_probability: float) -> float:
    """
    Predict safety score (0–100) using the LightGBM model.
    Higher score = more dangerous.
    Falls back to None if model unavailable (caller should use rule engine).
    """
    _load_models()
    if _safety_model is None:
        return None

    # Build feature row in the correct column order
    row = {
        "zone_encoded":    _zone_to_int(sensor_data.get("zone", "GREEN")),
        "hdop":            float(sensor_data.get("hdop")            or 1.0),
        "satellites":      int(  sensor_data.get("satellites")      or 8),
        "temperature":     float(sensor_data.get("temperature")     or 25.0),
        "humidity":        float(sensor_data.get("humidity")        or 50.0),
        "pressure":        float(sensor_data.get("pressure")        or 1013.0),
        "pressure_delta":  float(sensor_data.get("pressure_delta")  or 0.0),
        "light_level":     int(  sensor_data.get("ambient_light")   or 500),
        "rain_detected":   int(bool(sensor_data.get("rain_detected", False))),
        "vibration_rms":   _calc_vib_rms(sensor_data),
        "vibration_trend": float(sensor_data.get("vibration_trend") or 0.0),
        "tilt_angle":      float(sensor_data.get("tilt_angle")      or 0.0),
        "sensor_fault_flag": int(bool(sensor_data.get("sensor_failure", False))),
        "telemetry_loss":  int(bool(sensor_data.get("telemetry_loss", False))),
        "charge_current":  float(sensor_data.get("charging_current") or 0.0),
        "current_variation": float(sensor_data.get("current_variation") or 0.0),
        "dock_voltage":    float(sensor_data.get("voltage")          or 12.0),
        "charging_state":  int(bool(sensor_data.get("charging_state", True))),
        "chance_of_rain":  float(rain_probability),
    }

    df = pd.DataFrame([row])[SAFETY_FEATURES]
    score = _safety_model.predict(df)[0]
    return round(float(score), 2)


# ── Decision Layer ────────────────────────────────────────────────────────────

def ml_safety_decision(score: float) -> str:
    """Convert a safety score to a classification string."""
    if score >= 70:
        return "Not Safe to Fly"
    elif score >= 40:
        return "Fly with Caution"
    else:
        return "Safe to Fly"


# ── Full Pipeline ─────────────────────────────────────────────────────────────

def run_ml_pipeline(sensor_data: dict) -> dict:
    """
    Run the complete ML pipeline for a given sensor_data dict.

    Returns a dict with:
        ml_available      : bool
        rain_probability  : float  [0,1]
        safety_score      : float | None  (None = model unavailable)
        ml_classification : str | None
        load_error        : str | None
    """
    rain_prob = compute_rain_probability(
        sensor_data.get("temperature", 25.0),
        sensor_data.get("humidity",    50.0),
    )

    safety_score = compute_safety_score(sensor_data, rain_prob)

    if safety_score is not None:
        classification = ml_safety_decision(safety_score)
    else:
        classification = None

    return {
        "ml_available":      models_available(),
        "rain_probability":  rain_prob,
        "safety_score":      safety_score,
        "ml_classification": classification,
        "load_error":        get_load_error(),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _zone_to_int(zone: str) -> int:
    """Map zone string to the integer encoding used during training."""
    return {"GREEN": 0, "YELLOW": 1, "RED": 2}.get(str(zone).upper(), 1)


def _calc_vib_rms(sensor_data: dict) -> float:
    """
    Compute vibration RMS for the ML model feature.

    The dataset's vibration_rms column ranges 0.1–1.5 (normalised sensor units).
    The ESP32 sends raw axis values (vibration_x/y/z) in m/s² which can be much
    larger. We normalise them into the same 0.1–1.5 band the model was trained on
    so the model receives a meaningful input.

    Priority:
      1. Use vibration_rms directly if already provided (pre-normalised).
      2. Compute from x/y/z axes, then scale into [0.1, 1.5].
    """
    # Use pre-computed value if present
    if sensor_data.get("vibration_rms") is not None:
        return min(1.5, max(0.1, float(sensor_data["vibration_rms"])))

    x = float(sensor_data.get("vibration_x") or 0.0)
    y = float(sensor_data.get("vibration_y") or 0.0)
    z = float(sensor_data.get("vibration_z") or 0.0)
    raw_rms = math.sqrt(x**2 + y**2 + z**2)

    # Scale: raw values from MPU6050 in m/s² typically range 0–20+.
    # Map into model's expected range [0.1, 1.5] proportionally.
    # 0 m/s² → 0.1 (idle baseline), 15+ m/s² → 1.5 (max spike)
    scaled = 0.1 + (raw_rms / 15.0) * 1.4
    return round(min(1.5, max(0.1, scaled)), 4)
