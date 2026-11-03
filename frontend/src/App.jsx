import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, NavLink } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import ScanPage from './pages/ScanPage';
import InventoryPage from './pages/InventoryPage';
import ClientsPage from './pages/ClientsPage';
import ClientDetailPage from './pages/ClientDetailPage';
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
  const { user, isAdmin } = useAuth();

  // Desktop sidebar collapse state
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    return localStorage.getItem('qr_sidebar_collapsed') === 'true';
  });

  // Mobile drawer state
  const [mobileOpen, setMobileOpen] = useState(false);

  const toggleSidebarCollapse = () => {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem('qr_sidebar_collapsed', String(next));
      return next;
    });
  };

  const toggleMobileMenu = () => {
    setMobileOpen((prev) => !prev);
  };

  const closeMobileMenu = () => {
    setMobileOpen(false);
  };

  return (
    <div className={`app-shell ${sidebarCollapsed ? 'sidebar-is-collapsed' : 'sidebar-is-expanded'}`}>
      {/* Forced Password Change Security Banner */}
      {user?.must_change_password && (
        <div className="security-banner">
          <span>⚠️ Security Warning: Default credentials in use. Change password immediately!</span>
          <NavLink to="/settings" className="security-banner-btn">
            Go to Settings
          </NavLink>
        </div>
      )}

      {/* Unified Global Header */}
      <Header
        sidebarCollapsed={sidebarCollapsed}
        onToggleSidebarCollapse={toggleSidebarCollapse}
        onToggleMobileMenu={toggleMobileMenu}
      />

      <div className="app-body">
        {/* Collapsible Left Sidebar / Mobile Drawer */}
        <Sidebar
          collapsed={sidebarCollapsed}
          mobileOpen={mobileOpen}
          onCloseMobile={closeMobileMenu}
        />

        {/* Main Content Area */}
        <main className="main-content-viewport">
          <div className="page-content-wrapper">
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/inventory" element={<InventoryPage />} />
              <Route path="/scan" element={<ScanPage />} />
              <Route path="/clients" element={<ClientsPage />} />
              <Route path="/clients/:clientName" element={<ClientDetailPage />} />
              <Route path="/print-studio" element={isAdmin ? <PrintStudioPage /> : <Navigate to="/" replace />} />
              <Route path="/generate" element={isAdmin ? <GeneratePage /> : <Navigate to="/" replace />} />
              <Route path="/audit" element={isAdmin ? <AuditPage /> : <Navigate to="/" replace />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </div>
        </main>
      </div>
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
