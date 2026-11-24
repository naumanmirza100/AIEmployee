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

// Whole-system backups (super admin only): the database and the uploaded files in one zip.
export const listBackups = () => req('/admin/backups');

export const startBackup = () => req('/admin/backups', { method: 'POST' });

export const deleteBackup = (id) => req(`/admin/backups/${id}`, { method: 'DELETE' });

// A backup can be gigabytes, so the browser downloads it itself (streamed to disk) rather than through fetch.
// The link carries a short-lived signed ticket in place of the login token.
export const downloadBackup = async (id) => {
  const { ticket } = await req(`/admin/backups/${id}/link`, { method: 'POST' });
  window.location.href = `${API_BASE_URL}/admin/backups/${id}/download?ticket=${encodeURIComponent(ticket)}`;
};

export default { listBackups, startBackup, deleteBackup, downloadBackup };
