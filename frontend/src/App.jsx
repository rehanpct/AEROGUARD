import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { SystemProvider } from './context/SystemContext';
import TopNav from './components/TopNav';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import ZoneMap from './pages/ZoneMap';
import Analytics from './pages/Analytics';
import Telemetry from './pages/Telemetry';
import Logs from './pages/Logs';
import Settings from './pages/Settings';
import './index.css';

export default function App() {
  return (
    <SystemProvider>
      <BrowserRouter>
        <div style={{
          display: 'grid',
          gridTemplateRows: '72px 1fr',
          gridTemplateColumns: '220px 1fr',
          height: '100vh',
          width: '100vw',
          overflow: 'hidden',
          background: 'var(--bg-primary)',
        }}>
          {/* Top Nav — spans full width */}
          <div style={{ gridColumn: '1 / -1' }}>
            <TopNav />
          </div>

          {/* Sidebar */}
          <Sidebar />

          {/* Main content area */}
          <main style={{
            overflowY: 'auto',
            overflowX: 'hidden',
            display: 'flex',
            flexDirection: 'column',
            padding: '24px',
            gap: 0,
          }}>
            <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/telemetry" element={<Telemetry />} />
              <Route path="/zone-map" element={<ZoneMap />} />
              <Route path="/zonemap" element={<ZoneMap />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/logs" element={<Logs />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </SystemProvider>
  );
}
