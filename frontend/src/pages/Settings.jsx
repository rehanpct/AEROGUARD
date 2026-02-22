import { useState } from 'react';
import { useSystem } from '../context/SystemContext';
import { Settings as SettingsIcon, AlertTriangle, Bell, Shield, Sliders } from 'lucide-react';

function SettingRow({ label, desc, children }) {
    return (
        <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '12px 14px', background: 'rgba(255,255,255,0.025)',
            borderRadius: 10, border: '1px solid var(--border)',
        }}>
            <div>
                <div style={{ fontSize: 13, fontWeight: 500 }}>{label}</div>
                {desc && <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>{desc}</div>}
            </div>
            {children}
        </div>
    );
}

function Toggle({ checked, onChange }) {
    return (
        <label className="toggle-wrap">
            <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} />
            <span className="toggle-slider" />
        </label>
    );
}

function Section({ title, icon, children }) {
    return (
        <div className="glass-card p-5" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                {icon}
                <span style={{ fontWeight: 600, fontSize: 14 }}>{title}</span>
            </div>
            {children}
        </div>
    );
}

export default function Settings() {
    const { simulateFailsafe, setSimulateFailsafe, manualOverride, setManualOverride } = useSystem();
    const [notif, setNotif] = useState({ critical: true, warning: true, clear: false });
    const [thresholds, setThresholds] = useState({ riskLock: 75, battWarn: 20, windWarn: 10 });

    return (
        <div className="page-container">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18 }}>
                {/* Safety Settings */}
                <Section title="Safety System" icon={<Shield size={14} color="var(--accent-blue)" />}>
                    <SettingRow label="Failsafe Simulation" desc="Trigger RED zone + rain + high risk">
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            {simulateFailsafe && <span className="badge badge-blocked" style={{ fontSize: 10 }}>ACTIVE</span>}
                            <Toggle checked={simulateFailsafe} onChange={setSimulateFailsafe} />
                        </div>
                    </SettingRow>
                    <SettingRow label="Manual Override" desc="Bypass safety lock (operator use only)">
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            {manualOverride && <span className="badge badge-caution" style={{ fontSize: 10 }}>ON</span>}
                            <Toggle checked={manualOverride} onChange={setManualOverride} />
                        </div>
                    </SettingRow>

                    {simulateFailsafe && (
                        <div style={{
                            padding: '10px 12px', borderRadius: 10,
                            background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)',
                            fontSize: 12, color: 'var(--red)',
                        }}>
                            <AlertTriangle size={12} style={{ marginRight: 6, display: 'inline' }} />
                            Failsafe simulation is active — dock is locked
                        </div>
                    )}
                </Section>

                {/* Notifications */}
                <Section title="Notifications" icon={<Bell size={14} color="var(--accent-blue)" />}>
                    <SettingRow label="Critical Alerts" desc="Receive L1 hard-lock notifications">
                        <Toggle checked={notif.critical} onChange={v => setNotif(p => ({ ...p, critical: v }))} />
                    </SettingRow>
                    <SettingRow label="Warning Alerts" desc="Receive L2/L3 caution notifications">
                        <Toggle checked={notif.warning} onChange={v => setNotif(p => ({ ...p, warning: v }))} />
                    </SettingRow>
                    <SettingRow label="Clear / OK Events" desc="Log nominal system events">
                        <Toggle checked={notif.clear} onChange={v => setNotif(p => ({ ...p, clear: v }))} />
                    </SettingRow>
                </Section>

                {/* Thresholds */}
                <Section title="Risk Thresholds" icon={<Sliders size={14} color="var(--accent-blue)" />}>
                    {[
                        { key: 'riskLock', label: 'Risk Lock Threshold', unit: '/100', min: 50, max: 100 },
                        { key: 'battWarn', label: 'Battery Warning', unit: '%', min: 10, max: 40 },
                        { key: 'windWarn', label: 'Wind Warning', unit: ' m/s', min: 5, max: 25 },
                    ].map(({ key, label, unit, min, max }) => (
                        <SettingRow key={key} label={label} desc={`Current: ${thresholds[key]}${unit}`}>
                            <input type="range" min={min} max={max} value={thresholds[key]}
                                onChange={e => setThresholds(p => ({ ...p, [key]: +e.target.value }))}
                                style={{ width: 120, accentColor: 'var(--accent-blue)', cursor: 'pointer' }}
                            />
                        </SettingRow>
                    ))}
                </Section>

                {/* System Info */}
                <Section title="System Information" icon={<SettingsIcon size={14} color="var(--accent-blue)" />}>
                    {[
                        ['Version', 'AeroGuard v1.0.0'],
                        ['Backend', 'Flask 3.0 · SQLite WAL'],
                        ['ML Models', 'LightGBM + Sklearn fallback'],
                        ['Hardware', 'ESP32 · GPS · MPU6050 · DHT'],
                        ['Zone DB', '8 zones registered'],
                        ['Update Interval', '2 seconds'],
                    ].map(([k, v]) => (
                        <div key={k} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
                            <span style={{ color: 'var(--text-secondary)' }}>{k}</span>
                            <span style={{ fontWeight: 500, color: 'var(--text-primary)' }}>{v}</span>
                        </div>
                    ))}
                </Section>
            </div>
        </div>
    );
}
