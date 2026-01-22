// Recruitment Agent Service

import { companyApi } from './companyAuthService';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

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
 * Get CV records/candidates
 * @param {object} filters - Optional filters (job_id, decision)
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
 * Get interview settings for the company user
 */
export const getInterviewSettings = async () => {
  try {
    const response = await companyApi.get('/recruitment/settings/interview');
    return response;
  } catch (error) {
    console.error('Get interview settings error:', error);
    throw error;
  }
};

/**
 * Update interview settings
 * @param {object} settings - Interview settings data
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

export default {
  processCVs,
  getJobDescriptions,
  createJobDescription,
  updateJobDescription,
  deleteJobDescription,
  getInterviews,
  scheduleInterview,
  getInterviewDetails,
  getCVRecords,
  getEmailSettings,
  updateEmailSettings,
  getInterviewSettings,
  updateInterviewSettings,
  getQualificationSettings,
  updateQualificationSettings,
};


