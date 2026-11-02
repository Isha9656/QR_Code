import { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { printAPI, qrAPI } from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function PrintStudioPage() {
  const { isAdmin } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  // Mode: 'batch' (quantity of unassigned) or 'selected' (explicit unassigned IDs)
  const initialSelectedIds = location.state?.selectedIds || [];
  const [mode, setMode] = useState(initialSelectedIds.length > 0 ? 'selected' : 'batch');
  const [selectedIds, setSelectedIds] = useState(initialSelectedIds);
  const [quantity, setQuantity] = useState(24);
  const [unassignedStats, setUnassignedStats] = useState({ available: 0, total: 0 });

  // Print Configuration Settings
  const [qrSize, setQrSize] = useState(30); // mm
  const [margin, setMargin] = useState(10); // mm
  const [spacing, setSpacing] = useState(5); // mm
  const [showLabels, setShowLabels] = useState(true);
  const [enableBranding, setEnableBranding] = useState(true);
  const [companyName, setCompanyName] = useState('INTERNAL QR SYSTEM');
  const [headerText, setHeaderText] = useState('OFFICIAL ASSET STICKERS • DO NOT DISCARD');
  const [enableFooter, setEnableFooter] = useState(true);
  const [footerText, setFooterText] = useState('Scan with system camera to activate or reassign');
  const [customCols, setCustomCols] = useState('');
  const [customRows, setCustomRows] = useState('');

  // Sheet Layout & Preview State
  const [previewData, setPreviewData] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [downloading, setDownloading] = useState(false);
  const [toast, setToast] = useState(null);
  const [validationError, setValidationError] = useState('');

  useEffect(() => {
    loadUnassignedInventory();
  }, []);

  useEffect(() => {
    updateSheetPreview();
  }, [mode, quantity, selectedIds, qrSize, margin, spacing, showLabels, enableBranding, companyName, headerText, enableFooter, footerText, customCols, customRows]);

  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(null), 3500);
      return () => clearTimeout(t);
    }
  }, [toast]);

  const loadUnassignedInventory = async () => {
    try {
      const res = await qrAPI.getStats();
      setUnassignedStats({
        available: res.data.unassigned,
        total: res.data.total,
      });

      // If in selected mode, verify all selected are unassigned
      if (initialSelectedIds.length > 0) {
        verifySelectedAreUnassigned(initialSelectedIds);
      }
    } catch (err) {
      console.error('Failed to load stats', err);
    }
  };

  const verifySelectedAreUnassigned = async (ids) => {
    setValidationError('');
    try {
      const res = await qrAPI.list({ per_page: 100 });
      const found = res.data.items.filter(q => ids.includes(q.id));
      const nonUnassigned = found.filter(q => q.status !== 'unassigned');
      if (nonUnassigned.length > 0) {
        setValidationError(
          `Constraint Error: ${nonUnassigned.length} selected codes (${nonUnassigned.map(q => q.qr_id).join(', ')}) are not UNASSIGNED. Only unassigned QR codes can be printed in Bulk Printing Studio.`
        );
      }
    } catch (err) {
      console.error(err);
    }
  };

  const updateSheetPreview = async () => {
    setPreviewLoading(true);
    setValidationError('');
    try {
      const payload = {
        qr_size_mm: Number(qrSize) || 30,
        page_margin_mm: Number(margin) || 10,
        spacing_mm: Number(spacing) || 5,
        show_labels: showLabels,
        company_name: enableBranding ? companyName : null,
        header_text: enableBranding ? headerText : null,
        footer_text: enableFooter ? footerText : null,
        custom_cols: customCols ? Number(customCols) : null,
        custom_rows: customRows ? Number(customRows) : null,
        unassigned_only: true,
      };

      if (mode === 'selected' && selectedIds.length > 0) {
        payload.qr_ids = selectedIds;
      } else {
        payload.quantity = Number(quantity) || 24;
      }

      const res = await printAPI.previewStudioSheet(payload);
      setPreviewData(res.data);
      if (currentPage > res.data.total_pages) {
        setCurrentPage(1);
      }
    } catch (err) {
      setValidationError(err.response?.data?.detail || 'Layout calculation failed');
      setPreviewData(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleDownloadPDF = async () => {
    if (validationError) {
      setToast({ type: 'error', message: 'Please resolve validation errors before printing' });
      return;
    }

    setDownloading(true);
    try {
      const payload = {
        qr_size_mm: Number(qrSize) || 30,
        page_margin_mm: Number(margin) || 10,
        spacing_mm: Number(spacing) || 5,
        show_labels: showLabels,
        company_name: enableBranding ? companyName : null,
        header_text: enableBranding ? headerText : null,
        footer_text: enableFooter ? footerText : null,
        custom_cols: customCols ? Number(customCols) : null,
        custom_rows: customRows ? Number(customRows) : null,
        unassigned_only: true,
      };

      if (mode === 'selected' && selectedIds.length > 0) {
        payload.qr_ids = selectedIds;
      } else {
        payload.quantity = Number(quantity) || 24;
      }

      const res = await printAPI.exportStudioPDF(payload);
      const blob = new Blob([res.data], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `A4_QR_Stickers_${previewData?.total_qrs || 'batch'}_unassigned.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      setToast({ type: 'success', message: 'Printable A4 Sheet PDF downloaded successfully!' });
    } catch (err) {
      setToast({
        type: 'error',
        message: err.response?.data?.detail || 'Failed to generate PDF sheet',
      });
    } finally {
      setDownloading(false);
    }
  };

  if (!isAdmin) {
    return (
      <div className="empty-state">
        <div className="empty-icon">🔒</div>
        <h3>Admin Access Required</h3>
        <p>Only administrators can access the Bulk Printing Studio.</p>
        <button className="btn btn-primary" onClick={() => navigate('/inventory')}>
          Return to Inventory
        </button>
      </div>
    );
  }

  // Calculate items visible on the current preview page
  const itemsPerPage = previewData?.qrs_per_page || 24;
  const startIndex = (currentPage - 1) * itemsPerPage;
  const currentSheetItems = previewData?.sample_qrs?.slice(startIndex, startIndex + itemsPerPage) || [];

  return (
    <div className="print-studio-page">
      {toast && <div className={`toast toast-${toast.type}`}>{toast.message}</div>}

      {/* Top Header */}
      <div className="page-header-flex">
        <div>
          <h1 className="page-title">🖨️ Bulk Printing Studio</h1>
          <p className="page-subtitle">Configure, preview, and generate production-ready A4 sticker sheets</p>
        </div>
        <div className="header-actions">
          <button className="btn btn-secondary" onClick={() => navigate('/inventory')}>
            ← Back to Inventory
          </button>
        </div>
      </div>

      {/* Mode Selector and Status Alert */}
      <div className="studio-top-banner">
        <div className="inventory-stat-badge">
          <span>Available Unassigned Codes:</span>
          <strong>{unassignedStats.available} ready</strong>
        </div>

        <div className="mode-toggle-group">
          <button
            className={`btn-toggle ${mode === 'batch' ? 'active-toggle' : ''}`}
            onClick={() => setMode('batch')}
          >
            ⚡ Print by Quantity
          </button>
          <button
            className={`btn-toggle ${mode === 'selected' ? 'active-toggle' : ''}`}
            onClick={() => setMode('selected')}
          >
            📋 Print Selected ({selectedIds.length})
          </button>
        </div>
      </div>

      {/* CRITICAL CONSTRAINT: Strict Unassigned Notice */}
      <div className="alert alert-info">
        🛡️ <strong>Permanent Sticker Guarantee:</strong> Every printed QR code strictly contains its permanent system redirect URL (<code>/q/TOKEN</code>). Destination URLs are never hardcoded into physical stickers.
      </div>

      {validationError && (
        <div className="alert alert-danger">
          ⛔ {validationError}
        </div>
      )}

      {/* Main Studio Two-Column Grid */}
      <div className="studio-workspace-grid">
        {/* Left Column: Interactive Settings Panel */}
        <div className="studio-controls-card">
          <h2 className="studio-section-title">⚙️ Sheet Configuration</h2>

          {/* Source Selection */}
          <div className="control-group">
            <label className="control-label">
              {mode === 'batch' ? 'Quantity of Unassigned Codes to Print' : 'Selected QR Codes'}
            </label>
            {mode === 'batch' ? (
              <div className="preset-buttons-row">
                {[12, 24, 48, 96, 120, 240].map((q) => (
                  <button
                    key={q}
                    type="button"
                    className={`preset-btn ${quantity === q ? 'active-preset' : ''}`}
                    onClick={() => setQuantity(q)}
                  >
                    {q}
                  </button>
                ))}
                <div className="custom-qty-input">
                  <input
                    type="number"
                    min="1"
                    max={Math.min(2000, unassignedStats.available || 500)}
                    placeholder="Custom"
                    value={quantity}
                    onChange={(e) => setQuantity(Math.max(1, parseInt(e.target.value) || 1))}
                  />
                  <span className="unit-label">stickers</span>
                </div>
              </div>
            ) : (
              <div className="selected-codes-summary">
                <span className="selected-tag">{selectedIds.length} codes selected from inventory</span>
                <button
                  className="btn btn-sm btn-outline"
                  onClick={() => navigate('/inventory')}
                >
                  Change Selection
                </button>
              </div>
            )}
          </div>

          {/* QR Dimension */}
          <div className="control-group">
            <label className="control-label">
              QR Sticker Dimension (Width × Height)
            </label>
            <div className="preset-buttons-row">
              {[25, 30, 35, 40, 50].map((s) => (
                <button
                  key={s}
                  type="button"
                  className={`preset-btn ${qrSize === s ? 'active-preset' : ''}`}
                  onClick={() => setQrSize(s)}
                >
                  {s} mm
                </button>
              ))}
              <div className="custom-qty-input">
                <input
                  type="number"
                  min="15"
                  max="80"
                  value={qrSize}
                  onChange={(e) => setQrSize(Math.max(15, Math.min(80, parseInt(e.target.value) || 30)))}
                />
                <span className="unit-label">mm</span>
              </div>
            </div>
            <span className="field-hint">Standard recommendation: 30mm for table stands, 40mm for wall posters.</span>
          </div>

          {/* Margins & Spacing */}
          <div className="control-row-2col">
            <div className="control-group">
              <label className="control-label">Page Margin: <strong>{margin} mm</strong></label>
              <input
                type="range"
                min="5"
                max="30"
                value={margin}
                onChange={(e) => setMargin(parseInt(e.target.value))}
                className="slider-input"
              />
            </div>
            <div className="control-group">
              <label className="control-label">Sticker Spacing: <strong>{spacing} mm</strong></label>
              <input
                type="range"
                min="2"
                max="20"
                value={spacing}
                onChange={(e) => setSpacing(parseInt(e.target.value))}
                className="slider-input"
              />
            </div>
          </div>

          {/* Custom Grid Rows/Cols (Optional Override) */}
          <div className="control-row-2col">
            <div className="control-group">
              <label className="control-label">Columns (Auto / Override)</label>
              <input
                type="number"
                min="1"
                max="10"
                placeholder={`Auto (${previewData?.cols || 4})`}
                value={customCols}
                onChange={(e) => setCustomCols(e.target.value)}
                className="form-input"
              />
            </div>
            <div className="control-group">
              <label className="control-label">Rows (Auto / Override)</label>
              <input
                type="number"
                min="1"
                max="20"
                placeholder={`Auto (${previewData?.rows || 6})`}
                value={customRows}
                onChange={(e) => setCustomRows(e.target.value)}
                className="form-input"
              />
            </div>
          </div>

          {/* Labels & Branding */}
          <div className="control-group checkbox-toggle-group">
            <label className="checkbox-container">
              <input
                type="checkbox"
                checked={showLabels}
                onChange={(e) => setShowLabels(e.target.checked)}
              />
              <span><strong>Show QR ID Label below each sticker</strong> (e.g. QR-000001)</span>
            </label>
          </div>

          <div className="control-group checkbox-toggle-group">
            <label className="checkbox-container">
              <input
                type="checkbox"
                checked={enableBranding}
                onChange={(e) => setEnableBranding(e.target.checked)}
              />
              <span><strong>Add Corporate Branding Header to A4 Sheet</strong></span>
            </label>
            {enableBranding && (
              <div className="nested-branding-inputs">
                <input
                  type="text"
                  placeholder="Company Name / Header"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  className="form-input"
                />
                <input
                  type="text"
                  placeholder="Header Subtitle / Tagline"
                  value={headerText}
                  onChange={(e) => setHeaderText(e.target.value)}
                  className="form-input"
                />
              </div>
            )}
          </div>

          <div className="control-group checkbox-toggle-group">
            <label className="checkbox-container">
              <input
                type="checkbox"
                checked={enableFooter}
                onChange={(e) => setEnableFooter(e.target.checked)}
              />
              <span><strong>Add Footer Instructions & Page Counter</strong></span>
            </label>
            {enableFooter && (
              <div className="nested-branding-inputs">
                <input
                  type="text"
                  placeholder="Footer notice"
                  value={footerText}
                  onChange={(e) => setFooterText(e.target.value)}
                  className="form-input"
                />
              </div>
            )}
          </div>

          {/* Download Action */}
          <div className="studio-action-box">
            <button
              className="btn btn-primary btn-lg w-full"
              onClick={handleDownloadPDF}
              disabled={downloading || Boolean(validationError)}
            >
              {downloading ? '⏳ Rendering High-Res PDF...' : '📥 Generate & Download Printable A4 PDF'}
            </button>
            <p className="action-hint">Standard A4 format (210 × 297 mm) ready for sticker paper printing.</p>
          </div>
        </div>

        {/* Right Column: Interactive Sheet Preview Canvas */}
        <div className="studio-preview-card">
          <div className="preview-header-bar">
            <div>
              <h2 className="studio-section-title">📄 A4 Sheet Preview</h2>
              <span className="preview-stat-chip">
                {previewData ? (
                  <>
                    <strong>{previewData.cols} cols × {previewData.rows} rows</strong> ({previewData.qrs_per_page} stickers/sheet) • <strong>{previewData.total_pages} sheet{previewData.total_pages > 1 ? 's' : ''} total</strong>
                  </>
                ) : 'Calculating layout...'}
              </span>
            </div>

            {previewData?.total_pages > 1 && (
              <div className="sheet-page-nav">
                <button
                  className="btn btn-sm btn-secondary"
                  disabled={currentPage <= 1}
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                >
                  ← Prev
                </button>
                <span className="page-indicator">Page {currentPage} of {previewData.total_pages}</span>
                <button
                  className="btn btn-sm btn-secondary"
                  disabled={currentPage >= previewData.total_pages}
                  onClick={() => setCurrentPage(p => Math.min(previewData.total_pages, p + 1))}
                >
                  Next →
                </button>
              </div>
            )}
          </div>

          {/* A4 Sheet Canvas */}
          <div className="a4-sheet-wrapper">
            <div className="a4-sheet-canvas">
              {/* Sheet Header */}
              {enableBranding && (
                <div className="sheet-canvas-header">
                  <div className="sheet-brand-title">{companyName || 'INTERNAL QR SYSTEM'}</div>
                  <div className="sheet-brand-subtitle">{headerText}</div>
                </div>
              )}

              {/* Sheet QR Grid */}
              {previewLoading ? (
                <div className="sheet-loading-placeholder">
                  <div className="spinner" />
                  <span>Calculating grid layout...</span>
                </div>
              ) : (
                <div
                  className="sheet-canvas-grid"
                  style={{
                    gridTemplateColumns: `repeat(${previewData?.cols || 4}, 1fr)`,
                    gap: `${Math.max(4, spacing)}px`,
                    padding: `${Math.max(6, margin)}px`,
                  }}
                >
                  {Array.from({ length: previewData?.qrs_per_page || 24 }).map((_, idx) => {
                    const item = currentSheetItems[idx];
                    const label = item?.qr_id || `QR-${String(idx + 1).padStart(6, '0')}`;
                    return (
                      <div key={idx} className="sheet-sticker-cell">
                        <div className="sticker-cut-border">
                          {/* Simulated high-quality QR pattern */}
                          <div className="sticker-qr-graphic">
                            <div className="qr-eye eye-tl" />
                            <div className="qr-eye eye-tr" />
                            <div className="qr-eye eye-bl" />
                            <div className="qr-pattern-mesh" />
                          </div>
                          {showLabels && (
                            <div className="sticker-label-text">{label}</div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Sheet Footer */}
              {enableFooter && (
                <div className="sheet-canvas-footer">
                  <span>{footerText}</span>
                  <span>Sheet {currentPage} of {previewData?.total_pages || 1}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
