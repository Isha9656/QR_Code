import { useState, useEffect, useRef } from 'react';
import { Html5Qrcode } from 'html5-qrcode';
import { qrAPI } from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function ScanPage() {
  const { isAuthenticated, isAdmin } = useAuth();
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [manualInput, setManualInput] = useState('');

  // Feature 3 Assignment & Business state
  const [existingBusinesses, setExistingBusinesses] = useState([]);
  const [showAssign, setShowAssign] = useState(false);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [urlPreviewValid, setUrlPreviewValid] = useState(false);
  const [assignForm, setAssignForm] = useState({
    business_name: '',
    destination_url: '',
    notes: '',
    expiry_date: '',
    confirm_reassignment: false,
  });
  const [assignLoading, setAssignLoading] = useState(false);
  const [toast, setToast] = useState(null);
  const scannerRef = useRef(null);
  const html5QrRef = useRef(null);

  useEffect(() => {
    loadBusinesses();
    return () => {
      stopScanner();
    };
  }, []);

  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 3500);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  // Validate URL format for preview
  useEffect(() => {
    try {
      if (assignForm.destination_url.trim().length > 7) {
        let u = assignForm.destination_url.trim();
        if (!u.startsWith('http://') && !u.startsWith('https://')) {
          u = 'https://' + u;
        }
        const parsed = new URL(u);
        setUrlPreviewValid(parsed.protocol === 'http:' || parsed.protocol === 'https:');
      } else {
        setUrlPreviewValid(false);
      }
    } catch {
      setUrlPreviewValid(false);
    }
  }, [assignForm.destination_url]);

  const loadBusinesses = async () => {
    try {
      const res = await qrAPI.getBusinesses();
      setExistingBusinesses(res.data);
    } catch (err) {
      console.error('Failed to load businesses', err);
    }
  };

  const startScanner = async () => {
    setError('');
    setResult(null);
    setScanning(true);

    try {
      const html5Qr = new Html5Qrcode('qr-reader');
      html5QrRef.current = html5Qr;

      await html5Qr.start(
        { facingMode: 'environment' },
        { fps: 12, qrbox: { width: 260, height: 260 } },
        async (decodedText) => {
          await html5Qr.stop();
          html5QrRef.current = null;
          setScanning(false);
          await handleScanResult(decodedText);
        },
        () => {} // silent frame scan
      );
    } catch (err) {
      setScanning(false);
      setError(
        err.toString().includes('Permission')
          ? 'Camera permission was denied. Please allow camera access in your mobile browser permissions.'
          : 'Unable to start camera. Please verify camera hardware or use manual input below.'
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
    let token = null;

    if (match) {
      token = match[1];
    } else if (/^[A-Za-z0-9]{12,64}$/.test(scannedUrl.trim())) {
      token = scannedUrl.trim();
    } else {
      setResult({ status: 'invalid', message: 'Not a recognized QR code from this internal system' });
      return;
    }

    try {
      const res = await qrAPI.resolve(token);
      setResult({ ...res.data, token, qr_id: res.data.qr_id });
      // Reset assign form
      setAssignForm({
        business_name: res.data.business_name || '',
        destination_url: res.data.destination_url || '',
        notes: '',
        expiry_date: '',
        confirm_reassignment: false,
      });
      setShowAssign(res.data.status === 'unassigned');
    } catch (err) {
      setResult({ status: 'error', message: 'Failed to resolve QR token from system' });
    }
  };

  const handleManualLookup = async () => {
    if (!manualInput.trim()) return;
    setError('');

    try {
      const searchVal = manualInput.trim();
      if (searchVal.includes('/q/') || searchVal.includes('/qr/')) {
        await handleScanResult(searchVal);
      } else if (searchVal.startsWith('QR-')) {
        const res = await qrAPI.get(searchVal);
        const qr = res.data;
        setResult({
          status: qr.status,
          destination_url: qr.current_destination,
          business_name: qr.current_business_name,
          token: qr.token,
          qr_id: qr.qr_id,
        });
        setAssignForm({
          business_name: qr.current_business_name || '',
          destination_url: qr.current_destination || '',
          notes: '',
          expiry_date: '',
          confirm_reassignment: false,
        });
        setShowAssign(qr.status === 'unassigned');
      } else {
        await handleScanResult(searchVal);
      }
    } catch (err) {
      setResult({ status: 'not_found', message: `QR code "${manualInput}" was not found in database.` });
    }
  };

  const openConfirmation = (e) => {
    e.preventDefault();
    if (!assignForm.business_name.trim()) {
      setToast({ type: 'error', message: 'Please select or enter a business name' });
      return;
    }
    if (!urlPreviewValid) {
      setToast({ type: 'error', message: 'Please enter a valid HTTP or HTTPS destination URL' });
      return;
    }
    setShowConfirmModal(true);
  };

  const handleExecuteAssignment = async () => {
    if (!result?.qr_id && !result?.token) return;
    setAssignLoading(true);

    try {
      const targetIdentifier = result.qr_id || result.token;
      let finalUrl = assignForm.destination_url.trim();
      if (!finalUrl.startsWith('http://') && !finalUrl.startsWith('https://')) {
        finalUrl = 'https://' + finalUrl;
      }

      const payload = {
        business_name: assignForm.business_name.trim(),
        destination_url: finalUrl,
        notes: assignForm.notes || undefined,
        expiry_date: assignForm.expiry_date || undefined,
      };

      if (result.status === 'active') {
        // Reassignment
        payload.confirm_reassignment = true;
        await qrAPI.reassign(targetIdentifier, payload);
        setToast({ type: 'success', message: `Successfully REASSIGNED ${result.qr_id} to ${payload.business_name}!` });
      } else {
        // Initial Assignment
        await qrAPI.assign(targetIdentifier, payload);
        setToast({ type: 'success', message: `Successfully ACTIVATED ${result.qr_id} for ${payload.business_name}!` });
      }

      setShowConfirmModal(false);
      setShowAssign(false);

      // Refresh resolve status
      const refreshRes = await qrAPI.resolve(result.token);
      setResult({ ...refreshRes.data, token: result.token, qr_id: refreshRes.data.qr_id || targetIdentifier });
      loadBusinesses();
    } catch (err) {
      setToast({
        type: 'error',
        message: err.response?.data?.detail || 'Assignment activation failed',
      });
    } finally {
      setAssignLoading(false);
    }
  };

  const openDestinationPreviewInNewTab = () => {
    let u = assignForm.destination_url.trim();
    if (!u.startsWith('http://') && !u.startsWith('https://')) {
      u = 'https://' + u;
    }
    window.open(u, '_blank', 'noopener,noreferrer');
  };

  return (
    <div className="scan-page-container">
      {toast && <div className={`toast toast-${toast.type}`}>{toast.message}</div>}

      <div className="page-header">
        <h1 className="page-title">📷 Scan & Assign QR Code</h1>
        <p className="page-subtitle">Scan a physical QR code to identify its permanent ID and assign a business destination</p>
      </div>

      {/* Camera Viewfinder Card */}
      <div className="scanner-card">
        <div className="scanner-viewfinder-box">
          <div id="qr-reader" className="qr-reader-window" />
          {!scanning && (
            <div className="scanner-placeholder-overlay">
              <div className="viewfinder-frame">
                <div className="corner corner-tl" />
                <div className="corner corner-tr" />
                <div className="corner corner-bl" />
                <div className="corner corner-br" />
                <span className="camera-icon-big">📷</span>
              </div>
              <p className="placeholder-text">Camera inactive. Tap button below to scan physical QR sticker.</p>
            </div>
          )}
        </div>

        <div className="scanner-controls-bar">
          {!scanning ? (
            <button className="btn btn-primary btn-lg w-full" onClick={startScanner}>
              📷 Open Camera Scanner
            </button>
          ) : (
            <button className="btn btn-danger btn-lg w-full" onClick={stopScanner}>
              ⏹ Stop Camera
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="alert alert-danger" style={{ marginTop: '16px' }}>
          ⚠️ {error}
        </div>
      )}

      {/* Manual Input Search Card */}
      <div className="card" style={{ marginTop: '16px' }}>
        <h2 className="card-title" style={{ fontSize: '1rem', marginBottom: '8px' }}>
          🔍 Manual QR ID or URL Entry
        </h2>
        <div className="manual-input-row">
          <input
            type="text"
            className="form-input"
            placeholder="e.g. QR-000001 or paste /q/TOKEN url"
            value={manualInput}
            onChange={(e) => setManualInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleManualLookup()}
          />
          <button className="btn btn-secondary" onClick={handleManualLookup}>
            Lookup
          </button>
        </div>
      </div>

      {/* Scan / Identification Result */}
      {result && (
        <div className="card result-card" style={{ marginTop: '20px' }}>
          <div className="result-header-row">
            <div>
              <span className="result-chip-id">{result.qr_id || 'QR Identified'}</span>
              <h2 className="result-title">{result.business_name || 'Unassigned Physical Sticker'}</h2>
            </div>
            <div>
              <span className={`badge badge-${result.status}`}>● {result.status?.toUpperCase()}</span>
            </div>
          </div>

          <div className="result-body-box">
            <div className="result-info-row">
              <span className="info-label">Permanent Token:</span>
              <code className="info-token">{result.token}</code>
            </div>
            <div className="result-info-row">
              <span className="info-label">System Redirect:</span>
              <a
                href={`/q/${result.token}`}
                target="_blank"
                rel="noopener noreferrer"
                className="dest-link"
              >
                /q/{result.token}
              </a>
            </div>
            {result.destination_url && (
              <div className="result-info-row">
                <span className="info-label">Current Destination:</span>
                <a
                  href={result.destination_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="dest-link"
                >
                  {result.destination_url}
                </a>
              </div>
            )}
            {result.message && (
              <div className="result-status-msg">
                ℹ️ {result.message}
              </div>
            )}
          </div>

          {/* Trigger Assignment / Reassignment */}
          {!showAssign && (
            <div className="result-actions-row">
              {result.status === 'unassigned' && (
                <button className="btn btn-primary btn-lg w-full" onClick={() => setShowAssign(true)}>
                  ⚡ Assign to Business Now
                </button>
              )}
              {result.status === 'active' && isAdmin && (
                <button className="btn btn-warning btn-lg w-full" onClick={() => setShowAssign(true)}>
                  🔄 Reassign to Another Business
                </button>
              )}
              {result.status === 'active' && !isAdmin && (
                <p className="text-muted text-center" style={{ width: '100%' }}>
                  This QR code is already assigned to {result.business_name}. Admin role is required to reassign.
                </p>
              )}
            </div>
          )}

          {/* FEATURE 3: QR Assignment / Reassignment Form */}
          {showAssign && (
            <div className="assignment-form-card">
              <div className="form-header">
                <h3>{result.status === 'active' ? '🔄 Reassignment Form' : '⚡ QR Code Activation'}</h3>
                <button className="close-btn" onClick={() => setShowAssign(false)}>✕</button>
              </div>

              <form onSubmit={openConfirmation}>
                {/* Step 3: Select or Enter Business */}
                <div className="form-group">
                  <label className="form-label">
                    🏢 Select or Enter Business Name *
                  </label>
                  <input
                    type="text"
                    list="business-options"
                    required
                    placeholder="Type or select a business name..."
                    value={assignForm.business_name}
                    onChange={(e) => setAssignForm({ ...assignForm, business_name: e.target.value })}
                    className="form-input"
                  />
                  <datalist id="business-options">
                    {existingBusinesses.map((b, idx) => (
                      <option key={idx} value={b} />
                    ))}
                  </datalist>
                  <span className="field-hint">Choose from recent businesses or enter a new one.</span>
                </div>

                {/* Step 4: Destination URL */}
                <div className="form-group">
                  <label className="form-label">
                    🔗 Destination URL (Landing Page / Menu) *
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="https://clientbusiness.com/menu"
                    value={assignForm.destination_url}
                    onChange={(e) => setAssignForm({ ...assignForm, destination_url: e.target.value })}
                    className={`form-input ${urlPreviewValid ? 'input-valid' : ''}`}
                  />
                </div>

                {/* Step 5: Destination Live Preview Widget */}
                {assignForm.destination_url.trim().length > 5 && (
                  <div className={`destination-preview-box ${urlPreviewValid ? 'preview-ready' : 'preview-invalid'}`}>
                    <div className="preview-top">
                      <span className="preview-badge">
                        {urlPreviewValid ? '✅ Valid Destination' : '⚠️ Enter Full URL (https://...)'}
                      </span>
                      {urlPreviewValid && (
                        <button
                          type="button"
                          className="btn-preview-link"
                          onClick={openDestinationPreviewInNewTab}
                        >
                          🌐 Test / Open Preview ↗
                        </button>
                      )}
                    </div>
                    <div className="preview-url-text">
                      {assignForm.destination_url}
                    </div>
                  </div>
                )}

                {/* Notes */}
                <div className="form-group">
                  <label className="form-label">📝 Notes / Physical Location (Optional)</label>
                  <textarea
                    placeholder="e.g. Table 4 sticker, Front glass counter, etc."
                    value={assignForm.notes}
                    onChange={(e) => setAssignForm({ ...assignForm, notes: e.target.value })}
                    className="form-input"
                    rows="2"
                  />
                </div>

                <div className="form-actions-row">
                  <button type="button" className="btn btn-secondary" onClick={() => setShowAssign(false)}>
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={!assignForm.business_name || !urlPreviewValid}
                  >
                    Proceed to Confirmation →
                  </button>
                </div>
              </form>
            </div>
          )}
        </div>
      )}

      {/* FEATURE 3: Step 6 & 7 Assignment Confirmation Modal */}
      {showConfirmModal && (
        <div className="modal-backdrop" onClick={() => setShowConfirmModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Confirm QR Activation</h2>
              <button className="close-btn" onClick={() => setShowConfirmModal(false)}>✕</button>
            </div>

            <div className="confirmation-summary-box">
              <div className="confirm-row">
                <span className="confirm-label">Physical QR ID:</span>
                <span className="confirm-val highlight">{result?.qr_id}</span>
              </div>
              <div className="confirm-row">
                <span className="confirm-label">Permanent Token:</span>
                <span className="confirm-val token">{result?.token}</span>
              </div>
              <div className="confirm-row">
                <span className="confirm-label">Assigning To:</span>
                <span className="confirm-val"><strong>{assignForm.business_name}</strong></span>
              </div>
              <div className="confirm-row">
                <span className="confirm-label">Destination URL:</span>
                <span className="confirm-val dest">{assignForm.destination_url}</span>
              </div>
              <div className="confirm-row">
                <span className="confirm-label">Action:</span>
                <span className="confirm-val">
                  {result?.status === 'active' ? '🔄 Reassignment (Replaces previous destination)' : '⚡ First-Time Activation'}
                </span>
              </div>
            </div>

            {result?.status === 'active' && (
              <div className="alert alert-warning">
                ⚠️ Previous destination (<strong>{result.business_name}</strong>) will stop redirecting immediately. All prior history is preserved.
              </div>
            )}

            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setShowConfirmModal(false)}
                disabled={assignLoading}
              >
                Go Back & Edit
              </button>
              <button
                type="button"
                className="btn btn-primary btn-lg"
                onClick={handleExecuteAssignment}
                disabled={assignLoading}
              >
                {assignLoading ? 'Activating...' : '✓ Confirm & Activate QR'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
