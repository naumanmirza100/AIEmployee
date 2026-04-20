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

// ──────────────────────────────────────────────
// Knowledge Q&A
// ──────────────────────────────────────────────

/**
 * List all Q&A chats for current user
 */
export const listQaChats = async () => {
  try {
    return await companyApi.get('/operations/qa/chats');
  } catch (error) {
    console.error('List Q&A chats error:', error);
    throw error;
  }
};

/**
 * Create a new empty Q&A chat
 */
export const createQaChat = async (title = 'New chat') => {
  try {
    return await companyApi.post('/operations/qa/chats/create', { title });
  } catch (error) {
    console.error('Create Q&A chat error:', error);
    throw error;
  }
};

/**
 * Get a chat with all messages
 */
export const getQaChat = async (chatId) => {
  try {
    return await companyApi.get(`/operations/qa/chats/${chatId}/`);
  } catch (error) {
    console.error('Get Q&A chat error:', error);
    throw error;
  }
};

/**
 * Rename a Q&A chat
 */
export const renameQaChat = async (chatId, title) => {
  try {
    return await companyApi.patch(`/operations/qa/chats/${chatId}/rename`, { title });
  } catch (error) {
    console.error('Rename Q&A chat error:', error);
    throw error;
  }
};

/**
 * Delete a Q&A chat
 */
export const deleteQaChat = async (chatId) => {
  try {
    return await companyApi.delete(`/operations/qa/chats/${chatId}/delete`);
  } catch (error) {
    console.error('Delete Q&A chat error:', error);
    throw error;
  }
};

/**
 * Ask a question. Creates a chat if chatId omitted.
 * @param {string} question
 * @param {number|null} chatId
 * @param {number[]} [documentIds] optional restrict to specific doc ids
 */
export const askQaQuestion = async (question, chatId = null, documentIds = []) => {
  try {
    const body = { question };
    if (chatId) body.chat_id = chatId;
    if (Array.isArray(documentIds) && documentIds.length > 0) body.document_ids = documentIds;
    return await companyApi.post('/operations/qa/ask', body);
  } catch (error) {
    console.error('Ask Q&A question error:', error);
    throw error;
  }
};

// ──────────────────────────────────────────────
// Document Authoring
// ──────────────────────────────────────────────

/**
 * Generate a new professional document (non-streaming, blocking)
 * @param {object} payload { prompt, template_type, tone, title?, reference_document_ids? }
 */
export const generateDocument = async (payload) => {
  try {
    return await companyApi.post('/operations/authoring/generate', payload);
  } catch (error) {
    console.error('Generate document error:', error);
    throw error;
  }
};

/**
 * Streaming generation — text appears chunk-by-chunk as the AI writes.
 * @param {object} payload     { prompt, template_type, tone, title?, reference_document_ids? }
 * @param {object} handlers    { onMeta, onText, onDone, onError, signal }
 */
export const streamGenerateDocument = async (payload, handlers = {}) => {
  const { streamNdjsonPost } = await import('@/utils/streamingClient');
  const token = localStorage.getItem('company_auth_token');
  return streamNdjsonPost({
    url: `${API_BASE_URL}/operations/authoring/generate/stream`,
    headers: token ? { Authorization: `Token ${token}` } : {},
    body: payload,
    ...handlers,
  });
};

/** List generated documents */
export const listGeneratedDocuments = async (params = {}) => {
  try {
    return await companyApi.get('/operations/authoring/documents', params);
  } catch (error) {
    console.error('List generated documents error:', error);
    throw error;
  }
};

/** Get a single generated document (full content) */
export const getGeneratedDocument = async (docId) => {
  try {
    return await companyApi.get(`/operations/authoring/documents/${docId}/`);
  } catch (error) {
    console.error('Get generated document error:', error);
    throw error;
  }
};

/** Update (title and/or content) of a generated document */
export const updateGeneratedDocument = async (docId, payload) => {
  try {
    return await companyApi.patch(`/operations/authoring/documents/${docId}/update`, payload);
  } catch (error) {
    console.error('Update generated document error:', error);
    throw error;
  }
};

/** Delete a generated document */
export const deleteGeneratedDocument = async (docId) => {
  try {
    return await companyApi.delete(`/operations/authoring/documents/${docId}/delete`);
  } catch (error) {
    console.error('Delete generated document error:', error);
    throw error;
  }
};

/** Regenerate an existing document (fresh AI output, bumps version) */
export const regenerateDocument = async (docId, payload = {}) => {
  try {
    return await companyApi.post(`/operations/authoring/documents/${docId}/regenerate`, payload);
  } catch (error) {
    console.error('Regenerate document error:', error);
    throw error;
  }
};

/**
 * Returns the URL + auth header for directly downloading a generated doc as PDF.
 * Kept as a helper because we need the token on the fetch call.
 */
export const getGeneratedDocumentPdfUrl = (docId) => {
  return `${API_BASE_URL}/operations/authoring/documents/${docId}/export/pdf`;
};

/**
 * Fetch the PDF as a Blob (so we can trigger a download with a proper filename)
 */
export const fetchGeneratedDocumentPdf = async (docId) => {
  const token = localStorage.getItem('company_auth_token');
  const url = getGeneratedDocumentPdfUrl(docId);
  const response = await fetch(url, {
    method: 'GET',
    headers: token ? { Authorization: `Token ${token}` } : {},
  });
  if (!response.ok) {
    let msg = `HTTP ${response.status}`;
    try {
      const j = await response.json();
      if (j?.message) msg = j.message;
    } catch (_) { /* ignore */ }
    throw new Error(msg);
  }
  return await response.blob();
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
  // Q&A
  listQaChats,
  createQaChat,
  getQaChat,
  renameQaChat,
  deleteQaChat,
  askQaQuestion,
  // Authoring
  generateDocument,
  streamGenerateDocument,
  listGeneratedDocuments,
  getGeneratedDocument,
  updateGeneratedDocument,
  deleteGeneratedDocument,
  regenerateDocument,
  getGeneratedDocumentPdfUrl,
  fetchGeneratedDocumentPdf,
};
