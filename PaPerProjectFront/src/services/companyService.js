// Company Service

import api from './api';

/**
 * Create company (Admin only)
 */
export const createCompany = async (companyData) => {
  try {
    const response = await api.post('/companies/create', companyData);
    return response;
  } catch (error) {
    console.error('Create company error:', error);
    throw error;
  }
};

/**
 * Get all companies (Admin only)
 */
export const getAllCompanies = async (params = {}) => {
  try {
    const queryParams = {};
    if (params.page) queryParams.page = params.page;
    if (params.limit) queryParams.limit = params.limit;
    if (params.search) queryParams.search = params.search;
    if (params.isActive !== undefined) queryParams.isActive = params.isActive;

    const response = await api.get('/companies', queryParams);
    return response;
  } catch (error) {
    console.error('Get all companies error:', error);
    throw error;
  }
};

/**
 * Get company registration tokens (Admin only)
 */
export const getCompanyTokens = async (companyId) => {
  try {
    const response = await api.get(`/companies/${companyId}/tokens`);
    return response;
  } catch (error) {
    console.error('Get company tokens error:', error);
    throw error;
  }
};

/**
 * Generate new registration token (Admin only)
 */
export const generateToken = async (companyId) => {
  try {
    const response = await api.post(`/companies/${companyId}/tokens/generate`, {});
    return response;
  } catch (error) {
    console.error('Generate token error:', error);
    throw error;
  }
};

/**
 * Get all company AI agent purchases (Admin only)
 */
export const getCompanyAgents = async (params = {}) => {
  try {
    const queryParams = {};
    if (params.page) queryParams.page = params.page;
    if (params.limit) queryParams.limit = params.limit;
    if (params.search) queryParams.search = params.search;
    if (params.status) queryParams.status = params.status;
    if (params.module) queryParams.module = params.module;

    const response = await api.get('/admin/company-agents', queryParams);
    return response;
  } catch (error) {
    console.error('Get company agents error:', error);
    throw error;
  }
};

/**
 * Toggle company AI agent status (Admin only)
 */
export const toggleCompanyAgentStatus = async (purchaseId, newStatus) => {
  try {
    const response = await api.patch(`/admin/company-agents/${purchaseId}/toggle-status`, { status: newStatus });
    return response;
  } catch (error) {
    console.error('Toggle company agent status error:', error);
    throw error;
  }
};

export default {
  createCompany,
  getAllCompanies,
  getCompanyTokens,
  generateToken,
  getCompanyAgents,
  toggleCompanyAgentStatus,
};

