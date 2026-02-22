"""
AeroGuard - Rule-Based Risk Engine
Evaluates sensor + telemetry data through a 3-level priority rule system.

Priority Levels
───────────────
Level 1 – Hard Override  : Immediately classifies as UNSAFE (risk = 100).
                           Flight must be blocked. No negotiation.
Level 2 – High Risk      : Significant penalty applied to risk index.
Level 3 – Moderate Risk  : Moderate penalty applied to risk index.

Output
──────
risk_index      float  [0, 100]
classification  str    'Safe to Fly' | 'Fly with Caution' | 'Not Safe to Fly'
triggered_l1    list   Level-1 rules that fired
triggered_l2    list   Level-2 rules that fired
triggered_l3    list   Level-3 rules that fired
recommendations list   Human-readable guidance
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Thresholds (tune for your hardware) ──────────────────────────────────────

class Thresholds:
    # Environmental
    TEMP_HIGH       = 45.0      # °C – above this: L3
    TEMP_LOW        = -5.0      # °C – below this: L3
    HUMIDITY_HIGH   = 90.0      # % – above this: L3
    WIND_CAUTION    = 10.0      # m/s – L3
    WIND_DANGER     = 20.0      # m/s – L2

    # GPS
    HDOP_CAUTION    = 2.0       # L3
    HDOP_BAD        = 5.0       # L2
    SAT_MIN         = 4         # fewer than this → L2

    # Drone Health
    BATTERY_LOW     = 20.0      # % – L3
    BATTERY_CRIT    = 10.0      # % – L2
    VOLTAGE_LOW     = 10.5      # V – L3
    SIGNAL_WEAK     = 30        # % – L3
    SIGNAL_CRIT     = 10        # % – L2

    # Vibration (m/s² magnitude) from MPU6050
    VIBRATION_SPIKE = 15.0      # L2
    VIBRATION_HIGH  = 8.0       # L3

    # Charging
    CHARGING_UNSTABLE_DELTA = 0.5   # A variation → L2


# ── Risk Penalties ────────────────────────────────────────────────────────────

L1_PENALTY = 100    # Instant max
L2_PENALTY = 25     # Significant
L3_PENALTY = 10     # Moderate


# ── Classification Bands ──────────────────────────────────────────────────────

SAFE_MAX    = 30
CAUTION_MAX = 60
# > 60 → Not Safe to Fly


# ── Input Model ───────────────────────────────────────────────────────────────

@dataclass
class SensorData:
    # Environmental
    temperature:     Optional[float] = None
    humidity:        Optional[float] = None
    pressure:        Optional[float] = None
    ambient_light:   Optional[float] = None
    wind_speed:      Optional[float] = None
    rain_detected:   Optional[bool]  = None

    # GPS
    latitude:        Optional[float] = None
    longitude:       Optional[float] = None
    altitude:        Optional[float] = None
    satellites:      Optional[int]   = None
    hdop:            Optional[float] = None

    # Drone Telemetry
    battery_pct:     Optional[float] = None
    voltage:         Optional[float] = None
    signal_strength: Optional[int]   = None
    vibration_x:     Optional[float] = None
    vibration_y:     Optional[float] = None
    vibration_z:     Optional[float] = None
    charging_current:Optional[float] = None

    # Pre-computed zone (set by zone engine before calling risk engine)
    zone:            Optional[str]   = None     # 'GREEN' | 'YELLOW' | 'RED'

    # Sensor health flags (True = failed/missing)
    sensor_failure:  bool = False


# ── Engine ────────────────────────────────────────────────────────────────────

def evaluate_risk(data: SensorData, prev_charging_current: Optional[float] = None) -> dict:
    """
    Run all rules against `data` and return a risk assessment dict.

    Parameters
    ----------
    data                   : SensorData instance populated from incoming telemetry.
    prev_charging_current  : Previous charging current reading for delta calculation.
    """
    triggered_l1: List[str] = []
    triggered_l2: List[str] = []
    triggered_l3: List[str] = []
    recommendations: List[str] = []

    # ── Level 1 – Hard Override Rules ────────────────────────────────────────

    # 1.1 Red Zone
    if data.zone == "RED":
        triggered_l1.append("RED_ZONE")
        recommendations.append("Location is in a RED restricted zone. Flight is prohibited.")

    # 1.2 Rain Detected
    if data.rain_detected is True:
        triggered_l1.append("RAIN_DETECTED")
        recommendations.append("Rain detected. Do not fly – water ingress risk.")

    # 1.3 Sensor Failure
    if data.sensor_failure:
        triggered_l1.append("SENSOR_FAILURE")
        recommendations.append("Critical sensor failure detected. System cannot guarantee safe operation.")

    # ── Level 2 – High Risk Rules ─────────────────────────────────────────────

    # 2.1 HDOP too high (poor GPS accuracy)
    if data.hdop is not None and data.hdop > Thresholds.HDOP_BAD:
        triggered_l2.append(f"HDOP_BAD ({data.hdop:.1f})")
        recommendations.append(f"GPS accuracy very poor (HDOP={data.hdop:.1f}). Wait for better satellite fix.")

    # 2.2 Too few satellites
    if data.satellites is not None and data.satellites < Thresholds.SAT_MIN:
        triggered_l2.append(f"LOW_SATELLITES ({data.satellites})")
        recommendations.append(f"Only {data.satellites} satellites acquired. Minimum {Thresholds.SAT_MIN} required.")

    # 2.3 Critical battery
    if data.battery_pct is not None and data.battery_pct <= Thresholds.BATTERY_CRIT:
        triggered_l2.append(f"BATTERY_CRITICAL ({data.battery_pct:.0f}%)")
        recommendations.append("Battery critically low. Charge before flight.")

    # 2.4 Vibration spike
    if data.vibration_x is not None:
        import math
        magnitude = math.sqrt(
            (data.vibration_x or 0) ** 2 +
            (data.vibration_y or 0) ** 2 +
            (data.vibration_z or 0) ** 2
        )
        if magnitude > Thresholds.VIBRATION_SPIKE:
            triggered_l2.append(f"VIBRATION_SPIKE ({magnitude:.1f} m/s²)")
            recommendations.append("Severe vibration detected. Inspect drone for mechanical faults.")

    # 2.5 Critical signal strength
    if data.signal_strength is not None and data.signal_strength <= Thresholds.SIGNAL_CRIT:
        triggered_l2.append(f"SIGNAL_CRITICAL ({data.signal_strength}%)")
        recommendations.append("Signal strength critically low. Risk of total comms loss.")

    # 2.6 Charging current unstable
    if (
        data.charging_current is not None
        and prev_charging_current is not None
        and abs(data.charging_current - prev_charging_current) > Thresholds.CHARGING_UNSTABLE_DELTA
    ):
        delta = abs(data.charging_current - prev_charging_current)
        triggered_l2.append(f"CHARGING_UNSTABLE (Δ{delta:.2f}A)")
        recommendations.append("Charging current unstable. Check power supply before flight.")

    # 2.7 High wind speed
    if data.wind_speed is not None and data.wind_speed > Thresholds.WIND_DANGER:
        triggered_l2.append(f"WIND_DANGER ({data.wind_speed:.1f} m/s)")
        recommendations.append("Wind speed dangerously high. Ground all operations.")

    # ── Level 3 – Moderate Risk Rules ────────────────────────────────────────

    # 3.1 HDOP caution band
    if (
        data.hdop is not None
        and Thresholds.HDOP_CAUTION < data.hdop <= Thresholds.HDOP_BAD
    ):
        triggered_l3.append(f"HDOP_CAUTION ({data.hdop:.1f})")
        recommendations.append("GPS accuracy moderate. Exercise positional caution.")

    # 3.2 Battery low (not yet critical)
    if (
        data.battery_pct is not None
        and Thresholds.BATTERY_CRIT < data.battery_pct <= Thresholds.BATTERY_LOW
    ):
        triggered_l3.append(f"BATTERY_LOW ({data.battery_pct:.0f}%)")
        recommendations.append("Battery below 20%. Plan a short flight or recharge first.")

    # 3.3 Voltage low
    if data.voltage is not None and data.voltage < Thresholds.VOLTAGE_LOW:
        triggered_l3.append(f"VOLTAGE_LOW ({data.voltage:.1f}V)")
        recommendations.append("Battery voltage below safe threshold.")

    # 3.4 High temperature
    if data.temperature is not None and data.temperature > Thresholds.TEMP_HIGH:
        triggered_l3.append(f"TEMP_HIGH ({data.temperature:.1f}°C)")
        recommendations.append("Ambient temperature too high. Electronics may overheat.")

    # 3.5 Low temperature
    if data.temperature is not None and data.temperature < Thresholds.TEMP_LOW:
        triggered_l3.append(f"TEMP_LOW ({data.temperature:.1f}°C)")
        recommendations.append("Temperature below freezing. Battery performance degraded.")

    # 3.6 High humidity
    if data.humidity is not None and data.humidity > Thresholds.HUMIDITY_HIGH:
        triggered_l3.append(f"HUMIDITY_HIGH ({data.humidity:.0f}%)")
        recommendations.append("Very high humidity. Condensation risk on electronics.")

    # 3.7 Moderate wind
    if (
        data.wind_speed is not None
        and Thresholds.WIND_CAUTION < data.wind_speed <= Thresholds.WIND_DANGER
    ):
        triggered_l3.append(f"WIND_CAUTION ({data.wind_speed:.1f} m/s)")
        recommendations.append("Elevated wind speed. Fly with caution and maintain visual contact.")

    # 3.8 Weak signal (not critical)
    if (
        data.signal_strength is not None
        and Thresholds.SIGNAL_CRIT < data.signal_strength <= Thresholds.SIGNAL_WEAK
    ):
        triggered_l3.append(f"SIGNAL_WEAK ({data.signal_strength}%)")
        recommendations.append("Signal strength is weak. Stay within closer range.")

    # 3.9 Elevated vibration (not spike)
    if data.vibration_x is not None:
        import math
        magnitude = math.sqrt(
            (data.vibration_x or 0) ** 2 +
            (data.vibration_y or 0) ** 2 +
            (data.vibration_z or 0) ** 2
        )
        if Thresholds.VIBRATION_HIGH < magnitude <= Thresholds.VIBRATION_SPIKE:
            triggered_l3.append(f"VIBRATION_HIGH ({magnitude:.1f} m/s²)")
            recommendations.append("Elevated vibration. Monitor drone stability during flight.")

    # 3.10 Yellow Zone
    if data.zone == "YELLOW":
        triggered_l3.append("YELLOW_ZONE")
        recommendations.append("Location is in a YELLOW caution zone. Ensure you have proper authorisation.")

    # ── Compute Risk Index ────────────────────────────────────────────────────

    if triggered_l1:
        risk_index = 100.0
    else:
        raw = (
            len(triggered_l2) * L2_PENALTY +
            len(triggered_l3) * L3_PENALTY
        )
        # Base score of 5 (no sensor is perfectly zero-risk)
        risk_index = min(100.0, 5.0 + float(raw))

    # ── Classification ────────────────────────────────────────────────────────

    if risk_index <= SAFE_MAX and not triggered_l1 and not triggered_l2:
        classification = "Safe to Fly"
    elif risk_index <= CAUTION_MAX and not triggered_l1:
        classification = "Fly with Caution"
    else:
        classification = "Not Safe to Fly"

    if not recommendations:
        recommendations.append("All parameters nominal. Safe to proceed.")

    return {
        "risk_index":      round(risk_index, 2),
        "classification":  classification,
        "triggered_l1":    triggered_l1,
        "triggered_l2":    triggered_l2,
        "triggered_l3":    triggered_l3,
        "recommendations": recommendations,
        "hard_lock":       bool(triggered_l1),
    }
