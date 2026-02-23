"""
AeroGuard - Database Initialization
Uses SQLite via built-in sqlite3 (no ORM).
Supports backward-compatible migration for new Arduino sensor fields.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "aeroguard.db")


def get_db():
    """Return a new database connection with row_factory set."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _add_column_if_missing(cursor, table: str, column: str, col_type: str):
    """Silently add a column to a table if it doesn't already exist."""
    try:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
    except sqlite3.OperationalError:
        pass  # column already exists


def init_db():
    """Create all tables and migrate schema if they already exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    c = conn.cursor()

    # ── Sensor / Telemetry History ────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS sensor_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT    NOT NULL DEFAULT (datetime('now')),

            -- Environmental
            temperature     REAL,
            humidity        REAL,
            pressure        REAL,
            ambient_light   REAL,       -- legacy (kept for old rows)
            wind_speed      REAL,       -- legacy
            rain_detected   INTEGER,    -- legacy bool

            -- GPS
            latitude        REAL,
            longitude       REAL,
            altitude        REAL,
            satellites      INTEGER,
            hdop            REAL,
            location_name   TEXT,
            using_fallback_gps INTEGER DEFAULT 0,

            -- Drone Telemetry (legacy / manual readings)
            battery_pct     REAL,
            voltage         REAL,
            signal_strength INTEGER,

            -- Arduino IMU (MPU6050)
            acc_x           REAL,
            acc_y           REAL,
            acc_z           REAL,
            gyro_x          REAL,
            gyro_y          REAL,
            gyro_z          REAL,
            tilt_angle      REAL,

            -- Arduino sensors
            distance        REAL,       -- ultrasonic (cm)
            ldr             INTEGER,    -- light-dependent resistor
            water           INTEGER,    -- water/rain sensor (0-1023)
            current_a       REAL,       -- current sensor (Amperes)
            ir              INTEGER,    -- IR obstacle sensor (0/1)
            pir             INTEGER,    -- PIR motion sensor (0/1)

            -- Legacy vibration columns (kept for backward compat)
            vibration_x     REAL,
            vibration_y     REAL,
            vibration_z     REAL,
            charging_current REAL,

            -- Computed
            zone            TEXT        -- 'GREEN' | 'YELLOW' | 'RED'
        )
    """)

    # ── Migrate: add columns that may not exist in older databases ────────────
    NEW_COLS = [
        ("acc_x",              "REAL"),
        ("acc_y",              "REAL"),
        ("acc_z",              "REAL"),
        ("gyro_x",             "REAL"),
        ("gyro_y",             "REAL"),
        ("gyro_z",             "REAL"),
        ("tilt_angle",         "REAL"),
        ("distance",           "REAL"),
        ("ldr",                "INTEGER"),
        ("water",              "INTEGER"),
        ("current_a",          "REAL"),
        ("ir",                 "INTEGER"),
        ("pir",                "INTEGER"),
        ("location_name",      "TEXT"),
        ("using_fallback_gps", "INTEGER DEFAULT 0"),
    ]
    for col, col_type in NEW_COLS:
        _add_column_if_missing(c, "sensor_history", col, col_type)

    # ── Risk Score History ────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS risk_scores (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT    NOT NULL DEFAULT (datetime('now')),
            risk_index      REAL    NOT NULL,
            risk_level      TEXT    NOT NULL DEFAULT 'SAFE',   -- SAFE|CAUTION|UNSAFE
            classification  TEXT    NOT NULL,
            safety_score    REAL,                              -- 0-100, higher = safer
            level1_triggered TEXT,
            level2_triggered TEXT,
            level3_triggered TEXT,
            sensor_id       INTEGER REFERENCES sensor_history(id)
        )
    """)
    _add_column_if_missing(c, "risk_scores", "risk_level",   "TEXT NOT NULL DEFAULT 'SAFE'")
    _add_column_if_missing(c, "risk_scores", "safety_score", "REAL")

    # ── Event Log ─────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL DEFAULT (datetime('now')),
            event_type  TEXT    NOT NULL,
            severity    TEXT    NOT NULL,
            description TEXT,
            sensor_id   INTEGER REFERENCES sensor_history(id)
        )
    """)

    # ── Flight History ────────────────────────────────────────────────────────
    c.execute("""
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

    # ── Performance Indexes ───────────────────────────────────────────────────────
    # Speeds up ORDER BY id DESC LIMIT 1 queries (used on every /api/status poll)
    c.execute("CREATE INDEX IF NOT EXISTS idx_sensor_history_id ON sensor_history(id DESC)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_risk_scores_id    ON risk_scores(id DESC)")
    # Speeds up WHERE timestamp >= ... range queries (used by /api/status/summary and /api/logs/risk)
    c.execute("CREATE INDEX IF NOT EXISTS idx_risk_scores_ts    ON risk_scores(timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sensor_history_ts ON sensor_history(timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_ts         ON events(timestamp)")

    conn.commit()
    conn.close()
    print(f"[AeroGuard] Database ready: {DB_PATH}")
