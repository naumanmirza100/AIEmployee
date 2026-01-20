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
 * Get campaign details
 */
export const getCampaign = async (campaignId) => {
  try {
    const response = await companyApi.get(`/marketing/campaigns/${campaignId}`);
    return response;
  } catch (error) {
    console.error('Get campaign error:', error);
    throw error;
  }
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
 */
export const outreachCampaign = async (action, campaignData = {}, campaignId = null, context = {}, file = null) => {
  try {
    const formData = new FormData();
    formData.append('action', action);
    formData.append('campaign_data', JSON.stringify(campaignData));
    formData.append('context', JSON.stringify(context));
    if (campaignId) {
      formData.append('campaign_id', campaignId);
    }
    if (file) {
      formData.append('file', file);
    }

    const token = localStorage.getItem('company_auth_token');
    const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

    const response = await fetch(`${API_BASE_URL}/marketing/outreach-campaign`, {
      method: 'POST',
      headers: {
        'Authorization': `Token ${token}`,
      },
      body: formData,
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.message || `HTTP error! status: ${response.status}`);
    }
    return data;
  } catch (error) {
    console.error('Outreach campaign error:', error);
    throw error;
  }
};

/**
 * Document Authoring Agent
 */
export const documentAuthoring = async (action, documentType, documentData = {}, campaignId = null, context = {}) => {
  try {
    const response = await companyApi.post('/marketing/document-authoring', {
      action,
      document_type: documentType,
      document_data: documentData,
      campaign_id: campaignId,
      context,
    });
    return response;
  } catch (error) {
    console.error('Document authoring error:', error);
    throw error;
  }
};

/**
 * Get notifications
 */
export const getNotifications = async (params = {}) => {
  try {
    const response = await companyApi.get('/marketing/notifications', params);
    return response;
  } catch (error) {
    console.error('Get notifications error:', error);
    throw error;
  }
};

export default {
  getMarketingDashboard,
  listCampaigns,
  getCampaign,
  createCampaign,
  marketingQA,
  marketResearch,
  outreachCampaign,
  documentAuthoring,
  getNotifications,
};

