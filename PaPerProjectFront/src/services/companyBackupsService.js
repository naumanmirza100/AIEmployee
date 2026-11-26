import { API_BASE_URL } from '@/config/apiConfig';
import { companyApi } from '@/services/companyAuthService';

// The company's own backups (owners and admins only): its data across the agents and its uploaded files in one zip.
export const listBackups = () => companyApi.get('/company/backups');

export const startBackup = () => companyApi.post('/company/backups');

export const deleteBackup = (id) => companyApi.delete(`/company/backups/${id}`);

// A backup can be large, so the browser downloads it itself (streamed to disk) rather than through fetch.
// The link carries a short-lived signed ticket in place of the login token.
export const downloadBackup = async (id) => {
  const { ticket } = await companyApi.post(`/company/backups/${id}/link`);
  window.location.href = `${API_BASE_URL}/company/backups/${id}/download?ticket=${encodeURIComponent(ticket)}`;
};

export default { listBackups, startBackup, deleteBackup, downloadBackup };
