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

// The parts of the AI SDR that can be checked, each with its latest result, plus the run in progress.
export const getOverview = () => req('/admin/sdr-checks').then((r) => r.data);

// suite: a part's key, or 'all' for every AI SDR test.
export const startRun = (suite) =>
  req('/admin/sdr-checks/run', { method: 'POST', body: JSON.stringify({ suite }) }).then((r) => r.data);

// One run with every test's outcome; with `suite`, only that part's tests.
export const getRun = (runId, suite) =>
  req(`/admin/sdr-checks/runs/${runId}${suite ? `?suite=${encodeURIComponent(suite)}` : ''}`).then((r) => r.data);

export default { getOverview, startRun, getRun };
