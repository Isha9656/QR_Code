import { useState, useEffect } from 'react';
import { adminAPI } from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function AuditPage() {
  const { isAdmin } = useAuth();
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Filters
  const [actionFilter, setActionFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  // Active detail modal
  const [selectedLog, setSelectedLog] = useState(null);

  const fetchLogs = async () => {
    setLoading(true);
    setError('');
    try {
      const params = {
        page,
        per_page: 25,
      };
      if (actionFilter) params.action = actionFilter;
      if (statusFilter) params.status = statusFilter;

      const res = await adminAPI.getAuditLogs(params);
      setLogs(res.data.items || []);
      setTotal(res.data.total || 0);
      setTotalPages(res.data.total_pages || 1);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load audit logs');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAdmin) {
      fetchLogs();
    }
  }, [page, actionFilter, statusFilter, isAdmin]);

  const filteredLogs = logs.filter((log) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    const userMatch = log.username?.toLowerCase().includes(q);
    const actionMatch = log.action?.toLowerCase().includes(q);
    const detailsMatch = log.details?.toLowerCase().includes(q);
    const idMatch = log.entity_id?.toString().includes(q);
    return userMatch || actionMatch || detailsMatch || idMatch;
  });

  const getActionBadgeClass = (action, status) => {
    if (status === 'failed') return 'badge badge-retired';
    if (action.includes('login')) return 'badge badge-active';
    if (action === 'assign' || action === 'reassign') return 'badge badge-active';
    if (action === 'deactivate') return 'badge badge-disabled';
    if (action === 'retire') return 'badge badge-retired';
    return 'badge badge-unassigned';
  };

  return (
    <div className="audit-page">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 className="page-title">🛡️ Security Audit Trail</h1>
          <p className="page-subtitle">Immutable append-only activity & security event log</p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={fetchLogs} disabled={loading}>
          {loading ? 'Refreshing...' : '🔄 Refresh'}
        </button>
      </div>

      {error && <div className="login-error" style={{ marginBottom: '16px' }}>{error}</div>}

      {/* Filters Bar */}
      <div className="card" style={{ marginBottom: '16px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '10px' }}>
          <div>
            <label className="form-label">Action Filter</label>
            <select
              className="form-select"
              value={actionFilter}
              onChange={(e) => {
                setActionFilter(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All Actions</option>
              <option value="login">Login (Success)</option>
              <option value="login_failed">Login (Failed)</option>
              <option value="password_change">Password Change</option>
              <option value="assign">QR Assign</option>
              <option value="reassign">QR Reassign</option>
              <option value="deactivate">QR Deactivate (Disable)</option>
              <option value="reactivate">QR Reactivate</option>
              <option value="retire">QR Retire</option>
              <option value="bulk_generate">Bulk Generate</option>
              <option value="create_backup">Create Backup</option>
              <option value="create_user">Create User</option>
            </select>
          </div>

          <div>
            <label className="form-label">Status</label>
            <select
              className="form-select"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All Statuses</option>
              <option value="success">Success</option>
              <option value="failed">Failed / Blocked</option>
            </select>
          </div>

          <div>
            <label className="form-label">Search</label>
            <input
              type="text"
              className="form-input"
              placeholder="Search user, action, ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </div>
      </div>

      {/* Logs Table / Cards */}
      <div className="card" style={{ padding: '0', overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Showing {filteredLogs.length} of {total} audit records
          </span>
          <span className="badge badge-unassigned">Page {page} of {totalPages}</span>
        </div>

        {loading ? (
          <div style={{ padding: '32px', textAlign: 'center' }}>
            <div className="spinner" style={{ margin: '0 auto 12px auto' }} />
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Loading security logs...</p>
          </div>
        ) : filteredLogs.length === 0 ? (
          <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
            No audit records match the selected filters.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ background: 'var(--bg-secondary)', borderBottom: '1px solid var(--border-color)', color: 'var(--text-muted)' }}>
                  <th style={{ padding: '10px 14px' }}>Timestamp</th>
                  <th style={{ padding: '10px 14px' }}>Action</th>
                  <th style={{ padding: '10px 14px' }}>User</th>
                  <th style={{ padding: '10px 14px' }}>Status</th>
                  <th style={{ padding: '10px 14px' }}>Entity</th>
                  <th style={{ padding: '10px 14px' }}>IP</th>
                  <th style={{ padding: '10px 14px', textAlign: 'right' }}>Details</th>
                </tr>
              </thead>
              <tbody>
                {filteredLogs.map((log) => (
                  <tr
                    key={log.id}
                    style={{
                      borderBottom: '1px solid var(--border-color)',
                      transition: 'background 0.15s ease',
                    }}
                  >
                    <td style={{ padding: '10px 14px', whiteSpace: 'nowrap', color: 'var(--text-secondary)' }}>
                      {new Date(log.created_at).toLocaleString()}
                    </td>
                    <td style={{ padding: '10px 14px' }}>
                      <span className={getActionBadgeClass(log.action, log.status)}>
                        {log.action}
                      </span>
                    </td>
                    <td style={{ padding: '10px 14px', fontWeight: '500' }}>
                      {log.username || (log.user_id ? `User #${log.user_id}` : 'System')}
                    </td>
                    <td style={{ padding: '10px 14px' }}>
                      <span style={{
                        display: 'inline-block',
                        padding: '2px 6px',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                        fontWeight: '600',
                        background: log.status === 'failed' ? '#fee2e2' : '#dcfce7',
                        color: log.status === 'failed' ? '#dc2626' : '#16a34a',
                      }}>
                        {log.status?.toUpperCase() || 'SUCCESS'}
                      </span>
                    </td>
                    <td style={{ padding: '10px 14px', color: 'var(--text-secondary)' }}>
                      {log.entity_type} {log.entity_id ? `#${log.entity_id}` : ''}
                    </td>
                    <td style={{ padding: '10px 14px', color: 'var(--text-muted)', fontFamily: 'monospace' }}>
                      {log.ip_address || '—'}
                    </td>
                    <td style={{ padding: '10px 14px', textAlign: 'right' }}>
                      <button
                        className="btn btn-secondary btn-sm"
                        style={{ padding: '3px 8px', fontSize: '0.75rem' }}
                        onClick={() => setSelectedLog(log)}
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Controls */}
        {totalPages > 1 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', background: 'var(--bg-secondary)', borderTop: '1px solid var(--border-color)' }}>
            <button
              className="btn btn-secondary btn-sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              ◀ Previous
            </button>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              Page {page} of {totalPages}
            </span>
            <button
              className="btn btn-secondary btn-sm"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Next ▶
            </button>
          </div>
        )}
      </div>

      {/* Detail Modal */}
      {selectedLog && (
        <div className="modal-overlay" onClick={() => setSelectedLog(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '500px' }}>
            <div className="modal-header">
              <h3 className="modal-title">Log Record #{selectedLog.id}</h3>
              <button className="modal-close" onClick={() => setSelectedLog(null)}>✕</button>
            </div>
            <div style={{ marginTop: '14px', display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '0.85rem' }}>
              <div className="detail-row">
                <span className="detail-label">Action</span>
                <span className="detail-value font-mono">{selectedLog.action}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Status</span>
                <span className="detail-value">{selectedLog.status}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">User</span>
                <span className="detail-value">{selectedLog.username || `ID ${selectedLog.user_id}` || 'System'}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Timestamp</span>
                <span className="detail-value">{new Date(selectedLog.created_at).toLocaleString()}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">IP Address</span>
                <span className="detail-value font-mono">{selectedLog.ip_address || '—'}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Entity</span>
                <span className="detail-value">{selectedLog.entity_type} {selectedLog.entity_id ? `(${selectedLog.entity_id})` : ''}</span>
              </div>

              <div style={{ marginTop: '10px' }}>
                <span className="detail-label" style={{ display: 'block', marginBottom: '6px' }}>Payload Details:</span>
                <pre style={{
                  background: 'var(--bg-secondary)',
                  padding: '10px',
                  borderRadius: '6px',
                  border: '1px solid var(--border-color)',
                  fontSize: '0.8rem',
                  overflowX: 'auto',
                  maxHeight: '180px',
                  color: 'var(--text-primary)',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-all',
                }}>
                  {selectedLog.details ? JSON.stringify(JSON.parse(selectedLog.details), null, 2) : 'No additional details logged.'}
                </pre>
              </div>
            </div>
            <div style={{ marginTop: '16px', display: 'flex', justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={() => setSelectedLog(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
