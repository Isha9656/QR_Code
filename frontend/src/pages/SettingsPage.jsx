import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { authAPI, adminAPI } from '../services/api';

export default function SettingsPage() {
  const { user, isAdmin, logout } = useAuth();
  const [pwForm, setPwForm] = useState({ current_password: '', new_password: '', confirm: '' });
  const [pwError, setPwError] = useState('');
  const [pwSuccess, setPwSuccess] = useState('');
  const [pwLoading, setPwLoading] = useState(false);

  // User creation (admin)
  const [newUser, setNewUser] = useState({ username: '', password: '', display_name: '', role: 'operator' });
  const [userError, setUserError] = useState('');
  const [userSuccess, setUserSuccess] = useState('');
  const [userLoading, setUserLoading] = useState(false);

  // Backups (admin)
  const [backups, setBackups] = useState([]);
  const [backupLoading, setBackupLoading] = useState(false);
  const [backupMsg, setBackupMsg] = useState('');

  const fetchBackups = async () => {
    if (!isAdmin) return;
    try {
      const res = await adminAPI.getBackups();
      setBackups(res.data.backups || []);
    } catch (e) {
      // Ignore initial load error
    }
  };

  useEffect(() => {
    fetchBackups();
  }, [isAdmin]);

  const handlePasswordChange = async (e) => {
    e.preventDefault();
    setPwError('');
    setPwSuccess('');

    if (pwForm.new_password !== pwForm.confirm) {
      setPwError('Passwords do not match');
      return;
    }
    if (pwForm.new_password.length < 8) {
      setPwError('Password must be at least 8 characters');
      return;
    }
    if (!/[A-Z]/.test(pwForm.new_password) || !/[a-z]/.test(pwForm.new_password) || !/[0-9]/.test(pwForm.new_password)) {
      setPwError('Password must contain at least 1 uppercase letter, 1 lowercase letter, and 1 number');
      return;
    }

    setPwLoading(true);
    try {
      await authAPI.changePassword(pwForm.current_password, pwForm.new_password);
      setPwSuccess('Password changed successfully. Default credentials flag cleared.');
      setPwForm({ current_password: '', new_password: '', confirm: '' });

      // Update local storage user flag
      const savedUser = localStorage.getItem('user');
      if (savedUser) {
        const parsed = JSON.parse(savedUser);
        parsed.must_change_password = false;
        localStorage.setItem('user', JSON.stringify(parsed));
        window.location.reload();
      }
    } catch (err) {
      setPwError(err.response?.data?.detail || 'Failed to change password');
    } finally {
      setPwLoading(false);
    }
  };

  const handleCreateUser = async (e) => {
    e.preventDefault();
    setUserError('');
    setUserSuccess('');

    if (newUser.password.length < 8) {
      setUserError('Password must be at least 8 characters');
      return;
    }

    setUserLoading(true);
    try {
      await authAPI.createUser(newUser);
      setUserSuccess(`User "${newUser.username}" created successfully`);
      setNewUser({ username: '', password: '', display_name: '', role: 'operator' });
    } catch (err) {
      setUserError(err.response?.data?.detail || 'Failed to create user');
    } finally {
      setUserLoading(false);
    }
  };

  const handleCreateBackup = async () => {
    setBackupLoading(true);
    setBackupMsg('');
    try {
      const res = await adminAPI.createBackup();
      setBackupMsg(`Live backup created: ${res.data.backup?.filename}`);
      fetchBackups();
    } catch (err) {
      setBackupMsg(`Backup failed: ${err.response?.data?.detail || err.message}`);
    } finally {
      setBackupLoading(false);
    }
  };

  const handleDownloadBackup = async (filename) => {
    try {
      const res = await adminAPI.downloadBackup(filename);
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      alert('Failed to download backup file');
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">⚙️ Settings & Administration</h1>
        <p className="page-subtitle">Security, account policies, and database disaster recovery</p>
      </div>

      {/* Mandatory Password Change Warning */}
      {user?.must_change_password && (
        <div className="card" style={{ background: '#fef2f2', border: '1px solid #ef4444', marginBottom: '16px' }}>
          <h3 style={{ color: '#dc2626', marginBottom: '8px', fontSize: '1rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
            ⚠️ Mandatory Action: Default Password Replacement Required
          </h3>
          <p style={{ color: '#991b1b', fontSize: '0.85rem', lineHeight: '1.5' }}>
            You are currently logged in with default system credentials. For security reasons, you cannot access normal operations until you change your password below.
          </p>
        </div>
      )}

      {/* User Info */}
      <div className="card" style={{ marginBottom: '16px' }}>
        <h3 className="card-title" style={{ marginBottom: '12px' }}>👤 Account Profile</h3>
        <div className="detail-row">
          <span className="detail-label">Username</span>
          <span className="detail-value">{user?.username}</span>
        </div>
        <div className="detail-row">
          <span className="detail-label">Display Name</span>
          <span className="detail-value">{user?.display_name}</span>
        </div>
        <div className="detail-row">
          <span className="detail-label">Role</span>
          <span className="detail-value">
            <span className="badge badge-active">{user?.role?.toUpperCase()}</span>
          </span>
        </div>
        <button className="btn btn-danger btn-block" style={{ marginTop: '16px' }} onClick={logout}>
          🚪 Sign Out
        </button>
      </div>

      {/* Password Change */}
      <div className="card" style={{ marginBottom: '16px' }}>
        <h3 className="card-title" style={{ marginBottom: '12px' }}>🔑 Change Password</h3>
        {pwError && <div className="login-error">{pwError}</div>}
        {pwSuccess && (
          <div style={{ background: 'var(--green-100)', color: '#16a34a', padding: '10px 14px', borderRadius: '8px', fontSize: '0.83rem', marginBottom: '12px' }}>
            {pwSuccess}
          </div>
        )}
        <form onSubmit={handlePasswordChange}>
          <div className="form-group">
            <label className="form-label">Current Password</label>
            <input
              type="password"
              className="form-input"
              required
              value={pwForm.current_password}
              onChange={(e) => setPwForm({ ...pwForm, current_password: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label className="form-label">New Password (min 8 chars, 1 uppercase, 1 lowercase, 1 number, 1 special)</label>
            <input
              type="password"
              className="form-input"
              required
              minLength={8}
              value={pwForm.new_password}
              onChange={(e) => setPwForm({ ...pwForm, new_password: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label className="form-label">Confirm New Password</label>
            <input
              type="password"
              className="form-input"
              required
              value={pwForm.confirm}
              onChange={(e) => setPwForm({ ...pwForm, confirm: e.target.value })}
            />
          </div>
          <button type="submit" className="btn btn-primary btn-block" disabled={pwLoading}>
            {pwLoading ? 'Changing...' : 'Change Password'}
          </button>
        </form>
      </div>

      {/* Database Disaster Recovery (Admin Only) */}
      {isAdmin && (
        <div className="card" style={{ marginBottom: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <div>
              <h3 className="card-title">💾 Database Disaster Recovery & Backups</h3>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: '2px' }}>
                Safe live SQLite backups using sqlite3 online backup API
              </p>
            </div>
            <button
              className="btn btn-success btn-sm"
              onClick={handleCreateBackup}
              disabled={backupLoading}
            >
              {backupLoading ? 'Backing up...' : '➕ Create Live Backup'}
            </button>
          </div>

          {backupMsg && (
            <div style={{
              background: backupMsg.includes('failed') ? '#fee2e2' : 'var(--green-100)',
              color: backupMsg.includes('failed') ? '#dc2626' : '#16a34a',
              padding: '8px 12px',
              borderRadius: '6px',
              fontSize: '0.82rem',
              marginBottom: '12px',
            }}>
              {backupMsg}
            </div>
          )}

          {backups.length === 0 ? (
            <p style={{ fontSize: '0.83rem', color: 'var(--text-muted)', textAlign: 'center', padding: '16px 0' }}>
              No database backups generated yet.
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {backups.map((b) => (
                <div
                  key={b.filename}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '10px 12px',
                    background: 'var(--bg-secondary)',
                    borderRadius: '8px',
                    border: '1px solid var(--border-color)',
                    fontSize: '0.83rem',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: '600', color: 'var(--text-primary)' }}>{b.filename}</div>
                    <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', marginTop: '2px' }}>
                      {new Date(b.created_at).toLocaleString()} • {(b.size_bytes / 1024).toFixed(1)} KB
                    </div>
                  </div>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => handleDownloadBackup(b.filename)}
                  >
                    ⬇️ Download
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Recovery procedure info box */}
          <div style={{
            marginTop: '16px',
            padding: '12px 14px',
            background: 'var(--bg-secondary)',
            borderRadius: '8px',
            borderLeft: '4px solid var(--primary)',
            fontSize: '0.8rem',
            color: 'var(--text-secondary)',
          }}>
            <div style={{ fontWeight: '600', color: 'var(--text-primary)', marginBottom: '4px' }}>
              ℹ️ Offline Restoration Procedure:
            </div>
            <ol style={{ paddingLeft: '16px', margin: 0, lineHeight: '1.6' }}>
              <li>Stop the running servers using <code>stop.bat</code>.</li>
              <li>Execute <code>restore.bat</code> (or <code>python restore_database.py &lt;backup.db&gt;</code>).</li>
              <li>A pre-restore safety snapshot will be created automatically before replacement.</li>
              <li>Restart the application using <code>run.bat</code>.</li>
            </ol>
          </div>
        </div>
      )}

      {/* Create User (Admin Only) */}
      {isAdmin && (
        <div className="card">
          <h3 className="card-title" style={{ marginBottom: '12px' }}>👥 Operator Management</h3>
          {userError && <div className="login-error">{userError}</div>}
          {userSuccess && (
            <div style={{ background: 'var(--green-100)', color: '#16a34a', padding: '10px 14px', borderRadius: '8px', fontSize: '0.83rem', marginBottom: '12px' }}>
              {userSuccess}
            </div>
          )}
          <form onSubmit={handleCreateUser}>
            <div className="form-group">
              <label className="form-label">Username</label>
              <input
                type="text"
                className="form-input"
                required
                value={newUser.username}
                onChange={(e) => setNewUser({ ...newUser, username: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Display Name</label>
              <input
                type="text"
                className="form-input"
                required
                value={newUser.display_name}
                onChange={(e) => setNewUser({ ...newUser, display_name: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Password (min 8 chars)</label>
              <input
                type="password"
                className="form-input"
                required
                minLength={8}
                value={newUser.password}
                onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Role</label>
              <select
                className="form-select"
                value={newUser.role}
                onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
              >
                <option value="operator">Operator (Scan, View, Print)</option>
                <option value="admin">Administrator (Full Control, Backups, Users)</option>
              </select>
            </div>
            <button type="submit" className="btn btn-success btn-block" disabled={userLoading}>
              {userLoading ? 'Creating...' : '➕ Create User Account'}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
