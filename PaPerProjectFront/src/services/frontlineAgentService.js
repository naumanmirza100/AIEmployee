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

/** Save widget theming + operating hours + pre-chat + allowed_origins. */
export const updateFrontlineWidgetConfig = async ({ config, allowedOrigins } = {}) => {
  const payload = {};
  if (config !== undefined) payload.config = config;
  if (allowedOrigins !== undefined) payload.allowed_origins = allowedOrigins;
  const response = await companyApi.patch('/frontline/widget-config/update', payload);
  return response;
};

/** Fetch the public widget config — for use by the embedded widget itself.
 * Not auth'd; passes widget_key via query param. */
export const getPublicWidgetConfig = async (widgetKey) => {
  const base = (import.meta?.env?.VITE_API_BASE_URL || '').replace(/\/$/, '');
  const res = await fetch(`${base}/frontline/widget/public-config/?widget_key=${encodeURIComponent(widgetKey)}`);
  return res.json();
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
export const uploadDocument = async (file, title, description, documentType = 'knowledge_base', options = {}) => {
  try {
    const token = localStorage.getItem('company_auth_token');

    const formData = new FormData();
    formData.append('file', file);
    formData.append('title', title || file.name);
    formData.append('description', description || '');
    formData.append('document_type', documentType);
    // Optional new fields (Phase 2 Batch 5): visibility, retention, new-version, chunking
    if (options.visibility) formData.append('visibility', options.visibility);
    if (options.retentionDays) formData.append('retention_days', String(options.retentionDays));
    if (options.parentDocumentId) formData.append('parent_document_id', String(options.parentDocumentId));
    if (options.chunkSize) formData.append('chunk_size', String(options.chunkSize));
    if (options.chunkOverlap != null) formData.append('chunk_overlap', String(options.chunkOverlap));

    const response = await fetch(`${API_BASE_URL}/frontline/documents/upload/`, {
      method: 'POST',
      headers: token ? { 'Authorization': `Token ${token}` } : {},
      body: formData,
    });

    const data = await response.json();
    if (!response.ok && response.status !== 202) {
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

/** Poll a document's async processing status. */
export const getDocumentStatus = async (documentId) => {
  const response = await companyApi.get(`/frontline/documents/${documentId}/status`);
  return response;
};

/** Update document metadata (title/description/visibility/retention_days/allowed_user_ids). */
export const updateDocumentMetadata = async (documentId, patch) => {
  const response = await companyApi.patch(`/frontline/documents/${documentId}/metadata`, patch);
  return response;
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
 * Submit helpful/not helpful feedback for a KB answer (improves docs and RAG).
 * @param {{ question: string, helpful: boolean, document_id?: number }} data
 */
export const submitKnowledgeFeedback = async (data) => {
  try {
    const response = await companyApi.post('/frontline/knowledge/feedback', data);
    return response;
  } catch (error) {
    console.error('Submit knowledge feedback error:', error);
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

/** List tickets that are SLA breached or at risk (for aging alerts). */
export const listTicketsAging = async () => {
  try {
    const response = await companyApi.get('/frontline/tickets/aging');
    return response;
  } catch (error) {
    console.error('List tickets aging error:', error);
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

/** List internal notes on a ticket. */
export const listTicketNotes = async (ticketId) => {
  const response = await companyApi.get(`/frontline/tickets/${ticketId}/notes`);
  return response;
};

/** Add an internal note to a ticket. */
export const createTicketNote = async (ticketId, body, isInternal = true) => {
  const response = await companyApi.post(`/frontline/tickets/${ticketId}/notes/create`, {
    body,
    is_internal: isInternal,
  });
  return response;
};

/** Update a ticket note (author only). */
export const updateTicketNote = async (ticketId, noteId, body) => {
  const response = await companyApi.patch(`/frontline/tickets/${ticketId}/notes/${noteId}`, { body });
  return response;
};

/** Delete a ticket note (author only). */
export const deleteTicketNote = async (ticketId, noteId) => {
  const response = await companyApi.delete(`/frontline/tickets/${ticketId}/notes/${noteId}`);
  return response;
};

/** Snooze a ticket. Accepts either { hours } or { snoozedUntil: ISO string }. */
export const snoozeTicket = async (ticketId, { hours, snoozedUntil } = {}) => {
  const payload = snoozedUntil ? { snoozed_until: snoozedUntil } : { hours };
  const response = await companyApi.post(`/frontline/tickets/${ticketId}/snooze`, payload);
  return response;
};

/** Clear a ticket's snooze. */
export const unsnoozeTicket = async (ticketId) => {
  const response = await companyApi.post(`/frontline/tickets/${ticketId}/unsnooze`, {});
  return response;
};

/** Pause / resume SLA clock. */
export const pauseTicketSla = async (ticketId) => {
  const response = await companyApi.post(`/frontline/tickets/${ticketId}/sla/pause`, {});
  return response;
};
export const resumeTicketSla = async (ticketId) => {
  const response = await companyApi.post(`/frontline/tickets/${ticketId}/sla/resume`, {});
  return response;
};

/** Re-run LLM triage on a ticket (e.g. after description update). */
export const retriageTicket = async (ticketId) => {
  const response = await companyApi.post(`/frontline/tickets/${ticketId}/retriage`, {});
  return response;
};

// ---------- Meetings (Phase 2 Batch 6) ----------

/** List meetings. Params: status, date_from, date_to, organizer_id, page, limit. */
export const listMeetings = async (params = {}) => {
  const q = new URLSearchParams(params).toString();
  const response = await companyApi.get(`/frontline/meetings${q ? `?${q}` : ''}`);
  return response;
};

/** Create a meeting. `auto_jitsi` defaults to true on the server side. */
export const createMeeting = async (payload) => {
  const response = await companyApi.post('/frontline/meetings/create', payload);
  return response;
};

/** Get a single meeting (includes transcript). */
export const getMeeting = async (meetingId) => {
  const response = await companyApi.get(`/frontline/meetings/${meetingId}`);
  return response;
};

export const updateMeeting = async (meetingId, patch) => {
  const response = await companyApi.patch(`/frontline/meetings/${meetingId}/update`, patch);
  return response;
};

export const deleteMeeting = async (meetingId) => {
  const response = await companyApi.delete(`/frontline/meetings/${meetingId}/delete`);
  return response;
};

/** Check if a candidate slot conflicts for listed participants.
 * `participantCompanyUserIds` is an array of CompanyUser ids. */
export const checkMeetingAvailability = async (startIso, durationMinutes = 60, participantCompanyUserIds = []) => {
  const q = new URLSearchParams({
    start: startIso,
    duration_minutes: String(durationMinutes),
    participant_company_user_ids: participantCompanyUserIds.join(','),
  }).toString();
  const response = await companyApi.get(`/frontline/meetings/availability?${q}`);
  return response;
};

/** LLM-extract action items from the meeting transcript. When `createTickets=true`,
 * each extracted item also becomes a ticket. */
export const extractMeetingActionItems = async (meetingId, createTickets = false) => {
  const response = await companyApi.post(
    `/frontline/meetings/${meetingId}/extract-action-items`,
    { create_tickets: createTickets },
  );
  return response;
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

/** Render a template with sample placeholder values (no send). */
export const previewNotificationTemplate = async (templateId, context = {}) => {
  const response = await companyApi.post(
    `/frontline/notifications/templates/${templateId}/preview`,
    { context },
  );
  return response;
};

/** List dead-lettered (permanently failed) notifications for this company. */
export const listDeadLetteredNotifications = async (params = {}) => {
  const q = new URLSearchParams(params).toString();
  const response = await companyApi.get(`/frontline/notifications/dead-lettered${q ? `?${q}` : ''}`);
  return response;
};

/** Kick a dead-lettered or failed notification back into the pending queue. */
export const retryDeadLetteredNotification = async (notificationId) => {
  const response = await companyApi.post(`/frontline/notifications/${notificationId}/retry`, {});
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

/** Get current user's notification preferences (email, in-app, per-event toggles). */
export const getNotificationPreferences = async () => {
  const response = await companyApi.get('/frontline/notifications/preferences');
  return response;
};

/** Update current user's notification preferences. */
export const updateNotificationPreferences = async (data) => {
  const response = await companyApi.patch('/frontline/notifications/preferences/update', data);
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
/** Dry-run a workflow with a given context. No side effects. */
export const dryRunWorkflow = async (workflowId, context = {}) => {
  const response = await companyApi.post(`/frontline/workflows/${workflowId}/dry-run`, { context });
  return response;
};

/** List historical versions of a workflow (most recent first). */
export const listWorkflowVersions = async (workflowId) => {
  const response = await companyApi.get(`/frontline/workflows/${workflowId}/versions`);
  return response;
};

/** Roll a workflow back to a prior version (snapshots current state first). */
export const rollbackWorkflow = async (workflowId, version) => {
  const response = await companyApi.post(`/frontline/workflows/${workflowId}/versions/${version}/rollback`, {});
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

/** List company users for workflow assign step (same company). */
export const listWorkflowCompanyUsers = async () => {
  const response = await companyApi.get('/frontline/workflows/company-users');
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

/** AI Graph Maker: generate a chart from a natural language prompt. Returns { chart: { type, title, data, colors, color }, insights }. */
export const generateFrontlineGraph = async (prompt, dateFrom, dateTo) => {
  const response = await companyApi.post('/frontline/analytics/generate-graph', {
    prompt: prompt.trim(),
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  });
  return response;
};

/** Get saved graph prompts */
export const getFrontlineSavedGraphPrompts = async () => {
  const response = await companyApi.get('/frontline/analytics/graph-prompts');
  return response;
};

/** Save a graph prompt. Body: { title, prompt, tags?, chart_type? } */
export const saveFrontlineGraphPrompt = async (payload) => {
  const response = await companyApi.post('/frontline/analytics/graph-prompts/save', payload);
  return response;
};

/** Delete a saved graph prompt */
export const deleteFrontlineGraphPrompt = async (promptId) => {
  const response = await companyApi.delete(`/frontline/analytics/graph-prompts/${promptId}/delete`);
  return response;
};

/** Toggle favorite on a saved graph prompt. Body: { is_favorite: boolean } */
export const toggleFrontlineGraphPromptFavorite = async (promptId, isFavorite) => {
  const response = await companyApi.patch(`/frontline/analytics/graph-prompts/${promptId}/favorite`, { is_favorite: isFavorite });
  return response;
};
/** Download analytics export as CSV (uses auth token from localStorage). */
/** Per-agent performance summary (tickets assigned/resolved, avg resolution, SLA breaches). */
export const getFrontlineAgentPerformance = async (dateFrom, dateTo) => {
  const q = new URLSearchParams();
  if (dateFrom) q.set('date_from', dateFrom);
  if (dateTo) q.set('date_to', dateTo);
  const qs = q.toString();
  const response = await companyApi.get(`/frontline/analytics/agent-performance${qs ? `?${qs}` : ''}`);
  return response;
};

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

// =========================================================================
// Contacts + Customer 360 (Phase 3 Batch 2)
// =========================================================================

/** List contacts for the current company. Params: { q, tag, limit, offset } */
export const listContacts = async (params = {}) => {
  try {
    const q = new URLSearchParams();
    if (params.q) q.set('q', params.q);
    if (params.tag) q.set('tag', params.tag);
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    const qs = q.toString();
    const response = await companyApi.get(`/frontline/contacts${qs ? `?${qs}` : ''}`);
    return response;
  } catch (error) {
    console.error('List contacts error:', error);
    throw error;
  }
};

/** Create / upsert a contact. Body: { email, name?, phone?, tags?, custom_fields? } */
export const createContact = async (payload) => {
  try {
    const response = await companyApi.post('/frontline/contacts/create', payload);
    return response;
  } catch (error) {
    console.error('Create contact error:', error);
    throw error;
  }
};

/** Get a single contact by id. */
export const getContact = async (contactId) => {
  try {
    const response = await companyApi.get(`/frontline/contacts/${contactId}`);
    return response;
  } catch (error) {
    console.error('Get contact error:', error);
    throw error;
  }
};

/** Update contact fields (name/phone/tags/custom_fields). Email is immutable. */
export const updateContact = async (contactId, payload) => {
  try {
    const response = await companyApi.patch(`/frontline/contacts/${contactId}/update`, payload);
    return response;
  } catch (error) {
    console.error('Update contact error:', error);
    throw error;
  }
};

/** All tickets linked to a contact. */
export const listContactTickets = async (contactId) => {
  try {
    const response = await companyApi.get(`/frontline/contacts/${contactId}/tickets`);
    return response;
  } catch (error) {
    console.error('List contact tickets error:', error);
    throw error;
  }
};

// =========================================================================
// Ticket thread messages + outbound reply (Phase 3 Batch 1)
// =========================================================================

/** List all messages (inbound + outbound, oldest first) on a ticket thread. */
export const listTicketMessages = async (ticketId) => {
  try {
    const response = await companyApi.get(`/frontline/tickets/${ticketId}/messages`);
    return response;
  } catch (error) {
    console.error('List ticket messages error:', error);
    throw error;
  }
};

/** Send an outbound email reply on a ticket.
 *  Body: { body_text, body_html?, to?, cc? }  (to defaults to the last inbound sender) */
export const replyToTicket = async (ticketId, payload) => {
  try {
    const response = await companyApi.post(`/frontline/tickets/${ticketId}/reply`, payload);
    return response;
  } catch (error) {
    console.error('Reply to ticket error:', error);
    throw error;
  }
};

// =========================================================================
// Hand-off queue + reply-draft assist (Phase 3 Batch 4)
// =========================================================================

/** List hand-off queue. Params: { status: 'pending'|'accepted'|'all', mine?: boolean } */
export const listHandoffQueue = async (params = {}) => {
  try {
    const q = new URLSearchParams();
    if (params.status) q.set('status', params.status);
    if (params.mine) q.set('mine', '1');
    const qs = q.toString();
    const response = await companyApi.get(`/frontline/tickets/handoffs${qs ? `?${qs}` : ''}`);
    return response;
  } catch (error) {
    console.error('List handoff queue error:', error);
    throw error;
  }
};

/** Claim a pending hand-off — assigns the ticket to the caller. */
export const acceptHandoff = async (ticketId) => {
  try {
    const response = await companyApi.post(`/frontline/tickets/${ticketId}/accept-handoff`);
    return response;
  } catch (error) {
    console.error('Accept handoff error:', error);
    throw error;
  }
};

/** Ask the LLM to draft a reply for a ticket, grounded in the thread + KB. */
export const suggestTicketReply = async (ticketId) => {
  try {
    const response = await companyApi.post(`/frontline/tickets/${ticketId}/suggest-reply`);
    return response;
  } catch (error) {
    console.error('Suggest ticket reply error:', error);
    throw error;
  }
};

/** Customer-360 panel for a ticket: contact + stats + recent tickets. */
export const getTicketContext = async (ticketId) => {
  try {
    const response = await companyApi.get(`/frontline/tickets/${ticketId}/context`);
    return response;
  } catch (error) {
    console.error('Get ticket context error:', error);
    throw error;
  }
};


export default {
  getFrontlineDashboard,
  getFrontlineWidgetConfig,
  updateFrontlineWidgetConfig,
  getPublicWidgetConfig,
  listDocuments,
  getDocument,
  uploadDocument,
  deleteDocument,
  getDocumentStatus,
  updateDocumentMetadata,
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
  listTicketNotes,
  createTicketNote,
  updateTicketNote,
  deleteTicketNote,
  snoozeTicket,
  unsnoozeTicket,
  pauseTicketSla,
  resumeTicketSla,
  retriageTicket,
  listMeetings,
  createMeeting,
  getMeeting,
  updateMeeting,
  deleteMeeting,
  checkMeetingAvailability,
  extractMeetingActionItems,
  listNotificationTemplates,
  createNotificationTemplate,
  getNotificationTemplate,
  updateNotificationTemplate,
  deleteNotificationTemplate,
  previewNotificationTemplate,
  listDeadLetteredNotifications,
  retryDeadLetteredNotification,
  listScheduledNotifications,
  scheduleNotification,
  sendNotificationNow,
  listWorkflows,
  createWorkflow,
  getWorkflow,
  updateWorkflow,
  deleteWorkflow,
  executeWorkflow,
  dryRunWorkflow,
  listWorkflowVersions,
  rollbackWorkflow,
  listWorkflowExecutions,
  getFrontlineAnalytics,
  askFrontlineAnalytics,
  generateFrontlineGraph,
  getFrontlineSavedGraphPrompts,
  saveFrontlineGraphPrompt,
  deleteFrontlineGraphPrompt,
  toggleFrontlineGraphPromptFavorite,
  downloadFrontlineAnalyticsExport,
  getFrontlineAgentPerformance,
  listContacts,
  createContact,
  getContact,
  updateContact,
  listContactTickets,
  getTicketContext,
  listTicketMessages,
  replyToTicket,
  listHandoffQueue,
  acceptHandoff,
  suggestTicketReply,
};

