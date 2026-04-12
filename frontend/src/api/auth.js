import client from './client';

export const getMe        = () => client.get('/me').then(r => r.data);
export const login        = (email, password) => client.post('/login', { email, password }).then(r => r.data);
export const register     = (email, password) => client.post('/register', { email, password }).then(r => r.data);
export const logout       = () => client.post('/logout').then(r => r.data);
export const refreshToken = () => client.post('/refresh').then(r => r.data);
