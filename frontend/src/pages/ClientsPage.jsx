import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { clientAPI } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { formatIST } from '../utils/date';

export default function ClientsPage() {
  const navigate = useNavigate();
  const { isAdmin } = useAuth();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [clients, setClients] = useState([]);
  const [summary, setSummary] = useState(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  // Filters & Sorting
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all'); // 'all' | 'has_active' | 'has_disabled' | 'has_retired'
  const [activityFilter, setActivityFilter] = useState('all'); // 'all' | 'has_scans' | 'never_scanned'
  const [sortBy, setSortBy] = useState('client_name');
  const [sortDir, setSortDir] = useState('asc');

  const fetchClients = async () => {
    setLoading(true);
    setError('');
    try {
      const params = {
        page,
        per_page: 24, // Optimized for 3-4 column grid
        sort_by: sortBy,
        sort_dir: sortDir,
      };
      if (search.trim()) params.search = search.trim();
      if (statusFilter !== 'all') params.status_filter = statusFilter;
      if (activityFilter !== 'all') params.activity_filter = activityFilter;

      const res = await clientAPI.list(params);
      setClients(res.data.items || []);
      setTotal(res.data.total || 0);
      setTotalPages(res.data.total_pages || 1);
      setSummary(res.data.summary || null);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load business management data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchClients();
  }, [page, statusFilter, activityFilter, sortBy, sortDir]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    setPage(1);
    fetchClients();
  };

  const handleResetFilters = () => {
    setSearch('');
    setStatusFilter('all');
    setActivityFilter('all');
    setSortBy('client_name');
    setSortDir('asc');
    setPage(1);
  };

  // Generate a distinct avatar background color and initials for any business name
  const getAvatarProps = (name) => {
    if (!name) return { initials: '🏢', bg: 'var(--primary-600)' };
    const words = name.trim().split(/\s+/);
    const initials = words.length >= 2
      ? (words[0][0] + words[1][0]).toUpperCase()
      : name.slice(0, 2).toUpperCase();

    const colors = [
      '#2563eb', '#0891b2', '#059669', '#d97706', '#7c3aed',
      '#db2777', '#4f46e5', '#0284c7', '#16a34a', '#ea580c'
    ];
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
      hash = name.charCodeAt(i) + ((hash << 5) - hash);
    }
    const bg = colors[Math.abs(hash) % colors.length];
    return { initials, bg };
  };

  const getBusinessStatusBadge = (client) => {
    if (client.active_qr_codes > 0) {
      return <span className="status-pill active">● ACTIVE ({client.active_qr_codes})</span>;
    }
    if (client.disabled_qr_codes > 0) {
      return <span className="status-pill disabled">⏸️ DISABLED</span>;
    }
    if (client.retired_qr_codes > 0) {
      return <span className="status-pill retired">🚫 RETIRED</span>;
    }
    return <span className="status-pill unassigned">HISTORICAL</span>;
  };

  return (
    <div className="businesses-page">
      {/* Page Header */}
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h1 className="page-title">🏢 Business Management</h1>
          <p className="page-subtitle">Card-based workspace for managing businesses and their associated QR inventories</p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button className="btn btn-secondary btn-sm" onClick={fetchClients} disabled={loading}>
            {loading ? 'Refreshing...' : '🔄 Refresh'}
          </button>
        </div>
      </div>

      {error && <div className="login-error" style={{ marginBottom: '16px' }}>{error}</div>}

      {/* Summary Statistics Strip */}
      {summary && (
        <div className="biz-summary-grid">
          <div className="biz-summary-card">
            <span className="summary-icon">🏢</span>
            <div className="summary-info">
              <span className="summary-val">{summary.total_clients}</span>
              <span className="summary-lbl">Total Businesses</span>
            </div>
          </div>
          <div className="biz-summary-card">
            <span className="summary-icon">📦</span>
            <div className="summary-info">
              <span className="summary-val">{summary.total_qr_codes}</span>
              <span className="summary-lbl">Assigned QR Codes</span>
            </div>
          </div>
          <div className="biz-summary-card">
            <span className="summary-icon">🟢</span>
            <div className="summary-info">
              <span className="summary-val">{summary.active_qr_codes}</span>
              <span className="summary-lbl">Active Codes</span>
            </div>
          </div>
          <div className="biz-summary-card">
            <span className="summary-icon">⏸️</span>
            <div className="summary-info">
              <span className="summary-val">{summary.disabled_qr_codes}</span>
              <span className="summary-lbl">Disabled Codes</span>
            </div>
          </div>
          <div className="biz-summary-card">
            <span className="summary-icon">🚫</span>
            <div className="summary-info">
              <span className="summary-val">{summary.retired_qr_codes}</span>
              <span className="summary-lbl">Retired Codes</span>
            </div>
          </div>
          <div className="biz-summary-card">
            <span className="summary-icon">⏳</span>
            <div className="summary-info">
              <span className="summary-val">{summary.qr_codes_without_recent_usage}</span>
              <span className="summary-lbl">No Scans (30d)</span>
            </div>
          </div>
        </div>
      )}

      {/* Modern Filter & Search Toolbar */}
      <div className="biz-toolbar-card">
        <form className="biz-toolbar-form" onSubmit={handleSearchSubmit}>
          {/* Search Box */}
          <div className="biz-search-field">
            <span className="biz-search-icon">🔍</span>
            <input
              type="text"
              placeholder="Search business by name..."
              className="biz-search-input"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {search && (
              <button
                type="button"
                className="clear-btn"
                onClick={() => { setSearch(''); setPage(1); }}
              >
                ✕
              </button>
            )}
          </div>

          {/* Status Filter */}
          <div className="biz-filter-control">
            <label className="biz-filter-label">Status</label>
            <select
              className="form-select form-select-sm"
              value={statusFilter}
              onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
            >
              <option value="all">All Statuses</option>
              <option value="has_active">🟢 Has Active QRs</option>
              <option value="has_disabled">⏸️ Has Disabled QRs</option>
              <option value="has_retired">🚫 Has Retired QRs</option>
            </select>
          </div>

          {/* Activity Filter */}
          <div className="biz-filter-control">
            <label className="biz-filter-label">Scan Activity</label>
            <select
              className="form-select form-select-sm"
              value={activityFilter}
              onChange={(e) => { setActivityFilter(e.target.value); setPage(1); }}
            >
              <option value="all">All Activity</option>
              <option value="has_scans">🎯 Has Scans</option>
              <option value="never_scanned">💤 Never Scanned</option>
            </select>
          </div>

          {/* Sort By */}
          <div className="biz-filter-control">
            <label className="biz-filter-label">Sort By</label>
            <select
              className="form-select form-select-sm"
              value={sortBy}
              onChange={(e) => { setSortBy(e.target.value); setPage(1); }}
            >
              <option value="client_name">Name (Alphabetical)</option>
              <option value="total_qr_codes">Total QR Codes</option>
              <option value="active_qr_codes">Active QR Codes</option>
              <option value="total_scans">Lifetime Scans</option>
              <option value="last_scanned_at">Most Recent Scan</option>
            </select>
          </div>

          {/* Sort Direction */}
          <div className="biz-filter-control" style={{ width: '110px' }}>
            <label className="biz-filter-label">Order</label>
            <select
              className="form-select form-select-sm"
              value={sortDir}
              onChange={(e) => { setSortDir(e.target.value); setPage(1); }}
            >
              <option value="asc">Asc ⬆️</option>
              <option value="desc">Desc ⬇️</option>
            </select>
          </div>

          {/* Actions */}
          <div className="biz-toolbar-actions">
            <button type="submit" className="btn btn-primary btn-sm">
              Filter
            </button>
            {(search || statusFilter !== 'all' || activityFilter !== 'all' || sortBy !== 'client_name') && (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={handleResetFilters}
                title="Reset all filters"
              >
                Reset
              </button>
            )}
          </div>
        </form>
      </div>

      {/* BUSINESS CARDS GRID */}
      {loading ? (
        <div className="loading-spinner">
          <div className="spinner" />
          <p style={{ marginTop: '12px', color: 'var(--text-secondary)' }}>Loading businesses...</p>
        </div>
      ) : clients.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🏢</div>
          <h3>No Businesses Found</h3>
          <p>No business records matched your search or filter criteria.</p>
          <button className="btn btn-secondary" onClick={handleResetFilters}>
            Reset Filters
          </button>
        </div>
      ) : (
        <div className="biz-cards-grid">
          {clients.map((c) => {
            const { initials, bg } = getAvatarProps(c.client_name);
            return (
              <div
                key={c.client_name}
                className="biz-card"
                onClick={() => navigate(`/clients/${encodeURIComponent(c.client_name)}`)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    navigate(`/clients/${encodeURIComponent(c.client_name)}`);
                  }
                }}
              >
                {/* Card Top Row: Logo/Avatar, Business Name & Status */}
                <div className="biz-card-header">
                  <div className="biz-avatar" style={{ backgroundColor: bg }}>
                    {initials}
                  </div>
                  <div className="biz-card-titles">
                    <h3 className="biz-card-name" title={c.client_name}>
                      {c.client_name}
                    </h3>
                    <div className="biz-card-status">
                      {getBusinessStatusBadge(c)}
                    </div>
                  </div>
                </div>

                {/* Card Key Metrics Grid */}
                <div className="biz-card-metrics">
                  <div className="biz-metric-item">
                    <span className="metric-digit">{c.total_qr_codes}</span>
                    <span className="metric-desc">Assigned QRs</span>
                  </div>
                  <div className="biz-metric-item">
                    <span className="metric-digit" style={{ color: 'var(--green-600)' }}>
                      {c.active_qr_codes}
                    </span>
                    <span className="metric-desc">Active</span>
                  </div>
                  <div className="biz-metric-item">
                    <span className="metric-digit" style={{ color: 'var(--amber-600)' }}>
                      {c.disabled_qr_codes}
                    </span>
                    <span className="metric-desc">Disabled</span>
                  </div>
                  <div className="biz-metric-item">
                    <span className="metric-digit" style={{ color: 'var(--primary-600)' }}>
                      {(c.total_scans || 0).toLocaleString()}
                    </span>
                    <span className="metric-desc">Total Scans</span>
                  </div>
                </div>

                {/* Card Timeline & Alert Footer */}
                <div className="biz-card-footer">
                  <div className="biz-footer-meta">
                    <span className="biz-last-scan">
                      🕒 Last scan: {c.last_scanned_at_ist || (c.last_scanned_at ? formatIST(c.last_scanned_at) : 'Never')}
                    </span>
                    <div className="biz-alert-tags">
                      {c.never_scanned_count > 0 && (
                        <span className="alert-tag warning" title={`${c.never_scanned_count} assigned QR code(s) have never been scanned`}>
                          ⚠️ {c.never_scanned_count} Unscanned
                        </span>
                      )}
                      {c.not_scanned_30d_count > 0 && (
                        <span className="alert-tag muted" title={`${c.not_scanned_30d_count} active QR code(s) had no scans in the last 30 days`}>
                          ⏳ {c.not_scanned_30d_count} Inactive (30d)
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="biz-card-action-row" onClick={(e) => e.stopPropagation()}>
                    <button
                      className="btn btn-primary btn-block btn-sm"
                      onClick={() => navigate(`/clients/${encodeURIComponent(c.client_name)}`)}
                      title={`Open dedicated management workspace for ${c.client_name}`}
                    >
                      Manage QR Codes →
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Pagination Footer */}
      {totalPages > 1 && (
        <div className="pagination" style={{ marginTop: '24px' }}>
          <button
            className="pagination-btn"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            ← Previous
          </button>
          <span className="pagination-info">
            Page {page} of {totalPages} ({total} Businesses)
          </span>
          <button
            className="pagination-btn"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
