// Company Jobs Service

import { companyApi } from './companyAuthService';

/**
 * Create job position
 */
export const createJobPosition = async (jobData) => {
  try {
    const response = await companyApi.post('/company/jobs', jobData);
    return response;
  } catch (error) {
    console.error('Create job position error:', error);
    throw error;
  }
};

/**
 * Get company's jobs
 */
export const getCompanyJobs = async (params = {}) => {
  try {
    const queryParams = {};
    if (params.page) queryParams.page = params.page;
    if (params.limit) queryParams.limit = params.limit;
    if (params.search) queryParams.search = params.search;
    if (params.isActive !== undefined) queryParams.isActive = params.isActive;

    // Backend endpoint is /company/jobs/list, not /company/jobs
    const response = await companyApi.get('/company/jobs/list', queryParams);
    console.log('Get company jobs response:', response);
    return response;
  } catch (error) {
    console.error('Get company jobs error:', error);
    throw error;
  }
};

/**
 * Update job position
 */
export const updateJobPosition = async (jobId, jobData) => {
  try {
    const response = await companyApi.put(`/company/jobs/${jobId}`, jobData);
    return response;
  } catch (error) {
    console.error('Update job position error:', error);
    throw error;
  }
};

/**
 * Get job applications
 */
export const getJobApplications = async (jobId) => {
  try {
    const response = await companyApi.get(`/company/jobs/${jobId}/applications`);
    return response;
  } catch (error) {
    console.error('Get job applications error:', error);
    throw error;
  }
};

/**
 * Update application status
 */
export const updateApplicationStatus = async (applicationId, status) => {
  try {
    const response = await companyApi.patch(`/company/applications/${applicationId}/status`, { status });
    return response;
  } catch (error) {
    console.error('Update application status error:', error);
    throw error;
  }
};

/**
 * Run AI pipeline on all unprocessed applications for a job
 */
export const processJobApplicants = async (jobId) => {
  try {
    const response = await companyApi.post(`/company/jobs/${jobId}/process-applicants`);
    return response;
  } catch (error) {
    console.error('Process job applicants error:', error);
    throw error;
  }
};

export default {
  createJobPosition,
  getCompanyJobs,
  updateJobPosition,
  getJobApplications,
  updateApplicationStatus,
  processJobApplicants,
};

