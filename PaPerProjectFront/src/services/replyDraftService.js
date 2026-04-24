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

export const listPendingReplies = async ({ campaign = '', days = '' } = {}) => {
  try {
    const params = new URLSearchParams();
    if (campaign !== '' && campaign !== null && campaign !== undefined) {
      params.set('campaign', String(campaign));
    }
    if (days !== '' && days !== null && days !== undefined) {
      params.set('days', String(days));
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
  emailAccountId = null,
} = {}) => {
  try {
    const payload = {
      user_context: userContext,
      tone,
      email_account_id: emailAccountId,
    };
    if (originalEmailId) payload.original_email_id = originalEmailId;
    if (inboxEmailId) payload.inbox_email_id = inboxEmailId;
    return await companyApi.post('/reply-draft/drafts/generate', payload);
  } catch (error) {
    console.error('Generate draft error:', error);
    throw error;
  }
};

export const regenerateDraft = async (draftId, { newInstructions = '', tone = null } = {}) => {
  try {
    return await companyApi.post(`/reply-draft/drafts/${draftId}/regenerate`, {
      new_instructions: newInstructions,
      tone,
    });
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

