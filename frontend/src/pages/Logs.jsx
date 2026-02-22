import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useSystem } from '../context/SystemContext';
import { ScrollText, Filter, RefreshCw } from 'lucide-react';

const SEV_COLOR = {
    INFO: '#3B82F6',
    WARNING: '#facc15',
    CRITICAL: '#ef4444',
};
const SEV_BG = {
    INFO: 'rgba(59,130,246,0.08)',
    WARNING: 'rgba(250,204,21,0.08)',
    CRITICAL: 'rgba(239,68,68,0.08)',
};

function formatTime(ts) {
    if (!ts) return '—';
    try {
        const d = new Date(ts);
        return d.toLocaleTimeString('en-GB', { hour12: false });
    } catch { return ts; }
}

export default function Logs() {
    const { logs, backendOnline } = useSystem();
    const [filter, setFilter] = useState('ALL');

    // Context gives: { id, timestamp, severity, message }
    const safeLogs = Array.isArray(logs) ? logs : [];

    const filtered = filter === 'ALL'
        ? safeLogs
        : safeLogs.filter(l => l.severity === filter);

    const counts = {
        INFO: safeLogs.filter(l => l.severity === 'INFO').length,
        WARNING: safeLogs.filter(l => l.severity === 'WARNING').length,
        CRITICAL: safeLogs.filter(l => l.severity === 'CRITICAL').length,
    };

    return (
        <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35 }}
            style={{ display: 'flex', flexDirection: 'column', gap: 16 }}
        >
            {/* Header */}
            <div style={{
                display: 'flex', alignItems: 'center',
                justifyContent: 'space-between', flexWrap: 'wrap', gap: 10,
            }}>
                <div>
                    <h2 style={{ margin: 0, color: '#e2e8f0', fontSize: 22, fontWeight: 700 }}>
                        System Event Log
                    </h2>
                    <p style={{ margin: '4px 0 0', color: '#64748b', fontSize: 13 }}>
                        {safeLogs.length} events · auto-refreshes every 5 s
                    </p>
                </div>

                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <div style={{
                        padding: '5px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600,
                        background: backendOnline ? 'rgba(34,197,94,0.1)' : 'rgba(100,116,139,0.1)',
                        border: `1px solid ${backendOnline ? '#22c55e' : '#475569'}`,
                        color: backendOnline ? '#22c55e' : '#94a3b8',
                    }}>
                        {backendOnline ? '● Live' : '○ Simulation'}
                    </div>

                    {/* Filter buttons */}
                    <div style={{ display: 'flex', gap: 6 }}>
                        {['ALL', 'INFO', 'WARNING', 'CRITICAL'].map(f => (
                            <button
                                key={f}
                                onClick={() => setFilter(f)}
                                style={{
                                    padding: '5px 14px', borderRadius: 20, fontSize: 12,
                                    fontWeight: 600, cursor: 'pointer', border: '1px solid',
                                    background: filter === f
                                        ? (f === 'ALL' ? 'rgba(59,130,246,0.15)' : `${SEV_BG[f]}`)
                                        : 'transparent',
                                    borderColor: filter === f
                                        ? (f === 'ALL' ? '#3B82F6' : SEV_COLOR[f])
                                        : '#334155',
                                    color: filter === f
                                        ? (f === 'ALL' ? '#3B82F6' : SEV_COLOR[f])
                                        : '#64748b',
                                    transition: 'all .2s',
                                }}
                            >
                                {f} {f !== 'ALL' && `(${counts[f] ?? 0})`}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* Count stats */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
                {['INFO', 'WARNING', 'CRITICAL'].map(s => (
                    <div key={s} className="card" style={{
                        padding: '14px 18px',
                        borderTop: `3px solid ${SEV_COLOR[s]}`,
                        display: 'flex', alignItems: 'center', gap: 12,
                    }}>
                        <div>
                            <div style={{ fontSize: 11, color: '#64748b', marginBottom: 2 }}>{s}</div>
                            <div style={{ fontSize: 28, fontWeight: 800, color: SEV_COLOR[s], lineHeight: 1 }}>
                                {counts[s]}
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            {/* Log table */}
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                {/* Column headers */}
                <div style={{
                    display: 'grid',
                    gridTemplateColumns: '140px 110px 1fr',
                    gap: 0,
                    padding: '10px 16px',
                    borderBottom: '1px solid rgba(255,255,255,0.06)',
                    fontSize: 10, color: '#475569',
                    textTransform: 'uppercase', letterSpacing: '0.08em',
                    fontWeight: 700,
                }}>
                    <span>Timestamp</span>
                    <span>Severity</span>
                    <span>Message</span>
                </div>

                {/* Scroll area */}
                <div style={{ overflowY: 'auto', maxHeight: '55vh' }}>
                    <AnimatePresence initial={false}>
                        {filtered.length === 0 ? (
                            <div style={{
                                padding: 48, textAlign: 'center',
                                color: '#475569', fontSize: 13,
                            }}>
                                <RefreshCw size={18} style={{ marginBottom: 8, opacity: 0.4 }} />
                                <div>No events{filter !== 'ALL' ? ` matching "${filter}"` : ''}.</div>
                                {!backendOnline && (
                                    <div style={{ marginTop: 8, color: '#334155', fontSize: 12 }}>
                                        Backend offline — logs will appear when connected.
                                    </div>
                                )}
                            </div>
                        ) : filtered.map((log, i) => (
                            <motion.div
                                key={log.id ?? i}
                                initial={{ opacity: 0, x: -8 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ duration: 0.2, delay: i < 20 ? i * 0.01 : 0 }}
                                style={{
                                    display: 'grid',
                                    gridTemplateColumns: '140px 110px 1fr',
                                    gap: 0,
                                    padding: '9px 16px',
                                    borderBottom: '1px solid rgba(255,255,255,0.03)',
                                    alignItems: 'center',
                                    background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)',
                                    transition: 'background .15s',
                                }}
                            >
                                {/* Timestamp */}
                                <span style={{
                                    fontSize: 11.5, color: '#64748b',
                                    fontFamily: 'monospace',
                                }}>
                                    {formatTime(log.timestamp)}
                                </span>

                                {/* Severity badge */}
                                <span style={{
                                    display: 'inline-block',
                                    padding: '2px 10px',
                                    borderRadius: 12,
                                    fontSize: 10,
                                    fontWeight: 700,
                                    letterSpacing: '0.06em',
                                    background: SEV_BG[log.severity] ?? 'rgba(100,116,139,0.1)',
                                    color: SEV_COLOR[log.severity] ?? '#94a3b8',
                                    border: `1px solid ${SEV_COLOR[log.severity] ?? '#475569'}40`,
                                    width: 'fit-content',
                                }}>
                                    {log.severity ?? '—'}
                                </span>

                                {/* Message */}
                                <span style={{
                                    fontSize: 12.5,
                                    color: log.severity === 'CRITICAL' ? '#fca5a5'
                                        : log.severity === 'WARNING' ? '#fde68a'
                                            : '#cbd5e1',
                                }}>
                                    {log.message ?? '—'}
                                </span>
                            </motion.div>
                        ))}
                    </AnimatePresence>
                </div>
            </div>
        </motion.div>
    );
}
