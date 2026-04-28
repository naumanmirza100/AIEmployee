import React from 'react';
import { Users } from 'lucide-react';
import SDRComingSoon from './SDRComingSoon';

const SDRLeadsTab = () => (
  <SDRComingSoon
    icon={Users}
    title="Lead Management"
    description="AI-powered lead database with Hot / Warm / Cold scoring, search & filter, add leads manually or via CSV import, and one-click AI scoring."
    color="#f43f5e"
  />
);

export default SDRLeadsTab;
