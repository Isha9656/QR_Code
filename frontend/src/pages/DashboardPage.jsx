import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { analyticsAPI, clientAPI, adminAPI } from '../services/api';

export default function DashboardPage() {
  const { isAdmin } = useAuth();
  const navigate = useNavigate();

  const [stats, setStats] = useState(null);
  const [clientSummary, setClientSummary] = useState(null);
  const [topClients, setTopClients] = useState([]);
  const [recentActivity, setRecentActivity] = useState([]);
  const [loading, setLoading] = useState(true);
  const [backupStatus, setBackupStatus] = useState(null);
  const [isBackingUp, setIsBackingUp] = useState(false);

  useEffect(() => {
    loadDashboardData();
  }, [isAdmin]);

  const loadDashboardData = async () => {
    setLoading(true);
    try {
      const promises = [
        analyticsAPI.overview(),
        clientAPI.getOverview().catch(() => ({ data: null })),
        clientAPI.list({ per_page: 5, sort_by: 'active_qr_codes', sort_dir: 'desc' }).catch(() => ({ data: { items: [] } })),
      ];

      if (isAdmin) {
        promises.push(adminAPI.getAuditLogs({ per_page: 6 }).catch(() => ({ data: { items: [] } })));
      }

      const results = await Promise.all(promises);
      setStats(results[0].data);
      if (results[1]?.data) setClientSummary(results[1].data);
      if (results[2]?.data?.items) setTopClients(results[2].data.items);
      if (isAdmin && results[3]?.data?.items) setRecentActivity(results[3].data.items);
    } catch (err) {
      console.error('Failed to load dashboard data:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateBackup = async () => {
    setIsBackingUp(true);
    setBackupStatus(null);
    try {
      const res = await adminAPI.createBackup();
      setBackupStatus({
        type: 'success',
        text: `Live database backup created: ${res.data.backup?.filename || 'Backup successful'}`,
      });
    } catch (err) {
      setBackupStatus({
        type: 'error',
        text: `Backup failed: ${err.response?.data?.detail || err.message}`,
      });
    } finally {
      setIsBackingUp(false);
    }
  };

  if (loading) {
    return (
      <div className="loading-spinner">
        <div className="spinner" />
      </div>
    );
  }

  // Calculate percentage distribution for lifecycle bar
  const total = stats?.total_qr_codes || 0;
  const activePct = total > 0 ? ((stats?.active || 0) / total) * 100 : 0;
  const unassignedPct = total > 0 ? ((stats?.unassigned || 0) / total) * 100 : 0;
  const disabledPct = total > 0 ? ((stats?.disabled || 0) / total) * 100 : 0;
  const retiredPct = total > 0 ? ((stats?.retired || 0) / total) * 100 : 0;

  return (
    <div className="dashboard-container">
      {/* Page Header */}
      <div className="page-header" style={{ marginBottom: '20px' }}>
        <h1 className="page-title">Operational Control Center</h1>
        <p className="page-subtitle">Real-time QR lifecycle status, scan metrics, and client attribution</p>
      </div>

      {/* Backup Notification Toast */}
      {backupStatus && (
        <div
          className={`alert-banner ${backupStatus.type === 'success' ? 'alert-success' : 'alert-danger'}`}
          style={{ marginBottom: '16px' }}
        >
          <span>{backupStatus.type === 'success' ? '✅' : '⚠️'} {backupStatus.text}</span>
          <button className="alert-close" onClick={() => setBackupStatus(null)}>✕</button>
        </div>
      )}

      {/* QUICK ACTIONS BAR */}
      <div className="dashboard-section">
        <div className="section-header">
          <h2 className="section-title">⚡ Quick Actions</h2>
          <span className="section-hint">High-frequency management shortcuts</span>
        </div>
        <div className="quick-actions-grid">
          <button
            className="quick-action-card qa-primary"
            onClick={() => navigate('/scan')}
            id="qa-assign-qr"
          >
            <div className="qa-icon">📷</div>
            <div className="qa-text">
              <span className="qa-title">Assign QR Code</span>
              <span className="qa-desc">Scan or enter ID to link to client</span>
            </div>
          </button>

          <button
            className="quick-action-card qa-info"
            onClick={() => navigate('/inventory')}
            id="qa-find-qr"
          >
            <div className="qa-icon">🔍</div>
            <div className="qa-text">
              <span className="qa-title">Find QR Code</span>
              <span className="qa-desc">Search full QR token and ID registry</span>
            </div>
          </button>

          <button
            className="quick-action-card qa-accent"
            onClick={() => navigate('/clients')}
            id="qa-view-clients"
          >
            <div className="qa-icon">🏢</div>
            <div className="qa-text">
              <span className="qa-title">View Clients</span>
              <span className="qa-desc">Manage accounts & QR activations</span>
            </div>
          </button>

          {isAdmin && (
            <button
              className="quick-action-card qa-warning"
              onClick={() => navigate('/print-studio')}
              id="qa-printing-studio"
            >
              <div className="qa-icon">🖨️</div>
              <div className="qa-text">
                <span className="qa-title">Printing Studio</span>
                <span className="qa-desc">Bulk printable sheets & exports</span>
              </div>
            </button>
          )}

          {isAdmin && (
            <button
              className="quick-action-card qa-secondary"
              onClick={() => navigate('/audit')}
              id="qa-view-analytics"
            >
              <div className="qa-icon">🛡️</div>
              <div className="qa-text">
                <span className="qa-title">Audit & Activity</span>
                <span className="qa-desc">View immutable security trail</span>
              </div>
            </button>
          )}

          {isAdmin && (
            <button
              className="quick-action-card qa-success"
              onClick={handleCreateBackup}
              disabled={isBackingUp}
              id="qa-create-backup"
            >
              <div className="qa-icon">💾</div>
              <div className="qa-text">
                <span className="qa-title">{isBackingUp ? 'Backing up...' : 'Create Backup'}</span>
                <span className="qa-desc">Live SQLite database snapshot</span>
              </div>
            </button>
          )}
        </div>
      </div>

      {/* KEY METRICS STATS GRID */}
      {stats && (
        <div className="dashboard-section">
          <div className="section-header">
            <h2 className="section-title">📊 Key Inventory & Usage Metrics</h2>
          </div>
          <div className="stats-grid">
            <div className="stat-card primary">
              <div className="stat-icon">📦</div>
              <div className="stat-value">{stats.total_qr_codes}</div>
              <div className="stat-label">Total QR Registry</div>
            </div>

            <div className="stat-card warning">
              <div className="stat-icon">📥</div>
              <div className="stat-value">{stats.unassigned}</div>
              <div className="stat-label">Unassigned Available</div>
            </div>

            <div className="stat-card success">
              <div className="stat-icon">✅</div>
              <div className="stat-value">{stats.active}</div>
              <div className="stat-label">Active (Resolving)</div>
            </div>

            <div className="stat-card info">
              <div className="stat-icon">⏸️</div>
              <div className="stat-value">{stats.disabled}</div>
              <div className="stat-label">Disabled (Assigned)</div>
            </div>

            <div className="stat-card danger">
              <div className="stat-icon">🚫</div>
              <div className="stat-value">{stats.retired}</div>
              <div className="stat-label">Retired (Permanent)</div>
            </div>

            <div className="stat-card accent">
              <div className="stat-icon">🏢</div>
              <div className="stat-value">{clientSummary?.total_clients ?? topClients.length}</div>
              <div className="stat-label">Registered Clients</div>
            </div>

            <div className="stat-card purple">
              <div className="stat-icon">📈</div>
              <div className="stat-value">{stats.total_scans}</div>
              <div className="stat-label">Total Public Scans</div>
            </div>
          </div>
        </div>
      )}

      {/* LIFECYCLE DISTRIBUTION BAR */}
      {stats && total > 0 && (
        <div className="dashboard-section">
          <div className="card">
            <h3 className="card-title" style={{ marginBottom: '12px' }}>
              🔄 QR Lifecycle Distribution
            </h3>
            <div className="lifecycle-progress-bar">
              {activePct > 0 && (
                <div
                  className="bar-segment bar-active"
                  style={{ width: `${activePct}%` }}
                  title={`Active: ${stats.active} (${activePct.toFixed(1)}%)`}
                />
              )}
              {unassignedPct > 0 && (
                <div
                  className="bar-segment bar-unassigned"
                  style={{ width: `${unassignedPct}%` }}
                  title={`Unassigned: ${stats.unassigned} (${unassignedPct.toFixed(1)}%)`}
                />
              )}
              {disabledPct > 0 && (
                <div
                  className="bar-segment bar-disabled"
                  style={{ width: `${disabledPct}%` }}
                  title={`Disabled: ${stats.disabled} (${disabledPct.toFixed(1)}%)`}
                />
              )}
              {retiredPct > 0 && (
                <div
                  className="bar-segment bar-retired"
                  style={{ width: `${retiredPct}%` }}
                  title={`Retired: ${stats.retired} (${retiredPct.toFixed(1)}%)`}
                />
              )}
            </div>
            <div className="lifecycle-legend">
              <div className="legend-item">
                <span className="legend-dot dot-active" />
                <span>Active ({stats.active})</span>
              </div>
              <div className="legend-item">
                <span className="legend-dot dot-unassigned" />
                <span>Unassigned ({stats.unassigned})</span>
              </div>
              <div className="legend-item">
                <span className="legend-dot dot-disabled" />
                <span>Disabled ({stats.disabled})</span>
              </div>
              <div className="legend-item">
                <span className="legend-dot dot-retired" />
                <span>Retired ({stats.retired})</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TWO COLUMN GRID: TOP CLIENTS & RECENT ACTIVITY */}
      <div className="dashboard-columns-grid">
        {/* Top Clients Overview */}
        <div className="dashboard-column">
          <div className="card h-full">
            <div className="card-header-flex">
              <h3 className="card-title">🏢 Client Inventory & Usage</h3>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => navigate('/clients')}
              >
                View All Clients →
              </button>
            </div>

            {topClients.length === 0 ? (
              <div className="empty-state-card">
                <span className="empty-icon">🏢</span>
                <p>No active clients registered yet.</p>
              </div>
            ) : (
              <div className="dashboard-table-container">
                <table className="dashboard-mini-table">
                  <thead>
                    <tr>
                      <th>Client Name</th>
                      <th style={{ textAlign: 'center' }}>Total QRs</th>
                      <th style={{ textAlign: 'center' }}>Active</th>
                      <th style={{ textAlign: 'right' }}>Scans</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topClients.map((c) => (
                      <tr
                        key={c.client_name}
                        onClick={() => navigate(`/clients/${encodeURIComponent(c.client_name)}`)}
                        className="clickable-row"
                      >
                        <td className="fw-semibold">
                          🏢 {c.client_name}
                        </td>
                        <td style={{ textAlign: 'center' }}>{c.total_qr_codes}</td>
                        <td style={{ textAlign: 'center' }}>
                          <span className="badge badge-active">{c.active_qr_codes}</span>
                        </td>
                        <td style={{ textAlign: 'right' }} className="fw-mono">
                          {c.total_scans}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Recent Operational Activity */}
        {isAdmin && (
          <div className="dashboard-column">
            <div className="card h-full">
              <div className="card-header-flex">
                <h3 className="card-title">🛡️ Recent Security & QR Activity</h3>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => navigate('/audit')}
                >
                  Full Audit Log →
                </button>
              </div>

              {recentActivity.length === 0 ? (
                <div className="empty-state-card">
                  <span className="empty-icon">🛡️</span>
                  <p>No activity logs recorded yet.</p>
                </div>
              ) : (
                <div className="activity-feed">
                  {recentActivity.map((log) => (
                    <div key={log.id} className="activity-feed-item">
                      <div className="activity-indicator">
                        <span className={`status-dot ${log.status === 'failed' ? 'dot-failed' : 'dot-success'}`} />
                      </div>
                      <div className="activity-info">
                        <div className="activity-title-row">
                          <span className="activity-action">{log.action}</span>
                          <span className="activity-time">
                            {new Date(log.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </span>
                        </div>
                        <div className="activity-details">
                          <span>User: <strong>{log.username || 'System'}</strong></span>
                          {log.entity_type && (
                            <span> • {log.entity_type} #{log.entity_id}</span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* SCAN ACTIVITY VELOCITY */}
      {stats && (
        <div className="dashboard-section" style={{ marginTop: '20px' }}>
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">📈 Public Scan Velocity</h3>
            </div>
            <div className="stats-grid" style={{ marginBottom: 0 }}>
              <div className="stat-card primary">
                <div className="stat-value">{stats.total_scans}</div>
                <div className="stat-label">Lifetime Scans</div>
              </div>
              <div className="stat-card success">
                <div className="stat-value">{stats.scans_today}</div>
                <div className="stat-label">Scans Today</div>
              </div>
              <div className="stat-card info">
                <div className="stat-value">{stats.scans_this_week}</div>
                <div className="stat-label">This Week</div>
              </div>
              <div className="stat-card warning">
                <div className="stat-value">{stats.scans_this_month}</div>
                <div className="stat-label">This Month</div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
