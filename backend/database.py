"""
AeroGuard - Database Initialization
Uses SQLite via the built-in sqlite3 module (no ORM dependency needed).
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "aeroguard.db")


def get_db():
    """Return a new database connection with row_factory set."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db():
    """Create all tables if they don't already exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    cursor = conn.cursor()

    # ── Sensor / Telemetry History ────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sensor_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT    NOT NULL DEFAULT (datetime('now')),

            -- Environmental
            temperature     REAL,
            humidity        REAL,
            pressure        REAL,
            ambient_light   REAL,
            wind_speed      REAL,
            rain_detected   INTEGER,        -- 0 = dry, 1 = rain

            -- GPS
            latitude        REAL,
            longitude       REAL,
            altitude        REAL,
            satellites      INTEGER,
            hdop            REAL,

            -- Drone Telemetry
            battery_pct     REAL,
            voltage         REAL,
            signal_strength INTEGER,
            vibration_x     REAL,
            vibration_y     REAL,
            vibration_z     REAL,
            charging_current REAL,

            -- Computed zone
            zone            TEXT            -- 'GREEN' | 'YELLOW' | 'RED'
        )
    """)

    # ── Risk Score History ────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS risk_scores (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT    NOT NULL DEFAULT (datetime('now')),
            risk_index      REAL    NOT NULL,           -- 0-100
            classification  TEXT    NOT NULL,           -- Safe / Caution / Unsafe
            level1_triggered TEXT,                      -- JSON list of triggered L1 rules
            level2_triggered TEXT,
            level3_triggered TEXT,
            sensor_id       INTEGER REFERENCES sensor_history(id)
        )
    """)

    # ── Event Log ─────────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL DEFAULT (datetime('now')),
            event_type  TEXT    NOT NULL,   -- e.g. LOCK, CAUTION, CLEAR, SENSOR_FAIL
            severity    TEXT    NOT NULL,   -- INFO | WARNING | CRITICAL
            description TEXT,
            sensor_id   INTEGER REFERENCES sensor_history(id)
        )
    """)

    # ── Flight History ────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS flight_logs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            flight_start    TEXT,
            flight_end      TEXT,
            max_risk_index  REAL,
            classification  TEXT,
            zone            TEXT,
            notes           TEXT
        )
    """)

    conn.commit()
    conn.close()
    print(f"[AeroGuard] Database ready at {DB_PATH}")
