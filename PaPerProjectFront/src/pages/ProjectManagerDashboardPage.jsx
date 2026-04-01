import React, { useState, useEffect } from 'react';
import { Helmet } from 'react-helmet';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import { projectService } from '@/services';
import pmAgentService from '@/services/pmAgentService';
import { checkModuleAccess } from '@/services/modulePurchaseService';
import usePurchasedModules from '@/hooks/usePurchasedModules';
import { getAgentNavItems } from '@/utils/agentNavItems';
import { 
  BrainCircuit, 
  Target, 
  MessageSquare, 
  Calendar, 
  ListChecks,
  Loader2,
  FolderKanban,
  Sparkles,
  TrendingUp,
  Clock,
  Building2,
  ArrowLeft,
  Plus,
  Lock,
  Menu,
  Check,
  Workflow,
} from 'lucide-react';
import ProjectPilotAgent from '@/components/pm-agent/ProjectPilotAgent';
import TaskPrioritizationAgent from '@/components/pm-agent/TaskPrioritizationAgent';
import KnowledgeQAAgent from '@/components/pm-agent/KnowledgeQAAgent';
import TimelineGanttAgent from '@/components/pm-agent/TimelineGanttAgent';
import ManualProjectCreation from '@/components/pm-agent/ManualProjectCreation';
import ManualTaskCreation from '@/components/pm-agent/ManualTaskCreation';
import PMToolsHub from '@/components/pm-agent/PMToolsHub';
import DashboardNavbar from '@/components/common/DashboardNavbar';

const PM_TAB_ITEMS = [
  { value: 'overview', label: 'Overview', icon: BrainCircuit },
  { value: 'create-project', label: 'Create Project', icon: Plus },
  { value: 'create-task', label: 'Create Task', icon: Plus },
  { value: 'project-pilot', label: 'Project Pilot', icon: Target },
  { value: 'task-prioritization', label: 'Task Prioritization', icon: ListChecks },
  { value: 'knowledge-qa', label: 'Knowledge Q&A', icon: MessageSquare },
  { value: 'timeline-gantt', label: 'Timeline & Gantt', icon: Calendar },
  { value: 'ai-tools', label: 'AI Tools', icon: Workflow },
];

const ProjectManagerDashboardPage = () => {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');
  const [activeSection, setActiveSection] = useState('project-manager'); // 'dashboard', 'project-manager', 'recruitment'
  const { logout, user } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  
  // Get company user from localStorage
  const [companyUser, setCompanyUser] = useState(null);
  const [hasAccess, setHasAccess] = useState(false);
  const [checkingAccess, setCheckingAccess] = useState(true);
  const { purchasedModules, modulesLoaded } = usePurchasedModules();

  // Check if user is a company user
  const isCompanyUser = () => {
    return !!companyUser;
  };

  const checkModuleAccessForUser = async (user = null) => {
    const currentUser = user || companyUser;
    if (!currentUser) {
      setHasAccess(true); // Regular users have access
      setCheckingAccess(false);
      return;
    }
    
    try {
      setCheckingAccess(true);
      const response = await checkModuleAccess('project_manager_agent');
      if (response.status === 'success') {
        setHasAccess(response.has_access);
        if (!response.has_access) {
          toast({
            title: 'Module Not Purchased',
            description: 'Please purchase the Project Manager Agent module to access this dashboard',
            variant: 'default',
          });
        }
      }
    } catch (error) {
      console.error('Error checking module access:', error);
      // On error, allow access (graceful degradation)
      setHasAccess(true);
    } finally {
      setCheckingAccess(false);
    }
  };

  useEffect(() => {
    // Get company user from localStorage
    const companyUserStr = localStorage.getItem('company_user');
    if (companyUserStr) {
      try {
        const user = JSON.parse(companyUserStr);
        setCompanyUser(user);
        checkModuleAccessForUser(user);
      } catch (error) {
        console.error('Error parsing company user:', error);
        setCheckingAccess(false);
      }
    } else {
      // Regular user (not company user) - allow access
      setHasAccess(true);
      setCheckingAccess(false);
    }
  }, []);

  useEffect(() => {
    fetchProjects();
  }, []);

  const fetchProjects = async () => {
    try {
      setLoading(true);
      console.log('Fetching projects...');
      // Use company API if company user, otherwise use regular API
      const { companyApi } = await import('@/services/companyAuthService');
      const { getCompanyToken } = await import('@/services/companyAuthService');
      
      let response;
      if (getCompanyToken()) {
        // Use company dashboard API
        response = await companyApi.get('/project-manager/dashboard');
        if (response.status === 'success' && response.data.projects) {
          setProjects(response.data.projects);
          setLoading(false);
          return;
        }
      } else {
        // Use regular project service
        response = await projectService.listProjects();
      }
      console.log('Projects response:', response);
      
      if (response.status === 'success') {
        setProjects(response.data || []);
      } else {
        console.warn('Projects response not successful:', response);
        setProjects([]); // Ensure projects is always an array
      }
    } catch (error) {
      console.error('Error fetching projects:', error);
      setProjects([]); // Ensure projects is always an array even on error
      toast({
        title: 'Error',
        description: error.message || 'Failed to load projects',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    if (isCompanyUser()) {
      // Company user logout
      localStorage.removeItem('company_auth_token');
      localStorage.removeItem('company_user');
      localStorage.removeItem('company_purchased_modules');
      navigate('/company/login');
    } else {
      // Regular user logout
      logout().then(() => {
        navigate('/login');
      }).catch((error) => {
        console.error('Logout error:', error);
      });
    }
  };

  const currentTab = PM_TAB_ITEMS.find((item) => item.value === activeTab) || PM_TAB_ITEMS[0];
  const CurrentTabIcon = currentTab.icon;

  // Show loading while checking access or loading modules
  if (checkingAccess || (companyUser && !modulesLoaded)) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  // Show access denied if company user and module not purchased
  if (companyUser && !hasAccess) {
    return (
      <>
        <Helmet>
          <title>Access Denied | Pay Per Project</title>
        </Helmet>
        <div className="min-h-screen bg-background flex items-center justify-center p-4">
          <Card className="max-w-md w-full">
            <CardHeader>
              <div className="flex items-center justify-center mb-4">
                <Lock className="h-12 w-12 text-muted-foreground" />
              </div>
              <CardTitle className="text-center">Module Not Purchased</CardTitle>
              <CardDescription className="text-center">
                You need to purchase the Project Manager Agent module to access this dashboard.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Button 
                onClick={() => navigate('/')} 
                className="w-full"
              >
                Go to Home Page to Purchase
              </Button>
              <Button 
                onClick={() => navigate('/company/dashboard')} 
                variant="outline"
                className="w-full"
              >
                Back to Dashboard
              </Button>
            </CardContent>
          </Card>
        </div>
      </>
    );
  }

  return (
    <>
      <Helmet>
        <title>Project Manager Dashboard - PayPerProject</title>
        <meta name="description" content="AI-powered project management dashboard" />
      </Helmet>

      <div
        className="min-h-screen"
        style={{
          background: 'linear-gradient(135deg, #020308 0%, #0a0a1a 25%, #0d0b1f 50%, #0f0a20 75%, #020308 100%)',
        }}
      >
        {/* Header */}
        <DashboardNavbar
          icon={BrainCircuit}
          title={companyUser?.companyName || "Project Manager Dashboard"}
          subtitle={companyUser ? companyUser.fullName : "AI-powered project management"}
          user={companyUser || user}
          userRole={companyUser ? "Company User" : "Project Manager"}
          showNavTabs={isCompanyUser()}
          activeSection={activeSection}
          onLogout={handleLogout}
          navItems={isCompanyUser() ? getAgentNavItems(purchasedModules, 'project-manager', navigate) : []}
        />

        {/* Main Content */}
        <main className="container mx-auto px-3 sm:px-4 py-6 sm:py-8 w-full max-w-full overflow-x-hidden">
          <div
            className="w-full rounded-2xl border border-white/[0.06] p-0"
            style={{ background: 'linear-gradient(90deg, #020308 0%, #020308 55%, rgba(10,37,64,0.68) 85%, rgba(14,39,71,0.52) 100%)' }}
          >
          <div className="space-y-6 w-full max-w-full overflow-x-hidden p-4 md:p-6 lg:p-8">
          {/* Loading indicator */}
          {loading && (
            <div className="mb-4 flex items-center justify-center">
              <Loader2 className="h-5 w-5 animate-spin text-violet-400 mr-2" />
              <span className="text-sm text-white/50">Loading projects...</span>
            </div>
          )}

          {/* Stats Overview */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6 sm:mb-8 w-full">
            {[
              {
                label: 'Total Projects',
                value: projects.length,
                sub: 'All projects',
                icon: FolderKanban,
                color: '#a78bfa',
                bgColor: 'rgba(167,139,250,0.2)',
                borderColor: 'rgba(167,139,250,0.2)',
                gradientFrom: 'rgba(167,139,250,0.2)',
                gradientTo: 'rgba(147,51,234,0.1)',
              },
              {
                label: 'Active Projects',
                value: projects.filter(p => p.status === 'active' || p.status === 'in_progress').length,
                sub: 'In progress',
                icon: TrendingUp,
                color: '#34d399',
                bgColor: 'rgba(52,211,153,0.2)',
                borderColor: 'rgba(52,211,153,0.2)',
                gradientFrom: 'rgba(52,211,153,0.2)',
                gradientTo: 'rgba(22,163,74,0.1)',
              },
              {
                label: 'Planning',
                value: projects.filter(p => p.status === 'planning').length,
                sub: 'In planning phase',
                icon: Clock,
                color: '#fbbf24',
                bgColor: 'rgba(251,191,36,0.2)',
                borderColor: 'rgba(251,191,36,0.2)',
                gradientFrom: 'rgba(251,191,36,0.15)',
                gradientTo: 'rgba(245,158,11,0.08)',
              },
              {
                label: 'Completed',
                value: projects.filter(p => p.status === 'completed').length,
                sub: 'Successfully delivered',
                icon: Sparkles,
                color: '#60a5fa',
                bgColor: 'rgba(96,165,250,0.2)',
                borderColor: 'rgba(96,165,250,0.2)',
                gradientFrom: 'rgba(96,165,250,0.2)',
                gradientTo: 'rgba(34,211,238,0.1)',
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
                </div>
                <div className="space-y-1">
                  <p className="text-sm font-medium text-white/50 tracking-wide">{card.label}</p>
                  <p className="text-3xl font-bold text-white tracking-tight">{card.value}</p>
                  <p className="text-xs text-white/40">{card.sub}</p>
                </div>
              </div>
            ))}
          </div>

          {/* AI Agents Tabs */}
          <div className="w-full min-w-0">
              <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                {/* Mobile & Tablet: Hamburger menu (below lg) */}
                <div className="lg:hidden w-full mb-4">
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="outline" className="w-full justify-between h-11 border-[#3a295a] bg-[#1a1333] text-white/80 hover:bg-[#231845] hover:text-white">
                        <div className="flex items-center gap-2 min-w-0">
                          <CurrentTabIcon className="h-4 w-4 shrink-0 text-violet-400" />
                          <span className="font-medium truncate">{currentTab.label}</span>
                        </div>
                        <Menu className="h-5 w-5 text-white/40 shrink-0" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start" className="w-[calc(100vw-2rem)] max-w-sm max-h-[60vh] overflow-y-auto border-[#3a295a] bg-[#161630]">
                      {PM_TAB_ITEMS.map((item) => {
                        const isActive = item.value === activeTab;
                        const ItemIcon = item.icon;
                        return (
                          <DropdownMenuItem
                            key={item.value}
                            onClick={() => setActiveTab(item.value)}
                            className={`flex items-center justify-between py-3 cursor-pointer ${isActive ? 'bg-violet-600/20' : 'hover:bg-white/5'}`}
                          >
                            <div className="flex items-center gap-3 min-w-0">
                              <ItemIcon className={`h-4 w-4 shrink-0 ${isActive ? 'text-violet-400' : 'text-white/40'}`} />
                              <span className={isActive ? 'font-medium text-violet-300' : 'text-white/70'}>{item.label}</span>
                            </div>
                            {isActive && <Check className="h-4 w-4 text-violet-400 shrink-0" />}
                          </DropdownMenuItem>
                        );
                      })}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>

                {/* Desktop: Regular tabs (lg and above) with horizontal scroll */}
                <div className="hidden lg:block overflow-x-auto pb-1">
                  <TabsList
                    className="inline-flex w-max min-w-full h-auto p-1 gap-1 rounded-lg bg-[#1a1333] border border-[#3a295a]"
                    style={{ boxShadow: '0 2px 12px 0 #a259ff0a' }}
                  >
                    {PM_TAB_ITEMS.map((item) => {
                      const TabIcon = item.icon;
                      return (
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
                          <TabIcon className="h-4 w-4 mr-2" />
                          {item.label}
                        </TabsTrigger>
                      );
                    })}
                  </TabsList>
                </div>

                <TabsContent value="overview" className="mt-6">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-6 w-full min-w-0">
                    {[
                      {
                        title: 'Project Pilot',
                        desc: 'Create projects, tasks, and manage operations using natural language',
                        icon: Target,
                        tab: 'project-pilot',
                        color: '#a78bfa',
                        bgColor: 'rgba(167,139,250,0.15)',
                        borderHover: 'rgba(167,139,250,0.4)',
                      },
                      {
                        title: 'Task Prioritization',
                        desc: 'Prioritize tasks, find bottlenecks, and suggest delegation strategies',
                        icon: ListChecks,
                        tab: 'task-prioritization',
                        color: '#34d399',
                        bgColor: 'rgba(52,211,153,0.15)',
                        borderHover: 'rgba(52,211,153,0.4)',
                      },
                      {
                        title: 'Knowledge Q&A',
                        desc: 'Ask questions about your projects and get AI-powered answers',
                        icon: MessageSquare,
                        tab: 'knowledge-qa',
                        color: '#60a5fa',
                        bgColor: 'rgba(96,165,250,0.15)',
                        borderHover: 'rgba(96,165,250,0.4)',
                      },
                      {
                        title: 'Timeline & Gantt',
                        desc: 'Create timelines, generate Gantt charts, and manage project schedules',
                        icon: Calendar,
                        tab: 'timeline-gantt',
                        color: '#fbbf24',
                        bgColor: 'rgba(251,191,36,0.15)',
                        borderHover: 'rgba(251,191,36,0.4)',
                      },
                      {
                        title: 'AI Tools',
                        desc: 'Standup reports, health scores, meeting notes, team analytics & more',
                        icon: Workflow,
                        tab: 'ai-tools',
                        color: '#2dd4bf',
                        bgColor: 'rgba(45,212,191,0.15)',
                        borderHover: 'rgba(45,212,191,0.4)',
                      },
                    ].map((card) => (
                      <button
                        key={card.title}
                        onClick={() => setActiveTab(card.tab)}
                        className="group relative flex flex-col items-start gap-3 rounded-xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-sm p-5 text-left transition-all duration-300 hover:bg-white/[0.06] cursor-pointer w-full min-w-0"
                        onMouseEnter={(e) => e.currentTarget.style.borderColor = card.borderHover}
                        onMouseLeave={(e) => e.currentTarget.style.borderColor = ''}
                      >
                        <div className="rounded-lg p-2.5" style={{ backgroundColor: card.bgColor }}>
                          <card.icon className="h-5 w-5" style={{ color: card.color }} />
                        </div>
                        <div>
                          <p className="font-semibold text-sm text-white group-hover:text-white transition-colors">{card.title}</p>
                          <p className="text-xs text-white/40 mt-1 leading-relaxed">{card.desc}</p>
                        </div>
                      </button>
                    ))}
                  </div>
                </TabsContent>

                <TabsContent value="create-project" className="mt-6">
                  <ManualProjectCreation onProjectCreated={fetchProjects} />
                </TabsContent>

                <TabsContent value="create-task" className="mt-6">
                  <ManualTaskCreation onTaskCreated={fetchProjects} />
                </TabsContent>

                <TabsContent value="project-pilot" className="mt-6">
                  <ProjectPilotAgent projects={projects || []} onProjectUpdate={fetchProjects} />
                </TabsContent>

                <TabsContent value="task-prioritization" className="mt-6">
                  <TaskPrioritizationAgent projects={projects || []} />
                </TabsContent>

                <TabsContent value="knowledge-qa" className="mt-6">
                  <KnowledgeQAAgent projects={projects || []} />
                </TabsContent>

                <TabsContent value="timeline-gantt" className="mt-6">
                  <TimelineGanttAgent projects={projects || []} />
                </TabsContent>

                <TabsContent value="ai-tools" className="mt-6">
                  <PMToolsHub />
                </TabsContent>
              </Tabs>
          </div>
          </div>
          </div>

        </main>
      </div>
    </>
  );
};

export default ProjectManagerDashboardPage;

