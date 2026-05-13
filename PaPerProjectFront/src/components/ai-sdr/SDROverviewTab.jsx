import React from 'react';
import { LayoutDashboard } from 'lucide-react';
import SDRComingSoon from './SDRComingSoon';

const SDROverviewTab = () => (
  <SDRComingSoon
    icon={LayoutDashboard}
    title="Dashboard Overview"
    description="Your AI SDR command center is being built. KPI cards, top leads, quick actions, and real-time pipeline activity will appear here."
    color="#a855f7"
  />
);

export default SDROverviewTab;
