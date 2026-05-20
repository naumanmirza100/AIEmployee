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
/**
 * Ask the HR knowledge agent. `chatHistory` is an optional list of
 * `{role: 'user'|'assistant', content}` for multi-turn coherence.
 */
export const askHRKnowledge = async (question, chatHistory = []) => {
  try {
    const payload = { question };
    if (Array.isArray(chatHistory) && chatHistory.length > 0) {
      payload.chat_history = chatHistory;
    }
    const response = await companyApi.post('/hr/knowledge-qa', payload);
    return response;
  } catch (error) {
    console.error('HR knowledge QA error:', error);
    throw error;
  }
};

// ---------- Persisted HR Q&A chats ----------
export const listHRKnowledgeChats = async () => {
  try {
    const response = await companyApi.get('/hr/ai/knowledge-qa/chats');
    return response;
  } catch (error) {
    console.error('List HR knowledge chats error:', error);
    throw error;
  }
};

export const createHRKnowledgeChat = async (payload = {}) => {
  try {
    const response = await companyApi.post('/hr/ai/knowledge-qa/chats/create', payload);
    return response;
  } catch (error) {
    console.error('Create HR knowledge chat error:', error);
    throw error;
  }
};

export const updateHRKnowledgeChat = async (chatId, payload) => {
  try {
    const response = await companyApi.patch(`/hr/ai/knowledge-qa/chats/${chatId}/update`, payload);
    return response;
  } catch (error) {
    console.error('Update HR knowledge chat error:', error);
    throw error;
  }
};

export const deleteHRKnowledgeChat = async (chatId) => {
  try {
    const response = await companyApi.delete(`/hr/ai/knowledge-qa/chats/${chatId}/delete`);
    return response;
  } catch (error) {
    console.error('Delete HR knowledge chat error:', error);
    throw error;
  }
};

// ---------- Documents ----------
/** Upload an HR document (multipart). `options` may carry document_type,
 *  confidentiality, employee_id, retention_days. */
export const uploadHRDocument = async (file, title, description, options = {}) => {
  try {
    const { API_BASE_URL } = await import('@/config/apiConfig');
    const token = localStorage.getItem('company_auth_token');
    const fd = new FormData();
    fd.append('file', file);
    fd.append('title', title || file.name);
    fd.append('description', description || '');
    if (options.document_type) fd.append('document_type', options.document_type);
    if (options.confidentiality) fd.append('confidentiality', options.confidentiality);
    if (options.employee_id != null) fd.append('employee_id', String(options.employee_id));
    if (options.retention_days != null) fd.append('retention_days', String(options.retention_days));
    const res = await fetch(`${API_BASE_URL}/hr/documents/upload/`, {
      method: 'POST',
      headers: token ? { Authorization: `Token ${token}` } : {},
      body: fd,
    });
    const data = await res.json();
    if (!res.ok && res.status !== 202) throw new Error(data.message || `HTTP ${res.status}`);
    if (data.status === 'error') throw new Error(data.message || 'Upload failed');
    return data;
  } catch (error) {
    console.error('Upload HR document error:', error);
    throw error;
  }
};

export const listHRDocuments = async (params = {}) => {
  try {
    const q = new URLSearchParams();
    if (params.document_type) q.set('document_type', params.document_type);
    if (params.q) q.set('q', params.q);
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    const qs = q.toString();
    const response = await companyApi.get(`/hr/documents${qs ? `?${qs}` : ''}`);
    return response;
  } catch (error) {
    console.error('List HR documents error:', error);
    throw error;
  }
};

export const getHRDocument = async (documentId) => {
  try {
    const response = await companyApi.get(`/hr/documents/${documentId}`);
    return response;
  } catch (error) {
    console.error('Get HR document error:', error);
    throw error;
  }
};

export const deleteHRDocument = async (documentId) => {
  try {
    const response = await companyApi.delete(`/hr/documents/${documentId}/delete`);
    return response;
  } catch (error) {
    console.error('Delete HR document error:', error);
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

export const getHRWorkflow = async (workflowId) => {
  try {
    const response = await companyApi.get(`/hr/workflows/${workflowId}`);
    return response;
  } catch (error) {
    console.error('Get HR workflow error:', error);
    throw error;
  }
};

export const updateHRWorkflow = async (workflowId, payload) => {
  try {
    const response = await companyApi.patch(`/hr/workflows/${workflowId}/update`, payload);
    return response;
  } catch (error) {
    console.error('Update HR workflow error:', error);
    throw error;
  }
};

export const deleteHRWorkflow = async (workflowId) => {
  try {
    const response = await companyApi.delete(`/hr/workflows/${workflowId}/delete`);
    return response;
  } catch (error) {
    console.error('Delete HR workflow error:', error);
    throw error;
  }
};

export const executeHRWorkflow = async (workflowId, context = {}, options = {}) => {
  try {
    const payload = { context };
    if (options.simulate) payload.simulate = true;
    const response = await companyApi.post(`/hr/workflows/${workflowId}/execute`, payload);
    return response;
  } catch (error) {
    console.error('Execute HR workflow error:', error);
    throw error;
  }
};

export const listHRWorkflowExecutions = async (workflowId = null) => {
  try {
    const qs = workflowId ? `?workflow_id=${workflowId}` : '';
    const response = await companyApi.get(`/hr/workflows/executions${qs}`);
    return response;
  } catch (error) {
    console.error('List HR workflow executions error:', error);
    throw error;
  }
};

// ---------- Performance reviews ----------
export const listHRReviewCycles = async () => {
  try {
    const response = await companyApi.get('/hr/review-cycles');
    return response;
  } catch (error) {
    console.error('List HR review cycles error:', error);
    throw error;
  }
};

export const createHRReviewCycle = async (payload) => {
  try {
    const response = await companyApi.post('/hr/review-cycles/create', payload);
    return response;
  } catch (error) {
    console.error('Create HR review cycle error:', error);
    throw error;
  }
};

export const activateHRReviewCycle = async (cycleId) => {
  try {
    const response = await companyApi.post(`/hr/review-cycles/${cycleId}/activate`);
    return response;
  } catch (error) {
    console.error('Activate HR review cycle error:', error);
    throw error;
  }
};

export const deleteHRReviewCycle = async (cycleId) => {
  try {
    const response = await companyApi.post(`/hr/review-cycles/${cycleId}/delete`);
    return response;
  } catch (error) {
    console.error('Delete HR review cycle error:', error);
    throw error;
  }
};

export const listHREmployeeReviews = async (employeeId) => {
  try {
    const response = await companyApi.get(`/hr/employees/${employeeId}/reviews`);
    return response;
  } catch (error) {
    console.error('List HR employee reviews error:', error);
    throw error;
  }
};

export const updateHRPerfReview = async (reviewId, payload) => {
  try {
    const response = await companyApi.post(`/hr/reviews/${reviewId}/update`, payload);
    return response;
  } catch (error) {
    console.error('Update HR performance review error:', error);
    throw error;
  }
};

// ---------- Departments ----------
export const listHRDepartments = async ({ activeOnly = false } = {}) => {
  try {
    const qs = activeOnly ? '?active_only=1' : '';
    const response = await companyApi.get(`/hr/departments${qs}`);
    return response;
  } catch (error) {
    console.error('List HR departments error:', error);
    throw error;
  }
};

export const createHRDepartment = async (payload) => {
  try {
    const response = await companyApi.post('/hr/departments/create', payload);
    return response;
  } catch (error) {
    console.error('Create HR department error:', error);
    throw error;
  }
};

export const updateHRDepartment = async (deptId, payload) => {
  try {
    const response = await companyApi.post(`/hr/departments/${deptId}/update`, payload);
    return response;
  } catch (error) {
    console.error('Update HR department error:', error);
    throw error;
  }
};

export const deleteHRDepartment = async (deptId) => {
  try {
    const response = await companyApi.post(`/hr/departments/${deptId}/delete`);
    return response;
  } catch (error) {
    console.error('Delete HR department error:', error);
    throw error;
  }
};

export const approveHRWorkflowExecution = async (executionId, comment = '') => {
  try {
    const response = await companyApi.post(
      `/hr/workflows/executions/${executionId}/approve`, { comment },
    );
    return response;
  } catch (error) {
    console.error('Approve HR workflow execution error:', error);
    throw error;
  }
};

export const rejectHRWorkflowExecution = async (executionId, reason = '') => {
  try {
    const response = await companyApi.post(
      `/hr/workflows/executions/${executionId}/reject`, { reason },
    );
    return response;
  } catch (error) {
    console.error('Reject HR workflow execution error:', error);
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

// ---------- Meetings (CRUD + scheduling chat) ----------
/** Natural-language meeting scheduling. Body: `{message, chat_history?: [...]}` */
export const hrMeetingSchedule = async (message, chatHistory = []) => {
  try {
    const payload = { message };
    if (Array.isArray(chatHistory) && chatHistory.length > 0) {
      payload.chat_history = chatHistory;
    }
    const response = await companyApi.post('/hr/ai/meetings/schedule', payload);
    return response;
  } catch (error) {
    console.error('HR meeting schedule error:', error);
    throw error;
  }
};

export const listHRMeetingSchedulerChats = async () => {
  try {
    const response = await companyApi.get('/hr/ai/meeting-scheduler/chats');
    return response;
  } catch (error) {
    console.error('List HR meeting scheduler chats error:', error);
    throw error;
  }
};

export const createHRMeetingSchedulerChat = async (payload = {}) => {
  try {
    const response = await companyApi.post('/hr/ai/meeting-scheduler/chats/create', payload);
    return response;
  } catch (error) {
    console.error('Create HR meeting scheduler chat error:', error);
    throw error;
  }
};

export const updateHRMeetingSchedulerChat = async (chatId, payload) => {
  try {
    const response = await companyApi.patch(`/hr/ai/meeting-scheduler/chats/${chatId}/update`, payload);
    return response;
  } catch (error) {
    console.error('Update HR meeting scheduler chat error:', error);
    throw error;
  }
};

export const deleteHRMeetingSchedulerChat = async (chatId) => {
  try {
    const response = await companyApi.delete(`/hr/ai/meeting-scheduler/chats/${chatId}/delete`);
    return response;
  } catch (error) {
    console.error('Delete HR meeting scheduler chat error:', error);
    throw error;
  }
};

export const getHRMeeting = async (meetingId) => {
  try {
    const response = await companyApi.get(`/hr/meetings/${meetingId}`);
    return response;
  } catch (error) {
    console.error('Get HR meeting error:', error);
    throw error;
  }
};

export const updateHRMeeting = async (meetingId, payload) => {
  try {
    const response = await companyApi.patch(`/hr/meetings/${meetingId}/update`, payload);
    return response;
  } catch (error) {
    console.error('Update HR meeting error:', error);
    throw error;
  }
};

export const cancelHRMeeting = async (meetingId, reason = '') => {
  try {
    const response = await companyApi.post(`/hr/meetings/${meetingId}/cancel`, { reason });
    return response;
  } catch (error) {
    console.error('Cancel HR meeting error:', error);
    throw error;
  }
};

export const extractHRMeetingActionItems = async (meetingId) => {
  try {
    const response = await companyApi.post(`/hr/meetings/${meetingId}/extract-action-items`);
    return response;
  } catch (error) {
    console.error('Extract HR meeting action items error:', error);
    throw error;
  }
};

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

// ---------- Compensation history (HR-admin only) ----------
export const listCompensationHistory = async (employeeId) => {
  try {
    const response = await companyApi.get(`/hr/employees/${employeeId}/compensation`);
    return response;
  } catch (error) {
    console.error('List compensation error:', error);
    throw error;
  }
};

export const createCompensation = async (employeeId, payload) => {
  try {
    const response = await companyApi.post(`/hr/employees/${employeeId}/compensation/create`, payload);
    return response;
  } catch (error) {
    console.error('Create compensation error:', error);
    throw error;
  }
};

export const deleteCompensation = async (compId) => {
  try {
    const response = await companyApi.delete(`/hr/compensation/${compId}/delete`);
    return response;
  } catch (error) {
    console.error('Delete compensation error:', error);
    throw error;
  }
};

// ---------- Employee detail + edit ----------
export const getHREmployeeDetail = async (employeeId) => {
  try {
    const response = await companyApi.get(`/hr/employees/${employeeId}`);
    return response;
  } catch (error) {
    console.error('Get HR employee detail error:', error);
    throw error;
  }
};

export const updateHREmployee = async (employeeId, payload) => {
  try {
    const response = await companyApi.patch(`/hr/employees/${employeeId}/update`, payload);
    return response;
  } catch (error) {
    console.error('Update HR employee error:', error);
    throw error;
  }
};

// ---------- Audit log (HR-admin only) ----------
export const listHRAuditLog = async (params = {}) => {
  try {
    const q = new URLSearchParams();
    if (params.target_type) q.set('target_type', params.target_type);
    if (params.target_id != null) q.set('target_id', String(params.target_id));
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    const qs = q.toString();
    const response = await companyApi.get(`/hr/audit-log${qs ? `?${qs}` : ''}`);
    return response;
  } catch (error) {
    console.error('List HR audit log error:', error);
    throw error;
  }
};

// ---------- Leave requests ----------
export const listLeaveRequests = async (params = {}) => {
  try {
    const q = new URLSearchParams();
    if (params.status) q.set('status', params.status);
    if (params.mine) q.set('mine', '1');
    if (params.pending_for_me) q.set('pending_for_me', '1');
    const qs = q.toString();
    const response = await companyApi.get(`/hr/leave-requests${qs ? `?${qs}` : ''}`);
    return response;
  } catch (error) {
    console.error('List leave requests error:', error);
    throw error;
  }
};

// ---------- Holidays ----------
export const listHolidays = async (year = null) => {
  try {
    const qs = year ? `?year=${year}` : '';
    const response = await companyApi.get(`/hr/holidays${qs}`);
    return response;
  } catch (error) {
    console.error('List holidays error:', error);
    throw error;
  }
};

export const createHoliday = async (payload) => {
  try {
    const response = await companyApi.post('/hr/holidays/create', payload);
    return response;
  } catch (error) {
    console.error('Create holiday error:', error);
    throw error;
  }
};

export const deleteHoliday = async (holidayId) => {
  try {
    const response = await companyApi.delete(`/hr/holidays/${holidayId}/delete`);
    return response;
  } catch (error) {
    console.error('Delete holiday error:', error);
    throw error;
  }
};

// ---------- Leave accrual policies ----------
export const listLeaveAccrualPolicies = async () => {
  try {
    const response = await companyApi.get('/hr/leave-accrual-policies');
    return response;
  } catch (error) {
    console.error('List accrual policies error:', error);
    throw error;
  }
};

export const upsertLeaveAccrualPolicy = async (payload) => {
  try {
    const response = await companyApi.post('/hr/leave-accrual-policies/upsert', payload);
    return response;
  } catch (error) {
    console.error('Upsert accrual policy error:', error);
    throw error;
  }
};

export const deleteLeaveAccrualPolicy = async (policyId) => {
  try {
    const response = await companyApi.delete(`/hr/leave-accrual-policies/${policyId}/delete`);
    return response;
  } catch (error) {
    console.error('Delete accrual policy error:', error);
    throw error;
  }
};


export const submitLeaveRequest = async (payload) => {
  try {
    const response = await companyApi.post('/hr/leave-requests/submit', payload);
    return response;
  } catch (error) {
    console.error('Submit leave request error:', error);
    throw error;
  }
};

export const updateLeaveRequest = async (requestId, payload) => {
  try {
    const response = await companyApi.patch(`/hr/leave-requests/${requestId}/update`, payload);
    return response;
  } catch (error) {
    console.error('Update leave request error:', error);
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
  listHRKnowledgeChats,
  createHRKnowledgeChat,
  updateHRKnowledgeChat,
  deleteHRKnowledgeChat,
  uploadHRDocument,
  listHRDocuments,
  getHRDocument,
  deleteHRDocument,
  summarizeHRDocument,
  extractHRDocument,
  listHRWorkflows,
  createHRWorkflow,
  getHRWorkflow,
  updateHRWorkflow,
  deleteHRWorkflow,
  executeHRWorkflow,
  listHRWorkflowExecutions,
  approveHRWorkflowExecution,
  rejectHRWorkflowExecution,
  listHRDepartments,
  createHRDepartment,
  updateHRDepartment,
  deleteHRDepartment,
  listHRReviewCycles,
  createHRReviewCycle,
  activateHRReviewCycle,
  deleteHRReviewCycle,
  listHREmployeeReviews,
  updateHRPerfReview,
  listHRNotificationTemplates,
  createHRNotificationTemplate,
  listHRScheduledNotifications,
  hrMeetingSchedule,
  listHRMeetingSchedulerChats,
  createHRMeetingSchedulerChat,
  updateHRMeetingSchedulerChat,
  deleteHRMeetingSchedulerChat,
  getHRMeeting,
  updateHRMeeting,
  cancelHRMeeting,
  extractHRMeetingActionItems,
  listHRMeetings,
  createHRMeeting,
  checkHRMeetingAvailability,
  submitLeaveRequest,
  updateLeaveRequest,
  decideLeaveRequest,
  listLeaveRequests,
  getHREmployeeDetail,
  listHolidays,
  createHoliday,
  deleteHoliday,
  listLeaveAccrualPolicies,
  upsertLeaveAccrualPolicy,
  deleteLeaveAccrualPolicy,
  listCompensationHistory,
  createCompensation,
  deleteCompensation,
  updateHREmployee,
  listHRAuditLog,
};
