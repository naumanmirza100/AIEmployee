// Company Auth Service

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

/**
 * Get company authentication token from localStorage
 */
const getCompanyToken = () => {
  return localStorage.getItem('company_auth_token');
};

/**
 * Get company user from localStorage
 */
const getCompanyUser = () => {
  const userStr = localStorage.getItem('company_user');
  if (!userStr) return null;
  try {
    return JSON.parse(userStr);
  } catch {
    return null;
  }
};

/**
 * Base API request function for company routes
 * options.responseType === 'blob' → returns blob (for file downloads), otherwise parses JSON
 */
const companyApiRequest = async (endpoint, options = {}) => {
  const token = getCompanyToken();
  const wantBlob = options.responseType === 'blob';

  const isFormData = options.body instanceof FormData;
  const defaultHeaders = {};
  if (!isFormData) {
    defaultHeaders['Content-Type'] = 'application/json';
  }
  // Add token-based authentication
  if (token) {
    defaultHeaders['Authorization'] = `Token ${token}`;
  } else {
    console.warn('No company auth token found in localStorage');
  }

  const { responseType, ...restOptions } = options;
  const config = {
    ...restOptions,
    headers: {
      ...defaultHeaders,
      ...(options.headers || {}),
    },
  };

  try {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, config);

    if (!response.ok) {
      let errorData;
      try {
        errorData = wantBlob ? { message: `HTTP error! status: ${response.status}` } : await response.json();
      } catch {
        errorData = { message: `HTTP error! status: ${response.status}` };
      }
      const error = new Error(errorData.message || `HTTP error! status: ${response.status}`);
      error.status = response.status;
      error.data = errorData;
      throw error;
    }

    if (wantBlob) {
      return await response.blob();
    }
    const data = await response.json();
    return data;
  } catch (error) {
    if (error.name === 'TypeError' && error.message.includes('fetch')) {
      console.error('Network error - Failed to fetch:', error);
      const networkError = new Error('Failed to connect to server. Please check if the backend is running.');
      networkError.isNetworkError = true;
      throw networkError;
    }
    console.error('Company API Request Error:', error);
    throw error;
  }
};

/**
 * Verify registration token
 */
export const verifyToken = async (token) => {
  try {
    // URL encode the token to handle special characters
    const encodedToken = encodeURIComponent(token);
    const response = await fetch(`${API_BASE_URL}/company/verify-token?token=${encodedToken}`);
    const data = await response.json();
    
    if (!response.ok) {
      const error = new Error(data.message || `HTTP error! status: ${response.status}`);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    
    return data;
  } catch (error) {
    console.error('Verify token error:', error);
    throw error;
  }
};

/**
 * Register company account
 */
export const registerCompany = async (registrationData) => {
  try {
    const response = await fetch(`${API_BASE_URL}/company/register`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(registrationData),
    });
    const data = await response.json();
    
    if (!response.ok) {
      const error = new Error(data.message || `HTTP error! status: ${response.status}`);
      error.status = response.status;
      throw error;
    }
    
    return data;
  } catch (error) {
    console.error('Register company error:', error);
    throw error;
  }
};

/**
 * Company login
 */
export const loginCompany = async (email, password) => {
  try {
    const response = await fetch(`${API_BASE_URL}/company/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email, password }),
    });
    const data = await response.json();
    
    if (!response.ok) {
      const error = new Error(data.message || `HTTP error! status: ${response.status}`);
      error.status = response.status;
      throw error;
    }
    
    // Store token and user data
    if (data.status === 'success' && data.data.token) {
      localStorage.setItem('company_auth_token', data.data.token);
      localStorage.setItem('company_user', JSON.stringify(data.data.user));
    }
    
    return data;
  } catch (error) {
    console.error('Company login error:', error);
    throw error;
  }
};

/**
 * Company API helper for authenticated requests
 */
export const companyApi = {
  get: (endpoint, paramsOrOptions = {}) => {
    const isBlobRequest = paramsOrOptions && paramsOrOptions.responseType === 'blob';
    let url = endpoint;
    const requestOptions = { method: 'GET' };
    if (isBlobRequest) {
      requestOptions.responseType = 'blob';
    } else if (paramsOrOptions && typeof paramsOrOptions === 'object' && Object.keys(paramsOrOptions).length > 0) {
      const queryString = new URLSearchParams(paramsOrOptions).toString();
      url = queryString ? `${endpoint}?${queryString}` : endpoint;
    }
    return companyApiRequest(url, requestOptions);
  },
  post: (endpoint, data = {}, options = {}) => {
    const isFormData = data instanceof FormData;
    return companyApiRequest(endpoint, {
      method: 'POST',
      body: isFormData ? data : JSON.stringify(data),
      ...options,
    });
  },
  put: (endpoint, data = {}) => {
    return companyApiRequest(endpoint, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },
  patch: (endpoint, data = {}) => {
    return companyApiRequest(endpoint, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },
  delete: (endpoint) => {
    return companyApiRequest(endpoint, {
      method: 'DELETE',
    });
  },
};

export { getCompanyToken, getCompanyUser };

export default {
  verifyToken,
  registerCompany,
  loginCompany,
  getCompanyToken,
  getCompanyUser,
  companyApi,
};

