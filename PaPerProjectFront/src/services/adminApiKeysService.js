import { API_BASE_URL } from '@/config/apiConfig';

const getToken = () => localStorage.getItem('auth_token');

const req = async (path, options = {}) => {
  const token = getToken();
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Token ${token}` } : {}),
    ...(options.headers || {}),
  };
  const res = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  let data = null;
  try { data = await res.json(); } catch { /* empty */ }
  if (!res.ok) throw new Error(data?.message || `Request failed (${res.status})`);
  return data;
};

export const getOverview = () => req('/admin/api-keys/overview');

export const listAllKeys = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return req(`/admin/api-keys${qs ? `?${qs}` : ''}`);
};

export const assignManagedKey = (payload) =>
  req('/admin/api-keys/assign', { method: 'POST', body: JSON.stringify(payload) });

export const revokeKey = (keyId) =>
  req(`/admin/api-keys/${keyId}/revoke`, { method: 'POST' });

export const listPricing = () => req('/admin/pricing-config');

export const updatePricing = (agentName, payload) =>
  req(`/admin/pricing-config/${agentName}`, { method: 'PUT', body: JSON.stringify(payload) });

export const listQuotas = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return req(`/admin/token-quotas${qs ? `?${qs}` : ''}`);
};

export const adjustQuota = (quotaId, payload) =>
  req(`/admin/token-quotas/${quotaId}`, { method: 'PATCH', body: JSON.stringify(payload) });

export const listRequests = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return req(`/admin/key-requests${qs ? `?${qs}` : ''}`);
};

export const rejectRequest = (requestId, adminNote) =>
  req(`/admin/key-requests/${requestId}/reject`, {
    method: 'POST',
    body: JSON.stringify({ admin_note: adminNote || '' }),
  });

export const listPlatformKeys = () => req('/admin/platform-keys');

export const upsertPlatformKey = (provider, apiKey) =>
  req('/admin/platform-keys/upsert', {
    method: 'POST',
    body: JSON.stringify({ provider, api_key: apiKey }),
  });

export const revokePlatformKey = (provider) =>
  req(`/admin/platform-keys/${provider}/revoke`, { method: 'POST' });

export const listCompaniesSimple = (search = '') =>
  req(`/admin/companies-list${search ? `?search=${encodeURIComponent(search)}` : ''}`);

export default {
  getOverview,
  listAllKeys,
  assignManagedKey,
  revokeKey,
  listPricing,
  updatePricing,
  listQuotas,
  adjustQuota,
  listRequests,
  rejectRequest,
  listPlatformKeys,
  upsertPlatformKey,
  revokePlatformKey,
  listCompaniesSimple,
};
