import { useState, useEffect, useRef } from 'react';
import { useNavigate, NavLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { searchAPI } from '../services/api';

export default function Header({ onToggleMobileMenu, sidebarCollapsed, onToggleSidebarCollapse }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const searchRef = useRef(null);

  // Debounced search
  useEffect(() => {
    if (!query.trim() || query.trim().length < 2) {
      setResults(null);
      setLoading(false);
      return;
    }

    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await searchAPI.global(query.trim());
        setResults(res.data);
      } catch (err) {
        console.error('Global search failed:', err);
      } finally {
        setLoading(false);
      }
    }, 280);

    return () => clearTimeout(timer);
  }, [query]);

  // Click outside listener
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (searchRef.current && !searchRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Global keyboard shortcut (Ctrl+K or /)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.ctrlKey && e.key === 'k') || (e.key === '/' && document.activeElement.tagName !== 'INPUT')) {
        e.preventDefault();
        searchRef.current?.querySelector('input')?.focus();
        setIsOpen(true);
      } else if (e.key === 'Escape') {
        setIsOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleSelectQR = (qr) => {
    setIsOpen(false);
    setQuery('');
    navigate(`/inventory?search=${encodeURIComponent(qr.qr_id)}`);
  };

  const handleSelectClient = (clientName) => {
    setIsOpen(false);
    setQuery('');
    navigate(`/clients/${encodeURIComponent(clientName)}`);
  };

  return (
    <header className="app-header">
      <div className="header-left">
        {/* Mobile Hamburger Toggle */}
        <button
          className="mobile-menu-btn"
          onClick={onToggleMobileMenu}
          aria-label="Toggle navigation menu"
        >
          <span className="hamburger-icon">☰</span>
        </button>

        {/* Desktop Sidebar Toggle */}
        <button
          className="sidebar-toggle-btn"
          onClick={onToggleSidebarCollapse}
          title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {sidebarCollapsed ? "⇥" : "⇤"}
        </button>

        <NavLink to="/" className="brand-logo">
          <span className="brand-icon">📱</span>
          <span className="brand-title">QR Enterprise</span>
        </NavLink>
      </div>

      {/* Global Search Bar */}
      <div className="header-search-container" ref={searchRef}>
        <div className="search-input-wrapper">
          <span className="search-icon">🔍</span>
          <input
            type="text"
            className="header-search-input"
            placeholder="Search QR ID (e.g. QR-000061), Token, Client... (Ctrl+K)"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setIsOpen(true);
            }}
            onFocus={() => setIsOpen(true)}
          />
          {query && (
            <button
              className="search-clear-btn"
              onClick={() => {
                setQuery('');
                setResults(null);
              }}
            >
              ✕
            </button>
          )}
          <span className="search-shortcut-badge">⌘K</span>
        </div>

        {/* Search Results Dropdown */}
        {isOpen && query.trim().length >= 2 && (
          <div className="search-dropdown-menu">
            {loading && (
              <div className="search-status-message">
                <span className="spinner-mini" /> Searching inventory & clients...
              </div>
            )}

            {!loading && results && results.total_matches === 0 && (
              <div className="search-status-message empty">
                No QR codes or clients matching <strong>"{query}"</strong>
              </div>
            )}

            {!loading && results && results.total_matches > 0 && (
              <div className="search-results-content">
                {/* QR Codes Group */}
                {results.qr_codes.length > 0 && (
                  <div className="search-result-group">
                    <div className="search-group-header">
                      <span>🏷️ QR Codes ({results.qr_codes.length})</span>
                    </div>
                    {results.qr_codes.map((qr) => (
                      <div
                        key={qr.id}
                        className="search-result-item"
                        onClick={() => handleSelectQR(qr)}
                      >
                        <div className="result-item-main">
                          <span className="qr-id-highlight">{qr.qr_id}</span>
                          <span className={`status-pill ${qr.status.toLowerCase()}`}>
                            {qr.status}
                          </span>
                        </div>
                        <div className="result-item-sub">
                          <span className="qr-biz-name">
                            {qr.current_business_name ? `🏢 ${qr.current_business_name}` : '📦 Unassigned'}
                          </span>
                          <span className="qr-token-dim">Token: {qr.token}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Clients Group */}
                {results.clients.length > 0 && (
                  <div className="search-result-group">
                    <div className="search-group-header">
                      <span>🏢 Clients ({results.clients.length})</span>
                    </div>
                    {results.clients.map((client) => (
                      <div
                        key={client.client_name}
                        className="search-result-item"
                        onClick={() => handleSelectClient(client.client_name)}
                      >
                        <div className="result-item-main">
                          <span className="client-name-highlight">🏢 {client.client_name}</span>
                          <span className="client-badge-qrs">
                            {client.total_qrs} QRs ({client.active_qrs} active)
                          </span>
                        </div>
                        <div className="result-item-sub">
                          <span>Click to open client inventory & scan analytics →</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* User Information & Logout */}
      <div className="header-right">
        <div className="user-profile-badge">
          <span className="user-role-tag">{user?.role?.toUpperCase()}</span>
          <span className="user-display-name">{user?.display_name || user?.username}</span>
        </div>
        <button className="header-logout-btn" onClick={logout} title="Sign out">
          Sign out
        </button>
      </div>
    </header>
  );
}
