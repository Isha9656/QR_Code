import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { authAPI } from '../services/api';

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

    setPwLoading(true);
    try {
      await authAPI.changePassword(pwForm.current_password, pwForm.new_password);
      setPwSuccess('Password changed successfully');
      setPwForm({ current_password: '', new_password: '', confirm: '' });
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
      await authAPI.createUser(newUser.username, newUser.password, newUser.display_name, newUser.role);
      setUserSuccess(`User "${newUser.username}" created successfully`);
      setNewUser({ username: '', password: '', display_name: '', role: 'operator' });
    } catch (err) {
      setUserError(err.response?.data?.detail || 'Failed to create user');
    } finally {
      setUserLoading(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Settings</h1>
        <p className="page-subtitle">Account and system settings</p>
      </div>

      {/* User Info */}
      <div className="card" style={{ marginBottom: '16px' }}>
        <h3 className="card-title" style={{ marginBottom: '12px' }}>👤 Account</h3>
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
        {pwSuccess && <div style={{ background: 'var(--green-100)', color: '#16a34a', padding: '10px 14px', borderRadius: '8px', fontSize: '0.83rem', marginBottom: '12px' }}>{pwSuccess}</div>}
        <form onSubmit={handlePasswordChange}>
          <div className="form-group">
            <label className="form-label">Current Password</label>
            <input type="password" className="form-input" required
              value={pwForm.current_password}
              onChange={(e) => setPwForm({ ...pwForm, current_password: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label">New Password</label>
            <input type="password" className="form-input" required minLength={8}
              value={pwForm.new_password}
              onChange={(e) => setPwForm({ ...pwForm, new_password: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label">Confirm New Password</label>
            <input type="password" className="form-input" required
              value={pwForm.confirm}
              onChange={(e) => setPwForm({ ...pwForm, confirm: e.target.value })} />
          </div>
          <button type="submit" className="btn btn-primary btn-block" disabled={pwLoading}>
            {pwLoading ? 'Changing...' : 'Change Password'}
          </button>
        </form>
      </div>

      {/* Create User (Admin) */}
      {isAdmin && (
        <div className="card">
          <h3 className="card-title" style={{ marginBottom: '12px' }}>👥 Create User</h3>
          {userError && <div className="login-error">{userError}</div>}
          {userSuccess && <div style={{ background: 'var(--green-100)', color: '#16a34a', padding: '10px 14px', borderRadius: '8px', fontSize: '0.83rem', marginBottom: '12px' }}>{userSuccess}</div>}
          <form onSubmit={handleCreateUser}>
            <div className="form-group">
              <label className="form-label">Username</label>
              <input type="text" className="form-input" required
                value={newUser.username}
                onChange={(e) => setNewUser({ ...newUser, username: e.target.value })} />
            </div>
            <div className="form-group">
              <label className="form-label">Display Name</label>
              <input type="text" className="form-input" required
                value={newUser.display_name}
                onChange={(e) => setNewUser({ ...newUser, display_name: e.target.value })} />
            </div>
            <div className="form-group">
              <label className="form-label">Password</label>
              <input type="password" className="form-input" required minLength={8}
                value={newUser.password}
                onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} />
            </div>
            <div className="form-group">
              <label className="form-label">Role</label>
              <select className="form-select" value={newUser.role}
                onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}>
                <option value="operator">Operator</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            <button type="submit" className="btn btn-success btn-block" disabled={userLoading}>
              {userLoading ? 'Creating...' : '➕ Create User'}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
