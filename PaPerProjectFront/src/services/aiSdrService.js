import { companyApi } from './companyAuthService';

// --------------------------------------------------------------------------
// SDR Agent Settings (per-user API keys)
// --------------------------------------------------------------------------
export const getSdrSettings = async () => {
  try {
    return await companyApi.get('/sdr/settings/');
  } catch (error) {
    console.error('SDR settings error:', error);
    throw error;
  }
};

export const saveSdrSettings = async (data) => {
  try {
    return await companyApi.post('/sdr/settings/', data);
  } catch (error) {
    console.error('SDR save settings error:', error);
    throw error;
  }
};

// --------------------------------------------------------------------------
// Dashboard
// --------------------------------------------------------------------------
export const getSdrDashboard = async () => {
  try {
    return await companyApi.get('/sdr/dashboard/');
  } catch (error) {
    console.error('SDR dashboard error:', error);
    throw error;
  }
};

// --------------------------------------------------------------------------
// ICP Profile
// --------------------------------------------------------------------------
export const getIcpProfile = async () => {
  try {
    return await companyApi.get('/sdr/icp/');
  } catch (error) {
    console.error('Get ICP error:', error);
    throw error;
  }
};

export const listIcpProfiles = async () => {
  try {
    const res = await companyApi.get('/sdr/icp/');
    return res?.data?.all || res?.all || [];
  } catch (error) {
    console.error('List ICP profiles error:', error);
    return [];
  }
};

export const saveIcpProfile = async (data) => {
  try {
    return await companyApi.post('/sdr/icp/', data);
  } catch (error) {
    console.error('Save ICP error:', error);
    throw error;
  }
};

// Several ICPs: each lead is scored with the ICP it was found for; the default one is preselected in the dialogs.
export const createIcpProfile = (data) => saveIcpProfile({ ...data, new: true });
export const updateIcpProfile = (id, data) => saveIcpProfile({ ...data, id });
export const setDefaultIcpProfile = async (id) => companyApi.post(`/sdr/icp/${id}/default/`);
export const deleteIcpProfile = async (id) => companyApi.delete(`/sdr/icp/${id}/`);

// --------------------------------------------------------------------------
// Leads — CRUD
// --------------------------------------------------------------------------
export const listLeads = async ({
  search = '', temperature = '', status = '', source = '', category = '', enrichment = '', icp = '',
  sort = 'score_desc', page = 1, page_size = 25, not_in_campaign = '',
} = {}) => {
  try {
    const params = new URLSearchParams();
    if (search)      params.set('search', search);
    if (not_in_campaign) params.set('not_in_campaign', not_in_campaign);
    if (temperature) params.set('temperature', temperature);
    if (status)      params.set('status', status);
    if (source)      params.set('source', source);
    if (category)    params.set('category', category);   // a category id, or 'none'
    if (enrichment)  params.set('enrichment', enrichment); // done / not / in_progress / failed
    if (icp)         params.set('icp', icp);               // an ICP id, or 'none'
    if (sort)        params.set('sort', sort);
    params.set('page', page);
    params.set('page_size', page_size);
    return await companyApi.get(`/sdr/leads/?${params.toString()}`);
  } catch (error) {
    console.error('List leads error:', error);
    throw error;
  }
};

/**
 * Export ALL leads matching the current filters as a CSV blob (server-side, no
 * pagination) so thousands of leads can be exported in one download.
 */
export const exportAllLeadsCsv = async ({ search = '', temperature = '', status = '', source = '', category = '', enrichment = '', icp = '', sort = 'score_desc' } = {}) => {
  const params = {};
  if (search)      params.search = search;
  if (temperature) params.temperature = temperature;
  if (status)      params.status = status;
  if (source)      params.source = source;
  if (category)    params.category = category;
  if (enrichment)  params.enrichment = enrichment;
  if (icp)         params.icp = icp;
  if (sort)        params.sort = sort;
  // The filters go in the URL: companyApi.get drops a `params` option on a blob request, so "Export ALL" used to
  // export every lead whatever the filters said.
  const query = new URLSearchParams(params).toString();
  const resp = await companyApi.get(`/sdr/leads/export/${query ? `?${query}` : ''}`, { responseType: 'blob' });
  return resp?.data ?? resp;
};

// --------------------------------------------------------------------------
// Lead categories — the industry each batch of leads was gathered for.
// A category can be given by id or by name; a new name makes a new category.
// --------------------------------------------------------------------------
export const listLeadCategories = async () => {
  try {
    return await companyApi.get('/sdr/lead-categories/');
  } catch (error) {
    console.error('List lead categories error:', error);
    throw error;
  }
};

export const renameLeadCategory = async (id, name) => {
  try {
    return await companyApi.put(`/sdr/lead-categories/${id}/`, { name });
  } catch (error) {
    console.error('Rename lead category error:', error);
    throw error;
  }
};

export const deleteLeadCategory = async (id) => {
  try {
    return await companyApi.delete(`/sdr/lead-categories/${id}/`);
  } catch (error) {
    console.error('Delete lead category error:', error);
    throw error;
  }
};

/**
 * File leads under a category (null clears it). Pass `ids` for the ticked
 * leads, or `filters` (the list's current filters) to file every matching lead.
 */
export const bulkSetLeadCategory = async ({ category, ids, filters } = {}) => {
  try {
    if (filters) {
      const query = new URLSearchParams(Object.entries(filters).filter(([, v]) => v)).toString();
      return await companyApi.post(`/sdr/leads/bulk-category/${query ? `?${query}` : ''}`, { category, all_matching: true });
    }
    return await companyApi.post('/sdr/leads/bulk-category/', { category, ids });
  } catch (error) {
    console.error('Bulk set lead category error:', error);
    throw error;
  }
};

export const createLead = async (data) => {
  try {
    return await companyApi.post('/sdr/leads/', data);
  } catch (error) {
    console.error('Create lead error:', error);
    throw error;
  }
};

export const getLeadDetail = async (id) => {
  try {
    return await companyApi.get(`/sdr/leads/${id}/`);
  } catch (error) {
    console.error('Get lead detail error:', error);
    throw error;
  }
};

export const updateLead = async (id, data) => {
  try {
    return await companyApi.put(`/sdr/leads/${id}/`, data);
  } catch (error) {
    console.error('Update lead error:', error);
    throw error;
  }
};

export const deleteLead = async (id) => {
  try {
    return await companyApi.delete(`/sdr/leads/${id}/`);
  } catch (error) {
    console.error('Delete lead error:', error);
    throw error;
  }
};

export const bulkDeleteLeads = async (ids) => {
  try {
    return await companyApi.post('/sdr/leads/bulk-delete/', { ids });
  } catch (error) {
    console.error('Bulk delete leads error:', error);
    throw error;
  }
};

export const restoreLead = async (id) => {
  try {
    return await companyApi.post(`/sdr/leads/${id}/restore/`);
  } catch (error) {
    console.error('Restore lead error:', error);
    throw error;
  }
};

export const bulkRestoreLeads = async (ids) => {
  try {
    return await companyApi.post('/sdr/leads/bulk-restore/', { ids });
  } catch (error) {
    console.error('Bulk restore leads error:', error);
    throw error;
  }
};

// --------------------------------------------------------------------------
// Qualification
// --------------------------------------------------------------------------
export const qualifyLead = async (id) => {
  try {
    return await companyApi.post(`/sdr/leads/${id}/qualify/`);
  } catch (error) {
    console.error('Qualify lead error:', error);
    throw error;
  }
};

// No argument: every unscored lead. { ids }: the ticked leads. { filters }: every lead the list's filters match.
// Scored leads are skipped either way.
export const qualifyAllLeads = async ({ ids, filters } = {}) => {
  try {
    if (filters) {
      const query = new URLSearchParams(Object.entries(filters).filter(([, v]) => v)).toString();
      return await companyApi.post(`/sdr/leads/qualify-all/${query ? `?${query}` : ''}`, { all_matching: true });
    }
    return await companyApi.post('/sdr/leads/qualify-all/', ids ? { ids } : {});
  } catch (error) {
    console.error('Qualify all leads error:', error);
    throw error;
  }
};

// --------------------------------------------------------------------------
// Lead Research Workflow (Agent 1 Intelligence)
export const researchLead = async (leadId, data = {}) => {
  try {
    return await companyApi.post(`/sdr/leads/${leadId}/research/`, data);
  } catch (error) {
    console.error('Research lead error:', error);
    throw error;
  }
};

export const getLeadResearch = async (leadId) => {
  try {
    return await companyApi.get(`/sdr/leads/${leadId}/research/`);
  } catch (error) {
    console.error('Get lead research error:', error);
    throw error;
  }
};

export const enrichLead = async (leadId, data = {}) => {
  try {
    return await companyApi.post(`/sdr/leads/${leadId}/enrich/`, data);
  } catch (error) {
    console.error('Enrich lead error:', error);
    throw error;
  }
};

export const getLeadEnrichment = async (leadId) => {
  try {
    return await companyApi.get(`/sdr/leads/${leadId}/enrich/`);
  } catch (error) {
    console.error('Get lead enrichment error:', error);
    throw error;
  }
};

export const enrichLeadsBatch = async (leadIds, data = {}) => {
  try {
    return await companyApi.post('/sdr/leads/enrich-batch/', { lead_ids: leadIds, ...data });
  } catch (error) {
    console.error('Batch enrich leads error:', error);
    throw error;
  }
};

export const researchLeadsBatch = async (leadIds, data = {}) => {
  try {
    return await companyApi.post('/sdr/leads/research-batch/', { lead_ids: leadIds, ...data });
  } catch (error) {
    console.error('Batch research leads error:', error);
    throw error;
  }
};

// Research (Apollo.io or Apify discovery) — starts a background job and
// returns { job_id, ... }. Poll getResearchJob(jobId) for progress/result.
// --------------------------------------------------------------------------
export const researchLeads = async ({ count = 20, source = 'auto', icp_id, category } = {}) => {
  try {
    const body = { count, source };
    if (icp_id) body.icp_id = icp_id;
    if (category) body.category = category;   // else the leads go under the industry searched for
    return await companyApi.post('/sdr/leads/research/', body);
  } catch (error) {
    console.error('Research leads error:', error);
    throw error;
  }
};

/** Poll a background lead-discovery job started by researchLeads. */
export const getResearchJob = async (jobId) => {
  try {
    return await companyApi.get(`/sdr/leads/research/jobs/${jobId}/`);
  } catch (error) {
    console.error('Get research job error:', error);
    throw error;
  }
};

/** Import leads already generated in the Apify Console (works on the free plan). */
export const fetchApifyLeads = async ({ count = 200, actor, category } = {}) => {
  try {
    const body = { count };
    if (actor) body.actor = actor;
    if (category) body.category = category;
    return await companyApi.post('/sdr/leads/fetch-apify/', body);
  } catch (error) {
    console.error('Fetch Apify leads error:', error);
    throw error;
  }
};

export const getResearchSources = async () => {
  try {
    return await companyApi.get('/sdr/leads/research/sources/');
  } catch (error) {
    console.error('Get research sources error:', error);
    throw error;
  }
};

// --------------------------------------------------------------------------
// CSV Import — uses raw fetch to send multipart/form-data
// --------------------------------------------------------------------------
export const importLeadsFromCSV = async (file, category = '', icpId = '') => {
  try {
    const token = localStorage.getItem('company_auth_token');
    const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
    const formData = new FormData();
    formData.append('file', file);
    // Optional: files every row under this category; else each row goes under its Industry column.
    if (category) formData.append('category', category);
    // The ICP every row is scored with; the server uses the default one when it is left out.
    if (icpId) formData.append('icp_id', icpId);

    const resp = await fetch(`${baseUrl}/sdr/leads/import/`, {
      method: 'POST',
      headers: { Authorization: `Token ${token}` },
      body: formData,
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ message: 'Import failed' }));
      throw new Error(err.message || 'CSV import failed');
    }
    return resp.json();
  } catch (error) {
    console.error('CSV import error:', error);
    throw error;
  }
};

// Campaigns
// Email Assistant: write an email, or read a lead's reply.
export const assistantWriteEmail = async (data) => {
  try {
    return await companyApi.post('/sdr/email-assistant/write/', data);
  } catch (error) {
    console.error('Email assistant write error:', error);
    throw error;
  }
};

export const assistantReadReply = async (data) => {
  try {
    return await companyApi.post('/sdr/email-assistant/read/', data);
  } catch (error) {
    console.error('Email assistant read error:', error);
    throw error;
  }
};

export const listCampaigns = async () => {
  try {
    return await companyApi.get('/sdr/campaigns/');
  } catch (error) {
    console.error('List campaigns error:', error);
    throw error;
  }
};

export const createCampaign = async (data) => {
  try {
    return await companyApi.post('/sdr/campaigns/', data);
  } catch (error) {
    console.error('Create campaign error:', error);
    throw error;
  }
};

export const getCampaignDetail = async (id) => {
  try {
    return await companyApi.get(`/sdr/campaigns/${id}/`);
  } catch (error) {
    console.error('Get campaign detail error:', error);
    throw error;
  }
};

export const deleteCampaign = async (id) => {
  try {
    return await companyApi.delete(`/sdr/campaigns/${id}/`);
  } catch (error) {
    console.error('Delete campaign error:', error);
    throw error;
  }
};

export const retryFailedLeads = async (id) => {
  try {
    return await companyApi.post(`/sdr/campaigns/${id}/retry-failed/`, {});
  } catch (error) {
    console.error('Retry failed leads error:', error);
    throw error;
  }
};

export const clearCampaignLeads = async (id, payload = {}) => {
  try {
    return await companyApi.post(`/sdr/campaigns/${id}/clear-leads/`, payload);
  } catch (error) {
    console.error('Clear campaign leads error:', error);
    throw error;
  }
};

export const getCampaignSteps = async (id) => {
  try {
    return await companyApi.get(`/sdr/campaigns/${id}/steps/`);
  } catch (error) {
    console.error('Get campaign steps error:', error);
    throw error;
  }
};

export const generateSequenceSteps = async (id) => {
  try {
    return await companyApi.post(`/sdr/campaigns/${id}/generate-steps/`);
  } catch (error) {
    console.error('Generate sequence steps error:', error);
    throw error;
  }
};

export const getCampaignContacts = async (id) => {
  try {
    return await companyApi.get(`/sdr/campaigns/${id}/contacts/`);
  } catch (error) {
    console.error('Get campaign contacts error:', error);
    throw error;
  }
};

export const enrollLeads = async (campaignId, leadIds) => {
  try {
    return await companyApi.post(`/sdr/campaigns/${campaignId}/enroll/`, { lead_ids: leadIds });
  } catch (error) {
    console.error('Enroll leads error:', error);
    throw error;
  }
};

export const updateCampaign = async (id, data) => {
  try {
    return await companyApi.put(`/sdr/campaigns/${id}/`, data);
  } catch (error) {
    console.error('Update campaign error:', error);
    throw error;
  }
};

export const addCampaignStep = async (campaignId, data) => {
  try {
    return await companyApi.post(`/sdr/campaigns/${campaignId}/steps/`, data);
  } catch (error) {
    console.error('Add campaign step error:', error);
    throw error;
  }
};

export const updateCampaignStep = async (campaignId, stepId, data) => {
  try {
    return await companyApi.put(`/sdr/campaigns/${campaignId}/steps/${stepId}/`, data);
  } catch (error) {
    console.error('Update campaign step error:', error);
    throw error;
  }
};

export const deleteCampaignStep = async (campaignId, stepId) => {
  try {
    return await companyApi.delete(`/sdr/campaigns/${campaignId}/steps/${stepId}/`);
  } catch (error) {
    console.error('Delete campaign step error:', error);
    throw error;
  }
};

export const processOutreach = async (campaignId) => {
  try {
    return await companyApi.post(`/sdr/campaigns/${campaignId}/process/`);
  } catch (error) {
    console.error('Process outreach error:', error);
    throw error;
  }
};

export const markReplied = async (campaignId, enrollmentId, data) => {
  try {
    return await companyApi.post(`/sdr/campaigns/${campaignId}/enrollments/${enrollmentId}/reply/`, data);
  } catch (error) {
    console.error('Mark replied error:', error);
    throw error;
  }
};

export const resetEnrollment = async (campaignId, enrollmentId) => {
  try {
    return await companyApi.post(`/sdr/campaigns/${campaignId}/enrollments/${enrollmentId}/reset/`);
  } catch (error) {
    console.error('Reset enrollment error:', error);
    throw error;
  }
};

export const checkReplies = async (campaignId) => {
  try {
    return await companyApi.post(`/sdr/campaigns/${campaignId}/check-replies/`);
  } catch (error) {
    console.error('Check replies error:', error);
    throw error;
  }
};

// Answers the AI wrote to leads' replies, held for a person to check before they go
export const listReplyDrafts = async (campaignId) =>
  companyApi.get(`/sdr/campaigns/${campaignId}/reply-drafts/`);

export const sendReplyDraft = async (draftId, data) =>
  companyApi.post(`/sdr/reply-drafts/${draftId}/send/`, data);

export const discardReplyDraft = async (draftId) =>
  companyApi.post(`/sdr/reply-drafts/${draftId}/discard/`);

// Meetings
export const listMeetings = async ({
  status = '', campaign_id = '', campaign_status = '', search = '', search_field = 'all', temperature = '',
  sort = 'created_desc', active_only = false, page = 1, page_size = 20,
} = {}) => {
  try {
    const params = new URLSearchParams();
    if (status)          params.set('status', status);
    if (campaign_id)     params.set('campaign_id', campaign_id);
    if (campaign_status) params.set('campaign_status', campaign_status);
    if (search)          params.set('search', search);
    if (search_field && search_field !== 'all') params.set('search_field', search_field);
    if (temperature)     params.set('temperature', temperature);
    if (sort)            params.set('sort', sort);
    params.set('active_only', active_only ? 'true' : 'false');
    params.set('page', page);
    params.set('page_size', page_size);
    return await companyApi.get(`/sdr/meetings/?${params.toString()}`);
  } catch (error) {
    console.error('List meetings error:', error);
    throw error;
  }
};

export const createMeeting = async (data) => {
  try {
    return await companyApi.post('/sdr/meetings/', data);
  } catch (error) {
    console.error('Create meeting error:', error);
    throw error;
  }
};

export const updateMeeting = async (id, data) => {
  try {
    return await companyApi.put(`/sdr/meetings/${id}/`, data);
  } catch (error) {
    console.error('Update meeting error:', error);
    throw error;
  }
};

export const deleteMeeting = async (id) => {
  try {
    return await companyApi.delete(`/sdr/meetings/${id}/`);
  } catch (error) {
    console.error('Delete meeting error:', error);
    throw error;
  }
};

export const confirmMeeting = async (id, data) => {
  try {
    return await companyApi.post(`/sdr/meetings/${id}/confirm/`, data);
  } catch (error) {
    console.error('Confirm meeting error:', error);
    throw error;
  }
};

export const sendMeetingReminder = async (id) => {
  try {
    return await companyApi.post(`/sdr/meetings/${id}/send-reminder/`, {});
  } catch (error) {
    console.error('Send reminder error:', error);
    throw error;
  }
};

export const generateMeetingPrep = async (id) => {
  try {
    return await companyApi.post(`/sdr/meetings/${id}/generate-prep/`, {});
  } catch (error) {
    console.error('Generate prep error:', error);
    throw error;
  }
};

export const resendSchedulingEmail = async (id) => {
  try {
    return await companyApi.post(`/sdr/meetings/${id}/resend-scheduling/`, {});
  } catch (error) {
    console.error('Resend scheduling email error:', error);
    throw error;
  }
};

export const checkAllReplies = async () => {
  try {
    return await companyApi.post('/sdr/check-all-replies/', {});
  } catch (error) {
    console.error('Check all replies error:', error);
    throw error;
  }
};

// Analytics
export const getSdrAnalytics = async () => {
  try {
    return await companyApi.get('/sdr/analytics/');
  } catch (error) {
    console.error('Get SDR analytics error:', error);
    throw error;
  }
};

export const sendSdrDailySummary = async () => {
  try {
    return await companyApi.post('/sdr/analytics/send-summary/');
  } catch (error) {
    console.error('SDR send summary error:', error);
    throw error;
  }
};

// --------------------------------------------------------------------------
// Public booking (no auth — token from URL)
// --------------------------------------------------------------------------
const _bookingBase = (import.meta.env.VITE_API_URL || 'http://localhost:8000/api').replace(/\/$/, '');

export const getBookingInfo = async (token) => {
  const resp = await fetch(`${_bookingBase}/sdr/book/${token}/`);
  const data = await resp.json();
  if (!resp.ok) throw data;
  return data;
};

export const confirmBooking = async (token, scheduledAt) => {
  const resp = await fetch(`${_bookingBase}/sdr/book/${token}/confirm/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scheduled_at: scheduledAt }),
  });
  const data = await resp.json();
  if (!resp.ok) throw data;
  return data;
};

// --------------------------------------------------------------------------
// CRM Sync
// --------------------------------------------------------------------------
export const listCrmIntegrations = async () => {
  try { return await companyApi.get('/crm-sync/integrations/'); }
  catch (e) { console.error('CRM list error:', e); throw e; }
};

export const createCrmIntegration = async (data) => {
  try { return await companyApi.post('/crm-sync/integrations/', data); }
  catch (e) { console.error('CRM create error:', e); throw e; }
};

export const updateCrmIntegration = async (id, data) => {
  try { return await companyApi.patch(`/crm-sync/integrations/${id}/`, data); }
  catch (e) { console.error('CRM update error:', e); throw e; }
};

export const deleteCrmIntegration = async (id) => {
  try { return await companyApi.delete(`/crm-sync/integrations/${id}/`); }
  catch (e) { console.error('CRM delete error:', e); throw e; }
};

// The company's deal pipelines and stages, read from its CRM, to choose where new deals go.
export const getCrmPipelines = async (id) => companyApi.get(`/crm-sync/integrations/${id}/pipelines/`);

export const pingCrmIntegration = async (id) => {
  try { return await companyApi.post(`/crm-sync/integrations/${id}/ping/`); }
  catch (e) { console.error('CRM ping error:', e); throw e; }
};

export const syncCrmLeads = async (id) => {
  try { return await companyApi.post(`/crm-sync/integrations/${id}/sync-leads/`); }
  catch (e) { console.error('CRM sync error:', e); throw e; }
};

export const getCrmQueueStatus = async () => {
  try { return await companyApi.get('/crm-sync/queue/'); }
  catch (e) { console.error('CRM queue error:', e); throw e; }
};

export const getCrmSyncLogs = async (params = {}) => {
  try {
    const qs = new URLSearchParams(params).toString();
    return await companyApi.get(`/crm-sync/logs/${qs ? '?' + qs : ''}`);
  }
  catch (e) { console.error('CRM logs error:', e); throw e; }
};

export const retryCrmFailed = async () => {
  try { return await companyApi.post('/crm-sync/queue/retry/'); }
  catch (e) { console.error('CRM retry error:', e); throw e; }
};
