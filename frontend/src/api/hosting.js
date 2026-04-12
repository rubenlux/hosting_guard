import client from './client';

export const getDashboardSummary    = ()             => client.get('/dashboard/summary').then(r => r.data);
export const createHosting          = (name, plan)   => client.post('/create-hosting', { name, plan }).then(r => r.data);
export const listHostings           = ()             => client.get('/hosting').then(r => r.data);
export const deleteHosting          = (id)           => client.delete(`/hosting/${id}`).then(r => r.data);
export const restartHosting         = (id)           => client.post(`/hosting/${id}/restart`).then(r => r.data);
export const stopHosting            = (id)           => client.post(`/hosting/${id}/stop`).then(r => r.data);
export const startHosting           = (id)           => client.post(`/hosting/${id}/start`).then(r => r.data);
export const getLogs                = (id, since)    => client.get(`/hosting/${id}/logs`, { params: since ? { since } : {} }).then(r => r.data);
export const diagnoseHosting        = (id)           => client.post(`/hosting/${id}/diagnose`).then(r => r.data);
export const getHostingHealth       = (id)           => client.get(`/hosting/${id}/health`).then(r => r.data);
export const getHostingHealthHistory= (id, limit=24) => client.get(`/hosting/${id}/health/history`, { params: { limit } }).then(r => r.data);
