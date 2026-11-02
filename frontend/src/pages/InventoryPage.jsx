import { useState, useEffect } from 'react';
import { qrAPI, printAPI } from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function InventoryPage() {
  const { isAdmin } = useAuth();
  const [qrCodes, setQrCodes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [selected, setSelected] = useState(new Set());
  const [detailQR, setDetailQR] = useState(null);
  const [history, setHistory] = useState(null);
  const [toast, setToast] = useState(null);
  const [showReassign, setShowReassign] = useState(false);
  const [reassignForm, setReassignForm] = useState({
    business_name: '', destination_url: '', notes: '', confirm_reassignment: false,
  });
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    loadQRCodes();
  }, [page, statusFilter]);

  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(null), 3000);
      return () => clearTimeout(t);
    }
  }, [toast]);

  const loadQRCodes = async () => {
    setLoading(true);
    try {
      const params = { page, per_page: 20 };
      if (statusFilter) params.status = statusFilter;
      if (search) params.search = search;
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

  const handleSearch = () => {
    setPage(1);
    loadQRCodes();
  };

  const openDetail = async (qr) => {
    setDetailQR(qr);
    try {
      const res = await qrAPI.getHistory(qr.qr_id);
      setHistory(res.data);
    } catch (err) {
      setHistory(null);
    }
  };

  const handleDeactivate = async () => {
    if (!detailQR) return;
    setActionLoading(true);
    try {
      await qrAPI.deactivate(detailQR.qr_id);
      setToast({ type: 'success', message: `${detailQR.qr_id} deactivated` });
      setDetailQR(null);
      loadQRCodes();
    } catch (err) {
      setToast({ type: 'error', message: err.response?.data?.detail || 'Failed' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleRetire = async () => {
    if (!detailQR || !confirm(`Retire ${detailQR.qr_id}? This is permanent.`)) return;
    setActionLoading(true);
    try {
      await qrAPI.retire(detailQR.qr_id);
      setToast({ type: 'success', message: `${detailQR.qr_id} retired` });
      setDetailQR(null);
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
      setToast({ type: 'success', message: `${detailQR.qr_id} recovered` });
      setDetailQR(null);
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
      setToast({ type: 'error', message: 'Please confirm reassignment' });
      return;
    }
    setActionLoading(true);
    try {
      await qrAPI.reassign(detailQR.qr_id, reassignForm);
      setToast({ type: 'success', message: `${detailQR.qr_id} reassigned!` });
      setShowReassign(false);
      setDetailQR(null);
      setReassignForm({ business_name: '', destination_url: '', notes: '', confirm_reassignment: false });
      loadQRCodes();
    } catch (err) {
      setToast({ type: 'error', message: err.response?.data?.detail || 'Failed' });
    } finally {
      setActionLoading(false);
    }
  };

  const toggleSelect = (id) => {
    const newSet = new Set(selected);
    if (newSet.has(id)) newSet.delete(id);
    else newSet.add(id);
    setSelected(newSet);
  };

  const handleBulkPDF = async () => {
    try {
      const res = await printAPI.exportPDF({
        qr_ids: Array.from(selected),
        qr_size_mm: 30,
        show_labels: true,
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'qr_codes.pdf';
      a.click();
      URL.revokeObjectURL(url);
      setToast({ type: 'success', message: 'PDF downloaded!' });
    } catch (err) {
      setToast({ type: 'error', message: 'PDF export failed' });
    }
  };

  const handleBulkZIP = async () => {
    try {
      const res = await printAPI.exportZIP({
        qr_ids: Array.from(selected),
        qr_size_mm: 30,
        show_labels: true,
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'qr_codes.zip';
      a.click();
      URL.revokeObjectURL(url);
      setToast({ type: 'success', message: 'ZIP downloaded!' });
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
    return <span className={`badge ${map[status] || ''}`}>● {status}</span>;
  };

  const formatDate = (d) => {
    if (!d) return '—';
    return new Date(d).toLocaleDateString('en-IN', {
      day: 'numeric', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  };

  return (
    <div>
      {toast && <div className={`toast toast-${toast.type}`}>{toast.message}</div>}

      <div className="page-header">
        <h1 className="page-title">QR Inventory</h1>
        <p className="page-subtitle">{total} QR codes total</p>
      </div>

      {/* Search */}
      <div className="search-bar">
        <span className="search-icon">🔍</span>
        <input
          type="text"
          placeholder="Search by QR ID, business, or token..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
        />
      </div>

      {/* Filters */}
      <div className="filter-chips">
        {['', 'unassigned', 'active', 'disabled', 'retired'].map((s) => (
          <button
            key={s}
            className={`chip ${statusFilter === s ? 'active' : ''}`}
            onClick={() => { setStatusFilter(s); setPage(1); }}
          >
            {s || 'All'}
          </button>
        ))}
      </div>

      {/* QR List */}
      {loading ? (
        <div className="loading-spinner"><div className="spinner" /></div>
      ) : qrCodes.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📭</div>
          <h3>No QR Codes Found</h3>
          <p>Try adjusting your search or generate new QR codes.</p>
        </div>
      ) : (
        <div className="qr-list">
          {qrCodes.map((qr) => (
            <div key={qr.id} className="qr-item" onClick={() => openDetail(qr)}>
              <div className="checkbox-wrapper" onClick={(e) => e.stopPropagation()}>
                <input
                  type="checkbox"
                  checked={selected.has(qr.id)}
                  onChange={() => toggleSelect(qr.id)}
                />
              </div>
              <div className="qr-icon">📱</div>
              <div className="qr-info">
                <div className="qr-id">{qr.qr_id}</div>
                <div className="qr-business">
                  {qr.current_business_name || 'Not assigned'}
                </div>
              </div>
              <div className="qr-actions">
                {getStatusBadge(qr.status)}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="pagination">
          <button onClick={() => setPage(p => p - 1)} disabled={page <= 1}>← Prev</button>
          <span className="page-info">{page} / {totalPages}</span>
          <button onClick={() => setPage(p => p + 1)} disabled={page >= totalPages}>Next →</button>
        </div>
      )}

      {/* Bulk Actions */}
      {selected.size > 0 && (
        <div className="bulk-actions">
          <span className="bulk-count">{selected.size} selected</span>
          <div className="bulk-btns">
            <button className="btn btn-sm btn-primary" onClick={handleBulkPDF}>📄 PDF</button>
            <button className="btn btn-sm btn-outline" style={{ color: 'white', borderColor: 'rgba(255,255,255,0.3)' }} onClick={handleBulkZIP}>📦 ZIP</button>
            <button className="btn btn-sm btn-ghost" style={{ color: 'white' }} onClick={() => setSelected(new Set())}>✕</button>
          </div>
        </div>
      )}

      {/* Detail Modal */}
      {detailQR && (
        <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && setDetailQR(null)}>
          <div className="modal-content">
            <h3 className="modal-title">{detailQR.qr_id} Details</h3>

            <div className="detail-section">
              <div className="detail-row">
                <span className="detail-label">Status</span>
                <span className="detail-value">{getStatusBadge(detailQR.status)}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Token</span>
                <span className="detail-value" style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{detailQR.token}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Business</span>
                <span className="detail-value">{detailQR.current_business_name || '—'}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Destination</span>
                <span className="detail-value" style={{ fontSize: '0.78rem' }}>
                  {detailQR.current_destination ? (
                    <a href={detailQR.current_destination} target="_blank" rel="noreferrer" style={{ color: 'var(--primary-600)' }}>
                      {detailQR.current_destination}
                    </a>
                  ) : '—'}
                </span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Redirect URL</span>
                <span className="detail-value" style={{ fontSize: '0.75rem', fontFamily: 'monospace' }}>
                  {detailQR.redirect_url}
                </span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Created</span>
                <span className="detail-value">{formatDate(detailQR.created_at)}</span>
              </div>
            </div>

            {/* Actions */}
            {isAdmin && (
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '16px' }}>
                {detailQR.status === 'active' && (
                  <>
                    <button className="btn btn-sm btn-outline" onClick={() => setShowReassign(true)}>🔄 Reassign</button>
                    <button className="btn btn-sm btn-danger" onClick={handleDeactivate} disabled={actionLoading}>⏸ Deactivate</button>
                  </>
                )}
                {detailQR.status === 'unassigned' && (
                  <button className="btn btn-sm btn-danger" onClick={handleRetire} disabled={actionLoading}>🚫 Retire</button>
                )}
                {detailQR.status === 'retired' && (
                  <button className="btn btn-sm btn-success" onClick={handleRecover} disabled={actionLoading}>♻️ Recover</button>
                )}
              </div>
            )}

            {/* Assignment History */}
            {history && history.assignments.length > 0 && (
              <div>
                <h4 style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: '12px', color: 'var(--gray-700)' }}>
                  📋 Assignment History
                </h4>
                <div className="timeline">
                  {history.assignments.map((a, i) => (
                    <div key={a.id} className={`timeline-item ${a.is_active ? '' : 'inactive'}`}>
                      <div className="tl-header">
                        {a.business_name} {a.is_active && <span className="badge badge-active" style={{ marginLeft: '6px' }}>Current</span>}
                      </div>
                      <div className="tl-meta">
                        <div>→ {a.destination_url}</div>
                        <div>Assigned by {a.assigned_by_name} on {formatDate(a.assigned_at)}</div>
                        {a.deactivated_at && (
                          <div>Deactivated by {a.deactivated_by_name} on {formatDate(a.deactivated_at)}</div>
                        )}
                        {a.notes && <div style={{ fontStyle: 'italic' }}>"{a.notes}"</div>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <button className="btn btn-ghost btn-block" onClick={() => setDetailQR(null)} style={{ marginTop: '12px' }}>
              Close
            </button>
          </div>
        </div>
      )}

      {/* Reassign Modal */}
      {showReassign && (
        <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && setShowReassign(false)}>
          <div className="modal-content">
            <h3 className="modal-title">Reassign {detailQR?.qr_id}</h3>
            <div style={{ background: 'var(--yellow-100)', padding: '10px 14px', borderRadius: '8px', marginBottom: '16px', fontSize: '0.82rem', color: '#a16207' }}>
              ⚠️ The current assignment to <strong>{detailQR?.current_business_name}</strong> will be deactivated.
            </div>
            <form onSubmit={handleReassign}>
              <div className="form-group">
                <label className="form-label">New Business / Campaign *</label>
                <input type="text" className="form-input" required
                  value={reassignForm.business_name}
                  onChange={(e) => setReassignForm({ ...reassignForm, business_name: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">New Destination URL *</label>
                <input type="url" className="form-input" required
                  value={reassignForm.destination_url}
                  onChange={(e) => setReassignForm({ ...reassignForm, destination_url: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Notes</label>
                <textarea className="form-input"
                  value={reassignForm.notes}
                  onChange={(e) => setReassignForm({ ...reassignForm, notes: e.target.value })} />
              </div>
              <div className="checkbox-wrapper" style={{ marginBottom: '16px' }}>
                <input type="checkbox" checked={reassignForm.confirm_reassignment}
                  onChange={(e) => setReassignForm({ ...reassignForm, confirm_reassignment: e.target.checked })} />
                <span className="checkbox-label">I confirm this reassignment</span>
              </div>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button type="button" className="btn btn-ghost" style={{ flex: 1 }} onClick={() => setShowReassign(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" style={{ flex: 2 }} disabled={actionLoading || !reassignForm.confirm_reassignment}>
                  {actionLoading ? 'Reassigning...' : '🔄 Reassign'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
