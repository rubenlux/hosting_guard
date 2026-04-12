import client from './client';

export const topupBalance       = (amount)       => client.post('/billing/topup', { amount }).then(r => r.data);
export const updateUserConfig   = (config)       => client.patch('/user/config', config).then(r => r.data);
