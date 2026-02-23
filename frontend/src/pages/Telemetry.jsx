import React from "react";
import { motion } from "framer-motion";
import { useSystem } from "../context/SystemContext";

const fmt = (v, dec = 1, unit = "") =>
    v == null ? "—" : `${Number(v).toFixed(dec)}${unit}`;

function Section({ title, children }) {
    return (
        <div style={{ marginBottom: 20 }}>
            <p style={{
                margin: "0 0 10px", fontSize: 11, fontWeight: 700, letterSpacing: 1.2,
                textTransform: "uppercase", color: "#64748b"
            }}>
                {title}
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 10 }}>
                {children}
            </div>
        </div>
    );
}

function MetricBox({ label, value, sub, color }) {
    return (
        <div style={{
            background: "rgba(255,255,255,0.03)", borderRadius: 10, padding: "12px 14px",
            border: "1px solid rgba(255,255,255,0.06)"
        }}>
            <div style={{ fontSize: 10, color: "#64748b", marginBottom: 4 }}>{label}</div>
            <div style={{ fontSize: 17, fontWeight: 700, color: color ?? "#e2e8f0" }}>{value}</div>
            {sub && <div style={{ fontSize: 10, color: "#475569", marginTop: 2 }}>{sub}</div>}
        </div>
    );
}

export default function Telemetry() {
    const {
        environment, sensors, gps, drone, risk_index, risk_level,
        safety_score, rain_probability, zone_status, relay_action, backendOnline,
    } = useSystem();

    const env = environment ?? {};
    const sen = sensors ?? {};
    const gpsD = gps ?? {};
    const droneD = drone ?? {};

    const gyroRms = Math.sqrt(
        (sen.gyro_x ?? 0) ** 2 + (sen.gyro_y ?? 0) ** 2 + (sen.gyro_z ?? 0) ** 2
    );

    const levelColor =
        risk_level === "UNSAFE" ? "#ef4444" :
            risk_level === "CAUTION" ? "#facc15" : "#22c55e";

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
                    <h2 style={{ margin: 0, color: "#e2e8f0", fontSize: 22, fontWeight: 700 }}>
                        Telemetry
                    </h2>
                    <p style={{ margin: "4px 0 0", color: "#64748b", fontSize: 13 }}>
                        All sensor readings — live from ESP32 / Arduino
                    </p>
                </div>
                <div style={{
                    padding: "5px 14px", borderRadius: 20, fontSize: 12, fontWeight: 600,
                    background: backendOnline ? "rgba(34,197,94,0.1)" : "rgba(100,116,139,0.1)",
                    border: `1px solid ${backendOnline ? "#22c55e" : "#475569"}`,
                    color: backendOnline ? "#22c55e" : "#94a3b8",
                }}>
                    {backendOnline ? "● Live" : "○ Simulation"}
                </div>
            </div>

            <div className="card" style={{ padding: 20 }}>
                {/* Risk summary row */}
                <Section title="Risk Assessment">
                    <MetricBox label="Risk Level" value={risk_level ?? "SAFE"} color={levelColor} />
                    <MetricBox label="Risk Index" value={fmt(risk_index, 1)} color={levelColor} />
                    <MetricBox label="Safety Score" value={fmt(safety_score, 1, "%")} />
                    <MetricBox label="Zone" value={zone_status ?? "GREEN"}
                        color={zone_status === "RED" ? "#ef4444" : zone_status === "YELLOW" ? "#facc15" : "#22c55e"} />
                    <MetricBox label="Relay" value={relay_action ?? "ALLOW"}
                        color={relay_action === "LOCK" ? "#ef4444" : "#22c55e"} />
                    <MetricBox label="Rain Prob." value={fmt((rain_probability ?? 0) * 100, 0, "%")} />
                </Section>

                {/* Environmental */}
                <Section title="Environmental Sensors (BME280)">
                    <MetricBox label="Temperature" value={fmt(env.temperature, 1, " °C")} />
                    <MetricBox label="Humidity" value={fmt(env.humidity, 1, " %")} />
                    <MetricBox label="Pressure" value={fmt(env.pressure, 1, " hPa")} />
                    <MetricBox label="LDR Light" value={env.ldr ?? sen.ldr ?? "—"}
                        sub="0=dark, 1023=bright"
                        color={(env.ldr ?? sen.ldr ?? 512) < 80 ? "#facc15" : "#22c55e"} />
                </Section>

                {/* IMU */}
                <Section title="IMU — Accelerometer (MPU6050)">
                    <MetricBox label="Acc X" value={fmt(sen.acc_x, 3, " m/s²")} />
                    <MetricBox label="Acc Y" value={fmt(sen.acc_y, 3, " m/s²")} />
                    <MetricBox label="Acc Z" value={fmt(sen.acc_z, 3, " m/s²")} />
                    <MetricBox label="Tilt Angle" value={fmt(sen.tilt_angle, 1, "°")}
                        color={(sen.tilt_angle ?? 0) > 30 ? "#ef4444" : (sen.tilt_angle ?? 0) > 15 ? "#facc15" : "#22c55e"} />
                </Section>

                <Section title="IMU — Gyroscope (MPU6050)">
                    <MetricBox label="Gyro X" value={fmt(sen.gyro_x, 2, " °/s")} />
                    <MetricBox label="Gyro Y" value={fmt(sen.gyro_y, 2, " °/s")} />
                    <MetricBox label="Gyro Z" value={fmt(sen.gyro_z, 2, " °/s")} />
                    <MetricBox label="Vibration RMS" value={fmt(gyroRms, 1, " °/s")}
                        color={gyroRms > 250 ? "#ef4444" : gyroRms > 80 ? "#facc15" : "#22c55e"} />
                </Section>

                {/* Proximity & detection */}
                <Section title="Proximity & Detection Sensors">
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
                            ? ((rawDistance < 10) ? "#ef4444" : (rawDistance < 30) ? "#facc15" : "#22c55e")
                            : "#64748b";

                        return (
                            <>
                                <MetricBox label="Ultrasonic (cm)" value={distanceText}
                                    sub="obstacle distance"
                                    color={distanceColor} />
                                <MetricBox label="IR Obstacle" value={obstacleDetected ? "Detected" : "Clear"}
                                    color={obstacleDetected ? "#ef4444" : "#22c55e"} />
                                <MetricBox label="PIR Motion" value={sen.pir === 1 ? "Motion" : "None"}
                                    color={sen.pir === 1 ? "#facc15" : "#22c55e"} />
                            </>
                        );
                    })()}
                </Section>

                {/* Water & electrical */}
                <Section title="Water & Electrical">
                    <MetricBox label="Water Sensor" value={sen.water ?? 0}
                        sub="0=dry, 1023=soaked"
                        color={(sen.water ?? 0) > 500 ? "#ef4444" : (sen.water ?? 0) > 100 ? "#facc15" : "#22c55e"} />
                    <MetricBox label="Current" value={fmt(sen.current_a, 2, " A")}
                        color={(sen.current_a ?? 0) > 5 ? "#ef4444" : (sen.current_a ?? 0) > 3.5 ? "#facc15" : "#22c55e"} />
                    <MetricBox label="Voltage" value={fmt(droneD.voltage, 2, " V")} />
                    <MetricBox label="Battery" value={fmt(droneD.battery_pct, 0, "%")} />
                    <MetricBox label="Signal" value={fmt(droneD.signal_strength, 0, "%")} />
                </Section>

                {/* GPS */}
                <Section title="GPS (NEO-6M)">
                    <MetricBox label="Latitude" value={fmt(gpsD.latitude, 5, "°")} />
                    <MetricBox label="Longitude" value={fmt(gpsD.longitude, 5, "°")} />
                    <MetricBox label="Altitude" value={fmt(gpsD.altitude, 1, " m")} />
                    <MetricBox label="Satellites" value={gpsD.satellites ?? 0}
                        color={(gpsD.satellites ?? 0) < 3 ? "#ef4444" : (gpsD.satellites ?? 0) < 6 ? "#facc15" : "#22c55e"} />
                    <MetricBox label="HDOP" value={fmt(gpsD.hdop, 2)} />
                    <MetricBox label="Fallback" value={gpsD.using_fallback ? "Yes" : "No"}
                        color={gpsD.using_fallback ? "#facc15" : "#22c55e"}
                        sub={gpsD.using_fallback ? gpsD.location_name : "Live fix"} />
                </Section>
            </div>
        </motion.div>
    );
}
