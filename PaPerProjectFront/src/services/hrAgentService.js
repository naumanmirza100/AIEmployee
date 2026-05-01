/**
 * HR Support Agent Service
 *
 * Thin client for the `/api/hr/...` endpoints. Mirrors the shape of
 * `frontlineAgentService.js` so callers feel familiar.
 */

import { companyApi } from './companyAuthService';

// ---------- Dashboard / overview ----------
export const getHRDashboard = async () => {
  try {
    const response = await companyApi.get('/hr/dashboard');
    return response;
  } catch (error) {
    console.error('Get HR dashboard error:', error);
    throw error;
  }
};

// ---------- Employees ----------
export const listHREmployees = async (params = {}) => {
  try {
    const q = new URLSearchParams();
    if (params.q) q.set('q', params.q);
    if (params.department) q.set('department', params.department);
    if (params.status) q.set('status', params.status);
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    const qs = q.toString();
    const response = await companyApi.get(`/hr/employees${qs ? `?${qs}` : ''}`);
    return response;
  } catch (error) {
    console.error('List HR employees error:', error);
    throw error;
  }
};

export const createHREmployee = async (payload) => {
  try {
    const response = await companyApi.post('/hr/employees/create', payload);
    return response;
  } catch (error) {
    console.error('Create HR employee error:', error);
    throw error;
  }
};

// ---------- Knowledge Q&A ----------
export const askHRKnowledge = async (question) => {
  try {
    const response = await companyApi.post('/hr/knowledge-qa', { question });
    return response;
  } catch (error) {
    console.error('HR knowledge QA error:', error);
    throw error;
  }
};

// ---------- Documents ----------
export const listHRDocuments = async (params = {}) => {
  try {
    const q = new URLSearchParams();
    if (params.document_type) q.set('document_type', params.document_type);
    const qs = q.toString();
    const response = await companyApi.get(`/hr/documents${qs ? `?${qs}` : ''}`);
    return response;
  } catch (error) {
    console.error('List HR documents error:', error);
    throw error;
  }
};

export const summarizeHRDocument = async (documentId, options = {}) => {
  try {
    const response = await companyApi.post(`/hr/documents/${documentId}/summarize`, options);
    return response;
  } catch (error) {
    console.error('Summarize HR document error:', error);
    throw error;
  }
};

export const extractHRDocument = async (documentId, options = {}) => {
  try {
    const response = await companyApi.post(`/hr/documents/${documentId}/extract`, options);
    return response;
  } catch (error) {
    console.error('Extract HR document error:', error);
    throw error;
  }
};

// ---------- Workflows ----------
export const listHRWorkflows = async () => {
  try {
    const response = await companyApi.get('/hr/workflows');
    return response;
  } catch (error) {
    console.error('List HR workflows error:', error);
    throw error;
  }
};

export const createHRWorkflow = async (payload) => {
  try {
    const response = await companyApi.post('/hr/workflows/create', payload);
    return response;
  } catch (error) {
    console.error('Create HR workflow error:', error);
    throw error;
  }
};

// ---------- Notifications ----------
export const listHRNotificationTemplates = async () => {
  try {
    const response = await companyApi.get('/hr/notifications/templates');
    return response;
  } catch (error) {
    console.error('List HR notification templates error:', error);
    throw error;
  }
};

export const createHRNotificationTemplate = async (payload) => {
  try {
    const response = await companyApi.post('/hr/notifications/templates/create', payload);
    return response;
  } catch (error) {
    console.error('Create HR notification template error:', error);
    throw error;
  }
};

export const listHRScheduledNotifications = async () => {
  try {
    const response = await companyApi.get('/hr/notifications/scheduled');
    return response;
  } catch (error) {
    console.error('List HR scheduled notifications error:', error);
    throw error;
  }
};

// ---------- Meetings ----------
export const listHRMeetings = async () => {
  try {
    const response = await companyApi.get('/hr/meetings');
    return response;
  } catch (error) {
    console.error('List HR meetings error:', error);
    throw error;
  }
};

export const createHRMeeting = async (payload) => {
  try {
    const response = await companyApi.post('/hr/meetings/create', payload);
    return response;
  } catch (error) {
    console.error('Create HR meeting error:', error);
    throw error;
  }
};

export const checkHRMeetingAvailability = async (start, end) => {
  try {
    const q = new URLSearchParams({ start, end });
    const response = await companyApi.get(`/hr/meetings/availability?${q.toString()}`);
    return response;
  } catch (error) {
    console.error('HR meeting availability error:', error);
    throw error;
  }
};

// ---------- Leave requests ----------
export const submitLeaveRequest = async (payload) => {
  try {
    const response = await companyApi.post('/hr/leave-requests/submit', payload);
    return response;
  } catch (error) {
    console.error('Submit leave request error:', error);
    throw error;
  }
};

export const decideLeaveRequest = async (requestId, action, note = '') => {
  try {
    const response = await companyApi.post(`/hr/leave-requests/${requestId}/decide`, { action, note });
    return response;
  } catch (error) {
    console.error('Decide leave request error:', error);
    throw error;
  }
};

export default {
  getHRDashboard,
  listHREmployees,
  createHREmployee,
  askHRKnowledge,
  listHRDocuments,
  summarizeHRDocument,
  extractHRDocument,
  listHRWorkflows,
  createHRWorkflow,
  listHRNotificationTemplates,
  createHRNotificationTemplate,
  listHRScheduledNotifications,
  listHRMeetings,
  createHRMeeting,
  checkHRMeetingAvailability,
  submitLeaveRequest,
  decideLeaveRequest,
};
