import { useSystem } from '../context/SystemContext';
import { motion, AnimatePresence } from 'framer-motion';
import { Shield, User, Wifi } from 'lucide-react';

export default function TopNav() {
    const {
        classification, risk_index: riskIndex, hard_lock, risk_level, backendOnline,
    } = useSystem();

    const isBlocked = hard_lock || (riskIndex ?? 0) >= 75;
    const isCaution = !isBlocked && ((riskIndex ?? 0) >= 35 || risk_level === 'CAUTION' || classification === 'Fly with Caution');
    const statusLabel = isBlocked ? 'BLOCKED' : isCaution ? 'CAUTION' : 'SAFE';
    const badgeClass = isBlocked ? 'badge-blocked' : isCaution ? 'badge-caution' : 'badge-safe';
    const dotClass = isBlocked ? 'pulse-dot pulse-red' : isCaution ? 'pulse-dot pulse-yellow' : 'pulse-dot pulse-green';


    return (
        <nav style={{
            height: '72px',
            background: 'var(--bg-card)',
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 24px',
            backdropFilter: 'blur(16px)',
            boxShadow: '0 4px 24px rgba(0,0,0,0.3)',
            position: 'relative',
            zIndex: 100,
        }}>
            {/* Logo */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{
                    width: 36, height: 36, borderRadius: 10,
                    background: 'linear-gradient(135deg, #27272A, #09090B)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    boxShadow: '0 0 16px rgba(255,255,255,0.05)',
                    border: '1px solid var(--border)',
                }}>
                    <Shield size={20} color="white" />
                </div>
                <div>
                    <div style={{ fontFamily: 'Poppins, sans-serif', fontWeight: 700, fontSize: 18, color: '#E2E8F0', letterSpacing: '-0.5px' }}>
                        AeroGuard
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text-secondary)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
                        UAV Ground Station
                    </div>
                </div>
            </div>

            {/* Center Status Badge */}
            <AnimatePresence mode="wait">
                <motion.div
                    key={statusLabel}
                    initial={{ opacity: 0, scale: 0.85 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.85 }}
                    transition={{ duration: 0.3 }}
                    style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}
                >
                    <div className={`badge ${badgeClass}`} style={{ fontSize: 13, padding: '6px 20px' }}>
                        <div className={dotClass} />
                        SYSTEM {statusLabel}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                        Risk Index: <span style={{ color: isBlocked ? 'var(--red)' : isCaution ? 'var(--yellow)' : 'var(--green)', fontWeight: 600 }}>{(riskIndex ?? 0).toFixed(0)}</span>/100
                    </div>
                </motion.div>
            </AnimatePresence>

            {/* Right */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-secondary)' }}>
                    <Wifi size={14} color={backendOnline ? 'var(--green)' : '#64748b'} />
                    <span style={{ color: backendOnline ? 'var(--green)' : '#64748b', fontWeight: 600 }}>
                        {backendOnline ? 'LIVE' : 'SIM'}
                    </span>
                </div>
                <div style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '6px 12px',
                    background: 'rgba(255,255,255,0.04)',
                    borderRadius: 10,
                    border: '1px solid var(--border)',
                    cursor: 'pointer',
                }}>
                    <div style={{
                        width: 28, height: 28, borderRadius: '50%',
                        background: 'linear-gradient(135deg, #27272A, #09090B)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        border: '1px solid var(--border)'
                    }}>
                        <User size={14} color="white" />
                    </div>
                    <div>
                        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>Ops Command</div>
                        <div style={{ fontSize: 10, color: 'var(--text-secondary)' }}>Administrator</div>
                    </div>
                </div>
            </div>
        </nav>
    );
}
