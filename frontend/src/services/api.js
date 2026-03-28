import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'https://api.hostingguard.lat';

const api = axios.create({
  baseURL: API_URL,
});

// Interceptor para añadir el token a todas las peticiones
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Interceptor para errores de respuesta (especialmente 401)
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      if (typeof window !== 'undefined') {
        window.location.href = '/'; 
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

export default api;
