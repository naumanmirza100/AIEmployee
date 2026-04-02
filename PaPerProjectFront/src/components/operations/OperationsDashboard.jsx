import React, { useState, useEffect, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  FileText, BarChart3, MessageSquareText, PenTool, Bell,
  Upload, TrendingUp, Hash, Tag, Loader2, LayoutDashboard,
  Menu, Check, ArrowUpRight,
} from 'lucide-react';
import * as operationsService from '@/services/operationsAgentService';

// Tab components
import DocumentProcessing from './DocumentProcessing';
import DocumentDetailPage from './DocumentDetailPage';
import SummarizationInsights from './SummarizationInsights';
import AnalyticsDashboardTab from './AnalyticsDashboardTab';
import KnowledgeQA from './KnowledgeQA';
import DocumentAuthoring from './DocumentAuthoring';
import ProactiveNotifications from './ProactiveNotifications';

const TAB_ITEMS = [
  { value: 'dashboard',      icon: LayoutDashboard,   label: 'Dashboard' },
  { value: 'documents',      icon: Upload,            label: 'Documents' },
  { value: 'summarization',  icon: FileText,          label: 'Summarization' },
  { value: 'analytics',      icon: BarChart3,         label: 'Analytics' },
  { value: 'knowledge-qa',   icon: MessageSquareText, label: 'Knowledge Q&A' },
  { value: 'authoring',      icon: PenTool,           label: 'Authoring' },
  { value: 'notifications',  icon: Bell,              label: 'Notifications' },
];

const PATH_TO_TAB = {
  dashboard: 'dashboard',
  documents: 'documents',
  summarization: 'summarization',
  analytics: 'analytics',
  'knowledge-qa': 'knowledge-qa',
  authoring: 'authoring',
  notifications: 'notifications',
};

const TAB_TO_PATH = {
  'dashboard': 'dashboard',
  'documents': 'documents',
  'summarization': 'summarization',
  'analytics': 'analytics',
  'knowledge-qa': 'knowledge-qa',
  'authoring': 'authoring',
  'notifications': 'notifications',
};

const OperationsDashboard = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const pathSegment = (location.pathname.match(/\/operations\/?([^/]*)/) || [])[1] || 'dashboard';
  const docDetailMatch = location.pathname.match(/\/operations\/documents\/(\d+)/);
  const activeTab = docDetailMatch ? 'documents' : (PATH_TO_TAB[pathSegment] || 'dashboard');
  const currentTab = TAB_ITEMS.find(item => item.value === activeTab) || TAB_ITEMS[0];

  const [stats, setStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(true);

  const handleTabChange = (tab) => {
    navigate(`/operations/${TAB_TO_PATH[tab] || 'dashboard'}`);
  };

  const fetchStats = useCallback(async () => {
    try {
      setStatsLoading(true);
      const res = await operationsService.getDashboardStats();
      if (res.status === 'success') setStats(res.stats);
    } catch (e) {
      console.error('Stats fetch error:', e);
    } finally {
      setStatsLoading(false);
    }
  }, []);

  useEffect(() => { fetchStats(); }, [fetchStats]);

  // If on document detail page, render that instead
  if (docDetailMatch) {
    return <DocumentDetailPage />;
  }

  const statCards = [
    { label: 'Total Documents', value: stats?.total_documents ?? '-', icon: FileText, color: '#3b82f6', gradient: 'from-blue-500/10 to-blue-600/5' },
    { label: 'Processed', value: stats?.processed_documents ?? '-', icon: TrendingUp, color: '#10b981', gradient: 'from-emerald-500/10 to-emerald-600/5' },
    { label: 'Text Chunks', value: stats?.total_chunks ?? '-', icon: Hash, color: '#8b5cf6', gradient: 'from-violet-500/10 to-violet-600/5' },
    { label: 'Doc Types', value: stats?.document_types ? Object.keys(stats.document_types).length : '-', icon: Tag, color: '#f59e0b', gradient: 'from-amber-500/10 to-amber-600/5' },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white">Operations Agent</h1>
        <p className="text-gray-400 mt-1">Internal ops & analysis workhorse for documents and metrics</p>
      </div>

      {/* Stats Cards - always visible */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        {statCards.map((s, i) => (
          <Card key={i} className={`bg-gradient-to-br ${s.gradient} border-white/[0.06] backdrop-blur-sm`}>
            <CardContent className="p-4 sm:p-5 flex items-center gap-3 sm:gap-4">
              <div className="flex items-center justify-center w-10 h-10 sm:w-12 sm:h-12 rounded-xl" style={{ backgroundColor: `${s.color}15` }}>
                <s.icon className="h-5 w-5 sm:h-6 sm:w-6" style={{ color: s.color }} />
              </div>
              <div>
                <p className="text-xl sm:text-2xl font-bold text-white">
                  {statsLoading ? <Loader2 className="h-5 w-5 animate-spin text-gray-500" /> : s.value}
                </p>
                <p className="text-xs sm:text-sm text-gray-400">{s.label}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Main Tabs - each tab navigates to its URL */}
      <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
        {/* Mobile & Tablet: Hamburger Menu (below lg) */}
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
            <DropdownMenuContent align="start" className="w-[calc(100vw-2rem)] max-h-[60vh] overflow-y-auto">
              {TAB_ITEMS.map((item) => {
                const isActive = item.value === activeTab;
                return (
                  <DropdownMenuItem
                    key={item.value}
                    onClick={() => handleTabChange(item.value)}
                    className={`flex items-center justify-between py-3 cursor-pointer ${
                      isActive ? 'bg-primary/10' : ''
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <item.icon className={`h-4 w-4 ${isActive ? 'text-primary' : 'text-muted-foreground'}`} />
                      <span className={isActive ? 'font-medium text-primary' : ''}>{item.label}</span>
                    </div>
                    {isActive && <Check className="h-4 w-4 text-primary" />}
                  </DropdownMenuItem>
                );
              })}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {/* Desktop: Regular Tabs (lg and above) with horizontal scroll */}
        <div className="hidden lg:block overflow-x-auto pb-1">
          <TabsList
            className="inline-flex w-max min-w-full h-auto p-1 gap-1 rounded-lg bg-[#1a1333] border border-[#3a295a]"
            style={{ boxShadow: '0 2px 12px 0 #a259ff0a' }}
          >
            {TAB_ITEMS.map((item) => (
              <TabsTrigger
                key={item.value}
                value={item.value}
                className="whitespace-nowrap shrink-0 px-4 py-2 text-sm font-medium rounded-md border transition-all duration-150"
                style={activeTab === item.value
                  ? {
                      background: 'linear-gradient(90deg, #f59e0b 0%, #f97316 100%)',
                      color: '#fff',
                      border: '1.5px solid #f59e0b',
                      boxShadow: '0 0 8px 0 #f59e0b55',
                    }
                  : {
                      background: 'rgba(60, 30, 90, 0.22)',
                      color: '#cfc6e6',
                      border: '1.5px solid #2d2342',
                      boxShadow: 'none',
                    }
                }
              >
                <item.icon className="h-4 w-4 mr-2" />
                {item.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>

        <TabsContent value="dashboard" className="space-y-5 mt-2">
          {/* Quick Actions */}
          <div>
            <h3 className="text-sm font-semibold text-white/70 uppercase tracking-wider mb-3 flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-amber-400" />
              Quick Actions
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 w-full max-w-full">
              {[
                {
                  label: 'Upload Documents',
                  desc: 'Upload and process your documents',
                  icon: Upload,
                  tab: 'documents',
                  color: '#3b82f6',
                  bgColor: 'rgba(59,130,246,0.15)',
                  borderHover: 'rgba(59,130,246,0.4)',
                },
                {
                  label: 'Summarization',
                  desc: 'Get AI-powered document summaries',
                  icon: FileText,
                  tab: 'summarization',
                  color: '#10b981',
                  bgColor: 'rgba(16,185,129,0.15)',
                  borderHover: 'rgba(16,185,129,0.4)',
                },
                {
                  label: 'Analytics',
                  desc: 'View document analytics and insights',
                  icon: BarChart3,
                  tab: 'analytics',
                  color: '#8b5cf6',
                  bgColor: 'rgba(139,92,246,0.15)',
                  borderHover: 'rgba(139,92,246,0.4)',
                },
                {
                  label: 'Knowledge Q&A',
                  desc: 'Ask questions about your documents',
                  icon: MessageSquareText,
                  tab: 'knowledge-qa',
                  color: '#f59e0b',
                  bgColor: 'rgba(245,158,11,0.15)',
                  borderHover: 'rgba(245,158,11,0.4)',
                },
                {
                  label: 'Authoring',
                  desc: 'Create and edit documents with AI',
                  icon: PenTool,
                  tab: 'authoring',
                  color: '#ec4899',
                  bgColor: 'rgba(236,72,153,0.15)',
                  borderHover: 'rgba(236,72,153,0.4)',
                },
                {
                  label: 'Notifications',
                  desc: 'View proactive alerts and updates',
                  icon: Bell,
                  tab: 'notifications',
                  color: '#06b6d4',
                  bgColor: 'rgba(6,182,212,0.15)',
                  borderHover: 'rgba(6,182,212,0.4)',
                },
              ].map((action) => (
                <button
                  key={action.tab}
                  onClick={() => handleTabChange(action.tab)}
                  className="group flex items-center gap-4 rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 text-left transition-all hover:border-white/[0.12] hover:bg-white/[0.04]"
                >
                  <div
                    className="flex items-center justify-center w-10 h-10 rounded-lg shrink-0"
                    style={{ backgroundColor: action.bgColor }}
                  >
                    <action.icon className="h-5 w-5" style={{ color: action.color }} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-white">{action.label}</p>
                    <p className="text-xs text-gray-400 truncate">{action.desc}</p>
                  </div>
                  <ArrowUpRight className="h-4 w-4 text-gray-500 opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
                </button>
              ))}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="documents" className="mt-6">
          <DocumentProcessing />
        </TabsContent>

        <TabsContent value="summarization" className="mt-6">
          <SummarizationInsights />
        </TabsContent>

        <TabsContent value="analytics" className="mt-6">
          <AnalyticsDashboardTab />
        </TabsContent>

        <TabsContent value="knowledge-qa" className="mt-6">
          <KnowledgeQA />
        </TabsContent>

        <TabsContent value="authoring" className="mt-6">
          <DocumentAuthoring />
        </TabsContent>

        <TabsContent value="notifications" className="mt-6">
          <ProactiveNotifications />
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default OperationsDashboard;
