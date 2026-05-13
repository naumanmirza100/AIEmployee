import React from 'react';
import { Sparkles } from 'lucide-react';
import SDRComingSoon from './SDRComingSoon';

const SDREmailAssistantTab = () => (
  <SDRComingSoon
    icon={Sparkles}
    title="AI Email Assistant"
    description="Pick a template, set the tone (Professional / Friendly / Direct), fill in prospect details, and get a fully personalized outreach email in seconds."
    color="#ec4899"
  />
);

export default SDREmailAssistantTab;
