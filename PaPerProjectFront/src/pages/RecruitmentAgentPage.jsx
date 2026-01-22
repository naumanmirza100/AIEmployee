import React, { useState, useEffect } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate } from 'react-router-dom';
import { useToast } from '@/components/ui/use-toast';
import DashboardNavbar from '@/components/common/DashboardNavbar';
import RecruitmentDashboard from '@/components/recruitment/RecruitmentDashboard';
import { 
  UserCheck, 
  Building2, 
  BrainCircuit, 
  Megaphone,
  Loader2
} from 'lucide-react';

const RecruitmentAgentPage = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [companyUser, setCompanyUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeSection, setActiveSection] = useState('recruitment');

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
    } catch (error) {
      console.error('Error parsing company user:', error);
      localStorage.removeItem('company_user');
      navigate('/company/login');
    } finally {
      setLoading(false);
    }
  }, [navigate, toast]);

  const handleLogout = () => {
    localStorage.removeItem('company_auth_token');
    localStorage.removeItem('company_user');
    navigate('/company/login');
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!companyUser) {
    return null;
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
            {
              label: 'Project Manager Agent',
              icon: BrainCircuit,
              section: 'project-manager',
              onClick: () => navigate('/project-manager/dashboard'),
            },
            {
              label: 'Recruitment Agent',
              icon: UserCheck,
              section: 'recruitment',
              onClick: () => navigate('/recruitment/dashboard'),
            },
            {
              label: 'Marketing Agent',
              icon: Megaphone,
              section: 'marketing',
              onClick: () => navigate('/marketing/dashboard'),
            },
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

