// Career Service

import api from './api';

// Same pattern as modulePurchaseService.getModulePrices - base can be with or without /api
const getCareersUrl = () => {
  const base = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/+$/, '');
  return base.includes('/api') ? `${base}/careers/positions` : `${base}/api/careers/positions`;
};

/**
 * Get all job positions (public endpoint - uses direct fetch to avoid auth/header issues)
 */
export const getPositions = async (params = {}) => {
  try {
    const queryParams = {};
    if (params.search) queryParams.search = params.search;
    if (params.department) queryParams.department = params.department;
    if (params.type) queryParams.type = params.type;

    const queryString = new URLSearchParams(queryParams).toString();
    const url = `${getCareersUrl()}${queryString ? `?${queryString}` : ''}`;

    const response = await fetch(url, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      const err = new Error(errData?.message || `HTTP ${response.status}`);
      err.status = response.status;
      err.data = errData;
      throw err;
    }

    return await response.json();
  } catch (error) {
    console.error('Get positions error:', error);
    throw error;
  }
};

/**
 * Submit career application (supports file upload)
 */
export const submitApplication = async (applicationData, resumeFile = null) => {
  try {
    // Always use FormData to support file uploads
    const formDataToSend = new FormData();
    
    // Add text fields - positionTitle is required
    formDataToSend.append('positionTitle', applicationData.positionTitle || '');
    if (applicationData.positionId) formDataToSend.append('positionId', applicationData.positionId.toString());
    if (applicationData.applicantName) formDataToSend.append('applicantName', applicationData.applicantName);
    if (applicationData.name) formDataToSend.append('name', applicationData.name);
    formDataToSend.append('email', applicationData.email || '');
    if (applicationData.phone) formDataToSend.append('phone', applicationData.phone);
    if (applicationData.coverLetter) formDataToSend.append('coverLetter', applicationData.coverLetter);
    if (applicationData.message) formDataToSend.append('message', applicationData.message);
    
    // Add resume file if provided
    if (resumeFile) {
      formDataToSend.append('resume', resumeFile);
    }
    
    const response = await api.upload('/careers/applications', formDataToSend);
    return response;
  } catch (error) {
    console.error('Submit application error:', error);
    throw error;
  }
};

/**
 * Get all career applications (Admin only)
 */
export const getAllApplications = async (params = {}) => {
  try {
    const queryParams = {};
    if (params.page) queryParams.page = params.page;
    if (params.limit) queryParams.limit = params.limit;
    if (params.status) queryParams.status = params.status;
    if (params.search) queryParams.search = params.search;

    const queryString = new URLSearchParams(queryParams).toString();
    const endpoint = `/careers/admin/applications${queryString ? `?${queryString}` : ''}`;
    
    const response = await api.get(endpoint);
    return response;
  } catch (error) {
    console.error('Get all applications error:', error);
    throw error;
  }
};

/**
 * Get career application by ID (Admin only)
 */
export const getApplicationById = async (id) => {
  try {
    const response = await api.get(`/careers/admin/applications/${id}`);
    return response;
  } catch (error) {
    console.error('Get application by ID error:', error);
    throw error;
  }
};

/**
 * Update career application status (Admin only)
 */
export const updateApplicationStatus = async (id, status) => {
  try {
    const response = await api.patch(`/careers/admin/applications/${id}/status`, { status });
    return response;
  } catch (error) {
    console.error('Update application status error:', error);
    throw error;
  }
};

export default {
  getPositions,
  submitApplication,
  getAllApplications,
  getApplicationById,
  updateApplicationStatus,
};

