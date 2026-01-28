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
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import { companyJobsService } from '@/services';
import { companyApi } from '@/services/companyAuthService';
import { getPurchasedModules } from '@/services/modulePurchaseService';
import companyUserManagementService from '@/services/companyUserManagementService';
import companyProjectsTasksService from '@/services/companyProjectsTasksService';
import DashboardNavbar from '@/components/common/DashboardNavbar';
import { 
  Building2, Plus, Briefcase, Users, Eye, 
  Loader2, Search, Calendar, MapPin, Clock, Download, BrainCircuit, FolderKanban,
  ChevronDown, ChevronRight, ListTodo, UserCheck, Megaphone, UserPlus, Edit, Trash2, Mail,
  CheckCircle2, Circle, PlayCircle, AlertCircle, FileCheck, TrendingUp, User
} from 'lucide-react';

const CompanyDashboardPage = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  
  const [companyUser, setCompanyUser] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [projects, setProjects] = useState([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [activeSection, setActiveSection] = useState('dashboard'); // 'dashboard', 'project-manager'
  const [activeTab, setActiveTab] = useState('jobs');
  const [showCreateJobModal, setShowCreateJobModal] = useState(false);
  const [selectedJob, setSelectedJob] = useState(null);
  const [selectedJobApplications, setSelectedJobApplications] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, limit: 20, total: 0, totalPages: 0 });
  const [expandedProjects, setExpandedProjects] = useState(new Set());
  const [expandedTasks, setExpandedTasks] = useState(new Set());
  const [purchasedModules, setPurchasedModules] = useState([]);
  
  // User management state
  const [users, setUsers] = useState([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [showCreateUserModal, setShowCreateUserModal] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [userSearchQuery, setUserSearchQuery] = useState('');
  const [userForm, setUserForm] = useState({
    email: '',
    password: '',
    username: '',
    fullName: '',
    role: 'team_member',
    phoneNumber: '',
    bio: '',
    location: '',
  });
  
  // All users tasks state
  const [allUsersTasks, setAllUsersTasks] = useState([]);
  const [allUsersTasksLoading, setAllUsersTasksLoading] = useState(false);
  const [taskStatusFilter, setTaskStatusFilter] = useState('all');
  const [taskUserFilter, setTaskUserFilter] = useState('all');
  
  // Project and Task editing state
  const [editingProject, setEditingProject] = useState(null);
  const [editingTask, setEditingTask] = useState(null);
  const [showEditProjectModal, setShowEditProjectModal] = useState(false);
  const [showEditTaskModal, setShowEditTaskModal] = useState(false);
  const [projectForm, setProjectForm] = useState({
    name: '',
    description: '',
    status: 'active',
    priority: 'medium',
    project_type: 'web_app',
  });
  const [taskForm, setTaskForm] = useState({
    title: '',
    description: '',
    priority: 'medium',
    status: 'todo',
    assignee_id: '',
  });
  const [availableUsers, setAvailableUsers] = useState([]);

  const [jobForm, setJobForm] = useState({
    title: '',
    location: '',
    department: '',
    type: 'Full-time',
    description: '',
    requirements: '',
  });

  const fetchPurchasedModules = async () => {
    try {
      // Try to get from localStorage first (cache)
      const cachedModules = localStorage.getItem('company_purchased_modules');
      if (cachedModules) {
        try {
          const cached = JSON.parse(cachedModules);
          setPurchasedModules(cached);
        } catch (e) {
          // Invalid cache, continue to fetch
        }
      }

      const response = await getPurchasedModules();
      if (response.status === 'success') {
        const moduleNames = response.module_names || [];
        setPurchasedModules(moduleNames);
        // Cache in localStorage
        localStorage.setItem('company_purchased_modules', JSON.stringify(moduleNames));
      }
    } catch (error) {
      console.error('Error fetching purchased modules:', error);
      // If we have cached modules, use them
      const cachedModules = localStorage.getItem('company_purchased_modules');
      if (cachedModules) {
        try {
          const cached = JSON.parse(cachedModules);
          setPurchasedModules(cached);
        } catch (e) {
          setPurchasedModules([]);
        }
      } else {
        setPurchasedModules([]);
      }
    }
  };

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
      
      // Load cached modules immediately
      const cachedModules = localStorage.getItem('company_purchased_modules');
      if (cachedModules) {
        try {
          const cached = JSON.parse(cachedModules);
          setPurchasedModules(cached);
        } catch (e) {
          // Invalid cache
        }
      }
      
      fetchJobs();
      fetchPurchasedModules(); // Will update cache
      if (activeTab === 'projects') {
        fetchProjects();
      }

      // Check for section parameter in URL (legacy support - redirect to new routes)
      const urlParams = new URLSearchParams(window.location.search);
      const section = urlParams.get('section');
      if (section === 'recruitment') {
        // Redirect to recruitment dashboard
        navigate('/recruitment/dashboard', { replace: true });
        return;
      } else if (section === 'project-manager') {
        // Redirect to project manager dashboard
        navigate('/project-manager/dashboard', { replace: true });
        return;
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

  const fetchAvailableUsers = async () => {
    try {
      const response = await companyProjectsTasksService.getUsersForAssignment();
      if (response.status === 'success') {
        setAvailableUsers(response.data || []);
      }
    } catch (error) {
      console.error('Error fetching users for assignment:', error);
    }
  };

  const handleEditProject = (project) => {
    setEditingProject(project);
    setProjectForm({
      name: project.name || '',
      description: project.description || '',
      status: project.status || 'active',
      priority: project.priority || 'medium',
      project_type: project.project_type || 'web_app',
    });
    setShowEditProjectModal(true);
  };

  const handleUpdateProject = async (e) => {
    e.preventDefault();
    if (!editingProject) return;
    
    try {
      const response = await companyProjectsTasksService.updateProject(editingProject.id, projectForm);
      if (response.status === 'success') {
        toast({
          title: 'Success',
          description: 'Project updated successfully',
        });
        setShowEditProjectModal(false);
        setEditingProject(null);
        fetchProjects();
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to update project',
        variant: 'destructive',
      });
    }
  };

  const handleEditTask = (task) => {
    setEditingTask(task);
    // Convert null/undefined assignee_id to "none" for the select
    // Handle both assignee_id (from serializer) and assignee.id (if assignee object exists)
    const assigneeId = task.assignee_id || (task.assignee && task.assignee.id) || null;
    const assigneeIdString = assigneeId ? assigneeId.toString() : 'none';
    setTaskForm({
      title: task.title || '',
      description: task.description || '',
      priority: task.priority || 'medium',
      status: task.status || 'todo',
      assignee_id: assigneeIdString,
    });
    // Fetch users if not already loaded
    if (availableUsers.length === 0) {
      fetchAvailableUsers();
    }
    setShowEditTaskModal(true);
  };

  const handleUpdateTask = async (e) => {
    e.preventDefault();
    if (!editingTask) return;
    
    try {
      // Convert "none" to null for unassigning
      const assigneeId = taskForm.assignee_id === 'none' || taskForm.assignee_id === '' ? null : taskForm.assignee_id;
      
      const response = await companyProjectsTasksService.updateTask(editingTask.id, {
        ...taskForm,
        assignee_id: assigneeId,
      });
      if (response.status === 'success') {
        toast({
          title: 'Success',
          description: 'Task updated successfully',
        });
        setShowEditTaskModal(false);
        setEditingTask(null);
        // Refresh both projects and all users tasks
        fetchProjects();
        if (activeTab === 'all-tasks') {
          fetchAllUsersTasks();
        }
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to update task',
        variant: 'destructive',
      });
    }
  };

  useEffect(() => {
    if (activeTab === 'projects' && companyUser) {
      fetchProjects();
    }
    if (activeTab === 'users' && companyUser) {
      fetchUsers();
    }
    if (activeTab === 'all-tasks' && companyUser) {
      fetchAllUsersTasks();
    }
  }, [activeTab, companyUser, taskStatusFilter, taskUserFilter]);
  
  const fetchAllUsersTasks = async () => {
    try {
      setAllUsersTasksLoading(true);
      const params = {};
      if (taskStatusFilter !== 'all') {
        params.status = taskStatusFilter;
      }
      if (taskUserFilter !== 'all') {
        params.user_id = taskUserFilter;
      }
      
      const queryParams = new URLSearchParams(params);
      const queryString = queryParams.toString();
      const endpoint = `/company/users/tasks${queryString ? `?${queryString}` : ''}`;
      
      const response = await companyApi.get(endpoint);
      if (response.status === 'success') {
        setAllUsersTasks(response.data || []);
      } else {
        throw new Error(response.message || 'Failed to load tasks');
      }
    } catch (error) {
      console.error('Error fetching all users tasks:', error);
      toast({
        title: 'Error',
        description: error.message || 'Failed to load tasks',
        variant: 'destructive',
      });
      setAllUsersTasks([]);
    } finally {
      setAllUsersTasksLoading(false);
    }
  };
  
  const fetchUsers = async () => {
    try {
      setUsersLoading(true);
      const response = await companyUserManagementService.listUsers({ page: 1, limit: 50 });
      if (response.status === 'success') {
        setUsers(response.data || []);
      } else {
        throw new Error(response.message || 'Failed to load users');
      }
    } catch (error) {
      console.error('Error fetching users:', error);
      toast({
        title: 'Error',
        description: error.message || 'Failed to load users',
        variant: 'destructive',
      });
      setUsers([]);
    } finally {
      setUsersLoading(false);
    }
  };
  
  const handleCreateUser = async () => {
    try {
      if (!userForm.email || !userForm.password) {
        toast({
          title: 'Validation Error',
          description: 'Email and password are required',
          variant: 'destructive',
        });
        return;
      }
      
      const response = await companyUserManagementService.createUser(userForm);
      if (response.status === 'success') {
        toast({
          title: 'Success!',
          description: 'User created successfully',
        });
        setShowCreateUserModal(false);
        setUserForm({
          email: '', password: '', username: '', fullName: '', role: 'team_member',
          phoneNumber: '', bio: '', location: '',
        });
        fetchUsers();
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to create user',
        variant: 'destructive',
      });
    }
  };
  
  const handleEditUser = (user) => {
    setEditingUser(user);
    setUserForm({
      email: user.email || '',
      password: '', // Don't pre-fill password
      username: user.username || '',
      fullName: user.full_name || '',
      role: user.role || 'team_member',
      phoneNumber: user.phone_number || '',
      bio: user.bio || '',
      location: user.location || '',
    });
    setShowCreateUserModal(true);
  };
  
  const handleUpdateUser = async () => {
    try {
      if (!editingUser) return;
      
      const response = await companyUserManagementService.updateUser(editingUser.id, userForm);
      if (response.status === 'success') {
        toast({
          title: 'Success!',
          description: 'User updated successfully',
        });
        setShowCreateUserModal(false);
        setEditingUser(null);
        setUserForm({
          email: '', password: '', username: '', fullName: '', role: 'team_member',
          phoneNumber: '', bio: '', location: '',
        });
        fetchUsers();
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to update user',
        variant: 'destructive',
      });
    }
  };
  
  const handleDeleteUser = async (userId) => {
    if (!window.confirm('Are you sure you want to deactivate this user?')) {
      return;
    }
    
    try {
      const response = await companyUserManagementService.deleteUser(userId);
      if (response.status === 'success') {
        toast({
          title: 'Success!',
          description: 'User deactivated successfully',
        });
        fetchUsers();
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to deactivate user',
        variant: 'destructive',
      });
    }
  };

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
      // Task statuses
      case 'done':
        return 'bg-green-100 text-green-800';
      case 'in_progress':
        return 'bg-blue-100 text-blue-800';
      case 'review':
        return 'bg-purple-100 text-purple-800';
      case 'blocked':
        return 'bg-red-100 text-red-800';
      case 'todo':
        return 'bg-gray-100 text-gray-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'done':
        return <CheckCircle2 className="h-4 w-4 text-green-600" />;
      case 'in_progress':
        return <PlayCircle className="h-4 w-4 text-blue-600" />;
      case 'review':
        return <FileCheck className="h-4 w-4 text-purple-600" />;
      case 'blocked':
        return <AlertCircle className="h-4 w-4 text-red-600" />;
      default:
        return <Circle className="h-4 w-4 text-gray-600" />;
    }
  };

  const getPriorityColor = (priority) => {
    switch (priority) {
      case 'high':
        return 'bg-red-100 text-red-800';
      case 'medium':
        return 'bg-yellow-100 text-yellow-800';
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
        <DashboardNavbar
          icon={Building2}
          title={companyUser.companyName || 'Company Dashboard'}
          subtitle={companyUser.fullName}
          user={companyUser}
          userRole="Company User"
          showNavTabs={true}
          activeSection={activeSection}
          onLogout={handleLogout}
          navItems={[
            {
              label: 'Dashboard',
              icon: Building2,
              section: 'dashboard',
              onClick: () => setActiveSection('dashboard'),
            },
            // Only show Project Manager Agent if purchased
            ...(purchasedModules.includes('project_manager_agent') ? [{
              label: 'Project Manager Agent',
              icon: BrainCircuit,
              section: 'project-manager',
              onClick: () => navigate('/project-manager/dashboard'),
            }] : []),
            // Only show Recruitment Agent if purchased
            ...(purchasedModules.includes('recruitment_agent') ? [{
              label: 'Recruitment Agent',
              icon: UserCheck,
              section: 'recruitment',
              onClick: () => navigate('/recruitment/dashboard'),
            }] : []),
            // Only show Marketing Agent if purchased
            ...(purchasedModules.includes('marketing_agent') ? [{
              label: 'Marketing Agent',
              icon: Megaphone,
              section: 'marketing',
              onClick: () => navigate('/marketing/dashboard'),
            }] : []),
          ]}
        />

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
                <TabsTrigger value="users">
                  <UserCheck className="h-4 w-4 mr-2" />
                  Users
                </TabsTrigger>
                <TabsTrigger value="all-tasks">
                  <ListTodo className="h-4 w-4 mr-2" />
                  All Users Tasks
                </TabsTrigger>
              </TabsList>
              {activeTab === 'jobs' && (
                <Button onClick={() => setShowCreateJobModal(true)}>
                  <Plus className="h-4 w-4 mr-2" />
                  Post New Job
                </Button>
              )}
              {activeTab === 'users' && (
                <Button onClick={() => {
                  setEditingUser(null);
                  setUserForm({
                    email: '', password: '', username: '', fullName: '', role: 'team_member',
                    phoneNumber: '', bio: '', location: '',
                  });
                  setShowCreateUserModal(true);
                }}>
                  <UserPlus className="h-4 w-4 mr-2" />
                  Add User
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
                                <div className="flex items-center justify-between gap-2">
                                  <CardTitle className="text-lg">{project.name}</CardTitle>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleEditProject(project);
                                    }}
                                    className="h-8 w-8 p-0"
                                  >
                                    <Edit className="h-4 w-4" />
                                  </Button>
                                </div>
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
                                          <div className="flex items-center gap-2">
                                            <p className="font-medium">{task.title}</p>
                                            <Button
                                              variant="ghost"
                                              size="sm"
                                              onClick={(e) => {
                                                e.stopPropagation();
                                                handleEditTask(task);
                                              }}
                                              className="h-6 w-6 p-0"
                                            >
                                              <Edit className="h-3 w-3" />
                                            </Button>
                                          </div>
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
            
            <TabsContent value="users" className="space-y-4">
              {/* Search Bar */}
              {users.length > 0 && (
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      placeholder="Search users by name, email, or role..."
                      value={userSearchQuery}
                      onChange={(e) => setUserSearchQuery(e.target.value)}
                      className="pl-10"
                    />
                  </div>
                </div>
              )}
              
              {usersLoading ? (
                <div className="flex justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin" />
                </div>
              ) : users.length === 0 ? (
                <Card>
                  <CardContent className="py-12 text-center">
                    <UserCheck className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                    <p className="text-lg font-medium mb-2">No users yet</p>
                    <p className="text-sm text-muted-foreground mb-4">
                      Add users to your company to manage projects and tasks
                    </p>
                    <Button onClick={() => {
                      setEditingUser(null);
                      setUserForm({
                        email: '', password: '', username: '', fullName: '', role: 'team_member',
                        phoneNumber: '', bio: '', location: '',
                      });
                      setShowCreateUserModal(true);
                    }}>
                      <UserPlus className="h-4 w-4 mr-2" />
                      Add Your First User
                    </Button>
                  </CardContent>
                </Card>
              ) : (() => {
                // Filter users based on search query
                const filteredUsers = users.filter(user => {
                  if (!userSearchQuery) return true;
                  const query = userSearchQuery.toLowerCase();
                  return (
                    (user.full_name && user.full_name.toLowerCase().includes(query)) ||
                    (user.username && user.username.toLowerCase().includes(query)) ||
                    (user.email && user.email.toLowerCase().includes(query)) ||
                    (user.role && user.role.toLowerCase().includes(query))
                  );
                });
                
                if (filteredUsers.length === 0) {
                  return (
                    <Card>
                      <CardContent className="py-12 text-center">
                        <Search className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                        <p className="text-lg font-medium mb-2">No users found</p>
                        <p className="text-sm text-muted-foreground">
                          Try adjusting your search query
                        </p>
                      </CardContent>
                    </Card>
                  );
                }
                
                return (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <p className="text-sm text-muted-foreground">
                        Showing {filteredUsers.length} of {users.length} user{users.length !== 1 ? 's' : ''}
                      </p>
                    </div>
                    <div className="grid gap-4">
                      {filteredUsers.map((user) => (
                        <Card key={user.id} className="hover:shadow-md transition-shadow">
                          <CardHeader>
                            <div className="flex justify-between items-start">
                              <div className="flex-1">
                                <div className="flex items-center gap-2 mb-2">
                                  <CardTitle className="text-lg">{user.full_name || user.username}</CardTitle>
                                  {user.is_active === false && (
                                    <Badge variant="secondary" className="text-xs">Inactive</Badge>
                                  )}
                                </div>
                                <div className="flex flex-wrap gap-3 mt-2 text-sm text-muted-foreground">
                                  <span className="flex items-center gap-1">
                                    <Mail className="h-4 w-4" />
                                    {user.email}
                                  </span>
                                  <Badge variant="outline" className="capitalize">
                                    {user.role?.replace('_', ' ')}
                                  </Badge>
                                  {user.location && (
                                    <span className="flex items-center gap-1">
                                      <MapPin className="h-4 w-4" />
                                      {user.location}
                                    </span>
                                  )}
                                  {user.phone_number && (
                                    <span className="flex items-center gap-1">
                                      <Clock className="h-4 w-4" />
                                      {user.phone_number}
                                    </span>
                                  )}
                                </div>
                                {user.created_by_company_user_name && (
                                  <p className="text-xs text-muted-foreground mt-2">
                                    Created by: <span className="font-medium">{user.created_by_company_user_name}</span>
                                  </p>
                                )}
                                {user.date_joined && (
                                  <p className="text-xs text-muted-foreground mt-1">
                                    Joined: {new Date(user.date_joined).toLocaleDateString()}
                                  </p>
                                )}
                              </div>
                              <div className="flex gap-2 ml-4">
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => handleEditUser(user)}
                                  className="flex items-center gap-1"
                                >
                                  <Edit className="h-4 w-4" />
                                  Edit
                                </Button>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => handleDeleteUser(user.id)}
                                  className="text-red-600 hover:text-red-700 hover:bg-red-50"
                                >
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              </div>
                            </div>
                          </CardHeader>
                          {user.bio && (
                            <CardContent>
                              <p className="text-sm text-muted-foreground line-clamp-2">{user.bio}</p>
                            </CardContent>
                          )}
                        </Card>
                      ))}
                    </div>
                  </div>
                );
              })()}
            </TabsContent>

            <TabsContent value="all-tasks" className="space-y-4">
              {/* Filters */}
              <div className="flex items-center gap-4">
                <Select value={taskStatusFilter} onValueChange={setTaskStatusFilter}>
                  <SelectTrigger className="w-[180px]">
                    <SelectValue placeholder="Filter by status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Statuses</SelectItem>
                    <SelectItem value="todo">To Do</SelectItem>
                    <SelectItem value="in_progress">In Progress</SelectItem>
                    <SelectItem value="review">Review</SelectItem>
                    <SelectItem value="done">Done</SelectItem>
                    <SelectItem value="blocked">Blocked</SelectItem>
                  </SelectContent>
                </Select>
                
                <Select value={taskUserFilter} onValueChange={setTaskUserFilter}>
                  <SelectTrigger className="w-[180px]">
                    <SelectValue placeholder="Filter by user" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Users</SelectItem>
                    {users.map((user) => (
                      <SelectItem key={user.id} value={user.id.toString()}>
                        {user.full_name || user.username}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {allUsersTasksLoading ? (
                <div className="flex justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin" />
                </div>
              ) : allUsersTasks.length === 0 ? (
                <Card>
                  <CardContent className="py-12 text-center">
                    <ListTodo className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                    <p className="text-lg font-medium mb-2">No tasks found</p>
                    <p className="text-sm text-muted-foreground">
                      {taskStatusFilter !== 'all' || taskUserFilter !== 'all'
                        ? 'No tasks match the selected filters'
                        : 'No tasks have been assigned to your users yet'}
                    </p>
                  </CardContent>
                </Card>
              ) : (
                <div className="grid gap-4">
                  {allUsersTasks.map((task) => (
                    <Card key={task.id} className="hover:shadow-md transition-shadow">
                      <CardHeader>
                        <div className="flex justify-between items-start">
                          <div className="flex-1">
                            <div className="flex items-center justify-between gap-2 mb-2">
                              <CardTitle className="text-lg">{task.title}</CardTitle>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleEditTask(task)}
                                className="h-8 w-8 p-0"
                              >
                                <Edit className="h-4 w-4" />
                              </Button>
                            </div>
                            {task.description && (
                              <p className="text-sm text-muted-foreground mb-3 line-clamp-2">
                                {task.description}
                              </p>
                            )}
                            <div className="flex flex-wrap gap-2 items-center">
                              <Badge className={getStatusColor(task.status)}>
                                {getStatusIcon(task.status)}
                                <span className="ml-1 capitalize">{task.status.replace('_', ' ')}</span>
                              </Badge>
                              <Badge variant="outline" className={getPriorityColor(task.priority)}>
                                {task.priority} Priority
                              </Badge>
                              <span className="text-sm text-muted-foreground flex items-center gap-1">
                                <FolderKanban className="h-4 w-4" />
                                {task.project_name}
                              </span>
                              {task.assignee_name && (
                                <span className="text-sm text-muted-foreground flex items-center gap-1">
                                  <User className="h-4 w-4" />
                                  {task.assignee_name}
                                </span>
                              )}
                              {task.due_date && (
                                <span className="text-sm text-muted-foreground flex items-center gap-1">
                                  <Calendar className="h-4 w-4" />
                                  {new Date(task.due_date).toLocaleDateString()}
                                </span>
                              )}
                              {task.progress_percentage !== null && (
                                <span className="text-sm text-muted-foreground flex items-center gap-1">
                                  <TrendingUp className="h-4 w-4" />
                                  {task.progress_percentage}% complete
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </CardHeader>
                    </Card>
                  ))}
                </div>
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
        
        {/* Create/Edit User Modal */}
        <Dialog open={showCreateUserModal} onOpenChange={(open) => {
          setShowCreateUserModal(open);
          if (!open) {
            setEditingUser(null);
            setUserForm({
              email: '', password: '', username: '', fullName: '', role: 'team_member',
              phoneNumber: '', bio: '', location: '',
            });
          }
        }}>
          <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{editingUser ? 'Edit User' : 'Add New User'}</DialogTitle>
            </DialogHeader>
            <form onSubmit={(e) => {
              e.preventDefault();
              if (editingUser) {
                handleUpdateUser();
              } else {
                handleCreateUser();
              }
            }} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="email">Email *</Label>
                  <Input
                    id="email"
                    type="email"
                    value={userForm.email}
                    onChange={(e) => setUserForm({ ...userForm, email: e.target.value })}
                    required
                    disabled={!!editingUser}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="username">Username</Label>
                  <Input
                    id="username"
                    value={userForm.username}
                    onChange={(e) => setUserForm({ ...userForm, username: e.target.value })}
                    placeholder="Auto-generated from email if not provided"
                  />
                </div>
              </div>
              
              {!editingUser && (
                <div className="space-y-2">
                  <Label htmlFor="password">Password *</Label>
                  <Input
                    id="password"
                    type="password"
                    value={userForm.password}
                    onChange={(e) => setUserForm({ ...userForm, password: e.target.value })}
                    required
                    minLength={6}
                  />
                </div>
              )}
              
              {editingUser && (
                <div className="space-y-2">
                  <Label htmlFor="password">New Password (leave blank to keep current)</Label>
                  <Input
                    id="password"
                    type="password"
                    value={userForm.password}
                    onChange={(e) => setUserForm({ ...userForm, password: e.target.value })}
                    minLength={6}
                  />
                </div>
              )}
              
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="fullName">Full Name</Label>
                  <Input
                    id="fullName"
                    value={userForm.fullName}
                    onChange={(e) => setUserForm({ ...userForm, fullName: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="role">Role *</Label>
                  <Select
                    value={userForm.role}
                    onValueChange={(value) => setUserForm({ ...userForm, role: value })}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select role" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="project_manager">Project Manager</SelectItem>
                      <SelectItem value="team_member">Team Member</SelectItem>
                      <SelectItem value="developer">Developer</SelectItem>
                      <SelectItem value="viewer">Viewer</SelectItem>
                      <SelectItem value="internee">Internee</SelectItem>
                      <SelectItem value="designer">Designer</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="phoneNumber">Phone Number</Label>
                  <Input
                    id="phoneNumber"
                    value={userForm.phoneNumber}
                    onChange={(e) => setUserForm({ ...userForm, phoneNumber: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="location">Location</Label>
                  <Input
                    id="location"
                    value={userForm.location}
                    onChange={(e) => setUserForm({ ...userForm, location: e.target.value })}
                  />
                </div>
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="bio">Bio</Label>
                <Textarea
                  id="bio"
                  value={userForm.bio}
                  onChange={(e) => setUserForm({ ...userForm, bio: e.target.value })}
                  rows={3}
                />
              </div>
              
              <div className="flex justify-end gap-2 pt-4">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setShowCreateUserModal(false);
                    setEditingUser(null);
                    setUserForm({
                      email: '', password: '', username: '', fullName: '', role: 'team_member',
                      phoneNumber: '', bio: '', location: '',
                    });
                  }}
                >
                  Cancel
                </Button>
                <Button type="submit">
                  {editingUser ? 'Update User' : 'Create User'}
                </Button>
              </div>
            </form>
          </DialogContent>
        </Dialog>

        {/* Edit Project Modal */}
        <Dialog open={showEditProjectModal} onOpenChange={(open) => {
          setShowEditProjectModal(open);
          if (!open) {
            setEditingProject(null);
            setProjectForm({
              name: '',
              description: '',
              status: 'active',
              priority: 'medium',
              project_type: 'web_app',
            });
          }
        }}>
          <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Edit Project</DialogTitle>
              <DialogDescription>
                Update project details. Changes will be saved immediately.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleUpdateProject} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="project-name">Project Name *</Label>
                <Input
                  id="project-name"
                  value={projectForm.name}
                  onChange={(e) => setProjectForm({ ...projectForm, name: e.target.value })}
                  required
                />
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="project-description">Description</Label>
                <Textarea
                  id="project-description"
                  value={projectForm.description}
                  onChange={(e) => setProjectForm({ ...projectForm, description: e.target.value })}
                  rows={4}
                />
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="project-status">Status</Label>
                  <Select
                    value={projectForm.status}
                    onValueChange={(value) => setProjectForm({ ...projectForm, status: value })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="planning">Planning</SelectItem>
                      <SelectItem value="active">Active</SelectItem>
                      <SelectItem value="on_hold">On Hold</SelectItem>
                      <SelectItem value="completed">Completed</SelectItem>
                      <SelectItem value="cancelled">Cancelled</SelectItem>
                      <SelectItem value="draft">Draft</SelectItem>
                      <SelectItem value="posted">Posted</SelectItem>
                      <SelectItem value="in_progress">In Progress</SelectItem>
                      <SelectItem value="review">Review</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                
                <div className="space-y-2">
                  <Label htmlFor="project-priority">Priority</Label>
                  <Select
                    value={projectForm.priority}
                    onValueChange={(value) => setProjectForm({ ...projectForm, priority: value })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="low">Low</SelectItem>
                      <SelectItem value="medium">Medium</SelectItem>
                      <SelectItem value="high">High</SelectItem>
                      <SelectItem value="urgent">Urgent</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="project-type">Project Type</Label>
                <Select
                  value={projectForm.project_type}
                  onValueChange={(value) => setProjectForm({ ...projectForm, project_type: value })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="website">Website</SelectItem>
                    <SelectItem value="mobile_app">Mobile App</SelectItem>
                    <SelectItem value="web_app">Web Application</SelectItem>
                    <SelectItem value="ai_bot">AI Bot</SelectItem>
                    <SelectItem value="integration">Integration</SelectItem>
                    <SelectItem value="marketing">Marketing</SelectItem>
                    <SelectItem value="database">Database</SelectItem>
                    <SelectItem value="consulting">Consulting</SelectItem>
                    <SelectItem value="ai_system">AI System</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              
              <div className="flex justify-end gap-2 pt-4">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setShowEditProjectModal(false);
                    setEditingProject(null);
                  }}
                >
                  Cancel
                </Button>
                <Button type="submit">
                  Update Project
                </Button>
              </div>
            </form>
          </DialogContent>
        </Dialog>

        {/* Edit Task Modal */}
        <Dialog open={showEditTaskModal} onOpenChange={(open) => {
          setShowEditTaskModal(open);
          if (!open) {
            setEditingTask(null);
            setTaskForm({
              title: '',
              description: '',
              priority: 'medium',
              status: 'todo',
              assignee_id: 'none',
            });
          }
        }}>
          <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Edit Task</DialogTitle>
              <DialogDescription>
                Update task details including assignment, priority, and status.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleUpdateTask} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="task-title">Task Title *</Label>
                <Input
                  id="task-title"
                  value={taskForm.title}
                  onChange={(e) => setTaskForm({ ...taskForm, title: e.target.value })}
                  required
                />
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="task-description">Description</Label>
                <Textarea
                  id="task-description"
                  value={taskForm.description}
                  onChange={(e) => setTaskForm({ ...taskForm, description: e.target.value })}
                  rows={4}
                />
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="task-priority">Priority</Label>
                  <Select
                    value={taskForm.priority}
                    onValueChange={(value) => setTaskForm({ ...taskForm, priority: value })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="low">Low</SelectItem>
                      <SelectItem value="medium">Medium</SelectItem>
                      <SelectItem value="high">High</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                
                <div className="space-y-2">
                  <Label htmlFor="task-status">Status</Label>
                  <Select
                    value={taskForm.status}
                    onValueChange={(value) => setTaskForm({ ...taskForm, status: value })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="todo">To Do</SelectItem>
                      <SelectItem value="in_progress">In Progress</SelectItem>
                      <SelectItem value="review">Review</SelectItem>
                      <SelectItem value="done">Done</SelectItem>
                      <SelectItem value="blocked">Blocked</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="task-assignee">Assign To</Label>
                <Select
                  value={taskForm.assignee_id || 'none'}
                  onValueChange={(value) => setTaskForm({ ...taskForm, assignee_id: value })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select user (optional)" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None (Unassign)</SelectItem>
                    {availableUsers.map((user) => (
                      <SelectItem key={user.id} value={user.id.toString()}>
                        {user.full_name} ({user.email}) - {user.role}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              
              <div className="flex justify-end gap-2 pt-4">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setShowEditTaskModal(false);
                    setEditingTask(null);
                  }}
                >
                  Cancel
                </Button>
                <Button type="submit">
                  Update Task
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

