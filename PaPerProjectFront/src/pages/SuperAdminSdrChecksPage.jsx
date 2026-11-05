import React from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate } from 'react-router-dom';
import { FlaskConical } from 'lucide-react';
import DashboardNavbar from '@/components/common/DashboardNavbar';
import { getAdminNavItems } from '@/utils/adminNavItems';
import { useAuth } from '@/contexts/AuthContext';
import { GRADIENT_BG } from '@/components/admin/apiKeysShared';
import SDRChecksPanel from '@/components/ai-sdr/SDRChecksPanel';
import adminSdrChecksService from '@/services/adminSdrChecksService';

const SuperAdminSdrChecksPage = () => {
  const navigate = useNavigate();
  const { logout, user } = useAuth();

  const handleLogout = async () => {
    try {
      await logout();
      navigate('/login');
    } catch (error) {
      console.error('Logout error:', error);
    }
  };

  return (
    <>
      <Helmet><title>Super Admin — AI SDR Checks</title></Helmet>
      <div className="min-h-screen overflow-x-hidden" style={{ background: GRADIENT_BG }}>
        <DashboardNavbar
          icon={FlaskConical}
          title="AI SDR Checks"
          subtitle="Run the AI SDR's automated tests and see what passes"
          user={user}
          userRole="Admin"
          onLogout={handleLogout}
          showNavTabs
          activeSection="admin-sdr-checks"
          navItems={getAdminNavItems(navigate)}
        />
        <div className="container mx-auto px-4 py-8 max-w-7xl">
          <SDRChecksPanel api={adminSdrChecksService} />
        </div>
      </div>
    </>
  );
};

export default SuperAdminSdrChecksPage;
