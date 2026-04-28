import React from 'react';
import { Mail } from 'lucide-react';
import SDRComingSoon from './SDRComingSoon';

const SDROutreachTab = () => (
  <SDRComingSoon
    icon={Mail}
    title="Outreach Campaigns"
    description="Create multi-step outreach sequences — Day 1 email, Day 3 LinkedIn, Day 5 follow-up, Day 10 last touch. AI generates all steps automatically."
    color="#06b6d4"
  />
);

export default SDROutreachTab;
