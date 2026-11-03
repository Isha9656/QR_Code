import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { clientAPI } from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function ClientDetailPage() {
  const { clientName } = useParams();
  const decodedClientName = decodeURIComponent(clientName || '');
  const navigate = useNavigate();
  const { isAdmin } = useAuth();

  const [activeTab, setActiveTab] = useState('inventory'); // 'inventory' | 'analytics'

  // Data states
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [detail, setDetail] = useState(null);
  const [analytics, setAnalytics] = useState(null);

  // Filters & Pagination for QR table
  const [statusFilter, setStatusFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [analyticsDays, setAnalyticsDays] = useState(30);

  // Bulk selection
  const [selectedQrIds, setSelectedQrIds] = useState([]);

  // Confirmation Modal state
  const [modalConfig, setModalConfig] = useState({
    isOpen: false,
    title: '',
    message: '',
    actionType: '', // 'deactivate_selected' | 'activate_selected' | 'deactivate_all' | 'activate_all' | 'deactivate_single' | 'activate_single'
    targetQrId: null,
    affectedCount: 0,
  });

  const fetchDetail = async () => {
    setLoading(true);
    setError('');
    try {
      const params = {
        page,
        per_page: 25,
      };
      if (statusFilter !== 'all') params.status_filter = statusFilter;
      if (search.trim()) params.search = search.trim();

      const res = await clientAPI.getDetail(decodedClientName, params);
      setDetail(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load client details');
    } finally {
      setLoading(false);
    }
  };

  const fetchAnalytics = async () => {
    try {
      const res = await clientAPI.getAnalytics(decodedClientName, analyticsDays);
      setAnalytics(res.data);
    } catch (err) {
      console.error('Failed to load analytics:', err);
    }
  };

  useEffect(() => {
    fetchDetail();
    setSelectedQrIds([]);
  }, [clientName, page, statusFilter]);

  useEffect(() => {
    if (activeTab === 'analytics') {
      fetchAnalytics();
    }
  }, [activeTab, analyticsDays, clientName]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    setPage(1);
    fetchDetail();
  };

  // Selection handlers
  const handleSelectAll = (e) => {
    if (e.target.checked && detail?.items) {
      // Select all non-retired QRs on the current page
      const eligible = detail.items
        .filter((q) => q.status !== 'retired')
        .map((q) => q.qr_id);
      setSelectedQrIds(eligible);
    } else {
      setSelectedQrIds([]);
    }
  };

  const handleToggleSelect = (qrId) => {
    setSelectedQrIds((prev) =>
      prev.includes(qrId) ? prev.filter((id) => id !== qrId) : [...prev, qrId]
    );
  };

  // Modal open helpers
  const openConfirmModal = (actionType, targetQrId = null) => {
    let title = '';
    let message = '';
    let affectedCount = 0;

    if (actionType === 'deactivate_single') {
      title = `Deactivate QR Code (${targetQrId})`;
      message = `Are you sure you want to disable ${targetQrId}? Redirection will be suspended, but the destination URL will be preserved.`;
      affectedCount = 1;
    } else if (actionType === 'activate_single') {
      title = `Activate QR Code (${targetQrId})`;
      message = `Are you sure you want to reactivate ${targetQrId}? Redirection to its preserved destination will be restored immediately.`;
      affectedCount = 1;
    } else if (actionType === 'deactivate_selected') {
      title = `Bulk Deactivate (${selectedQrIds.length} QR Codes)`;
      message = `You are about to deactivate ${selectedQrIds.length} selected QR codes for client "${decodedClientName}". Their destinations will be preserved.`;
      affectedCount = selectedQrIds.length;
    } else if (actionType === 'activate_selected') {
      title = `Bulk Activate (${selectedQrIds.length} QR Codes)`;
      message = `You are about to reactivate ${selectedQrIds.length} selected QR codes for client "${decodedClientName}". Redirection will resume.`;
      affectedCount = selectedQrIds.length;
    } else if (actionType === 'deactivate_all') {
      title = `Deactivate All Active QRs for "${decodedClientName}"`;
      affectedCount = detail?.active_qr_codes || 0;
      message = `CRITICAL ACTION: This will disable ALL ${affectedCount} active QR code(s) belonging to "${decodedClientName}". Destinations will remain intact.`;
    } else if (actionType === 'activate_all') {
      title = `Reactivate All Disabled QRs for "${decodedClientName}"`;
      affectedCount = detail?.disabled_qr_codes || 0;
      message = `This will reactivate ALL ${affectedCount} disabled QR code(s) belonging to "${decodedClientName}".`;
    }

    setModalConfig({
      isOpen: true,
      title,
      message,
      actionType,
      targetQrId,
      affectedCount,
    });
  };

  const executeModalAction = async () => {
    const { actionType, targetQrId } = modalConfig;
    setModalConfig((prev) => ({ ...prev, isOpen: false }));
    setError('');
    setSuccessMsg('');

    try {
      if (actionType === 'activate_single') {
        const res = await clientAPI.activateQR(decodedClientName, targetQrId);
        setSuccessMsg(res.data.message || `Activated ${targetQrId}`);
      } else if (actionType === 'deactivate_single') {
        const res = await clientAPI.deactivateQR(decodedClientName, targetQrId);
        setSuccessMsg(res.data.message || `Deactivated ${targetQrId}`);
      } else if (actionType === 'deactivate_selected') {
        const res = await clientAPI.bulkDeactivate(decodedClientName, selectedQrIds);
        setSuccessMsg(res.data.message);
        setSelectedQrIds([]);
      } else if (actionType === 'activate_selected') {
        const res = await clientAPI.bulkActivate(decodedClientName, selectedQrIds);
        setSuccessMsg(res.data.message);
        setSelectedQrIds([]);
      } else if (actionType === 'deactivate_all') {
        const res = await clientAPI.deactivateAll(decodedClientName);
        setSuccessMsg(res.data.message);
      } else if (actionType === 'activate_all') {
        const res = await clientAPI.activateAll(decodedClientName);
        setSuccessMsg(res.data.message);
      }

      await fetchDetail();
      if (activeTab === 'analytics') {
        await fetchAnalytics();
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Operation failed');
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'Never';
    return new Date(dateStr).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="client-detail-page">
      {/* Navigation Breadcrumb */}
      <div style={{ marginBottom: '16px' }}>
        <button
          className="btn btn-secondary btn-sm"
          onClick={() => navigate('/clients')}
          style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
        >
          <span>← Back to All Clients</span>
        </button>
      </div>

      {/* Header Banner */}
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '28px' }}>🏢</span>
            <h1 className="page-title" style={{ margin: 0 }}>{decodedClientName}</h1>
          </div>
          <p className="page-subtitle" style={{ marginTop: '4px' }}>
            Client QR Usage, Diagnostics & Lifecycle Management
          </p>
        </div>

        {/* Client-Wide Quick Actions (Admin Only) */}
        {isAdmin && (
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => openConfirmModal('activate_all')}
              disabled={loading || (detail?.disabled_qr_codes === 0)}
              title="Reactivate all currently disabled QR codes"
            >
              ✅ Reactivate All Disabled ({detail?.disabled_qr_codes || 0})
            </button>
            <button
              className="btn btn-danger btn-sm"
              onClick={() => openConfirmModal('deactivate_all')}
              disabled={loading || (detail?.active_qr_codes === 0)}
              title="Deactivate all currently active QR codes"
            >
              ⏸️ Deactivate All Active ({detail?.active_qr_codes || 0})
            </button>
          </div>
        )}
      </div>

      {/* Alert Messages */}
      {error && <div className="login-error" style={{ marginBottom: '16px' }}>{error}</div>}
      {successMsg && (
        <div style={{ background: 'rgba(34, 197, 94, 0.15)', border: '1px solid #22c55e', color: '#4ade80', padding: '12px 16px', borderRadius: '8px', marginBottom: '16px' }}>
          {successMsg}
        </div>
      )}

      {/* Client Overview Statistics */}
      {detail && (
        <div className="stats-grid" style={{ marginBottom: '20px' }}>
          <div className="stat-card primary">
            <div className="stat-icon">📱</div>
            <div className="stat-value">{detail.total_qr_codes}</div>
            <div className="stat-label">Total QRs Assigned</div>
          </div>
          <div className="stat-card success">
            <div className="stat-icon">✅</div>
            <div className="stat-value">{detail.active_qr_codes}</div>
            <div className="stat-label">Active Codes</div>
          </div>
          <div className="stat-card warning">
            <div className="stat-icon">⏸️</div>
            <div className="stat-value">{detail.disabled_qr_codes}</div>
            <div className="stat-label">Disabled Codes</div>
          </div>
          <div className="stat-card danger">
            <div className="stat-icon">🚫</div>
            <div className="stat-value">{detail.retired_qr_codes}</div>
            <div className="stat-label">Retired Codes</div>
          </div>
          <div className="stat-card info">
            <div className="stat-icon">🎯</div>
            <div className="stat-value">{detail.total_scans.toLocaleString()}</div>
            <div className="stat-label">Lifetime Scans</div>
          </div>
          <div className="stat-card primary" style={{ borderColor: 'rgba(56, 189, 248, 0.3)' }}>
            <div className="stat-icon">⚡</div>
            <div className="stat-value">{detail.scans_30d.toLocaleString()}</div>
            <div className="stat-label">Scans (Last 30 Days)</div>
          </div>
        </div>
      )}

      {/* Tab Navigation */}
      <div style={{ display: 'flex', borderBottom: '1px solid rgba(255,255,255,0.08)', marginBottom: '20px', gap: '8px' }}>
        <button
          onClick={() => setActiveTab('inventory')}
          style={{
            background: 'transparent',
            border: 'none',
            borderBottom: activeTab === 'inventory' ? '2px solid #38bdf8' : '2px solid transparent',
            color: activeTab === 'inventory' ? '#38bdf8' : '#94a3b8',
            padding: '10px 18px',
            fontWeight: '600',
            fontSize: '0.95rem',
            cursor: 'pointer',
          }}
        >
          📋 QR Code Inventory ({detail?.total || 0})
        </button>
        <button
          onClick={() => setActiveTab('analytics')}
          style={{
            background: 'transparent',
            border: 'none',
            borderBottom: activeTab === 'analytics' ? '2px solid #38bdf8' : '2px solid transparent',
            color: activeTab === 'analytics' ? '#38bdf8' : '#94a3b8',
            padding: '10px 18px',
            fontWeight: '600',
            fontSize: '0.95rem',
            cursor: 'pointer',
          }}
        >
          📈 Scan Analytics &amp; Trends
        </button>
      </div>

      {/* TAB 1: QR INVENTORY & LIFECYCLE MANAGEMENT */}
      {activeTab === 'inventory' && (
        <>
          {/* Filters & Search */}
          <div className="card" style={{ marginBottom: '16px' }}>
            <form onSubmit={handleSearchSubmit} style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', alignItems: 'flex-end' }}>
              <div style={{ flex: '1 1 200px' }}>
                <label className="form-label">Search</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="Search by QR ID, token or URL..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>

              <div style={{ width: '200px' }}>
                <label className="form-label">Status &amp; Usage Filter</label>
                <select
                  className="form-select"
                  value={statusFilter}
                  onChange={(e) => {
                    setStatusFilter(e.target.value);
                    setPage(1);
                  }}
                >
                  <option value="all">All QR Codes</option>
                  <option value="active">Active Only</option>
                  <option value="disabled">Disabled Only</option>
                  <option value="retired">Retired Only</option>
                  <option value="recently_used">Recently Used (30d)</option>
                  <option value="not_used_30d">Not Used in 30 Days</option>
                  <option value="never_scanned">Never Scanned (0 scans)</option>
                </select>
              </div>

              <div>
                <button type="submit" className="btn btn-primary" style={{ height: '42px' }}>
                  Filter
                </button>
              </div>
            </form>
          </div>

          {/* Floating Bulk Action Bar */}
          {isAdmin && selectedQrIds.length > 0 && (
            <div
              style={{
                background: 'rgba(15, 23, 42, 0.95)',
                border: '1px solid #38bdf8',
                boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
                borderRadius: '8px',
                padding: '12px 18px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '12px',
                marginBottom: '16px',
                position: 'sticky',
                top: '55px',
                zIndex: 99,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontWeight: 'bold', color: '#f8fafc' }}>
                  ☑️ {selectedQrIds.length} QR Code(s) Selected
                </span>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => setSelectedQrIds([])}
                  style={{ fontSize: '0.75rem', padding: '2px 8px' }}
                >
                  Clear Selection
                </button>
              </div>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => openConfirmModal('activate_selected')}
                >
                  ✅ Activate Selected
                </button>
                <button
                  className="btn btn-danger btn-sm"
                  onClick={() => openConfirmModal('deactivate_selected')}
                >
                  ⏸️ Deactivate Selected
                </button>
              </div>
            </div>
          )}

          {/* QR Inventory Table */}
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            {loading ? (
              <div style={{ padding: '40px', textAlign: 'center' }}>
                <div className="spinner" style={{ margin: '0 auto 12px' }} />
                <p style={{ color: '#94a3b8' }}>Loading QR records...</p>
              </div>
            ) : detail?.items?.length === 0 ? (
              <div style={{ padding: '40px', textAlign: 'center', color: '#94a3b8' }}>
                <div style={{ fontSize: '42px', marginBottom: '12px' }}>🔲</div>
                <h3>No Matching QR Codes</h3>
                <p>No QR codes found under the selected filter criteria.</p>
              </div>
            ) : (
              <div className="table-responsive">
                <table className="table" style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ background: 'rgba(30, 41, 59, 0.7)', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                      {isAdmin && (
                        <th style={{ padding: '12px 14px', width: '36px', textAlign: 'center' }}>
                          <input
                            type="checkbox"
                            onChange={handleSelectAll}
                            checked={
                              detail?.items?.length > 0 &&
                              detail.items.filter((q) => q.status !== 'retired').every((q) => selectedQrIds.includes(q.qr_id))
                            }
                          />
                        </th>
                      )}
                      <th style={{ padding: '12px 14px', textAlign: 'left' }}>QR ID &amp; Token</th>
                      <th style={{ padding: '12px 14px', textAlign: 'left' }}>Destination URL</th>
                      <th style={{ padding: '12px 14px', textAlign: 'center' }}>Status</th>
                      <th style={{ padding: '12px 14px', textAlign: 'center' }}>Lifetime Scans</th>
                      <th style={{ padding: '12px 14px', textAlign: 'center' }}>Last 30 Days</th>
                      <th style={{ padding: '12px 14px', textAlign: 'left' }}>Last Scanned</th>
                      <th style={{ padding: '12px 14px', textAlign: 'right' }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail?.items?.map((qr) => {
                      const isSelected = selectedQrIds.includes(qr.qr_id);
                      const isRetired = qr.status === 'retired';

                      return (
                        <tr
                          key={qr.qr_id}
                          style={{
                            borderBottom: '1px solid rgba(255,255,255,0.04)',
                            background: isSelected ? 'rgba(56, 189, 248, 0.07)' : 'transparent',
                          }}
                        >
                          {isAdmin && (
                            <td style={{ padding: '12px 14px', textAlign: 'center' }}>
                              <input
                                type="checkbox"
                                disabled={isRetired}
                                checked={isSelected}
                                onChange={() => handleToggleSelect(qr.qr_id)}
                              />
                            </td>
                          )}
                          <td style={{ padding: '12px 14px' }}>
                            <div style={{ fontWeight: 'bold', color: '#f8fafc', fontSize: '0.92rem' }}>
                              {qr.qr_id}
                            </div>
                            <div style={{ fontSize: '0.75rem', color: '#64748b', fontFamily: 'monospace' }}>
                              {qr.token.substring(0, 14)}...
                            </div>
                          </td>
                          <td style={{ padding: '12px 14px', maxWidth: '240px' }}>
                            {qr.destination_url ? (
                              <a
                                href={qr.destination_url}
                                target="_blank"
                                rel="noreferrer"
                                style={{
                                  color: '#38bdf8',
                                  textDecoration: 'none',
                                  fontSize: '0.85rem',
                                  display: 'block',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  whiteSpace: 'nowrap',
                                }}
                                title={qr.destination_url}
                              >
                                {qr.destination_url} 🔗
                              </a>
                            ) : (
                              <span style={{ color: '#64748b', fontSize: '0.82rem', fontStyle: 'italic' }}>
                                None (Unassigned)
                              </span>
                            )}
                          </td>
                          <td style={{ padding: '12px 14px', textAlign: 'center' }}>
                            <span
                              className={`badge ${
                                qr.status === 'active'
                                  ? 'badge-active'
                                  : qr.status === 'disabled'
                                  ? 'badge-disabled'
                                  : 'badge-retired'
                              }`}
                            >
                              {qr.status.toUpperCase()}
                            </span>
                          </td>
                          <td style={{ padding: '12px 14px', textAlign: 'center', fontWeight: 'bold' }}>
                            {qr.total_scans.toLocaleString()}
                          </td>
                          <td style={{ padding: '12px 14px', textAlign: 'center' }}>
                            <span style={{ color: qr.scans_30d > 0 ? '#34d399' : '#64748b' }}>
                              {qr.scans_30d}
                            </span>
                          </td>
                          <td style={{ padding: '12px 14px', fontSize: '0.82rem', color: '#94a3b8' }}>
                            {formatDate(qr.last_scanned_at)}
                          </td>
                          <td style={{ padding: '12px 14px', textAlign: 'right' }}>
                            {isAdmin ? (
                              isRetired ? (
                                <span style={{ fontSize: '0.78rem', color: '#64748b' }}>Terminal</span>
                              ) : qr.status === 'active' ? (
                                <button
                                  className="btn btn-secondary btn-sm"
                                  style={{ padding: '3px 8px', fontSize: '0.78rem' }}
                                  onClick={() => openConfirmModal('deactivate_single', qr.qr_id)}
                                >
                                  ⏸️ Deactivate
                                </button>
                              ) : (
                                <button
                                  className="btn btn-primary btn-sm"
                                  style={{ padding: '3px 8px', fontSize: '0.78rem' }}
                                  onClick={() => openConfirmModal('activate_single', qr.qr_id)}
                                >
                                  ✅ Activate
                                </button>
                              )
                            ) : (
                              <span style={{ fontSize: '0.78rem', color: '#64748b' }}>View only</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* Pagination Footer */}
            {detail?.total_pages > 1 && (
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
                  Showing Page {detail.page} of {detail.total_pages} ({detail.total} matching codes)
                </span>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    className="btn btn-secondary btn-sm"
                    disabled={detail.page <= 1}
                    onClick={() => setPage(page - 1)}
                  >
                    ◀ Previous
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    disabled={detail.page >= detail.total_pages}
                    onClick={() => setPage(page + 1)}
                  >
                    Next ▶
                  </button>
                </div>
              </div>
            )}
          </div>
        </>
      )}

      {/* TAB 2: CLIENT USAGE ANALYTICS */}
      {activeTab === 'analytics' && (
        <div>
          {/* Date Range Selector */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '10px' }}>
            <h3 style={{ margin: 0, color: '#f8fafc' }}>📊 Real-Time Scan Analytics &amp; Activity</h3>
            <div style={{ display: 'flex', gap: '6px' }}>
              {[7, 30, 90].map((d) => (
                <button
                  key={d}
                  className={`btn btn-sm ${analyticsDays === d ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setAnalyticsDays(d)}
                >
                  Last {d} Days
                </button>
              ))}
            </div>
          </div>

          {/* Daily Scan Chart */}
          <div className="card" style={{ marginBottom: '20px' }}>
            <h4 style={{ margin: '0 0 16px 0', color: '#cbd5e1' }}>Daily Scan Activity ({analyticsDays} Days)</h4>
            {analytics?.daily_scans?.length > 0 ? (
              <div>
                {/* Responsive SVG Chart */}
                {(() => {
                  const maxScan = Math.max(...analytics.daily_scans.map((s) => s.scans), 1);
                  const chartHeight = 140;
                  const barCount = analytics.daily_scans.length;

                  return (
                    <div style={{ overflowX: 'auto', paddingBottom: '8px' }}>
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'flex-end',
                          height: `${chartHeight}px`,
                          gap: barCount > 30 ? '3px' : '8px',
                          minWidth: `${barCount * (barCount > 30 ? 14 : 26)}px`,
                          borderBottom: '1px solid rgba(255,255,255,0.1)',
                          paddingBottom: '4px',
                        }}
                      >
                        {analytics.daily_scans.map((item) => {
                          const heightPct = Math.round((item.scans / maxScan) * 100);
                          const isZero = item.scans === 0;

                          return (
                            <div
                              key={item.date}
                              style={{
                                flex: 1,
                                display: 'flex',
                                flexDirection: 'column',
                                alignItems: 'center',
                                height: '100%',
                                justifyContent: 'flex-end',
                              }}
                              title={`${item.date}: ${item.scans} scan(s)`}
                            >
                              <div
                                style={{
                                  width: '100%',
                                  height: `${Math.max(heightPct, isZero ? 2 : 6)}%`,
                                  background: isZero
                                    ? 'rgba(255,255,255,0.06)'
                                    : 'linear-gradient(180deg, #38bdf8 0%, #0284c7 100%)',
                                  borderRadius: '3px 3px 0 0',
                                  transition: 'height 0.3s ease',
                                }}
                              />
                              <span style={{ fontSize: '0.62rem', color: '#64748b', marginTop: '4px', whiteSpace: 'nowrap' }}>
                                {item.date.substring(5)}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })()}
              </div>
            ) : (
              <p style={{ color: '#64748b' }}>No scan data recorded in this period.</p>
            )}
          </div>

          {/* Performance Ranking Grids */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '16px', marginBottom: '20px' }}>
            {/* Most Used QRs */}
            <div className="card">
              <h4 style={{ margin: '0 0 12px 0', color: '#34d399' }}>🔥 Top Performing QR Codes</h4>
              {analytics?.most_used_qrs?.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {analytics.most_used_qrs.map((q, idx) => (
                    <div
                      key={q.qr_id}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        padding: '8px 12px',
                        background: 'rgba(255,255,255,0.02)',
                        borderRadius: '6px',
                        fontSize: '0.85rem',
                      }}
                    >
                      <div>
                        <span style={{ fontWeight: 'bold', color: '#f8fafc', marginRight: '8px' }}>
                          #{idx + 1} {q.qr_id}
                        </span>
                        <span style={{ color: '#64748b', fontSize: '0.78rem' }}>
                          {q.destination_url?.substring(0, 24)}...
                        </span>
                      </div>
                      <span className="badge badge-active">{q.total_scans} scans</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p style={{ color: '#64748b', fontSize: '0.85rem' }}>No scans recorded yet.</p>
              )}
            </div>

            {/* Least Used QRs */}
            <div className="card">
              <h4 style={{ margin: '0 0 12px 0', color: '#f59e0b' }}>❄️ Least Used QR Codes (&gt; 0 scans)</h4>
              {analytics?.least_used_qrs?.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {analytics.least_used_qrs.map((q) => (
                    <div
                      key={q.qr_id}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        padding: '8px 12px',
                        background: 'rgba(255,255,255,0.02)',
                        borderRadius: '6px',
                        fontSize: '0.85rem',
                      }}
                    >
                      <span style={{ fontWeight: 'bold', color: '#f8fafc' }}>{q.qr_id}</span>
                      <span className="badge badge-disabled">{q.total_scans} scans</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p style={{ color: '#64748b', fontSize: '0.85rem' }}>No low-usage codes detected.</p>
              )}
            </div>

            {/* Declining Usage Alerts */}
            <div className="card">
              <h4 style={{ margin: '0 0 12px 0', color: '#f87171' }}>⚠️ Declining Usage Alerts (&gt;= 50% Drop)</h4>
              {analytics?.declining_qrs?.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {analytics.declining_qrs.map((q) => (
                    <div
                      key={q.qr_id}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        padding: '8px 12px',
                        background: 'rgba(239, 68, 68, 0.08)',
                        border: '1px solid rgba(239, 68, 68, 0.2)',
                        borderRadius: '6px',
                        fontSize: '0.82rem',
                      }}
                    >
                      <div>
                        <div style={{ fontWeight: 'bold', color: '#fca5a5' }}>{q.qr_id}</div>
                        <div style={{ color: '#94a3b8', fontSize: '0.75rem' }}>
                          Prior 14d: {q.prior_14d_scans} ➔ Last 14d: {q.recent_14d_scans}
                        </div>
                      </div>
                      <span style={{ color: '#ef4444', fontWeight: 'bold' }}>-{q.drop_percentage}%</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p style={{ color: '#34d399', fontSize: '0.85rem' }}>No steep usage drop detected across active codes.</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Explicit Confirmation Modal */}
      {modalConfig.isOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '16px',
          }}
        >
          <div
            className="card"
            style={{
              maxWidth: '480px',
              width: '100%',
              background: '#0f172a',
              border: '1px solid rgba(255,255,255,0.15)',
              boxShadow: '0 20px 40px rgba(0,0,0,0.8)',
            }}
          >
            <h3 style={{ margin: '0 0 12px 0', color: '#f8fafc' }}>{modalConfig.title}</h3>
            <p style={{ color: '#94a3b8', lineHeight: 1.5, fontSize: '0.92rem', marginBottom: '20px' }}>
              {modalConfig.message}
            </p>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button
                className="btn btn-secondary"
                onClick={() => setModalConfig((prev) => ({ ...prev, isOpen: false }))}
              >
                Cancel
              </button>
              <button
                className={`btn ${modalConfig.actionType.includes('deactivate') ? 'btn-danger' : 'btn-primary'}`}
                onClick={executeModalAction}
              >
                Confirm &amp; Proceed
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
