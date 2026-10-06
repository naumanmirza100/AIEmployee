import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

/**
 * UserDashboardRedirect — replaces the old /user/dashboard landing.
 *
 * Sends every employee to the /me/home shell. Employees with the Project
 * Manager role used to go to the company's Project Manager dashboard, which
 * needs a dashboard login's key and refused nearly everything they tried;
 * their own project screen (/user/dashboard/classic, which uses the employee
 * API) is linked from My Space home.
 *
 * See USER_DASHBOARD_REDESIGN.md, Chunks G + I.
 */
export default function UserDashboardRedirect() {
  const navigate = useNavigate();
  const { user, isAuthenticated, loading } = useAuth();

  useEffect(() => {
    if (loading) return;
    if (!isAuthenticated || !user) {
      navigate('/login', { replace: true });
      return;
    }
    navigate('/me/home', { replace: true });
  }, [user, isAuthenticated, loading, navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--sfc-07030f)' }}>
      <Loader2 className="h-8 w-8 animate-spin text-violet-400" />
    </div>
  );
}
