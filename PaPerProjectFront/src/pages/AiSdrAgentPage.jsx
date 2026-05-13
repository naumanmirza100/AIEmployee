import React, { useState, useEffect } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate } from 'react-router-dom';
import { useToast } from '@/components/ui/use-toast';
import DashboardNavbar from '@/components/common/DashboardNavbar';
import SDRDashboard from '@/components/ai-sdr/SDRDashboard';
import usePurchasedModules from '@/hooks/usePurchasedModules';
import { getAgentNavItems } from '@/utils/agentNavItems';
import { Target, Loader2 } from 'lucide-react';

const AiSdrAgentPage = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [companyUser, setCompanyUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [hasAccess, setHasAccess] = useState(false);
  const [checkingAccess, setCheckingAccess] = useState(true);
  const [activeSection] = useState('ai-sdr');
  const { purchasedModules, modulesLoaded } = usePurchasedModules();

  useEffect(() => {
    const companyUserStr = localStorage.getItem('company_user');
    if (!companyUserStr) {
      toast({
        title: 'Not logged in',
        description: 'Please log in to access the AI SDR Agent',
        variant: 'destructive',
      });
      navigate('/company/login');
      return;
    }

    try {
      const user = JSON.parse(companyUserStr);
      setCompanyUser(user);
      checkModuleAccessForUser().finally(() => setLoading(false));
    } catch (error) {
      console.error('Error parsing company user:', error);
      localStorage.removeItem('company_user');
      navigate('/company/login');
      setLoading(false);
    }
  }, [navigate, toast]);

  const checkModuleAccessForUser = async () => {
    try {
      setCheckingAccess(true);
      // Always grant access — module gates handled by purchase flow
      setHasAccess(true);
    } catch (error) {
      setHasAccess(true);
    } finally {
      setCheckingAccess(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('company_auth_token');
    localStorage.removeItem('company_user');
    localStorage.removeItem('company_purchased_modules');
    navigate('/company/login');
  };

  if (loading || checkingAccess || !modulesLoaded) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!companyUser) return null;

  return (
    <>
      <Helmet>
        <title>AI SDR Agent | Pay Per Project</title>
      </Helmet>
      <div
        className="min-h-screen"
        style={{
          background: 'linear-gradient(135deg, #020308 0%, #0a0a1a 25%, #0d0b1f 50%, #0f0a20 75%, #020308 100%)',
        }}
      >
        <DashboardNavbar
          icon={Target}
          title={companyUser.companyName || 'AI SDR Agent'}
          subtitle={companyUser.fullName}
          user={companyUser}
          userRole="Company User"
          showNavTabs={true}
          activeSection={activeSection}
          onLogout={handleLogout}
          navItems={getAgentNavItems(purchasedModules, 'ai-sdr', navigate)}
        />

        <div className="container mx-auto px-6 sm:px-10 lg:px-16 xl:px-20 py-4 sm:py-8 max-w-full overflow-x-hidden">
          <SDRDashboard />
        </div>
      </div>
    </>
  );
};

export default AiSdrAgentPage;
