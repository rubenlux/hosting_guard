/**
 * Base Axios instance shared by all domain API modules.
 * Interceptor logic (token refresh, session expiry) lives here.
 */
import axios from 'axios';

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'https://api.hostingguard.lat',
  withCredentials: true,
});

let _isRefreshing = false;
let _refreshQueue = [];

const _drainQueue = (err) => {
  _refreshQueue.forEach(p => (err ? p.reject(err) : p.resolve()));
  _refreshQueue = [];
};

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const isAuthEndpoint =
      originalRequest?.url?.includes('/login') ||
      originalRequest?.url?.includes('/refresh');

    if (
      error.response?.status === 401 &&
      !isAuthEndpoint &&
      !originalRequest._retry &&
      !originalRequest._noRefresh
    ) {
      if (_isRefreshing) {
        return new Promise((resolve, reject) => {
          _refreshQueue.push({ resolve, reject });
        })
          .then(() => client(originalRequest))
          .catch(err => Promise.reject(err));
      }

      originalRequest._retry = true;
      _isRefreshing = true;

      try {
        await client.post('/refresh');
        _drainQueue(null);
        return client(originalRequest);
      } catch (refreshError) {
        _drainQueue(refreshError);
        window.dispatchEvent(new Event('auth:session-expired'));
        return Promise.reject(refreshError);
      } finally {
        _isRefreshing = false;
      }
    }

    // Global error handler: surface network and server errors via custom event
    const status = error.response?.status;
    if (!status) {
      // Network error (no response at all)
      window.dispatchEvent(new CustomEvent('api:error', { detail: { type: 'network' } }));
    } else if (status >= 500) {
      window.dispatchEvent(new CustomEvent('api:error', { detail: { type: 'server', status } }));
    }

    return Promise.reject(error);
  }
);

export default client;
