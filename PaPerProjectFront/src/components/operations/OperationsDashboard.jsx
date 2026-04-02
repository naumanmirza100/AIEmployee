import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  FileText, BarChart3, MessageSquare, PenTool, Bell,
  Upload, TrendingUp, Hash, Tag, Loader2,
} from 'lucide-react';
import * as operationsService from '@/services/operationsAgentService';

// Tab components
import DocumentProcessing from './DocumentProcessing';
import SummarizationInsights from './SummarizationInsights';
import AnalyticsDashboardTab from './AnalyticsDashboardTab';
import KnowledgeQA from './KnowledgeQA';
import DocumentAuthoring from './DocumentAuthoring';
import ProactiveNotifications from './ProactiveNotifications';

const TAB_CONFIG = [
  { value: 'documents',      icon: Upload,            label: 'Documents' },
  { value: 'summarization',  icon: FileText,          label: 'Summarization' },
  { value: 'analytics',      icon: BarChart3,         label: 'Analytics' },
  { value: 'knowledge-qa',   icon: MessageSquare, label: 'Knowledge Q&A' },
  { value: 'authoring',      icon: PenTool,           label: 'Authoring' },
  { value: 'notifications',  icon: Bell,              label: 'Notifications' },
];

const OperationsDashboard = () => {
  const [activeTab, setActiveTab] = useState('documents');
  const [stats, setStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(true);

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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white">Operations Agent</h1>
        <p className="text-gray-400 mt-1">Internal ops & analysis workhorse for documents and metrics</p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        {[
          { label: 'Total Documents', value: stats?.total_documents ?? '-', icon: FileText, color: '#3b82f6', gradient: 'from-blue-500/10 to-blue-600/5' },
          { label: 'Processed', value: stats?.processed_documents ?? '-', icon: TrendingUp, color: '#10b981', gradient: 'from-emerald-500/10 to-emerald-600/5' },
          { label: 'Text Chunks', value: stats?.total_chunks ?? '-', icon: Hash, color: '#8b5cf6', gradient: 'from-violet-500/10 to-violet-600/5' },
          { label: 'Doc Types', value: stats?.document_types ? Object.keys(stats.document_types).length : '-', icon: Tag, color: '#f59e0b', gradient: 'from-amber-500/10 to-amber-600/5' },
        ].map((s, i) => (
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

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="bg-[#1a1333] border border-[#3a295a] rounded-xl p-1 flex gap-1 h-auto flex-wrap" style={{ boxShadow: '0 2px 12px 0 #a259ff0a' }}>
          {TAB_CONFIG.map(({ value, icon: TabIcon, label }) => (
            <TabsTrigger
              key={value}
              value={value}
              className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-all border"
              style={activeTab === value
                ? { background: 'linear-gradient(90deg, #f59e0b 0%, #f97316 100%)', color: '#fff', border: '1.5px solid #f59e0b', boxShadow: '0 0 8px 0 #f59e0b55' }
                : { background: 'rgba(60,30,90,0.22)', color: '#cfc6e6', border: '1.5px solid #2d2342' }
              }
            >
              <TabIcon className="h-4 w-4" />
              {label}
            </TabsTrigger>
          ))}
        </TabsList>

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
