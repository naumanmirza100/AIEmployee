// API Configuration and Service Layer

import { API_BASE_URL } from '@/config/apiConfig';

/**
 * Get authentication token from localStorage
 */
export const getToken = () => {
  return localStorage.getItem('auth_token');
};

/**
 * Set authentication token in localStorage
 */
export const setToken = (token) => {
  if (token) {
    localStorage.setItem('auth_token', token);
  } else {
    localStorage.removeItem('auth_token');
  }
};

/**
 * Remove authentication token
 */
export const removeToken = () => {
  localStorage.removeItem('auth_token');
  localStorage.removeItem('user');
};

/**
 * Get user from localStorage
 */
export const getUser = () => {
  const userStr = localStorage.getItem('user');
  return userStr ? JSON.parse(userStr) : null;
};

/**
 * Set user in localStorage
 */
export const setUser = (user) => {
  if (user) {
    localStorage.setItem('user', JSON.stringify(user));
  } else {
    localStorage.removeItem('user');
  }
};

/**
 * Get company user from localStorage
 */
const getCompanyUser = () => {
  try {
    const userStr = localStorage.getItem('company_user');
    return userStr ? JSON.parse(userStr) : null;
  } catch {
    return null;
  }
};

/**
 * Base API request function
 */
const apiRequest = async (endpoint, options = {}) => {
  const token = getToken();
  const companyUser = getCompanyUser();
  
  const defaultHeaders = {
    'Content-Type': 'application/json',
  };
  
  // Use regular token authentication if available
  if (token) {
    // Django REST Framework TokenAuthentication uses "Token" prefix, not "Bearer"
    defaultHeaders['Authorization'] = `Token ${token}`;
  } 
  // Otherwise, use company user authentication headers
  else if (companyUser) {
    const userId = companyUser.id?.toString() || companyUser.id;
    const companyId = companyUser.companyId?.toString() || companyUser.company_id;
    
    if (userId && companyId) {
      defaultHeaders['X-Company-User-ID'] = userId;
      defaultHeaders['X-Company-ID'] = companyId;
    }
  }
  
  const config = {
    ...options,
    headers: {
      ...defaultHeaders,
      ...(options.headers || {}),
    },
  };
  
  try {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, config);
    
    // Handle non-JSON responses
    const contentType = response.headers.get('content-type');
    const isJson = contentType && contentType.includes('application/json');
    
    let data;
    try {
      if (isJson) {
        data = await response.json();
      } else {
        data = await response.text();
      }
    } catch (parseError) {
      // If response parsing fails, but status is OK, return empty object
      if (response.ok) {
        return {};
      }
      throw new Error(`Failed to parse response: ${parseError.message}`);
    }
    
    if (!response.ok) {
      // Handle error responses
      const errorMessage = data?.message || data?.error || `HTTP error! status: ${response.status}`;
      const error = new Error(errorMessage);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    
    return data;
  } catch (error) {
    // Check if it's a network error (CORS, connection failed, etc.)
    if (error.name === 'TypeError' && error.message.includes('fetch')) {
      console.error('Network Error (CORS or connection issue):', error);
      const networkError = new Error('Network error: Unable to connect to server. Please check CORS settings and ensure the backend is running.');
      networkError.isNetworkError = true;
      throw networkError;
    }
    
    // If error already has a message, re-throw it
    if (error.message) {
      console.error('API Request Error:', error);
      throw error;
    }
    
    // Generic error fallback
    console.error('API Request Error:', error);
    throw new Error(error.message || 'An unexpected error occurred');
  }
};

/**
 * API Methods
 */
export const api = {
  // GET request
  get: (endpoint, params = {}) => {
    const queryString = new URLSearchParams(params).toString();
    const url = queryString ? `${endpoint}?${queryString}` : endpoint;
    return apiRequest(url, { method: 'GET' });
  },
  
  // POST request
  post: (endpoint, data = {}) => {
    return apiRequest(endpoint, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
  
  // PUT request
  put: (endpoint, data = {}) => {
    return apiRequest(endpoint, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },
  
  // DELETE request
  delete: (endpoint) => {
    return apiRequest(endpoint, { method: 'DELETE' });
  },
  
  // PATCH request
  patch: (endpoint, data = {}) => {
    return apiRequest(endpoint, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },
  
  // Upload file
  upload: async (endpoint, formData) => {
    const token = getToken();
    const companyUser = getCompanyUser();
    const headers = {};
    
    if (token) {
      // Django REST Framework TokenAuthentication uses "Token" prefix, not "Bearer"
      headers['Authorization'] = `Token ${token}`;
    } 
    // Otherwise, use company user authentication headers
    else if (companyUser) {
      const userId = companyUser.id?.toString() || companyUser.id;
      const companyId = companyUser.companyId?.toString() || companyUser.company_id;
      
      if (userId && companyId) {
        headers['X-Company-User-ID'] = userId;
        headers['X-Company-ID'] = companyId;
      }
    }
    // Don't set Content-Type for FormData, browser will set it with boundary
    
    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'POST',
        headers,
        body: formData,
      });
      
      const data = await response.json();
      
      if (!response.ok) {
        const error = new Error(data.message || `HTTP error! status: ${response.status}`);
        error.status = response.status;
        error.data = data;
        throw error;
      }
      
      return data;
    } catch (error) {
      console.error('API Upload Error:', error);
      throw error;
    }
  },
};

export default api;

