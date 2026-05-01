import { companyApi } from './companyAuthService';

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

export const saveIcpProfile = async (data) => {
  try {
    return await companyApi.post('/sdr/icp/', data);
  } catch (error) {
    console.error('Save ICP error:', error);
    throw error;
  }
};

// --------------------------------------------------------------------------
// Leads — CRUD
// --------------------------------------------------------------------------
export const listLeads = async ({ search = '', temperature = '', status = '' } = {}) => {
  try {
    const params = new URLSearchParams();
    if (search)      params.set('search', search);
    if (temperature) params.set('temperature', temperature);
    if (status)      params.set('status', status);
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

export const qualifyAllLeads = async () => {
  try {
    return await companyApi.post('/sdr/leads/qualify-all/');
  } catch (error) {
    console.error('Qualify all leads error:', error);
    throw error;
  }
};

// --------------------------------------------------------------------------
// Research (Apollo.io or AI generation)
// --------------------------------------------------------------------------
export const researchLeads = async ({ count = 20 } = {}) => {
  try {
    return await companyApi.post('/sdr/leads/research/', { count });
  } catch (error) {
    console.error('Research leads error:', error);
    throw error;
  }
};

// --------------------------------------------------------------------------
// CSV Import — uses raw fetch to send multipart/form-data
// --------------------------------------------------------------------------
export const importLeadsFromCSV = async (file) => {
  try {
    const token = localStorage.getItem('company_auth_token');
    const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
    const formData = new FormData();
    formData.append('file', file);

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
