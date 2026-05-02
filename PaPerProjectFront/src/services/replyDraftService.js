// Reply Draft Agent API service
// Mirrors the pattern used by marketingAgentService.js

import { companyApi } from './companyAuthService';

export const getReplyDraftDashboard = async () => {
  try {
    return await companyApi.get('/reply-draft/dashboard');
  } catch (error) {
    console.error('Get reply draft dashboard error:', error);
    throw error;
  }
};

export const listPendingReplies = async ({ campaign = '', days = '', direction = '' } = {}) => {
  try {
    const params = new URLSearchParams();
    if (campaign !== '' && campaign !== null && campaign !== undefined) {
      params.set('campaign', String(campaign));
    }
    if (days !== '' && days !== null && days !== undefined) {
      params.set('days', String(days));
    }
    // direction='out' switches the same endpoint to return synced Sent
    // folder mail (InboxEmail rows where direction='out'). Default 'in'
    // server-side keeps existing inbox callers unchanged.
    if (direction === 'in' || direction === 'out') {
      params.set('direction', direction);
    }
    const qs = params.toString();
    const path = qs ? `/reply-draft/pending-replies?${qs}` : '/reply-draft/pending-replies';
    return await companyApi.get(path);
  } catch (error) {
    console.error('List pending replies error:', error);
    throw error;
  }
};

export const listReplyDraftCampaigns = async () => {
  try {
    return await companyApi.get('/reply-draft/campaigns');
  } catch (error) {
    console.error('List reply-draft campaigns error:', error);
    throw error;
  }
};

export const listReplyDraftLeads = async ({ search = '', hasReplied = '', campaign = '' } = {}) => {
  try {
    const params = new URLSearchParams();
    if (search) params.set('search', search);
    if (hasReplied) params.set('has_replied', hasReplied);
    if (campaign) params.set('campaign', String(campaign));
    const qs = params.toString();
    const path = qs ? `/reply-draft/leads?${qs}` : '/reply-draft/leads';
    return await companyApi.get(path);
  } catch (error) {
    console.error('List reply-draft leads error:', error);
    throw error;
  }
};

export const listDrafts = async (statusFilter = null) => {
  try {
    const path = statusFilter
      ? `/reply-draft/drafts?status=${encodeURIComponent(statusFilter)}`
      : '/reply-draft/drafts';
    return await companyApi.get(path);
  } catch (error) {
    console.error('List drafts error:', error);
    throw error;
  }
};

export const generateDraft = async ({
  originalEmailId = null,
  inboxEmailId = null,
  userContext = '',
  tone = 'professional',
  length = null,
  emailAccountId = null,
} = {}) => {
  try {
    const payload = {
      user_context: userContext,
      tone,
      email_account_id: emailAccountId,
    };
    if (length) payload.length = length;
    if (originalEmailId) payload.original_email_id = originalEmailId;
    if (inboxEmailId) payload.inbox_email_id = inboxEmailId;
    return await companyApi.post('/reply-draft/drafts/generate', payload);
  } catch (error) {
    console.error('Generate draft error:', error);
    throw error;
  }
};

export const regenerateDraft = async (draftId, { newInstructions = '', tone = null, length = null } = {}) => {
  try {
    const payload = {
      new_instructions: newInstructions,
      tone,
    };
    if (length) payload.length = length;
    return await companyApi.post(`/reply-draft/drafts/${draftId}/regenerate`, payload);
  } catch (error) {
    console.error('Regenerate draft error:', error);
    throw error;
  }
};

export const approveDraft = async (draftId, { editedSubject = null, editedBody = null } = {}) => {
  try {
    return await companyApi.post(`/reply-draft/drafts/${draftId}/approve`, {
      edited_subject: editedSubject,
      edited_body: editedBody,
    });
  } catch (error) {
    console.error('Approve draft error:', error);
    throw error;
  }
};

export const rejectDraft = async (draftId) => {
  try {
    return await companyApi.post(`/reply-draft/drafts/${draftId}/reject`, {});
  } catch (error) {
    console.error('Reject draft error:', error);
    throw error;
  }
};

export const sendDraft = async (draftId) => {
  try {
    return await companyApi.post(`/reply-draft/drafts/${draftId}/send`, {});
  } catch (error) {
    console.error('Send draft error:', error);
    throw error;
  }
};

// Summary of the email accounts this company syncs from. Drives the
// visibility card in the Reply Draft UI (show which account is syncing /
// prompt to add one when none is configured).
export const listSyncAccounts = async () => {
  try {
    return await companyApi.get('/reply-draft/sync-accounts');
  } catch (error) {
    console.error('List sync accounts error:', error);
    throw error;
  }
};

// Create the Reply Draft Agent's dedicated inbox account. Isolated from
// marketing — accounts created here never surface on the marketing agent
// side because they carry the `is_reply_agent_account` flag.
export const createReplyAccount = async (data) => {
  try {
    return await companyApi.post('/reply-draft/accounts/create', data);
  } catch (error) {
    console.error('Create reply account error:', error);
    throw error;
  }
};

// Disconnect (delete) the Reply Draft Agent's attached EmailAccount. This
// cascades the account's InboxEmail + ReplyDraft rows, so the UI should
// gate this behind an explicit confirm.
export const deleteReplyAccount = async () => {
  try {
    return await companyApi.delete('/reply-draft/accounts/delete');
  } catch (error) {
    console.error('Delete reply account error:', error);
    throw error;
  }
};

// Daily-bucketed inbox volume for the attached account. Pass days to pick
// the window (30 / 60 / 90 / 120); the backend clamps anything unexpected.
// companyApi.get's second arg is the query object directly (NOT { params })
// — wrapping it broke this endpoint and made every window return the same
// default 30-day payload.
export const getReplyAnalytics = async ({ days = 30 } = {}) => {
  try {
    return await companyApi.get('/reply-draft/analytics', { days });
  } catch (error) {
    console.error('Reply analytics error:', error);
    throw error;
  }
};

// Fetch the full body for a single inbox item. The list endpoint serves
// only a 200-char preview so the page loads fast; this fills in the full
// content when the user clicks a row.
export const getReplyItem = async (source, id) => {
  try {
    const path = source === 'inbox'
      ? `/reply-draft/inbox/${id}`
      : `/reply-draft/reply/${id}`;
    return await companyApi.get(path);
  } catch (error) {
    console.error('Get reply item error:', error);
    throw error;
  }
};

// Create a fresh-compose draft (Gmail-style "+ Compose"). Returns a
// serialized ReplyDraft so the UI can attach files (uploads need a
// draft FK), edit further via composeUpdateDraft, and finally send via
// the existing approveDraft + sendDraft pipeline.
export const composeCreateDraft = async ({
  toEmail,
  subject,
  body = '',
  bodyFormat = 'text',
} = {}) => {
  try {
    return await companyApi.post('/reply-draft/drafts/compose', {
      to_email: toEmail,
      subject,
      body,
      body_format: bodyFormat,
    });
  } catch (error) {
    console.error('Compose create draft error:', error);
    throw error;
  }
};

// Update fields on an in-flight compose draft (recipient/subject/body/format).
// Reply drafts use approveDraft instead, which only touches subject + body.
export const composeUpdateDraft = async (draftId, {
  toEmail,
  subject,
  body,
  bodyFormat,
} = {}) => {
  try {
    const payload = {};
    if (toEmail !== undefined) payload.to_email = toEmail;
    if (subject !== undefined) payload.subject = subject;
    if (body !== undefined) payload.body = body;
    if (bodyFormat !== undefined) payload.body_format = bodyFormat;
    return await companyApi.post(`/reply-draft/drafts/${draftId}/compose`, payload);
  } catch (error) {
    console.error('Compose update draft error:', error);
    throw error;
  }
};

// Upload a user-picked file as an attachment on the given draft. Posts
// multipart/form-data — companyApi.post detects FormData and skips the
// JSON content-type header so the boundary is set correctly. Returns the
// new attachment object so the UI can append it to its local list.
export const uploadDraftAttachment = async (draftId, file) => {
  try {
    const form = new FormData();
    form.append('file', file);
    return await companyApi.post(`/reply-draft/drafts/${draftId}/attachments/upload`, form);
  } catch (error) {
    console.error('Upload draft attachment error:', error);
    throw error;
  }
};

// Remove a single attachment from a draft. Backend cascades the file delete
// via a post_delete signal, so disk/S3 stays in sync with DB.
export const deleteDraftAttachment = async (draftId, attachmentId) => {
  try {
    return await companyApi.delete(`/reply-draft/drafts/${draftId}/attachments/${attachmentId}`);
  } catch (error) {
    console.error('Delete draft attachment error:', error);
    throw error;
  }
};

