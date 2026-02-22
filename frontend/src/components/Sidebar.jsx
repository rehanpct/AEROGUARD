import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Radio, Map, BarChart2, ScrollText, Settings, Cpu } from 'lucide-react';

const NAV = [
    { path: '/dashboard', label: 'Dashboard', Icon: LayoutDashboard },
    { path: '/telemetry', label: 'Telemetry', Icon: Radio },
    { path: '/zone-map', label: 'Zone Map', Icon: Map },
    { path: '/analytics', label: 'Analytics', Icon: BarChart2 },
    { path: '/logs', label: 'Logs', Icon: ScrollText },
    { path: '/settings', label: 'Settings', Icon: Settings },
];

export default function Sidebar() {
    return (
        <aside style={{
            background: 'var(--bg-sidebar)',
            borderRight: '1px solid var(--border)',
            display: 'flex',
            flexDirection: 'column',
            padding: '16px 12px',
            gap: 4,
            overflowY: 'auto',
        }}>
            {/* System tag */}
            <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '8px 12px 16px',
                marginBottom: 4,
            }}>
                <Cpu size={13} color="var(--accent-blue)" />
                <span style={{ fontSize: 11, color: 'var(--text-secondary)', letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 600 }}>
                    Navigation
                </span>
            </div>

            {NAV.map(({ path, label, Icon }) => (
                <NavLink
                    key={path}
                    to={path}
                    className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                >
                    <Icon size={16} />
                    {label}
                </NavLink>
            ))}

            {/* Bottom version info */}
            <div style={{ marginTop: 'auto', padding: '16px 12px 4px' }}>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.06em' }}>
                    AEROGUARD v1.0.0
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                    ESP32 · Flask · LightGBM
                </div>
            </div>
        </aside>
    );
}
