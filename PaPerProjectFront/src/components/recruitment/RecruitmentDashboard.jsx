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
import { Loader2, FileText, Briefcase, Calendar, Settings, Users, Upload, BarChart3, Menu, ChevronDown, Check, LayoutDashboard, BarChart2 } from 'lucide-react';
import { 
  getJobDescriptions, 
  getInterviews, 
  getCVRecords,
  getEmailSettings,
  getInterviewSettings,
  getSavedPrompts,
  isPromptOnDashboard,
} from '@/services/recruitmentAgentService';
import CVProcessing from './CVProcessing';
import JobDescriptions from './JobDescriptions';
import Interviews from './Interviews';
import CVRecords from './CVRecords';
import RecruiterSettings from './RecruiterSettings';
import RecruitmentAnalytics from './RecruitmentAnalytics';
import RecruitmentApiTester from './RecruitmentApiTester';
import AiInterviewQuestions from './AiInterviewQuestions';
import AIGraphGenerator from './AIGraphGenerator';
import { FlaskConical, HelpCircle, Sparkles } from 'lucide-react';

// Tab items configuration
const TAB_ITEMS = [
  { value: 'dashboard', label: 'Dashboard', icon: FileText },
  { value: 'analytics', label: 'Analytics', icon: BarChart3 },
  { value: 'ai-graphs', label: 'AI Graphs', icon: Sparkles },
  { value: 'cv-processing', label: 'CV Processing', icon: Upload },
  { value: 'api-tester', label: 'API Tester', icon: FlaskConical },
  { value: 'ai-interview-questions', label: 'AI Questions', icon: HelpCircle },
  { value: 'jobs', label: 'Job Descriptions', icon: Briefcase },
  { value: 'candidates', label: 'Candidates', icon: Users },
  { value: 'interviews', label: 'Interviews', icon: Calendar },
  { value: 'settings', label: 'Settings', icon: Settings },
];

const PATH_TO_TAB = {
  dashboard: 'dashboard',
  cvprocessing: 'cv-processing',
  analytics: 'analytics',
  'ai-graphs': 'ai-graphs',
  'api-tester': 'api-tester',
  'ai-interview-questions': 'ai-interview-questions',
  'job-descriptions': 'jobs',
  candidates: 'candidates',
  interviews: 'interviews',
  settings: 'settings',
};
const TAB_TO_PATH = {
  'dashboard': 'dashboard',
  'cv-processing': 'cvprocessing',
  'analytics': 'analytics',
  'ai-graphs': 'ai-graphs',
  'api-tester': 'api-tester',
  'ai-interview-questions': 'ai-interview-questions',
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

  return (
    <div className="space-y-6 w-full max-w-full overflow-x-hidden">
      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8 w-full">
        <Card className="w-full min-w-0">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total CVs Processed</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.totalCVs}</div>
            <p className="text-xs text-muted-foreground">Candidates analyzed</p>
          </CardContent>
        </Card>

        <Card className="w-full min-w-0">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active Jobs</CardTitle>
            <Briefcase className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.activeJobs}</div>
            <p className="text-xs text-muted-foreground">Job descriptions</p>
          </CardContent>
        </Card>

        <Card className="w-full min-w-0">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Interviews</CardTitle>
            <Calendar className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.totalInterviews}</div>
            <p className="text-xs text-muted-foreground">Scheduled interviews</p>
          </CardContent>
        </Card>

        <Card className="w-full min-w-0">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Pending Interviews</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.pendingInterviews}</div>
            <p className="text-xs text-muted-foreground">Awaiting confirmation</p>
          </CardContent>
        </Card>
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
          <TabsList className="inline-flex w-max min-w-full h-auto p-1 gap-1">
            {TAB_ITEMS.map((item) => (
              <TabsTrigger 
                key={item.value} 
                value={item.value} 
                className="whitespace-nowrap shrink-0 px-3 py-1.5 text-sm"
              >
                <item.icon className="h-4 w-4 mr-2" />
                {item.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>

        <TabsContent value="dashboard" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Quick Actions</CardTitle>
              <CardDescription>Get started with recruitment tasks</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 w-full max-w-full">
                <Button
                  variant="outline"
                  className="h-auto flex-col items-start p-4"
                  onClick={() => navigate('/recruitment/cvprocessing')}
                >
                  <Upload className="h-6 w-6 mb-2" />
                  <span className="font-semibold">Process CVs</span>
                  <span className="text-xs text-muted-foreground mt-1">
                    Upload and analyze candidate resumes
                  </span>
                </Button>

                <Button
                  variant="outline"
                  className="h-auto flex-col items-start p-4"
                  onClick={() => navigate('/recruitment/job-descriptions')}
                >
                  <Briefcase className="h-6 w-6 mb-2" />
                  <span className="font-semibold">Manage Jobs</span>
                  <span className="text-xs text-muted-foreground mt-1">
                    Create and manage job descriptions
                  </span>
                </Button>

                <Button
                  variant="outline"
                  className="h-auto flex-col items-start p-4"
                  onClick={() => navigate('/recruitment/interviews')}
                >
                  <Calendar className="h-6 w-6 mb-2" />
                  <span className="font-semibold">Schedule Interview</span>
                  <span className="text-xs text-muted-foreground mt-1">
                    Schedule interviews with candidates
                  </span>
                </Button>

                <Button
                  variant="outline"
                  className="h-auto flex-col items-start p-4"
                  onClick={() => navigate('/recruitment/ai-interview-questions')}
                >
                  <HelpCircle className="h-6 w-6 mb-2" />
                  <span className="font-semibold">AI Interview Questions</span>
                  <span className="text-xs text-muted-foreground mt-1">
                    Get suggested questions for a candidate + job
                  </span>
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Dashboard graph cards - saved prompts added via "Add to dashboard" */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <LayoutDashboard className="h-5 w-5" />
                Dashboard Graphs
              </CardTitle>
              <CardDescription>
                Your saved graphs. Click a card to open and view the graph in AI Graphs.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {loadingDashboardPrompts ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : dashboardPrompts.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4">
                  No graphs on dashboard yet. Save a prompt in AI Graphs and use &quot;Add to dashboard&quot; to see cards here.
                </p>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {dashboardPrompts.map((prompt) => (
                    <Button
                      key={prompt.id}
                      variant="outline"
                      className="h-auto flex-col items-start p-4 text-left"
                      onClick={() => navigate(`/recruitment/ai-graphs?runPromptId=${prompt.id}`)}
                    >
                      <BarChart2 className="h-5 w-5 mb-2 text-muted-foreground" />
                      <span className="font-medium truncate w-full">{prompt.title}</span>
                      {prompt.chart_type && (
                        <Badge variant="secondary" className="mt-1 text-[10px]">
                          {prompt.chart_type}
                        </Badge>
                      )}
                    </Button>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="analytics">
          <RecruitmentAnalytics />
        </TabsContent>

        <TabsContent value="ai-graphs">
          <AIGraphGenerator />
        </TabsContent>

        <TabsContent value="cv-processing">
          <CVProcessing onProcessComplete={fetchStats} />
        </TabsContent>

        <TabsContent value="api-tester">
          <RecruitmentApiTester />
        </TabsContent>

        <TabsContent value="ai-interview-questions">
          <AiInterviewQuestions />
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
  );
};

export default RecruitmentDashboard;


