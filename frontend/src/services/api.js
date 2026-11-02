import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 responses
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

// Auth
export const authAPI = {
  login: (username, password) => api.post('/api/auth/login', { username, password }),
  logout: () => api.post('/api/auth/logout'),
  me: () => api.get('/api/auth/me'),
  changePassword: (current_password, new_password) =>
    api.post('/api/auth/change-password', { current_password, new_password }),
  createUser: (data) => api.post('/api/auth/users', data),
};

// QR Codes
export const qrAPI = {
  bulkGenerate: (quantity) => api.post('/api/qr/bulk-generate', { quantity }),
  list: (params) => api.get('/api/qr', { params }),
  get: (id) => api.get(`/api/qr/${id}`),
  getHistory: (id) => api.get(`/api/qr/${id}/history`),
  assign: (id, data) => api.post(`/api/qr/${id}/assign`, data),
  reassign: (id, data) => api.post(`/api/qr/${id}/reassign`, data),
  deactivate: (id) => api.post(`/api/qr/${id}/deactivate`),
  retire: (id) => api.post(`/api/qr/${id}/retire`),
  recover: (id) => api.post(`/api/qr/${id}/recover`),
  resolve: (token) => api.get(`/api/qr/resolve/${token}`),
};

// Printing
export const printAPI = {
  exportPDF: (data) => api.post('/api/qr/export/pdf', data, { responseType: 'blob' }),
  exportPNG: (qrId, size = 300) => api.get(`/api/qr/export/png/${qrId}?size=${size}`, { responseType: 'blob' }),
  exportZIP: (data) => api.post('/api/qr/export/zip', data, { responseType: 'blob' }),
};

// Analytics
export const analyticsAPI = {
  overview: () => api.get('/api/analytics/overview'),
  scans: (params) => api.get('/api/analytics/scans', { params }),
};

export default api;
