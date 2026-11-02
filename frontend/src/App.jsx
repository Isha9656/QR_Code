import { BrowserRouter, Routes, Route, Navigate, NavLink, useNavigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import ScanPage from './pages/ScanPage';
import InventoryPage from './pages/InventoryPage';
import GeneratePage from './pages/GeneratePage';
import SettingsPage from './pages/SettingsPage';
import PrintStudioPage from './pages/PrintStudioPage';
import AuditPage from './pages/AuditPage';

function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth();
  if (loading) {
    return (
      <div className="loading-spinner" style={{ minHeight: '100vh' }}>
        <div className="spinner" />
      </div>
    );
  }
  return isAuthenticated ? children : <Navigate to="/login" replace />;
}

function AppLayout() {
  const { user, isAdmin, logout } = useAuth();

  return (
    <div className="app-layout">
      {/* Forced Password Change Security Banner */}
      {user?.must_change_password && (
        <div style={{
          background: '#dc2626',
          color: '#ffffff',
          padding: '8px 16px',
          textAlign: 'center',
          fontSize: '0.82rem',
          fontWeight: '600',
          position: 'sticky',
          top: 0,
          zIndex: 1000,
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          gap: '12px',
        }}>
          <span>⚠️ Security Warning: Default credentials in use. Change password immediately!</span>
          <NavLink
            to="/settings"
            style={{
              background: '#ffffff',
              color: '#dc2626',
              padding: '3px 8px',
              borderRadius: '4px',
              textDecoration: 'none',
              fontSize: '0.75rem',
            }}
          >
            Go to Settings
          </NavLink>
        </div>
      )}

      {/* Top Bar */}
      <header className="top-bar">
        <h1>📱 QR Manager</h1>
        <div className="user-info">
          <span className="user-badge">{user?.role?.toUpperCase()}</span>
          <button className="logout-btn" onClick={logout}>Logout</button>
        </div>
      </header>

      {/* Page Content */}
      <main className="page-container">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/scan" element={<ScanPage />} />
          <Route path="/inventory" element={<InventoryPage />} />
          <Route path="/print-studio" element={isAdmin ? <PrintStudioPage /> : <Navigate to="/" replace />} />
          <Route path="/generate" element={isAdmin ? <GeneratePage /> : <Navigate to="/" replace />} />
          <Route path="/audit" element={isAdmin ? <AuditPage /> : <Navigate to="/" replace />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      {/* Bottom Navigation */}
      <nav className="bottom-nav">
        <NavLink to="/" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} end>
          <span className="nav-icon">📊</span>
          <span>Dashboard</span>
        </NavLink>
        <NavLink to="/scan" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <span className="nav-icon">📷</span>
          <span>Scan</span>
        </NavLink>
        <NavLink to="/inventory" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <span className="nav-icon">📋</span>
          <span>Inventory</span>
        </NavLink>
        {isAdmin && (
          <NavLink to="/print-studio" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span className="nav-icon">🖨️</span>
            <span>Studio</span>
          </NavLink>
        )}
        {isAdmin && (
          <NavLink to="/audit" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span className="nav-icon">🛡️</span>
            <span>Audit</span>
          </NavLink>
        )}
        {isAdmin && (
          <NavLink to="/generate" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span className="nav-icon">⚡</span>
            <span>Generate</span>
          </NavLink>
        )}
        <NavLink to="/settings" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <span className="nav-icon">⚙️</span>
          <span>Settings</span>
        </NavLink>
      </nav>
    </div>
  );
}

function LoginWrapper() {
  const { isAuthenticated } = useAuth();
  return isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginWrapper />} />
          <Route
            path="/*"
            element={
              <ProtectedRoute>
                <AppLayout />
              </ProtectedRoute>
            }
          />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
