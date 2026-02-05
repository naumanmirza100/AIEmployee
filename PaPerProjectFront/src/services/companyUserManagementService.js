/**
 * Company User Management Service
 * Service for managing users created by company users
 */

import { companyApi } from './companyAuthService';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://aiemployeemine.onrender.com/api';

/**
 * Create a new user
 */
export const createUser = async (userData) => {
  try {
    const response = await companyApi.post('/company/users/create', userData);
    return response;
  } catch (error) {
    console.error('Error creating user:', error);
    throw error;
  }
};

/**
 * List all users created by the company user
 */
export const listUsers = async (params = {}) => {
  try {
    const queryParams = new URLSearchParams();
    if (params.page) queryParams.append('page', params.page);
    if (params.limit) queryParams.append('limit', params.limit);
    if (params.include_company_users) queryParams.append('include_company_users', params.include_company_users);
    
    const queryString = queryParams.toString();
    const endpoint = `/company/users${queryString ? `?${queryString}` : ''}`;
    
    const response = await companyApi.get(endpoint);
    return response;
  } catch (error) {
    console.error('Error listing users:', error);
    throw error;
  }
};

/**
 * Get user details
 */
export const getUser = async (userId) => {
  try {
    const response = await companyApi.get(`/company/users/${userId}`);
    return response;
  } catch (error) {
    console.error('Error getting user:', error);
    throw error;
  }
};

/**
 * Update user
 */
export const updateUser = async (userId, userData) => {
  try {
    const response = await companyApi.put(`/company/users/${userId}/update`, userData);
    return response;
  } catch (error) {
    console.error('Error updating user:', error);
    throw error;
  }
};

/**
 * Delete (deactivate) user
 */
export const deleteUser = async (userId) => {
  try {
    const response = await companyApi.delete(`/company/users/${userId}/delete`);
    return response;
  } catch (error) {
    console.error('Error deleting user:', error);
    throw error;
  }
};

export default {
  createUser,
  listUsers,
  getUser,
  updateUser,
  deleteUser,
};

