import { companyApi } from './companyAuthService';

export const listAgentKeys = () => companyApi.get('/company/agent-keys');

export const upsertByokKey = ({ agent_name, provider, api_key }) =>
  companyApi.post('/company/agent-keys/byok', { agent_name, provider, api_key });

export const revokeByokKey = (agentName) =>
  companyApi.delete(`/company/agent-keys/byok/${agentName}`);

export const setTokenPool = ({ agent_name, preferred_pool }) =>
  companyApi.post('/company/agent-keys/pool', { agent_name, preferred_pool });

export const setByokLimit = ({ agent_name, limit }) =>
  companyApi.post('/company/agent-keys/byok-limit', { agent_name, limit });

// This company's weekly managed-token reset history (own data only).
export const listResetLogs = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return companyApi.get(`/company/agent-keys/reset-logs${qs ? `?${qs}` : ''}`);
};

// Managed-key lifecycle history (assigned / renewed / expired / revoked).
// The key row itself is overwritten on every re-issue, so this log is the only
// place previous expiry and renewal dates survive.
export const listKeyEvents = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return companyApi.get(`/company/agent-keys/key-events${qs ? `?${qs}` : ''}`);
};

export const listKeyRequests = () => companyApi.get('/company/key-requests');

export const createKeyRequest = ({ agent_name, provider, note, preferred_duration, is_renewal }) =>
  companyApi.post('/company/key-requests/create', { agent_name, provider, note, preferred_duration, is_renewal });

export const payForRequest = (requestId) =>
  companyApi.post(`/company/key-requests/${requestId}/pay`, {});

export const createKeyPaymentSession = (requestId) =>
  companyApi.post(`/company/key-requests/${requestId}/checkout`, {});

export const verifyKeyPaymentSession = (sessionId) =>
  companyApi.get(`/company/key-requests/verify-session/${sessionId}`);

export default {
  listAgentKeys,
  upsertByokKey,
  revokeByokKey,
  setTokenPool,
  setByokLimit,
  listResetLogs,
  listKeyEvents,
  listKeyRequests,
  createKeyRequest,
  payForRequest,
  createKeyPaymentSession,
  verifyKeyPaymentSession,
};
