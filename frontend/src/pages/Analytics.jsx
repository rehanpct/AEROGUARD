import React from "react";
import { motion } from "framer-motion";
import {
    AreaChart, Area, LineChart, Line, PieChart, Pie, Cell,
    XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import { useSystem } from "../context/SystemContext";

const PIE_COLORS = { SAFE: "#22c55e", CAUTION: "#facc15", BLOCKED: "#ef4444" };

function Card({ title, children }) {
    return (
        <div className="card" style={{ padding: 20 }}>
            <p style={{
                margin: "0 0 14px", fontSize: 11, fontWeight: 700,
                letterSpacing: 1.2, textTransform: "uppercase", color: "#64748b"
            }}>
                {title}
            </p>
            {children}
        </div>
    );
}

export default function Analytics() {
    const { history, backendOnline } = useSystem();

    // Derive pie data from history
    const pieCounts = (history ?? []).reduce(
        (acc, pt) => {
            if ((pt.risk ?? 0) <= 30) acc.SAFE++;
            else if (pt.risk <= 60) acc.CAUTION++;
            else acc.BLOCKED++;
            return acc;
        },
        { SAFE: 0, CAUTION: 0, BLOCKED: 0 }
    );
    const pieData = Object.entries(pieCounts).map(([name, value]) => ({ name, value }));

    // Current draw and vibration from history (if backend provided, else simulate)
    const currentData = (history ?? []).map((pt, i) => ({
        t: i,
        current: +(2.0 + Math.sin(i * 0.3) * 0.8).toFixed(2),
        safe: pt.safe,
    }));

    const vibData = (history ?? []).map((pt, i) => ({
        t: i,
        rms: +(Math.abs(Math.sin(i * 0.4) * 3.5) + 0.2).toFixed(2),
    }));

    return (
        <motion.div
            initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
        >
            <div style={{
                display: "flex", alignItems: "center", justifyContent: "space-between",
                marginBottom: 20, flexWrap: "wrap", gap: 10
            }}>
                <div>
                    <h2 style={{ margin: 0, color: "#e2e8f0", fontSize: 22, fontWeight: 700 }}>Analytics</h2>
                    <p style={{ margin: "4px 0 0", color: "#64748b", fontSize: 13 }}>
                        Risk trends &amp; sensor analytics
                    </p>
                </div>
                <div style={{
                    padding: "5px 14px", borderRadius: 20, fontSize: 12, fontWeight: 600,
                    background: backendOnline ? "rgba(34,197,94,0.1)" : "rgba(100,116,139,0.1)",
                    border: `1px solid ${backendOnline ? "#22c55e" : "#475569"}`,
                    color: backendOnline ? "#22c55e" : "#94a3b8",
                }}>
                    {backendOnline ? "● Live from Backend" : "○ Simulated"}
                </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 18, marginBottom: 18 }}>
                {/* Risk Index Trend */}
                <Card title="Risk Index Over Time">
                    <ResponsiveContainer width="100%" height={200}>
                        <AreaChart data={history ?? []}>
                            <defs>
                                <linearGradient id="riGrad" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.45} />
                                    <stop offset="95%" stopColor="#3B82F6" stopOpacity={0.02} />
                                </linearGradient>
                            </defs>
                            <XAxis dataKey="t" hide />
                            <YAxis domain={[0, 100]} tick={{ fill: "#4b5563", fontSize: 10 }} />
                            <Tooltip
                                contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
                                formatter={v => [`${Number(v).toFixed(1)}`, "Risk Index"]}
                                labelFormatter={() => ""}
                            />
                            <Area type="monotone" dataKey="risk" stroke="#3B82F6"
                                fill="url(#riGrad)" strokeWidth={2} dot={false} />
                        </AreaChart>
                    </ResponsiveContainer>
                </Card>

                {/* Risk Breakdown */}
                <Card title="Risk Breakdown">
                    <ResponsiveContainer width="100%" height={200}>
                        <PieChart>
                            <Pie data={pieData} cx="50%" cy="50%" innerRadius={48} outerRadius={72}
                                paddingAngle={3} dataKey="value">
                                {pieData.map(({ name }) => (
                                    <Cell key={name} fill={PIE_COLORS[name]} />
                                ))}
                            </Pie>
                            <Tooltip
                                contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
                            />
                            <Legend wrapperStyle={{ fontSize: 12, color: "#94a3b8" }} />
                        </PieChart>
                    </ResponsiveContainer>
                </Card>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
                {/* Safety Score trend */}
                <Card title="Safety Score Trend">
                    <ResponsiveContainer width="100%" height={160}>
                        <LineChart data={currentData}>
                            <XAxis dataKey="t" hide />
                            <YAxis domain={[0, 100]} tick={{ fill: "#4b5563", fontSize: 10 }} />
                            <Tooltip
                                contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
                                formatter={v => [`${Number(v).toFixed(1)}%`, "Safety"]}
                                labelFormatter={() => ""}
                            />
                            <Line type="monotone" dataKey="safe" stroke="#22c55e" dot={false} strokeWidth={2} />
                        </LineChart>
                    </ResponsiveContainer>
                </Card>

                {/* Vibration RMS */}
                <Card title="Gyro Vibration RMS">
                    <ResponsiveContainer width="100%" height={160}>
                        <AreaChart data={vibData}>
                            <defs>
                                <linearGradient id="vibGrad" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#8B5CF6" stopOpacity={0.4} />
                                    <stop offset="95%" stopColor="#8B5CF6" stopOpacity={0.02} />
                                </linearGradient>
                            </defs>
                            <XAxis dataKey="t" hide />
                            <YAxis tick={{ fill: "#4b5563", fontSize: 10 }} />
                            <Tooltip
                                contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
                                formatter={v => [`${Number(v).toFixed(2)} °/s`, "RMS"]}
                                labelFormatter={() => ""}
                            />
                            <Area type="monotone" dataKey="rms" stroke="#8B5CF6"
                                fill="url(#vibGrad)" strokeWidth={2} dot={false} />
                        </AreaChart>
                    </ResponsiveContainer>
                </Card>
            </div>
        </motion.div>
    );
}
