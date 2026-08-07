import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  LayoutDashboard, Users, Mail, Calendar, BarChart3,
  RefreshCw, Menu, Check, Settings,
} from 'lucide-react';

import SDROverviewTab from './SDROverviewTab';
import SDRLeadsTab from './SDRLeadsTab';
import SDROutreachTab from './SDROutreachTab';
import SDRMeetingsTab from './SDRMeetingsTab';
import SDRAnalyticsTab from './SDRAnalyticsTab';
import SDRCRMSyncTab from './SDRCRMSyncTab';
import SDRSettingsTab from './SDRSettingsTab';

const TAB_ITEMS = [
  { value: 'dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { value: 'leads',     icon: Users,           label: 'Leads' },
  { value: 'outreach',  icon: Mail,            label: 'Outreach' },
  { value: 'meetings',  icon: Calendar,        label: 'Meetings' },
  { value: 'analytics', icon: BarChart3,       label: 'Analytics' },
  { value: 'crm-sync',  icon: RefreshCw,       label: 'CRM Sync' },
  { value: 'settings',  icon: Settings,        label: 'Settings' },
];

const PATH_TO_TAB = {
  dashboard: 'dashboard',
  leads:     'leads',
  outreach:  'outreach',
  meetings:  'meetings',
  analytics: 'analytics',
  'crm-sync':'crm-sync',
  settings:  'settings',
};

const TAB_TO_PATH = {
  dashboard: 'dashboard',
  leads:     'leads',
  outreach:  'outreach',
  meetings:  'meetings',
  analytics: 'analytics',
  'crm-sync':'crm-sync',
  settings:  'settings',
};

const SDRDashboard = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const pathSegment = (location.pathname.match(/\/ai-sdr\/?([^/]*)/) || [])[1] || 'dashboard';
  const activeTab = PATH_TO_TAB[pathSegment] || 'dashboard';
  const currentTab = TAB_ITEMS.find(item => item.value === activeTab) || TAB_ITEMS[0];

  const handleTabChange = (tab) => {
    navigate(`/ai-sdr/${TAB_TO_PATH[tab] || 'dashboard'}`);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white">AI SDR Agent</h1>
        <p className="text-gray-400 mt-1">Automated sales development — leads, outreach, meetings, and analytics</p>
      </div>

      {/* Tabs — the tab BAR now lives in the left sidebar; this keeps the
          URL-driven content switching. */}
      <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">


        <TabsContent value="dashboard" className="mt-4">
          <SDROverviewTab />
        </TabsContent>
        <TabsContent value="leads" className="mt-4">
          <SDRLeadsTab />
        </TabsContent>
        <TabsContent value="outreach" className="mt-4">
          <SDROutreachTab />
        </TabsContent>
        <TabsContent value="meetings" className="mt-4">
          <SDRMeetingsTab />
        </TabsContent>
        <TabsContent value="analytics" className="mt-4">
          <SDRAnalyticsTab />
        </TabsContent>
        <TabsContent value="crm-sync" className="mt-4">
          <SDRCRMSyncTab />
        </TabsContent>
        <TabsContent value="settings" className="mt-4">
          <SDRSettingsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default SDRDashboard;
