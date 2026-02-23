/**
 * AeroGuard – System Context
 * Polls the Flask backend every 2 s and exposes live state to all pages.
 * Falls back to synthetic simulation when backend is offline so the UI
 * never goes blank.
 */
import React, {
  createContext, useContext, useState, useEffect, useRef, useCallback,
} from "react";

// ─── Backend config ──────────────────────────────────────────────────────────
const BACKEND_URL = "http://localhost:5000/api";
const POLL_MS = 3000;   // 3 s — hardware sensors don't update faster than this

// ─── GPS Fallback ─────────────────────────────────────────────────────────────
const FALLBACK_LAT = 10.8505;
const FALLBACK_LON = 76.2711;
const FALLBACK_NAME = "Kerala Demo Location";

// ─── Context ──────────────────────────────────────────────────────────────────
const SystemContext = createContext(null);
export const useSystem = () => useContext(SystemContext);

// ─── Simulation helpers (used when backend offline) ──────────────────────────
const rand = (min, max, dec = 1) =>
  parseFloat((Math.random() * (max - min) + min).toFixed(dec));
const randInt = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;

function buildSimState(prev, failsafe) {
  const base = {
    // Risk
    risk_index: failsafe ? 100 : rand(5, 35),
    risk_level: failsafe ? "UNSAFE" : "SAFE",
    classification: failsafe ? "Not Safe to Fly" : "Safe to Fly",
    safety_score: failsafe ? 0 : rand(70, 98),
    hard_lock: failsafe,
    rain_probability: failsafe ? 0.85 : rand(0.05, 0.25, 2),

    // Zone
    zone_status: failsafe ? "RED" : "GREEN",
    relay_action: failsafe ? "LOCK" : "ALLOW",
    timestamp: new Date().toISOString(),

    // GPS
    gps: {
      latitude: FALLBACK_LAT + rand(-0.001, 0.001, 5),
      longitude: FALLBACK_LON + rand(-0.001, 0.001, 5),
      altitude: rand(0, 10, 1),
      satellites: failsafe ? 0 : randInt(6, 12),
      hdop: rand(0.8, 1.5, 2),
      using_fallback: true,
      location_name: FALLBACK_NAME,
    },

    // Environment
    environment: {
      temperature: rand(22, 35, 1),
      humidity: rand(50, 80, 1),
      pressure: rand(1008, 1018, 1),
      ldr: failsafe ? randInt(0, 80) : randInt(300, 800),
      rain_detected: failsafe,
    },

    // All Arduino sensor readings
    sensors: {
      acc_x: rand(-0.5, 0.5, 2),
      acc_y: rand(-0.5, 0.5, 2),
      acc_z: rand(9.3, 10.2, 2),
      gyro_x: rand(-2, 2, 2),
      gyro_y: rand(-2, 2, 2),
      gyro_z: rand(-2, 2, 2),
      tilt_angle: failsafe ? rand(25, 45, 1) : rand(0, 8, 1),
      distance: failsafe ? rand(5, 12, 1) : rand(50, 300, 1),
      ldr: failsafe ? randInt(0, 80) : randInt(300, 800),
      ir: failsafe ? 1 : 0,
      pir: failsafe ? 1 : 0,
      water: failsafe ? randInt(500, 900) : randInt(0, 50),
      current_a: failsafe ? rand(5.5, 8.0, 2) : rand(0.5, 2.5, 2),
      charging_current: rand(0.5, 2.5, 2),
    },

    // Legacy drone
    drone: {
      battery_pct: rand(60, 95, 1),
      voltage: rand(11.5, 12.6, 2),
      signal_strength: randInt(60, 95),
      charging_current: rand(0.5, 2.5, 2),
    },

    // Triggered rules
    triggered_l1: failsafe
      ? ["WATER_HIGH (720)", "OVERCURRENT (6.10A)", "TILT_EXTREME (32.4°)"]
      : [],
    triggered_l2: failsafe ? [] : ["LOW_SATELLITES (2)"],
    triggered_l3: [],

    // ML Engine
    ml_decision: failsafe ? "Not Safe" : "Safe",
    ml_explanation: failsafe
      ? `UAV Safety Assessment — Decision: Not Safe (score: 85.0/100)\n\nRisk Factors:\n  ⚠ CRITICAL: Zone is RED (restricted) — flight is prohibited.\n  ⚠ CRITICAL: Sensor fault detected — system integrity compromised.\n  ⚠ CRITICAL: Vibration RMS=6.10 — severe mechanical abnormality.\n\nOperational Recommendation:\n  Do NOT launch. Resolve all critical issues before attempting flight.\n\nSummary: ML safety score 85.0/100 in zone RED (restricted).\nDecision 'Not Safe' based on critical fault(s).`
      : `UAV Safety Assessment — Decision: Safe (score: 18.0/100)\n\nRisk Factors:\n  ✓ No significant risk factors detected.\n\nOperational Recommendation:\n  Conditions are acceptable. Conduct normal pre-flight checklist and proceed.\n\nSummary: ML safety score 18.0/100 in zone GREEN (permitted).\nDecision 'Safe' based on nominal readings.`,
  };
  return base;
}

// ─── Transform backend response → context state ───────────────────────────────
function transformApiResponse(json) {
  return {
    risk_index: json.risk_index ?? 0,
    risk_level: json.risk_level ?? "SAFE",
    classification: json.classification ?? "Safe to Fly",
    safety_score: json.safety_score ?? 100,
    hard_lock: json.hard_lock ?? false,
    rain_probability: json.rain_probability ?? 0,
    zone_status: json.zone_status ?? "GREEN",
    relay_action: json.relay_action ?? "ALLOW",
    timestamp: json.timestamp ?? new Date().toISOString(),
    gps: json.gps ?? {
      latitude: FALLBACK_LAT, longitude: FALLBACK_LON,
      using_fallback: true, location_name: FALLBACK_NAME,
      satellites: 0, hdop: 0, altitude: 0,
    },
    environment: json.environment ?? {},
    sensors: json.sensors ?? {},
    drone: json.drone ?? {},
    triggered_l1: json.triggered_l1 ?? [],
    triggered_l2: json.triggered_l2 ?? [],
    triggered_l3: json.triggered_l3 ?? [],
    // ML Engine
    ml_explanation: json.ml_explanation ?? "",
    ml_decision: json.ml_decision ?? "Safe",
  };
}

// ─── Provider ─────────────────────────────────────────────────────────────────
export function SystemProvider({ children }) {
  const [state, setState] = useState(() => buildSimState(null, false));
  const [backendOnline, setBackendOnline] = useState(false);
  const [failsafeActive, setFailsafeActive] = useState(false);
  const [manualOverride, setManualOverride] = useState(false);

  // Historical series for charts (keep last 40 points)
  const [history, setHistory] = useState(() =>
    Array.from({ length: 20 }, (_, i) => ({
      t: i,
      risk: rand(5, 30),
      safe: rand(70, 95),
    }))
  );

  // Log ring buffer
  const [logs, setLogs] = useState([
    { id: 1, timestamp: new Date().toISOString(), severity: "INFO", message: "System initialised. Waiting for backend…" },
  ]);
  const logIdRef = useRef(2);

  const pushLog = useCallback((severity, message) => {
    setLogs(prev => [
      { id: logIdRef.current++, timestamp: new Date().toISOString(), severity, message },
      ...prev.slice(0, 199),
    ]);
  }, []);

  // ── Risk score history from backend ────────────────────────────────────────
  const fetchHistory = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/logs/risk?hours=1&limit=40`);
      const json = await res.json();
      if (Array.isArray(json.records) && json.records.length > 0) {
        const pts = json.records
          .slice().reverse()
          .map((r, i) => ({
            t: i,
            risk: r.risk_index ?? 0,
            safe: r.safety_score ?? (100 - (r.risk_index ?? 0)),
          }));
        setHistory(pts);
      }
    } catch (_) {/* keep existing */ }
  }, []);

  // ── Main poll loop ──────────────────────────────────────────────────────────
  useEffect(() => {
    let active = true;
    const pollingRef = { inFlight: false };  // single-flight guard

    const poll = async () => {
      if (pollingRef.inFlight) return;       // skip if previous fetch still running
      pollingRef.inFlight = true;
      try {
        const res = await fetch(`${BACKEND_URL}/status`, { signal: AbortSignal.timeout(3000) });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        if (!active) return;

        const transformed = transformApiResponse(json);

        // ── Skip state update if nothing meaningful changed ─────────────────────────
        // Avoids a React re-render and avoids spamming the history chart
        // when the backend is up but no new sensor data has arrived.
        setState(prev => {
          if (
            prev &&
            prev.risk_level === transformed.risk_level &&
            prev.risk_index === transformed.risk_index &&
            prev.safety_score === transformed.safety_score &&
            prev.timestamp === transformed.timestamp &&
            prev.ml_explanation === transformed.ml_explanation &&
            prev.ml_decision === transformed.ml_decision
          ) {
            return prev;  // bail out — same data, no re-render
          }
          return transformed;
        });
        setBackendOnline(true);

        // Auto-log significant events
        if (transformed.hard_lock && transformed.triggered_l1.length > 0) {
          pushLog("CRITICAL", `HARD LOCK: ${transformed.triggered_l1.join(" | ")}`);
        } else if (transformed.triggered_l2.length > 0) {
          pushLog("WARNING", `Caution: ${transformed.triggered_l2.join(" | ")}`);
        }

        // Update history
        setHistory(prev => {
          const next = [...prev, {
            t: (prev[prev.length - 1]?.t ?? 0) + 1,
            risk: transformed.risk_index,
            safe: transformed.safety_score,
          }];
          return next.slice(-40);
        });

      } catch (_) {
        if (!active) return;
        setBackendOnline(false);
        // Simulate while offline
        setState(prev => buildSimState(prev, failsafeActive));
      } finally {
        pollingRef.inFlight = false;         // release guard regardless of outcome
      }
    };

    poll();
    const id = setInterval(poll, POLL_MS);
    const hid = setInterval(fetchHistory, 10_000);

    return () => {
      active = false;
      clearInterval(id);
      clearInterval(hid);
    };
  }, [failsafeActive, fetchHistory, pushLog]);

  // ── Event log from backend ─────────────────────────────────────────────────
  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/logs/events?limit=100`);
        const json = await res.json();
        if (Array.isArray(json.events) && json.events.length > 0) {
          setLogs(json.events.map(e => ({
            id: e.id,
            timestamp: e.timestamp,
            severity: e.severity,
            message: e.description ?? e.event_type,
          })));
        }
      } catch (_) {/* keep sim logs */ }
    };
    fetchLogs();
    const id = setInterval(fetchLogs, 5000);
    return () => clearInterval(id);
  }, []);

  const ctx = {
    // Live state
    ...state,
    backendOnline,
    failsafeActive,
    manualOverride,

    // History for charts
    history,

    // Logs
    logs,
    pushLog,

    // Actions
    toggleFailsafe: () => setFailsafeActive(v => !v),
    toggleOverride: () => setManualOverride(v => !v),

    // Convenience aliases used by older components
    sensors: state.sensors ?? {},
    environment: state.environment ?? {},
    gps: state.gps ?? {},
    drone: state.drone ?? {},
    riskIndex: state.risk_index ?? 0,
    riskLevel: state.risk_level ?? "SAFE",
    safetyScore: state.safety_score ?? 100,
    rainProbability: state.rain_probability ?? 0,
    zoneStatus: state.zone_status ?? "GREEN",
    relayAction: state.relay_action ?? "ALLOW",

    // ML Engine
    ml_explanation: state.ml_explanation ?? "",
    ml_decision: state.ml_decision ?? "Safe",
  };

  return (
    <SystemContext.Provider value={ctx}>
      {children}
    </SystemContext.Provider>
  );
}

export default SystemContext;
