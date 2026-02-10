// Recruitment Agent Service

import { companyApi } from './companyAuthService';

import { API_BASE_URL } from '@/config/apiConfig';

/**
 * Get company authentication token from localStorage
 */
const getCompanyToken = () => {
  return localStorage.getItem('company_auth_token');
};

/**
 * Process CV files and return ranked results
 * @param {FileList|File[]} files - CV files to process
 * @param {number|null} jobDescriptionId - Optional job description ID
 * @param {string} jobDescriptionText - Optional job description text
 * @param {string} jobKeywords - Optional comma-separated keywords
 * @param {number|null} topN - Optional limit for top N results
 * @param {boolean} parseOnly - If true, only parse CVs without ranking
 */

export const processCVs = async (files, jobDescriptionId = null, jobDescriptionText = '', jobKeywords = '', topN = null, parseOnly = false) => {
  try {
    const token = getCompanyToken();
    if (!token) {
      throw new Error('No authentication token found');
    }

    const formData = new FormData();
    
    // Add files
    if (files && files.length > 0) {
      Array.from(files).forEach(file => {
        formData.append('files', file);
      });
    }

    // Add other parameters
    if (jobDescriptionId) {
      formData.append('job_description_id', jobDescriptionId);
    }
    if (jobDescriptionText) {
      formData.append('job_description_text', jobDescriptionText);
    }
    if (jobKeywords) {
      formData.append('job_keywords', jobKeywords);
    }
    if (topN) {
      formData.append('top_n', topN);
    }
    if (parseOnly) {
      formData.append('parse_only', 'true');
    }

    const response = await fetch(`${API_BASE_URL}/recruitment/process-cvs`, {
      method: 'POST',
      headers: {
        'Authorization': `Token ${token}`,
      },
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.message || `HTTP error! status: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Process CVs error:', error);
    throw error;
  }
};

// ---------- Per-agent APIs (call each agent individually) ----------

/**
 * CV Parser agent only. Returns structured parsed CV.
 * @param {File|undefined} file - PDF/DOCX/TXT file (optional)
 * @param {string|undefined} text - Raw CV text (optional, used if file not provided)
 */
export const apiCvParse = async (file, text) => {
  if (file) {
    const formData = new FormData();
    formData.append('file', file);
    // Do not set Content-Type manually - axios adds multipart/form-data with boundary
    const response = await companyApi.post('/recruitment/agents/cv/parse', formData);
    return response;
  }
  if (text) {
    const response = await companyApi.post('/recruitment/agents/cv/parse', { text });
    return response;
  }
  throw new Error("Provide 'file' or 'text'");
};

/**
 * Summarization agent only. Returns insights for a parsed CV.
 * @param {object|undefined} parsedJson - Parsed CV object (optional if cvRecordId provided)
 * @param {number|undefined} cvRecordId - CV record ID to load parsed from DB (optional)
 * @param {string[]|string|undefined} jobKeywords - Optional keywords (array or comma-separated)
 */
export const apiCvSummarize = async (parsedJson, cvRecordId, jobKeywords) => {
  const body = {};
  if (parsedJson) body.parsed_json = parsedJson;
  if (cvRecordId) body.cv_record_id = cvRecordId;
  if (jobKeywords !== undefined) body.job_keywords = Array.isArray(jobKeywords) ? jobKeywords : jobKeywords;
  const response = await companyApi.post('/recruitment/agents/cv/summarize', body);
  return response;
};

/**
 * Lead enrichment agent only. Returns enriched data.
 * @param {object|undefined} parsedJson - Parsed CV (optional if cvRecordId provided)
 * @param {object|undefined} insightsJson - Insights from summarize (optional if cvRecordId provided)
 * @param {number|undefined} cvRecordId - CV record ID to load from DB (optional)
 */
export const apiCvEnrich = async (parsedJson, insightsJson, cvRecordId) => {
  const body = {};
  if (parsedJson) body.parsed_json = parsedJson;
  if (insightsJson) body.insights_json = insightsJson;
  if (cvRecordId) body.cv_record_id = cvRecordId;
  const response = await companyApi.post('/recruitment/agents/cv/enrich', body);
  return response;
};

/**
 * Lead qualification agent only. Returns INTERVIEW/HOLD/REJECT with confidence and reasoning.
 * @param {object|undefined} parsedJson - Parsed CV (optional if cvRecordId provided)
 * @param {object|undefined} insightsJson - Insights (optional if cvRecordId provided)
 * @param {number|undefined} cvRecordId - CV record ID to load from DB (optional)
 * @param {string[]|string|undefined} jobKeywords - Optional job keywords
 * @param {object|undefined} enrichedJson - Optional enrichment from enrich agent
 * @param {number|undefined} interviewThreshold - Optional (default from settings)
 * @param {number|undefined} holdThreshold - Optional (default from settings)
 */
export const apiCvQualify = async (parsedJson, insightsJson, cvRecordId, jobKeywords, enrichedJson, interviewThreshold, holdThreshold) => {
  const body = {};
  if (parsedJson) body.parsed_json = parsedJson;
  if (insightsJson) body.insights_json = insightsJson;
  if (cvRecordId) body.cv_record_id = cvRecordId;
  if (jobKeywords !== undefined) body.job_keywords = Array.isArray(jobKeywords) ? jobKeywords : jobKeywords;
  if (enrichedJson) body.enriched_json = enrichedJson;
  if (interviewThreshold != null) body.interview_threshold = interviewThreshold;
  if (holdThreshold != null) body.hold_threshold = holdThreshold;
  const response = await companyApi.post('/recruitment/agents/cv/qualify', body);
  return response;
};

/**
 * Job description parser agent only. Returns extracted keywords and requirements.
 * @param {File|undefined} file - PDF/DOCX/TXT file (optional)
 * @param {string|undefined} text - Job description text (optional, used if file not provided)
 */
export const apiJobDescriptionParse = async (file, text) => {
  if (file) {
    const formData = new FormData();
    formData.append('file', file);
    const response = await companyApi.post('/recruitment/agents/job-description/parse', formData);
    return response;
  }
  if (text) {
    const response = await companyApi.post('/recruitment/agents/job-description/parse', { text });
    return response;
  }
  throw new Error("Provide 'file' or 'text'");
};

/**
 * AI-suggested interview questions from candidate CV + job (no history saved).
 * @param {number} cvRecordId - CV record ID
 * @param {number} jobDescriptionId - Job description ID
 */
export const suggestInterviewQuestions = async (cvRecordId, jobDescriptionId) => {
  const response = await companyApi.post('/recruitment/ai/suggest-interview-questions', {
    cv_record_id: cvRecordId,
    job_description_id: jobDescriptionId,
  });
  return response;
};

/**
 * Recruitment Knowledge Q&A. Ask questions about jobs, candidates, best fit, settings.
 * Returns { status, data: { answer, insights } }.
 */
export const recruitmentQA = async (question) => {
  const response = await companyApi.post('/recruitment/qa', { question });
  return response;
};

/**
 * List all QA chats (stored in DB)
 */
export const listQAChats = async () => {
  const response = await companyApi.get('/recruitment/qa/chats');
  return response;
};

/**
 * Create a new QA chat with optional messages
 * @param {{ title?: string, messages?: Array<{role, content, responseData?}> }} data
 */
export const createQAChat = async (data) => {
  const response = await companyApi.post('/recruitment/qa/chats/create', data);
  return response;
};

/**
 * Update a QA chat (add messages, optional title)
 * @param {number|string} chatId
 * @param {{ title?: string, messages?: Array<{role, content, responseData?}> }} data
 */
export const updateQAChat = async (chatId, data) => {
  const response = await companyApi.patch(`/recruitment/qa/chats/${chatId}/update`, data);
  return response;
};

/**
 * Delete a QA chat and all its messages
 * @param {number|string} chatId
 */
export const deleteQAChat = async (chatId) => {
  const response = await companyApi.delete(`/recruitment/qa/chats/${chatId}/delete`);
  return response;
};

/**
 * Get all job descriptions for the company user
 */
export const getJobDescriptions = async () => {
  try {
    const response = await companyApi.get('/recruitment/job-descriptions');
    return response;
  } catch (error) {
    console.error('Get job descriptions error:', error);
    throw error;
  }
};

/**
 * Generate job title and description from a prompt (AI fills form; user saves to create)
 * @param {string} prompt - User prompt describing the job to generate
 * @returns {Promise<{ title, description, requirements, location, department, type }>}
 */
export const generateJobDescription = async (prompt) => {
  try {
    const response = await companyApi.post('/recruitment/job-descriptions/generate', { prompt });
    return response;
  } catch (error) {
    console.error('Generate job description error:', error);
    throw error;
  }
};

/**
 * Create a new job description
 * @param {object} jobData - Job description data
 */
export const createJobDescription = async (jobData) => {
  try {
    const response = await companyApi.post('/recruitment/job-descriptions/create', jobData);
    return response;
  } catch (error) {
    console.error('Create job description error:', error);
    throw error;
  }
};

/**
 * Update an existing job description
 * @param {number} jobId - Job description ID
 * @param {object} jobData - Updated job description data
 */
export const updateJobDescription = async (jobId, jobData) => {
  try {
    const response = await companyApi.put(`/recruitment/job-descriptions/${jobId}/update`, jobData);
    return response;
  } catch (error) {
    console.error('Update job description error:', error);
    throw error;
  }
};

/**
 * Delete a job description
 * @param {number} jobId - Job description ID
 */
export const deleteJobDescription = async (jobId) => {
  try {
    const response = await companyApi.delete(`/recruitment/job-descriptions/${jobId}/delete`);
    return response;
  } catch (error) {
    console.error('Delete job description error:', error);
    throw error;
  }
};

/**
 * Get all interviews for the company user
 * @param {object} filters - Optional filters (status, etc.)
 */
export const getInterviews = async (filters = {}) => {
  try {
    const params = new URLSearchParams();
    if (filters.status) {
      params.append('status', filters.status);
    }
    if (filters.outcome !== undefined && filters.outcome !== '') {
      params.append('outcome', filters.outcome);
    }
    
    const queryString = params.toString();
    const endpoint = `/recruitment/interviews${queryString ? `?${queryString}` : ''}`;
    
    const response = await companyApi.get(endpoint);
    return response;
  } catch (error) {
    console.error('Get interviews error:', error);
    throw error;
  }
};

/**
 * Schedule a new interview
 * @param {object} interviewData - Interview data
 */
export const scheduleInterview = async (interviewData) => {
  try {
    const response = await companyApi.post('/recruitment/interviews/schedule', interviewData);
    return response;
  } catch (error) {
    console.error('Schedule interview error:', error);
    throw error;
  }
};

/**
 * Update interview status and/or outcome
 * @param {number} interviewId - Interview ID
 * @param {object} payload - { status?, outcome? }
 */
export const updateInterview = async (interviewId, payload) => {
  try {
    const response = await companyApi.patch(`/recruitment/interviews/${interviewId}/update`, payload);
    return response;
  } catch (error) {
    console.error('Update interview error:', error);
    throw error;
  }
};

/**
 * Get interview details
 * @param {number} interviewId - Interview ID
 */
export const getInterviewDetails = async (interviewId) => {
  try {
    const response = await companyApi.get(`/recruitment/interviews/${interviewId}`);
    return response;
  } catch (error) {
    console.error('Get interview details error:', error);
    throw error;
  }
};

/**
 * Get available slots for rescheduling an interview
 * @param {number} interviewId - Interview ID
 */
export const getRescheduleSlots = async (interviewId) => {
  try {
    const response = await companyApi.get(`/recruitment/interviews/${interviewId}/reschedule-slots`);
    return response;
  } catch (error) {
    console.error('Get reschedule slots error:', error);
    throw error;
  }
};

/**
 * Reschedule an interview to a new slot (sends new invitation to candidate)
 * @param {number} interviewId - Interview ID
 * @param {string} newSlotDatetime - New slot in ISO format
 */
export const rescheduleInterview = async (interviewId, newSlotDatetime) => {
  try {
    const response = await companyApi.post(`/recruitment/interviews/${interviewId}/reschedule`, {
      new_slot_datetime: newSlotDatetime,
    });
    return response;
  } catch (error) {
    console.error('Reschedule interview error:', error);
    throw error;
  }
};

/**
 * Get CV records/candidates with server-side pagination
 * @param {object} filters - Optional filters (job_id, decision, page, page_size)
 */
export const getCVRecords = async (filters = {}) => {
  try {
    const params = new URLSearchParams();
    if (filters.job_id) {
      params.append('job_id', filters.job_id);
    }
    if (filters.decision) {
      params.append('decision', filters.decision);
    }
    if (filters.page != null) {
      params.append('page', String(filters.page));
    }
    if (filters.page_size != null) {
      params.append('page_size', String(filters.page_size));
    }
    
    const queryString = params.toString();
    const endpoint = `/recruitment/cv-records${queryString ? `?${queryString}` : ''}`;
    
    const response = await companyApi.get(endpoint);
    return response;
  } catch (error) {
    console.error('Get CV records error:', error);
    throw error;
  }
};

/**
 * Bulk update qualification decision for selected CV records (admin override).
 * @param {number[]} cvRecordIds - Array of CV record IDs
 * @param {string} qualificationDecision - One of: INTERVIEW, HOLD, REJECT
 */
export const bulkUpdateCVRecords = async (cvRecordIds, qualificationDecision) => {
  try {
    const response = await companyApi.post('/recruitment/cv-records/bulk-update', {
      cv_record_ids: cvRecordIds,
      qualification_decision: qualificationDecision,
    });
    return response;
  } catch (error) {
    console.error('Bulk update CV records error:', error);
    throw error;
  }
};

/**
 * Get email settings for the company user
 */
export const getEmailSettings = async () => {
  try {
    const response = await companyApi.get('/recruitment/settings/email');
    return response;
  } catch (error) {
    console.error('Get email settings error:', error);
    throw error;
  }
};

/**
 * Update email settings
 * @param {object} settings - Email settings data
 */
export const updateEmailSettings = async (settings) => {
  try {
    const response = await companyApi.post('/recruitment/settings/email', settings);
    return response;
  } catch (error) {
    console.error('Update email settings error:', error);
    throw error;
  }
};

/**
 * Get interview settings for the company user (optionally for a specific job)
 * @param {number} jobId - Optional job ID to get job-specific settings
 */
export const getInterviewSettings = async (jobId = null) => {
  try {
    const params = jobId ? { job_id: jobId } : {};
    const response = await companyApi.get('/recruitment/settings/interview', params);
    return response;
  } catch (error) {
    console.error('Get interview settings error:', error);
    throw error;
  }
};

/**
 * Update interview settings
 * @param {object} settings - Interview settings data (can include job_id for job-specific settings)
 */
export const updateInterviewSettings = async (settings) => {
  try {
    const response = await companyApi.post('/recruitment/settings/interview', settings);
    return response;
  } catch (error) {
    console.error('Update interview settings error:', error);
    throw error;
  }
};

/**
 * Get qualification settings for the company user
 */
export const getQualificationSettings = async () => {
  try {
    const response = await companyApi.get('/recruitment/settings/qualification');
    return response;
  } catch (error) {
    console.error('Get qualification settings error:', error);
    throw error;
  }
};

/**
 * Update qualification settings
 * @param {object} settings - Qualification settings data (interview_threshold, hold_threshold, use_custom_thresholds)
 */
export const updateQualificationSettings = async (settings) => {
  try {
    const response = await companyApi.post('/recruitment/settings/qualification', settings);
    return response;
  } catch (error) {
    console.error('Update qualification settings error:', error);
    throw error;
  }
};

/**
 * Get recruitment analytics data
 * @param {number} days - Number of days for time-based analytics (default: 30)
 * @param {number} months - Number of months for monthly analytics (default: 6)
 * @param {number|null} jobId - Optional job ID to filter analytics by job
 */
export const getRecruitmentAnalytics = async (days = 30, months = 6, jobId = null) => {
  try {
    // companyApi.get(endpoint, queryParams) – second arg is the query object, not { params }
    const queryParams = { days, months };
    if (jobId != null && jobId !== '' && jobId !== 'all') {
      queryParams.job_id = typeof jobId === 'number' ? jobId : Number(jobId) || jobId;
    }
    const response = await companyApi.get('/recruitment/analytics', queryParams);
    return response;
  } catch (error) {
    console.error('Get recruitment analytics error:', error);
    throw error;
  }
};

export default {
  processCVs,
  getJobDescriptions,
  generateJobDescription,
  createJobDescription,
  updateJobDescription,
  deleteJobDescription,
  getInterviews,
  scheduleInterview,
  getInterviewDetails,
  getRescheduleSlots,
  rescheduleInterview,
  getCVRecords,
  bulkUpdateCVRecords,
  getEmailSettings,
  updateEmailSettings,
  getInterviewSettings,
  updateInterviewSettings,
  getQualificationSettings,
  updateQualificationSettings,
  getRecruitmentAnalytics,
  recruitmentQA,
  listQAChats,
  createQAChat,
  updateQAChat,
  deleteQAChat,
};


