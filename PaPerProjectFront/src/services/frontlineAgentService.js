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
 * Get widget key and build embed snippet (frontend builds URLs from window.location.origin)
 */
export const getFrontlineWidgetConfig = async () => {
  try {
    const response = await companyApi.get('/frontline/widget-config');
    return response;
  } catch (error) {
    console.error('Get frontline widget config error:', error);
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
 * Summarize document (LLM). Options: { max_sentences?, by_section? }
 */
export const summarizeDocument = async (documentId, options = {}) => {
  try {
    const response = await companyApi.post(`/frontline/documents/${documentId}/summarize/`, options);
    return response;
  } catch (error) {
    console.error('Summarize document error:', error);
    throw error;
  }
};

/**
 * Extract structured data from document (LLM). Options: { schema?: string[] }
 */
export const extractDocument = async (documentId, options = {}) => {
  try {
    const response = await companyApi.post(`/frontline/documents/${documentId}/extract/`, options);
    return response;
  } catch (error) {
    console.error('Extract document error:', error);
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
 * @param {string} question
 * @param {{ scope_document_type?: string[], scope_document_ids?: number[] }} options - Optional scope to restrict answers to document type(s) and/or specific document IDs
 */
export const knowledgeQA = async (question, options = {}) => {
  try {
    const body = { question };
    if (options.scope_document_type?.length) body.scope_document_type = options.scope_document_type;
    if (options.scope_document_ids?.length) body.scope_document_ids = options.scope_document_ids;
    const response = await companyApi.post('/frontline/knowledge/qa', body);
    return response;
  } catch (error) {
    console.error('Knowledge Q&A error:', error);
    throw error;
  }
};

/**
 * List all QA chats (stored in DB)
 */
export const listQAChats = async () => {
  const response = await companyApi.get('/frontline/qa/chats');
  return response;
};

/**
 * Create a new QA chat with optional messages
 * @param {{ title?: string, messages?: Array<{role, content, responseData?}> }} data
 */
export const createQAChat = async (data) => {
  const response = await companyApi.post('/frontline/qa/chats/create', data);
  return response;
};

/**
 * Update a QA chat (add messages, optional title)
 * @param {number|string} chatId
 * @param {{ title?: string, messages?: Array<{role, content, responseData?}> }} data
 */
export const updateQAChat = async (chatId, data) => {
  const response = await companyApi.patch(`/frontline/qa/chats/${chatId}/update`, data);
  return response;
};

/**
 * Delete a QA chat and all its messages
 * @param {number|string} chatId
 */
export const deleteQAChat = async (chatId) => {
  const response = await companyApi.delete(`/frontline/qa/chats/${chatId}/delete`);
  return response;
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
 * List support tickets with filters and pagination
 * @param {{ status?, priority?, category?, date_from?, date_to?, page?, limit? }} params
 */
export const listTickets = async (params = {}) => {
  try {
    const query = new URLSearchParams();
    if (params.status) query.set('status', params.status);
    if (params.priority) query.set('priority', params.priority);
    if (params.category) query.set('category', params.category);
    if (params.date_from) query.set('date_from', params.date_from);
    if (params.date_to) query.set('date_to', params.date_to);
    if (params.page) query.set('page', params.page);
    if (params.limit) query.set('limit', params.limit);
    const response = await companyApi.get(`/frontline/tickets?${query.toString()}`);
    return response;
  } catch (error) {
    console.error('List tickets error:', error);
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

/**
 * List ticket tasks (KB-gap tasks assigned to current user)
 */
export const listTicketTasks = async () => {
  try {
    const response = await companyApi.get('/frontline/ticket-tasks');
    return response;
  } catch (error) {
    console.error('List ticket tasks error:', error);
    throw error;
  }
};

/**
 * Update a ticket task (e.g. mark as resolved)
 */
export const updateTicketTask = async (ticketId, data) => {
  try {
    const response = await companyApi.patch(`/frontline/ticket-tasks/${ticketId}`, data);
    return response;
  } catch (error) {
    console.error('Update ticket task error:', error);
    throw error;
  }
};

// ---------- Notification templates & scheduled ----------
export const listNotificationTemplates = async () => {
  const response = await companyApi.get('/frontline/notifications/templates');
  return response;
};
export const createNotificationTemplate = async (data) => {
  const response = await companyApi.post('/frontline/notifications/templates/create', data);
  return response;
};
export const getNotificationTemplate = async (templateId) => {
  const response = await companyApi.get(`/frontline/notifications/templates/${templateId}`);
  return response;
};
export const updateNotificationTemplate = async (templateId, data) => {
  const response = await companyApi.patch(`/frontline/notifications/templates/${templateId}/update`, data);
  return response;
};
export const deleteNotificationTemplate = async (templateId) => {
  const response = await companyApi.delete(`/frontline/notifications/templates/${templateId}/delete`);
  return response;
};
export const listScheduledNotifications = async (params = {}) => {
  const q = new URLSearchParams(params).toString();
  const response = await companyApi.get(`/frontline/notifications/scheduled${q ? `?${q}` : ''}`);
  return response;
};
export const scheduleNotification = async (data) => {
  const response = await companyApi.post('/frontline/notifications/schedule', data);
  return response;
};
export const sendNotificationNow = async (data) => {
  const response = await companyApi.post('/frontline/notifications/send', data);
  return response;
};

// ---------- Workflows ----------
export const listWorkflows = async () => {
  const response = await companyApi.get('/frontline/workflows');
  return response;
};
export const createWorkflow = async (data) => {
  const response = await companyApi.post('/frontline/workflows/create', data);
  return response;
};
export const getWorkflow = async (workflowId) => {
  const response = await companyApi.get(`/frontline/workflows/${workflowId}`);
  return response;
};
export const updateWorkflow = async (workflowId, data) => {
  const response = await companyApi.patch(`/frontline/workflows/${workflowId}/update`, data);
  return response;
};
export const deleteWorkflow = async (workflowId) => {
  const response = await companyApi.delete(`/frontline/workflows/${workflowId}/delete`);
  return response;
};
export const executeWorkflow = async (workflowId, context) => {
  const response = await companyApi.post(`/frontline/workflows/${workflowId}/execute`, { context });
  return response;
};
export const listWorkflowExecutions = async (workflowId = null) => {
  const url = workflowId ? `/frontline/workflows/executions?workflow_id=${workflowId}` : '/frontline/workflows/executions';
  const response = await companyApi.get(url);
  return response;
};

// ---------- Analytics ----------
export const getFrontlineAnalytics = async (dateFrom, dateTo, options = {}) => {
  const params = new URLSearchParams();
  if (dateFrom) params.set('date_from', dateFrom);
  if (dateTo) params.set('date_to', dateTo);
  if (options.narrative !== false) params.set('narrative', '1');
  const response = await companyApi.get(`/frontline/analytics?${params.toString()}`);
  return response;
};
/** Ask analytics in natural language (e.g. "How many tickets were resolved last week?"). Returns answer + optional chart_type + analytics_data. */
export const askFrontlineAnalytics = async (question, dateFrom, dateTo) => {
  const response = await companyApi.post('/frontline/analytics/ask', {
    question: question.trim(),
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  });
  return response;
};
/** Download analytics export as CSV (uses auth token from localStorage). */
export const downloadFrontlineAnalyticsExport = async (dateFrom, dateTo) => {
  const params = new URLSearchParams();
  if (dateFrom) params.set('date_from', dateFrom);
  if (dateTo) params.set('date_to', dateTo);
  const token = localStorage.getItem('company_auth_token');
  const { API_BASE_URL } = await import('@/config/apiConfig');
  const url = `${API_BASE_URL}/frontline/analytics/export?${params.toString()}`;
  const res = await fetch(url, { headers: token ? { Authorization: `Token ${token}` } : {} });
  if (!res.ok) throw new Error(res.statusText || 'Export failed');
  const blob = await res.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `frontline_tickets_export_${dateFrom || 'all'}_${dateTo || 'all'}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
};

export default {
  getFrontlineDashboard,
  getFrontlineWidgetConfig,
  listDocuments,
  getDocument,
  uploadDocument,
  deleteDocument,
  knowledgeQA,
  listQAChats,
  createQAChat,
  updateQAChat,
  deleteQAChat,
  searchKnowledge,
  listTickets,
  createTicket,
  listTicketTasks,
  updateTicketTask,
  listNotificationTemplates,
  createNotificationTemplate,
  getNotificationTemplate,
  updateNotificationTemplate,
  deleteNotificationTemplate,
  listScheduledNotifications,
  scheduleNotification,
  sendNotificationNow,
  listWorkflows,
  createWorkflow,
  getWorkflow,
  updateWorkflow,
  deleteWorkflow,
  executeWorkflow,
  listWorkflowExecutions,
  getFrontlineAnalytics,
  askFrontlineAnalytics,
  downloadFrontlineAnalyticsExport,
};

