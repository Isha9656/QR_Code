import { useState, useEffect, useRef } from 'react';
import { Html5Qrcode } from 'html5-qrcode';
import { qrAPI } from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function ScanPage() {
  const { isAuthenticated } = useAuth();
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [manualInput, setManualInput] = useState('');
  const [showAssign, setShowAssign] = useState(false);
  const [assignForm, setAssignForm] = useState({
    business_name: '',
    destination_url: '',
    notes: '',
    expiry_date: '',
  });
  const [assignLoading, setAssignLoading] = useState(false);
  const [toast, setToast] = useState(null);
  const scannerRef = useRef(null);
  const html5QrRef = useRef(null);

  const startScanner = async () => {
    setError('');
    setResult(null);
    setScanning(true);

    try {
      const html5Qr = new Html5Qrcode('qr-reader');
      html5QrRef.current = html5Qr;

      await html5Qr.start(
        { facingMode: 'environment' },
        { fps: 10, qrbox: { width: 250, height: 250 } },
        async (decodedText) => {
          await html5Qr.stop();
          html5QrRef.current = null;
          setScanning(false);
          await handleScanResult(decodedText);
        },
        () => {} // ignore errors during scanning
      );
    } catch (err) {
      setScanning(false);
      setError(
        err.toString().includes('Permission')
          ? 'Camera permission denied. Please allow camera access in your browser settings.'
          : 'Unable to start camera. Please ensure no other app is using the camera.'
      );
    }
  };

  const stopScanner = async () => {
    if (html5QrRef.current) {
      try {
        await html5QrRef.current.stop();
      } catch {}
      html5QrRef.current = null;
    }
    setScanning(false);
  };

  const handleScanResult = async (scannedUrl) => {
    // Extract token from URL: /q/TOKEN or /qr/TOKEN
    const match = scannedUrl.match(/\/(?:q|qr)\/([A-Za-z0-9]+)(?:[/?#]|$)/);
    if (!match) {
      // Check if raw token was entered/scanned
      if (/^[A-Za-z0-9]{16,64}$/.test(scannedUrl.trim())) {
        const token = scannedUrl.trim();
        try {
          const res = await qrAPI.resolve(token);
          setResult({ ...res.data, token, qr_id: res.data.qr_id });
          return;
        } catch {
          setResult({ status: 'error', message: 'Failed to resolve QR code' });
          return;
        }
      }
      setResult({ status: 'invalid', message: 'Not a valid QR code from this system' });
      return;
    }

    const token = match[1];
    try {
      const res = await qrAPI.resolve(token);
      setResult({ ...res.data, token, qr_id: res.data.qr_id });
    } catch (err) {
      setResult({ status: 'error', message: 'Failed to resolve QR code' });
    }
  };

  const handleManualLookup = async () => {
    if (!manualInput.trim()) return;
    setError('');

    try {
      const searchVal = manualInput.trim();
      // Check if it's a URL or contains /q/ or /qr/
      if (searchVal.includes('/q/') || searchVal.includes('/qr/')) {
        await handleScanResult(searchVal);
      } else if (searchVal.startsWith('QR-')) {
        // Lookup by QR-ID
        const res = await qrAPI.get(searchVal);
        const qr = res.data;
        setResult({
          status: qr.status,
          destination_url: qr.current_destination,
          business_name: qr.current_business_name,
          token: qr.token,
          qr_id: qr.qr_id,
        });
      } else {
        // Try resolving as token
        await handleScanResult(searchVal);
      }
    } catch (err) {
      setResult({ status: 'not_found', message: 'QR code not found' });
    }
  };

  const handleAssign = async (e) => {
    e.preventDefault();
    if (!result?.token) return;
    setAssignLoading(true);

    try {
      // Use qr_id directly if available, otherwise search by token or pass token directly
      let qrIdentifier = result.qr_id;
      if (!qrIdentifier) {
        const resolveRes = await qrAPI.list({ search: result.token, per_page: 1 });
        if (resolveRes.data.items.length > 0) {
          qrIdentifier = resolveRes.data.items[0].qr_id;
        } else {
          qrIdentifier = result.token;
        }
      }

      const assignData = {
        business_name: assignForm.business_name,
        destination_url: assignForm.destination_url,
        notes: assignForm.notes || undefined,
        expiry_date: assignForm.expiry_date || undefined,
      };

      await qrAPI.assign(qrIdentifier, assignData);
      setToast({ type: 'success', message: 'QR code assigned successfully!' });
      setShowAssign(false);
      setAssignForm({ business_name: '', destination_url: '', notes: '', expiry_date: '' });

      // Refresh result
      const refreshRes = await qrAPI.resolve(result.token);
      setResult({ ...refreshRes.data, token: result.token, qr_id: refreshRes.data.qr_id || qrIdentifier });
    } catch (err) {
      setToast({
        type: 'error',
        message: err.response?.data?.detail || 'Assignment failed',
      });
    } finally {
      setAssignLoading(false);
    }
  };

  useEffect(() => {
    return () => {
      stopScanner();
    };
  }, []);

  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  return (
    <div>
      {toast && (
        <div className={`toast toast-${toast.type}`}>{toast.message}</div>
      )}

      <div className="page-header">
        <h1 className="page-title">Scan QR Code</h1>
        <p className="page-subtitle">Use camera or enter QR ID manually</p>
      </div>

      {/* Scanner */}
      <div className="scanner-container">
        <div className="scanner-viewfinder">
          <div id="qr-reader" style={{ width: '100%' }} />
        </div>

        <div style={{ display: 'flex', gap: '8px', marginTop: '16px' }}>
          {!scanning ? (
            <button className="btn btn-primary btn-block" onClick={startScanner}>
              📷 Start Scanner
            </button>
          ) : (
            <button className="btn btn-danger btn-block" onClick={stopScanner}>
              ⏹ Stop Scanner
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="card" style={{ marginTop: '16px', background: '#fef2f2', borderColor: '#fecaca' }}>
          <p style={{ color: '#dc2626', fontSize: '0.85rem' }}>⚠️ {error}</p>
        </div>
      )}

      {/* Manual Lookup */}
      <div className="card" style={{ marginTop: '16px' }}>
        <h3 className="card-title" style={{ marginBottom: '12px' }}>🔍 Manual Lookup</h3>
        <div style={{ display: 'flex', gap: '8px' }}>
          <input
            type="text"
            className="form-input"
            placeholder="Enter QR-ID (e.g. QR-000001) or URL"
            value={manualInput}
            onChange={(e) => setManualInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleManualLookup()}
          />
          <button className="btn btn-primary" onClick={handleManualLookup}>
            Search
          </button>
        </div>
      </div>

      {/* Scan Result */}
      {result && (
        <div className="card" style={{ marginTop: '16px' }}>
          <h3 className="card-title" style={{ marginBottom: '12px' }}>Scan Result</h3>

          {result.status === 'active' && (
            <div>
              <span className="badge badge-active">● Active</span>
              <div className="detail-row" style={{ marginTop: '12px' }}>
                <span className="detail-label">Business</span>
                <span className="detail-value">{result.business_name}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Destination</span>
                <a
                  href={result.destination_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="detail-value"
                  style={{ color: 'var(--primary-600)', textDecoration: 'underline' }}
                >
                  {result.destination_url}
                </a>
              </div>
            </div>
          )}

          {result.status === 'unassigned' && (
            <div>
              <span className="badge badge-unassigned">● Unassigned</span>
              <p style={{ marginTop: '12px', fontSize: '0.9rem', color: 'var(--gray-600)' }}>
                This QR code has not been activated yet.
              </p>
              {isAuthenticated && (
                <button
                  className="btn btn-success btn-block"
                  style={{ marginTop: '16px' }}
                  onClick={() => setShowAssign(true)}
                >
                  ✨ Assign This QR Code
                </button>
              )}
            </div>
          )}

          {result.status === 'disabled' && (
            <div>
              <span className="badge badge-disabled">● Disabled</span>
              <p style={{ marginTop: '12px', fontSize: '0.9rem', color: 'var(--gray-600)' }}>
                This QR code is currently disabled.
              </p>
            </div>
          )}

          {result.status === 'retired' && (
            <div>
              <span className="badge badge-retired">● Retired</span>
              <p style={{ marginTop: '12px', fontSize: '0.9rem', color: 'var(--gray-600)' }}>
                This QR code has been permanently retired.
              </p>
            </div>
          )}

          {(result.status === 'not_found' || result.status === 'invalid' || result.status === 'error') && (
            <div>
              <p style={{ fontSize: '0.9rem', color: 'var(--red-500)' }}>
                ⚠️ {result.message}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Assignment Modal */}
      {showAssign && (
        <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && setShowAssign(false)}>
          <div className="modal-content">
            <h3 className="modal-title">Assign QR Code</h3>
            <form onSubmit={handleAssign}>
              <div className="form-group">
                <label className="form-label">Business / Campaign Name *</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g., Nasta Ghar"
                  value={assignForm.business_name}
                  onChange={(e) => setAssignForm({ ...assignForm, business_name: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">Destination URL *</label>
                <input
                  type="url"
                  className="form-input"
                  placeholder="https://example.com/review"
                  value={assignForm.destination_url}
                  onChange={(e) => setAssignForm({ ...assignForm, destination_url: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">Notes (optional)</label>
                <textarea
                  className="form-input"
                  placeholder="Any additional notes..."
                  value={assignForm.notes}
                  onChange={(e) => setAssignForm({ ...assignForm, notes: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Expiry Date (optional)</label>
                <input
                  type="datetime-local"
                  className="form-input"
                  value={assignForm.expiry_date}
                  onChange={(e) => setAssignForm({ ...assignForm, expiry_date: e.target.value })}
                />
              </div>
              <div style={{ display: 'flex', gap: '8px', marginTop: '20px' }}>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => setShowAssign(false)}
                  style={{ flex: 1 }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-success"
                  disabled={assignLoading}
                  style={{ flex: 2 }}
                >
                  {assignLoading ? 'Activating...' : '✅ Activate QR'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
