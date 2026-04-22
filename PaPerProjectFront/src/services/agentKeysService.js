import { companyApi } from './companyAuthService';

export const listAgentKeys = () => companyApi.get('/company/agent-keys');

export const upsertByokKey = ({ agent_name, provider, api_key }) =>
  companyApi.post('/company/agent-keys/byok', { agent_name, provider, api_key });

export const revokeByokKey = (agentName) =>
  companyApi.delete(`/company/agent-keys/byok/${agentName}`);

export const listKeyRequests = () => companyApi.get('/company/key-requests');

export const createKeyRequest = ({ agent_name, provider, note }) =>
  companyApi.post('/company/key-requests/create', { agent_name, provider, note });

export default {
  listAgentKeys,
  upsertByokKey,
  revokeByokKey,
  listKeyRequests,
  createKeyRequest,
};
