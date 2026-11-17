import { useState, useEffect } from 'react';
import { qrAPI, printAPI } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { formatIST } from '../utils/date';

export default function QRDetailDrawer({ qr, onClose, onUpdated }) {
  const { isAdmin } = useAuth();

  const [activeTab, setActiveTab] = useState('overview'); // 'overview' | 'analytics' | 'history'
  const [tokenRevealed, setTokenRevealed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [analytics, setAnalytics] = useState(null);
  const [history, setHistory] = useState(null);
  const [previewBlobUrl, setPreviewBlobUrl] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [toast, setToast] = useState(null);

  // Reassign / Destination Modal
  const [showReassign, setShowReassign] = useState(false);
  const [reassignForm, setReassignForm] = useState({
    business_name: qr?.current_business_name || '',
    destination_url: qr?.current_destination || '',
    notes: '',
  });

  const qrId = qr?.qr_id || (typeof qr === 'string' ? qr : null);
  const numericId = qr?.id;

  // Escape key and background scroll locking
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && !showReassign) {
        onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    const origOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = origOverflow;
      if (previewBlobUrl) {
        URL.revokeObjectURL(previewBlobUrl);
      }
    };
  }, [onClose, showReassign, previewBlobUrl]);

  // Load preview image, analytics, and history
  useEffect(() => {
    if (!qrId) return;

    let isMounted = true;
    setLoading(true);

    const loadData = async () => {
      // 1. Fetch QR analytics
      try {
        const aRes = await qrAPI.getAnalytics(qrId);
        if (isMounted) setAnalytics(aRes.data);
      } catch (err) {
        console.error('Failed to load QR analytics', err);
      }

      // 2. Fetch assignment history
      try {
        const hRes = await qrAPI.getHistory(qrId);
        if (isMounted) setHistory(hRes.data);
      } catch (err) {
        console.error('Failed to load QR history', err);
      }

      // 3. Fetch PNG Sticker preview
      try {
        const pRes = await printAPI.exportPNG(numericId || qrId, 240);
        if (isMounted) {
          setPreviewBlobUrl(URL.createObjectURL(pRes.data));
        }
      } catch (err) {
        // Fallback handled via direct img src with auth token param
      }

      if (isMounted) setLoading(false);
    };

    loadData();

    return () => {
      isMounted = false;
    };
  }, [qrId, numericId]);

  const showToast = (type, message) => {
    setToast({ type, message });
    setTimeout(() => setToast(null), 3500);
  };

  const handleDownloadPNG = async () => {
    try {
      const res = await printAPI.exportPNG(numericId || qrId, 400);
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${qrId}_sticker.png`;
      a.click();
      URL.revokeObjectURL(url);
      showToast('success', 'Sticker PNG downloaded');
    } catch (err) {
      showToast('error', 'Failed to download PNG');
    }
  };

  const handleDeactivate = async () => {
    if (!confirm(`Are you sure you want to deactivate ${qrId}? The destination will be preserved.`)) return;
    setActionLoading(true);
    try {
      await qrAPI.deactivate(qrId);
      showToast('success', `${qrId} deactivated successfully`);
      if (onUpdated) onUpdated();
    } catch (err) {
      showToast('error', err.response?.data?.detail || 'Deactivation failed');
    } finally {
      setActionLoading(false);
    }
  };

  const handleReactivate = async () => {
    setActionLoading(true);
    try {
      await qrAPI.reactivate(qrId);
      showToast('success', `${qrId} reactivated successfully`);
      if (onUpdated) onUpdated();
    } catch (err) {
      showToast('error', err.response?.data?.detail || 'Reactivation failed');
    } finally {
      setActionLoading(false);
    }
  };

  const handleReassignSubmit = async (e) => {
    e.preventDefault();
    setActionLoading(true);
    try {
      await qrAPI.reassign(qrId, {
        business_name: reassignForm.business_name.trim(),
        destination_url: reassignForm.destination_url.trim(),
        notes: reassignForm.notes ? reassignForm.notes.trim() : null,
        confirm_reassignment: true,
      });
      showToast('success', `${qrId} updated successfully`);
      setShowReassign(false);
      if (onUpdated) onUpdated();
    } catch (err) {
      showToast('error', err.response?.data?.detail || 'Update failed');
    } finally {
      setActionLoading(false);
    }
  };

  const copyToClipboard = (text, label) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    showToast('success', `${label} copied to clipboard!`);
  };

  const currentStatus = (analytics?.status || qr?.status || 'unassigned').toLowerCase();

  return (
    <div className="drawer-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div className="drawer-container" onClick={(e) => e.stopPropagation()}>
        {/* Toast notification */}
        {toast && (
          <div className={`drawer-toast toast-${toast.type}`}>
            {toast.type === 'success' ? '✅' : '⚠️'} {toast.message}
          </div>
        )}

        {/* Drawer Header */}
        <div className="drawer-header">
          <div className="drawer-header-left">
            <div className="drawer-title-group">
              <h2 className="drawer-qr-id">{qrId}</h2>
              <span className={`status-pill ${currentStatus}`}>
                {currentStatus.toUpperCase()}
              </span>
            </div>
            <div className="drawer-business-subtitle">
              🏢 {analytics?.current_business_name || qr?.current_business_name || 'Unassigned Inventory'}
            </div>
          </div>
          <button className="drawer-close-btn" onClick={onClose} title="Close (Esc)" aria-label="Close">
            ✕
          </button>
        </div>

        {/* Drawer Tabs */}
        <div className="drawer-tabs">
          <button
            className={`drawer-tab-btn ${activeTab === 'overview' ? 'active' : ''}`}
            onClick={() => setActiveTab('overview')}
          >
            📋 Overview & Details
          </button>
          <button
            className={`drawer-tab-btn ${activeTab === 'analytics' ? 'active' : ''}`}
            onClick={() => setActiveTab('analytics')}
          >
            📈 Scan Analytics ({analytics?.total_scans ?? qr?.total_scans ?? 0})
          </button>
          <button
            className={`drawer-tab-btn ${activeTab === 'history' ? 'active' : ''}`}
            onClick={() => setActiveTab('history')}
          >
            🕒 History Timeline ({history?.assignments?.length ?? 0})
          </button>
        </div>

        {/* Drawer Body */}
        <div className="drawer-body">
          {loading ? (
            <div className="drawer-loading">
              <div className="spinner" />
              <p>Loading QR details & analytics...</p>
            </div>
          ) : (
            <>
              {/* TAB 1: OVERVIEW */}
              {activeTab === 'overview' && (
                <div className="drawer-tab-content">
                  {/* Top Preview Card */}
                  <div className="drawer-preview-card">
                    <div className="drawer-qr-image-wrapper">
                      <img
                        src={
                          previewBlobUrl ||
                          `${import.meta.env.VITE_API_URL || ''}/api/qr/export/png/${numericId || qrId}?size=240${
                            localStorage.getItem('token') ? `&token=${encodeURIComponent(localStorage.getItem('token'))}` : ''
                          }`
                        }
                        alt={qrId}
                        className="drawer-qr-img"
                      />
                      <span className="drawer-qr-watermark">PERMANENT CODE</span>
                    </div>

                    <div className="drawer-preview-meta">
                      <div className="drawer-destination-box">
                        <span className="drawer-meta-label">Destination URL:</span>
                        {analytics?.current_destination || qr?.current_destination ? (
                          <div className="drawer-url-row">
                            <a
                              href={analytics?.current_destination || qr?.current_destination}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="drawer-dest-link"
                              title={analytics?.current_destination || qr?.current_destination}
                            >
                              {analytics?.current_destination || qr?.current_destination} 🔗
                            </a>
                            <button
                              className="drawer-copy-btn"
                              onClick={() => copyToClipboard(analytics?.current_destination || qr?.current_destination, 'Destination URL')}
                              title="Copy URL"
                            >
                              📋
                            </button>
                          </div>
                        ) : (
                          <span className="text-muted font-italic">Not assigned yet</span>
                        )}
                      </div>

                      <div className="drawer-token-box">
                        <div className="drawer-token-header">
                          <span className="drawer-meta-label">Permanent Token:</span>
                          <button
                            className="text-action-btn"
                            onClick={() => setTokenRevealed(!tokenRevealed)}
                            style={{ fontSize: '0.78rem' }}
                          >
                            {tokenRevealed ? '🙈 Mask' : '👁️ Reveal'}
                          </button>
                        </div>
                        <div className="drawer-token-val">
                          <code>
                            {tokenRevealed
                              ? (analytics?.token || qr?.token)
                              : ((analytics?.token || qr?.token)?.slice(0, 4) + '••••••••••••')}
                          </code>
                          <button
                            className="drawer-copy-btn"
                            onClick={() => copyToClipboard(analytics?.token || qr?.token, 'Token')}
                            title="Copy Token"
                          >
                            📋
                          </button>
                        </div>
                      </div>

                      <div className="drawer-quick-export-actions">
                        <button className="btn btn-secondary btn-sm" onClick={handleDownloadPNG}>
                          📥 Download PNG Sticker
                        </button>
                        <a
                          href={`/q/${analytics?.token || qr?.token}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="btn btn-outline btn-sm"
                        >
                          🚀 Test Redirect URL
                        </a>
                      </div>
                    </div>
                  </div>

                  {/* Summary Metric Stats */}
                  <div className="drawer-stats-row">
                    <div className="drawer-stat-mini primary">
                      <span className="stat-mini-val">{(analytics?.total_scans ?? 0).toLocaleString()}</span>
                      <span className="stat-mini-lbl">Lifetime Scans</span>
                    </div>
                    <div className="drawer-stat-mini success">
                      <span className="stat-mini-val">{analytics?.scans_today ?? 0}</span>
                      <span className="stat-mini-lbl">Today (IST)</span>
                    </div>
                    <div className="drawer-stat-mini info">
                      <span className="stat-mini-val">{analytics?.scans_7d ?? 0}</span>
                      <span className="stat-mini-lbl">Last 7 Days</span>
                    </div>
                    <div className="drawer-stat-mini accent">
                      <span className="stat-mini-val">{analytics?.scans_30d ?? 0}</span>
                      <span className="stat-mini-lbl">Last 30 Days</span>
                    </div>
                  </div>

                  {/* Detailed Metadata Grid */}
                  <div className="drawer-section">
                    <h4 className="drawer-section-title">📌 Registry Information</h4>
                    <div className="drawer-info-grid">
                      <div className="drawer-info-cell">
                        <span className="info-cell-key">Assigned Business</span>
                        <strong className="info-cell-val">
                          {analytics?.current_business_name || qr?.current_business_name || 'None (Unassigned)'}
                        </strong>
                      </div>
                      <div className="drawer-info-cell">
                        <span className="info-cell-key">Lifecycle Status</span>
                        <span className={`status-pill ${currentStatus}`}>
                          {currentStatus.toUpperCase()}
                        </span>
                      </div>
                      <div className="drawer-info-cell">
                        <span className="info-cell-key">Created Date (IST)</span>
                        <span className="info-cell-val">
                          {qr?.created_at_ist || formatIST(qr?.created_at)}
                        </span>
                      </div>
                      <div className="drawer-info-cell">
                        <span className="info-cell-key">Last Scanned (IST)</span>
                        <span className="info-cell-val">
                          {analytics?.last_scanned_at_ist || qr?.last_scanned_at_ist || 'Never Scanned'}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 2: ANALYTICS */}
              {activeTab === 'analytics' && (
                <div className="drawer-tab-content">
                  <div className="drawer-chart-card">
                    <div className="drawer-chart-header">
                      <h4>📊 30-Day Daily Scans (Asia/Kolkata)</h4>
                      <span className="badge badge-primary">{analytics?.total_scans ?? 0} Total</span>
                    </div>
                    {analytics?.daily_trend && analytics.daily_trend.some((d) => d.scans > 0) ? (
                      <div className="drawer-bar-chart">
                        {(() => {
                          const maxScans = Math.max(...analytics.daily_trend.map((d) => d.scans), 1);
                          return analytics.daily_trend.map((d) => {
                            const heightPct = Math.max(Math.round((d.scans / maxScans) * 100), d.scans > 0 ? 12 : 2);
                            return (
                              <div
                                key={d.date}
                                className="chart-bar-col"
                                title={`${d.date}: ${d.scans} scan(s)`}
                              >
                                <div
                                  className={`chart-bar ${d.scans > 0 ? 'bar-has-scans' : 'bar-empty'}`}
                                  style={{ height: `${heightPct}%` }}
                                >
                                  {d.scans > 0 && <span className="bar-val">{d.scans}</span>}
                                </div>
                                <span className="chart-date-lbl">{d.date.slice(5)}</span>
                              </div>
                            );
                          });
                        })()}
                      </div>
                    ) : (
                      <div className="empty-chart-notice">
                        <span>💤</span> No scan activity recorded for this QR code in the last 30 days.
                      </div>
                    )}
                  </div>

                  {/* Recent Scan Events Table */}
                  <div className="drawer-section">
                    <h4 className="drawer-section-title">⚡ Recent Scan Events</h4>
                    {analytics?.recent_scans?.length > 0 ? (
                      <div className="drawer-scans-table-wrap">
                        <table className="drawer-table">
                          <thead>
                            <tr>
                              <th>Timestamp (IST)</th>
                              <th>Result</th>
                              <th>Attributed Client</th>
                              <th>IP / Device</th>
                            </tr>
                          </thead>
                          <tbody>
                            {analytics.recent_scans.map((s) => (
                              <tr key={s.id}>
                                <td>{s.scanned_at_ist}</td>
                                <td>
                                  <span className={`status-pill ${s.result_type}`}>
                                    {s.result_type}
                                  </span>
                                </td>
                                <td><strong>{s.attributed_client || '—'}</strong></td>
                                <td className="text-muted font-mono">{s.ip_address || 'Anonymized'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <p className="text-muted font-italic">No scan events logged yet.</p>
                    )}
                  </div>
                </div>
              )}

              {/* TAB 3: HISTORY */}
              {activeTab === 'history' && (
                <div className="drawer-tab-content">
                  <div className="drawer-section">
                    <h4 className="drawer-section-title">📜 Complete Assignment Timeline</h4>
                    {!history || !history.assignments || history.assignments.length === 0 ? (
                      <div className="empty-history-notice">
                        <span>⚪</span> This QR code has never been assigned to any business.
                      </div>
                    ) : (
                      <div className="history-timeline">
                        {history.assignments.map((item) => (
                          <div
                            key={item.id}
                            className={`timeline-entry ${item.is_active ? 'entry-active' : 'entry-historical'}`}
                          >
                            <div className="timeline-marker">{item.is_active ? '🟢' : '⚪'}</div>
                            <div className="timeline-content">
                              <div className="timeline-header">
                                <strong className="timeline-business">{item.business_name}</strong>
                                <span className={`status-pill ${item.is_active ? 'active' : 'disabled'}`}>
                                  {item.is_active ? 'CURRENT ACTIVE' : 'HISTORICAL'}
                                </span>
                              </div>
                              <div className="timeline-url">
                                <a href={item.destination_url} target="_blank" rel="noopener noreferrer">
                                  {item.destination_url} 🔗
                                </a>
                              </div>
                              <div className="timeline-dates">
                                <span>Assigned: {formatIST(item.assigned_at)} {item.assigned_by_name && `by ${item.assigned_by_name}`}</span>
                                {item.deactivated_at && (
                                  <span className="deact-date">Ended: {formatIST(item.deactivated_at)}</span>
                                )}
                              </div>
                              {item.notes && <div className="timeline-notes">📝 {item.notes}</div>}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Drawer Footer Actions */}
        <div className="drawer-footer">
          <div className="drawer-footer-actions">
            {isAdmin && currentStatus === 'active' && (
              <>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => setShowReassign(true)}
                  disabled={actionLoading}
                >
                  🔄 Transfer / Edit Destination
                </button>
                <button
                  className="btn btn-warning btn-sm"
                  onClick={handleDeactivate}
                  disabled={actionLoading}
                >
                  ⏸️ Deactivate
                </button>
              </>
            )}

            {isAdmin && currentStatus === 'disabled' && (
              <>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => setShowReassign(true)}
                  disabled={actionLoading}
                >
                  🔄 Transfer / Reassign
                </button>
                <button
                  className="btn btn-success btn-sm"
                  onClick={handleReactivate}
                  disabled={actionLoading}
                >
                  ✅ Reactivate
                </button>
              </>
            )}

            <button className="btn btn-secondary btn-sm" onClick={handleDownloadPNG}>
              📥 Download PNG
            </button>
            <button className="btn btn-outline btn-sm" onClick={onClose}>
              Close
            </button>
          </div>
        </div>

        {/* REASSIGN / TRANSFER MODAL */}
        {showReassign && (
          <div className="modal-backdrop" onClick={() => setShowReassign(false)}>
            <div className="modal-content" onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <h3>🔄 Transfer or Update Destination: {qrId}</h3>
                <button className="close-btn" onClick={() => setShowReassign(false)}>✕</button>
              </div>
              <form onSubmit={handleReassignSubmit}>
                <div className="form-group">
                  <label className="form-label">Business / Client Name</label>
                  <input
                    type="text"
                    className="form-input"
                    required
                    value={reassignForm.business_name}
                    onChange={(e) => setReassignForm({ ...reassignForm, business_name: e.target.value })}
                  />
                  <small className="form-hint">Changing this transfers the QR code to the new business while preserving historical scans.</small>
                </div>

                <div className="form-group">
                  <label className="form-label">Destination URL</label>
                  <input
                    type="url"
                    className="form-input"
                    required
                    value={reassignForm.destination_url}
                    onChange={(e) => setReassignForm({ ...reassignForm, destination_url: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Audit Notes (Optional)</label>
                  <textarea
                    className="form-input"
                    rows="2"
                    placeholder="Reason for transfer or URL update..."
                    value={reassignForm.notes}
                    onChange={(e) => setReassignForm({ ...reassignForm, notes: e.target.value })}
                  />
                </div>

                <div className="modal-actions-bar" style={{ marginTop: '20px' }}>
                  <button type="submit" className="btn btn-primary" disabled={actionLoading}>
                    {actionLoading ? 'Saving...' : 'Confirm Update / Transfer'}
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={() => setShowReassign(false)}>
                    Cancel
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
