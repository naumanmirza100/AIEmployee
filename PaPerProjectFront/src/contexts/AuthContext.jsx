// Authentication Context

import React, { createContext, useContext, useState, useEffect } from 'react';
import authService, { isAuthenticated as checkAuth } from '@/services/authService';
import { getUser as getStoredUser } from '@/services/api';
import { getCompanyUser, getCompanyToken } from '@/services/companyAuthService';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  // Check for both regular user and company user
  const storedUser = getStoredUser();
  const companyUser = getCompanyUser();
  const [user, setUser] = useState(storedUser || companyUser);
  const [loading, setLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(checkAuth() || !!getCompanyToken());

  useEffect(() => {
    // Check if user is authenticated on mount
    const checkUser = async () => {
      // Check for company user first
      const companyUser = getCompanyUser();
      const companyToken = getCompanyToken();
      
      if (companyUser && companyToken) {
        setUser(companyUser);
        setIsAuthenticated(true);
        setLoading(false);
        return;
      }
      
      // Check for regular user
      if (checkAuth()) {
        try {
          const currentUser = await authService.getCurrentUser();
          if (currentUser) {
            setUser(currentUser);
            setIsAuthenticated(true);
          } else {
            // Token might be invalid
            setUser(null);
            setIsAuthenticated(false);
          }
        } catch (error) {
          console.error('Auth check error:', error);
          setUser(null);
          setIsAuthenticated(false);
        }
      }
      setLoading(false);
    };

    checkUser();
  }, []);

  const login = async (email, password) => {
    try {
      const response = await authService.login(email, password);
      if (response.status === 'success' && response.data.user) {
        setUser(response.data.user);
        setIsAuthenticated(true);
        return response;
      }
      throw new Error(response.message || 'Login failed');
    } catch (error) {
      throw error;
    }
  };

  const register = async (userData) => {
    try {
      const response = await authService.register(userData);
      if (response.status === 'success' && response.data.user) {
        setUser(response.data.user);
        setIsAuthenticated(true);
        return response;
      }
      throw new Error(response.message || 'Registration failed');
    } catch (error) {
      throw error;
    }
  };

  const logout = async () => {
    try {
      await authService.logout();
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      // Clear company user data
      localStorage.removeItem('company_auth_token');
      localStorage.removeItem('company_user');
      localStorage.removeItem('company_purchased_modules');
      setUser(null);
      setIsAuthenticated(false);
    }
  };

  const updateUser = (userData) => {
    setUser(userData);
  };

  const value = {
    user,
    isAuthenticated,
    loading,
    login,
    register,
    logout,
    updateUser,
    isClient: () => user?.userType === 'client',
    isFreelancer: () => user?.userType === 'freelancer',
    isAdmin: () => user?.userType === 'admin',
    isProjectManager: () => {
      // Check for company user with project_manager or company_user role
      if ((user?.role === 'project_manager' || user?.role === 'company_user') && (user?.companyId || user?.company_id)) {
        return true;
      }
      // Check for regular user with project_manager role
      if (user?.role === 'project_manager' || user?.userType === 'project_manager') {
        return true;
      }
      return false;
    },
    isCompanyUser: () => !!user?.companyId || !!getCompanyToken(),
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export default AuthContext;

