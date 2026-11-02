import { useState } from 'react';
import { qrAPI, printAPI } from '../services/api';
import { useAuth } from '../context/AuthContext';

const PRESETS = [10, 50, 100, 500, 1000];

export default function GeneratePage() {
  const { isAdmin } = useAuth();
  const [quantity, setQuantity] = useState(null);
  const [customQty, setCustomQty] = useState('');
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState(null);
  const [toast, setToast] = useState(null);

  // Print settings
  const [qrSize, setQrSize] = useState(30);
  const [showLabels, setShowLabels] = useState(true);
  const [showPrint, setShowPrint] = useState(false);

  const handleGenerate = async () => {
    const qty = quantity || parseInt(customQty);
    if (!qty || qty < 1) return;
    if (!isAdmin) {
      setToast({ type: 'error', message: 'Admin access required' });
      return;
    }

    setGenerating(true);
    try {
      const res = await qrAPI.bulkGenerate(qty);
      setResult(res.data);
      setToast({ type: 'success', message: `${res.data.length} QR codes generated!` });
    } catch (err) {
      setToast({ type: 'error', message: err.response?.data?.detail || 'Generation failed' });
    } finally {
      setGenerating(false);
    }
  };

  const handleExportPDF = async () => {
    if (!result) return;
    try {
      const ids = result.map(qr => qr.id);
      const res = await printAPI.exportPDF({
        qr_ids: ids,
        qr_size_mm: qrSize,
        show_labels: showLabels,
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `qr_codes_${result[0]?.qr_id}_to_${result[result.length - 1]?.qr_id}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      setToast({ type: 'success', message: 'PDF downloaded!' });
    } catch (err) {
      setToast({ type: 'error', message: 'PDF export failed' });
    }
  };

  const handleExportZIP = async () => {
    if (!result) return;
    try {
      const ids = result.map(qr => qr.id);
      const res = await printAPI.exportZIP({
        qr_ids: ids,
        qr_size_mm: qrSize,
        show_labels: showLabels,
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

  if (toast) {
    setTimeout(() => setToast(null), 3000);
  }

  if (!isAdmin) {
    return (
      <div className="empty-state">
        <div className="empty-icon">🔒</div>
        <h3>Admin Access Required</h3>
        <p>Only administrators can generate QR codes.</p>
      </div>
    );
  }

  return (
    <div>
      {toast && <div className={`toast toast-${toast.type}`}>{toast.message}</div>}

      <div className="page-header">
        <h1 className="page-title">Generate QR Codes</h1>
        <p className="page-subtitle">Create new QR codes in bulk</p>
      </div>

      {!result ? (
        <>
          <div className="card">
            <h3 className="card-title" style={{ marginBottom: '16px' }}>Select Quantity</h3>
            <div className="generate-grid">
              {PRESETS.map((n) => (
                <div
                  key={n}
                  className={`generate-option ${quantity === n ? 'selected' : ''}`}
                  onClick={() => { setQuantity(n); setCustomQty(''); }}
                >
                  <div className="gen-number">{n}</div>
                  <div className="gen-label">QR Codes</div>
                </div>
              ))}
              <div
                className={`generate-option ${quantity === null && customQty ? 'selected' : ''}`}
                onClick={() => setQuantity(null)}
              >
                <div className="gen-number">✏️</div>
                <div className="gen-label">Custom</div>
              </div>
            </div>

            {quantity === null && (
              <div className="form-group">
                <label className="form-label">Custom Quantity</label>
                <input
                  type="number"
                  className="form-input"
                  placeholder="Enter number (1–5000)"
                  min="1"
                  max="5000"
                  value={customQty}
                  onChange={(e) => setCustomQty(e.target.value)}
                />
              </div>
            )}

            <button
              className="btn btn-primary btn-block btn-lg"
              onClick={handleGenerate}
              disabled={generating || (!quantity && !customQty)}
              style={{ marginTop: '16px' }}
            >
              {generating ? (
                <>⏳ Generating...</>
              ) : (
                <>⚡ Generate {quantity || customQty || 0} QR Codes</>
              )}
            </button>
          </div>
        </>
      ) : (
        <>
          {/* Success Result */}
          <div className="card" style={{ borderLeft: '4px solid var(--green-500)' }}>
            <div style={{ textAlign: 'center', padding: '12px 0' }}>
              <div style={{ fontSize: '3rem', marginBottom: '12px' }}>✅</div>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: '8px' }}>
                {result.length} QR Codes Generated
              </h3>
              <p style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>
                {result[0]?.qr_id} → {result[result.length - 1]?.qr_id}
              </p>
            </div>
          </div>

          {/* Print Settings */}
          <div className="card" style={{ marginTop: '16px' }}>
            <div className="card-header">
              <h3 className="card-title">🖨️ Print Settings</h3>
              <button className="btn btn-sm btn-ghost" onClick={() => setShowPrint(!showPrint)}>
                {showPrint ? 'Hide' : 'Show'}
              </button>
            </div>

            {showPrint && (
              <div className="print-settings">
                <div className="form-group">
                  <label className="form-label">QR Size: {qrSize}mm</label>
                  <div className="range-group">
                    <input type="range" min="15" max="80" value={qrSize}
                      onChange={(e) => setQrSize(parseInt(e.target.value))} />
                    <span className="range-value">{qrSize}mm</span>
                  </div>
                </div>
                <div className="checkbox-wrapper">
                  <input type="checkbox" checked={showLabels}
                    onChange={(e) => setShowLabels(e.target.checked)} />
                  <span className="checkbox-label">Show QR ID labels</span>
                </div>
              </div>
            )}
          </div>

          {/* Export Buttons */}
          <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
            <button className="btn btn-primary" style={{ flex: 1 }} onClick={handleExportPDF}>
              📄 Export PDF
            </button>
            <button className="btn btn-outline" style={{ flex: 1 }} onClick={handleExportZIP}>
              📦 Export ZIP
            </button>
          </div>

          {/* Generated List Preview */}
          <div className="card" style={{ marginTop: '16px' }}>
            <h3 className="card-title" style={{ marginBottom: '12px' }}>Generated QR Codes</h3>
            <div className="qr-list" style={{ maxHeight: '300px', overflowY: 'auto' }}>
              {result.slice(0, 50).map((qr) => (
                <div key={qr.id} className="qr-item" style={{ cursor: 'default' }}>
                  <div className="qr-icon">📱</div>
                  <div className="qr-info">
                    <div className="qr-id">{qr.qr_id}</div>
                    <div className="qr-business" style={{ fontFamily: 'monospace', fontSize: '0.7rem' }}>
                      {qr.token}
                    </div>
                  </div>
                  <span className="badge badge-unassigned">● Unassigned</span>
                </div>
              ))}
              {result.length > 50 && (
                <p style={{ textAlign: 'center', padding: '12px', fontSize: '0.8rem', color: 'var(--gray-500)' }}>
                  +{result.length - 50} more...
                </p>
              )}
            </div>
          </div>

          <button
            className="btn btn-ghost btn-block"
            onClick={() => { setResult(null); setQuantity(null); setCustomQty(''); }}
            style={{ marginTop: '16px' }}
          >
            ← Generate More
          </button>
        </>
      )}
    </div>
  );
}
