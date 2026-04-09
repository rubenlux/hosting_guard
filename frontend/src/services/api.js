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

    // _noRefresh: flag para peticiones que no deben intentar refresh al recibir 401.
    // Se usa en initAuth (primer chequeo de sesión al cargar la app) para evitar que
    // un usuario sin sesión active el loop: GET /me → 401 → POST /refresh → 401 → reload.
    if (error.response?.status === 401 && !isAuthEndpoint && !originalRequest._retry && !originalRequest._noRefresh) {
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
        await api.post('/refresh');
        _drainQueue(null);
        return api(originalRequest);
      } catch (refreshError) {
        _drainQueue(refreshError);
        // No hacer window.location.href aquí: causaría un reload loop si el usuario
        // está en '/'. En su lugar, emitir un evento para que useAuth limpie la sesión
        // y PrivateRoute redirija a '/' via React Router sin recargar la página.
        window.dispatchEvent(new Event('auth:session-expired'));
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

export const getAdminUsers = async () => {
    const response = await api.get('/admin/users');
    return response.data;
};

export const getAdminHostings = async () => {
    const response = await api.get('/admin/hostings');
    return response.data;
};

export const getAdminPixelStats = async () => {
    const response = await api.get('/pixel/admin/stats');
    return response.data;
};

export const getAdminHostingsMetrics = async () => {
    const response = await api.get('/admin/hostings/metrics');
    return response.data;
};

export const adminRestartHosting = async (hostingId) => {
    const response = await api.post(`/admin/hostings/${hostingId}/restart`);
    return response.data;
};

export const adminStopHosting = async (hostingId) => {
    const response = await api.post(`/admin/hostings/${hostingId}/stop`);
    return response.data;
};

export const adminStartHosting = async (hostingId) => {
    const response = await api.post(`/admin/hostings/${hostingId}/start`);
    return response.data;
};

export const adminGetHostingLogs = async (hostingId, since = null) => {
    const params = since ? { since } : {};
    const response = await api.get(`/admin/hostings/${hostingId}/logs`, { params });
    return response.data;
};

export const adminTerminateHosting = async (hostingId, reason) => {
    const response = await api.delete(`/admin/hostings/${hostingId}/terminate`, { data: { reason } });
    return response.data;
};

export const getAdminUserFull = async (userId) => {
    const response = await api.get(`/admin/users/${userId}/full`);
    return response.data;
};

export const getAdminPixelOverview = async () => {
    const response = await api.get('/admin/pixel/overview');
    return response.data;
};

export const getAdminPixelEvents = async (limit = 100, offset = 0) => {
    const response = await api.get(`/admin/pixel/events?limit=${limit}&offset=${offset}`);
    return response.data;
};

export const getAdminOrchestratorEvents = async (limit = 200) => {
    const response = await api.get(`/admin/orchestrator/events?limit=${limit}`);
    return response.data;
};

export const getAdminFinanceSummary = async () => {
    const response = await api.get('/admin/finance/summary');
    return response.data;
};

export const getAdminPixelHealth = async () => {
    const response = await api.get('/pixel/admin/health');
    return response.data;
};

export const getPixelSiteStats = async (siteId, days = 30) => {
    const response = await api.get(`/pixel/sites/${siteId}/stats?days=${days}`);
    return response.data;
};

export const getPixelRealtime = async (siteId) => {
    const response = await api.get(`/pixel/sites/${siteId}/realtime`);
    return response.data;
};

export const getPixelFunnel = async (siteId, days = 30) => {
    const response = await api.get(`/pixel/sites/${siteId}/funnel?days=${days}`);
    return response.data;
};

export const getPixelTimeseries = async (siteId, days = 30) => {
    const response = await api.get(`/pixel/sites/${siteId}/timeseries?days=${days}`);
    return response.data;
};

export const getPixelDevices = async (siteId, days = 30) => {
    const response = await api.get(`/pixel/sites/${siteId}/devices?days=${days}`);
    return response.data;
};

export const getPixelCountries = async (siteId, days = 30) => {
    const response = await api.get(`/pixel/sites/${siteId}/countries?days=${days}`);
    return response.data;
};

export const getPixelPages = async (siteId, days = 30) => {
    const response = await api.get(`/pixel/sites/${siteId}/pages?days=${days}`);
    return response.data;
};

export const startSupportSession = async (userId) => {
    const response = await api.post(`/admin/impersonate/${userId}`);
    return response.data;
};

export const getSupportSessions = async () => {
    const response = await api.get('/admin/impersonate/sessions');
    return response.data;
};

export const getSessionDetail = async (sessionId) => {
    const response = await api.get(`/admin/impersonate/sessions/${sessionId}`);
    return response.data;
};

export const closeSession = async (sessionId, result, resolutionNotes, actionTaken) => {
    const response = await api.post(`/admin/impersonate/${sessionId}/close`, {
        result,
        resolution_notes: resolutionNotes,
        action_taken: actionTaken,
    });
    return response.data;
};

export const closeStaffSession = async (sessionId, result, resolutionNotes, actionTaken) => {
    const response = await api.post(`/admin/impersonate/staff/${sessionId}/close`, {
        result,
        resolution_notes: resolutionNotes,
        action_taken: actionTaken,
    });
    return response.data;
};

export const startSupportSessionWithIssue = async (userId, issueDescription, origin = 'manual') => {
    const response = await api.post(`/admin/impersonate/staff/${userId}`, {
        issue_description: issueDescription,
        origin,
    });
    return response.data;
};

export const revokeSupportSession = async (sessionId) => {
    const response = await api.delete(`/admin/impersonate/${sessionId}`);
    return response.data;
};

export const listFiles = async (hostingId, path = '') => {
    const response = await api.get(`/files/${hostingId}`, { params: { path } });
    return response.data;
};

export const readFile = async (hostingId, path) => {
    const response = await api.get(`/files/${hostingId}/read`, { params: { path } });
    return response.data;
};

export const diagnoseHosting = async (hostingId) => {
  const response = await api.post(`/hosting/${hostingId}/diagnose`);
  return response.data;
};

export const getHostingHealth = async (hostingId) => {
  const response = await api.get(`/health/${hostingId}`);
  return response.data;
};

export const getHostingHealthHistory = async (hostingId, limit = 24) => {
  const response = await api.get(`/health/${hostingId}/history`, { params: { limit } });
  return response.data;
};

export const getUserAlerts = async (limit = 20) => {
  const response = await api.get('/user/alerts', { params: { limit } });
  return response.data;
};

export const getRecentActivity = async (limit = 20) => {
  const response = await api.get('/user/recent-activity', { params: { limit } });
  return response.data;
};


export const resolveAlert = async (alertId) => {
  const response = await api.post(`/alerts/${alertId}/resolve`);
  return response.data;
};

export const getDashboardSummary = async () => {
  const response = await api.get('/dashboard/summary');
  return response.data;
};

export const saveFile = async (hostingId, path, content) => {
    const response = await api.post(`/files/${hostingId}/save`, { path, content });
    return response.data;
};

// ---------------------------------------------------------------------------
// Staff — gestión de colaboradores (admin)
// ---------------------------------------------------------------------------

export const createStaff = async (data) => {
  const response = await api.post('/admin/staff', data);
  return response.data;
};

export const listStaff = async () => {
  const response = await api.get('/admin/staff');
  return response.data;
};

export const updateStaff = async (staffId, data) => {
  const response = await api.patch(`/admin/staff/${staffId}`, data);
  return response.data;
};

export const deactivateStaff = async (staffId) => {
  const response = await api.delete(`/admin/staff/${staffId}`);
  return response.data;
};

export const resetStaffPassword = async (staffId) => {
  const response = await api.post(`/admin/staff/${staffId}/reset-password`);
  return response.data;
};

export const getStaffActivity = async (staffId, limit = 100) => {
  const response = await api.get(`/admin/staff/${staffId}/activity`, { params: { limit } });
  return response.data;
};

export const getStaffAnalytics = async (days = 30) => {
  const response = await api.get('/admin/staff/analytics', { params: { days } });
  return response.data;
};

// ---------------------------------------------------------------------------
// Staff — sesión propia del colaborador
// ---------------------------------------------------------------------------

export const staffLogin = async (email, password) => {
  const response = await api.post('/staff/login', { email, password });
  return response.data;
};

export const staffLogout = async () => {
  const response = await api.post('/staff/logout');
  return response.data;
};

export const getStaffMe = async () => {
  const response = await api.get('/staff/me');
  return response.data;
};

export const getStaffClients = async () => {
  const response = await api.get('/staff/clients');
  return response.data;
};

export const getMyActivity = async (limit = 50) => {
  const response = await api.get('/staff/my-activity', { params: { limit } });
  return response.data;
};

// Staff inicia una sesión de soporte (rol support)
export const staffStartSupportSession = async (userId) => {
  const response = await api.post(`/admin/impersonate/staff/${userId}`);
  return response.data;
};

// ---------------------------------------------------------------------------
// Staff activity tracking (fire-and-forget, nunca lanza)
// ---------------------------------------------------------------------------

export const trackActivity = async (data) => {
  // No lanzar nunca — el tracking no debe interrumpir la UI
  try {
    const response = await api.post('/staff/activity', data);
    return response.data;
  } catch {
    return null;
  }
};

export default api;

// ---------------------------------------------------------------------------
// Support Chat — cliente
// ---------------------------------------------------------------------------

export const getSupportCategories = async () => {
  const response = await api.get('/support/categories');
  return response.data;
};

export const createSupportTicket = async (data) => {
  const response = await api.post('/support/tickets', data);
  return response.data;
};

export const getMyTickets = async () => {
  const response = await api.get('/support/tickets');
  return response.data;
};

export const getTicketDetail = async (ticketId) => {
  const response = await api.get(`/support/tickets/${ticketId}`);
  return response.data;
};

export const sendTicketMessage = async (ticketId, content) => {
  const response = await api.post(`/support/tickets/${ticketId}/messages`, { content });
  return response.data;
};

export const escalateTicket = async (ticketId, reason) => {
  const response = await api.post(`/support/tickets/${ticketId}/escalate`, { reason });
  return response.data;
};

export const resolveTicket = async (ticketId, resolution_note) => {
  const response = await api.post(`/support/tickets/${ticketId}/resolve`, { resolution_note });
  return response.data;
};

// ---------------------------------------------------------------------------
// Support Chat — staff
// ---------------------------------------------------------------------------

export const getSupportQueue = async () => {
  const response = await api.get('/support/queue');
  return response.data;
};

export const assignTicket = async (ticketId) => {
  const response = await api.post(`/support/tickets/${ticketId}/assign`);
  return response.data;
};

export const getAllTickets = async () => {
  const response = await api.get('/support/tickets');
  return response.data;
};

export const createSupportWebSocket = (ticketId) => {
  const wsBase = (import.meta.env.VITE_API_URL || 'https://api.hostingguard.lat')
    .replace('https://', 'wss://')
    .replace('http://', 'ws://');
  return new WebSocket(`${wsBase}/ws/support/${ticketId}`);
};
