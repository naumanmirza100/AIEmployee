import { useState, useEffect } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Lock } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import DashboardNavbar from '@/components/common/DashboardNavbar';
import ErrorBoundary from '@/components/common/ErrorBoundary';
import usePurchasedModules from '@/hooks/usePurchasedModules';
import { getAgentNavItems } from '@/utils/agentNavItems';
import { logoutCompany } from '@/services/companyAuthService';
import { checkModuleAccess } from '@/services/modulePurchaseService';
import { agentMetaForPath, AGENT_META } from '@/utils/agentMeta';

/**
 * Shared layout for every agent (SDR, Recruitment, Marketing, …).
 *
 * Mounts the top navbar + left sidebar + purchased-modules fetch ONCE and keeps
 * them alive while the user moves between agents — only the routed <Outlet/>
 * content changes. This removes the "full page reload" feel: the sidebar never
 * unmounts and modules are fetched a single time.
 *
 * The current agent is derived from the URL, so one layout instance serves all
 * agent routes nested beneath it.
 */
const AgentLayout = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { toast } = useToast();

  const [companyUser, setCompanyUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);
  const { purchasedModules, modulesLoaded } = usePurchasedModules();

  // Access is tracked per-section so switching agents re-evaluates the gate
  // without re-fetching modules. { [section]: true|false }
  const [accessBySection, setAccessBySection] = useState({});

  const meta = agentMetaForPath(location.pathname) || AGENT_META['ai-sdr'];
  const section = meta.section;

  // ── Auth guard (runs once) ──
  useEffect(() => {
    const companyUserStr = localStorage.getItem('company_user');
    if (!companyUserStr) {
      toast({ title: 'Not logged in', description: 'Please log in to continue.', variant: 'destructive' });
      navigate('/company/login');
      setAuthChecked(true);
      return;
    }
    try {
      setCompanyUser(JSON.parse(companyUserStr));
    } catch {
      localStorage.removeItem('company_user');
      navigate('/company/login');
    } finally {
      setAuthChecked(true);
    }
  }, [navigate, toast]);

  // ── Module access check — re-runs when the agent (section) changes ──
  useEffect(() => {
    let cancelled = false;
    const { moduleKey } = meta;
    // null moduleKey → always granted (matches AI SDR's historic behaviour).
    if (!moduleKey) {
      setAccessBySection((prev) => (prev[section] === true ? prev : { ...prev, [section]: true }));
      return undefined;
    }
    // Already resolved for this section — don't re-check.
    if (accessBySection[section] !== undefined) return undefined;

    (async () => {
      try {
        const response = await checkModuleAccess(moduleKey);
        if (cancelled) return;
        const granted = response?.status === 'success' ? !!response.has_access : true;
        setAccessBySection((prev) => ({ ...prev, [section]: granted }));
        if (!granted) {
          toast({
            title: 'Module Not Purchased',
            description: `Please purchase the ${meta.title} module to access this dashboard.`,
            variant: 'default',
          });
        }
      } catch {
        // Network/API error — fail open (matches previous per-page behaviour).
        if (!cancelled) setAccessBySection((prev) => ({ ...prev, [section]: true }));
      }
    })();
    return () => { cancelled = true; };
  }, [section, meta, accessBySection, toast]);

  const handleLogout = async () => {
    await logoutCompany();
    navigate('/company/login');
  };

  // Auth still resolving, or redirected away.
  if (!authChecked) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#07030f' }}>
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }
  if (!companyUser) return null;

  const modulesLoading = !modulesLoaded;
  const hasAccess = accessBySection[section];
  const accessResolved = hasAccess !== undefined;

  // Decide what goes in the content area. The shell (navbar + sidebar) is the
  // SAME element tree in every case, so React keeps it mounted and only the
  // inner content swaps — no reload/flash between agents.
  let content;
  if (modulesLoading || !accessResolved) {
    content = (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-7 w-7 animate-spin text-primary" />
      </div>
    );
  } else if (!hasAccess) {
    content = (
      <div className="flex items-center justify-center py-16 px-4">
        <Card className="max-w-md w-full">
          <CardHeader>
            <div className="flex items-center justify-center mb-4">
              <Lock className="h-12 w-12 text-muted-foreground" />
            </div>
            <CardTitle className="text-center">Module Not Purchased</CardTitle>
            <CardDescription className="text-center">
              You need to purchase the {meta.title} module to access this dashboard.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button onClick={() => navigate('/')} className="w-full">
              Go to Home Page to Purchase
            </Button>
            <Button onClick={() => navigate('/company/dashboard')} variant="outline" className="w-full">
              Back to Dashboard
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  } else {
    content = (
      <ErrorBoundary>
        <Outlet />
      </ErrorBoundary>
    );
  }

  return (
    <>
      <Helmet><title>{meta.title} | Pay Per Project</title></Helmet>
      <div
        className="min-h-screen"
        style={{ background: 'linear-gradient(135deg, #020308 0%, #0a0a1a 25%, #0d0b1f 50%, #0f0a20 75%, #020308 100%)' }}
      >
        <DashboardNavbar
          icon={meta.icon}
          title={companyUser.companyName || meta.title}
          subtitle={companyUser.fullName}
          user={companyUser}
          userRole="Company User"
          showNavTabs
          activeSection={section}
          onLogout={handleLogout}
          navItems={getAgentNavItems(purchasedModules, section, navigate)}
          sidebarLoading={modulesLoading}
        />
        <main className="container mx-auto px-3 sm:px-4 py-4 sm:py-6 w-full max-w-full overflow-x-hidden">
          {content}
        </main>
      </div>
    </>
  );
};

export default AgentLayout;
