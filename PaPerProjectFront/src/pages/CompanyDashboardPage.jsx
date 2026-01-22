import React, { useState, useEffect } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import { companyJobsService } from '@/services';
import { companyApi } from '@/services/companyAuthService';
import RecruitmentDashboard from '@/components/recruitment/RecruitmentDashboard';
import { 
  Building2, LogOut, Plus, Briefcase, Users, Eye, 
  Loader2, Search, Calendar, MapPin, Clock, Download, BrainCircuit, FolderKanban,
  ChevronDown, ChevronRight, ListTodo, UserCheck
} from 'lucide-react';

const CompanyDashboardPage = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  
  const [companyUser, setCompanyUser] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [projects, setProjects] = useState([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [activeSection, setActiveSection] = useState('dashboard'); // 'dashboard', 'project-manager', 'recruitment'
  const [activeTab, setActiveTab] = useState('jobs');
  const [showCreateJobModal, setShowCreateJobModal] = useState(false);
  const [selectedJob, setSelectedJob] = useState(null);
  const [selectedJobApplications, setSelectedJobApplications] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, limit: 20, total: 0, totalPages: 0 });
  const [expandedProjects, setExpandedProjects] = useState(new Set());
  const [expandedTasks, setExpandedTasks] = useState(new Set());

  const [jobForm, setJobForm] = useState({
    title: '',
    location: '',
    department: '',
    type: 'Full-time',
    description: '',
    requirements: '',
  });

  useEffect(() => {
    // Get company user from localStorage
    const userStr = localStorage.getItem('company_user');
    if (!userStr) {
      toast({
        title: 'Not logged in',
        description: 'Please log in to access the company dashboard',
        variant: 'destructive',
      });
      navigate('/company/login');
      return;
    }
    
    try {
      const user = JSON.parse(userStr);
      console.log('Company user from localStorage:', user);
      
      // Validate user data
      if (!user.id || !user.companyId) {
        console.error('Invalid company user data:', user);
        toast({
          title: 'Invalid session',
          description: 'Please log in again',
          variant: 'destructive',
        });
        localStorage.removeItem('company_user');
        navigate('/company/login');
        return;
      }
      
      setCompanyUser(user);
      fetchJobs();
      if (activeTab === 'projects') {
        fetchProjects();
      }

      // Check for section parameter in URL
      const urlParams = new URLSearchParams(window.location.search);
      const section = urlParams.get('section');
      if (section === 'recruitment') {
        setActiveSection('recruitment');
      } else if (section === 'project-manager') {
        setActiveSection('project-manager');
      }
    } catch (error) {
      console.error('Error parsing company user:', error);
      localStorage.removeItem('company_user');
      navigate('/company/login');
    }
  }, []);

  const fetchJobs = async () => {
    try {
      setLoading(true);
      console.log('Fetching company jobs...');
      const response = await companyJobsService.getCompanyJobs({
        page: pagination.page,
        limit: pagination.limit,
      });
      console.log('Company jobs response:', response);

      if (response.status === 'success') {
        setJobs(response.data || []);
        setPagination(response.pagination || { page: 1, limit: 20, total: 0, totalPages: 0 });
      } else {
        throw new Error(response.message || 'Failed to load jobs');
      }
    } catch (error) {
      console.error('Error fetching jobs:', error);
      let errorMessage = 'Failed to load jobs';
      
      if (error.isNetworkError) {
        errorMessage = 'Cannot connect to server. Please check if the backend is running on http://localhost:8000';
      } else if (error.data?.message) {
        errorMessage = error.data.message;
      } else if (error.message) {
        errorMessage = error.message;
      }
      
      toast({
        title: 'Error',
        description: errorMessage,
        variant: 'destructive',
      });
      // Set empty jobs array on error so UI shows empty state
      setJobs([]);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateJob = async (e) => {
    e.preventDefault();
    try {
      const response = await companyJobsService.createJobPosition(jobForm);
      if (response.status === 'success') {
        toast({
          title: 'Success!',
          description: 'Job posted successfully',
        });
        setShowCreateJobModal(false);
        setJobForm({
          title: '', location: '', department: '', type: 'Full-time', description: '', requirements: '',
        });
        fetchJobs();
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to create job',
        variant: 'destructive',
      });
    }
  };

  const handleViewApplications = async (jobId) => {
    try {
      const response = await companyJobsService.getJobApplications(jobId);
      if (response.status === 'success') {
        setSelectedJob(jobs.find(j => j.id === jobId));
        setSelectedJobApplications(response.data || []);
        setActiveTab('applications');
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to load applications',
        variant: 'destructive',
      });
    }
  };

  const handleUpdateStatus = async (applicationId, newStatus) => {
    try {
      await companyJobsService.updateApplicationStatus(applicationId, newStatus);
      toast({
        title: 'Success',
        description: 'Application status updated',
      });
      if (selectedJob) {
        handleViewApplications(selectedJob.id);
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to update status',
        variant: 'destructive',
      });
    }
  };

  const fetchProjects = async () => {
    try {
      setProjectsLoading(true);
      const response = await companyApi.get('/company/projects');
      if (response.status === 'success') {
        setProjects(response.data || []);
      } else {
        throw new Error(response.message || 'Failed to load projects');
      }
    } catch (error) {
      console.error('Error fetching projects:', error);
      toast({
        title: 'Error',
        description: error.message || 'Failed to load projects',
        variant: 'destructive',
      });
      setProjects([]);
    } finally {
      setProjectsLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'projects' && companyUser) {
      fetchProjects();
    }
  }, [activeTab, companyUser]);

  const toggleProject = (projectId) => {
    setExpandedProjects(prev => {
      const newSet = new Set(prev);
      if (newSet.has(projectId)) {
        newSet.delete(projectId);
        // Also collapse all tasks in this project when collapsing the project
        setExpandedTasks(prevTasks => {
          const newTaskSet = new Set(prevTasks);
          const project = projects.find(p => p.id === projectId);
          if (project && project.tasks) {
            project.tasks.forEach(task => {
              newTaskSet.delete(task.id);
            });
          }
          return newTaskSet;
        });
      } else {
        newSet.add(projectId);
      }
      return newSet;
    });
  };

  const toggleTaskSubtasks = (taskId, event) => {
    event.stopPropagation(); // Prevent project from toggling
    setExpandedTasks(prev => {
      const newSet = new Set(prev);
      if (newSet.has(taskId)) {
        newSet.delete(taskId);
      } else {
        newSet.add(taskId);
      }
      return newSet;
    });
  };

  const handleLogout = () => {
    localStorage.removeItem('company_auth_token');
    localStorage.removeItem('company_user');
    navigate('/company/login');
  };

  const getResumeUrl = (resumePath) => {
    if (!resumePath) return null;
    const apiBaseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
    return `${apiBaseUrl.replace('/api', '')}/${resumePath}`;
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'pending':
        return 'bg-yellow-100 text-yellow-800';
      case 'reviewing':
        return 'bg-blue-100 text-blue-800';
      case 'interview':
        return 'bg-purple-100 text-purple-800';
      case 'accepted':
        return 'bg-green-100 text-green-800';
      case 'rejected':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  if (!companyUser) {
    return null;
  }

  return (
    <>
      <Helmet>
        <title>Company Dashboard | Pay Per Project</title>
      </Helmet>
      <div className="min-h-screen bg-background overflow-x-hidden">
        {/* Header */}
        <header className="border-b bg-card">
          <div className="container mx-auto px-4 py-4 max-w-7xl">
            <div className="flex justify-between items-center mb-4">
              <div className="flex items-center gap-3">
                <Building2 className="h-8 w-8 text-primary" />
                <div>
                  <h1 className="text-xl font-bold">{companyUser.companyName || 'Company Dashboard'}</h1>
                  <p className="text-sm text-muted-foreground">{companyUser.fullName}</p>
                </div>
              </div>
              <Button variant="outline" onClick={handleLogout}>
                <LogOut className="h-4 w-4 mr-2" />
                Logout
              </Button>
            </div>
            {/* Navigation Tabs */}
            <div className="flex gap-2 border-t pt-4">
              <Button
                variant={activeSection === 'dashboard' ? 'default' : 'ghost'}
                onClick={() => setActiveSection('dashboard')}
                className="flex items-center gap-2"
              >
                <Building2 className="h-4 w-4" />
                Dashboard
              </Button>
              <Button
                variant={activeSection === 'project-manager' ? 'default' : 'ghost'}
                onClick={() => navigate('/project-manager/dashboard')}
                className="flex items-center gap-2"
              >
                <BrainCircuit className="h-4 w-4" />
                Project Manager Agent
              </Button>
              <Button
                variant={activeSection === 'recruitment' ? 'default' : 'ghost'}
                onClick={() => setActiveSection('recruitment')}
                className="flex items-center gap-2"
              >
                <UserCheck className="h-4 w-4" />
                Recruitment Agent
              </Button>
            </div>
          </div>
        </header>

        <div className="container mx-auto px-4 py-8 max-w-7xl w-full overflow-x-hidden">
          {activeSection === 'dashboard' && (
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <div className="flex justify-between items-center mb-6">
              <TabsList>
                <TabsTrigger value="jobs">
                  <Briefcase className="h-4 w-4 mr-2" />
                  My Jobs
                </TabsTrigger>
                <TabsTrigger value="projects">
                  <FolderKanban className="h-4 w-4 mr-2" />
                  Projects
                </TabsTrigger>
                <TabsTrigger value="applications">
                  <Users className="h-4 w-4 mr-2" />
                  Applications
                </TabsTrigger>
              </TabsList>
              {activeTab === 'jobs' && (
                <Button onClick={() => setShowCreateJobModal(true)}>
                  <Plus className="h-4 w-4 mr-2" />
                  Post New Job
                </Button>
              )}
            </div>
            

            <TabsContent value="jobs" className="space-y-4">
              {loading ? (
                <div className="flex justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin" />
                </div>
              ) : jobs.length === 0 ? (
                <Card>
                  <CardContent className="py-12 text-center">
                    <Briefcase className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                    <p className="text-lg font-medium mb-2">No jobs posted yet</p>
                    <Button onClick={() => setShowCreateJobModal(true)}>
                      Post Your First Job
                    </Button>
                  </CardContent>
                </Card>
              ) : (
                <div className="grid gap-4">
                  {jobs.map((job) => (
                    <Card key={job.id}>
                      <CardHeader>
                        <div className="flex justify-between items-start">
                          <div>
                            <CardTitle>{job.title}</CardTitle>
                            <div className="flex gap-4 mt-2 text-sm text-muted-foreground">
                              <span className="flex items-center gap-1">
                                <MapPin className="h-4 w-4" />
                                {job.location}
                              </span>
                              <span className="flex items-center gap-1">
                                <Briefcase className="h-4 w-4" />
                                {job.department}
                              </span>
                              <Badge>{job.type}</Badge>
                            </div>
                          </div>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleViewApplications(job.id)}
                          >
                            <Eye className="h-4 w-4 mr-2" />
                            View Applications
                          </Button>
                        </div>
                      </CardHeader>
                      <CardContent>
                        <p className="text-sm text-muted-foreground line-clamp-2">{job.description}</p>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </TabsContent>

            <TabsContent value="projects" className="space-y-4">
              {projectsLoading ? (
                <div className="flex justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin" />
                </div>
              ) : projects.length === 0 ? (
                <Card>
                  <CardContent className="py-12 text-center">
                    <FolderKanban className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                    <p className="text-lg font-medium mb-2">No projects yet</p>
                    <p className="text-sm text-muted-foreground mb-4">
                      Create projects using the Project Manager Agent
                    </p>
                    <Button onClick={() => navigate('/project-manager/dashboard')}>
                      <BrainCircuit className="h-4 w-4 mr-2" />
                      Go to Project Manager Dashboard
                    </Button>
                  </CardContent>
                </Card>
              ) : (
                <div className="space-y-4">
                  {projects.map((project) => {
                    const isExpanded = expandedProjects.has(project.id);
                    return (
                      <Card key={project.id} className="cursor-pointer hover:shadow-md transition-shadow">
                        <CardHeader 
                          onClick={() => toggleProject(project.id)}
                          className="pb-3"
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3 flex-1">
                              <div className="flex-shrink-0">
                                {isExpanded ? (
                                  <ChevronDown className="h-5 w-5 text-muted-foreground" />
                                ) : (
                                  <ChevronRight className="h-5 w-5 text-muted-foreground" />
                                )}
                              </div>
                              <div className="flex-1 min-w-0">
                                <CardTitle className="text-lg">{project.name}</CardTitle>
                                <div className="mt-2 flex items-center gap-3 flex-wrap">
                                  <Badge variant={project.status === 'active' ? 'default' : 'secondary'}>
                                    {project.status}
                                  </Badge>
                                  <Badge variant="outline">{project.priority}</Badge>
                                  <span className="text-sm text-muted-foreground flex items-center gap-1">
                                    <ListTodo className="h-3 w-3" />
                                    {project.tasks_count} task{project.tasks_count !== 1 ? 's' : ''}
                                  </span>
                                  {project.created_at && (
                                    <span className="text-sm text-muted-foreground flex items-center gap-1">
                                      <Calendar className="h-3 w-3" />
                                      {new Date(project.created_at).toLocaleDateString()}
                                    </span>
                                  )}
                                </div>
                                {project.description && !isExpanded && (
                                  <p className="text-sm text-muted-foreground mt-2 line-clamp-2">
                                    {project.description}
                                  </p>
                                )}
                              </div>
                            </div>
                          </div>
                        </CardHeader>
                        {isExpanded && (
                          <CardContent className="pt-0">
                            {project.description && (
                              <p className="text-sm text-muted-foreground mb-4 pb-4 border-b">
                                {project.description}
                              </p>
                            )}
                            {project.tasks && project.tasks.length > 0 ? (
                              <div className="space-y-3">
                                <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                                  <ListTodo className="h-4 w-4" />
                                  Tasks ({project.tasks.length})
                                </h4>
                                {project.tasks.map((task) => {
                                  const hasSubtasks = task.subtasks && task.subtasks.length > 0;
                                  const showSubtasks = expandedTasks.has(task.id);
                                  return (
                                    <div 
                                      key={task.id} 
                                      className="border-l-2 border-primary pl-4 py-3 bg-muted/30 rounded-r"
                                    >
                                      <div className="flex items-start justify-between gap-3">
                                        <div className="flex-1 min-w-0">
                                          <p className="font-medium">{task.title}</p>
                                          {task.description && (
                                            <p className="text-sm text-muted-foreground mt-1">
                                              {task.description}
                                            </p>
                                          )}
                                          {task.due_date && (
                                            <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
                                              <Clock className="h-3 w-3" />
                                              Due: {new Date(task.due_date).toLocaleDateString()}
                                            </p>
                                          )}
                                        </div>
                                        <div className="flex items-center gap-2 flex-shrink-0">
                                          <Badge variant="outline" className="text-xs">
                                            {task.status}
                                          </Badge>
                                          <Badge variant="secondary" className="text-xs">
                                            {task.priority}
                                          </Badge>
                                          {hasSubtasks && (
                                            <Button
                                              variant="ghost"
                                              size="sm"
                                              onClick={(e) => toggleTaskSubtasks(task.id, e)}
                                              className="h-7 px-2 text-xs"
                                            >
                                              {showSubtasks ? (
                                                <>
                                                  <ChevronDown className="h-3 w-3 mr-1" />
                                                  Hide ({task.subtasks.length})
                                                </>
                                              ) : (
                                                <>
                                                  <ChevronRight className="h-3 w-3 mr-1" />
                                                  View ({task.subtasks.length})
                                                </>
                                              )}
                                            </Button>
                                          )}
                                        </div>
                                      </div>
                                      {hasSubtasks && showSubtasks && (
                                        <div className="mt-3 ml-2 space-y-2 pl-4 border-l-2 border-muted">
                                          <p className="text-xs font-medium text-muted-foreground mb-2">
                                            Subtasks ({task.subtasks.length}):
                                          </p>
                                          {task.subtasks.map((subtask) => (
                                            <div 
                                              key={subtask.id} 
                                              className="flex items-center gap-2 text-sm bg-background p-2 rounded"
                                            >
                                              <span className="text-primary">•</span>
                                              <span className="flex-1">{subtask.title}</span>
                                              {subtask.description && (
                                                <span className="text-xs text-muted-foreground hidden md:block">
                                                  {subtask.description}
                                                </span>
                                              )}
                                              <Badge variant="outline" className="text-xs">
                                                {subtask.status}
                                              </Badge>
                                            </div>
                                          ))}
                                        </div>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            ) : (
                              <div className="text-center py-8 text-muted-foreground">
                                <ListTodo className="h-8 w-8 mx-auto mb-2 opacity-50" />
                                <p className="text-sm">No tasks yet</p>
                              </div>
                            )}
                          </CardContent>
                        )}
                      </Card>
                    );
                  })}
                </div>
              )}
            </TabsContent>

            <TabsContent value="applications" className="space-y-4">
              {selectedJob ? (
                <div>
                  <div className="flex justify-between items-center mb-4">
                    <h2 className="text-2xl font-bold">Applications for {selectedJob.title}</h2>
                    <Button variant="outline" onClick={() => setSelectedJob(null)}>
                      Back to Jobs
                    </Button>
                  </div>
                  {selectedJobApplications.length === 0 ? (
                    <Card>
                      <CardContent className="py-12 text-center">
                        <Users className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                        <p className="text-lg font-medium">No applications yet</p>
                      </CardContent>
                    </Card>
                  ) : (
                    <div className="space-y-4">
                      {selectedJobApplications.map((app) => (
                        <Card key={app.id}>
                          <CardHeader>
                            <div className="flex justify-between items-start">
                              <div>
                                <CardTitle>{app.applicant_name}</CardTitle>
                                <CardDescription>{app.email}</CardDescription>
                              </div>
                              <Badge className={getStatusColor(app.status)}>{app.status}</Badge>
                            </div>
                          </CardHeader>
                          <CardContent>
                            <div className="space-y-2">
                              {app.cover_letter && (
                                <p className="text-sm">{app.cover_letter}</p>
                              )}
                              {app.resume_path && (
                                <a
                                  href={getResumeUrl(app.resume_path)}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-2 text-sm text-primary hover:underline"
                                >
                                  <Download className="h-4 w-4" />
                                  Download Resume
                                </a>
                              )}
                              <div className="flex gap-2 pt-2">
                                {['pending', 'reviewing', 'interview', 'accepted', 'rejected'].map((status) => (
                                  <Button
                                    key={status}
                                    variant={app.status === status ? 'default' : 'outline'}
                                    size="sm"
                                    onClick={() => handleUpdateStatus(app.id, status)}
                                    disabled={app.status === status}
                                    className="capitalize"
                                  >
                                    {status}
                                  </Button>
                                ))}
                              </div>
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <Card>
                  <CardContent className="py-12 text-center">
                    <Users className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                    <p className="text-lg font-medium">Select a job to view applications</p>
                  </CardContent>
                </Card>
              )}
            </TabsContent>
          </Tabs>
          )}

          {activeSection === 'project-manager' && (
            <div className="text-center py-12">
              <BrainCircuit className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
              <p className="text-lg font-medium mb-2">Project Manager Agent</p>
              <p className="text-sm text-muted-foreground mb-4">
                Click the button below to access the Project Manager Dashboard
              </p>
              <Button onClick={() => navigate('/project-manager/dashboard')}>
                <BrainCircuit className="h-4 w-4 mr-2" />
                Go to Project Manager Dashboard
              </Button>
            </div>
          )}

          {activeSection === 'recruitment' && (
            <RecruitmentDashboard />
          )}
        </div>

        {/* Create Job Modal */}
        <Dialog open={showCreateJobModal} onOpenChange={setShowCreateJobModal}>
          <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Post New Job</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleCreateJob} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="title">Job Title *</Label>
                <Input
                  id="title"
                  value={jobForm.title}
                  onChange={(e) => setJobForm({ ...jobForm, title: e.target.value })}
                  required
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="location">Location *</Label>
                  <Input
                    id="location"
                    value={jobForm.location}
                    onChange={(e) => setJobForm({ ...jobForm, location: e.target.value })}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="department">Department *</Label>
                  <Input
                    id="department"
                    value={jobForm.department}
                    onChange={(e) => setJobForm({ ...jobForm, department: e.target.value })}
                    required
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="type">Job Type *</Label>
                <Select value={jobForm.type} onValueChange={(value) => setJobForm({ ...jobForm, type: value })}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Full-time">Full-time</SelectItem>
                    <SelectItem value="Part-time">Part-time</SelectItem>
                    <SelectItem value="Contract">Contract</SelectItem>
                    <SelectItem value="Internship">Internship</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="description">Job Description *</Label>
                <Textarea
                  id="description"
                  value={jobForm.description}
                  onChange={(e) => setJobForm({ ...jobForm, description: e.target.value })}
                  required
                  className="min-h-[100px]"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="requirements">Requirements</Label>
                <Textarea
                  id="requirements"
                  value={jobForm.requirements}
                  onChange={(e) => setJobForm({ ...jobForm, requirements: e.target.value })}
                  className="min-h-[100px]"
                />
              </div>
              <div className="flex gap-2 pt-4">
                <Button type="submit" className="flex-1">
                  Post Job
                </Button>
                <Button type="button" variant="outline" onClick={() => setShowCreateJobModal(false)}>
                  Cancel
                </Button>
              </div>
            </form>
          </DialogContent>
        </Dialog>
      </div>
    </>
  );
};

export default CompanyDashboardPage;

