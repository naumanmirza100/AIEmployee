/**
 * Marketing Agent Service
 * API calls for marketing agent features
 */

import { companyApi } from './companyAuthService';

/**
 * Get marketing dashboard stats and overview
 */
export const getMarketingDashboard = async () => {
  try {
    const response = await companyApi.get('/marketing/dashboard');
    return response;
  } catch (error) {
    console.error('Get marketing dashboard error:', error);
    throw error;
  }
};

/**
 * List campaigns
 */
export const listCampaigns = async (params = {}) => {
  try {
    const response = await companyApi.get('/marketing/campaigns', params);
    return response;
  } catch (error) {
    console.error('List campaigns error:', error);
    throw error;
  }
};

/**
 * Get campaign details. Pass { detail: 1 } for full detail (stats, analytics, email_sends, leads).
 */
export const getCampaign = async (campaignId, params = {}) => {
  try {
    const query = params.detail ? { detail: 1 } : {};
    const response = await companyApi.get(`/marketing/campaigns/${campaignId}`, query);
    return response;
  } catch (error) {
    console.error('Get campaign error:', error);
    throw error;
  }
};

/**
 * List email sequences for a campaign (for sequence management page).
 */
export const getSequences = async (campaignId) => {
  try {
    const response = await companyApi.get(`/marketing/campaigns/${campaignId}/sequences`);
    return response;
  } catch (error) {
    console.error('Get sequences error:', error);
    throw error;
  }
};

/**
 * Get full email sending status (stats + emails by sequence) for email status page.
 */
export const getEmailStatusFull = async (campaignId) => {
  try {
    const response = await companyApi.get(`/marketing/campaigns/${campaignId}/email-status/full`);
    return response;
  } catch (error) {
    console.error('Get email status full error:', error);
    throw error;
  }
};

/**
 * Create email sequence
 */
export const createSequence = async (campaignId, data) => {
  try {
    const response = await companyApi.post(`/marketing/campaigns/${campaignId}/sequences/create`, data);
    return response;
  } catch (error) {
    console.error('Create sequence error:', error);
    throw error;
  }
};

/**
 * Get sequence details
 */
export const getSequenceDetails = async (campaignId, sequenceId) => {
  try {
    const response = await companyApi.get(`/marketing/campaigns/${campaignId}/sequences/${sequenceId}`);
    return response;
  } catch (error) {
    console.error('Get sequence details error:', error);
    throw error;
  }
};

/**
 * Update sequence
 */
export const updateSequence = async (campaignId, sequenceId, data) => {
  try {
    const response = await companyApi.put(`/marketing/campaigns/${campaignId}/sequences/${sequenceId}/update`, data);
    return response;
  } catch (error) {
    console.error('Update sequence error:', error);
    throw error;
  }
};

/**
 * Delete sequence
 */
export const deleteSequence = async (campaignId, sequenceId) => {
  try {
    const response = await companyApi.post(`/marketing/campaigns/${campaignId}/sequences/${sequenceId}/delete`, {});
    return response;
  } catch (error) {
    console.error('Delete sequence error:', error);
    throw error;
  }
};

/**
 * Create email template
 */
export const createTemplate = async (campaignId, data) => {
  try {
    const response = await companyApi.post(`/marketing/campaigns/${campaignId}/templates`, data);
    return response;
  } catch (error) {
    console.error('Create template error:', error);
    throw error;
  }
};

/**
 * Update email template
 */
export const updateTemplate = async (campaignId, templateId, data) => {
  try {
    const response = await companyApi.put(`/marketing/campaigns/${campaignId}/templates/${templateId}/update`, data);
    return response;
  } catch (error) {
    console.error('Update template error:', error);
    throw error;
  }
};

/**
 * Delete email template
 */
export const deleteTemplate = async (campaignId, templateId) => {
  try {
    const response = await companyApi.post(`/marketing/campaigns/${campaignId}/templates/${templateId}/delete`, {});
    return response;
  } catch (error) {
    console.error('Delete template error:', error);
    throw error;
  }
};

/**
 * List email accounts
 */
export const listEmailAccounts = async () => {
  try {
    const response = await companyApi.get('/marketing/email-accounts');
    return response;
  } catch (error) {
    console.error('List email accounts error:', error);
    throw error;
  }
};

/**
 * Create email account
 */
export const createEmailAccount = async (data) => {
  try {
    const response = await companyApi.post('/marketing/email-accounts/create', data);
    return response;
  } catch (error) {
    console.error('Create email account error:', error);
    throw error;
  }
};

/**
 * Get email account (for edit)
 */
export const getEmailAccount = async (accountId) => {
  try {
    const response = await companyApi.get(`/marketing/email-accounts/${accountId}`);
    return response;
  } catch (error) {
    console.error('Get email account error:', error);
    throw error;
  }
};

/**
 * Update email account
 */
export const updateEmailAccount = async (accountId, data) => {
  try {
    const response = await companyApi.put(`/marketing/email-accounts/${accountId}/update`, data);
    return response;
  } catch (error) {
    console.error('Update email account error:', error);
    throw error;
  }
};

/**
 * Delete email account
 */
export const deleteEmailAccount = async (accountId) => {
  try {
    const response = await companyApi.post(`/marketing/email-accounts/${accountId}/delete`, {});
    return response;
  } catch (error) {
    console.error('Delete email account error:', error);
    throw error;
  }
};

/**
 * Test email account (send test email)
 */
export const testEmailAccount = async (accountId, testEmail) => {
  try {
    const response = await companyApi.post(`/marketing/email-accounts/${accountId}/test`, { test_email: testEmail });
    return response;
  } catch (error) {
    console.error('Test email account error:', error);
    throw error;
  }
};

/**
 * Update campaign
 */
export const updateCampaign = async (campaignId, data) => {
  try {
    const response = await companyApi.put(`/marketing/campaigns/${campaignId}/update`, data);
    return response;
  } catch (error) {
    console.error('Update campaign error:', error);
    throw error;
  }
};

/**
 * Stop campaign (set status to paused)
 */
export const campaignStop = async (campaignId) => {
  try {
    const response = await companyApi.post(`/marketing/campaigns/${campaignId}/stop`, {});
    return response;
  } catch (error) {
    console.error('Campaign stop error:', error);
    throw error;
  }
};

/**
 * Delete campaign
 */
export const campaignDelete = async (campaignId) => {
  try {
    const response = await companyApi.post(`/marketing/campaigns/${campaignId}/delete`, {});
    return response;
  } catch (error) {
    console.error('Campaign delete error:', error);
    throw error;
  }
};

/**
 * Add lead to campaign
 */
export const addCampaignLead = async (campaignId, data) => {
  try {
    const response = await companyApi.post(`/marketing/campaigns/${campaignId}/leads/add`, data);
    return response;
  } catch (error) {
    console.error('Add campaign lead error:', error);
    throw error;
  }
};

/**
 * Update lead
 */
export const updateCampaignLead = async (campaignId, leadId, data) => {
  try {
    const response = await companyApi.put(`/marketing/campaigns/${campaignId}/leads/${leadId}`, data);
    return response;
  } catch (error) {
    console.error('Update campaign lead error:', error);
    throw error;
  }
};

/**
 * Delete lead from campaign
 */
export const deleteCampaignLead = async (campaignId, leadId) => {
  try {
    const response = await companyApi.post(`/marketing/campaigns/${campaignId}/leads/${leadId}/delete`, {});
    return response;
  } catch (error) {
    console.error('Delete campaign lead error:', error);
    throw error;
  }
};

/**
 * Upload leads CSV/Excel for campaign. Uses FormData with file key.
 */
export const uploadCampaignLeads = async (campaignId, file) => {
  try {
    const token = localStorage.getItem('company_auth_token');
    // Base URL must not end with slash so we get /api/marketing/... not /api//marketing/...
    const base = (import.meta.env.VITE_API_URL || 'http://localhost:8000/api').replace(/\/+$/, '');
    const formData = new FormData();
    formData.append('file', file);
    const url = `${base}/marketing/campaigns/${campaignId}/leads/upload`;
    const response = await fetch(url, {
      method: 'POST',
      headers: token ? { 'Authorization': `Token ${token}` } : {},
      body: formData,
    });
    const contentType = response.headers.get('content-type') || '';
    let data;
    if (contentType.includes('application/json')) {
      try {
        data = await response.json();
      } catch (_) {
        if (!response.ok) throw new Error(`Upload failed (${response.status}): ${response.statusText}. Check VITE_API_URL (e.g. http://localhost:8000/api).`);
        throw new Error('Invalid JSON response from server.');
      }
    } else {
      const text = await response.text();
      if (!response.ok) {
        throw new Error(`Upload failed (${response.status}): ${response.statusText}. Ensure VITE_API_URL points to the API root (e.g. http://localhost:8000/api).`);
      }
      throw new Error('Server did not return JSON. Check API URL and server.');
    }
    if (!response.ok) throw new Error(data?.message || data?.error || `HTTP ${response.status}`);
    if (data.status === 'error') throw new Error(data.message || data.error || 'Upload failed');
    return data;
  } catch (error) {
    console.error('Upload campaign leads error:', error);
    throw error;
  }
};

/**
 * Get URL for exporting campaign leads (CSV). Use with fetch + blob for download with auth.
 */
export const getExportLeadsUrl = (campaignId) => {
  const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
  return `${API_BASE_URL}/marketing/campaigns/${campaignId}/leads/export/`;
};

/**
 * Create campaign
 */
export const createCampaign = async (campaignData) => {
  try {
    const response = await companyApi.post('/marketing/campaigns/create', campaignData);
    return response;
  } catch (error) {
    console.error('Create campaign error:', error);
    throw error;
  }
};

/**
 * Marketing Q&A Agent
 */
export const marketingQA = async (question) => {
  try {
    const response = await companyApi.post('/marketing/qa', { question });
    return response;
  } catch (error) {
    console.error('Marketing Q&A error:', error);
    throw error;
  }
};

/**
 * Market Research Agent
 */
export const marketResearch = async (researchType, topic, context = {}) => {
  try {
    const response = await companyApi.post('/marketing/market-research', {
      research_type: researchType,
      topic,
      context,
    });
    return response;
  } catch (error) {
    console.error('Market research error:', error);
    throw error;
  }
};

/**
 * Outreach Campaign Agent
 * API: POST /api/marketing/outreach-campaign
 * With file: multipart/form-data (action, campaign_data, campaign_id?, context?, file).
 * Without file: application/json { action, campaign_data?, campaign_id?, context? }.
 * Response: { status: 'success', data: <agent result> } or { status: 'error', message, error }.
 */
export const outreachCampaign = async (action, campaignData = {}, campaignId = null, context = {}, file = null) => {
  try {
    if (file) {
      const formData = new FormData();
      formData.append('action', action);
      formData.append('campaign_data', JSON.stringify(campaignData));
      formData.append('context', JSON.stringify(context || {}));
      if (campaignId != null && campaignId !== '') {
        formData.append('campaign_id', String(campaignId));
      }
      formData.append('file', file);

      const token = localStorage.getItem('company_auth_token');
      const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

      const response = await fetch(`${API_BASE_URL}/marketing/outreach-campaign`, {
        method: 'POST',
        headers: token ? { 'Authorization': `Token ${token}` } : {},
        body: formData,
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.message || data.error || `HTTP ${response.status}`);
      }
      if (data.status === 'error') {
        throw new Error(data.message || data.error || 'Outreach campaign failed');
      }
      return data.data ?? data;
    }

    const body = {
      action,
      campaign_data: campaignData,
      context: context || {},
    };
    if (campaignId != null && campaignId !== '') {
      body.campaign_id = Number(campaignId);
    }

    const response = await companyApi.post('/marketing/outreach-campaign', body);
    if (response.status === 'error') {
      throw new Error(response.message || response.error || 'Outreach campaign failed');
    }
    return response.data;
  } catch (error) {
    console.error('Outreach campaign error:', error);
    throw error;
  }
};

/**
 * Document Authoring Agent.
 * API: POST /api/marketing/document-authoring
 * Body: { action, document_type, document_data, campaign_id?, context }.
 * Response: { status: 'success', data: { success, title?, content?, message?, document_id?, error? } }
 *   or { status: 'error', message } on failure.
 */
export const documentAuthoring = async (action, documentType, documentData = {}, campaignId = null, context = {}) => {
  try {
    const body = {
      action: action || 'create',
      document_type: documentType,
      document_data: documentData || {},
      context: context || {},
    };
    if (campaignId != null && campaignId !== '') body.campaign_id = Number(campaignId);
    const response = await companyApi.post('/marketing/document-authoring', body);
    return response;
  } catch (error) {
    console.error('Document authoring error:', error);
    throw error;
  }
};

/**
 * Get notifications (Proactive Notification sub-agent).
 * API: GET /api/marketing/notifications
 * Query params: unread_only (boolean), type (string), campaign_id (number).
 * Response: { status: 'success', data: { success, count, unread_count, notifications[] } }
 *   or { status: 'error', message } on failure.
 */
export const getNotifications = async (params = {}) => {
  try {
    const query = {};
    if (params.unread_only !== undefined) query.unread_only = String(params.unread_only);
    if (params.type) query.type = params.type;
    if (params.campaign_id != null) query.campaign_id = params.campaign_id;
    const response = await companyApi.get('/marketing/notifications', query);
    return response;
  } catch (error) {
    console.error('Get notifications error:', error);
    throw error;
  }
};

/**
 * Run Proactive Notification Agent (monitor campaigns).
 * API: POST /api/marketing/notifications/monitor
 * Body: { action?: 'monitor'|'check_campaign', campaign_id?: number, context?: {} }
 * Response: { status: 'success', data: { success, campaigns_monitored?, notifications_created?, issues_found?, opportunities_found?, ... } }
 */
export const monitorCampaigns = async (campaignId = null) => {
  try {
    const body = {
      action: campaignId ? 'check_campaign' : 'monitor',
      campaign_id: campaignId != null && campaignId !== '' ? Number(campaignId) : null,
      context: {},
    };
    const response = await companyApi.post('/marketing/notifications/monitor', body);
    return response;
  } catch (error) {
    console.error('Monitor campaigns error:', error);
    throw error;
  }
};

/**
 * Mark a marketing notification as read.
 * API: POST /api/marketing/notifications/:id/read
 */
export const markNotificationRead = async (notificationId) => {
  try {
    const response = await companyApi.post(`/marketing/notifications/${notificationId}/read`, {});
    return response;
  } catch (error) {
    console.error('Mark notification read error:', error);
    throw error;
  }
};

/**
 * Delete a marketing notification.
 * API: POST /api/marketing/notifications/:id/delete
 */
export const deleteNotification = async (notificationId) => {
  try {
    const response = await companyApi.post(`/marketing/notifications/${notificationId}/delete`, {});
    return response;
  } catch (error) {
    console.error('Delete notification error:', error);
    throw error;
  }
};

export default {
  getMarketingDashboard,
  listCampaigns,
  getCampaign,
  getSequences,
  getEmailStatusFull,
  createSequence,
  getSequenceDetails,
  updateSequence,
  deleteSequence,
  createTemplate,
  updateTemplate,
  deleteTemplate,
  listEmailAccounts,
  createEmailAccount,
  getEmailAccount,
  updateEmailAccount,
  deleteEmailAccount,
  testEmailAccount,
  createCampaign,
  updateCampaign,
  campaignStop,
  campaignDelete,
  addCampaignLead,
  updateCampaignLead,
  deleteCampaignLead,
  uploadCampaignLeads,
  getExportLeadsUrl,
  marketingQA,
  marketResearch,
  outreachCampaign,
  documentAuthoring,
  getNotifications,
  monitorCampaigns,
  markNotificationRead,
  deleteNotification,
};

