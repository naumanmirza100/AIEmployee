import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import {
  FileText,
  BarChart3,
  MessageSquareText,
  PenTool,
  Bell,
  Search,
  Upload,
  TrendingUp
} from 'lucide-react';

const OperationsDashboard = () => {
  const agents = [
    {
      title: 'Document Processing',
      description: 'Upload and parse PDFs, Word docs, Excel sheets, and more. Auto-extract text, tables, and metadata.',
      icon: Upload,
      color: '#3b82f6',
      status: 'Coming Soon',
    },
    {
      title: 'Summarization & Insights',
      description: 'Generate executive summaries, extract key findings, action items, and compare documents.',
      icon: FileText,
      color: '#8b5cf6',
      status: 'Coming Soon',
    },
    {
      title: 'Analytics & Dashboard',
      description: 'Aggregate metrics from documents, detect trends and anomalies, build visual dashboards.',
      icon: BarChart3,
      color: '#10b981',
      status: 'Coming Soon',
    },
    {
      title: 'Knowledge Q&A',
      description: 'Ask questions about your documents and get answers with source citations.',
      icon: MessageSquareText,
      color: '#f59e0b',
      status: 'Coming Soon',
    },
    {
      title: 'Document Authoring',
      description: 'Generate reports, memos, proposals, and executive briefs using your documents as reference.',
      icon: PenTool,
      color: '#ec4899',
      status: 'Coming Soon',
    },
    {
      title: 'Proactive Notifications',
      description: 'Get alerted on metric anomalies, threshold breaches, and document activity digests.',
      icon: Bell,
      color: '#ef4444',
      status: 'Coming Soon',
    },
  ];

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white mb-2">Operations Agent</h1>
        <p className="text-gray-400 text-lg">
          Your internal ops & analysis workhorse for documents and metrics.
        </p>
      </div>

      {/* Stats Overview */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[
          { label: 'Documents', value: '0', icon: FileText, color: '#3b82f6' },
          { label: 'Insights Generated', value: '0', icon: TrendingUp, color: '#8b5cf6' },
          { label: 'Q&A Sessions', value: '0', icon: Search, color: '#f59e0b' },
          { label: 'Notifications', value: '0', icon: Bell, color: '#ef4444' },
        ].map((stat, idx) => (
          <Card key={idx} className="bg-[#1a1333]/80 border-[#2d2342]">
            <CardContent className="p-5 flex items-center gap-4">
              <div
                className="flex items-center justify-center w-12 h-12 rounded-xl"
                style={{ backgroundColor: `${stat.color}20` }}
              >
                <stat.icon className="h-6 w-6" style={{ color: stat.color }} />
              </div>
              <div>
                <p className="text-2xl font-bold text-white">{stat.value}</p>
                <p className="text-sm text-gray-400">{stat.label}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Agent Cards */}
      <div>
        <h2 className="text-xl font-semibold text-white mb-4">AI Sub-Agents</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {agents.map((agent, idx) => (
            <Card
              key={idx}
              className="bg-[#1a1333]/80 border-[#2d2342] hover:border-[#3a295a] transition-all duration-300 hover:shadow-lg"
            >
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between mb-3">
                  <div
                    className="flex items-center justify-center w-12 h-12 rounded-xl"
                    style={{ backgroundColor: `${agent.color}20` }}
                  >
                    <agent.icon className="h-6 w-6" style={{ color: agent.color }} />
                  </div>
                  <span
                    className="text-xs font-medium px-3 py-1 rounded-full"
                    style={{
                      backgroundColor: `${agent.color}20`,
                      color: agent.color,
                    }}
                  >
                    {agent.status}
                  </span>
                </div>
                <CardTitle className="text-white text-lg">{agent.title}</CardTitle>
                <CardDescription className="text-gray-400">
                  {agent.description}
                </CardDescription>
              </CardHeader>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
};

export default OperationsDashboard;
