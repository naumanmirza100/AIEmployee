import React from 'react';
import { RefreshCw } from 'lucide-react';
import SDRComingSoon from './SDRComingSoon';

const SDRCRMSyncTab = () => (
  <SDRComingSoon
    icon={RefreshCw}
    title="CRM & System Sync"
    description="Automatically saves leads, logs emails, and records meetings to your CRM — HubSpot, Salesforce, Pipedrive and more. Every agent always works on up-to-date information."
    color="#06b6d4"
  />
);

export default SDRCRMSyncTab;
