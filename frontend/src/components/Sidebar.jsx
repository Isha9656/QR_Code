import { NavLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Sidebar({ collapsed, mobileOpen, onCloseMobile }) {
  const { user, isAdmin, logout } = useAuth();

  const handleNavClick = () => {
    if (onCloseMobile) {
      onCloseMobile();
    }
  };

  const navGroups = [
    {
      groupTitle: 'OVERVIEW',
      items: [
        { to: '/', label: 'Dashboard', icon: '📊', exact: true, adminOnly: false },
      ],
    },
    {
      groupTitle: 'QR MANAGEMENT',
      items: [
        { to: '/inventory', label: 'QR Inventory', icon: '📋', adminOnly: false },
        { to: '/scan', label: 'Assign QR Codes', icon: '📷', adminOnly: false },
        { to: '/clients', label: 'Client Management', icon: '🏢', adminOnly: false },
        { to: '/generate', label: 'Batch Generate', icon: '⚡', adminOnly: true },
      ],
    },
    {
      groupTitle: 'OPERATIONS',
      items: [
        { to: '/print-studio', label: 'Printing Studio', icon: '🖨️', adminOnly: true },
        { to: '/audit', label: 'QR Activity & Audit', icon: '🛡️', adminOnly: true },
      ],
    },
    {
      groupTitle: 'SYSTEM MANAGEMENT',
      items: [
        { to: '/settings', label: 'Settings & Security', icon: '⚙️', adminOnly: false },
      ],
    },
  ];

  return (
    <>
      {/* Mobile Drawer Backdrop */}
      {mobileOpen && (
        <div
          className="sidebar-backdrop"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      )}

      <aside className={`app-sidebar ${collapsed ? 'collapsed' : ''} ${mobileOpen ? 'mobile-open' : ''}`}>
        {/* Sidebar Brand Header */}
        <div className="sidebar-brand">
          <span className="sidebar-brand-icon">⚡</span>
          {!collapsed && (
            <div className="sidebar-brand-text">
              <span className="brand-main">QR SYSTEM</span>
              <span className="brand-sub">ENTERPRISE ADMIN</span>
            </div>
          )}
          {mobileOpen && (
            <button className="sidebar-close-btn" onClick={onCloseMobile} aria-label="Close menu">
              ✕
            </button>
          )}
        </div>

        {/* Sidebar Navigation Links Grouped */}
        <div className="sidebar-nav-container">
          {navGroups.map((group) => {
            // Filter out items user doesn't have permission for
            const visibleItems = group.items.filter((item) => !item.adminOnly || isAdmin);
            if (visibleItems.length === 0) return null;

            return (
              <div key={group.groupTitle} className="sidebar-group">
                {!collapsed && (
                  <div className="sidebar-group-title">{group.groupTitle}</div>
                )}
                <ul className="sidebar-nav-list">
                  {visibleItems.map((item) => (
                    <li key={item.to} className="sidebar-nav-item">
                      <NavLink
                        to={item.to}
                        end={item.exact}
                        onClick={handleNavClick}
                        className={({ isActive }) =>
                          `sidebar-link ${isActive ? 'active' : ''}`
                        }
                        title={collapsed ? item.label : undefined}
                      >
                        <span className="sidebar-icon">{item.icon}</span>
                        {!collapsed && <span className="sidebar-label">{item.label}</span>}
                      </NavLink>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>

        {/* Sidebar Footer / User Profile */}
        <div className="sidebar-footer">
          <div className="sidebar-user-info" title={collapsed ? `${user?.display_name || user?.username} (${user?.role})` : undefined}>
            <div className="sidebar-user-avatar">
              {(user?.display_name || user?.username || 'U')[0].toUpperCase()}
            </div>
            {!collapsed && (
              <div className="sidebar-user-details">
                <span className="sidebar-username">{user?.display_name || user?.username}</span>
                <span className={`sidebar-role-pill ${user?.role === 'admin' ? 'admin' : 'operator'}`}>
                  {user?.role?.toUpperCase()}
                </span>
              </div>
            )}
          </div>
          <button
            className="sidebar-logout-btn"
            onClick={logout}
            title={collapsed ? "Sign Out" : undefined}
          >
            <span className="logout-icon">🚪</span>
            {!collapsed && <span className="logout-text">Sign Out</span>}
          </button>
        </div>
      </aside>
    </>
  );
}
