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
  Sparkles, RefreshCw, Menu, Check,
} from 'lucide-react';

import SDROverviewTab from './SDROverviewTab';
import SDRLeadsTab from './SDRLeadsTab';
import SDROutreachTab from './SDROutreachTab';
import SDRMeetingsTab from './SDRMeetingsTab';
import SDRAnalyticsTab from './SDRAnalyticsTab';
import SDREmailAssistantTab from './SDREmailAssistantTab';
import SDRCRMSyncTab from './SDRCRMSyncTab';

const TAB_ITEMS = [
  { value: 'dashboard',        icon: LayoutDashboard, label: 'Dashboard' },
  { value: 'leads',            icon: Users,           label: 'Leads' },
  { value: 'outreach',         icon: Mail,            label: 'Outreach' },
  { value: 'meetings',         icon: Calendar,        label: 'Meetings' },
  { value: 'analytics',        icon: BarChart3,       label: 'Analytics' },
  { value: 'email-assistant',  icon: Sparkles,        label: 'Email Assistant' },
  { value: 'crm-sync',         icon: RefreshCw,       label: 'CRM Sync' },
];

const PATH_TO_TAB = {
  dashboard:         'dashboard',
  leads:             'leads',
  outreach:          'outreach',
  meetings:          'meetings',
  analytics:         'analytics',
  'email-assistant': 'email-assistant',
  'crm-sync':        'crm-sync',
};

const TAB_TO_PATH = {
  'dashboard':       'dashboard',
  'leads':           'leads',
  'outreach':        'outreach',
  'meetings':        'meetings',
  'analytics':       'analytics',
  'email-assistant': 'email-assistant',
  'crm-sync':        'crm-sync',
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

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">

        {/* Mobile: Dropdown */}
        <div className="lg:hidden">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" className="w-full justify-between h-11">
                <div className="flex items-center gap-2">
                  <currentTab.icon className="h-4 w-4" />
                  <span className="font-medium">{currentTab.label}</span>
                </div>
                <Menu className="h-5 w-5 text-muted-foreground" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-[calc(100vw-2rem)]">
              {TAB_ITEMS.map((item) => (
                <DropdownMenuItem
                  key={item.value}
                  onClick={() => handleTabChange(item.value)}
                  className={`flex items-center justify-between py-3 cursor-pointer ${item.value === activeTab ? 'bg-primary/10' : ''}`}
                >
                  <div className="flex items-center gap-3">
                    <item.icon className={`h-4 w-4 ${item.value === activeTab ? 'text-primary' : 'text-muted-foreground'}`} />
                    <span className={item.value === activeTab ? 'font-medium text-primary' : ''}>{item.label}</span>
                  </div>
                  {item.value === activeTab && <Check className="h-4 w-4 text-primary" />}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {/* Desktop: Tab Bar */}
        <div className="hidden lg:block overflow-x-auto pb-1">
          <TabsList
            className="inline-flex w-max min-w-full h-auto p-1 gap-1 rounded-lg"
            style={{ background: '#0f0a1f', border: '1px solid #2d1f4a', boxShadow: '0 2px 12px 0 #a259ff0a' }}
          >
            {TAB_ITEMS.map((item) => (
              <TabsTrigger
                key={item.value}
                value={item.value}
                className="whitespace-nowrap shrink-0 px-4 py-2 text-sm font-medium rounded-md border transition-all duration-150 flex items-center gap-2"
                style={activeTab === item.value
                  ? {
                      background: 'linear-gradient(90deg, #f43f5e 0%, #a855f7 100%)',
                      color: '#fff',
                      border: '1.5px solid #f43f5e',
                      boxShadow: '0 0 10px 0 #f43f5e55',
                    }
                  : {
                      background: 'rgba(60, 20, 80, 0.22)',
                      color: '#cfc6e6',
                      border: '1.5px solid #2d1f4a',
                      boxShadow: 'none',
                    }
                }
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>

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
        <TabsContent value="email-assistant" className="mt-4">
          <SDREmailAssistantTab />
        </TabsContent>
        <TabsContent value="crm-sync" className="mt-4">
          <SDRCRMSyncTab />
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default SDRDashboard;
