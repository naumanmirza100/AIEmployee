import { useEffect, useState, useCallback } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, User as UserIcon } from 'lucide-react';
import DashboardNavbar from '@/components/common/DashboardNavbar';
import ErrorBoundary from '@/components/common/ErrorBoundary';
import { useAuth } from '@/contexts/AuthContext';
import { getEmployeeNavItems, EMPLOYEE_SECTION_FROM_PATH } from '@/utils/employeeNavItems';
import userTaskService from '@/services/userTaskService';
import { API_BASE_URL } from '@/config/apiConfig';
import { isOverdue } from '@/utils/taskHelpers';

/**
 * EmployeeLayout — shared shell for the `/me/*` route group.
 *
 * Peer to AgentLayout but scoped to individual employees (regular
 * Django-token users AND company_user accounts). Unlike AgentLayout,
 * this does NOT require a `company_user` in localStorage — a plain
 * Django-token employee should be able to reach every /me route.
 *
 * Also fetches badge counts (overdue tasks / pending meetings / unread
 * notifications) once on mount and every 60s, and passes them to
 * getEmployeeNavItems so the sidebar shows live pills.
 */
const EmployeeLayout = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { toast } = useToast();
  const { user, isAuthenticated, loading, logout } = useAuth();

  const section = EMPLOYEE_SECTION_FROM_PATH(location.pathname);

  const [counts, setCounts] = useState({
    overdueTasks: 0,
    pendingMeetings: 0,
    unreadNotifications: 0,
  });

  const refreshCounts = useCallback(async () => {
    const token = localStorage.getItem('auth_token') || localStorage.getItem('company_auth_token');
    if (!token) return;
    try {
      const [tRes, mRes, nRes] = await Promise.all([
        userTaskService.getMyTasks().catch(() => ({ status: 'error' })),
        fetch(`${API_BASE_URL}/meetings`, { headers: { 'Authorization': `Token ${token}` } })
          .then((r) => r.ok ? r.json() : { data: { meetings: [] } })
          .catch(() => ({ data: { meetings: [] } })),
        fetch(`${API_BASE_URL}/notifications`, { headers: { 'Authorization': `Token ${token}` } })
          .then((r) => r.ok ? r.json() : { data: [] })
          .catch(() => ({ data: [] })),
      ]);

      const tasks = tRes?.status === 'success' ? (tRes.data || []) : [];
      const meetings = mRes?.data?.meetings || [];
      const notifRaw = nRes?.data?.notifications || nRes?.data || [];
      const notifs = Array.isArray(notifRaw) ? notifRaw : [];

      const pending = meetings.filter((m) =>
        (m.my_status === 'pending' || m.my_status === 'counter_proposed' ||
         m.status === 'pending' || m.status === 'counter_proposed')
        && m.status !== 'withdrawn' && m.my_status !== 'accepted',
      ).length;

      const unread = notifs.filter((n) => !n.is_read).length;
      const overdue = tasks.filter(isOverdue).length;

      setCounts({
        overdueTasks: overdue,
        pendingMeetings: pending,
        unreadNotifications: unread,
      });
    } catch { /* silent — badges are best-effort */ }
  }, []);

  useEffect(() => {
    if (loading) return;
    if (!isAuthenticated || !user) {
      toast({
        title: 'Not logged in',
        description: 'Please log in to continue.',
        variant: 'destructive',
      });
      navigate('/login');
    }
  }, [isAuthenticated, user, loading, navigate, toast]);

  useEffect(() => {
    if (!user) return undefined;
    refreshCounts();
    const iv = setInterval(refreshCounts, 60_000);
    return () => clearInterval(iv);
  }, [user, refreshCounts]);

  // Also refresh whenever the route changes — visiting Tasks after
  // completing one should drop the overdue count immediately.
  useEffect(() => {
    if (user) refreshCounts();
  }, [location.pathname, user, refreshCounts]);

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#07030f' }}>
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }
  if (!user) return null;

  const displayName = user.fullName || user.username || user.email?.split('@')[0] || 'Employee';

  return (
    <>
      <Helmet><title>My Space | Pay Per Project</title></Helmet>
      <div
        className="min-h-screen"
        style={{ background: 'linear-gradient(135deg, #020308 0%, #0a0a1a 25%, #0d0b1f 50%, #0f0a20 75%, #020308 100%)' }}
      >
        <DashboardNavbar
          icon={UserIcon}
          title="My Space"
          subtitle={displayName}
          user={user}
          showNavTabs
          activeSection={section}
          onLogout={handleLogout}
          navItems={getEmployeeNavItems(navigate, counts)}
        />
        <main className="container mx-auto px-3 sm:px-4 py-4 sm:py-6 w-full max-w-full overflow-x-hidden">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </>
  );
};

export default EmployeeLayout;
