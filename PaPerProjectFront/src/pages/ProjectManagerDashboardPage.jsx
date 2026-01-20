import React, { useState, useEffect } from 'react';
import { Helmet } from 'react-helmet';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import { projectService } from '@/services';
import pmAgentService from '@/services/pmAgentService';
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
  UserCheck,
  Plus,
  Megaphone
} from 'lucide-react';
import ProjectPilotAgent from '@/components/pm-agent/ProjectPilotAgent';
import TaskPrioritizationAgent from '@/components/pm-agent/TaskPrioritizationAgent';
import KnowledgeQAAgent from '@/components/pm-agent/KnowledgeQAAgent';
import TimelineGanttAgent from '@/components/pm-agent/TimelineGanttAgent';
import ManualProjectCreation from '@/components/pm-agent/ManualProjectCreation';
import ManualTaskCreation from '@/components/pm-agent/ManualTaskCreation';
import DashboardNavbar from '@/components/common/DashboardNavbar';

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
  
  useEffect(() => {
    // Get company user from localStorage
    const companyUserStr = localStorage.getItem('company_user');
    if (companyUserStr) {
      try {
        const user = JSON.parse(companyUserStr);
        setCompanyUser(user);
      } catch (error) {
        console.error('Error parsing company user:', error);
      }
    }
  }, []);
  
  // Check if user is a company user
  const isCompanyUser = () => {
    return !!companyUser;
  };

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

  // Don't block rendering while loading - show content with empty projects
  // This prevents blank page when switching tabs
  // if (loading) {
  //   return (
  //     <div className="min-h-screen flex items-center justify-center bg-background">
  //       <Loader2 className="h-8 w-8 animate-spin text-primary" />
  //     </div>
  //   );
  // }

  return (
    <>
      <Helmet>
        <title>Project Manager Dashboard - PayPerProject</title>
        <meta name="description" content="AI-powered project management dashboard" />
      </Helmet>

      <div className="min-h-screen bg-background">
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
          navItems={isCompanyUser() ? [
            {
              label: 'Dashboard',
              icon: Building2,
              section: 'dashboard',
              onClick: () => navigate('/company/dashboard'),
            },
            {
              label: 'Project Manager Agent',
              icon: BrainCircuit,
              section: 'project-manager',
              onClick: () => navigate('/project-manager/dashboard'),
            },
            {
              label: 'Recruitment Agent',
              icon: UserCheck,
              section: 'recruitment',
              onClick: () => navigate('/recruitment/dashboard'),
            },
            {
              label: 'Marketing Agent',
              icon: Megaphone,
              section: 'marketing',
              onClick: () => navigate('/marketing/dashboard'),
            },
          ] : []}
        />

        {/* Main Content */}
        <main className="container mx-auto px-4 py-8">
          {/* Loading indicator */}
          {loading && (
            <div className="mb-4 flex items-center justify-center">
              <Loader2 className="h-5 w-5 animate-spin text-primary mr-2" />
              <span className="text-sm text-muted-foreground">Loading projects...</span>
            </div>
          )}
          
          {/* Stats Overview */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">Total Projects</p>
                    <p className="text-2xl font-bold">{projects.length}</p>
                  </div>
                  <FolderKanban className="h-8 w-8 text-primary opacity-50" />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">Active Projects</p>
                    <p className="text-2xl font-bold">
                      {projects.filter(p => p.status === 'active' || p.status === 'in_progress').length}
                    </p>
                  </div>
                  <TrendingUp className="h-8 w-8 text-green-500 opacity-50" />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">Planning</p>
                    <p className="text-2xl font-bold">
                      {projects.filter(p => p.status === 'planning').length}
                    </p>
                  </div>
                  <Clock className="h-8 w-8 text-yellow-500 opacity-50" />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">Completed</p>
                    <p className="text-2xl font-bold">
                      {projects.filter(p => p.status === 'completed').length}
                    </p>
                  </div>
                  <Sparkles className="h-8 w-8 text-blue-500 opacity-50" />
                </div>
              </CardContent>
            </Card>
          </div>

          {/* AI Agents Tabs */}
          <Card>
            <CardHeader>
              <CardTitle>AI Agents</CardTitle>
              <CardDescription>
                Interact with AI-powered agents to manage your projects and tasks
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                <TabsList className="grid w-full grid-cols-7">
                  <TabsTrigger value="overview">
                    <BrainCircuit className="h-4 w-4 mr-2" />
                    Overview
                  </TabsTrigger>
                  <TabsTrigger value="create-project">
                    <Plus className="h-4 w-4 mr-2" />
                    Create Project
                  </TabsTrigger>
                  <TabsTrigger value="create-task">
                    <Plus className="h-4 w-4 mr-2" />
                    Create Task
                  </TabsTrigger>
                  <TabsTrigger value="project-pilot">
                    <Target className="h-4 w-4 mr-2" />
                    Project Pilot
                  </TabsTrigger>
                  <TabsTrigger value="task-prioritization">
                    <ListChecks className="h-4 w-4 mr-2" />
                    Task Prioritization
                  </TabsTrigger>
                  <TabsTrigger value="knowledge-qa">
                    <MessageSquare className="h-4 w-4 mr-2" />
                    Knowledge Q&A
                  </TabsTrigger>
                  <TabsTrigger value="timeline-gantt">
                    <Calendar className="h-4 w-4 mr-2" />
                    Timeline & Gantt
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="overview" className="mt-6">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <Card>
                      <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                          <Target className="h-5 w-5 text-primary" />
                          Project Pilot
                        </CardTitle>
                        <CardDescription>
                          Create projects, tasks, and manage operations using natural language
                        </CardDescription>
                      </CardHeader>
                      <CardContent>
                        <Button 
                          onClick={() => setActiveTab('project-pilot')}
                          className="w-full"
                        >
                          Open Project Pilot
                        </Button>
                      </CardContent>
                    </Card>

                    <Card>
                      <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                          <ListChecks className="h-5 w-5 text-primary" />
                          Task Prioritization
                        </CardTitle>
                        <CardDescription>
                          Prioritize tasks, find bottlenecks, and suggest delegation strategies
                        </CardDescription>
                      </CardHeader>
                      <CardContent>
                        <Button 
                          onClick={() => setActiveTab('task-prioritization')}
                          className="w-full"
                        >
                          Open Task Prioritization
                        </Button>
                      </CardContent>
                    </Card>

                    <Card>
                      <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                          <MessageSquare className="h-5 w-5 text-primary" />
                          Knowledge Q&A
                        </CardTitle>
                        <CardDescription>
                          Ask questions about your projects and get AI-powered answers
                        </CardDescription>
                      </CardHeader>
                      <CardContent>
                        <Button 
                          onClick={() => setActiveTab('knowledge-qa')}
                          className="w-full"
                        >
                          Open Knowledge Q&A
                        </Button>
                      </CardContent>
                    </Card>

                    <Card>
                      <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                          <Calendar className="h-5 w-5 text-primary" />
                          Timeline & Gantt
                        </CardTitle>
                        <CardDescription>
                          Create timelines, generate Gantt charts, and manage project schedules
                        </CardDescription>
                      </CardHeader>
                      <CardContent>
                        <Button 
                          onClick={() => setActiveTab('timeline-gantt')}
                          className="w-full"
                        >
                          Open Timeline & Gantt
                        </Button>
                      </CardContent>
                    </Card>
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
              </Tabs>
            </CardContent>
          </Card>
          )}
        </main>
      </div>
    </>
  );
};

export default ProjectManagerDashboardPage;

