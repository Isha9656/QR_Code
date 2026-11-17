import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { qrAPI, printAPI } from '../services/api';
import { useAuth } from '../context/AuthContext';
import QRDetailDrawer from '../components/QRDetailDrawer';

export default function InventoryPage() {
  const { isAdmin } = useAuth();
  const navigate = useNavigate();

  const [qrCodes, setQrCodes] = useState([]);
  const [stats, setStats] = useState({ total: 0, unassigned: 0, active: 0, disabled: 0, retired: 0 });
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [scanActivity, setScanActivity] = useState('all');
  const [revealedTokens, setRevealedTokens] = useState(new Set());
  const [selected, setSelected] = useState(new Set());
  const [detailQR, setDetailQR] = useState(null);
  const [previewBlobUrl, setPreviewBlobUrl] = useState(null);
  const [history, setHistory] = useState(null);
  const [toast, setToast] = useState(null);
  const [showReassign, setShowReassign] = useState(false);
  const [reassignForm, setReassignForm] = useState({
    business_name: '', destination_url: '', notes: '', confirm_reassignment: false,
  });
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    loadStats();
    loadQRCodes();
  }, [page, statusFilter, scanActivity]);

  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(null), 3500);
      return () => clearTimeout(t);
    }
  }, [toast]);

  const toggleTokenReveal = (id) => {
    setRevealedTokens(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleExportCSV = async () => {
    try {
      setToast({ type: 'info', message: 'Generating CSV export...' });
      const params = {};
      if (statusFilter) params.status = statusFilter;
      if (search) params.search = search;
      if (scanActivity && scanActivity !== 'all') params.scan_activity = scanActivity;
      const res = await qrAPI.exportCSV(params);
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `qr_inventory_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      setToast({ type: 'success', message: 'CSV exported successfully!' });
    } catch (err) {
      console.error(err);
      setToast({ type: 'error', message: 'Failed to export CSV' });
    }
  };

  const loadStats = async () => {
    try {
      const res = await qrAPI.getStats();
      setStats(res.data);
    } catch (err) {
      console.error('Failed to load stats', err);
    }
  };

  const loadQRCodes = async () => {
    setLoading(true);
    try {
      const params = { page, per_page: 20 };
      if (statusFilter) params.status = statusFilter;
      if (search) params.search = search;
      if (scanActivity && scanActivity !== 'all') params.scan_activity = scanActivity;
      const res = await qrAPI.list(params);
      setQrCodes(res.data.items);
      setTotalPages(res.data.total_pages);
      setTotal(res.data.total);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (e) => {
    if (e) e.preventDefault();
    setPage(1);
    loadQRCodes();
  };

  const clearSearch = () => {
    setSearch('');
    setPage(1);
    setTimeout(() => loadQRCodes(), 10);
  };

  const closeDetail = () => {
    if (previewBlobUrl) {
      URL.revokeObjectURL(previewBlobUrl);
      setPreviewBlobUrl(null);
    }
    setDetailQR(null);
  };

  const openDetail = async (qr) => {
    if (previewBlobUrl) {
      URL.revokeObjectURL(previewBlobUrl);
      setPreviewBlobUrl(null);
    }
    setDetailQR(qr);
    try {
      const res = await qrAPI.getHistory(qr.qr_id);
      setHistory(res.data);
    } catch (err) {
      setHistory(null);
    }
    try {
      const imgRes = await printAPI.exportPNG(qr.id, 240);
      setPreviewBlobUrl(URL.createObjectURL(imgRes.data));
    } catch (err) {
      // Fallback handled via query token in img src
    }
  };

  const handleDeactivate = async () => {
    if (!detailQR) return;
    setActionLoading(true);
    try {
      await qrAPI.deactivate(detailQR.qr_id);
      setToast({ type: 'success', message: `${detailQR.qr_id} deactivated successfully` });
      closeDetail();
      loadStats();
      loadQRCodes();
    } catch (err) {
      setToast({ type: 'error', message: err.response?.data?.detail || 'Failed' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleRetire = async () => {
    if (!detailQR || !confirm(`Permanently retire ${detailQR.qr_id}? This code can only be restored by an Admin.`)) return;
    setActionLoading(true);
    try {
      await qrAPI.retire(detailQR.qr_id);
      setToast({ type: 'success', message: `${detailQR.qr_id} retired` });
      closeDetail();
      loadStats();
      loadQRCodes();
    } catch (err) {
      setToast({ type: 'error', message: err.response?.data?.detail || 'Failed' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleRecover = async () => {
    if (!detailQR) return;
    setActionLoading(true);
    try {
      await qrAPI.recover(detailQR.qr_id);
      setToast({ type: 'success', message: `${detailQR.qr_id} recovered to unassigned state` });
      closeDetail();
      loadStats();
      loadQRCodes();
    } catch (err) {
      setToast({ type: 'error', message: err.response?.data?.detail || 'Failed' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleReassign = async (e) => {
    e.preventDefault();
    if (!reassignForm.confirm_reassignment) {
      setToast({ type: 'error', message: 'Please check the confirmation box' });
      return;
    }
    setActionLoading(true);
    try {
      await qrAPI.reassign(detailQR.qr_id, reassignForm);
      setToast({ type: 'success', message: `${detailQR.qr_id} reassigned to ${reassignForm.business_name}!` });
      setShowReassign(false);
      closeDetail();
      setReassignForm({ business_name: '', destination_url: '', notes: '', confirm_reassignment: false });
      loadStats();
      loadQRCodes();
    } catch (err) {
      setToast({ type: 'error', message: err.response?.data?.detail || 'Failed' });
    } finally {
      setActionLoading(false);
    }
  };

  // Selection handlers
  const toggleSelect = (id) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };

  const selectAllOnPage = () => {
    const next = new Set(selected);
    qrCodes.forEach(q => next.add(q.id));
    setSelected(next);
  };

  const selectAllUnassignedOnPage = () => {
    const next = new Set(selected);
    qrCodes.filter(q => q.status === 'unassigned').forEach(q => next.add(q.id));
    setSelected(next);
  };

  const clearSelection = () => {
    setSelected(new Set());
  };

  const handleGoToPrintStudio = () => {
    const selectedIds = Array.from(selected);
    navigate('/print-studio', { state: { selectedIds } });
  };

  const handleDownloadSinglePNG = async (qrId, qrCodeStr) => {
    try {
      const res = await printAPI.exportPNG(qrId, 400);
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${qrCodeStr}.png`;
      a.click();
      URL.revokeObjectURL(url);
      setToast({ type: 'success', message: `Downloaded ${qrCodeStr}.png` });
    } catch (err) {
      setToast({ type: 'error', message: 'PNG download failed' });
    }
  };

  const handleBulkZIP = async () => {
    if (selected.size === 0) return;
    try {
      const res = await printAPI.exportZIP({
        qr_ids: Array.from(selected),
        qr_size_mm: 30,
        show_labels: true,
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'qr_codes_archive.zip';
      a.click();
      URL.revokeObjectURL(url);
      setToast({ type: 'success', message: 'ZIP archive downloaded!' });
    } catch (err) {
      setToast({ type: 'error', message: 'ZIP export failed' });
    }
  };

  const getStatusBadge = (status) => {
    const map = {
      unassigned: 'badge-unassigned',
      active: 'badge-active',
      disabled: 'badge-disabled',
      retired: 'badge-retired',
    };
    return <span className={`badge ${map[status] || ''}`}>● {status.toUpperCase()}</span>;
  };

  const formatDate = (d) => {
    if (!d) return '—';
    return new Date(d).toLocaleDateString('en-IN', {
      day: 'numeric', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  };

  const hasSelectedNonUnassigned = Array.from(selected).some(id => {
    const item = qrCodes.find(q => q.id === id);
    return item && item.status !== 'unassigned';
  });

  return (
    <div className="inventory-dashboard">
      {toast && <div className={`toast toast-${toast.type}`}>{toast.message}</div>}

      {/* Top Header */}
      <div className="page-header-flex">
        <div>
          <h1 className="page-title">QR Inventory Management</h1>
          <p className="page-subtitle">Track, filter, print, and assign physical & digital QR codes</p>
        </div>
        <div className="header-actions">
          <button
            className="btn btn-secondary"
            onClick={handleExportCSV}
            title="Export filtered inventory to CSV with Asia/Kolkata timestamps"
          >
            📥 Export CSV
          </button>
          {isAdmin && (
            <button className="btn btn-primary" onClick={() => navigate('/print-studio')}>
              🖨️ Bulk Printing Studio
            </button>
          )}
        </div>
      </div>

      {/* FEATURE 1: Professional Inventory Metric Cards */}
      <div className="metric-cards-grid">
        <div
          className={`metric-card ${statusFilter === '' ? 'active-metric' : ''}`}
          onClick={() => { setStatusFilter(''); setPage(1); }}
        >
          <div className="metric-icon">📦</div>
          <div className="metric-value">{stats.total}</div>
          <div className="metric-label">Total Generated</div>
        </div>

        <div
          className={`metric-card metric-unassigned ${statusFilter === 'unassigned' ? 'active-metric' : ''}`}
          onClick={() => { setStatusFilter('unassigned'); setPage(1); }}
        >
          <div className="metric-icon">⚪</div>
          <div className="metric-value">{stats.unassigned}</div>
          <div className="metric-label">Unassigned (Ready)</div>
        </div>

        <div
          className={`metric-card metric-active ${statusFilter === 'active' ? 'active-metric' : ''}`}
          onClick={() => { setStatusFilter('active'); setPage(1); }}
        >
          <div className="metric-icon">🟢</div>
          <div className="metric-value">{stats.active}</div>
          <div className="metric-label">Active Assigned</div>
        </div>

        <div
          className={`metric-card metric-disabled ${statusFilter === 'disabled' ? 'active-metric' : ''}`}
          onClick={() => { setStatusFilter('disabled'); setPage(1); }}
        >
          <div className="metric-icon">🟡</div>
          <div className="metric-value">{stats.disabled}</div>
          <div className="metric-label">Inactive / Disabled</div>
        </div>

        <div
          className={`metric-card metric-retired ${statusFilter === 'retired' ? 'active-metric' : ''}`}
          onClick={() => { setStatusFilter('retired'); setPage(1); }}
        >
          <div className="metric-icon">🔴</div>
          <div className="metric-value">{stats.retired}</div>
          <div className="metric-label">Retired Codes</div>
        </div>
      </div>

      {/* Search and Filter Toolbar */}
      <div className="toolbar-section">
        <form className="search-bar" onSubmit={handleSearch}>
          <span className="search-icon">🔍</span>
          <input
            type="text"
            placeholder="Search by QR ID (e.g. QR-000001), Business Name, or Token..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {search && (
            <button type="button" className="clear-btn" onClick={clearSearch}>✕</button>
          )}
          <button type="submit" className="search-submit-btn">Search</button>
        </form>

        <div className="filter-chips">
          {[
            { id: '', label: 'All Statuses' },
            { id: 'unassigned', label: '⚪ Unassigned' },
            { id: 'active', label: '🟢 Active' },
            { id: 'disabled', label: '🟡 Inactive' },
            { id: 'retired', label: '🔴 Retired' }
          ].map((s) => (
            <button
              key={s.id}
              className={`chip ${statusFilter === s.id ? 'active' : ''}`}
              onClick={() => { setStatusFilter(s.id); setPage(1); }}
            >
              {s.label}
            </button>
          ))}
          <select
            className="chip select-activity"
            value={scanActivity}
            onChange={(e) => { setScanActivity(e.target.value); setPage(1); }}
            style={{ padding: '6px 12px', borderRadius: '20px', border: '1px solid var(--gray-300)', background: 'white', fontSize: '0.82rem', cursor: 'pointer' }}
          >
            <option value="all">⚡ All Activity</option>
            <option value="has_scans">🎯 Has Scans</option>
            <option value="never_scanned">💤 Never Scanned</option>
            <option value="inactive_30d">⏳ Inactive 30d</option>
          </select>
        </div>
      </div>

      {/* Bulk Selection Actions Bar */}
      <div className="bulk-selection-bar">
        <div className="selection-stats">
          <label className="checkbox-container">
            <input
              type="checkbox"
              checked={qrCodes.length > 0 && qrCodes.every(q => selected.has(q.id))}
              onChange={(e) => e.target.checked ? selectAllOnPage() : clearSelection()}
            />
            <span>Select Page</span>
          </label>
          <button className="text-action-btn" onClick={selectAllUnassignedOnPage}>
            Select All Unassigned ({qrCodes.filter(q => q.status === 'unassigned').length})
          </button>
          {selected.size > 0 && (
            <button className="text-action-btn text-danger" onClick={clearSelection}>
              Clear ({selected.size})
            </button>
          )}
        </div>

        {selected.size > 0 && (
          <div className="selection-actions">
            <span className="selected-counter"><strong>{selected.size}</strong> selected</span>
            {isAdmin && (
              <button
                className="btn btn-sm btn-primary"
                onClick={handleGoToPrintStudio}
                title="Open selected codes in Bulk Printing Studio"
              >
                🖨️ Print in Studio ({selected.size})
              </button>
            )}
            <button className="btn btn-sm btn-secondary" onClick={handleBulkZIP}>
              📦 Download ZIP
            </button>
          </div>
        )}
      </div>

      {hasSelectedNonUnassigned && (
        <div className="alert alert-warning">
          ⚠️ <strong>Notice:</strong> Some selected codes are already active or retired. The Bulk Printing Studio will automatically focus on <em>unassigned</em> codes.
        </div>
      )}

      {/* QR Inventory Grid / List */}
      {loading ? (
        <div className="loading-spinner"><div className="spinner" /></div>
      ) : qrCodes.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📭</div>
          <h3>No QR Codes Found</h3>
          <p>Try searching for a different QR ID or clear your filters.</p>
          <button className="btn btn-secondary" onClick={() => { setSearch(''); setStatusFilter(''); setPage(1); }}>
            Reset Filters
          </button>
        </div>
      ) : (
        <div className="inventory-cards-container">
          {qrCodes.map((qr) => (
            <div
              key={qr.id}
              className={`inventory-card ${selected.has(qr.id) ? 'selected-card' : ''}`}
              onClick={() => openDetail(qr)}
            >
              <div className="card-top-row">
                <div className="checkbox-wrapper" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={selected.has(qr.id)}
                    onChange={() => toggleSelect(qr.id)}
                  />
                </div>
                <div className="qr-id-chip">{qr.qr_id}</div>
                <div className="badge-wrapper">{getStatusBadge(qr.status)}</div>
              </div>

              <div className="card-body">
                {qr.current_business_name ? (
                  <div className="card-business">
                    <span className="biz-icon">🏢</span>
                    <strong>{qr.current_business_name}</strong>
                  </div>
                ) : (
                  <div className="card-business text-muted">
                    <span className="biz-icon">🏷️</span>
                    <em>Ready to Assign</em>
                  </div>
                )}

                {qr.current_destination && (
                  <div className="card-dest">
                    <span className="dest-icon">🔗</span>
                    <a
                      href={qr.current_destination}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="dest-link"
                    >
                      {qr.current_destination}
                    </a>
                  </div>
                )}

                <div className="card-meta">
                  <span>📅 {qr.created_at_ist || formatDate(qr.created_at)}</span>
                  <span
                    className="token-hint"
                    onClick={(e) => { e.stopPropagation(); toggleTokenReveal(qr.id); }}
                    style={{ cursor: 'pointer' }}
                    title="Click to reveal/hide full token"
                  >
                    🔑 {revealedTokens.has(qr.id) ? qr.token : (qr.token?.slice(0, 4) + '••••••••')}
                  </span>
                  {qr.total_scans > 0 && (
                    <span className="scans-count" title={`Last scan: ${qr.last_scanned_at_ist || 'Never'}`}>
                      🎯 {qr.total_scans} scans
                    </span>
                  )}
                </div>
              </div>

              <div className="card-actions-row" onClick={(e) => e.stopPropagation()}>
                <button
                  className="card-action-btn"
                  onClick={() => openDetail(qr)}
                  title="View Details & History"
                >
                  👁️ Details
                </button>
                <button
                  className="card-action-btn"
                  onClick={() => handleDownloadSinglePNG(qr.id, qr.qr_id)}
                  title="Download Sticker PNG"
                >
                  📥 PNG
                </button>
                {qr.status === 'unassigned' && (
                  <button
                    className="card-action-btn action-assign"
                    onClick={() => navigate('/scan')}
                    title="Assign in Scanner"
                  >
                    ⚡ Assign
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="pagination">
          <button
            className="page-btn"
            disabled={page <= 1}
            onClick={() => setPage(p => Math.max(1, p - 1))}
          >
            ← Previous
          </button>
          <span className="page-info">
            Page {page} of {totalPages} ({total} total codes)
          </span>
          <button
            className="page-btn"
            disabled={page >= totalPages}
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
          >
            Next →
          </button>
        </div>
      )}

      {/* QR Details Slide-In Drawer */}
      {detailQR && (
        <QRDetailDrawer
          qr={detailQR}
          onClose={closeDetail}
          onUpdated={() => {
            loadStats();
            loadQRCodes();
          }}
        />
      )}
    </div>
  );
}
