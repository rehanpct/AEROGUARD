"""
AeroGuard - /api/logs
Endpoints for retrieving event logs, flight history, and risk score history.
"""

from flask import Blueprint, request, jsonify
from database import get_db
import json

logs_bp = Blueprint("logs", __name__)


# ── Event Logs ────────────────────────────────────────────────────────────────

@logs_bp.route("/logs/events", methods=["GET"])
def get_events():
    """
    Returns paginated event log.

    Query params:
        limit    : int  (default 100, max 500)
        offset   : int  (default 0)
        severity : str  filter by INFO | WARNING | CRITICAL
        type     : str  filter by event_type (LOCK, CAUTION, CLEAR, SENSOR_FAIL …)
    """
    limit    = min(int(request.args.get("limit",  100)), 500)
    offset   = int(request.args.get("offset", 0))
    severity = request.args.get("severity")
    etype    = request.args.get("type")

    conn = get_db()
    try:
        where_clauses = []
        params: list = []

        if severity:
            where_clauses.append("severity = ?")
            params.append(severity.upper())
        if etype:
            where_clauses.append("event_type = ?")
            params.append(etype.upper())

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        rows = conn.execute(f"""
            SELECT * FROM events
            {where_sql}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
        """, params + [limit, offset]).fetchall()

        total = conn.execute(f"SELECT COUNT(*) FROM events {where_sql}", params).fetchone()[0]

        return jsonify({
            "total":   total,
            "limit":   limit,
            "offset":  offset,
            "events":  [dict(r) for r in rows],
        }), 200

    finally:
        conn.close()


# ── Risk Score History ────────────────────────────────────────────────────────

@logs_bp.route("/logs/risk", methods=["GET"])
def get_risk_history():
    """
    Returns time-series risk scores for chart visualisation.

    Query params:
        limit  : int (default 200, max 1000)
        offset : int (default 0)
        hours  : float – only return records from the last N hours (e.g. 24)
    """
    limit  = min(int(request.args.get("limit",  200)), 1000)
    offset = int(request.args.get("offset", 0))
    hours  = request.args.get("hours")

    conn = get_db()
    try:
        where_sql = ""
        params: list = []
        if hours:
            where_sql = "WHERE timestamp >= datetime('now', ?)"
            params.append(f"-{float(hours)} hours")

        rows = conn.execute(f"""
            SELECT id, timestamp, risk_index, classification,
                   level1_triggered, level2_triggered, level3_triggered
            FROM risk_scores
            {where_sql}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
        """, params + [limit, offset]).fetchall()

        records = []
        for row in rows:
            d = dict(row)
            for key in ("level1_triggered", "level2_triggered", "level3_triggered"):
                if d.get(key):
                    d[key] = json.loads(d[key])
                else:
                    d[key] = []
            records.append(d)

        total = conn.execute(f"SELECT COUNT(*) FROM risk_scores {where_sql}", params).fetchone()[0]

        return jsonify({
            "total":   total,
            "limit":   limit,
            "offset":  offset,
            "records": records,
        }), 200

    finally:
        conn.close()


# ── Flight Logs ───────────────────────────────────────────────────────────────

@logs_bp.route("/logs/flights", methods=["GET"])
def get_flights():
    """Return all logged flight sessions."""
    limit  = min(int(request.args.get("limit",  50)), 500)
    offset = int(request.args.get("offset", 0))

    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT * FROM flight_logs ORDER BY id DESC LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()

        total = conn.execute("SELECT COUNT(*) FROM flight_logs").fetchone()[0]

        return jsonify({
            "total":   total,
            "limit":   limit,
            "offset":  offset,
            "flights": [dict(r) for r in rows],
        }), 200

    finally:
        conn.close()


@logs_bp.route("/logs/flights", methods=["POST"])
def create_flight():
    """
    Log the start of a new flight session.

    JSON body:
        flight_start (str)  : ISO datetime, defaults to now
        notes        (str)  : optional
    """
    payload = request.get_json(force=True, silent=True) or {}

    conn = get_db()
    try:
        cursor = conn.execute("""
            INSERT INTO flight_logs (flight_start, notes)
            VALUES (COALESCE(?, datetime('now')), ?)
        """, (payload.get("flight_start"), payload.get("notes")))
        conn.commit()
        return jsonify({"flight_id": cursor.lastrowid, "status": "created"}), 201
    finally:
        conn.close()


@logs_bp.route("/logs/flights/<int:flight_id>", methods=["PATCH"])
def close_flight(flight_id: int):
    """
    Close a flight session (log end time and final risk/zone).

    JSON body:
        flight_end     (str)
        max_risk_index (float)
        classification (str)
        zone           (str)
        notes          (str)
    """
    payload = request.get_json(force=True, silent=True) or {}

    conn = get_db()
    try:
        conn.execute("""
            UPDATE flight_logs SET
                flight_end     = COALESCE(?, datetime('now')),
                max_risk_index = ?,
                classification = ?,
                zone           = ?,
                notes          = COALESCE(?, notes)
            WHERE id = ?
        """, (
            payload.get("flight_end"),
            payload.get("max_risk_index"),
            payload.get("classification"),
            payload.get("zone"),
            payload.get("notes"),
            flight_id,
        ))
        if conn.execute("SELECT changes()").fetchone()[0] == 0:
            return jsonify({"error": "Flight not found"}), 404
        conn.commit()
        return jsonify({"flight_id": flight_id, "status": "closed"}), 200
    finally:
        conn.close()


# ── Failure Statistics ────────────────────────────────────────────────────────

@logs_bp.route("/logs/failures", methods=["GET"])
def get_failure_stats():
    """
    Returns failure event counts per day for the last 30 days.
    Useful for the analytics graph on the dashboard.
    """
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT DATE(timestamp) as day, severity, COUNT(*) as cnt
            FROM events
            WHERE timestamp >= datetime('now', '-30 days')
              AND severity IN ('WARNING', 'CRITICAL')
            GROUP BY day, severity
            ORDER BY day ASC
        """).fetchall()

        return jsonify({"failure_stats": [dict(r) for r in rows]}), 200

    finally:
        conn.close()
