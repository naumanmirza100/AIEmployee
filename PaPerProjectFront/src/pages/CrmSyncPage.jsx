import React, { useEffect, useMemo, useState } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate } from 'react-router-dom';
import { Loader2, Lock, RefreshCw } from 'lucide-react';

import DashboardNavbar from '@/components/common/DashboardNavbar';
import SDRCRMSyncTab from '@/components/ai-sdr/SDRCRMSyncTab';
import { Button } from '@/components/ui/button';
import usePurchasedModules from '@/hooks/usePurchasedModules';
import { getCompanyUser, logoutCompany } from '@/services/companyAuthService';
import { getAgentNavItems } from '@/utils/agentNavItems';

/**
 * /crm-sync — CRM Sync as the agent of its own that it is priced and
 * access-checked as. Its only screen used to be a tab inside AI SDR, shown to
 * every AI SDR customer whether or not they had bought it (connecting a CRM
 * then failed), and unreachable for a company that bought CRM Sync alone.
 */
export default function CrmSyncPage() {
  const navigate = useNavigate();
  const { purchasedModules, modulesLoaded } = usePurchasedModules();
  const companyUser = useMemo(() => getCompanyUser(), []);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!companyUser) navigate('/company/login');
    else setReady(true);
  }, [companyUser, navigate]);

  const handleLogout = async () => {
    await logoutCompany();
    navigate('/company/login');
  };

  if (!ready || !modulesLoaded) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  const bought = purchasedModules.includes('crm_sync_agent');

  return (
    <>
      <Helmet><title>CRM Sync | Pay Per Project</title></Helmet>
      <div className="min-h-screen overflow-x-hidden" style={{ background: 'var(--app-page-bg)' }}>
        <DashboardNavbar
          icon={RefreshCw}
          title="CRM Sync"
          subtitle="Keep your CRM up to date with what the agents do"
          user={companyUser}
          userRole="Company User"
          onLogout={handleLogout}
          showNavTabs
          activeSection="crm-sync"
          navItems={getAgentNavItems(purchasedModules, 'crm-sync', navigate)}
        />
        <div className="container mx-auto px-4 sm:px-10 py-6 max-w-full">
          {bought ? <SDRCRMSyncTab /> : (
            <div className="mx-auto mt-10 max-w-md rounded-xl border border-border bg-[var(--panel-2)] p-6 text-center">
              <Lock className="mx-auto mb-3 h-10 w-10 text-muted-foreground" />
              <h1 className="text-lg font-semibold text-foreground">CRM Sync is not part of your plan</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                It sends contacts, emails, replies and meetings to HubSpot, Salesforce or Pipedrive.
              </p>
              <Button className="mt-4 w-full" onClick={() => navigate('/company/dashboard/ai-agents')}>
                See AI agents
              </Button>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
