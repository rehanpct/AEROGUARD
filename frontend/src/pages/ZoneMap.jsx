/**
 * AeroGuard – Zone Map
 *
 * All zones AND the drone position use the SAME GPS coordinate system.
 * Every zone is defined by an array of GPS corners; coordToSvg() maps
 * those corners to SVG viewBox space so nothing is ever misaligned.
 *
 * Bounding box used for Kerala test region:
 *   LAT: 8.0 (south) → 13.5 (north)   SVG Y: 0 (top) → 100 (bottom)
 *   LON: 74.5 (west) → 78.0 (east)     SVG X: 0 (left) → 100 (right)
 */
import React, { useState } from "react";
import { motion } from "framer-motion";
import { useSystem } from "../context/SystemContext";

// ── Map bounding box ──────────────────────────────────────────────────────────
const LAT_MAX = 13.5, LAT_MIN = 8.0;
const LON_MIN = 74.5, LON_MAX = 78.0;

function coordToSvg(lat, lon) {
    const x = ((lon - LON_MIN) / (LON_MAX - LON_MIN)) * 100;
    const y = ((LAT_MAX - lat) / (LAT_MAX - LAT_MIN)) * 100;   // invert Y (north = top)
    return {
        x: Math.max(0.5, Math.min(99.5, x)),
        y: Math.max(0.5, Math.min(99.5, y)),
    };
}

// Convert an array of {lat,lon} points to an SVG polygon "points" string
function toPolygonPoints(coords) {
    return coords.map(c => {
        const { x, y } = coordToSvg(c.lat, c.lon);
        return `${x},${y}`;
    }).join(" ");
}

// ── Zone definitions (GPS coordinates) ───────────────────────────────────────
const ZONES = [
    {
        id: "red_1",
        color: "RED",
        name: "Restricted Airspace – Bengaluru North",
        reason: "Military exclusion zone — no-fly at all times",
        risk: "1.0×", auth: "Prohibited",
        coords: [
            { lat: 13.30, lon: 77.40 },
            { lat: 13.30, lon: 77.80 },
            { lat: 13.10, lon: 77.80 },
            { lat: 13.10, lon: 77.40 },
        ],
    },
    {
        id: "yellow_1",
        color: "YELLOW",
        name: "Airport Approach Zone – Kempegowda",
        reason: "Within 5 km of Kempegowda International Airport",
        risk: "0.6×", auth: "NOTAMs required",
        coords: [
            { lat: 13.10, lon: 77.40 },
            { lat: 13.10, lon: 77.80 },
            { lat: 12.85, lon: 77.80 },
            { lat: 12.85, lon: 77.40 },
        ],
    },
    {
        id: "green_1",
        color: "GREEN",
        name: "Rural Open Area – Bengaluru South",
        reason: "Low-density, uncontrolled airspace — open operations",
        risk: "0.2×", auth: "Open",
        coords: [
            { lat: 12.85, lon: 77.40 },
            { lat: 12.85, lon: 77.80 },
            { lat: 12.60, lon: 77.80 },
            { lat: 12.60, lon: 77.40 },
        ],
    },
    {
        id: "yellow_2",
        color: "YELLOW",
        name: "Urban Overfly Zone – Mysuru Corridor",
        reason: "Populated area – height limit 50 m AGL",
        risk: "0.5×", auth: "Registration needed",
        coords: [
            { lat: 12.60, lon: 76.40 },
            { lat: 12.60, lon: 77.00 },
            { lat: 12.20, lon: 77.00 },
            { lat: 12.20, lon: 76.40 },
        ],
    },
    {
        id: "green_2",
        color: "GREEN",
        name: "Kerala Test Zone (Fallback GPS)",
        reason: "Default test area for GPIO Kerala coordinates",
        risk: "0.1×", auth: "Open",
        coords: [
            { lat: 11.10, lon: 75.80 },
            { lat: 11.10, lon: 76.70 },
            { lat: 10.50, lon: 76.70 },
            { lat: 10.50, lon: 75.80 },
        ],
    },
];

// ── Style maps ────────────────────────────────────────────────────────────────
const ZONE_STYLE = {
    RED: { fill: "rgba(239,68,68,0.18)", stroke: "#ef4444" },
    YELLOW: { fill: "rgba(250,204,21,0.14)", stroke: "#facc15" },
    GREEN: { fill: "rgba(34,197,94,0.14)", stroke: "#22c55e" },
};

// ── Component ─────────────────────────────────────────────────────────────────
export default function ZoneMap() {
    const { gps, zone_status, classification, backendOnline } = useSystem();

    const [selectedZone, setSelectedZone] = useState(ZONES[2]);

    const gpsD = gps ?? {};
    const droneLat = gpsD.latitude ?? 10.8505;
    const droneLon = gpsD.longitude ?? 76.2711;
    const usingFallback = gpsD.using_fallback ?? true;
    const locationName = gpsD.location_name ?? "Kerala Demo Location";

    const dronePos = coordToSvg(droneLat, droneLon);

    const ringColor =
        zone_status === "RED" ? "#ef4444" :
            zone_status === "YELLOW" ? "#facc15" : "#22c55e";

    // Compute label centroid from GPS corners
    const centroid = (coords) => {
        const lat = coords.reduce((s, c) => s + c.lat, 0) / coords.length;
        const lon = coords.reduce((s, c) => s + c.lon, 0) / coords.length;
        return coordToSvg(lat, lon);
    };

    return (
        <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            style={{ display: "flex", flexDirection: "column", gap: 18 }}
        >
            {/* ── Header ──────────────────────────────────────────────────── */}
            <div style={{
                display: "flex", alignItems: "center",
                justifyContent: "space-between", flexWrap: "wrap", gap: 10,
            }}>
                <div>
                    <h2 style={{ margin: 0, color: "#e2e8f0", fontSize: 22, fontWeight: 700 }}>
                        Airspace Zone Map
                    </h2>
                    <p style={{ margin: "4px 0 0", color: "#64748b", fontSize: 13 }}>
                        GPS-accurate geofenced zones · click a zone for details
                    </p>
                </div>

                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <div style={{
                        padding: "5px 14px", borderRadius: 20, fontSize: 12, fontWeight: 600,
                        background: backendOnline ? "rgba(34,197,94,0.1)" : "rgba(100,116,139,0.1)",
                        border: `1px solid ${backendOnline ? "#22c55e" : "#475569"}`,
                        color: backendOnline ? "#22c55e" : "#94a3b8",
                    }}>
                        {backendOnline ? "● Live Data" : "○ Simulated"}
                    </div>

                    {usingFallback && (
                        <motion.div
                            initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}
                            style={{
                                padding: "5px 14px", borderRadius: 20, fontSize: 12, fontWeight: 600,
                                background: "rgba(250,204,21,0.12)",
                                border: "1px solid rgba(250,204,21,0.4)",
                                color: "#facc15",
                                display: "flex", alignItems: "center", gap: 6,
                            }}
                        >
                            ⚠ GPS Signal Not Available – Using Default Location ({locationName})
                        </motion.div>
                    )}
                </div>
            </div>

            {/* ── Main layout ──────────────────────────────────────────────── */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 290px", gap: 18 }}>

                {/* ── SVG Map ─────────────────────────────────────────────── */}
                <div className="card" style={{ padding: 0, overflow: "hidden", position: "relative" }}>
                    {/* Coord legend overlay */}
                    <div style={{
                        position: "absolute", top: 10, left: 10, zIndex: 10,
                        fontSize: 10, color: "#334155",
                        fontFamily: "monospace",
                        background: "rgba(11,31,58,0.7)",
                        padding: "4px 8px", borderRadius: 6,
                        border: "1px solid rgba(255,255,255,0.06)",
                    }}>
                        {droneLat.toFixed(4)}°N {droneLon.toFixed(4)}°E
                        {usingFallback && " (fallback)"}
                    </div>

                    <svg
                        viewBox="0 0 100 100"
                        preserveAspectRatio="xMidYMid meet"
                        style={{ width: "100%", display: "block", background: "#0B1020" }}
                    >
                        {/* Background grid */}
                        {[10, 20, 30, 40, 50, 60, 70, 80, 90].map(v => (
                            <g key={v}>
                                <line x1={v} y1={0} x2={v} y2={100}
                                    stroke="#1a2744" strokeWidth={0.25} />
                                <line x1={0} y1={v} x2={100} y2={v}
                                    stroke="#1a2744" strokeWidth={0.25} />
                            </g>
                        ))}

                        {/* Meridian / parallel labels */}
                        {[75, 76, 77].map(lon => {
                            const { x } = coordToSvg(10, lon);
                            return (
                                <text key={lon} x={x} y={99} textAnchor="middle"
                                    fontSize={2.2} fill="#1e3a5f">{lon}°E</text>
                            );
                        })}
                        {[9, 10, 11, 12, 13].map(lat => {
                            const { y } = coordToSvg(lat, 74.5);
                            return (
                                <text key={lat} x={1} y={y} textAnchor="start"
                                    dominantBaseline="middle" fontSize={2.2} fill="#1e3a5f">{lat}°N</text>
                            );
                        })}

                        {/* ── Zone polygons ──────────────────────────────── */}
                        {ZONES.map(z => {
                            const pts = toPolygonPoints(z.coords);
                            const ctr = centroid(z.coords);
                            const sty = ZONE_STYLE[z.color];
                            const isSel = selectedZone?.id === z.id;
                            return (
                                <g key={z.id} onClick={() => setSelectedZone(z)}
                                    style={{ cursor: "pointer" }}>
                                    <polygon
                                        points={pts}
                                        fill={sty.fill}
                                        stroke={sty.stroke}
                                        strokeWidth={isSel ? 0.7 : 0.35}
                                        strokeDasharray={isSel ? "0" : "1.5 0.8"}
                                        style={{ transition: "all .2s" }}
                                    />
                                    <text
                                        x={ctr.x} y={ctr.y}
                                        textAnchor="middle" dominantBaseline="middle"
                                        fontSize={2.2} fill={sty.stroke}
                                        style={{ pointerEvents: "none", userSelect: "none", fontWeight: 700 }}
                                    >
                                        {z.color}
                                    </text>
                                </g>
                            );
                        })}

                        {/* ── Drone position (no framer-motion inside SVG) ─── */}
                        {/* Pulse ring – native SVG SMIL animate */}
                        <circle cx={dronePos.x} cy={dronePos.y}
                            r={4} fill="none" stroke={ringColor} strokeWidth={0.45}>
                            <animate attributeName="r"
                                values="3;8;3" dur="2s" repeatCount="indefinite" />
                            <animate attributeName="opacity"
                                values="1;0;1" dur="2s" repeatCount="indefinite" />
                        </circle>
                        {/* Second softer ring */}
                        <circle cx={dronePos.x} cy={dronePos.y}
                            r={2} fill="none" stroke={ringColor} strokeWidth={0.3}>
                            <animate attributeName="r"
                                values="2;5;2" dur="2s" begin="0.4s" repeatCount="indefinite" />
                            <animate attributeName="opacity"
                                values="0.8;0;0.8" dur="2s" begin="0.4s" repeatCount="indefinite" />
                        </circle>
                        {/* Solid inner dot */}
                        <circle cx={dronePos.x} cy={dronePos.y} r={1.6}
                            fill={ringColor} />
                        {/* Crosshair */}
                        <line x1={dronePos.x - 4} y1={dronePos.y}
                            x2={dronePos.x - 2} y2={dronePos.y}
                            stroke={ringColor} strokeWidth={0.35} />
                        <line x1={dronePos.x + 2} y1={dronePos.y}
                            x2={dronePos.x + 4} y2={dronePos.y}
                            stroke={ringColor} strokeWidth={0.35} />
                        <line x1={dronePos.x} y1={dronePos.y - 4}
                            x2={dronePos.x} y2={dronePos.y - 2}
                            stroke={ringColor} strokeWidth={0.35} />
                        <line x1={dronePos.x} y1={dronePos.y + 2}
                            x2={dronePos.x} y2={dronePos.y + 4}
                            stroke={ringColor} strokeWidth={0.35} />
                        {/* Label */}
                        <text x={dronePos.x} y={dronePos.y - 6}
                            textAnchor="middle" fontSize={2.8}
                            fill="#e2e8f0" fontWeight="bold"
                            style={{ userSelect: "none" }}>
                            UAV{usingFallback ? " ⚠" : ""}
                        </text>
                    </svg>
                </div>

                {/* ── Info Panel ──────────────────────────────────────────── */}
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>

                    {/* Drone GPS */}
                    <div className="card" style={{ padding: 16 }}>
                        <p style={{
                            margin: "0 0 10px", color: "#64748b", fontSize: 11,
                            fontWeight: 700, textTransform: "uppercase", letterSpacing: 1
                        }}>
                            Drone Position
                        </p>
                        {usingFallback && (
                            <div style={{
                                padding: "6px 10px", borderRadius: 8, marginBottom: 10,
                                background: "rgba(250,204,21,0.08)",
                                border: "1px solid rgba(250,204,21,0.25)",
                                color: "#facc15", fontSize: 11,
                            }}>
                                ⚠ No GPS Fix — Default location
                            </div>
                        )}
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                            {[
                                { label: "Lat", value: droneLat.toFixed(4) + "°" },
                                { label: "Lon", value: droneLon.toFixed(4) + "°" },
                                { label: "Sats", value: gpsD.satellites ?? 0 },
                                { label: "HDOP", value: (gpsD.hdop ?? 0).toFixed(2) },
                            ].map(({ label, value }) => (
                                <div key={label} style={{
                                    background: "rgba(255,255,255,0.03)",
                                    borderRadius: 8, padding: "8px 10px",
                                }}>
                                    <div style={{ fontSize: 10, color: "#475569", marginBottom: 2 }}>{label}</div>
                                    <div style={{ fontSize: 13, color: "#e2e8f0", fontWeight: 600 }}>{value}</div>
                                </div>
                            ))}
                        </div>
                        <div style={{ marginTop: 8, fontSize: 11, color: "#475569" }}>
                            {locationName}
                        </div>
                    </div>

                    {/* Current zone */}
                    <div className="card" style={{ padding: 16 }}>
                        <p style={{
                            margin: "0 0 10px", color: "#64748b", fontSize: 11,
                            fontWeight: 700, textTransform: "uppercase", letterSpacing: 1
                        }}>
                            Current Zone
                        </p>
                        <div style={{
                            display: "inline-block", padding: "4px 16px", borderRadius: 20,
                            background: `${ZONE_STYLE[zone_status ?? "GREEN"].fill}`,
                            border: `1px solid ${ringColor}`,
                            color: ringColor, fontWeight: 700, fontSize: 14,
                        }}>
                            {zone_status ?? "GREEN"}
                        </div>
                        <p style={{ margin: "10px 0 0", fontSize: 12, color: "#94a3b8" }}>
                            {classification ?? "Safe to Fly"}
                        </p>
                    </div>

                    {/* Selected zone details */}
                    {selectedZone && (
                        <div className="card" style={{ padding: 16 }}>
                            <p style={{
                                margin: "0 0 10px", color: "#64748b", fontSize: 11,
                                fontWeight: 700, textTransform: "uppercase", letterSpacing: 1
                            }}>
                                Selected Zone
                            </p>
                            <div style={{
                                width: 10, height: 10, borderRadius: "50%",
                                background: ZONE_STYLE[selectedZone.color].stroke,
                                display: "inline-block", marginBottom: 6,
                            }} />
                            <p style={{ margin: "0 0 4px", color: "#e2e8f0", fontSize: 13, fontWeight: 600 }}>
                                {selectedZone.name}
                            </p>
                            <p style={{ margin: "0 0 10px", color: "#64748b", fontSize: 12 }}>
                                {selectedZone.reason}
                            </p>
                            {[
                                { l: "Risk Multiplier", v: selectedZone.risk },
                                { l: "Authorization", v: selectedZone.auth },
                                { l: "Zone Type", v: selectedZone.color },
                            ].map(({ l, v }) => (
                                <div key={l} style={{
                                    display: "flex", justifyContent: "space-between",
                                    fontSize: 12, padding: "4px 0",
                                    borderBottom: "1px solid rgba(255,255,255,0.04)",
                                }}>
                                    <span style={{ color: "#64748b" }}>{l}</span>
                                    <span style={{
                                        color: v === "RED" ? "#ef4444" :
                                            v === "YELLOW" ? "#facc15" :
                                                v === "GREEN" ? "#22c55e" : "#cbd5e1",
                                        fontWeight: 600,
                                    }}>{v}</span>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Legend */}
                    <div className="card" style={{ padding: 14 }}>
                        <p style={{
                            margin: "0 0 8px", color: "#64748b", fontSize: 10,
                            fontWeight: 700, textTransform: "uppercase"
                        }}>Legend</p>
                        {["RED", "YELLOW", "GREEN"].map(c => (
                            <div key={c} style={{
                                display: "flex", alignItems: "center",
                                gap: 8, marginBottom: 6,
                            }}>
                                <div style={{
                                    width: 12, height: 12, borderRadius: 3,
                                    background: ZONE_STYLE[c].fill,
                                    border: `1px solid ${ZONE_STYLE[c].stroke}`,
                                }} />
                                <span style={{ fontSize: 11, color: "#94a3b8" }}>
                                    {c === "RED" ? "Restricted – No Fly" :
                                        c === "YELLOW" ? "Caution – Auth may be needed" :
                                            "Open – Safe to operate"}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </motion.div>
    );
}
