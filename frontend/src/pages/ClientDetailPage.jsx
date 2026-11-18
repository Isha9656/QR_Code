import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { clientAPI, qrAPI } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { formatIST } from '../utils/date';
import QRDetailDrawer from '../components/QRDetailDrawer';

export default function ClientDetailPage() {
  const { clientName } = useParams();
  const decodedClientName = decodeURIComponent(clientName || '');
  const navigate = useNavigate();
  const { isAdmin } = useAuth();

  // 6 Tabs: 'active' | 'disabled' | 'overview' | 'historical' | 'analytics' | 'history'
  const [activeTab, setActiveTab] = useState('active');

  // Data states
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [detail, setDetail] = useState(null);
  const [analytics, setAnalytics] = useState(null);

  // Drawer state
  const [selectedQR, setSelectedQR] = useState(null);

  // Filters & Pagination for QR table
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [analyticsDays, setAnalyticsDays] = useState(30);

  // Bulk selection for active tab
  const [selectedQrIds, setSelectedQrIds] = useState([]);

  // Confirmation Modal state
  const [modalConfig, setModalConfig] = useState({
    isOpen: false,
    title: '',
    message: '',
    actionType: '',
    targetQrId: null,
    affectedCount: 0,
  });

  const fetchDetail = async () => {
    setLoading(true);
    setError('');
    try {
      const params = {
        page,
        per_page: 50,
      };
      if (search.trim()) params.search = search.trim();

      const res = await clientAPI.getDetail(decodedClientName, params);
      setDetail(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load business details');
    } finally {
      setLoading(false);
    }
  };

  const fetchAnalytics = async () => {
    try {
      const res = await clientAPI.getAnalytics(decodedClientName, analyticsDays);
      setAnalytics(res.data);
    } catch (err) {
      console.error('Failed to load business analytics:', err);
    }
  };

  useEffect(() => {
    fetchDetail();
    setSelectedQrIds([]);
  }, [clientName, page]);

  useEffect(() => {
    if (activeTab === 'analytics' || activeTab === 'overview') {
      fetchAnalytics();
    }
  }, [activeTab, analyticsDays, clientName]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    setPage(1);
    fetchDetail();
  };

  // Selection handlers
  const handleSelectAll = (e, items) => {
    if (e.target.checked && items) {
      const eligible = items
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

  // Modals & Action Confirmations
  const openConfirmModal = (type, targetQrId = null) => {
    let title = '';
    let message = '';
    let count = 0;

    switch (type) {
      case 'deactivate_selected':
        count = selectedQrIds.length;
        title = `Deactivate ${count} Selected QR Code(s)`;
        message = `Are you sure you want to deactivate ${count} QR code(s)? While deactivated, public scans will be blocked with a 404/maintenance message.`;
        break;
      case 'activate_selected':
        count = selectedQrIds.length;
        title = `Reactivate ${count} Selected QR Code(s)`;
        message = `Are you sure you want to reactivate ${count} QR code(s)? Public scans will immediately resume redirecting to their destination URLs.`;
        break;
      case 'deactivate_all':
        count = detail?.active_qr_codes || 0;
        title = `Deactivate All Active QR Codes (${count})`;
        message = `⚠️ CAUTION: This will pause public redirects for ALL ${count} active QR codes assigned to ${decodedClientName}. Are you sure you want to proceed?`;
        break;
      case 'activate_all':
        count = detail?.disabled_qr_codes || 0;
        title = `Reactivate All Disabled QR Codes (${count})`;
        message = `This will reactivate ALL ${count} disabled QR codes for ${decodedClientName}.`;
        break;
      case 'deactivate_single':
        count = 1;
        title = `Deactivate QR Code: ${targetQrId}`;
        message = `Are you sure you want to deactivate ${targetQrId}? Public scans will be suspended until reactivated.`;
        break;
      case 'activate_single':
        count = 1;
        title = `Reactivate QR Code: ${targetQrId}`;
        message = `Are you sure you want to reactivate ${targetQrId}? Redirects will immediately resume.`;
        break;
      default:
        return;
    }

    setModalConfig({
      isOpen: true,
      title,
      message,
      actionType: type,
      targetQrId,
      affectedCount: count,
    });
  };

  const handleModalConfirm = async () => {
    const { actionType, targetQrId } = modalConfig;
    setModalConfig((prev) => ({ ...prev, isOpen: false }));
    setLoading(true);
    setError('');
    setSuccessMsg('');

    try {
      if (actionType === 'deactivate_single') {
        await clientAPI.deactivateQR(decodedClientName, targetQrId);
        setSuccessMsg(`QR Code ${targetQrId} deactivated successfully.`);
      } else if (actionType === 'activate_single') {
        await clientAPI.activateQR(decodedClientName, targetQrId);
        setSuccessMsg(`QR Code ${targetQrId} reactivated successfully.`);
      } else if (actionType === 'deactivate_selected') {
        const res = await clientAPI.bulkDeactivate(decodedClientName, selectedQrIds);
        setSuccessMsg(`Successfully deactivated ${res.data.affected_count} QR code(s).`);
        setSelectedQrIds([]);
      } else if (actionType === 'activate_selected') {
        const res = await clientAPI.bulkActivate(decodedClientName, selectedQrIds);
        setSuccessMsg(`Successfully reactivated ${res.data.affected_count} QR code(s).`);
        setSelectedQrIds([]);
      } else if (actionType === 'deactivate_all') {
        const res = await clientAPI.deactivateAll(decodedClientName);
        setSuccessMsg(`Successfully deactivated all ${res.data.affected_count} QR code(s).`);
        setSelectedQrIds([]);
      } else if (actionType === 'activate_all') {
        const res = await clientAPI.activateAll(decodedClientName);
        setSuccessMsg(`Successfully reactivated all ${res.data.affected_count} QR code(s).`);
        setSelectedQrIds([]);
      }

      await fetchDetail();
    } catch (err) {
      setError(err.response?.data?.detail || 'Action failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleExportCSV = () => {
    if (!detail?.items || detail.items.length === 0) return;
    const headers = ['QR ID', 'Token', 'Status', 'Ownership', 'Destination URL', 'Total Scans (IST)', 'Scans 7d', 'Scans 30d', 'Last Scanned (IST)', 'Assigned At (IST)'];
    const rows = detail.items.map((q) => [
      q.qr_id,
      q.token,
      q.status,
      q.ownership_type,
      `"${(q.destination_url || '').replace(/"/g, '""')}"`,
      q.total_scans,
      q.scans_7d,
      q.scans_30d,
      `"${q.last_scanned_at_ist || 'Never'}"`,
      `"${q.assigned_at_ist || ''}"`,
    ]);

    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((e) => e.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `${decodedClientName.replace(/\s+/g, '_')}_qr_inventory.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Filter items into categories
  const allItems = detail?.items || [];
  const activeQRs = allItems.filter((i) => i.is_current_owner && i.status === 'active');
  const disabledQRs = allItems.filter((i) => i.is_current_owner && i.status === 'disabled');
  const historicalQRs = allItems.filter((i) => !i.is_current_owner);

  // Avatar helper
  const getInitials = (name) => {
    if (!name) return '??';
    const parts = name.trim().split(/\s+/);
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  };

  const stringToColor = (str) => {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    const colors = ['#2563eb', '#7c3aed', '#059669', '#d97706', '#dc2626', '#0891b2', '#4f46e5', '#be185d'];
    return colors[Math.abs(hash) % colors.length];
  };

  const avatarColor = stringToColor(decodedClientName);

  return (
    <div className="businesses-page">
      {/* Top Back Navigation */}
      <div>
        <button
          className="btn btn-secondary btn-sm"
          onClick={() => navigate('/businesses')}
          style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
        >
          <span>← Back to Businesses</span>
        </button>
      </div>

      {/* Header Workspace Banner */}
      <div
        className="card"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '16px',
          padding: '20px 24px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div
            className="biz-avatar"
            style={{
              backgroundColor: avatarColor,
              width: '56px',
              height: '56px',
              fontSize: '1.35rem',
              borderRadius: '12px',
            }}
          >
            {getInitials(decodedClientName)}
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <h1 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 800, color: 'var(--gray-900)' }}>
                {decodedClientName}
              </h1>
              {detail && (
                <span
                  className={`status-pill ${detail.active_qr_codes > 0 ? 'active' : detail.disabled_qr_codes > 0 ? 'disabled' : 'unassigned'
                    }`}
                >
                  {detail.active_qr_codes > 0
                    ? `● ACTIVE (${detail.active_qr_codes})`
                    : detail.disabled_qr_codes > 0
                      ? '⏸️ DISABLED'
                      : 'HISTORICAL'}
                </span>
              )}
            </div>
            <p style={{ margin: '4px 0 0', fontSize: '0.85rem', color: 'var(--gray-500)' }}>
              Dedicated Business Workspace • Asia/Kolkata (IST) Scan Attribution
            </p>
          </div>
        </div>

        {/* Workspace Quick Actions */}
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <button
            className="btn btn-outline btn-sm"
            onClick={handleExportCSV}
            disabled={allItems.length === 0}
            title="Export business QR inventory to CSV"
          >
            📥 Export CSV
          </button>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => navigate(`/print-studio`)}
            title="Open Printing Studio"
          >
            🖨️ Print Studio
          </button>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => navigate('/scan')}
            title="Assign a new QR code to this business"
          >
            ➕ Assign QR Code
          </button>
          {isAdmin && (
            <>
              {detail?.disabled_qr_codes > 0 && (
                <button
                  className="btn btn-success btn-sm"
                  onClick={() => openConfirmModal('activate_all')}
                  disabled={loading}
                >
                  ✅ Reactivate All ({detail.disabled_qr_codes})
                </button>
              )}
              {detail?.active_qr_codes > 0 && (
                <button
                  className="btn btn-warning btn-sm"
                  onClick={() => openConfirmModal('deactivate_all')}
                  disabled={loading}
                >
                  ⏸️ Deactivate All ({detail.active_qr_codes})
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Alert Messages */}
      {error && <div className="login-error" style={{ marginBottom: '16px' }}>{error}</div>}
      {successMsg && (
        <div
          style={{
            background: 'var(--green-100)',
            border: '1px solid var(--green-500)',
            color: '#15803d',
            padding: '12px 16px',
            borderRadius: 'var(--radius-sm)',
            marginBottom: '16px',
            fontWeight: 500,
          }}
        >
          {successMsg}
        </div>
      )}

      {/* Top Metrics Row */}
      {detail && (
        <div className="biz-summary-grid">
          <div className="biz-summary-card">
            <span className="summary-icon">📱</span>
            <div className="summary-info">
              <span className="summary-val">{detail.total_qr_codes}</span>
              <span className="summary-lbl">Assigned QRs</span>
            </div>
          </div>
          <div className="biz-summary-card">
            <span className="summary-icon">🟢</span>
            <div className="summary-info">
              <span className="summary-val">{detail.active_qr_codes}</span>
              <span className="summary-lbl">Active QRs</span>
            </div>
          </div>
          <div className="biz-summary-card">
            <span className="summary-icon">⏸️</span>
            <div className="summary-info">
              <span className="summary-val">{detail.disabled_qr_codes}</span>
              <span className="summary-lbl">Disabled QRs</span>
            </div>
          </div>
          <div className="biz-summary-card">
            <span className="summary-icon">🎯</span>
            <div className="summary-info">
              <span className="summary-val">{detail.total_scans.toLocaleString()}</span>
              <span className="summary-lbl">Lifetime Scans</span>
            </div>
          </div>
          <div className="biz-summary-card">
            <span className="summary-icon">⚡</span>
            <div className="summary-info">
              <span className="summary-val">{(detail.scans_today ?? 0).toLocaleString()}</span>
              <span className="summary-lbl">Today (IST)</span>
            </div>
          </div>
          <div className="biz-summary-card">
            <span className="summary-icon">📅</span>
            <div className="summary-info">
              <span className="summary-val">{(detail.scans_7d ?? 0).toLocaleString()}</span>
              <span className="summary-lbl">7 Days (IST)</span>
            </div>
          </div>
        </div>
      )}

      {/* 6 Workspace Tabs Navigation */}
      <div
        style={{
          display: 'flex',
          borderBottom: '1px solid var(--gray-200)',
          gap: '8px',
          overflowX: 'auto',
          background: 'var(--bg-card)',
          padding: '0 16px',
          borderRadius: 'var(--radius) var(--radius) 0 0',
        }}
      >
        <button
          onClick={() => setActiveTab('active')}
          className={`drawer-tab-btn ${activeTab === 'active' ? 'active' : ''}`}
        >
          🟢 Active QRs ({activeQRs.length})
        </button>
        <button
          onClick={() => setActiveTab('disabled')}
          className={`drawer-tab-btn ${activeTab === 'disabled' ? 'active' : ''}`}
        >
          ⏸️ Deactivated QRs ({disabledQRs.length})
        </button>
        <button
          onClick={() => setActiveTab('overview')}
          className={`drawer-tab-btn ${activeTab === 'overview' ? 'active' : ''}`}
        >
          📋 Overview
        </button>
        <button
          onClick={() => setActiveTab('historical')}
          className={`drawer-tab-btn ${activeTab === 'historical' ? 'active' : ''}`}
        >
          📜 Historical QRs ({historicalQRs.length})
        </button>
        <button
          onClick={() => setActiveTab('analytics')}
          className={`drawer-tab-btn ${activeTab === 'analytics' ? 'active' : ''}`}
        >
          📊 Scan Analytics
        </button>
        <button
          onClick={() => setActiveTab('history')}
          className={`drawer-tab-btn ${activeTab === 'history' ? 'active' : ''}`}
        >
          ⏱️ Assignment History
        </button>
      </div>

      {/* Tab 1: OVERVIEW */}
      {activeTab === 'overview' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div className="card">
            <h3 style={{ margin: '0 0 16px', color: 'var(--gray-900)', fontSize: '1.1rem', fontWeight: 700 }}>
              Business Profile & Inventory Health
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '20px' }}>
              <div style={{ background: 'var(--gray-50)', padding: '16px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--gray-200)' }}>
                <h4 style={{ margin: '0 0 8px', fontSize: '0.85rem', color: 'var(--gray-500)', textTransform: 'uppercase' }}>QR Status Breakdown</h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
                    <span style={{ color: 'var(--gray-700)' }}>Active QR Codes:</span>
                    <strong style={{ color: 'var(--green-500)' }}>{detail?.active_qr_codes || 0}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
                    <span style={{ color: 'var(--gray-700)' }}>Disabled QR Codes:</span>
                    <strong style={{ color: 'var(--yellow-500)' }}>{detail?.disabled_qr_codes || 0}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
                    <span style={{ color: 'var(--gray-700)' }}>Retired QR Codes:</span>
                    <strong style={{ color: 'var(--red-500)' }}>{detail?.retired_qr_codes || 0}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', borderTop: '1px solid var(--gray-200)', paddingTop: '6px' }}>
                    <span style={{ color: 'var(--gray-700)' }}>Transferred Away (Historical):</span>
                    <strong style={{ color: 'var(--gray-600)' }}>{historicalQRs.length}</strong>
                  </div>
                </div>
              </div>

              <div style={{ background: 'var(--gray-50)', padding: '16px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--gray-200)' }}>
                <h4 style={{ margin: '0 0 8px', fontSize: '0.85rem', color: 'var(--gray-500)', textTransform: 'uppercase' }}>Scan & Usage Alerts</h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
                    <span style={{ color: 'var(--gray-700)' }}>Last Scanned (IST):</span>
                    <strong style={{ color: 'var(--gray-900)' }}>{detail?.last_scanned_at_ist || 'Never'}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
                    <span style={{ color: 'var(--gray-700)' }}>Never Scanned Codes:</span>
                    <strong style={{ color: detail?.never_scanned_count > 0 ? 'var(--orange-500)' : 'var(--gray-600)' }}>
                      {detail?.never_scanned_count || 0}
                    </strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
                    <span style={{ color: 'var(--gray-700)' }}>Inactive 30+ Days:</span>
                    <strong style={{ color: detail?.not_scanned_30d_count > 0 ? 'var(--yellow-500)' : 'var(--gray-600)' }}>
                      {detail?.not_scanned_30d_count || 0}
                    </strong>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Quick Preview of Top Active QRs */}
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <h3 style={{ margin: 0, color: 'var(--gray-900)', fontSize: '1.05rem', fontWeight: 700 }}>
                Active QR Codes Quick List
              </h3>
              <button className="btn btn-outline btn-sm" onClick={() => setActiveTab('active')}>
                View All Active ({activeQRs.length}) →
              </button>
            </div>
            {activeQRs.length === 0 ? (
              <p style={{ color: 'var(--gray-500)', fontStyle: 'italic', margin: '8px 0' }}>No active QR codes assigned.</p>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '12px' }}>
                {activeQRs.slice(0, 6).map((q) => (
                  <div
                    key={q.id}
                    onClick={() => setSelectedQR(q)}
                    style={{
                      background: 'var(--gray-50)',
                      border: '1px solid var(--gray-200)',
                      borderRadius: 'var(--radius-sm)',
                      padding: '12px',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      transition: 'all 0.15s ease',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = 'var(--primary-400)';
                      e.currentTarget.style.transform = 'translateY(-1px)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = 'var(--gray-200)';
                      e.currentTarget.style.transform = 'none';
                    }}
                  >
                    <div>
                      <strong style={{ fontFamily: 'monospace', color: 'var(--primary-600)', fontSize: '0.95rem' }}>{q.qr_id}</strong>
                      <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {q.destination_url}
                      </div>
                    </div>
                    <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--gray-800)', background: 'var(--gray-200)', padding: '2px 8px', borderRadius: '4px' }}>
                      {q.total_scans} scans
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab 2: ACTIVE QRs */}
      {activeTab === 'active' && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '10px' }}>
            <h3 style={{ margin: 0, color: 'var(--gray-900)', fontSize: '1.05rem', fontWeight: 700 }}>
              🟢 Active QR Codes ({activeQRs.length})
            </h3>
            {isAdmin && selectedQrIds.length > 0 && (
              <button
                className="btn btn-warning btn-sm"
                onClick={() => openConfirmModal('deactivate_selected')}
              >
                ⏸️ Deactivate {selectedQrIds.length} Selected
              </button>
            )}
          </div>

          {activeQRs.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--gray-500)' }}>
              <span style={{ fontSize: '2.5rem' }}>🟢</span>
              <p style={{ marginTop: '8px' }}>No active QR codes for {decodedClientName}.</p>
            </div>
          ) : (
            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    {isAdmin && (
                      <th style={{ width: '40px' }}>
                        <input
                          type="checkbox"
                          checked={selectedQrIds.length === activeQRs.length && activeQRs.length > 0}
                          onChange={(e) => handleSelectAll(e, activeQRs)}
                        />
                      </th>
                    )}
                    <th>QR ID</th>
                    <th>Destination URL</th>
                    <th>Total Scans (IST)</th>
                    <th>Last Scanned (IST)</th>
                    <th>Assigned Date (IST)</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {activeQRs.map((qr) => (
                    <tr key={qr.id}>
                      {isAdmin && (
                        <td>
                          <input
                            type="checkbox"
                            checked={selectedQrIds.includes(qr.qr_id)}
                            onChange={() => handleToggleSelect(qr.qr_id)}
                          />
                        </td>
                      )}
                      <td>
                        <strong
                          style={{ color: 'var(--primary-600)', fontFamily: 'monospace', cursor: 'pointer' }}
                          onClick={() => setSelectedQR(qr)}
                          title="Click to view details"
                        >
                          {qr.qr_id}
                        </strong>
                      </td>
                      <td style={{ maxWidth: '280px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        <a href={qr.destination_url} target="_blank" rel="noreferrer" style={{ color: 'var(--primary-600)', fontSize: '0.85rem' }}>
                          {qr.destination_url}
                        </a>
                      </td>
                      <td>
                        <strong style={{ color: 'var(--gray-900)' }}>{qr.total_scans.toLocaleString()}</strong>
                      </td>
                      <td style={{ fontSize: '0.8rem', color: 'var(--gray-600)' }}>
                        {qr.last_scanned_at_ist || 'Never'}
                      </td>
                      <td style={{ fontSize: '0.8rem', color: 'var(--gray-600)' }}>
                        {qr.assigned_at_ist || '-'}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <div style={{ display: 'inline-flex', gap: '6px' }}>
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => setSelectedQR(qr)}
                          >
                            Details
                          </button>
                          {isAdmin && (
                            <button
                              className="btn btn-warning btn-sm"
                              onClick={() => openConfirmModal('deactivate_single', qr.qr_id)}
                            >
                              Deactivate
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Tab 3: DISABLED QRs */}
      {activeTab === 'disabled' && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '10px' }}>
            <h3 style={{ margin: 0, color: 'var(--gray-900)', fontSize: '1.05rem', fontWeight: 700 }}>
              ⏸️ Disabled QR Codes ({disabledQRs.length})
            </h3>
            {isAdmin && selectedQrIds.length > 0 && (
              <button
                className="btn btn-success btn-sm"
                onClick={() => openConfirmModal('activate_selected')}
              >
                ✅ Reactivate {selectedQrIds.length} Selected
              </button>
            )}
          </div>

          {disabledQRs.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--gray-500)' }}>
              <span style={{ fontSize: '2.5rem' }}>✨</span>
              <p style={{ marginTop: '8px' }}>No disabled QR codes. All assigned codes are currently active!</p>
            </div>
          ) : (
            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    {isAdmin && (
                      <th style={{ width: '40px' }}>
                        <input
                          type="checkbox"
                          checked={selectedQrIds.length === disabledQRs.length && disabledQRs.length > 0}
                          onChange={(e) => handleSelectAll(e, disabledQRs)}
                        />
                      </th>
                    )}
                    <th>QR ID</th>
                    <th>Destination URL</th>
                    <th>Total Scans (IST)</th>
                    <th>Last Scanned (IST)</th>
                    <th>Disabled Date (IST)</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {disabledQRs.map((qr) => (
                    <tr key={qr.id}>
                      {isAdmin && (
                        <td>
                          <input
                            type="checkbox"
                            checked={selectedQrIds.includes(qr.qr_id)}
                            onChange={() => handleToggleSelect(qr.qr_id)}
                          />
                        </td>
                      )}
                      <td>
                        <strong
                          style={{ color: 'var(--yellow-600)', fontFamily: 'monospace', cursor: 'pointer' }}
                          onClick={() => setSelectedQR(qr)}
                          title="Click to view details"
                        >
                          {qr.qr_id}
                        </strong>
                      </td>
                      <td style={{ maxWidth: '280px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        <span style={{ color: 'var(--gray-500)', fontSize: '0.85rem' }}>{qr.destination_url}</span>
                      </td>
                      <td>
                        <strong style={{ color: 'var(--gray-900)' }}>{qr.total_scans.toLocaleString()}</strong>
                      </td>
                      <td style={{ fontSize: '0.8rem', color: 'var(--gray-600)' }}>
                        {qr.last_scanned_at_ist || 'Never'}
                      </td>
                      <td style={{ fontSize: '0.8rem', color: 'var(--gray-600)' }}>
                        {qr.deactivated_at_ist || '-'}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <div style={{ display: 'inline-flex', gap: '6px' }}>
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => setSelectedQR(qr)}
                          >
                            Details
                          </button>
                          {isAdmin && (
                            <button
                              className="btn btn-success btn-sm"
                              onClick={() => openConfirmModal('activate_single', qr.qr_id)}
                            >
                              Reactivate
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Tab 4: HISTORICAL QRs (Transferred away) */}
      {activeTab === 'historical' && (
        <div className="card">
          <div style={{ marginBottom: '16px' }}>
            <h3 style={{ margin: '0 0 4px', color: 'var(--gray-900)', fontSize: '1.05rem', fontWeight: 700 }}>
              📜 Historical QR Codes ({historicalQRs.length})
            </h3>
            <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--gray-500)' }}>
              These QR codes were previously assigned to {decodedClientName} and later transferred to another business.
              Historical scans recorded during this business's ownership remain permanently attributed here.
            </p>
          </div>

          {historicalQRs.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--gray-500)' }}>
              <span style={{ fontSize: '2.5rem' }}>📁</span>
              <p style={{ marginTop: '8px' }}>No historical transfers. All QRs ever assigned are still currently owned.</p>
            </div>
          ) : (
            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>QR ID</th>
                    <th>Historical Destination</th>
                    <th>Attributed Scans</th>
                    <th>Assignment Duration</th>
                    <th>Current Status</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {historicalQRs.map((qr) => (
                    <tr key={qr.id}>
                      <td>
                        <strong
                          style={{ color: 'var(--gray-700)', fontFamily: 'monospace', cursor: 'pointer' }}
                          onClick={() => setSelectedQR(qr)}
                        >
                          {qr.qr_id}
                        </strong>
                      </td>
                      <td style={{ maxWidth: '280px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        <span style={{ color: 'var(--gray-500)', fontSize: '0.85rem' }}>{qr.destination_url}</span>
                      </td>
                      <td>
                        <strong style={{ color: 'var(--gray-900)' }}>{qr.total_scans.toLocaleString()}</strong>
                      </td>
                      <td style={{ fontSize: '0.78rem', color: 'var(--gray-500)' }}>
                        {qr.assigned_at_ist} → {qr.deactivated_at_ist || 'Transferred'}
                      </td>
                      <td>
                        <span className="status-pill unassigned">TRANSFERRED</span>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => setSelectedQR(qr)}
                        >
                          View History
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Tab 5: SCAN ANALYTICS */}
      {activeTab === 'analytics' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '10px' }}>
              <h3 style={{ margin: 0, color: 'var(--gray-900)', fontSize: '1.05rem', fontWeight: 700 }}>
                📊 Scan Activity Trend (Asia/Kolkata IST)
              </h3>
              <div style={{ display: 'flex', gap: '6px' }}>
                {[7, 30, 90].map((d) => (
                  <button
                    key={d}
                    className={`btn btn-sm ${analyticsDays === d ? 'btn-primary' : 'btn-outline'}`}
                    onClick={() => setAnalyticsDays(d)}
                  >
                    {d} Days
                  </button>
                ))}
              </div>
            </div>

            {analytics?.daily_scans && analytics.daily_scans.length > 0 ? (
              <div className="drawer-chart-container">
                <div className="drawer-bar-chart" style={{ height: '160px' }}>
                  {analytics.daily_scans.map((day) => {
                    const maxVal = Math.max(...analytics.daily_scans.map((x) => x.count), 1);
                    const pct = Math.min(100, Math.round((day.count / maxVal) * 100));
                    return (
                      <div key={day.date} className="drawer-bar-col" title={`${day.date}: ${day.count} scans`}>
                        <div className="drawer-bar-val">{day.count > 0 ? day.count : ''}</div>
                        <div className="drawer-bar-track" style={{ height: '110px' }}>
                          <div className="drawer-bar-fill" style={{ height: `${Math.max(pct, 4)}%` }} />
                        </div>
                        <span className="drawer-bar-date">{day.date.slice(5)}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <p style={{ color: 'var(--gray-500)', fontStyle: 'italic' }}>No daily scan activity recorded.</p>
            )}
          </div>

          {/* Top Scanned Codes */}
          <div className="card">
            <h3 style={{ margin: '0 0 14px', color: 'var(--gray-900)', fontSize: '1.05rem', fontWeight: 700 }}>
              🏆 Top QR Codes by Scans
            </h3>
            {analytics?.top_qr_codes && analytics.top_qr_codes.length > 0 ? (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '12px' }}>
                {analytics.top_qr_codes.map((q, idx) => (
                  <div
                    key={q.qr_id}
                    style={{
                      background: 'var(--gray-50)',
                      border: '1px solid var(--gray-200)',
                      borderRadius: 'var(--radius-sm)',
                      padding: '12px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                    }}
                  >
                    <div>
                      <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--gray-500)', marginRight: '6px' }}>
                        #{idx + 1}
                      </span>
                      <strong style={{ fontFamily: 'monospace', color: 'var(--primary-600)' }}>{q.qr_id}</strong>
                    </div>
                    <span style={{ fontWeight: 800, color: 'var(--gray-900)' }}>{q.total_scans} scans</span>
                  </div>
                ))}
              </div>
            ) : (
              <p style={{ color: 'var(--gray-500)', fontStyle: 'italic' }}>No scans recorded yet.</p>
            )}
          </div>
        </div>
      )}

      {/* Tab 6: ASSIGNMENT HISTORY TIMELINE */}
      {activeTab === 'history' && (
        <div className="card">
          <h3 style={{ margin: '0 0 16px', color: 'var(--gray-900)', fontSize: '1.05rem', fontWeight: 700 }}>
            ⏱️ Complete Assignment History for {decodedClientName}
          </h3>
          {allItems.length === 0 ? (
            <p style={{ color: 'var(--gray-500)', fontStyle: 'italic' }}>No assignments found.</p>
          ) : (
            <div className="history-timeline">
              {allItems.map((item) => (
                <div key={item.id} className="timeline-item">
                  <div className="timeline-marker">{item.is_current_owner ? '🟢' : '⚪'}</div>
                  <div className="timeline-content">
                    <div className="timeline-header">
                      <strong className="timeline-business" style={{ fontFamily: 'monospace' }}>
                        {item.qr_id}
                      </strong>
                      <span className={`status-pill ${item.is_current_owner ? 'active' : 'unassigned'}`}>
                        {item.is_current_owner ? 'CURRENTLY ASSIGNED' : 'TRANSFERRED'}
                      </span>
                    </div>
                    <div className="timeline-url">
                      Destination: <a href={item.destination_url} target="_blank" rel="noreferrer">{item.destination_url}</a>
                    </div>
                    <div className="timeline-dates">
                      <span>Assigned: {item.assigned_at_ist}</span>
                      {item.deactivated_at_ist && <span>Ended: {item.deactivated_at_ist}</span>}
                      <span>Attributed Scans: {item.total_scans}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Confirmation Modal */}
      {modalConfig.isOpen && (
        <div className="modal-backdrop" onClick={() => setModalConfig((prev) => ({ ...prev, isOpen: false }))}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 style={{ margin: 0, color: 'var(--gray-900)' }}>{modalConfig.title}</h3>
              <button
                className="close-btn"
                onClick={() => setModalConfig((prev) => ({ ...prev, isOpen: false }))}
              >
                ✕
              </button>
            </div>
            <p style={{ color: 'var(--gray-600)', lineHeight: 1.5, fontSize: '0.92rem', marginBottom: '20px' }}>
              {modalConfig.message}
            </p>
            <div className="modal-actions-bar">
              <button className="btn btn-primary" onClick={handleModalConfirm} disabled={loading}>
                {loading ? 'Processing...' : 'Confirm'}
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => setModalConfig((prev) => ({ ...prev, isOpen: false }))}
                disabled={loading}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* QR Details Slide-In Drawer */}
      {selectedQR && (
        <QRDetailDrawer
          qr={selectedQR}
          onClose={() => setSelectedQR(null)}
          onUpdated={() => {
            fetchDetail();
            fetchAnalytics();
          }}
        />
      )}
    </div>
  );
}
