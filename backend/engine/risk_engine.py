"""
AeroGuard - Rule-Based Risk Engine  (Arduino sensor schema)
============================================================

Arduino sensors handled
───────────────────────
  IMU (MPU6050)    : accX/Y/Z (m/s²), gyroX/Y/Z (°/s)
  Environment      : temperature (°C), humidity (%), pressure (hPa)
  Ultrasonic       : distance (cm)
  Light            : ldr (0-1023, 0=dark)
  Water / Rain     : water (0-1023, 0=dry)
  Current          : current_a (Amperes)
  IR obstacle      : ir  (0=clear, 1=obstacle)
  PIR motion       : pir (0=none,  1=motion)
  GPS              : latitude, longitude, satellites, hdop

Priority Levels
───────────────
  L1 – UNSAFE override  : risk_index = 100, relay LOCKED
  L2 – CAUTION          : significant penalty
  L3 – MODERATE         : moderate penalty

Tilt formula
────────────
  tilt_angle = degrees( atan2( sqrt(accX²+accY²), |accZ| ) )
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Optional


# ── Thresholds ────────────────────────────────────────────────────────────────

class T:
    # Environmental
    TEMP_HIGH         = 45.0      # °C
    TEMP_LOW          = -5.0      # °C
    HUMIDITY_HIGH     = 90.0      # %
    PRESSURE_MIN      = 950.0     # hPa – unusually low
    PRESSURE_MAX      = 1050.0    # hPa – unusually high

    # IMU
    TILT_UNSAFE       = 10.0      # degrees → L1  (was 15)
    TILT_CAUTION      = 7.0       # degrees → L2  (was 12)
    GYRO_RMS_UNSAFE   = 250.0     # °/s RMS → L1
    GYRO_RMS_CAUTION  = 80.0      # °/s RMS → L2

    # Ultrasonic  (distance <= 0 / -1 is INVALID – never triggers risk)
    DIST_UNSAFE       = 6.0       # cm  → L1 (was 10)
    DIST_CAUTION      = 15.0      # cm  → L2 (was 30)

    # Light (LDR, analog 0-1023)
    LDR_BRIGHT        = 3000      # > this → overexposure L2 (was LDR_DARK < 80)

    # Water (analog 0-1023, 0=dry, 1023=submerged)
    WATER_WET         = 120       # > this → wet (L2)  (was 100)
    WATER_UNSAFE      = 300       # > this → L1         (was 500)

    # Electrical
    CURRENT_UNSAFE    = 5.0       # |A| → L1 overcurrent
    CURRENT_HIGH      = 3.0       # |A| → L2 high draw  (was 3.5)

    # GPS
    SAT_MIN           = 3         # > 0 and < SAT_MIN → L2 (sat==0 = cold start, NOT penalised)
    HDOP_BAD          = 5.0       # sat>=3 AND hdop>5 → L1; hdop alone → L2
    HDOP_CAUTION      = 2.0       # → L3

    # Legacy battery / signal
    BATTERY_CRIT      = 10.0      # % → L1
    BATTERY_LOW       = 20.0      # % → L2
    SIGNAL_CRIT       = 10        # % → L1
    SIGNAL_WEAK       = 30        # % → L2


# ── Penalties ─────────────────────────────────────────────────────────────────
L1_PENALTY = 100   # instant UNSAFE
L2_PENALTY = 25
L3_PENALTY = 10

# ── Classification bands ──────────────────────────────────────────────────────
SAFE_MAX    = 30
CAUTION_MAX = 60


# ── Input dataclass ───────────────────────────────────────────────────────────

@dataclass
class SensorData:
    # Environmental
    temperature:     Optional[float] = None
    humidity:        Optional[float] = None
    pressure:        Optional[float] = None

    # Legacy rain detection (bool)
    rain_detected:   Optional[bool]  = None

    # GPS
    latitude:        Optional[float] = None
    longitude:       Optional[float] = None
    altitude:        Optional[float] = None
    satellites:      Optional[int]   = None
    hdop:            Optional[float] = None

    # IMU (MPU6050)
    acc_x:           Optional[float] = None
    acc_y:           Optional[float] = None
    acc_z:           Optional[float] = None
    gyro_x:          Optional[float] = None
    gyro_y:          Optional[float] = None
    gyro_z:          Optional[float] = None

    # Arduino sensors
    distance:        Optional[float] = None   # cm
    ldr:             Optional[int]   = None   # 0-1023
    water:           Optional[int]   = None   # 0-1023
    current_a:       Optional[float] = None   # Amperes
    ir:              Optional[int]   = None   # 0/1
    pir:             Optional[int]   = None   # 0/1

    # Legacy drone telemetry
    battery_pct:     Optional[float] = None
    voltage:         Optional[float] = None
    signal_strength: Optional[int]   = None
    charging_current:Optional[float] = None

    # Pre-computed zone
    zone:            Optional[str]   = None   # 'GREEN'|'YELLOW'|'RED'

    # Sensor health flag
    sensor_failure:  bool = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tilt_angle(acc_x, acc_y, acc_z) -> float:
    """
    Compute tilt angle in degrees from accelerometer readings.
    Uses the angle between the gravity vector projection and the Z-axis.
    Returns 0-90° (0 = perfectly level).
    """
    try:
        xy_mag = math.sqrt((acc_x or 0) ** 2 + (acc_y or 0) ** 2)
        z_abs  = abs(acc_z or 1e-9)      # avoid division by zero
        return math.degrees(math.atan2(xy_mag, z_abs))
    except Exception:
        return 0.0


def _gyro_rms(gx, gy, gz) -> float:
    """RMS magnitude of gyroscope readings (°/s)."""
    try:
        return math.sqrt((gx or 0) ** 2 + (gy or 0) ** 2 + (gz or 0) ** 2)
    except Exception:
        return 0.0


# ── Main Risk Evaluator ───────────────────────────────────────────────────────

def evaluate_risk(data: SensorData, prev_charging_current: Optional[float] = None) -> dict:
    """
    Evaluate risk for the given sensor snapshot.

    Returns
    -------
    dict with keys:
        risk_index       float  0-100
        risk_level       str    'SAFE' | 'CAUTION' | 'UNSAFE'
        classification   str    human-readable (kept for UI compat)
        safety_score     float  0-100  (100 = perfectly safe)
        tilt_angle       float  degrees
        triggered_l1     list
        triggered_l2     list
        triggered_l3     list
        recommendations  list
        hard_lock        bool
    """
    triggered_l1: List[str] = []
    triggered_l2: List[str] = []
    triggered_l3: List[str] = []
    recommendations: List[str] = []

    # ── Pre-compute derived values ────────────────────────────────────────────
    # Use getattr so a missing tilt_angle field never raises AttributeError.
    # Falls back to inline acc-based atan2 formula when the attribute is absent.
    _tilt_raw = getattr(data, "tilt_angle", None)
    if _tilt_raw is None:
        ax = data.acc_x or 0
        az = data.acc_z or 0
        _tilt_raw = abs(math.degrees(math.atan2(ax, az))) if az != 0 else 0
    tilt = abs(_tilt_raw or 0)
    gyro = _gyro_rms(data.gyro_x, data.gyro_y, data.gyro_z)

    # ── Named sensor aliases (safe defaults; keeps conditions readable) ────────
    # IR is ACTIVE-LOW: ir==0 means obstacle present
    obstacleDetected = (data.ir == 0)
    # Ultrasonic: distance <= 0 or -1 is INVALID – must NEVER influence risk
    validDistance = (data.distance is not None and data.distance > 0)
    # Absolute current value (may be negative from firmware)
    current      = abs(data.current_a or 0)
    satellites   = data.satellites or 0
    hdop         = data.hdop or 0
    water        = data.water or 0
    ldr          = data.ldr or 0
    temperature  = data.temperature or 0
    pir          = data.pir or 0

    # ── L1 – Hard Override (UNSAFE) ───────────────────────────────────────────

    # 1.1 Red Airspace Zone
    if data.zone == "RED":
        triggered_l1.append("RED_ZONE")
        recommendations.append("Location is in a RED restricted zone. Flight prohibited.")

    # 1.2 Rain / water sensor
    if data.rain_detected is True:
        triggered_l1.append("RAIN_DETECTED")
        recommendations.append("Rain detected (legacy sensor). Do not fly – water ingress risk.")

    if (data.water or 0) > T.WATER_UNSAFE:
        triggered_l1.append(f"WATER_HIGH ({data.water})")
        recommendations.append(f"Water sensor reading {data.water} exceeds safety threshold. Abort launch.")

    # 1.3 Sensor failure flag
    if data.sensor_failure:
        triggered_l1.append("SENSOR_FAILURE")
        recommendations.append("Critical sensor failure. System cannot guarantee safe operation.")

    # 1.4 Tilt too extreme (drone not level)
    if tilt > T.TILT_UNSAFE:
        triggered_l1.append(f"TILT_EXTREME ({tilt:.1f}°)")
        recommendations.append(f"Tilt angle {tilt:.1f}° exceeds {T.TILT_UNSAFE}° safety limit.")

    # 1.5 Overcurrent – use abs() to handle negative current readings
    if current > T.CURRENT_UNSAFE:
        triggered_l1.append(f"OVERCURRENT ({data.current_a:.2f}A)")
        recommendations.append(f"Current |{data.current_a:.2f}|A exceeds {T.CURRENT_UNSAFE}A limit. Check power system.")

    # 1.6 Extreme vibration (gyro RMS)
    if gyro > T.GYRO_RMS_UNSAFE:
        triggered_l1.append(f"VIBRATION_EXTREME ({gyro:.0f}°/s)")
        recommendations.append(f"Extreme vibration detected ({gyro:.0f} °/s). Inspect motor mounts.")

    # 1.7 Collision imminent – ONLY when distance is valid (> 0) and < DIST_UNSAFE
    #     IR alone does NOT trigger L1; requires valid ultrasonic confirmation
    if validDistance and data.distance < T.DIST_UNSAFE:
        triggered_l1.append(f"COLLISION_IMMINENT ({data.distance:.1f}cm)")
        recommendations.append(f"Obstacle at {data.distance:.1f} cm. Abort – collision imminent.")

    # 1.8 GPS degraded while satellites are locked (cold-start / sat==0 does NOT penalise)
    if satellites >= T.SAT_MIN and hdop > T.HDOP_BAD:
        triggered_l1.append(f"GPS_DEGRADED (sats={satellites}, HDOP={hdop:.1f})")
        recommendations.append(f"GPS fix locked but accuracy is poor (HDOP {hdop:.1f}). Reposition to open sky.")

    # 1.9 Critical battery (legacy)
    if data.battery_pct is not None and data.battery_pct <= T.BATTERY_CRIT:
        triggered_l1.append(f"BATTERY_CRITICAL ({data.battery_pct:.0f}%)")
        recommendations.append("Battery critically low. Charge before flight.")

    # 1.10 Critical signal (legacy)
    if data.signal_strength is not None and data.signal_strength <= T.SIGNAL_CRIT:
        triggered_l1.append(f"SIGNAL_CRITICAL ({data.signal_strength}%)")
        recommendations.append("Control signal critically weak. Risk of lost link.")

    # ── L2 – High Risk (CAUTION) — only evaluated when L1 is clear ───────────
    if not triggered_l1:

        # 2.1 Elevated tilt (between caution and unsafe threshold)
        if T.TILT_CAUTION < tilt <= T.TILT_UNSAFE:
            triggered_l2.append(f"TILT_HIGH ({tilt:.1f}°)")
            recommendations.append(f"Tilt angle {tilt:.1f}° elevated. Ensure drone is on level ground.")

        # 2.2 Elevated current (abs value, handles negative firmware readings)
        if T.CURRENT_HIGH <= current <= T.CURRENT_UNSAFE:
            triggered_l2.append(f"CURRENT_HIGH ({data.current_a:.2f}A)")
            recommendations.append(f"High current draw |{data.current_a:.2f}|A. Monitor power system.")

        # 2.3 Obstacle proximity (ultrasonic) – ONLY for valid readings (> 0)
        if validDistance and data.distance < T.DIST_CAUTION:
            triggered_l2.append(f"OBSTACLE_CLOSE ({data.distance:.1f}cm)")
            recommendations.append(f"Object at {data.distance:.1f} cm. Maintain safe separation.")

        # 2.4 Low satellite count (> 0 guards against GPS cold-start)
        if 0 < satellites < T.SAT_MIN:
            triggered_l2.append(f"LOW_SATELLITES ({satellites})")
            recommendations.append(f"Only {satellites} satellite(s). Minimum {T.SAT_MIN} required for safe flight.")

        # 2.5 LDR overexposure (high brightness, glare risk)
        if ldr > T.LDR_BRIGHT:
            triggered_l2.append(f"LDR_OVEREXPOSURE (LDR={ldr})")
            recommendations.append(f"Ambient light very high (LDR={ldr}). Optical sensors may be impaired.")

        # 2.6 Wet dock (moderate water between WET and UNSAFE)
        if T.WATER_WET < (data.water or 0) <= T.WATER_UNSAFE:
            triggered_l2.append(f"WATER_DETECTED ({data.water})")
            recommendations.append(f"Moisture detected (water={data.water}). Inspect before launch.")

        # 2.7 PIR motion near dock
        if pir == 1:
            triggered_l2.append("PIR_MOTION")
            recommendations.append("Motion detected near dock. Verify area is clear before launch.")

        # 2.8 Elevated gyro vibration
        if T.GYRO_RMS_CAUTION < gyro <= T.GYRO_RMS_UNSAFE:
            triggered_l2.append(f"VIBRATION_HIGH ({gyro:.0f}°/s)")
            recommendations.append(f"Elevated vibration {gyro:.0f} °/s. Inspect frame and propellers.")

        # 2.9 Low battery (legacy)
        if data.battery_pct is not None and T.BATTERY_CRIT < data.battery_pct <= T.BATTERY_LOW:
            triggered_l2.append(f"BATTERY_LOW ({data.battery_pct:.0f}%)")
            recommendations.append("Battery below 20%. Plan short flight or recharge.")

        # 2.10 Weak signal (legacy)
        if data.signal_strength is not None and T.SIGNAL_CRIT < data.signal_strength <= T.SIGNAL_WEAK:
            triggered_l2.append(f"SIGNAL_WEAK ({data.signal_strength}%)")
            recommendations.append("Signal weak. Stay within closer range.")

    # ── L3 – Moderate Risk (informational) ───────────────────────────────────

    # 3.1 Temperature extremes
    if data.temperature is not None and data.temperature > T.TEMP_HIGH:
        triggered_l3.append(f"TEMP_HIGH ({data.temperature:.1f}°C)")
        recommendations.append("High temperature. Electronics may overheat.")
    if data.temperature is not None and data.temperature < T.TEMP_LOW:
        triggered_l3.append(f"TEMP_LOW ({data.temperature:.1f}°C)")
        recommendations.append("Temperature below freezing. Battery performance reduced.")

    # 3.2 High humidity
    if data.humidity is not None and data.humidity > T.HUMIDITY_HIGH:
        triggered_l3.append(f"HUMIDITY_HIGH ({data.humidity:.0f}%)")
        recommendations.append("High humidity. Condensation risk on electronics.")

    # 3.3 Pressure anomaly
    if data.pressure is not None and (data.pressure < T.PRESSURE_MIN or data.pressure > T.PRESSURE_MAX):
        triggered_l3.append(f"PRESSURE_ANOMALY ({data.pressure:.0f}hPa)")
        recommendations.append("Unusual atmospheric pressure. Verify altimeter calibration.")

    # 3.4 HDOP caution band (moderate GPS accuracy, no L1 triggered)
    if data.hdop is not None and T.HDOP_CAUTION < data.hdop <= T.HDOP_BAD:
        triggered_l3.append(f"HDOP_CAUTION ({data.hdop:.1f})")
        recommendations.append("GPS accuracy moderate. Avoid GPS-dependent flight modes.")

    # 3.5 Yellow zone
    if data.zone == "YELLOW":
        triggered_l3.append("YELLOW_ZONE")
        recommendations.append("In YELLOW caution zone. Verify authorisation before launch.")

    # ── Weighted Risk Index (sensor-driven, additive) ─────────────────────────
    risk_index = 0.0

    # Major level triggers
    if triggered_l1:
        risk_index += 35
    if triggered_l2:
        risk_index += 20

    # GPS accuracy – only penalise when a fix is actually locked
    if satellites >= 3 and hdop > 3.5:
        risk_index += 10

    # Environmental sensors
    if water > 200:
        risk_index += 15
    # Tilt – higher weight, lower threshold to catch front/back lean early
    if tilt > 5:
        risk_index += 20

    # Proximity – IR must be paired with a valid ultrasonic reading
    if obstacleDetected and validDistance:
        risk_index += 10

    # Minor sensor contributions
    if pir == 1:
        risk_index += 5     # motion near dock
    if ldr > 3000:
        risk_index += 5
    if temperature > 55:
        risk_index += 5

    risk_index = min(100.0, risk_index)

    # ── Classification ────────────────────────────────────────────────────────
    if risk_index >= 60:
        risk_level     = "UNSAFE"
        classification = "Not Safe to Fly"
    elif risk_index >= 30:
        risk_level     = "CAUTION"
        classification = "Fly with Caution"
    else:
        risk_level     = "SAFE"
        classification = "Safe to Fly"

    if not recommendations:
        recommendations.append("All parameters nominal. Safe to proceed with pre-flight checklist.")

    # Safety score is the inverse of risk (100 = perfectly safe)
    safety_score = round(100.0 - risk_index, 2)

    return {
        "risk_index":      round(risk_index, 2),
        "risk_level":      risk_level,                   # SAFE | CAUTION | UNSAFE
        "classification":  classification,               # human-readable (UI compat)
        "safety_score":    safety_score,                 # 0-100, higher = safer
        "tilt_angle":      round(tilt, 2),
        "gyro_rms":        round(gyro, 2),
        "triggered_l1":    triggered_l1,
        "triggered_l2":    triggered_l2,
        "triggered_l3":    triggered_l3,
        "recommendations": recommendations,
        "hard_lock":       bool(triggered_l1),
    }
