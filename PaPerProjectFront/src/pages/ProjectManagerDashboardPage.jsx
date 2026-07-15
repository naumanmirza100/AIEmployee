import React, { useState, useEffect } from 'react';
import { logoutCompany } from '@/services/companyAuthService';
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
  CalendarPlus,
} from 'lucide-react';
import ProjectPilotAgent from '@/components/pm-agent/ProjectPilotAgent';
import TaskPrioritizationAgent from '@/components/pm-agent/TaskPrioritizationAgent';
import KnowledgeQAAgent from '@/components/pm-agent/KnowledgeQAAgent';
import TimelineGanttAgent from '@/components/pm-agent/TimelineGanttAgent';
import ManualProjectCreation from '@/components/pm-agent/ManualProjectCreation';
import ManualTaskCreation from '@/components/pm-agent/ManualTaskCreation';
import PMToolsHub from '@/components/pm-agent/PMToolsHub';
import MeetingScheduler from '@/components/pm-agent/MeetingScheduler';
import DashboardNavbar from '@/components/common/DashboardNavbar';
import ErrorBoundary from '@/components/common/ErrorBoundary';
// Tutorial + hints + floating chat (generic components reused, PM-specific content)
import InfoHint, { HintsProvider, useHints } from '@/components/frontline/InfoHint';
import FrontlineTutorial, { hasSeenTutorial, resetTutorial } from '@/components/frontline/FrontlineTutorial';
import PMFloatingChat from '@/components/pm-agent/PMFloatingChat';
import {
  PM_MAIN_TOUR_STEPS, PM_TAB_TOURS, PM_HINTS, PM_MAIN_TOUR_KEY,
} from '@/components/pm-agent/pmTutorialSteps';
import {
  shouldSpotlightTour, markSpotlightSeen,
  tourAvailable, makeHoverLaunchHandlers,
} from '@/components/frontline/tourUtils';
import { GraduationCap, Eye, EyeOff } from 'lucide-react';

const PM_TAB_ITEMS = [
  { value: 'overview', label: 'Overview', icon: BrainCircuit },
  { value: 'create-project', label: 'Create Project', icon: Plus },
  { value: 'create-task', label: 'Create Task', icon: Plus },
  { value: 'project-pilot', label: 'Project Pilot', icon: Target },
  { value: 'task-prioritization', label: 'Task Prioritization', icon: ListChecks },
  { value: 'knowledge-qa', label: 'Knowledge Q&A', icon: MessageSquare },
  { value: 'timeline-gantt', label: 'Timeline & Gantt', icon: Calendar },
  { value: 'meeting-scheduler', label: 'Meeting Scheduler', icon: CalendarPlus },
  { value: 'ai-tools', label: 'AI Tools', icon: Workflow },
];

const ProjectManagerDashboardPage = () => {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');

  // ---- Onboarding tutorial + per-tab tours ----
  const [tutorialOpen, setTutorialOpen] = useState(false);
  const [activeTabTour, setActiveTabTour] = useState(null);

  useEffect(() => {
    if (!hasSeenTutorial(PM_MAIN_TOUR_KEY)) {
      const t = setTimeout(() => setTutorialOpen(true), 600);
      return () => clearTimeout(t);
    }
  }, []);

  useEffect(() => {
    if (tutorialOpen) return;
    const tour = PM_TAB_TOURS[activeTab];
    if (!tour) return;
    if (hasSeenTutorial(tour.key)) return;
    const t = setTimeout(() => setActiveTabTour(activeTab), 500);
    return () => clearTimeout(t);
  }, [activeTab, tutorialOpen]);

  // One-time spotlight on "Take the Tour"
  const [spotlightTour, setSpotlightTour] = useState(false);
  useEffect(() => {
    if (tutorialOpen) return;
    if (!hasSeenTutorial(PM_MAIN_TOUR_KEY)) return;
    if (!shouldSpotlightTour('pm')) return;
    setSpotlightTour(true);
    const t = setTimeout(() => { setSpotlightTour(false); markSpotlightSeen('pm'); }, 5500);
    return () => clearTimeout(t);
  }, [tutorialOpen]);

  const handleReplayTutorial = () => {
    setSpotlightTour(false);
    markSpotlightSeen('pm');
    resetTutorial(PM_MAIN_TOUR_KEY);
    setTutorialOpen(true);
  };
  const pmTabTourKeys = React.useMemo(() => Object.values(PM_TAB_TOURS).map((t) => t.key), []);
  const handleReplayTabTour = (tabKey) => {
    const tour = PM_TAB_TOURS[tabKey];
    if (!tour) return;
    resetTutorial(tour.key);
    setActiveTabTour(tabKey);
  };

  const TabTourButton = ({ tabKey }) => (
    <button
      type="button"
      onClick={() => handleReplayTabTour(tabKey)}
      title={`Take a guided tour of the ${PM_TAB_TOURS[tabKey]?.label || 'this'} tab`}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-cyan-400/40 bg-cyan-500/10 text-cyan-200 text-xs font-semibold hover:bg-cyan-500/20 hover:text-cyan-100 transition"
    >
      <GraduationCap className="h-3.5 w-3.5" />
      Tour this tab
    </button>
  );

  const HintsToggleButton = () => {
    const { enabled, toggle } = useHints();
    return (
      <button
        type="button"
        onClick={toggle}
        aria-pressed={enabled}
        title={enabled ? 'Hide the ! help icons on every element' : 'Show the ! help icons on every element'}
        className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-semibold transition border ${
          enabled
            ? 'border-cyan-400/40 bg-cyan-500/10 text-cyan-200 hover:bg-cyan-500/20 hover:text-cyan-100'
            : 'border-white/10 bg-white/[0.03] text-white/50 hover:bg-white/[0.06] hover:text-white/70'
        }`}
      >
        {enabled ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
        <span>Hints: {enabled ? 'On' : 'Off'}</span>
      </button>
    );
  };
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

  const handleLogout = async () => {
    if (isCompanyUser()) {
      await logoutCompany();
      navigate('/company/login');
    } else {
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
    <HintsProvider>
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
          onNotificationClick={(n) => {
            const type = n.type || n.notification_type || '';
            const data = n.data || {};
            if (type.includes('meeting') || data.type?.includes('meeting')) {
              setActiveTab('meeting-scheduler');
            } else if (type.includes('task') || type.includes('overdue') || type.includes('blocked') || type.includes('unassigned') || type.includes('sprint')) {
              setActiveTab('task-prioritization');
            } else if (type.includes('deadline') || type.includes('milestone')) {
              setActiveTab('timeline-gantt');
            } else if (type.includes('project') || type.includes('workload')) {
              setActiveTab('overview');
            } else {
              setActiveTab('overview');
            }
          }}
        />

        {/* Main Content */}
        <main className="container mx-auto px-3 sm:px-4 py-6 sm:py-8 w-full max-w-full overflow-x-hidden">
          <div
            className="w-full rounded-2xl border border-white/[0.06] p-0"
            style={{ background: 'linear-gradient(90deg, #020308 0%, #020308 55%, rgba(10,37,64,0.68) 85%, rgba(14,39,71,0.52) 100%)' }}
          >
          <div className="space-y-6 w-full max-w-full overflow-x-hidden p-4 md:p-6 lg:p-8">
          {/* Top bar: Hints toggle + Take the Tour */}
          <div className="flex justify-end items-center gap-2 relative">
            <HintsToggleButton />
            <button
              type="button"
              onClick={handleReplayTutorial}
              data-tour-pm="replay"
              title="Replay the onboarding tutorial"
              className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-lg border border-cyan-400/40 bg-cyan-500/10 text-cyan-200 text-sm font-semibold hover:bg-cyan-500/20 hover:text-cyan-100 transition ${spotlightTour ? 'pm-spotlight' : ''}`}
            >
              <GraduationCap className="h-4 w-4" />
              Take the Tour
            </button>
            {spotlightTour && (
              <div className="absolute -bottom-12 right-0 z-10 rounded-md border border-cyan-400/40 bg-[#0a1929] px-2.5 py-1.5 text-xs text-white/90 shadow-lg pointer-events-none whitespace-nowrap">
                👋 Take the tour anytime from here
                <span className="absolute -top-1 right-6 h-2 w-2 bg-[#0a1929] border-t border-l border-cyan-400/40 rotate-45" />
              </div>
            )}
          </div>
          <style>{`
            @keyframes pmSpotlight {
              0%, 100% { box-shadow: 0 0 0 0 rgba(6, 182, 212, 0.4), 0 0 0 0 rgba(6, 182, 212, 0.2); }
              50%      { box-shadow: 0 0 0 6px rgba(6, 182, 212, 0.15), 0 0 0 12px rgba(6, 182, 212, 0.08); }
            }
            .pm-spotlight { animation: pmSpotlight 1.6s ease-in-out infinite; }
            @keyframes pmDotPulse {
              0%, 100% { transform: scale(1); opacity: 1; }
              50%      { transform: scale(1.3); opacity: 0.7; }
            }
          `}</style>

          {/* Loading indicator */}
          {loading && (
            <div className="mb-4 flex items-center justify-center">
              <Loader2 className="h-5 w-5 animate-spin text-violet-400 mr-2" />
              <span className="text-sm text-white/50">Loading projects...</span>
            </div>
          )}

          {/* Stats Overview */}
          <div data-tour-pm="stats" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6 sm:mb-8 w-full">
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
                <div data-tour-pm="tabs" className="hidden lg:block overflow-x-auto pb-1">
                  <TabsList
                    className="inline-flex w-max min-w-full h-auto p-1 gap-1 rounded-lg bg-[#1a1333] border border-[#3a295a]"
                    style={{ boxShadow: '0 2px 12px 0 #a259ff0a' }}
                  >
                    {PM_TAB_ITEMS.map((item) => {
                      const TabIcon = item.icon;
                      const tour = PM_TAB_TOURS[item.value];
                      const showBadge = tour && tourAvailable(tour.key);
                      const hoverHandlers = tour ? makeHoverLaunchHandlers({
                        tourStorageKey: tour.key,
                        onLaunch: () => setActiveTabTour(item.value),
                      }) : {};
                      return (
                        <TabsTrigger
                          key={item.value}
                          value={item.value}
                          data-tour-pm-tab={item.value}
                          {...hoverHandlers}
                          className="relative whitespace-nowrap shrink-0 px-4 py-2 text-sm font-medium rounded-md border transition-all duration-150"
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
                          <TabIcon className="h-4 w-4 mr-2" />
                          {item.label}
                          {showBadge && (
                            <span
                              title="Tour available — hover to launch or click 'Tour this tab' inside"
                              className="absolute -top-1 -right-1 h-2 w-2 rounded-full bg-cyan-400 ring-2 ring-[#1a1333]"
                              style={{ animation: 'pmDotPulse 2s ease-in-out infinite' }}
                            />
                          )}
                        </TabsTrigger>
                      );
                    })}
                  </TabsList>
                </div>

                <TabsContent value="overview" className="mt-6">
                  <div className="flex items-center gap-2 justify-end mb-3">
                    <InfoHint {...PM_HINTS.pmOvQuicknav} />
                    <TabTourButton tabKey="overview" />
                  </div>
                  <div data-tour-pm-ov="quicknav" className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-6 w-full min-w-0">
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
                  <div className="flex justify-end mb-3"><TabTourButton tabKey="create-project" /></div>
                  <ManualProjectCreation onProjectCreated={fetchProjects} />
                </TabsContent>

                <TabsContent value="create-task" className="mt-6">
                  <div className="flex justify-end mb-3"><TabTourButton tabKey="create-task" /></div>
                  <ManualTaskCreation onTaskCreated={fetchProjects} />
                </TabsContent>

                <TabsContent value="project-pilot" className="mt-6">
                  <div className="flex justify-end mb-3"><TabTourButton tabKey="project-pilot" /></div>
                  <ErrorBoundary><ProjectPilotAgent projects={projects || []} onProjectUpdate={fetchProjects} onNavigate={setActiveTab} /></ErrorBoundary>
                </TabsContent>

                <TabsContent value="task-prioritization" className="mt-6">
                  <div className="flex justify-end mb-3"><TabTourButton tabKey="task-prioritization" /></div>
                  <ErrorBoundary><TaskPrioritizationAgent projects={projects || []} /></ErrorBoundary>
                </TabsContent>

                <TabsContent value="knowledge-qa" className="mt-6">
                  <div className="flex justify-end mb-3"><TabTourButton tabKey="knowledge-qa" /></div>
                  <ErrorBoundary><KnowledgeQAAgent projects={projects || []} /></ErrorBoundary>
                </TabsContent>

                <TabsContent value="timeline-gantt" className="mt-6">
                  <div className="flex justify-end mb-3"><TabTourButton tabKey="timeline-gantt" /></div>
                  <ErrorBoundary><TimelineGanttAgent projects={projects || []} /></ErrorBoundary>
                </TabsContent>

                <TabsContent value="meeting-scheduler" className="mt-6">
                  <div className="flex justify-end mb-3"><TabTourButton tabKey="meeting-scheduler" /></div>
                  <ErrorBoundary><MeetingScheduler /></ErrorBoundary>
                </TabsContent>

                <TabsContent value="ai-tools" className="mt-6">
                  <div className="flex justify-end mb-3"><TabTourButton tabKey="ai-tools" /></div>
                  <ErrorBoundary><PMToolsHub /></ErrorBoundary>
                </TabsContent>
              </Tabs>
          </div>
          </div>
          </div>

        </main>
      </div>

      {/* Main onboarding tour */}
      <FrontlineTutorial
        open={tutorialOpen}
        onClose={() => setTutorialOpen(false)}
        setActiveTab={setActiveTab}
        steps={PM_MAIN_TOUR_STEPS}
        storageKey={PM_MAIN_TOUR_KEY}
        siblingKeys={pmTabTourKeys}
      />

      {/* Per-tab guided tour */}
      {activeTabTour && PM_TAB_TOURS[activeTabTour] && (
        <FrontlineTutorial
          open={!!activeTabTour}
          onClose={() => setActiveTabTour(null)}
          steps={PM_TAB_TOURS[activeTabTour].steps}
          storageKey={PM_TAB_TOURS[activeTabTour].key}
          siblingKeys={pmTabTourKeys.filter((k) => k !== PM_TAB_TOURS[activeTabTour].key)}
        />
      )}

      {/* Floating dual-mode PM Quick Chat — pinned bottom-right */}
      <PMFloatingChat />
    </>
    </HintsProvider>
  );
};

export default ProjectManagerDashboardPage;

