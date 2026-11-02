// Authentication Service

import api, { setToken, setUser, removeToken, getUser, getToken } from './api';

// There is no self sign-up for employee logins: their company adds them (the old marketplace
// sign-up was removed on the server, CO-269). Companies sign up through companyAuthService.

/**
 * Login user
 */
export const login = async (email, password) => {
  try {
    const response = await api.post('/auth/login', {
      email,
      password,
    });
    
    if (response.status === 'success' && response.data.token) {
      setToken(response.data.token);
      setUser(response.data.user);
    }
    
    return response;
  } catch (error) {
    console.error('Login error:', error);
    throw error;
  }
};

/**
 * Logout user
 */
export const logout = async () => {
  try {
    await api.post('/auth/logout');
  } catch (error) {
    console.error('Logout error:', error);
  } finally {
    removeToken();
    setUser(null);
  }
};

/**
 * Get current authenticated user
 */
export const getCurrentUser = async () => {
  try {
    const response = await api.get('/auth/me');
    
    if (response.status === 'success' && response.data.user) {
      setUser(response.data.user);
      return response.data.user;
    }
    
    return null;
  } catch (error) {
    console.error('Get current user error:', error);
    removeToken();
    return null;
  }
};

/**
 * Check if user is authenticated
 */
export const isAuthenticated = () => {
  return !!getToken();
};

/**
 * Check if user has specific role
 */
export const hasRole = (role) => {
  const user = getUser();
  return user && user.userType === role;
};

/**
 * Check if user is client
 */
export const isClient = () => {
  return hasRole('client');
};

/**
 * Check if user is freelancer
 */
export const isFreelancer = () => {
  return hasRole('freelancer');
};

/**
 * Check if user is admin
 */
export const isAdmin = () => {
  return hasRole('admin');
};

export default {
  login,
  logout,
  getCurrentUser,
  isAuthenticated,
  hasRole,
  isClient,
  isFreelancer,
  isAdmin,
};

