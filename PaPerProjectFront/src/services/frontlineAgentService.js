/**
 * Frontline Agent Service
 * API calls for frontline agent features
 */

import { companyApi } from './companyAuthService';
import { API_BASE_URL } from '@/config/apiConfig';

/**
 * Get frontline dashboard stats and overview
 */
export const getFrontlineDashboard = async () => {
  try {
    const response = await companyApi.get('/frontline/dashboard');
    return response;
  } catch (error) {
    console.error('Get frontline dashboard error:', error);
    throw error;
  }
};

/**
 * List documents
 */
export const listDocuments = async (params = {}) => {
  try {
    const response = await companyApi.get('/frontline/documents', params);
    return response;
  } catch (error) {
    console.error('List documents error:', error);
    throw error;
  }
};

/**
 * Get document details
 */
export const getDocument = async (documentId) => {
  try {
    const response = await companyApi.get(`/frontline/documents/${documentId}`);
    return response;
  } catch (error) {
    console.error('Get document error:', error);
    throw error;
  }
};

/**
 * Upload document
 */
export const uploadDocument = async (file, title, description, documentType = 'knowledge_base') => {
  try {
    const token = localStorage.getItem('company_auth_token');
    
    const formData = new FormData();
    formData.append('file', file);
    formData.append('title', title || file.name);
    formData.append('description', description || '');
    formData.append('document_type', documentType);
    
    const response = await fetch(`${API_BASE_URL}/frontline/documents/upload/`, {
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
 * Delete document
 */
export const deleteDocument = async (documentId) => {
  try {
    const response = await companyApi.post(`/frontline/documents/${documentId}/delete`, {});
    return response;
  } catch (error) {
    console.error('Delete document error:', error);
    throw error;
  }
};

/**
 * Knowledge Q&A - Ask a question
 */
export const knowledgeQA = async (question) => {
  try {
    const response = await companyApi.post('/frontline/knowledge/qa', { question });
    return response;
  } catch (error) {
    console.error('Knowledge Q&A error:', error);
    throw error;
  }
};

/**
 * Search knowledge base
 */
export const searchKnowledge = async (query, maxResults = 5) => {
  try {
    const response = await companyApi.get('/frontline/knowledge/search', {
      q: query,
      max_results: maxResults,
    });
    return response;
  } catch (error) {
    console.error('Search knowledge error:', error);
    throw error;
  }
};

/**
 * Create support ticket
 */
export const createTicket = async (title, description) => {
  try {
    const response = await companyApi.post('/frontline/tickets/create', {
      title,
      description,
    });
    return response;
  } catch (error) {
    console.error('Create ticket error:', error);
    throw error;
  }
};

export default {
  getFrontlineDashboard,
  listDocuments,
  getDocument,
  uploadDocument,
  deleteDocument,
  knowledgeQA,
  searchKnowledge,
  createTicket,
};

