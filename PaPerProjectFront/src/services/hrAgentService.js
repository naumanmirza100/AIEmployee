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
 *  confidentiality, employee_id, retention_days.
 *
 *  Pass `options.onProgress({ loaded, total, percent })` to receive real
 *  upload-byte progress. We use XHR under the hood because `fetch` still
 *  can't report upload-side progress in a portable way.
 */
export const uploadHRDocument = async (file, title, description, options = {}) => {
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

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE_URL}/hr/documents/upload/`, true);
    if (token) xhr.setRequestHeader('Authorization', `Token ${token}`);

    if (typeof options.onProgress === 'function' && xhr.upload) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          options.onProgress({
            loaded: e.loaded,
            total: e.total,
            percent: Math.round((e.loaded / e.total) * 100),
          });
        }
      };
    }

    xhr.onload = () => {
      let data = null;
      try { data = JSON.parse(xhr.responseText || '{}'); } catch { data = {}; }
      const ok = (xhr.status >= 200 && xhr.status < 300) || xhr.status === 202;
      if (!ok) {
        const err = new Error(data.message || `HTTP ${xhr.status}`);
        err.status = xhr.status;
        return reject(err);
      }
      if (data.status === 'error') {
        return reject(new Error(data.message || 'Upload failed'));
      }
      resolve(data);
    };
    xhr.onerror = () => reject(new Error('Network error during upload'));
    xhr.onabort = () => reject(Object.assign(new Error('Upload aborted'), { aborted: true }));

    if (options.signal) {
      if (options.signal.aborted) { xhr.abort(); return; }
      options.signal.addEventListener('abort', () => xhr.abort(), { once: true });
    }

    xhr.send(fd);
  });
};

/** Poll indexing progress for a single HR document. Returns
 *  { processing_status, chunks_processed, chunks_total, percent, is_indexed }. */
export const getHRDocumentStatus = async (documentId) => {
  try {
    const response = await companyApi.get(`/hr/documents/${documentId}/status`);
    return response;
  } catch (error) {
    console.error('Get HR document status error:', error);
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

export const closeHRReviewCycle = async (cycleId, { releaseReviews = false, reason = '' } = {}) => {
  try {
    const response = await companyApi.post(`/hr/review-cycles/${cycleId}/close`, {
      release_reviews: !!releaseReviews,
      reason: reason || '',
    });
    return response;
  } catch (error) {
    console.error('Close HR review cycle error:', error);
    throw error;
  }
};

export const reopenHRReviewCycle = async (cycleId, { reason = '' } = {}) => {
  try {
    const response = await companyApi.post(`/hr/review-cycles/${cycleId}/reopen`, {
      reason: reason || '',
    });
    return response;
  } catch (error) {
    console.error('Reopen HR review cycle error:', error);
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

// ---------- Performance goals / OKRs ----------
export const listEmployeeGoals = async (employeeId, { cycleId } = {}) => {
  try {
    const qs = cycleId ? `?cycle_id=${encodeURIComponent(cycleId)}` : '';
    const response = await companyApi.get(`/hr/employees/${employeeId}/goals${qs}`);
    return response;
  } catch (error) {
    console.error('List employee goals error:', error);
    throw error;
  }
};

export const createEmployeeGoal = async (employeeId, payload) => {
  try {
    const response = await companyApi.post(`/hr/employees/${employeeId}/goals/create`, payload);
    return response;
  } catch (error) {
    console.error('Create employee goal error:', error);
    throw error;
  }
};

export const updateEmployeeGoal = async (goalId, payload) => {
  try {
    const response = await companyApi.post(`/hr/goals/${goalId}/update`, payload);
    return response;
  } catch (error) {
    console.error('Update employee goal error:', error);
    throw error;
  }
};

export const deleteEmployeeGoal = async (goalId) => {
  try {
    const response = await companyApi.post(`/hr/goals/${goalId}/delete`);
    return response;
  } catch (error) {
    console.error('Delete employee goal error:', error);
    throw error;
  }
};

// ---------- Built-in workflow templates ----------
export const listWorkflowTemplates = async () => {
  try {
    const response = await companyApi.get('/hr/workflow-templates');
    return response;
  } catch (error) {
    console.error('List workflow templates error:', error);
    throw error;
  }
};

export const createWorkflowFromTemplate = async (payload) => {
  try {
    const response = await companyApi.post('/hr/workflows/from-template', payload);
    return response;
  } catch (error) {
    console.error('Create workflow from template error:', error);
    throw error;
  }
};

// ---------- Manager portal + org chart ----------
export const getManagerTeamSummary = async ({ managerId } = {}) => {
  try {
    const qs = managerId ? `?manager_id=${encodeURIComponent(managerId)}` : '';
    const response = await companyApi.get(`/hr/manager/team${qs}`);
    return response;
  } catch (error) {
    console.error('Get manager team summary error:', error);
    throw error;
  }
};

export const getHROrgChart = async () => {
  try {
    const response = await companyApi.get('/hr/org-chart');
    return response;
  } catch (error) {
    console.error('Get org chart error:', error);
    throw error;
  }
};

// ---------- Self-service + document versions ----------
export const getMyHRProfile = async () => {
  try {
    const response = await companyApi.get('/hr/me');
    return response;
  } catch (error) {
    console.error('Get my HR profile error:', error);
    throw error;
  }
};

export const listHRDocumentVersions = async (documentId) => {
  try {
    const response = await companyApi.get(`/hr/documents/${documentId}/versions`);
    return response;
  } catch (error) {
    console.error('List HR document versions error:', error);
    throw error;
  }
};

// ---------- Compliance — GDPR anonymize + document access log ----------
export const anonymizeHREmployee = async (employeeId) => {
  try {
    const response = await companyApi.post(`/hr/employees/${employeeId}/anonymize`);
    return response;
  } catch (error) {
    console.error('Anonymize HR employee error:', error);
    throw error;
  }
};

export const listHRDocumentAccessLog = async (documentId, { limit = 50, offset = 0 } = {}) => {
  try {
    const qs = `?limit=${limit}&offset=${offset}`;
    const response = await companyApi.get(`/hr/documents/${documentId}/access-log${qs}`);
    return response;
  } catch (error) {
    console.error('List HR document access log error:', error);
    throw error;
  }
};

// GDPR right-to-export — returns a ZIP. The endpoint requires the company
// auth token in a header, so we can't just use `window.location.href`. Fetch
// the blob with the auth header, then trigger a client-side download.
export const exportHREmployeeData = async (employeeId, filenameHint = '') => {
  const token = localStorage.getItem('company_auth_token');
  const apiBase = (import.meta?.env?.VITE_API_URL || 'http://localhost:8000/api').replace(/\/$/, '');
  const resp = await fetch(`${apiBase}/hr/employees/${employeeId}/export`, {
    method: 'GET',
    headers: token ? { Authorization: `Token ${token}` } : {},
  });
  if (!resp.ok) {
    // Try to surface the API's error JSON when present.
    let detail = '';
    try { detail = (await resp.json())?.message || ''; } catch { /* not json */ }
    throw new Error(`Export failed: ${resp.status} ${detail}`.trim());
  }
  const blob = await resp.blob();
  // Filename from Content-Disposition when the server sets it, else fall back.
  const cd = resp.headers.get('Content-Disposition') || '';
  let filename = '';
  const match = /filename="?([^"]+)"?/i.exec(cd);
  if (match) filename = match[1];
  if (!filename) {
    const safe = (filenameHint || `employee_${employeeId}`).replace(/[^a-z0-9_-]/gi, '_');
    filename = `${safe}_gdpr_export.zip`;
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  return { status: 'success', size: blob.size, filename };
};

export const markHRDocumentOutdated = async (documentId) => {
  try {
    const response = await companyApi.post(`/hr/documents/${documentId}/mark-outdated`);
    return response;
  } catch (error) {
    console.error('Mark HR document outdated error:', error);
    throw error;
  }
};

export const unmarkHRDocumentOutdated = async (documentId) => {
  try {
    const response = await companyApi.post(`/hr/documents/${documentId}/unmark-outdated`);
    return response;
  } catch (error) {
    console.error('Unmark HR document outdated error:', error);
    throw error;
  }
};

export const reingestHRDocument = async (documentId) => {
  try {
    const response = await companyApi.post(`/hr/documents/${documentId}/reingest`);
    return response;
  } catch (error) {
    console.error('Reingest HR document error:', error);
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

export const updateHRNotificationTemplate = async (templateId, payload) => {
  try {
    const response = await companyApi.patch(`/hr/notifications/templates/${templateId}/update`, payload);
    return response;
  } catch (error) {
    console.error('Update HR notification template error:', error);
    throw error;
  }
};

export const deleteHRNotificationTemplate = async (templateId) => {
  try {
    const response = await companyApi.delete(`/hr/notifications/templates/${templateId}/delete`);
    return response;
  } catch (error) {
    console.error('Delete HR notification template error:', error);
    throw error;
  }
};

/** Fire a template right now — tests a template or sends a one-off announcement.
 * At least one of `recipient_email` / `recipient_employee_id` must be provided
 * for email-channel templates (Slack/Teams post into the company's channel and
 * ignore the recipient address). */
export const sendHRNotificationNow = async ({ template_id, recipient_email = '', recipient_employee_id = null, context = {} }) => {
  try {
    const response = await companyApi.post('/hr/notifications/send-now', {
      template_id,
      recipient_email,
      recipient_employee_id,
      context,
    });
    return response;
  } catch (error) {
    console.error('Send HR notification now error:', error);
    throw error;
  }
};

/** Dedicated leave-balance read. Employees can read their own; managers
 * can read their reports'; HR admins can read anyone. */
export const listHRLeaveBalances = async (employeeId) => {
  try {
    const response = await companyApi.get(`/hr/employees/${employeeId}/leave-balances`);
    return response;
  } catch (error) {
    console.error('List HR leave balances error:', error);
    throw error;
  }
};

/** HR-admin only. Adjust one leave_type's balance via deltas OR hard-sets.
 * `reason` is required and goes to the audit log. */
export const adjustHRLeaveBalance = async (employeeId, payload) => {
  try {
    const response = await companyApi.post(`/hr/employees/${employeeId}/leave-balances/adjust`, payload);
    return response;
  } catch (error) {
    console.error('Adjust HR leave balance error:', error);
    throw error;
  }
};

/** HR-admin only. Set an employee's employment_status to 'offboarded' with
 * a distinct audit-log entry (as opposed to editing the status via the
 * generic update endpoint). Idempotent — safe to call twice. */
export const deactivateHREmployee = async (employeeId, reason = '') => {
  try {
    const response = await companyApi.post(`/hr/employees/${employeeId}/deactivate`, { reason });
    return response;
  } catch (error) {
    console.error('Deactivate HR employee error:', error);
    throw error;
  }
};

/** HR-admin only. Reverse a deactivation. `target_status` defaults to
 * 'active' on the server side; pass explicitly to restore a specific
 * pre-offboard status (probation / on_leave / notice / etc.). */
export const reactivateHREmployee = async (employeeId, { target_status = 'active', reason = '' } = {}) => {
  try {
    const response = await companyApi.post(`/hr/employees/${employeeId}/reactivate`, {
      target_status, reason,
    });
    return response;
  } catch (error) {
    console.error('Reactivate HR employee error:', error);
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

export const cancelLeaveRequest = async (requestId, note = '') => {
  try {
    const response = await companyApi.post(`/hr/leave-requests/${requestId}/cancel`, { note });
    return response;
  } catch (error) {
    console.error('Cancel leave request error:', error);
    throw error;
  }
};

export const withdrawLeaveRequest = async (requestId, reason = '') => {
  try {
    const response = await companyApi.post(`/hr/leave-requests/${requestId}/withdraw`, { reason });
    return response;
  } catch (error) {
    console.error('Withdraw leave request error:', error);
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
  getHRDocumentStatus,
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
  closeHRReviewCycle,
  reopenHRReviewCycle,
  deleteHRReviewCycle,
  listHREmployeeReviews,
  updateHRPerfReview,
  listHRNotificationTemplates,
  createHRNotificationTemplate,
  updateHRNotificationTemplate,
  deleteHRNotificationTemplate,
  sendHRNotificationNow,
  listHRLeaveBalances,
  adjustHRLeaveBalance,
  deactivateHREmployee,
  reactivateHREmployee,
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
  cancelLeaveRequest,
  withdrawLeaveRequest,
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
  listEmployeeGoals,
  createEmployeeGoal,
  updateEmployeeGoal,
  deleteEmployeeGoal,
  listWorkflowTemplates,
  createWorkflowFromTemplate,
  getManagerTeamSummary,
  getHROrgChart,
  getMyHRProfile,
  listHRDocumentVersions,
  anonymizeHREmployee,
  exportHREmployeeData,
  markHRDocumentOutdated,
  unmarkHRDocumentOutdated,
  reingestHRDocument,
  listHRDocumentAccessLog,
};
