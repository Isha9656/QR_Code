import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { clientAPI } from '../services/api';
import { useAuth } from '../context/AuthContext';

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
  const [sortBy, setSortBy] = useState('client_name');
  const [sortDir, setSortDir] = useState('asc');

  const fetchClients = async () => {
    setLoading(true);
    setError('');
    try {
      const params = {
        page,
        per_page: 15,
        sort_by: sortBy,
        sort_dir: sortDir,
      };
      if (search.trim()) params.search = search.trim();

      const res = await clientAPI.list(params);
      setClients(res.data.items || []);
      setTotal(res.data.total || 0);
      setTotalPages(res.data.total_pages || 1);
      setSummary(res.data.summary || null);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load client management data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchClients();
  }, [page, sortBy, sortDir]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    setPage(1);
    fetchClients();
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'Never';
    const d = new Date(dateStr);
    return d.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="clients-page">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h1 className="page-title">🏢 Client QR Management</h1>
          <p className="page-subtitle">Track, monitor usage, activate & deactivate QR inventory by business</p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={fetchClients} disabled={loading}>
          {loading ? 'Refreshing...' : '🔄 Refresh'}
        </button>
      </div>

      {error && <div className="login-error" style={{ marginBottom: '16px' }}>{error}</div>}

      {/* Summary Stat Cards */}
      {summary && (
        <div className="stats-grid" style={{ marginBottom: '20px' }}>
          <div className="stat-card primary">
            <div className="stat-icon">🏢</div>
            <div className="stat-value">{summary.total_clients}</div>
            <div className="stat-label">Total Clients</div>
          </div>
          <div className="stat-card info">
            <div className="stat-icon">📱</div>
            <div className="stat-value">{summary.total_qr_codes}</div>
            <div className="stat-label">Assigned QRs</div>
          </div>
          <div className="stat-card success">
            <div className="stat-icon">✅</div>
            <div className="stat-value">{summary.active_qr_codes}</div>
            <div className="stat-label">Active QRs</div>
          </div>
          <div className="stat-card warning">
            <div className="stat-icon">⏸️</div>
            <div className="stat-value">{summary.disabled_qr_codes}</div>
            <div className="stat-label">Disabled QRs</div>
          </div>
          <div className="stat-card danger">
            <div className="stat-icon">🚫</div>
            <div className="stat-value">{summary.retired_qr_codes}</div>
            <div className="stat-label">Retired QRs</div>
          </div>
          <div className="stat-card warning" style={{ borderColor: 'rgba(234, 179, 8, 0.4)' }}>
            <div className="stat-icon">⏳</div>
            <div className="stat-value">{summary.qr_codes_without_recent_usage}</div>
            <div className="stat-label">No Scans in 30 Days</div>
          </div>
        </div>
      )}

      {/* Controls & Search Bar */}
      <div className="card" style={{ marginBottom: '20px' }}>
        <form onSubmit={handleSearchSubmit} style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', alignItems: 'flex-end' }}>
          <div style={{ flex: '1 1 240px' }}>
            <label className="form-label">Search Client Name</label>
            <input
              type="text"
              className="form-input"
              placeholder="Search by client or business name..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          <div style={{ width: '180px' }}>
            <label className="form-label">Sort By</label>
            <select
              className="form-select"
              value={sortBy}
              onChange={(e) => {
                setSortBy(e.target.value);
                setPage(1);
              }}
            >
              <option value="client_name">Client Name</option>
              <option value="total_qr_codes">Total QR Codes</option>
              <option value="active_qr_codes">Active QRs</option>
              <option value="total_scans">Total Scans</option>
              <option value="last_scanned_at">Last Scanned Date</option>
            </select>
          </div>

          <div style={{ width: '130px' }}>
            <label className="form-label">Direction</label>
            <select
              className="form-select"
              value={sortDir}
              onChange={(e) => {
                setSortDir(e.target.value);
                setPage(1);
              }}
            >
              <option value="asc">Ascending ⬆️</option>
              <option value="desc">Descending ⬇️</option>
            </select>
          </div>

          <div>
            <button type="submit" className="btn btn-primary" style={{ height: '42px' }}>
              🔍 Search
            </button>
          </div>
        </form>
      </div>

      {/* Client List Table / Cards */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: '40px', textAlign: 'center' }}>
            <div className="spinner" style={{ margin: '0 auto 12px' }} />
            <p style={{ color: '#94a3b8' }}>Loading client inventory...</p>
          </div>
        ) : clients.length === 0 ? (
          <div style={{ padding: '40px', textAlign: 'center', color: '#94a3b8' }}>
            <div style={{ fontSize: '42px', marginBottom: '12px' }}>🏢</div>
            <h3>No Clients Found</h3>
            <p>No client or business records matched your criteria.</p>
          </div>
        ) : (
          <div className="table-responsive">
            <table className="table" style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: 'rgba(30, 41, 59, 0.7)', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                  <th style={{ padding: '12px 16px', textAlign: 'left' }}>Client / Business</th>
                  <th style={{ padding: '12px 16px', textAlign: 'center' }}>Total QRs</th>
                  <th style={{ padding: '12px 16px', textAlign: 'center' }}>Lifecycle Status</th>
                  <th style={{ padding: '12px 16px', textAlign: 'center' }}>Lifetime Scans</th>
                  <th style={{ padding: '12px 16px', textAlign: 'left' }}>Last Scanned</th>
                  <th style={{ padding: '12px 16px', textAlign: 'center' }}>Usage Alerts</th>
                  <th style={{ padding: '12px 16px', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {clients.map((c) => (
                  <tr
                    key={c.client_name}
                    style={{
                      borderBottom: '1px solid rgba(255,255,255,0.04)',
                      transition: 'background 0.15s ease',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.02)')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                  >
                    <td style={{ padding: '14px 16px' }}>
                      <div style={{ fontWeight: '600', color: '#f8fafc', fontSize: '0.98rem' }}>
                        {c.client_name}
                      </div>
                    </td>
                    <td style={{ padding: '14px 16px', textAlign: 'center', fontWeight: 'bold' }}>
                      {c.total_qr_codes}
                    </td>
                    <td style={{ padding: '14px 16px', textAlign: 'center' }}>
                      <div style={{ display: 'inline-flex', gap: '6px', flexWrap: 'wrap', justifyContent: 'center' }}>
                        <span className="badge badge-active" title="Active QR Codes">
                          ✅ {c.active_qr_codes} Active
                        </span>
                        {c.disabled_qr_codes > 0 && (
                          <span className="badge badge-disabled" title="Disabled QR Codes">
                            ⏸️ {c.disabled_qr_codes} Disabled
                          </span>
                        )}
                        {c.retired_qr_codes > 0 && (
                          <span className="badge badge-retired" title="Retired QR Codes">
                            🚫 {c.retired_qr_codes} Retired
                          </span>
                        )}
                      </div>
                    </td>
                    <td style={{ padding: '14px 16px', textAlign: 'center' }}>
                      <span style={{ fontWeight: '600', color: '#38bdf8' }}>
                        {c.total_scans.toLocaleString()}
                      </span>
                    </td>
                    <td style={{ padding: '14px 16px', color: '#94a3b8', fontSize: '0.88rem' }}>
                      {formatDate(c.last_scanned_at)}
                    </td>
                    <td style={{ padding: '14px 16px', textAlign: 'center' }}>
                      <div style={{ display: 'inline-flex', flexDirection: 'column', gap: '4px', fontSize: '0.78rem' }}>
                        {c.never_scanned_count > 0 && (
                          <span style={{ color: '#fbbf24', background: 'rgba(251, 191, 36, 0.1)', padding: '2px 8px', borderRadius: '4px' }}>
                            {c.never_scanned_count} Never Scanned
                          </span>
                        )}
                        {c.not_scanned_30d_count > 0 && (
                          <span style={{ color: '#f87171', background: 'rgba(248, 113, 113, 0.1)', padding: '2px 8px', borderRadius: '4px' }}>
                            {c.not_scanned_30d_count} Inactive &gt; 30d
                          </span>
                        )}
                        {c.never_scanned_count === 0 && c.not_scanned_30d_count === 0 && (
                          <span style={{ color: '#34d399' }}>Healthy</span>
                        )}
                      </div>
                    </td>
                    <td style={{ padding: '14px 16px', textAlign: 'right' }}>
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={() => navigate(`/clients/${encodeURIComponent(c.client_name)}`)}
                      >
                        Manage QRs ➜
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Footer */}
        {totalPages > 1 && (
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '12px 16px',
              borderTop: '1px solid rgba(255,255,255,0.06)',
            }}
          >
            <span style={{ fontSize: '0.85rem', color: '#94a3b8' }}>
              Showing Page {page} of {totalPages} ({total} total clients)
            </span>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                className="btn btn-secondary btn-sm"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
              >
                ◀ Previous
              </button>
              <button
                className="btn btn-secondary btn-sm"
                disabled={page >= totalPages}
                onClick={() => setPage(page + 1)}
              >
                Next ▶
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
