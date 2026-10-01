import React, { useMemo } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate } from 'react-router-dom';
import { ChevronLeft, ListChecks } from 'lucide-react';

import DashboardNavbar from '@/components/common/DashboardNavbar';
import MyWorkList from '@/components/common/MyWorkList';
import usePurchasedModules from '@/hooks/usePurchasedModules';
import { getAgentNavItems } from '@/utils/agentNavItems';
import { getCompanyUser, logoutCompany } from '@/services/companyAuthService';

/**
 * /my-work — "My work" for a dashboard login, reached from the navbar.
 * Employee logins have the same list at /me/work, inside My Space.
 */
export default function MyWorkPage() {
  const navigate = useNavigate();
  const { purchasedModules, modulesLoaded } = usePurchasedModules();
  const companyUser = useMemo(() => getCompanyUser(), []);

  const handleLogout = async () => {
    await logoutCompany();
    navigate('/company/login');
  };

  return (
    <>
      <Helmet><title>My work — AIEmployee</title></Helmet>
      <div className="min-h-screen overflow-x-hidden" style={{ background: 'var(--app-page-bg)' }}>
        <DashboardNavbar
          icon={ListChecks}
          title="My work"
          subtitle="What's waiting for you in every agent"
          user={companyUser}
          userRole="Company User"
          onLogout={handleLogout}
          showNavTabs
          activeSection="dashboard"
          navItems={getAgentNavItems(purchasedModules, 'dashboard', navigate)}
          sidebarLoading={!modulesLoaded}
        />
        <div className="container mx-auto max-w-4xl px-4 py-8">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ChevronLeft className="h-4 w-4" /> Back
          </button>
          <MyWorkList />
        </div>
      </div>
    </>
  );
}
