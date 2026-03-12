import React, { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Loader2, FileText, Briefcase, Calendar, Settings, Users, Upload, BarChart3, Menu, Check, LayoutDashboard, BarChart2, X, Star, TrendingUp, ArrowUpRight } from 'lucide-react';
import {
  getJobDescriptions,
  getInterviews,
  getCVRecords,
  getSavedPrompts,
  isPromptOnDashboard,
  generateGraph,
} from '@/services/recruitmentAgentService';
import CVProcessing from './CVProcessing';
import JobDescriptions from './JobDescriptions';
import Interviews from './Interviews';
import CVRecords from './CVRecords';
import RecruiterSettings from './RecruiterSettings';
import RecruitmentAnalytics from './RecruitmentAnalytics';
import RecruitmentApiTester from './RecruitmentApiTester';
import AiInterviewQuestions from './AiInterviewQuestions';
// import AIGraphGenerator from './AIGraphGenerator';
import SavedPrompts from './SavedPrompts';
import { renderChart } from './ChartRenderer';
import { FlaskConical, HelpCircle, Sparkles } from 'lucide-react';

// Tab items configuration
const TAB_ITEMS = [
  { value: 'dashboard', label: 'Dashboard', icon: FileText },
  { value: 'analytics', label: 'Analytics', icon: BarChart3 },
  // { value: 'ai-graphs', label: 'AI Graphs', icon: Sparkles },
  { value: 'cv-processing', label: 'CV Processing', icon: Upload },
  { value: 'api-tester', label: 'API Tester', icon: FlaskConical },
  { value: 'ai-interview-questions', label: 'AI Questions', icon: HelpCircle },
  { value: 'saved-prompts', label: 'Saved Prompts', icon: Star },
  { value: 'jobs', label: 'Job Descriptions', icon: Briefcase },
  { value: 'candidates', label: 'Candidates', icon: Users },
  { value: 'interviews', label: 'Interviews', icon: Calendar },
  { value: 'settings', label: 'Settings', icon: Settings },
];

const PATH_TO_TAB = {
  dashboard: 'dashboard',
  cvprocessing: 'cv-processing',
  analytics: 'analytics',
  // 'ai-graphs': 'ai-graphs',
  'api-tester': 'api-tester',
  'ai-interview-questions': 'ai-interview-questions',
  'saved-prompts': 'saved-prompts',
  'job-descriptions': 'jobs',
  candidates: 'candidates',
  interviews: 'interviews',
  settings: 'settings',
};
const TAB_TO_PATH = {
  'dashboard': 'dashboard',
  'cv-processing': 'cvprocessing',
  'analytics': 'analytics',
  // 'ai-graphs': 'ai-graphs',
  'api-tester': 'api-tester',
  'ai-interview-questions': 'ai-interview-questions',
  'saved-prompts': 'saved-prompts',
  'jobs': 'job-descriptions',
  'candidates': 'candidates',
  'interviews': 'interviews',
  'settings': 'settings',
};

const RecruitmentDashboard = () => {
  const { toast } = useToast();
  const location = useLocation();
  const navigate = useNavigate();
  const pathSegment = (location.pathname.match(/\/recruitment\/?([^/]*)/) || [])[1] || 'dashboard';
  const activeTab = PATH_TO_TAB[pathSegment] || 'dashboard';
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({
    totalCVs: 0,
    totalInterviews: 0,
    activeJobs: 0,
    pendingInterviews: 0,
  });
  const [dashboardPrompts, setDashboardPrompts] = useState([]);
  const [loadingDashboardPrompts, setLoadingDashboardPrompts] = useState(false);
  const [selectedGraphPrompt, setSelectedGraphPrompt] = useState(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphData, setGraphData] = useState(null);
  const [graphInsights, setGraphInsights] = useState('');

  // Get current tab info for mobile display
  const currentTab = TAB_ITEMS.find(item => item.value === activeTab) || TAB_ITEMS[0];

  const handleTabChange = (tab) => {
    navigate(`/recruitment/${TAB_TO_PATH[tab] || 'dashboard'}`);
  };

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchDashboardPrompts = async () => {
    try {
      setLoadingDashboardPrompts(true);
      const res = await getSavedPrompts();
      const list = res?.data || [];
      setDashboardPrompts(list.filter(isPromptOnDashboard));
    } catch (e) {
      console.error('Error fetching dashboard prompts:', e);
    } finally {
      setLoadingDashboardPrompts(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'dashboard') {
      fetchDashboardPrompts();
    }
  }, [activeTab]);

  const fetchStats = async () => {
    try {
      setLoading(true);
      
      const [jobsRes, interviewsRes, cvRecordsRes] = await Promise.all([
        getJobDescriptions().catch(() => ({ status: 'success', data: [] })),
        getInterviews().catch(() => ({ status: 'success', data: [] })),
        getCVRecords().catch(() => ({ status: 'success', data: [] })),
      ]);

      const jobs = jobsRes.data || [];
      const interviews = interviewsRes.data || [];
      const cvRecords = cvRecordsRes.data || [];

      setStats({
        totalCVs: cvRecords.length,
        totalInterviews: interviews.length,
        activeJobs: jobs.filter(j => j.is_active).length,
        pendingInterviews: interviews.filter(i => i.status === 'PENDING').length,
      });
    } catch (error) {
      console.error('Error fetching stats:', error);
      toast({
        title: 'Error',
        description: 'Failed to load recruitment statistics',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleViewGraph = async (prompt) => {
    setSelectedGraphPrompt(prompt);
    setGraphLoading(true);
    setGraphData(null);
    setGraphInsights('');
    try {
      const response = await generateGraph(prompt.prompt);
      if (response.status === 'success') {
        setGraphData(response.data.chart);
        setGraphInsights(response.data.insights || '');
      }
    } catch (error) {
      console.error('Error generating graph:', error);
      toast({
        title: 'Error',
        description: 'Failed to generate graph',
        variant: 'destructive',
      });
    } finally {
      setGraphLoading(false);
    }
  };

  const handleCloseGraph = () => {
    setSelectedGraphPrompt(null);
    setGraphData(null);
    setGraphInsights('');
  };


  return (
    <div
      className="w-full rounded-2xl border border-white/[0.06] p-0 overflow-hidden"
      style={{ background: 'linear-gradient(90deg, #020308 0%, #020308 55%, rgba(10,37,64,0.68) 85%, rgba(14,39,71,0.52) 100%)' }}
    >
    <div className="space-y-6 w-full max-w-full overflow-x-hidden p-4 md:p-6 lg:p-8">
      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8 w-full">
        {[
          {
            label: 'Total CVs Processed',
            value: stats.totalCVs,
            sub: 'Candidates analyzed',
            icon: FileText,
            color: '#a78bfa',
            bgColor: 'rgba(167,139,250,0.2)',
            borderColor: 'rgba(167,139,250,0.2)',
            gradientFrom: 'rgba(167,139,250,0.2)',
            gradientTo: 'rgba(147,51,234,0.1)',
          },
          {
            label: 'Active Jobs',
            value: stats.activeJobs,
            sub: 'Job descriptions',
            icon: Briefcase,
            color: '#60a5fa',
            bgColor: 'rgba(96,165,250,0.2)',
            borderColor: 'rgba(96,165,250,0.2)',
            gradientFrom: 'rgba(96,165,250,0.2)',
            gradientTo: 'rgba(34,211,238,0.1)',
          },
          {
            label: 'Total Interviews',
            value: stats.totalInterviews,
            sub: 'Scheduled interviews',
            icon: Calendar,
            color: '#34d399',
            bgColor: 'rgba(52,211,153,0.2)',
            borderColor: 'rgba(52,211,153,0.2)',
            gradientFrom: 'rgba(52,211,153,0.2)',
            gradientTo: 'rgba(22,163,74,0.1)',
          },
          {
            label: 'Pending Interviews',
            value: stats.pendingInterviews,
            sub: 'Awaiting confirmation',
            icon: Users,
            color: '#f87171',
            bgColor: 'rgba(248,113,113,0.2)',
            borderColor: 'rgba(248,113,113,0.2)',
            gradientFrom: 'rgba(248,113,113,0.15)',
            gradientTo: 'rgba(220,38,38,0.08)',
          },
        ].map((card) => (
          <div
            key={card.label}
            className="relative group w-full min-w-0 rounded-xl backdrop-blur-sm p-5 transition-all duration-300 hover:scale-[1.02] hover:shadow-lg"
            style={{
              border: `1px solid ${card.borderColor}`,
              background: `linear-gradient(135deg, ${card.gradientFrom} 0%, ${card.gradientTo} 100%)`,
            }}
          >
            <div className="flex items-start justify-between mb-3">
              <div className="rounded-lg p-2.5" style={{ backgroundColor: card.bgColor }}>
                <card.icon className="h-5 w-5" style={{ color: card.color }} />
              </div>
              <ArrowUpRight className="h-4 w-4 text-white/20 group-hover:text-white/40 transition-colors" />
            </div>
            <div className="space-y-1">
              <p className="text-sm font-medium text-white/50 tracking-wide">{card.label}</p>
              <p className="text-3xl font-bold text-white tracking-tight">{card.value}</p>
              <p className="text-xs text-white/40">{card.sub}</p>
            </div>
          </div>
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

        {/* Desktop: Regular Tabs (lg and above - 1024px+) with horizontal scroll */}
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
                      background: 'linear-gradient(90deg, #a259ff 0%, #7c3aed 100%)',
                      color: '#fff',
                      border: '1.5px solid #a259ff',
                      boxShadow: '0 0 8px 0 #a259ff55',
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
              <TrendingUp className="h-4 w-4 text-violet-400" />
              Quick Actions
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 w-full max-w-full">
              {[
                {
                  label: 'Process CVs',
                  desc: 'Upload and analyze candidate resumes',
                  icon: Upload,
                  path: '/recruitment/cvprocessing',
                  color: '#a78bfa',
                  bgColor: 'rgba(167,139,250,0.15)',
                  borderHover: 'rgba(167,139,250,0.4)',
                },
                {
                  label: 'Manage Jobs',
                  desc: 'Create and manage job descriptions',
                  icon: Briefcase,
                  path: '/recruitment/job-descriptions',
                  color: '#60a5fa',
                  bgColor: 'rgba(96,165,250,0.15)',
                  borderHover: 'rgba(96,165,250,0.4)',
                },
                {
                  label: 'Schedule Interview',
                  desc: 'Schedule interviews with candidates',
                  icon: Calendar,
                  path: '/recruitment/interviews',
                  color: '#34d399',
                  bgColor: 'rgba(52,211,153,0.15)',
                  borderHover: 'rgba(52,211,153,0.4)',
                },
                {
                  label: 'AI Interview Questions',
                  desc: 'Get suggested questions for a candidate + job',
                  icon: HelpCircle,
                  path: '/recruitment/ai-interview-questions',
                  color: '#fbbf24',
                  bgColor: 'rgba(251,191,36,0.15)',
                  borderHover: 'rgba(251,191,36,0.4)',
                },
              ].map((action) => (
                <button
                  key={action.label}
                  onClick={() => navigate(action.path)}
                  className="group relative flex flex-col items-start gap-3 rounded-xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-sm p-4 text-left transition-all duration-300 hover:bg-white/[0.06] cursor-pointer"
                  style={{ '--hover-border': action.borderHover }}
                  onMouseEnter={(e) => e.currentTarget.style.borderColor = action.borderHover}
                  onMouseLeave={(e) => e.currentTarget.style.borderColor = ''}
                >
                  <div className="rounded-lg p-2" style={{ backgroundColor: action.bgColor }}>
                    <action.icon className="h-5 w-5" style={{ color: action.color }} />
                  </div>
                  <div>
                    <p className="font-semibold text-sm text-white group-hover:text-white transition-colors">{action.label}</p>
                    <p className="text-xs text-white/40 mt-0.5 leading-relaxed">{action.desc}</p>
                  </div>
                  <ArrowUpRight className="absolute top-4 right-4 h-3.5 w-3.5 text-white/0 group-hover:text-white/30 transition-all duration-300" />
                </button>
              ))}
            </div>
          </div>

          {/* Dashboard Graphs */}
          <div>
            <h3 className="text-sm font-semibold text-white/70 uppercase tracking-wider mb-3 flex items-center gap-2">
              <LayoutDashboard className="h-4 w-4 text-blue-400" />
              Dashboard Graphs
            </h3>
            <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] backdrop-blur-sm p-4 sm:p-5">
              {loadingDashboardPrompts ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin text-violet-400" />
                </div>
              ) : dashboardPrompts.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 text-center">
                  <div className="bg-white/[0.05] rounded-full p-4 mb-4">
                    <BarChart2 className="h-8 w-8 text-white/20" />
                  </div>
                  <p className="text-sm font-medium text-white/50 mb-1">No graphs on dashboard yet</p>
                  <p className="text-xs text-white/30 max-w-xs">
                    Save a prompt in AI Questions and use "Add to dashboard" to pin graphs here.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {dashboardPrompts.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => handleViewGraph(p)}
                      className={`group flex items-center gap-3 rounded-lg border p-3.5 text-left transition-all duration-200 cursor-pointer ${
                        selectedGraphPrompt?.id === p.id
                          ? 'border-violet-500/50 bg-violet-500/10 shadow-md shadow-violet-500/10'
                          : 'border-white/[0.08] bg-white/[0.03] hover:border-violet-500/30 hover:bg-white/[0.05]'
                      }`}
                    >
                      <div className={`shrink-0 rounded-lg p-2 ${
                        selectedGraphPrompt?.id === p.id ? 'bg-violet-500/20' : 'bg-white/[0.05]'
                      }`}>
                        <BarChart2 className={`h-4 w-4 ${
                          selectedGraphPrompt?.id === p.id ? 'text-violet-400' : 'text-white/30 group-hover:text-violet-400'
                        } transition-colors`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-sm text-white truncate">{p.title}</p>
                        {p.chart_type && (
                          <span className="inline-block mt-1 text-[10px] px-1.5 py-0.5 rounded bg-white/[0.06] text-white/40">
                            {p.chart_type}
                          </span>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              )}

              {/* Inline Graph Render */}
              {(graphLoading || graphData) && (
                <div className="mt-5 rounded-xl border border-white/[0.08] bg-black/30 p-4 sm:p-6">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                      <div className="bg-violet-500/20 rounded-lg p-1.5">
                        <BarChart2 className="h-4 w-4 text-violet-400" />
                      </div>
                      <h3 className="text-base font-semibold text-white">
                        {selectedGraphPrompt?.title || 'Graph'}
                      </h3>
                    </div>
                    <button
                      onClick={handleCloseGraph}
                      className="rounded-lg p-1.5 text-white/40 hover:text-white hover:bg-white/10 transition-all"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                  {graphLoading ? (
                    <div className="flex flex-col items-center justify-center py-14">
                      <Loader2 className="h-8 w-8 animate-spin text-violet-400 mb-3" />
                      <span className="text-sm text-white/50">Generating graph...</span>
                    </div>
                  ) : graphData ? (
                    <div>
                      <div className="bg-black/20 rounded-lg p-4 min-h-[300px]">
                        {renderChart(graphData)}
                      </div>
                      {graphInsights && (
                        <div className="mt-4 p-4 rounded-lg bg-violet-500/[0.05] border border-violet-500/10">
                          <p className="text-sm text-white/70 whitespace-pre-wrap leading-relaxed">{graphInsights}</p>
                        </div>
                      )}
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="analytics">
          <RecruitmentAnalytics />
        </TabsContent>

        {/* AI Graphs tab removed - graphs now render inline on dashboard */}

        <TabsContent value="cv-processing">
          <CVProcessing onProcessComplete={fetchStats} />
        </TabsContent>

        <TabsContent value="api-tester">
          <RecruitmentApiTester />
        </TabsContent>

        <TabsContent value="ai-interview-questions">
          <AiInterviewQuestions />
        </TabsContent>

        <TabsContent value="saved-prompts">
          <SavedPrompts />
        </TabsContent>

        <TabsContent value="jobs">
          <JobDescriptions onUpdate={fetchStats} />
        </TabsContent>

        <TabsContent value="candidates">
          <CVRecords />
        </TabsContent>

        <TabsContent value="interviews">
          <Interviews onUpdate={fetchStats} />
        </TabsContent>

        <TabsContent value="settings">
          <RecruiterSettings />
        </TabsContent>
      </Tabs>
    </div>
    </div>
  );
};

export default RecruitmentDashboard;


