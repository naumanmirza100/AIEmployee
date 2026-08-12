import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

/**
 * UserDashboardRedirect — replaces the old /user/dashboard landing.
 *
 * Sends project managers to the full PM dashboard (which duplicated the
 * PM branch of the old UserDashboardPage anyway) and every other
 * employee to the new /me/home shell. The legacy page is still reachable
 * at /user/dashboard/classic for rollback / debugging.
 *
 * See USER_DASHBOARD_REDESIGN.md, Chunks G + I.
 */
export default function UserDashboardRedirect() {
  const navigate = useNavigate();
  const { user, isAuthenticated, loading, isProjectManager } = useAuth();

  useEffect(() => {
    if (loading) return;
    if (!isAuthenticated || !user) {
      navigate('/login', { replace: true });
      return;
    }
    if (isProjectManager && isProjectManager()) {
      navigate('/project-manager/dashboard', { replace: true });
    } else {
      navigate('/me/home', { replace: true });
    }
  }, [user, isAuthenticated, loading, isProjectManager, navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: '#07030f' }}>
      <Loader2 className="h-8 w-8 animate-spin text-violet-400" />
    </div>
  );
}
