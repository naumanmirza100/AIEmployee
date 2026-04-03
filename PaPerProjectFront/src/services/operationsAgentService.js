/**
 * Operations Agent Service
 * API calls for operations agent features (document processing, analytics, Q&A, etc.)
 */

import { companyApi } from './companyAuthService';
import { API_BASE_URL } from '@/config/apiConfig';

/**
 * Get operations dashboard stats
 */
export const getDashboardStats = async () => {
  try {
    const response = await companyApi.get('/operations/dashboard');
    return response;
  } catch (error) {
    console.error('Get operations dashboard error:', error);
    throw error;
  }
};

/**
 * Upload document for processing
 */
export const uploadDocument = async (file, title = '', tags = '') => {
  try {
    const token = localStorage.getItem('company_auth_token');

    const formData = new FormData();
    formData.append('file', file);
    if (title) formData.append('title', title);
    if (tags) formData.append('tags', tags);

    const response = await fetch(`${API_BASE_URL}/operations/documents/upload/`, {
      method: 'POST',
      headers: token ? { 'Authorization': `Token ${token}` } : {},
      body: formData,
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.message || data.error || `HTTP ${response.status}`);
    }
    if (data.status === 'error') {
      throw new Error(data.message || data.error || 'Upload failed');
    }
    return data;
  } catch (error) {
    console.error('Upload document error:', error);
    throw error;
  }
};

/**
 * List documents with optional filters
 */
export const listDocuments = async (params = {}) => {
  try {
    const response = await companyApi.get('/operations/documents', params);
    return response;
  } catch (error) {
    console.error('List documents error:', error);
    throw error;
  }
};

/**
 * Get document detail
 */
export const getDocument = async (documentId) => {
  try {
    const response = await companyApi.get(`/operations/documents/${documentId}/`);
    return response;
  } catch (error) {
    console.error('Get document error:', error);
    throw error;
  }
};

/**
 * Delete document
 */
export const deleteDocument = async (documentId) => {
  try {
    const token = localStorage.getItem('company_auth_token');
    const response = await fetch(`${API_BASE_URL}/operations/documents/${documentId}/delete/`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Token ${token}` } : {}),
      },
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.message || `HTTP ${response.status}`);
    }
    return data;
  } catch (error) {
    console.error('Delete document error:', error);
    throw error;
  }
};

/**
 * Upload a file and generate a rich summary (no document storage)
 */
export const uploadAndSummarize = async (file) => {
  try {
    const token = localStorage.getItem('company_auth_token');
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE_URL}/operations/summaries/upload/`, {
      method: 'POST',
      headers: token ? { 'Authorization': `Token ${token}` } : {},
      body: formData,
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.message || `HTTP ${response.status}`);
    }
    if (data.status === 'error') {
      throw new Error(data.message || 'Summarization failed');
    }
    return data;
  } catch (error) {
    console.error('Upload and summarize error:', error);
    throw error;
  }
};

/**
 * List all saved summaries
 */
export const listSummaries = async (params = {}) => {
  try {
    const response = await companyApi.get('/operations/summaries', params);
    return response;
  } catch (error) {
    console.error('List summaries error:', error);
    throw error;
  }
};

/**
 * Get a single summary
 */
export const getSummary = async (summaryId) => {
  try {
    const response = await companyApi.get(`/operations/summaries/${summaryId}/`);
    return response;
  } catch (error) {
    console.error('Get summary error:', error);
    throw error;
  }
};

/**
 * Delete a summary
 */
export const deleteSummary = async (summaryId) => {
  try {
    const token = localStorage.getItem('company_auth_token');
    const response = await fetch(`${API_BASE_URL}/operations/summaries/${summaryId}/delete/`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Token ${token}` } : {}),
      },
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.message || `HTTP ${response.status}`);
    }
    return data;
  } catch (error) {
    console.error('Delete summary error:', error);
    throw error;
  }
};

export default {
  getDashboardStats,
  uploadDocument,
  listDocuments,
  getDocument,
  deleteDocument,
  uploadAndSummarize,
  listSummaries,
  getSummary,
  deleteSummary,
};
