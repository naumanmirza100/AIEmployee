import { companyApi } from './companyAuthService';

export const getSdrDashboard = async () => {
  try {
    return await companyApi.get('/sdr/dashboard/');
  } catch (error) {
    console.error('SDR dashboard error:', error);
    throw error;
  }
};

// Leads
export const listLeads = async ({ search = '', status = '', scoring = '' } = {}) => {
  try {
    const params = new URLSearchParams();
    if (search) params.set('search', search);
    if (status) params.set('status', status);
    if (scoring) params.set('scoring', scoring);
    const qs = params.toString();
    return await companyApi.get(qs ? `/sdr/leads/?${qs}` : '/sdr/leads/');
  } catch (error) {
    console.error('List leads error:', error);
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

export const scoreLead = async (id) => {
  try {
    return await companyApi.post(`/sdr/leads/${id}/score/`);
  } catch (error) {
    console.error('Score lead error:', error);
    throw error;
  }
};

export const bulkScoreLeads = async () => {
  try {
    return await companyApi.post('/sdr/leads/bulk-score/');
  } catch (error) {
    console.error('Bulk score leads error:', error);
    throw error;
  }
};

// Campaigns
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

// Meetings
export const listMeetings = async ({ status = '' } = {}) => {
  try {
    const qs = status ? `?status=${status}` : '';
    return await companyApi.get(`/sdr/meetings/${qs}`);
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

// Analytics
export const getSdrAnalytics = async () => {
  try {
    return await companyApi.get('/sdr/analytics/');
  } catch (error) {
    console.error('Get SDR analytics error:', error);
    throw error;
  }
};

export const generatePersonalizedEmail = async (data) => {
  try {
    return await companyApi.post('/sdr/emails/generate/', data);
  } catch (error) {
    console.error('Generate email error:', error);
    throw error;
  }
};
