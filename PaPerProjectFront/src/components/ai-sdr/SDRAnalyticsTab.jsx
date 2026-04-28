import React from 'react';
import { BarChart3 } from 'lucide-react';
import SDRComingSoon from './SDRComingSoon';

const SDRAnalyticsTab = () => (
  <SDRComingSoon
    icon={BarChart3}
    title="Analytics & Pipeline"
    description="Full pipeline funnel from lead to close, weekly email performance charts, Hot / Warm / Cold breakdown, and conversion rate tracking."
    color="#f59e0b"
  />
);

export default SDRAnalyticsTab;
