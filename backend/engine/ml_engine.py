from __future__ import annotations
import os
import math
import logging
from typing import Optional

import pandas as pd
import warnings
warnings.filterwarnings("ignore", category=UserWarning)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# MODEL PATHS
# ─────────────────────────────────────────────────────────────

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MODELS_DIR       = os.path.join(_HERE, "models")
RAIN_MODEL_PATH   = os.path.join(_MODELS_DIR, "rain_regressor.pkl")
SAFETY_MODEL_PATH = os.path.join(_MODELS_DIR, "lgbm_model (3).joblib")

# ─────────────────────────────────────────────────────────────
# MODEL LOADING
# ─────────────────────────────────────────────────────────────

_rain_model = None
_safety_model = None
_models_loaded = False
_load_error: Optional[str] = None


def _load_models():
    global _rain_model, _safety_model, _models_loaded, _load_error

    if _models_loaded:
        return

    try:
        import joblib
        _rain_model   = joblib.load(RAIN_MODEL_PATH)
        _safety_model = joblib.load(SAFETY_MODEL_PATH)
        logger.info("[ML Engine] Models loaded successfully.")
    except Exception as e:
        _load_error = str(e)
        logger.warning(f"[ML Engine] Model load failed: {e}")

    _models_loaded = True


def models_available() -> bool:
    _load_models()
    return _rain_model is not None and _safety_model is not None


def get_load_error() -> Optional[str]:
    _load_models()
    return _load_error


# ─────────────────────────────────────────────────────────────
# RAIN PROBABILITY
# ─────────────────────────────────────────────────────────────

def compute_rain_probability(temperature: float, humidity: float) -> float:
    _load_models()

    if _rain_model is not None:
        try:
            predicted_precip = _rain_model.predict([[temperature, humidity]])[0]
            predicted_precip = max(float(predicted_precip), 0.0)
            rain_prob = 1.0 / (1.0 + math.exp(-predicted_precip / 5.0))
            return round(float(rain_prob), 4)
        except Exception as e:
            logger.warning(f"[ML Engine] Rain prediction error: {e}")

    # fallback heuristic
    base = (humidity - 50.0) / 100.0
    temp_factor = max(0.0, (25.0 - temperature) / 50.0)
    return round(min(1.0, max(0.0, base + temp_factor)), 4)


# ─────────────────────────────────────────────────────────────
# SAFETY SCORE (FORCED EXACT MODEL FEATURES)
# ─────────────────────────────────────────────────────────────

def compute_safety_score(sensor_data: dict, rain_probability: float) -> Optional[float]:
    _load_models()

    if _safety_model is None:
        return None

    try:
        # Get exactly what model expects
        expected_features = _safety_model.feature_name_

        if not expected_features:
            logger.warning("[ML Engine] Model has no stored feature names.")
            return None

        # Build row dynamically using model feature list
        row = {}

        for feature in expected_features:

            if feature == "zone_encoded":
                row[feature] = _zone_to_int(sensor_data.get("zone", "GREEN"))

            elif feature == "chance_of_rain":
                row[feature] = float(rain_probability)

            elif feature == "vibration_rms":
                row[feature] = float(
                    sensor_data.get("vibration_rms") or _calc_vib_rms(sensor_data)
                )

            else:
                row[feature] = sensor_data.get(feature, 0)

        df = pd.DataFrame([row])

        score = _safety_model.predict(df)[0]

        return round(float(score), 2)

    except Exception as e:
        logger.warning(f"[ML Engine] Safety prediction error: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# DECISION LAYER
# ─────────────────────────────────────────────────────────────

def ml_safety_decision(score: float) -> str:
    if score >= 70:
        return "Not Safe to Fly"
    elif score >= 40:
        return "Fly with Caution"
    else:
        return "Safe to Fly"


# ─────────────────────────────────────────────────────────────
# FULL PIPELINE
# ─────────────────────────────────────────────────────────────

def run_ml_pipeline(sensor_data: dict) -> dict:

    rain_prob = compute_rain_probability(
        sensor_data.get("temperature", 25.0),
        sensor_data.get("humidity", 50.0),
    )

    safety_score = compute_safety_score(sensor_data, rain_prob)

    classification = None
    if safety_score is not None:
        classification = ml_safety_decision(safety_score)

    return {
        "ml_available":      models_available(),
        "rain_probability":  rain_prob,
        "safety_score":      safety_score,
        "ml_classification": classification,
        "load_error":        get_load_error(),
    }


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _zone_to_int(zone: str) -> int:
    return {"GREEN": 0, "YELLOW": 1, "RED": 2}.get(str(zone).upper(), 1)


def _calc_vib_rms(sensor_data: dict) -> float:
    x = float(sensor_data.get("vibration_x") or 0.0)
    y = float(sensor_data.get("vibration_y") or 0.0)
    z = float(sensor_data.get("vibration_z") or 0.0)
    return round(math.sqrt(x**2 + y**2 + z**2), 4)