import React from 'react';
import { Calendar } from 'lucide-react';
import SDRComingSoon from './SDRComingSoon';

const SDRMeetingsTab = () => (
  <SDRComingSoon
    icon={Calendar}
    title="Meeting Scheduler"
    description="Book discovery calls, get AI-generated meeting prep notes, track upcoming and past meetings, and update meeting status with one click."
    color="#10b981"
  />
);

export default SDRMeetingsTab;
