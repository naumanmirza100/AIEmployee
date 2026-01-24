import React, { useState, useEffect } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate } from 'react-router-dom';
import { useToast } from '@/components/ui/use-toast';
import DashboardNavbar from '@/components/common/DashboardNavbar';
import RecruitmentDashboard from '@/components/recruitment/RecruitmentDashboard';
import { checkModuleAccess, getPurchasedModules } from '@/services/modulePurchaseService';
import { 
  UserCheck, 
  Building2, 
  BrainCircuit, 
  Megaphone,
  Loader2,
  Lock
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

const RecruitmentAgentPage = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [companyUser, setCompanyUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [hasAccess, setHasAccess] = useState(false);
  const [checkingAccess, setCheckingAccess] = useState(true);
  const [activeSection, setActiveSection] = useState('recruitment');
  const [purchasedModules, setPurchasedModules] = useState([]);
  const [modulesLoaded, setModulesLoaded] = useState(false);

  useEffect(() => {
    // Get company user from localStorage
    const companyUserStr = localStorage.getItem('company_user');
    if (!companyUserStr) {
      toast({
        title: 'Not logged in',
        description: 'Please log in to access the recruitment agent',
        variant: 'destructive',
      });
      navigate('/company/login');
      return;
    }
    
    try {
      const user = JSON.parse(companyUserStr);
      setCompanyUser(user);
      
      // Load cached modules immediately
      const cachedModules = localStorage.getItem('company_purchased_modules');
      if (cachedModules) {
        try {
          const cached = JSON.parse(cachedModules);
          setPurchasedModules(cached);
          setModulesLoaded(true);
        } catch (e) {
          // Invalid cache
        }
      }
      
      // Check module access and fetch purchased modules (will update cache)
      Promise.all([
        checkModuleAccessForUser(),
        fetchPurchasedModules()
      ]).finally(() => {
        setLoading(false);
      });
    } catch (error) {
      console.error('Error parsing company user:', error);
      localStorage.removeItem('company_user');
      navigate('/company/login');
      setLoading(false);
    }
  }, [navigate, toast]);

  const fetchPurchasedModules = async () => {
    try {
      // Try to get from localStorage first (cache)
      const cachedModules = localStorage.getItem('company_purchased_modules');
      if (cachedModules) {
        try {
          const cached = JSON.parse(cachedModules);
          setPurchasedModules(cached);
          setModulesLoaded(true);
        } catch (e) {
          // Invalid cache, continue to fetch
        }
      }

      const response = await getPurchasedModules();
      if (response.status === 'success') {
        const moduleNames = response.module_names || [];
        setPurchasedModules(moduleNames);
        // Cache in localStorage
        localStorage.setItem('company_purchased_modules', JSON.stringify(moduleNames));
        setModulesLoaded(true);
      } else {
        setModulesLoaded(true);
      }
    } catch (error) {
      console.error('Error fetching purchased modules:', error);
      // If we have cached modules, use them
      const cachedModules = localStorage.getItem('company_purchased_modules');
      if (cachedModules) {
        try {
          const cached = JSON.parse(cachedModules);
          setPurchasedModules(cached);
        } catch (e) {
          setPurchasedModules([]);
        }
      } else {
        setPurchasedModules([]);
      }
      setModulesLoaded(true);
    }
  };

  const checkModuleAccessForUser = async () => {
    try {
      setCheckingAccess(true);
      const response = await checkModuleAccess('recruitment_agent');
      if (response.status === 'success') {
        setHasAccess(response.has_access);
        if (!response.has_access) {
          toast({
            title: 'Module Not Purchased',
            description: 'Please purchase the Recruitment Agent module to access this dashboard',
            variant: 'default',
          });
        }
      }
    } catch (error) {
      console.error('Error checking module access:', error);
      // On error, allow access (graceful degradation)
      setHasAccess(true);
    } finally {
      setCheckingAccess(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('company_auth_token');
    localStorage.removeItem('company_user');
    navigate('/company/login');
  };

  if (loading || checkingAccess || !modulesLoaded) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!companyUser) {
    return null;
  }

  // Show access denied if module not purchased
  if (!hasAccess) {
    return (
      <>
        <Helmet>
          <title>Access Denied | Pay Per Project</title>
        </Helmet>
        <div className="min-h-screen bg-background flex items-center justify-center p-4">
          <Card className="max-w-md w-full">
            <CardHeader>
              <div className="flex items-center justify-center mb-4">
                <Lock className="h-12 w-12 text-muted-foreground" />
              </div>
              <CardTitle className="text-center">Module Not Purchased</CardTitle>
              <CardDescription className="text-center">
                You need to purchase the Recruitment Agent module to access this dashboard.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Button 
                onClick={() => navigate('/')} 
                className="w-full"
              >
                Go to Home Page to Purchase
              </Button>
              <Button 
                onClick={() => navigate('/company/dashboard')} 
                variant="outline"
                className="w-full"
              >
                Back to Dashboard
              </Button>
            </CardContent>
          </Card>
        </div>
      </>
    );
  }

  return (
    <>
      <Helmet>
        <title>Recruitment Agent | Pay Per Project</title>
      </Helmet>
      <div className="min-h-screen bg-background">
        {/* Header */}
        <DashboardNavbar
          icon={UserCheck}
          title={companyUser.companyName || 'Recruitment Agent'}
          subtitle={companyUser.fullName}
          user={companyUser}
          userRole="Company User"
          showNavTabs={true}
          activeSection={activeSection}
          onLogout={handleLogout}
          navItems={[
            {
              label: 'Dashboard',
              icon: Building2,
              section: 'dashboard',
              onClick: () => navigate('/company/dashboard'),
            },
            // Only show Project Manager Agent if purchased
            ...(purchasedModules.includes('project_manager_agent') ? [{
              label: 'Project Manager Agent',
              icon: BrainCircuit,
              section: 'project-manager',
              onClick: () => navigate('/project-manager/dashboard'),
            }] : []),
            {
              label: 'Recruitment Agent',
              icon: UserCheck,
              section: 'recruitment',
              onClick: () => navigate('/recruitment/dashboard'),
            },
            // Show Marketing Agent if purchased (always show current page's module)
            ...(purchasedModules.includes('marketing_agent') ? [{
              label: 'Marketing Agent',
              icon: Megaphone,
              section: 'marketing',
              onClick: () => navigate('/marketing/dashboard'),
            }] : []),
          ]}
        />

        <div className="container mx-auto px-4 py-8">
          <RecruitmentDashboard />
        </div>
      </div>
    </>
  );
};

export default RecruitmentAgentPage;

