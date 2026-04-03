import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'https://api.hostingguard.lat';

const api = axios.create({
  baseURL: API_URL,
  // Necesario para que el navegador envíe automáticamente las cookies HttpOnly
  // en cada petición cross-origin al backend.
  withCredentials: true,
});

// Interceptor de respuesta: en 401 intentar renovar el access_token con /refresh
// (el refresh_token llega automáticamente como cookie HttpOnly).
// Si /refresh también falla, redirigir al inicio de sesión.
let _isRefreshing = false;
let _refreshQueue = []; // { resolve, reject }[]

const _drainQueue = (err) => {
  _refreshQueue.forEach(p => (err ? p.reject(err) : p.resolve()));
  _refreshQueue = [];
};

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const isAuthEndpoint =
      originalRequest?.url?.includes('/login') ||
      originalRequest?.url?.includes('/refresh');

    if (error.response?.status === 401 && !isAuthEndpoint && !originalRequest._retry) {
      // If a refresh is already in flight, queue this request until it finishes
      if (_isRefreshing) {
        return new Promise((resolve, reject) => {
          _refreshQueue.push({ resolve, reject });
        })
          .then(() => api(originalRequest))
          .catch(err => Promise.reject(err));
      }

      originalRequest._retry = true;
      _isRefreshing = true;

      try {
        await api.post('/refresh'); // cookie auto-included via withCredentials
        _drainQueue(null);
        return api(originalRequest);
      } catch (refreshError) {
        _drainQueue(refreshError);
        if (typeof window !== 'undefined') {
          window.location.href = '/';
        }
        return Promise.reject(refreshError);
      } finally {
        _isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export const getMe = async () => {
    const response = await api.get('/me');
    return response.data;
};

export const createHosting = async (name, plan) => {
  const response = await api.post('/create-hosting', { name, plan });
  return response.data;
};

export const createWordPress = async (name, plan) => {
  const response = await api.post('/create-wordpress', { name, plan });
  return response.data;
};

export const deployFromGithub = async (name, plan, repoUrl, branch = 'main') => {
  const response = await api.post('/deploy-from-github', {
    name,
    plan,
    repo_url: repoUrl,
    branch,
  });
  return response.data;
};

export const login = async (email, password) => {
  const response = await api.post('/login', { email, password });
  return response.data;
};

export const register = async (email, password) => {
  const response = await api.post('/register', { email, password });
  return response.data;
};

export const listHostings = async () => {
    const response = await api.get('/list-hostings');
    return response.data;
};

export const deleteHosting = async (hostingId) => {
    const response = await api.delete(`/delete-hosting/${hostingId}`);
    return response.data;
};

export const restartHosting = async (id) => {
    const response = await api.post(`/hostings/${id}/restart`);
    return response.data;
};

export const stopHosting = async (id) => {
    const response = await api.post(`/hostings/${id}/stop`);
    return response.data;
};

export const startHosting = async (id) => {
    const response = await api.post(`/hostings/${id}/start`);
    return response.data;
};

export const getLogs = async (id, since = null) => {
    const url = since ? `/hostings/${id}/logs?since=${since}` : `/hostings/${id}/logs`;
    const response = await api.get(url);
    return response.data;
};

export const getMetrics = async (id) => {
    const response = await api.get(`/hostings/${id}/metrics`);
    return response.data;
};

export const getOrchestratorEvents = async () => {
    const response = await api.get('/orchestrator/events');
    return response.data;
};

export const updateUserConfig = async (config) => {
    const response = await api.post('/user/config', config);
    return response.data;
};

export const topupBalance = async (amount) => {
    const response = await api.post('/user/topup', { amount });
    return response.data;
};

export const uploadZip = async (hostingId, file) => {
    const formData = new FormData();
    formData.append('file', file);
    // No forzar Content-Type: axios lo establece automáticamente con el boundary correcto
    // cuando detecta un FormData. Forzarlo manualmente omite el boundary y puede romper el upload.
    const response = await api.post(`/hostings/${hostingId}/upload-zip`, formData);
    return response.data;
};

export default api;
