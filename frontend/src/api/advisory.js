import client from './client';

export const getUserAlerts    = (limit=20) => client.get('/alerts', { params: { limit } }).then(r => r.data);
export const resolveAlert     = (alertId)  => client.patch(`/alerts/${alertId}/resolve`).then(r => r.data);
export const getRecentActivity= (limit=20) => client.get('/activity', { params: { limit } }).then(r => r.data);
