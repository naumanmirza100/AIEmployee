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

// The demo companies (super admin only): what there is, whether it is in the database, and its logins.
export const getTestData = () => req('/admin/test-data');

// Add ('load') or remove ('remove') the test data in the background. Resolves with { data: run }.
export const startTestDataJob = (action, keys = []) =>
  req(`/admin/test-data/${action}`, { method: 'POST', body: JSON.stringify({ keys }) });

// How far a run has got: { data: { processing_status, percent, chunks_processed, chunks_total, step, ... } }.
export const getTestDataRun = (id) => req(`/admin/test-data/runs/${id}`);

export default { getTestData, startTestDataJob, getTestDataRun };
