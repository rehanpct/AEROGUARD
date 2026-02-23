import React from "react";
import { motion } from "framer-motion";
import {
    AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";
import { useSystem } from "../context/SystemContext";

// ─── Tiny helpers ─────────────────────────────────────────────────────────────
const clampColor = (v, warn, danger, invert = false) => {
    if (invert) {
        if (v < danger) return "#ef4444";
        if (v < warn) return "#facc15";
        return "#22c55e";
    }
    if (v > danger) return "#ef4444";
    if (v > warn) return "#facc15";
    return "#22c55e";
};

const fmt = (v, dec = 1, unit = "") =>
    v == null ? "—" : `${Number(v).toFixed(dec)}${unit}`;

// ─── Card shell ───────────────────────────────────────────────────────────────
function Card({ title, accent, children, style = {} }) {
    return (
        <div className="card" style={{ padding: 18, borderTop: `3px solid ${accent ?? "#3B82F6"}`, ...style }}>
            <p style={{
                margin: "0 0 14px", fontSize: 11, fontWeight: 700, letterSpacing: 1.2,
                textTransform: "uppercase", color: "#64748b"
            }}>
                {title}
            </p>
            {children}
        </div>
    );
}

// Small metric row inside a card
function Row({ label, value, color }) {
    return (
        <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            padding: "5px 0", borderBottom: "1px solid rgba(255,255,255,0.04)"
        }}>
            <span style={{ fontSize: 12, color: "#64748b" }}>{label}</span>
            <span style={{ fontSize: 13, fontWeight: 600, color: color ?? "#e2e8f0" }}>{value}</span>
        </div>
    );
}

// Circle badge for big risk number
function RiskCircle({ index, level }) {
    const color =
        level === "UNSAFE" ? "#ef4444" :
            level === "CAUTION" ? "#facc15" : "#22c55e";
    return (
        <div style={{ position: "relative", width: 120, height: 120, margin: "0 auto 12px" }}>
            <svg viewBox="0 0 36 36" style={{ width: "100%", height: "100%", transform: "rotate(-90deg)" }}>
                <circle cx={18} cy={18} r={15.9} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={3} />
                <circle cx={18} cy={18} r={15.9} fill="none"
                    stroke={color} strokeWidth={3}
                    strokeDasharray={`${index} ${100 - index}`}
                    strokeLinecap="round"
                    style={{ transition: "stroke-dasharray 1s ease, stroke 0.5s" }}
                />
            </svg>
            <div style={{
                position: "absolute", inset: 0, display: "flex", flexDirection: "column",
                alignItems: "center", justifyContent: "center"
            }}>
                <span style={{ fontSize: 26, fontWeight: 800, color, lineHeight: 1 }}>
                    {Math.round(index ?? 0)}
                </span>
                <span style={{ fontSize: 10, color: "#64748b", marginTop: 2 }}>RISK</span>
            </div>
        </div>
    );
}

// ─── Main Dashboard ───────────────────────────────────────────────────────────
// ─── ML Explanation line renderer ────────────────────────────────────────────
function ExplainLine({ text }) {
    let color = "#94a3b8";
    if (text.startsWith("  ⚠ CRITICAL:")) color = "#ef4444";
    else if (text.startsWith("  ⚡ CAUTION:")) color = "#facc15";
    else if (text.startsWith("  ✓")) color = "#22c55e";
    else if (text.startsWith("UAV Safety") || text.startsWith("Risk") ||
        text.startsWith("Operational") || text.startsWith("Summary")) {
        color = "#cbd5e1";
    }
    return (
        <div style={{
            fontFamily: "monospace", fontSize: 12, color, lineHeight: 1.7,
            whiteSpace: "pre-wrap"
        }}>{text || "\u00a0"}</div>
    );
}

export default function Dashboard() {
    const {
        risk_index, risk_level, safety_score, rain_probability,
        zone_status, relay_action, classification, hard_lock,
        environment, sensors, gps, drone,
        triggered_l1, triggered_l2, triggered_l3,
        history,
        backendOnline,
        ml_explanation, ml_decision,
    } = useSystem();

    const env = environment ?? {};
    const sen = sensors ?? {};
    const gpsD = gps ?? {};
    const droneD = drone ?? {};

    const ringColor =
        risk_level === "UNSAFE" ? "#ef4444" :
            risk_level === "CAUTION" ? "#facc15" : "#22c55e";

    return (
        <motion.div
            initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35 }}
        >
            {/* ── Top status bar ─────────────────────────────────────────────── */}
            <div style={{
                display: "flex", alignItems: "center", justifyContent: "space-between",
                flexWrap: "wrap", gap: 10, marginBottom: 20
            }}>
                <div>
                    <h2 style={{ margin: 0, color: "#e2e8f0", fontSize: 22, fontWeight: 700 }}>
                        Mission Dashboard
                    </h2>
                    <p style={{ margin: "3px 0 0", color: "#64748b", fontSize: 13 }}>
                        Real-time UAV ground safety monitoring
                    </p>
                </div>

                <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                    <div style={{
                        padding: "5px 14px", borderRadius: 20, fontSize: 12, fontWeight: 600,
                        background: backendOnline ? "rgba(34,197,94,0.1)" : "rgba(100,116,139,0.1)",
                        border: `1px solid ${backendOnline ? "#22c55e" : "#475569"}`,
                        color: backendOnline ? "#22c55e" : "#94a3b8",
                    }}>
                        {backendOnline ? "● Backend Live" : "○ Offline – Simulation"}
                    </div>

                    {gpsD.using_fallback && (
                        <div style={{
                            padding: "5px 14px", borderRadius: 20, fontSize: 12, fontWeight: 600,
                            background: "rgba(250,204,21,0.1)", border: "1px solid rgba(250,204,21,0.3)",
                            color: "#facc15",
                        }}>
                            ⚠ GPS Fallback: {gpsD.location_name}
                        </div>
                    )}

                    {/* Relay / Dock status */}
                    <motion.div
                        animate={{ scale: hard_lock ? [1, 1.05, 1] : 1 }}
                        transition={{ duration: 1, repeat: hard_lock ? Infinity : 0 }}
                        style={{
                            padding: "5px 14px", borderRadius: 20, fontSize: 12, fontWeight: 700,
                            background: hard_lock ? "rgba(239,68,68,0.15)" : "rgba(34,197,94,0.1)",
                            border: `1px solid ${hard_lock ? "#ef4444" : "#22c55e"}`,
                            color: hard_lock ? "#ef4444" : "#22c55e",
                        }}
                    >
                        {hard_lock ? "🔒 DOCK LOCKED" : "🔓 DOCK OPEN"}
                    </motion.div>
                </div>
            </div>

            {/* ── Hard-lock banner ────────────────────────────────────────────── */}
            {hard_lock && (
                <motion.div
                    initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                    style={{
                        background: "rgba(239,68,68,0.12)", border: "1px solid #ef4444",
                        borderRadius: 12, padding: "12px 18px", marginBottom: 18,
                        color: "#ef4444", fontSize: 13, fontWeight: 600,
                    }}
                >
                    🚨 HARD LOCK ACTIVE — {triggered_l1?.join(" · ")}
                </motion.div>
            )}

            {/* ── Main grid ───────────────────────────────────────────────────── */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>

                {/* ── 1. Risk Overview ─────────────────────────────────────────── */}
                <Card title="System Risk" accent={ringColor}>
                    <RiskCircle index={risk_index ?? 0} level={risk_level} />
                    <p style={{
                        textAlign: "center", margin: "0 0 12px", fontSize: 15,
                        fontWeight: 700, color: ringColor
                    }}>
                        {classification ?? "Safe to Fly"}
                    </p>
                    <Row label="Risk Level" value={risk_level ?? "SAFE"} color={ringColor} />
                    <Row label="Safety Score" value={fmt(safety_score, 1, "%")}
                        color={clampColor(safety_score ?? 100, 70, 40, true)} />
                    <Row label="Zone Status" value={zone_status ?? "GREEN"}
                        color={zone_status === "RED" ? "#ef4444" : zone_status === "YELLOW" ? "#facc15" : "#22c55e"} />
                    <Row label="Relay" value={relay_action ?? "ALLOW"}
                        color={relay_action === "LOCK" ? "#ef4444" : "#22c55e"} />
                    <Row label="Rain Prob." value={fmt((rain_probability ?? 0) * 100, 0, "%")}
                        color={clampColor(rain_probability ?? 0, 0.4, 0.7)} />
                </Card>

                {/* ── 2. Environment ───────────────────────────────────────────── */}
                <Card title="Environment" accent="#3B82F6">
                    <Row label="Temperature" value={fmt(env.temperature, 1, " °C")}
                        color={clampColor(env.temperature ?? 25, 38, 45)} />
                    <Row label="Humidity" value={fmt(env.humidity, 1, " %")}
                        color={clampColor(env.humidity ?? 55, 80, 90)} />
                    <Row label="Pressure" value={fmt(env.pressure, 1, " hPa")} />
                    <Row label="Light (LDR)" value={env.ldr ?? sen.ldr ?? "—"}
                        color={clampColor(env.ldr ?? 512, 80, 40, true)} />
                    <Row label="Rain Sensor" value={env.rain_detected ? "⚠ Detected" : "Clear"}
                        color={env.rain_detected ? "#ef4444" : "#22c55e"} />
                </Card>

                {/* ── 3. GPS & Location ─────────────────────────────────────────── */}
                <Card title="GPS & Location" accent={gpsD.using_fallback ? "#facc15" : "#22c55e"}>
                    {gpsD.using_fallback && (
                        <div style={{
                            padding: "6px 10px", borderRadius: 8, marginBottom: 10,
                            background: "rgba(250,204,21,0.1)", border: "1px solid rgba(250,204,21,0.25)",
                            color: "#facc15", fontSize: 11
                        }}>
                            ⚠ No GPS Fix — Default location in use
                        </div>
                    )}
                    <Row label="Latitude" value={fmt(gpsD.latitude, 5, "°")} />
                    <Row label="Longitude" value={fmt(gpsD.longitude, 5, "°")} />
                    <Row label="Altitude" value={fmt(gpsD.altitude, 1, " m")} />
                    <Row label="Satellites" value={gpsD.satellites ?? 0}
                        color={clampColor(gpsD.satellites ?? 0, 3, 1, true)} />
                    <Row label="HDOP" value={fmt(gpsD.hdop, 2)} />
                    <Row label="Location" value={gpsD.location_name ?? "Unknown"} />
                </Card>

                {/* ── 4. IMU – Accelerometer & Tilt ─────────────────────────────── */}
                <Card title="IMU — Accelerometer / Tilt" accent="#8B5CF6">
                    <Row label="Acc X" value={fmt(sen.acc_x, 2, " m/s²")} />
                    <Row label="Acc Y" value={fmt(sen.acc_y, 2, " m/s²")} />
                    <Row label="Acc Z" value={fmt(sen.acc_z, 2, " m/s²")} />
                    <Row label="Tilt Angle" value={fmt(sen.tilt_angle, 1, "°")}
                        color={clampColor(sen.tilt_angle ?? 0, 15, 30)} />
                    <div style={{
                        marginTop: 10, background: "rgba(139,92,246,0.08)",
                        borderRadius: 8, padding: "8px 12px"
                    }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                            <span style={{ fontSize: 11, color: "#64748b" }}>Tilt</span>
                            <span style={{ fontSize: 11, color: clampColor(sen.tilt_angle ?? 0, 15, 30) }}>
                                {fmt(sen.tilt_angle, 1, "°")}
                            </span>
                        </div>
                        <div style={{ background: "rgba(255,255,255,0.06)", borderRadius: 4, height: 6 }}>
                            <div style={{
                                height: 6, borderRadius: 4,
                                width: `${Math.min(100, ((sen.tilt_angle ?? 0) / 90) * 100)}%`,
                                background: clampColor(sen.tilt_angle ?? 0, 15, 30),
                                transition: "width 0.5s ease",
                            }} />
                        </div>
                    </div>
                </Card>

                {/* ── 5. IMU – Gyroscope ─────────────────────────────────────────── */}
                <Card title="IMU — Gyroscope" accent="#06B6D4">
                    <Row label="Gyro X" value={fmt(sen.gyro_x, 2, " °/s")} />
                    <Row label="Gyro Y" value={fmt(sen.gyro_y, 2, " °/s")} />
                    <Row label="Gyro Z" value={fmt(sen.gyro_z, 2, " °/s")} />
                    {(() => {
                        const rms = Math.sqrt(
                            (sen.gyro_x ?? 0) ** 2 + (sen.gyro_y ?? 0) ** 2 + (sen.gyro_z ?? 0) ** 2
                        );
                        return (
                            <Row label="Vibration RMS" value={fmt(rms, 1, " °/s")}
                                color={clampColor(rms, 80, 250)} />
                        );
                    })()}
                </Card>

                {/* ── 6. Proximity & Obstacle ───────────────────────────────────── */}
                <Card title="Proximity & Obstacle Detection" accent="#F59E0B">
                    {(() => {
                        // IR: ACTIVE-LOW — ir===0 means obstacle detected
                        const irVal = sen.ir ?? 1;
                        const obstacleDetected = (irVal === 0);

                        // Ultrasonic: distance===-1 or <=0 is invalid / no echo
                        const rawDistance = sen.distance ?? -1;
                        const validDistance = rawDistance > 0;
                        const distanceText = validDistance
                            ? `${rawDistance.toFixed(1)} cm`
                            : "No Echo";
                        const distanceColor = validDistance
                            ? clampColor(rawDistance, 30, 10, true)
                            : "#64748b";
                        const barWidth = validDistance
                            ? Math.min(100, (rawDistance / 200) * 100)
                            : 0;

                        return (
                            <>
                                <Row label="Distance (Ultrasonic)" value={distanceText}
                                    color={distanceColor} />
                                <Row label="IR Obstacle" value={obstacleDetected ? "⚠ Detected" : "Clear"}
                                    color={obstacleDetected ? "#ef4444" : "#22c55e"} />
                                <Row label="PIR Motion" value={sen.pir === 1 ? "⚠ Motion" : "None"}
                                    color={sen.pir === 1 ? "#facc15" : "#22c55e"} />
                                {/* Visual distance bar */}
                                <div style={{
                                    marginTop: 10, background: "rgba(245,158,11,0.06)",
                                    borderRadius: 8, padding: "8px 12px"
                                }}>
                                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                                        <span style={{ fontSize: 11, color: "#64748b" }}>Clearance</span>
                                        <span style={{ fontSize: 11, color: distanceColor }}>
                                            {distanceText}
                                        </span>
                                    </div>
                                    <div style={{ background: "rgba(255,255,255,0.06)", borderRadius: 4, height: 6 }}>
                                        <div style={{
                                            height: 6, borderRadius: 4,
                                            width: `${barWidth}%`,
                                            background: distanceColor,
                                            transition: "width 0.5s ease",
                                        }} />
                                    </div>
                                </div>
                            </>
                        );
                    })()}
                </Card>

                {/* ── 7. Electrical – Current Draw ──────────────────────────────── */}
                <Card title="Electrical — Current Draw" accent={clampColor(sen.current_a ?? 0, 3.5, 5)}>
                    <Row label="Current" value={fmt(sen.current_a, 2, " A")}
                        color={clampColor(sen.current_a ?? 0, 3.5, 5)} />
                    <Row label="Voltage" value={fmt(droneD.voltage, 2, " V")} />
                    <Row label="Battery" value={fmt(droneD.battery_pct, 0, "%")}
                        color={clampColor(droneD.battery_pct ?? 100, 20, 10, true)} />
                    <Row label="Signal" value={fmt(droneD.signal_strength, 0, "%")}
                        color={clampColor(droneD.signal_strength ?? 100, 30, 10, true)} />
                    {(sen.current_a ?? 0) > 5 && (
                        <div style={{
                            marginTop: 8, padding: "6px 10px", borderRadius: 8,
                            background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)",
                            color: "#ef4444", fontSize: 11, fontWeight: 600
                        }}>
                            ⚡ OVERCURRENT — {fmt(sen.current_a, 2, " A")} exceeds 5 A limit
                        </div>
                    )}
                </Card>

                {/* ── 8. Water & Light ──────────────────────────────────────────── */}
                <Card title="Water Sensor & Ambient Light" accent="#0EA5E9">
                    <Row label="Water Level" value={sen.water ?? 0}
                        color={sen.water > 500 ? "#ef4444" : sen.water > 100 ? "#facc15" : "#22c55e"} />
                    <Row label="Water State"
                        value={sen.water > 500 ? "⚠ UNSAFE" : sen.water > 100 ? "⚠ Wet" : "✓ Dry"}
                        color={sen.water > 500 ? "#ef4444" : sen.water > 100 ? "#facc15" : "#22c55e"} />
                    <Row label="LDR Light" value={sen.ldr ?? 0}
                        color={(sen.ldr ?? 512) < 80 ? "#facc15" : "#22c55e"} />
                    <Row label="Light State"
                        value={(sen.ldr ?? 512) < 80 ? "⚠ Dark" : "✓ Adequate"}
                        color={(sen.ldr ?? 512) < 80 ? "#facc15" : "#22c55e"} />
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 10 }}>
                        {[
                            {
                                label: "Water", val: sen.water ?? 0, max: 1023,
                                color: sen.water > 500 ? "#ef4444" : sen.water > 100 ? "#facc15" : "#22c55e"
                            },
                            {
                                label: "Light", val: sen.ldr ?? 0, max: 1023,
                                color: (sen.ldr ?? 512) < 80 ? "#facc15" : "#22c55e"
                            },
                        ].map(({ label, val, max, color }) => (
                            <div key={label} style={{ background: "rgba(255,255,255,0.03)", borderRadius: 8, padding: "8px 10px" }}>
                                <div style={{ fontSize: 10, color: "#64748b", marginBottom: 4 }}>{label}</div>
                                <div style={{ background: "rgba(255,255,255,0.06)", borderRadius: 3, height: 5 }}>
                                    <div style={{
                                        height: 5, borderRadius: 3,
                                        width: `${(val / max) * 100}%`,
                                        background: color, transition: "width 0.5s ease",
                                    }} />
                                </div>
                                <div style={{ fontSize: 11, color, marginTop: 3, fontWeight: 600 }}>{val}</div>
                            </div>
                        ))}
                    </div>
                </Card>

                {/* ── 9. Risk Trend Chart ───────────────────────────────────────── */}
                <Card title="Risk Index Trend" accent="#3B82F6">
                    <ResponsiveContainer width="100%" height={130}>
                        <AreaChart data={history ?? []}>
                            <defs>
                                <linearGradient id="riskGrad" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.4} />
                                    <stop offset="95%" stopColor="#3B82F6" stopOpacity={0.02} />
                                </linearGradient>
                            </defs>
                            <XAxis dataKey="t" hide />
                            <YAxis domain={[0, 100]} hide />
                            <Tooltip
                                contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
                                formatter={v => [`${v.toFixed(1)}`, "Risk"]}
                                labelFormatter={() => ""}
                            />
                            <Area type="monotone" dataKey="risk" stroke="#3B82F6"
                                fill="url(#riskGrad)" strokeWidth={2} dot={false} />
                        </AreaChart>
                    </ResponsiveContainer>
                </Card>

                {/* ── 10. AI VSO Panel ─────────────────────────────────────────── */}
                <Card title="AI Virtual Safety Officer" accent="#8B5CF6" style={{ gridColumn: "1 / -1" }}>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
                        <div style={{ background: "rgba(139,92,246,0.07)", borderRadius: 10, padding: 12 }}>
                            <div style={{ fontSize: 11, color: "#64748b", marginBottom: 4 }}>Decision</div>
                            <div style={{ fontSize: 16, fontWeight: 700, color: ringColor }}>
                                {classification ?? "Safe to Fly"}
                            </div>
                        </div>
                        <div style={{ background: "rgba(139,92,246,0.07)", borderRadius: 10, padding: 12 }}>
                            <div style={{ fontSize: 11, color: "#64748b", marginBottom: 4 }}>Safety Score</div>
                            <div style={{ fontSize: 16, fontWeight: 700, color: clampColor(safety_score ?? 100, 70, 40, true) }}>
                                {fmt(safety_score, 1)}
                            </div>
                        </div>
                        <div style={{ background: "rgba(139,92,246,0.07)", borderRadius: 10, padding: 12 }}>
                            <div style={{ fontSize: 11, color: "#64748b", marginBottom: 4 }}>Rain Probability</div>
                            <div style={{ fontSize: 16, fontWeight: 700, color: clampColor(rain_probability ?? 0, 0.4, 0.7) }}>
                                {fmt((rain_probability ?? 0) * 100, 0, "%")}
                            </div>
                        </div>
                        <div style={{ background: "rgba(139,92,246,0.07)", borderRadius: 10, padding: 12 }}>
                            <div style={{ fontSize: 11, color: "#64748b", marginBottom: 4 }}>Active Triggers</div>
                            <div style={{ fontSize: 16, fontWeight: 700, color: triggered_l1?.length ? "#ef4444" : "#22c55e" }}>
                                L1: {triggered_l1?.length ?? 0} &nbsp;·&nbsp;
                                L2: {triggered_l2?.length ?? 0} &nbsp;·&nbsp;
                                L3: {triggered_l3?.length ?? 0}
                            </div>
                        </div>
                    </div>

                    {/* Triggered rule details */}
                    {((triggered_l1?.length ?? 0) + (triggered_l2?.length ?? 0)) > 0 && (
                        <div style={{ marginTop: 12, display: "flex", flexWrap: "wrap", gap: 6 }}>
                            {[...(triggered_l1 ?? [])].map(t => (
                                <span key={t} style={{
                                    padding: "3px 10px", borderRadius: 12, fontSize: 11,
                                    background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.3)",
                                    color: "#ef4444"
                                }}>{t}</span>
                            ))}
                            {[...(triggered_l2 ?? [])].map(t => (
                                <span key={t} style={{
                                    padding: "3px 10px", borderRadius: 12, fontSize: 11,
                                    background: "rgba(250,204,21,0.1)", border: "1px solid rgba(250,204,21,0.3)",
                                    color: "#facc15"
                                }}>{t}</span>
                            ))}
                        </div>
                    )}
                </Card>

                {/* ── 11. ML Engine Assessment ──────────────────────────────── */}
                <Card title="ML Engine Assessment" accent="#6366F1" style={{ gridColumn: "1 / -1" }}>
                    {/* Header row: ML decision badge + score */}
                    <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
                        <div style={{
                            padding: "4px 16px", borderRadius: 20, fontSize: 13, fontWeight: 700,
                            background:
                                ml_decision === "Not Safe" ? "rgba(239,68,68,0.15)" :
                                    ml_decision === "Caution" ? "rgba(250,204,21,0.12)" :
                                        "rgba(34,197,94,0.12)",
                            border: `1px solid ${ml_decision === "Not Safe" ? "rgba(239,68,68,0.5)" :
                                ml_decision === "Caution" ? "rgba(250,204,21,0.4)" :
                                    "rgba(34,197,94,0.4)"}`,
                            color:
                                ml_decision === "Not Safe" ? "#ef4444" :
                                    ml_decision === "Caution" ? "#facc15" : "#22c55e",
                        }}>
                            {ml_decision === "Not Safe" ? "🚫 Not Safe to Fly" :
                                ml_decision === "Caution" ? "⚠ Caution" : "✓ Safe to Fly"}
                        </div>
                        <div style={{ fontSize: 12, color: "#64748b" }}>
                            Combined Safety Score: <span style={{
                                fontWeight: 700,
                                color:
                                    ml_decision === "Not Safe" ? "#ef4444" :
                                        ml_decision === "Caution" ? "#facc15" : "#22c55e",
                            }}>{fmt(safety_score, 1)}/100</span>
                        </div>
                        <div style={{ fontSize: 12, color: "#64748b" }}>
                            Rain Probability: <span style={{
                                fontWeight: 700,
                                color: clampColor(rain_probability ?? 0, 0.4, 0.7),
                            }}>{fmt((rain_probability ?? 0) * 100, 0, "%")}</span>
                        </div>
                    </div>

                    {/* Explanation body */}
                    <div style={{
                        background: "rgba(99,102,241,0.05)",
                        border: "1px solid rgba(99,102,241,0.15)",
                        borderRadius: 10,
                        padding: "14px 16px",
                    }}>
                        {ml_explanation
                            ? ml_explanation.split("\n").map((line, i) =>
                                <ExplainLine key={i} text={line} />
                            )
                            : <div style={{ color: "#475569", fontSize: 13, fontStyle: "italic" }}>
                                Awaiting sensor data… ML assessment will appear here once data is received.
                            </div>
                        }
                    </div>
                </Card>

            </div>
        </motion.div>
    );
}
