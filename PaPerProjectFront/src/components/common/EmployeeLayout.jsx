import { useEffect } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, User as UserIcon } from 'lucide-react';
import DashboardNavbar from '@/components/common/DashboardNavbar';
import ErrorBoundary from '@/components/common/ErrorBoundary';
import { useAuth } from '@/contexts/AuthContext';
import { getEmployeeNavItems, EMPLOYEE_SECTION_FROM_PATH } from '@/utils/employeeNavItems';

/**
 * EmployeeLayout — shared shell for the `/me/*` route group.
 *
 * Peer to AgentLayout but scoped to individual employees (regular
 * Django-token users AND company_user accounts). Unlike AgentLayout,
 * this does NOT require a `company_user` in localStorage — a plain
 * Django-token employee should be able to reach every /me route.
 *
 * Mounts navbar + left sidebar ONCE; only the routed <Outlet/> content
 * swaps between /me/home, /me/tasks, /me/meetings, etc.
 */
const EmployeeLayout = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { toast } = useToast();
  const { user, isAuthenticated, loading, logout } = useAuth();

  const section = EMPLOYEE_SECTION_FROM_PATH(location.pathname);

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
          navItems={getEmployeeNavItems(navigate)}
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
