import { useState, useEffect } from 'react';
import { analyticsAPI } from '../services/api';

export default function DashboardPage() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStats();
  }, []);

  const loadStats = async () => {
    try {
      const res = await analyticsAPI.overview();
      setStats(res.data);
    } catch (err) {
      console.error('Failed to load stats:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="loading-spinner">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Dashboard</h1>
        <p className="page-subtitle">QR Code Inventory Overview</p>
      </div>

      {stats && (
        <>
          <div className="stats-grid">
            <div className="stat-card primary">
              <div className="stat-icon">📊</div>
              <div className="stat-value">{stats.total_qr_codes}</div>
              <div className="stat-label">Total QR Codes</div>
            </div>
            <div className="stat-card success">
              <div className="stat-icon">✅</div>
              <div className="stat-value">{stats.active}</div>
              <div className="stat-label">Active</div>
            </div>
            <div className="stat-card warning">
              <div className="stat-icon">📦</div>
              <div className="stat-value">{stats.unassigned}</div>
              <div className="stat-label">Unassigned</div>
            </div>
            <div className="stat-card info">
              <div className="stat-icon">⏸️</div>
              <div className="stat-value">{stats.disabled}</div>
              <div className="stat-label">Disabled</div>
            </div>
            <div className="stat-card danger">
              <div className="stat-icon">🚫</div>
              <div className="stat-value">{stats.retired}</div>
              <div className="stat-label">Retired</div>
            </div>
          </div>

          <div className="card" style={{ marginBottom: '16px' }}>
            <div className="card-header">
              <h3 className="card-title">📈 Scan Activity</h3>
            </div>
            <div className="stats-grid" style={{ marginBottom: 0 }}>
              <div className="stat-card primary">
                <div className="stat-value">{stats.total_scans}</div>
                <div className="stat-label">Total Scans</div>
              </div>
              <div className="stat-card success">
                <div className="stat-value">{stats.scans_today}</div>
                <div className="stat-label">Today</div>
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
        </>
      )}
    </div>
  );
}
