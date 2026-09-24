import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Loader2 } from 'lucide-react';

/**
 * Check whether a company account is logged in.
 *
 * This used to only accept the `project_manager` and `company_user` roles, but
 * CompanyUser has twelve and defaults to `admin` — so an owner or admin whose
 * company had bought the PM module still got "Access Denied". Which agent a
 * company may open is decided by the purchased modules, not by this role, and
 * every other agent already gates on the module alone. So any company login
 * passes here and the page's own module check does the real work.
 */
const isCompanyUserAuthenticated = () => {
  try {
    const companyUserStr = localStorage.getItem('company_user');
    if (!companyUserStr) return false;
    return !!JSON.parse(companyUserStr);
  } catch {
    return false;
  }
};

/**
 * Protected Route Component
 * Redirects to login if not authenticated
 * Checks for admin or project manager role if required
 * Also allows company users to access routes
 */
const ProtectedRoute = ({ children, requireAdmin = false, requireProjectManager = false }) => {
  const { isAuthenticated, loading, user, isAdmin, isProjectManager } = useAuth();
  const location = useLocation();
  
  // Check if user is authenticated (either regular user or company user)
  const companyUserAuth = isCompanyUserAuthenticated();
  const userIsAuthenticated = isAuthenticated || companyUserAuth;

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!userIsAuthenticated) {
    // Redirect to login page with return path
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (requireAdmin && !isAdmin()) {
    // User is authenticated but not an admin
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-destructive mb-2">Access Denied</h1>
          <p className="text-muted-foreground">
            You don't have permission to access this page. Admin access required.
          </p>
        </div>
      </div>
    );
  }

  if (requireProjectManager) {
    // Any company login gets through — the dashboard then checks that the
    // company actually bought the module. This only turns people away on the
    // employee login, where there is no company and no module to check.
    const isPM = isProjectManager() || companyUserAuth;
    if (!isPM) {
      return (
        <div className="min-h-screen flex items-center justify-center">
          <div className="text-center">
            <h1 className="text-2xl font-bold text-destructive mb-2">Access Denied</h1>
            <p className="text-muted-foreground">
              You don't have permission to access this page. Project Manager access required.
            </p>
            <p className="text-sm text-muted-foreground mt-2">
              Please log in with your company account.
            </p>
          </div>
        </div>
      );
    }
  }

  return children;
};

export default ProtectedRoute;

