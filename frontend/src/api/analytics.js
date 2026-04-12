import client from './client';

export const getPixelSiteStats       = (siteId, days=30)  => client.get(`/pixel/sites/${siteId}/stats`, { params: { days } }).then(r => r.data);
export const getPixelRealtime        = (siteId)           => client.get(`/pixel/sites/${siteId}/realtime`).then(r => r.data);
export const getPixelTimeseries      = (siteId, days=30)  => client.get(`/pixel/sites/${siteId}/timeseries`, { params: { days } }).then(r => r.data);
export const getPixelDevices         = (siteId, days=30)  => client.get(`/pixel/sites/${siteId}/devices`, { params: { days } }).then(r => r.data);
export const getPixelCountries       = (siteId, days=30)  => client.get(`/pixel/sites/${siteId}/countries`, { params: { days } }).then(r => r.data);
export const getPixelPages           = (siteId, days=30)  => client.get(`/pixel/sites/${siteId}/pages`, { params: { days } }).then(r => r.data);
export const getPixelFunnel          = (siteId, days=30)  => client.get(`/pixel/sites/${siteId}/funnel`, { params: { days } }).then(r => r.data);
export const getPixelDashboardSummary= (siteId, days=7)   => client.get(`/pixel/sites/${siteId}/dashboard-summary`, { params: { days } }).then(r => r.data);
