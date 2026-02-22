"""
AeroGuard - /api/status
GET : Returns the current system status based on the latest telemetry reading.
      This is the primary endpoint polled by the dashboard.
"""

from flask import Blueprint, jsonify, request
from database import get_db
import json

status_bp = Blueprint("status", __name__)


@status_bp.route("/status", methods=["GET"])
def get_status():
    """
    Returns a summarised current-status object containing:
      - Latest sensor readings
      - Current risk index and classification
      - Zone information
      - Relay / dock state
      - Trend direction compared to the previous reading
    """
    conn = get_db()
    try:
        # ── Latest record ─────────────────────────────────────────────────────
        latest = conn.execute("""
            SELECT s.*, r.risk_index, r.classification,
                   r.level1_triggered, r.level2_triggered, r.level3_triggered
            FROM sensor_history s
            LEFT JOIN risk_scores r ON r.sensor_id = s.id
            ORDER BY s.id DESC LIMIT 1
        """).fetchone()

        if not latest:
            return jsonify({
                "status":         "NO_DATA",
                "message":        "No telemetry received yet.",
                "risk_index":     None,
                "classification": None,
            }), 200

        current = dict(latest)
        for key in ("level1_triggered", "level2_triggered", "level3_triggered"):
            if current.get(key):
                current[key] = json.loads(current[key])
            else:
                current[key] = []

        # ── Previous record (for trend) ───────────────────────────────────────
        prev = conn.execute("""
            SELECT r.risk_index
            FROM sensor_history s
            LEFT JOIN risk_scores r ON r.sensor_id = s.id
            ORDER BY s.id DESC LIMIT 1 OFFSET 1
        """).fetchone()

        risk_now  = current.get("risk_index")
        risk_prev = float(prev["risk_index"]) if prev and prev["risk_index"] is not None else None

        if risk_prev is None or risk_now is None:
            trend = "STABLE"
        elif risk_now > risk_prev + 2:
            trend = "INCREASING"
        elif risk_now < risk_prev - 2:
            trend = "DECREASING"
        else:
            trend = "STABLE"

        # ── Relay / dock state ────────────────────────────────────────────────
        hard_lock = bool(current.get("level1_triggered"))
        relay_state = "LOCKED" if hard_lock else "ARMED"

        # ── Aggregate failure count from events ───────────────────────────────
        failures_today = conn.execute("""
            SELECT COUNT(*) FROM events
            WHERE severity='CRITICAL'
              AND DATE(timestamp) = DATE('now')
        """).fetchone()[0]

        return jsonify({
            "status":           "OK",
            "timestamp":        current.get("timestamp"),
            "sensor_id":        current.get("id"),

            # Risk
            "risk_index":       current.get("risk_index"),
            "classification":   current.get("classification"),
            "trend":            trend,
            "hard_lock":        hard_lock,
            "relay_state":      relay_state,

            # Zone
            "zone":             current.get("zone"),

            # Environmental snapshot
            "environment": {
                "temperature":   current.get("temperature"),
                "humidity":      current.get("humidity"),
                "pressure":      current.get("pressure"),
                "wind_speed":    current.get("wind_speed"),
                "rain_detected": bool(current.get("rain_detected")),
                "ambient_light": current.get("ambient_light"),
            },

            # GPS snapshot
            "gps": {
                "latitude":   current.get("latitude"),
                "longitude":  current.get("longitude"),
                "altitude":   current.get("altitude"),
                "satellites": current.get("satellites"),
                "hdop":       current.get("hdop"),
            },

            # Drone health snapshot
            "drone": {
                "battery_pct":      current.get("battery_pct"),
                "voltage":          current.get("voltage"),
                "signal_strength":  current.get("signal_strength"),
                "charging_current": current.get("charging_current"),
            },

            # Triggered rules
            "triggered_rules": {
                "level1": current.get("level1_triggered", []),
                "level2": current.get("level2_triggered", []),
                "level3": current.get("level3_triggered", []),
            },

            # Stats
            "failures_today": failures_today,
        }), 200

    finally:
        conn.close()


@status_bp.route("/status/summary", methods=["GET"])
def get_summary():
    """
    Returns aggregate analytics for dashboard cards:
      - Total flights logged
      - Average risk index (last 24h)
      - Most common triggered rule
      - Zone distribution
    """
    conn = get_db()
    try:
        # Average risk last 24h
        avg_risk = conn.execute("""
            SELECT AVG(risk_index) FROM risk_scores
            WHERE timestamp >= datetime('now', '-1 day')
        """).fetchone()[0]

        # Total sensor records
        total_records = conn.execute("SELECT COUNT(*) FROM sensor_history").fetchone()[0]

        # Classification breakdown last 24h
        classifications = conn.execute("""
            SELECT classification, COUNT(*) as cnt
            FROM risk_scores
            WHERE timestamp >= datetime('now', '-1 day')
            GROUP BY classification
        """).fetchall()

        # Zone distribution
        zones = conn.execute("""
            SELECT zone, COUNT(*) as cnt FROM sensor_history
            WHERE timestamp >= datetime('now', '-1 day')
              AND zone IS NOT NULL
            GROUP BY zone
        """).fetchall()

        # Event counts
        events = conn.execute("""
            SELECT event_type, COUNT(*) as cnt FROM events
            WHERE timestamp >= datetime('now', '-1 day')
            GROUP BY event_type
        """).fetchall()

        return jsonify({
            "avg_risk_24h":        round(avg_risk, 2) if avg_risk else None,
            "total_sensor_records": total_records,
            "classification_breakdown": {r["classification"]: r["cnt"] for r in classifications},
            "zone_distribution":   {r["zone"]: r["cnt"] for r in zones},
            "event_counts":        {r["event_type"]: r["cnt"] for r in events},
        }), 200

    finally:
        conn.close()
