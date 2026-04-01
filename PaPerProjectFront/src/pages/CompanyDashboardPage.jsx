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
import SearchableSelect from '@/components/ui/searchable-select';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useToast } from '@/components/ui/use-toast';
import { companyJobsService } from '@/services';
import { companyApi } from '@/services/companyAuthService';
import usePurchasedModules from '@/hooks/usePurchasedModules';
import { getAgentNavItems } from '@/utils/agentNavItems';
import companyUserManagementService from '@/services/companyUserManagementService';
import companyProjectsTasksService from '@/services/companyProjectsTasksService';
import frontlineAgentService from '@/services/frontlineAgentService';
import DashboardNavbar from '@/components/common/DashboardNavbar';
import { API_BASE_URL } from '@/config/apiConfig';
import {
  Building2, Plus, Briefcase, Users, Eye,
  Loader2, Search, Calendar, MapPin, Clock, Download, BrainCircuit, FolderKanban,
  ChevronDown, ChevronRight, ListTodo, UserCheck, UserPlus, Edit, Trash2, Mail,
  CheckCircle2, Circle, PlayCircle, AlertCircle, FileCheck, TrendingUp, User, ChevronLeft,
  Ticket, RotateCcw
} from 'lucide-react';
import { createCheckoutSession } from '@/services/modulePurchaseService';

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
  const { purchasedModules, allPurchases, refetch: refetchModules } = usePurchasedModules();
  const [purchasingModule, setPurchasingModule] = useState(null);

  // User management state
  const [users, setUsers] = useState([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [usersPagination, setUsersPagination] = useState({ page: 1, limit: 20, total: 0, totalPages: 0 });
  const [showCreateUserModal, setShowCreateUserModal] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [userSubmitting, setUserSubmitting] = useState(false);
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
  const [tasksPagination, setTasksPagination] = useState({ page: 1, limit: 20, total: 0, totalPages: 0 });
  const [taskStatusFilter, setTaskStatusFilter] = useState('all');
  const [taskUserFilter, setTaskUserFilter] = useState('all');
  const [taskProjectFilter, setTaskProjectFilter] = useState('all');
  const [selectedTaskDescription, setSelectedTaskDescription] = useState(null);
  const [showDescriptionModal, setShowDescriptionModal] = useState(false);
  
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
    due_date: '',
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
  const [jobSubmitting, setJobSubmitting] = useState(false);

  // Ticket Tasks (Frontline KB-gap tasks) - only relevant when frontline_agent is purchased
  const [ticketTasks, setTicketTasks] = useState([]);
  const [loadingTicketTasks, setLoadingTicketTasks] = useState(false);
  const [resolvingTaskId, setResolvingTaskId] = useState(null);

  const handlePurchaseAgain = async (moduleName) => {
    setPurchasingModule(moduleName);
    try {
      const response = await createCheckoutSession(moduleName);
      if (response.status === 'success' && response.url) {
        window.location.href = response.url;
      } else {
        toast({ title: 'Error', description: response.message || 'Failed to start purchase', variant: 'destructive' });
      }
    } catch (error) {
      toast({ title: 'Error', description: error.message || 'Failed to start purchase', variant: 'destructive' });
    } finally {
      setPurchasingModule(null);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
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

      fetchJobs();
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
        errorMessage = `Cannot connect to server. Please check if the backend is running on ${API_BASE_URL.replace('/api', '')}`;
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
    if (jobSubmitting) return; // Prevent duplicate submissions

    // Validate required fields have meaningful content (at least 2 alphanumeric chars)
    const validateField = (value, fieldName) => {
      const alnumCount = (value.match(/[a-zA-Z0-9]/g) || []).length;
      if (alnumCount < 2) {
        toast({
          title: 'Validation Error',
          description: `${fieldName} must contain at least 2 alphanumeric characters.`,
          variant: 'destructive',
        });
        return false;
      }
      return true;
    };

    if (!validateField(jobForm.title, 'Job Title')) return;
    if (!validateField(jobForm.location, 'Location')) return;
    if (!validateField(jobForm.department, 'Department')) return;

    // Description must have at least 20 alphanumeric characters
    const descAlnum = (jobForm.description.match(/[a-zA-Z0-9]/g) || []).length;
    if (descAlnum < 20) {
      toast({ title: 'Validation Error', description: 'Job description must contain at least 20 alphanumeric characters. Please provide a meaningful description.', variant: 'destructive' });
      return;
    }

    // Requirements validation (if provided) - at least 10 alphanumeric characters
    if (jobForm.requirements?.trim()) {
      const reqAlnum = (jobForm.requirements.match(/[a-zA-Z0-9]/g) || []).length;
      if (reqAlnum < 10) {
        toast({ title: 'Validation Error', description: 'Requirements must contain at least 10 alphanumeric characters if provided.', variant: 'destructive' });
        return;
      }
    }

    setJobSubmitting(true);
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
    } finally {
      setJobSubmitting(false);
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
    
    // Format due_date for datetime-local input (YYYY-MM-DDTHH:mm)
    let formattedDueDate = '';
    if (task.due_date) {
      const dueDate = new Date(task.due_date);
      // Format as YYYY-MM-DDTHH:mm for datetime-local input
      const year = dueDate.getFullYear();
      const month = String(dueDate.getMonth() + 1).padStart(2, '0');
      const day = String(dueDate.getDate()).padStart(2, '0');
      const hours = String(dueDate.getHours()).padStart(2, '0');
      const minutes = String(dueDate.getMinutes()).padStart(2, '0');
      formattedDueDate = `${year}-${month}-${day}T${hours}:${minutes}`;
    }
    
    setTaskForm({
      title: task.title || '',
      description: task.description || '',
      priority: task.priority || 'medium',
      status: task.status || 'todo',
      assignee_id: assigneeIdString,
      due_date: formattedDueDate,
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
      
      // Format due_date for API (convert to ISO string or null)
      let dueDateValue = null;
      if (taskForm.due_date) {
        const dateObj = new Date(taskForm.due_date);
        if (!isNaN(dateObj.getTime())) {
          dueDateValue = dateObj.toISOString();
        }
      }
      
      const response = await companyProjectsTasksService.updateTask(editingTask.id, {
        ...taskForm,
        assignee_id: assigneeId,
        due_date: dueDateValue,
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

  const loadTicketTasks = async () => {
    try {
      setLoadingTicketTasks(true);
      const res = await frontlineAgentService.listTicketTasks();
      if (res.status === 'success' && res.data) {
        setTicketTasks(res.data || []);
      } else {
        setTicketTasks([]);
      }
    } catch (err) {
      console.error('Load ticket tasks error:', err);
      setTicketTasks([]);
    } finally {
      setLoadingTicketTasks(false);
    }
  };

  const handleCloseTicketTask = async (taskId) => {
    try {
      setResolvingTaskId(taskId);
      const res = await frontlineAgentService.updateTicketTask(taskId, { status: 'closed' });
      if (res.status === 'success') {
        toast({ title: 'Ticket closed', description: 'The ticket task has been closed.' });
        loadTicketTasks();
      }
    } catch (err) {
      toast({ title: 'Error', description: err.message || 'Failed to close ticket', variant: 'destructive' });
    } finally {
      setResolvingTaskId(null);
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
      // Fetch projects for the filter if not already loaded
      if (projects.length === 0) {
        fetchProjects();
      }
      // Fetch users for the filter if not already loaded
      if (users.length === 0) {
        fetchUsers();
      }
      // Fetch available users for assignment if not already loaded
      if (availableUsers.length === 0) {
        fetchAvailableUsers();
      }
      fetchAllUsersTasks();
    }
    if (activeTab === 'ticket-tasks' && companyUser && purchasedModules.includes('frontline_agent')) {
      loadTicketTasks();
    }
  }, [activeTab, companyUser, taskStatusFilter, taskUserFilter, taskProjectFilter, usersPagination.page, usersPagination.limit, tasksPagination.page, tasksPagination.limit]);
  
  const fetchAllUsersTasks = async () => {
    try {
      setAllUsersTasksLoading(true);
      const params = {
        page: tasksPagination.page,
        limit: tasksPagination.limit,
      };
      if (taskStatusFilter !== 'all') {
        params.status = taskStatusFilter;
      }
      if (taskUserFilter !== 'all') {
        params.user_id = taskUserFilter;
      }
      if (taskProjectFilter !== 'all') {
        params.project_id = taskProjectFilter;
      }
      
      const queryParams = new URLSearchParams(params);
      const queryString = queryParams.toString();
      const endpoint = `/company/users/tasks${queryString ? `?${queryString}` : ''}`;
      
      const response = await companyApi.get(endpoint);
      if (response.status === 'success') {
        setAllUsersTasks(response.data || []);
        if (response.pagination) {
          setTasksPagination(response.pagination);
        }
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
      const response = await companyUserManagementService.listUsers({ 
        page: usersPagination.page, 
        limit: usersPagination.limit 
      });
      if (response.status === 'success') {
        setUsers(response.data || []);
        if (response.pagination) {
          setUsersPagination(response.pagination);
        }
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
    if (userSubmitting) return; // Prevent duplicate submissions

    // Validate required fields
    if (!userForm.email || !userForm.password || !userForm.fullName || !userForm.phoneNumber) {
      toast({
        title: 'Validation Error',
        description: 'Email, password, full name, and phone number are required',
        variant: 'destructive',
      });
      return;
    }

    // Full name validation: only letters and spaces, at least 2 alpha chars, no digits
    if (/\d/.test(userForm.fullName)) {
      toast({ title: 'Validation Error', description: 'Full name must not contain digits.', variant: 'destructive' });
      return;
    }
    if (!/^[a-zA-Z\s]+$/.test(userForm.fullName.trim())) {
      toast({ title: 'Validation Error', description: 'Full name must contain only letters and spaces.', variant: 'destructive' });
      return;
    }
    const nameAlpha = (userForm.fullName.match(/[a-zA-Z]/g) || []).length;
    if (nameAlpha < 2) {
      toast({ title: 'Validation Error', description: 'Full name must contain at least 2 alphabetic characters.', variant: 'destructive' });
      return;
    }

    // Phone number validation: at least 7 digits, valid format
    const phoneDigits = (userForm.phoneNumber.match(/\d/g) || []).length;
    if (phoneDigits < 7) {
      toast({ title: 'Validation Error', description: 'Phone number must contain at least 7 digits.', variant: 'destructive' });
      return;
    }
    if (!/^[+\d\s\-()]+$/.test(userForm.phoneNumber.trim())) {
      toast({ title: 'Validation Error', description: 'Phone number contains invalid characters.', variant: 'destructive' });
      return;
    }

    // Location validation if provided
    if (userForm.location?.trim()) {
      const locAlnum = (userForm.location.match(/[a-zA-Z0-9]/g) || []).length;
      if (locAlnum < 2) {
        toast({ title: 'Validation Error', description: 'Location must contain at least 2 alphanumeric characters if provided.', variant: 'destructive' });
        return;
      }
    }

    // Bio validation if provided (at least 10 alphanumeric chars)
    if (userForm.bio?.trim()) {
      const bioAlnum = (userForm.bio.match(/[a-zA-Z0-9]/g) || []).length;
      if (bioAlnum < 10) {
        toast({ title: 'Validation Error', description: 'Bio must contain at least 10 alphanumeric characters if provided.', variant: 'destructive' });
        return;
      }
    }

    // Strict email validation
    const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
    if (!emailRegex.test(userForm.email.trim())) {
      toast({ title: 'Validation Error', description: 'Please enter a valid email address.', variant: 'destructive' });
      return;
    }

    // Password strength: min 8 chars, uppercase, lowercase, digit, special char
    if (userForm.password.length < 8) {
      toast({ title: 'Validation Error', description: 'Password must be at least 8 characters long.', variant: 'destructive' });
      return;
    }
    if (!/[A-Z]/.test(userForm.password)) {
      toast({ title: 'Validation Error', description: 'Password must contain at least one uppercase letter.', variant: 'destructive' });
      return;
    }
    if (!/[a-z]/.test(userForm.password)) {
      toast({ title: 'Validation Error', description: 'Password must contain at least one lowercase letter.', variant: 'destructive' });
      return;
    }
    if (!/\d/.test(userForm.password)) {
      toast({ title: 'Validation Error', description: 'Password must contain at least one digit.', variant: 'destructive' });
      return;
    }
    if (!/[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(userForm.password)) {
      toast({ title: 'Validation Error', description: 'Password must contain at least one special character.', variant: 'destructive' });
      return;
    }

    setUserSubmitting(true);
    try {
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
    } finally {
      setUserSubmitting(false);
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

  const handleReactivateUser = async (userId) => {
    if (!window.confirm('Are you sure you want to reactivate this user?')) {
      return;
    }

    try {
      const response = await companyUserManagementService.reactivateUser(userId);
      if (response.status === 'success') {
        toast({
          title: 'Success!',
          description: 'User reactivated successfully',
        });
        fetchUsers();
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to reactivate user',
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
    return `${API_BASE_URL.replace('/api', '')}/${resumePath}`;
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
      <div
        className="min-h-screen overflow-x-hidden"
        style={{
          background: 'linear-gradient(135deg, #020308 0%, #0a0a1a 25%, #0d0b1f 50%, #0f0a20 75%, #020308 100%)',
        }}
      >
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
          navItems={getAgentNavItems(purchasedModules, 'dashboard', navigate)}
        />

        <div className="container mx-auto px-4 py-8 max-w-7xl w-full overflow-x-hidden">
          {activeSection === 'dashboard' && (
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <div className="flex justify-between items-center mb-6">
              <TabsList
                className="bg-[#1a1333] border border-[#3a295a] rounded-xl p-1 flex gap-1 h-auto flex-wrap"
                style={{ boxShadow: '0 2px 12px 0 #a259ff0a' }}
              >
                {[
                  { value: 'jobs', icon: Briefcase, label: 'My Jobs' },
                  { value: 'projects', icon: FolderKanban, label: 'Projects' },
                  { value: 'applications', icon: Users, label: 'Applications' },
                  { value: 'users', icon: UserCheck, label: 'Users' },
                  { value: 'all-tasks', icon: ListTodo, label: 'All Users Tasks' },
                  ...(purchasedModules.includes('frontline_agent') ? [{ value: 'ticket-tasks', icon: Ticket, label: 'Ticket Tasks' }] : []),
                  { value: 'ai-agents', icon: BrainCircuit, label: 'AI Agents' },
                ].map(({ value, icon: TabIcon, label }) => (
                  <TabsTrigger
                    key={value}
                    value={value}
                    className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-all border"
                    style={activeTab === value
                      ? { background: 'linear-gradient(90deg, #a259ff 0%, #7c3aed 100%)', color: '#fff', border: '1.5px solid #a259ff', boxShadow: '0 0 8px 0 #a259ff55' }
                      : { background: 'rgba(60,30,90,0.22)', color: '#cfc6e6', border: '1.5px solid #2d2342' }
                    }
                  >
                    <TabIcon className="h-4 w-4" />
                    {label}
                  </TabsTrigger>
                ))}
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
                  <Loader2 className="h-8 w-8 animate-spin text-violet-400" />
                </div>
              ) : jobs.length === 0 ? (
                <Card className="bg-[#120d22] border border-[#2d2342]">
                  <CardContent className="py-12 text-center">
                    <Briefcase className="h-12 w-12 mx-auto text-white/20 mb-4" />
                    <p className="text-lg font-medium mb-2 text-white">No jobs posted yet</p>
                    <Button onClick={() => setShowCreateJobModal(true)} className="bg-violet-600 hover:bg-violet-700">
                      Post Your First Job
                    </Button>
                  </CardContent>
                </Card>
              ) : (
                <div className="grid gap-4">
                  {jobs.map((job) => (
                    <Card key={job.id} className="bg-[#120d22] border border-[#2d2342] hover:border-violet-500/30 transition-colors">
                      <CardHeader>
                        <div className="flex justify-between items-start">
                          <div>
                            <CardTitle className="text-white">{job.title}</CardTitle>
                            <div className="flex gap-4 mt-2 text-sm text-white/50">
                              <span className="flex items-center gap-1">
                                <MapPin className="h-4 w-4" />
                                {job.location}
                              </span>
                              <span className="flex items-center gap-1">
                                <Briefcase className="h-4 w-4" />
                                {job.department}
                              </span>
                              <Badge className="bg-violet-600/20 text-violet-300 border border-violet-500/30">{job.type}</Badge>
                            </div>
                          </div>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleViewApplications(job.id)}
                            className="border-white/20 text-white/70 hover:text-white hover:bg-white/10"
                          >
                            <Eye className="h-4 w-4 mr-2" />
                            View Applications
                          </Button>
                        </div>
                      </CardHeader>
                      <CardContent>
                        <p className="text-sm text-white/50 line-clamp-2">{job.description}</p>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </TabsContent>

            <TabsContent value="projects" className="space-y-4">
              {projectsLoading ? (
                <div className="flex justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin text-violet-400" />
                </div>
              ) : projects.length === 0 ? (
                <Card className="bg-[#120d22] border border-[#2d2342]">
                  <CardContent className="py-12 text-center">
                    <FolderKanban className="h-12 w-12 mx-auto text-white/20 mb-4" />
                    <p className="text-lg font-medium mb-2 text-white">No projects yet</p>
                    <p className="text-sm text-white/50 mb-4">
                      Create projects using the Project Manager Agent
                    </p>
                    <Button onClick={() => navigate('/project-manager/dashboard')} className="bg-violet-600 hover:bg-violet-700">
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
                      <Card key={project.id} className="cursor-pointer bg-[#120d22] border border-[#2d2342] hover:border-violet-500/30 transition-colors">
                        <CardHeader
                          onClick={() => toggleProject(project.id)}
                          className="pb-3"
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3 flex-1">
                              <div className="flex-shrink-0">
                                {isExpanded ? (
                                  <ChevronDown className="h-5 w-5 text-white/40" />
                                ) : (
                                  <ChevronRight className="h-5 w-5 text-white/40" />
                                )}
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center justify-between gap-2">
                                  <CardTitle className="text-lg text-white">{project.name}</CardTitle>
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
                                  <Badge className={project.status === 'active' ? 'bg-green-500/20 text-green-300 border border-green-500/30' : 'bg-white/10 text-white/50 border border-white/10'}>
                                    {project.status}
                                  </Badge>
                                  <Badge variant="outline" className="border-white/20 text-white/60">{project.priority}</Badge>
                                  <span className="text-sm text-white/50 flex items-center gap-1">
                                    <ListTodo className="h-3 w-3" />
                                    {project.tasks_count} task{project.tasks_count !== 1 ? 's' : ''}
                                  </span>
                                  {project.created_at && (
                                    <span className="text-sm text-white/50 flex items-center gap-1">
                                      <Calendar className="h-3 w-3" />
                                      {new Date(project.created_at).toLocaleDateString()}
                                    </span>
                                  )}
                                </div>
                                {project.description && !isExpanded && (
                                  <p className="text-sm text-white/50 mt-2 line-clamp-2">
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
                              <p className="text-sm text-white/50 mb-4 pb-4 border-b border-white/10">
                                {project.description}
                              </p>
                            )}
                            {project.tasks && project.tasks.length > 0 ? (
                              <div className="space-y-3">
                                <h4 className="font-semibold text-sm mb-3 flex items-center gap-2 text-white/70">
                                  <ListTodo className="h-4 w-4" />
                                  Tasks ({project.tasks.length})
                                </h4>
                                {project.tasks.map((task) => {
                                  const hasSubtasks = task.subtasks && task.subtasks.length > 0;
                                  const showSubtasks = expandedTasks.has(task.id);
                                  return (
                                    <div
                                      key={task.id}
                                      className="border-l-2 border-violet-500/50 pl-4 py-3 bg-white/[0.03] rounded-r"
                                    >
                                      <div className="flex items-start justify-between gap-3">
                                        <div className="flex-1 min-w-0">
                                          <div className="flex items-center gap-2">
                                            <p className="font-medium text-white">{task.title}</p>
                                            <Button
                                              variant="ghost"
                                              size="sm"
                                              onClick={(e) => {
                                                e.stopPropagation();
                                                handleEditTask(task);
                                              }}
                                              className="h-6 w-6 p-0 text-white/40 hover:text-white"
                                            >
                                              <Edit className="h-3 w-3" />
                                            </Button>
                                          </div>
                                          {task.description && (
                                            <p className="text-sm text-white/50 mt-1">
                                              {task.description}
                                            </p>
                                          )}
                                          {task.due_date && (
                                            <p className="text-xs text-white/40 mt-1 flex items-center gap-1">
                                              <Clock className="h-3 w-3" />
                                              Due: {new Date(task.due_date).toLocaleDateString()}
                                            </p>
                                          )}
                                        </div>
                                        <div className="flex items-center gap-2 flex-shrink-0">
                                          <Badge variant="outline" className="text-xs border-white/20 text-white/60">
                                            {task.status}
                                          </Badge>
                                          <Badge className="text-xs bg-white/10 text-white/60 border border-white/10">
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
                                        <div className="mt-3 ml-2 space-y-2 pl-4 border-l-2 border-white/10">
                                          <p className="text-xs font-medium text-white/40 mb-2">
                                            Subtasks ({task.subtasks.length}):
                                          </p>
                                          {task.subtasks.map((subtask) => (
                                            <div
                                              key={subtask.id}
                                              className="flex items-center gap-2 text-sm bg-white/[0.03] p-2 rounded"
                                            >
                                              <span className="text-violet-400">•</span>
                                              <span className="flex-1 text-white/70">{subtask.title}</span>
                                              {subtask.description && (
                                                <span className="text-xs text-white/40 hidden md:block">
                                                  {subtask.description}
                                                </span>
                                              )}
                                              <Badge variant="outline" className="text-xs border-white/20 text-white/60">
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
                              <div className="text-center py-8 text-white/30">
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
                    <h2 className="text-2xl font-bold text-white">Applications for {selectedJob.title}</h2>
                    <Button variant="outline" onClick={() => setSelectedJob(null)} className="border-white/20 text-white/70 hover:text-white hover:bg-white/10">
                      Back to Jobs
                    </Button>
                  </div>
                  {selectedJobApplications.length === 0 ? (
                    <Card className="bg-[#120d22] border border-[#2d2342]">
                      <CardContent className="py-12 text-center">
                        <Users className="h-12 w-12 mx-auto text-white/20 mb-4" />
                        <p className="text-lg font-medium text-white">No applications yet</p>
                      </CardContent>
                    </Card>
                  ) : (
                    <div className="space-y-4">
                      {selectedJobApplications.map((app) => (
                        <Card key={app.id} className="bg-[#120d22] border border-[#2d2342]">
                          <CardHeader>
                            <div className="flex justify-between items-start">
                              <div>
                                <CardTitle className="text-white">{app.applicant_name}</CardTitle>
                                <CardDescription className="text-white/50">{app.email}</CardDescription>
                              </div>
                              <Badge className={getStatusColor(app.status)}>{app.status}</Badge>
                            </div>
                          </CardHeader>
                          <CardContent>
                            <div className="space-y-2">
                              {app.cover_letter && (
                                <p className="text-sm text-white/70">{app.cover_letter}</p>
                              )}
                              {app.resume_path && (
                                <a
                                  href={getResumeUrl(app.resume_path)}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-2 text-sm text-violet-400 hover:text-violet-300 hover:underline"
                                >
                                  <Download className="h-4 w-4" />
                                  Download Resume
                                </a>
                              )}
                              <div className="flex gap-2 pt-2 flex-wrap">
                                {['pending', 'reviewing', 'interview', 'accepted', 'rejected'].map((status) => (
                                  <Button
                                    key={status}
                                    size="sm"
                                    onClick={() => handleUpdateStatus(app.id, status)}
                                    disabled={app.status === status}
                                    className={`capitalize ${app.status === status ? 'bg-violet-600 text-white' : 'border-white/20 text-white/60 hover:text-white hover:bg-white/10 bg-transparent border'}`}
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
                <Card className="bg-[#120d22] border border-[#2d2342]">
                  <CardContent className="py-12 text-center">
                    <Users className="h-12 w-12 mx-auto text-white/20 mb-4" />
                    <p className="text-lg font-medium text-white/50">Select a job to view applications</p>
                  </CardContent>
                </Card>
              )}
            </TabsContent>
            
            <TabsContent value="users" className="space-y-4">
              {usersLoading ? (
                <div className="flex justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin text-violet-400" />
                </div>
              ) : users.length === 0 ? (
                <Card className="bg-[#120d22] border border-[#2d2342]">
                  <CardContent className="py-12 text-center">
                    <UserCheck className="h-12 w-12 mx-auto text-white/20 mb-4" />
                    <p className="text-lg font-medium mb-2 text-white">No users yet</p>
                    <p className="text-sm text-white/50 mb-4">
                      Add users to your company to manage projects and tasks
                    </p>
                    <Button onClick={() => {
                      setEditingUser(null);
                      setUserForm({
                        email: '', password: '', username: '', fullName: '', role: 'team_member',
                        phoneNumber: '', bio: '', location: '',
                      });
                      setShowCreateUserModal(true);
                    }} className="bg-violet-600 hover:bg-violet-700">
                      <UserPlus className="h-4 w-4 mr-2" />
                      Add Your First User
                    </Button>
                  </CardContent>
                </Card>
              ) : (
                <div className="space-y-4">
                  <Card className="bg-[#120d22] border border-[#2d2342]">
                    <CardContent className="p-0">
                      <Table>
                        <TableHeader>
                          <TableRow className="bg-[#1a1333] border-b border-[#2d2342] hover:bg-[#1a1333]">
                            <TableHead className="text-white/60 font-semibold">Name</TableHead>
                            <TableHead className="text-white/60 font-semibold">Email</TableHead>
                            <TableHead className="text-white/60 font-semibold">Role</TableHead>
                            <TableHead className="text-white/60 font-semibold">Location</TableHead>
                            <TableHead className="text-white/60 font-semibold">Phone</TableHead>
                            <TableHead className="text-white/60 font-semibold">Joined</TableHead>
                            <TableHead className="text-right text-white/60 font-semibold">Actions</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {users.map((user) => (
                            <TableRow key={user.id} className="border-white/[0.06] hover:bg-white/[0.04]">
                              <TableCell className="font-medium text-white">
                                <div className="flex items-center gap-2">
                                  {user.full_name || user.username}
                                  {user.is_active === false && (
                                    <Badge className="text-xs bg-white/10 text-white/50 border border-white/10">Inactive</Badge>
                                  )}
                                </div>
                              </TableCell>
                              <TableCell className="text-white/70">
                                <div className="flex items-center gap-1">
                                  <Mail className="h-3 w-3 text-white/30" />
                                  {user.email}
                                </div>
                              </TableCell>
                              <TableCell>
                                <Badge variant="outline" className="capitalize border-white/20 text-white/60">
                                  {user.role?.replace('_', ' ')}
                                </Badge>
                              </TableCell>
                              <TableCell>
                                {user.location ? (
                                  <div className="flex items-center gap-1">
                                    <MapPin className="h-3 w-3 text-white/30" />
                                    <span className="text-white/70">{user.location}</span>
                                  </div>
                                ) : (
                                  <span className="text-white/30">-</span>
                                )}
                              </TableCell>
                              <TableCell className="text-white/70">
                                {user.phone_number || <span className="text-white/30">-</span>}
                              </TableCell>
                              <TableCell className="text-white/70">
                                {user.date_joined ? (
                                  new Date(user.date_joined).toLocaleDateString()
                                ) : (
                                  <span className="text-white/30">-</span>
                                )}
                              </TableCell>
                              <TableCell className="text-right">
                                <div className="flex items-center justify-end gap-2">
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => handleEditUser(user)}
                                    className="h-8 w-8 p-0 border-white/20 text-white/60 hover:text-white hover:bg-white/10"
                                  >
                                    <Edit className="h-4 w-4" />
                                  </Button>
                                  {user.is_active === false ? (
                                    <Button
                                      variant="outline"
                                      size="sm"
                                      onClick={() => handleReactivateUser(user.id)}
                                      className="h-8 w-8 p-0 border-green-500/30 text-green-400 hover:text-green-300 hover:bg-green-500/10"
                                      title="Reactivate user"
                                    >
                                      <RotateCcw className="h-4 w-4" />
                                    </Button>
                                  ) : (
                                    <Button
                                      variant="outline"
                                      size="sm"
                                      onClick={() => handleDeleteUser(user.id)}
                                      className="h-8 w-8 p-0 border-red-500/30 text-red-400 hover:text-red-300 hover:bg-red-500/10"
                                      title="Deactivate user"
                                    >
                                      <Trash2 className="h-4 w-4" />
                                    </Button>
                                  )}
                                </div>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </CardContent>
                  </Card>

                  {/* Pagination */}
                  {usersPagination.totalPages > 1 && (
                    <div className="flex items-center justify-between">
                      <p className="text-sm text-white/50">
                        Showing page {usersPagination.page} of {usersPagination.totalPages} ({usersPagination.total} total users)
                      </p>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setUsersPagination(prev => ({ ...prev, page: prev.page - 1 }))}
                          disabled={usersPagination.page === 1 || usersLoading}
                          className="border-white/20 text-white/60 hover:text-white hover:bg-white/10"
                        >
                          <ChevronLeft className="h-4 w-4" />
                          Previous
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setUsersPagination(prev => ({ ...prev, page: prev.page + 1 }))}
                          disabled={usersPagination.page >= usersPagination.totalPages || usersLoading}
                          className="border-white/20 text-white/60 hover:text-white hover:bg-white/10"
                        >
                          Next
                          <ChevronRight className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </TabsContent>

            <TabsContent value="all-tasks" className="space-y-4">
              {/* Filters */}
              <div className="flex items-center gap-4 flex-wrap">
                <SearchableSelect
                  value={taskStatusFilter}
                  onValueChange={(value) => { setTaskStatusFilter(value); setTasksPagination(prev => ({ ...prev, page: 1 })); }}
                  placeholder="Filter by status"
                  triggerClassName="w-[180px]"
                  options={[
                    { value: 'all', label: 'All Statuses' },
                    { value: 'todo', label: 'To Do' },
                    { value: 'in_progress', label: 'In Progress' },
                    { value: 'review', label: 'Review' },
                    { value: 'done', label: 'Done' },
                    { value: 'blocked', label: 'Blocked' },
                  ]}
                />

                <SearchableSelect
                  value={taskUserFilter}
                  onValueChange={(value) => { setTaskUserFilter(value); setTasksPagination(prev => ({ ...prev, page: 1 })); }}
                  placeholder="Filter by user"
                  triggerClassName="w-[180px]"
                  displayLength={20}
                  options={[
                    { value: 'all', label: 'All Users' },
                    ...(availableUsers.length > 0 ? availableUsers : users).map(u => ({
                      value: u.id.toString(),
                      label: u.full_name || u.username || u.email,
                    })),
                  ]}
                />

                <SearchableSelect
                  value={taskProjectFilter}
                  onValueChange={(value) => { setTaskProjectFilter(value); setTasksPagination(prev => ({ ...prev, page: 1 })); }}
                  placeholder="Filter by project"
                  triggerClassName="w-[180px]"
                  displayLength={20}
                  options={[
                    { value: 'all', label: 'All Projects' },
                    ...projects.map(p => ({
                      value: p.id.toString(),
                      label: p.name,
                    })),
                  ]}
                />
              </div>

              {allUsersTasksLoading ? (
                <div className="flex justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin" />
                </div>
              ) : allUsersTasks.length === 0 ? (
                <Card className="bg-[#120d22] border border-[#2d2342]">
                  <CardContent className="py-12 text-center">
                    <ListTodo className="h-12 w-12 mx-auto text-white/20 mb-4" />
                    <p className="text-lg font-medium mb-2 text-white">No tasks found</p>
                    <p className="text-sm text-white/50">
                      {taskStatusFilter !== 'all' || taskUserFilter !== 'all' || taskProjectFilter !== 'all'
                        ? 'No tasks match the selected filters'
                        : 'No tasks have been assigned to your users yet'}
                    </p>
                  </CardContent>
                </Card>
              ) : (
                <div className="space-y-4">
                  <Card className="bg-[#120d22] border border-[#2d2342]">
                    <CardContent className="p-0">
                      <Table>
                        <TableHeader>
                          <TableRow className="bg-[#1a1333] border-b border-[#2d2342] hover:bg-[#1a1333]">
                            <TableHead className="w-[250px] text-white/60 font-semibold">Task</TableHead>
                            <TableHead className="text-white/60 font-semibold">Description</TableHead>
                            <TableHead className="text-white/60 font-semibold">Assignee</TableHead>
                            <TableHead className="text-white/60 font-semibold">Status</TableHead>
                            <TableHead className="text-white/60 font-semibold">Priority</TableHead>
                            <TableHead className="text-white/60 font-semibold">Due Date</TableHead>
                            <TableHead className="text-white/60 font-semibold">Progress</TableHead>
                            <TableHead className="text-right text-white/60 font-semibold">Actions</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {allUsersTasks.map((task) => (
                            <TableRow key={task.id} className="border-white/[0.06] hover:bg-white/[0.04]">
                              <TableCell className="w-[250px]">
                                <div>
                                  <div className="font-medium text-white">{task.title}</div>
                                  <div className="text-sm text-white/40 mt-1 flex items-center gap-1">
                                    <FolderKanban className="h-3 w-3" />
                                    {task.project_name}
                                  </div>
                                </div>
                              </TableCell>
                              <TableCell>
                                {task.description ? (
                                  <div
                                    className="text-sm text-white/50 line-clamp-2 cursor-pointer hover:text-violet-300 hover:underline"
                                    onClick={() => {
                                      setSelectedTaskDescription({
                                        title: task.title,
                                        description: task.description
                                      });
                                      setShowDescriptionModal(true);
                                    }}
                                  >
                                    {task.description}
                                  </div>
                                ) : (
                                  <span className="text-white/30 text-sm">No description</span>
                                )}
                              </TableCell>
                              <TableCell className="text-white/70">
                                {task.assignee_name ? (
                                  <div className="flex items-center gap-1">
                                    <User className="h-3 w-3 text-white/30" />
                                    {task.assignee_name}
                                  </div>
                                ) : (
                                  <span className="text-white/30">Unassigned</span>
                                )}
                              </TableCell>
                              <TableCell>
                                <Badge className={getStatusColor(task.status)}>
                                  {getStatusIcon(task.status)}
                                  <span className="ml-1 capitalize">{task.status.replace('_', ' ')}</span>
                                </Badge>
                              </TableCell>
                              <TableCell>
                                <Badge variant="outline" className={`${getPriorityColor(task.priority)} border-white/20`}>
                                  {task.priority}
                                </Badge>
                              </TableCell>
                              <TableCell className="text-white/70">
                                {task.due_date ? (
                                  <div className="flex items-center gap-1">
                                    <Calendar className="h-3 w-3 text-white/30" />
                                    {new Date(task.due_date).toLocaleDateString()}
                                  </div>
                                ) : (
                                  <span className="text-white/30">-</span>
                                )}
                              </TableCell>
                              <TableCell className="text-white/70">
                                {task.progress_percentage !== null ? (
                                  <div className="flex items-center gap-1">
                                    <TrendingUp className="h-3 w-3 text-violet-400" />
                                    {task.progress_percentage}%
                                  </div>
                                ) : (
                                  <span className="text-white/30">-</span>
                                )}
                              </TableCell>
                              <TableCell className="text-right">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleEditTask(task)}
                                  className="h-8 w-8 p-0 text-white/40 hover:text-white hover:bg-white/10"
                                >
                                  <Edit className="h-4 w-4" />
                                </Button>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </CardContent>
                  </Card>

                  {/* Pagination */}
                  {tasksPagination.totalPages > 1 && (
                    <div className="flex items-center justify-between">
                      <p className="text-sm text-white/50">
                        Showing page {tasksPagination.page} of {tasksPagination.totalPages} ({tasksPagination.total} total tasks)
                      </p>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setTasksPagination(prev => ({ ...prev, page: prev.page - 1 }))}
                          disabled={tasksPagination.page === 1 || allUsersTasksLoading}
                          className="border-white/20 text-white/60 hover:text-white hover:bg-white/10"
                        >
                          <ChevronLeft className="h-4 w-4" />
                          Previous
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setTasksPagination(prev => ({ ...prev, page: prev.page + 1 }))}
                          disabled={tasksPagination.page >= tasksPagination.totalPages || allUsersTasksLoading}
                          className="border-white/20 text-white/60 hover:text-white hover:bg-white/10"
                        >
                          Next
                          <ChevronRight className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </TabsContent>

            {purchasedModules.includes('frontline_agent') && (
              <TabsContent value="ticket-tasks" className="space-y-4">
                <Card className="bg-[#120d22] border border-[#2d2342]">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-white">
                      <Ticket className="h-5 w-5 text-violet-400" />
                      Ticket Tasks
                    </CardTitle>
                    <CardDescription className="text-white/50">
                      When the Frontline agent doesn&apos;t have an answer in Knowledge Q&A, a ticket is created here. Upload a document in the Frontline Agent (Documents tab) that covers the topic, then close the ticket from this tab when done.
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    {loadingTicketTasks ? (
                      <div className="flex justify-center py-8">
                        <Loader2 className="h-8 w-8 animate-spin text-violet-400" />
                      </div>
                    ) : ticketTasks.length === 0 ? (
                      <div className="text-center py-8 text-white/40">
                        No ticket tasks yet. When you ask something in Frontline Knowledge Q&A that the agent can&apos;t answer, a task will appear here. Add a document in the Frontline Agent to expand the knowledge base, then close the ticket here.
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {ticketTasks.map((task) => (
                          <div
                            key={task.id}
                            className={`rounded-lg border p-4 ${task.status === 'resolved' || task.status === 'closed' ? 'bg-white/[0.02] border-white/[0.05] opacity-60' : 'bg-white/[0.04] border-[#2d2342]'}`}
                          >
                            <div className="flex items-start justify-between gap-4">
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className="font-medium text-white">{task.title}</span>
                                  <span className="text-xs px-2 py-0.5 rounded-full bg-violet-500/20 text-violet-300 border border-violet-500/20">{task.status}</span>
                                </div>
                                <div className="mt-2 text-sm text-white/50 whitespace-pre-wrap break-words max-w-none">
                                  {task.description?.replace(/\*\*/g, '')}
                                </div>
                                <p className="text-xs text-white/30 mt-2">
                                  Created {task.created_at ? new Date(task.created_at).toLocaleString() : ''}
                                </p>
                              </div>
                              {(task.status !== 'resolved' && task.status !== 'closed') && (
                                <Button
                                  size="sm"
                                  onClick={() => handleCloseTicketTask(task.id)}
                                  disabled={resolvingTaskId === task.id}
                                  className="bg-violet-600 hover:bg-violet-700 text-white shrink-0"
                                >
                                  {resolvingTaskId === task.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4 mr-1" />}
                                  Close
                                </Button>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>
            )}

            <TabsContent value="ai-agents" className="space-y-4">
              <Card className="bg-[#120d22] border border-[#2d2342]">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-white">
                    <BrainCircuit className="h-5 w-5 text-violet-400" />
                    Your AI Agents
                  </CardTitle>
                  <CardDescription className="text-white/50">
                    View all your AI agent purchases, their current status, and timeline
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {allPurchases.length === 0 ? (
                    <div className="text-center py-12">
                      <BrainCircuit className="h-12 w-12 mx-auto text-white/20 mb-4" />
                      <p className="text-lg font-medium text-white/60">No AI Agents Purchased Yet</p>
                      <p className="text-sm text-white/40 mt-2 mb-4">
                        Explore our AI agents to supercharge your workflow
                      </p>
                      <Button
                        onClick={() => navigate('/value-and-pricing')}
                        className="bg-violet-600 hover:bg-violet-700 text-white"
                      >
                        Browse AI Agents
                      </Button>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {allPurchases.map((agent) => {
                        const isActive = agent.status === 'active' && !agent.is_expired;
                        const isDeactivatedByAdmin = agent.deactivated_by_admin;
                        const isExpired = agent.is_expired || agent.status === 'expired';
                        const isCancelled = agent.status === 'cancelled' && !isDeactivatedByAdmin;
                        const canRepurchase = !isActive;

                        return (
                          <motion.div
                            key={agent.id}
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            className={`rounded-xl border p-5 transition-all ${
                              isActive
                                ? 'bg-white/[0.04] border-green-500/30'
                                : isDeactivatedByAdmin
                                ? 'bg-red-500/[0.04] border-red-500/30'
                                : isExpired
                                ? 'bg-yellow-500/[0.04] border-yellow-500/30'
                                : 'bg-white/[0.02] border-white/10'
                            }`}
                          >
                            <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
                              {/* Left: Agent Info */}
                              <div className="flex-1">
                                <div className="flex items-center gap-3 flex-wrap">
                                  <div className={`p-2 rounded-lg ${
                                    isActive ? 'bg-green-500/20' : isDeactivatedByAdmin ? 'bg-red-500/20' : isExpired ? 'bg-yellow-500/20' : 'bg-white/10'
                                  }`}>
                                    <BrainCircuit className={`h-5 w-5 ${
                                      isActive ? 'text-green-400' : isDeactivatedByAdmin ? 'text-red-400' : isExpired ? 'text-yellow-400' : 'text-white/40'
                                    }`} />
                                  </div>
                                  <div>
                                    <h3 className="text-lg font-semibold text-white">{agent.module_display_name}</h3>
                                    <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                                      {isActive && (
                                        <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-green-500/20 text-green-300 border border-green-500/30">
                                          <CheckCircle2 className="h-3 w-3" /> Active
                                        </span>
                                      )}
                                      {agent.active_label && (
                                        <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-300 border border-blue-500/20">
                                          <Clock className="h-3 w-3" /> {agent.active_label}
                                          {agent.time_remaining && <>&nbsp;&middot;&nbsp;{agent.time_remaining}</>}
                                        </span>
                                      )}
                                      {isDeactivatedByAdmin && (
                                        <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-red-500/20 text-red-300 border border-red-500/30">
                                          <AlertCircle className="h-3 w-3" /> Deactivated by Admin
                                        </span>
                                      )}
                                      {isExpired && (
                                        <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-yellow-500/20 text-yellow-300 border border-yellow-500/30">
                                          <Clock className="h-3 w-3" /> Time Ended
                                        </span>
                                      )}
                                      {isExpired && agent.time_ended_ago && (
                                        <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-red-500/15 text-red-300 border border-red-500/20">
                                          <Clock className="h-3 w-3" /> {agent.time_ended_ago}
                                        </span>
                                      )}
                                      {isCancelled && (
                                        <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-gray-500/20 text-gray-300 border border-gray-500/30">
                                          <Circle className="h-3 w-3" /> Cancelled
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                </div>

                                {/* Deactivated by Admin Banner */}
                                {isDeactivatedByAdmin && (
                                  <div className="mt-3 p-3 rounded-lg bg-red-500/10 border border-red-500/20">
                                    <p className="text-sm text-red-300 font-medium flex items-center gap-2">
                                      <AlertCircle className="h-4 w-4 shrink-0" />
                                      This agent has been deactivated by the administrator
                                    </p>
                                    <p className="text-xs text-red-300/60 mt-1 ml-6">
                                      Please contact support or purchase again to reactivate this agent.
                                    </p>
                                  </div>
                                )}

                                {/* Expired Banner */}
                                {isExpired && !isDeactivatedByAdmin && (
                                  <div className="mt-3 p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20">
                                    <p className="text-sm text-yellow-300 font-medium flex items-center gap-2">
                                      <Clock className="h-4 w-4 shrink-0" />
                                      Your subscription for this agent has ended
                                    </p>
                                    <p className="text-xs text-yellow-300/60 mt-1 ml-6">
                                      {agent.expires_at ? `Expired on ${formatDate(agent.expires_at)}` : 'Subscription period has ended'}.
                                      {agent.time_ended_ago && <span className="font-semibold text-yellow-300/80"> ({agent.time_ended_ago})</span>}
                                      {' '}Purchase again to continue using this agent.
                                    </p>
                                  </div>
                                )}

                                {/* Timeline */}
                                <div className="mt-4 ml-1">
                                  <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">Timeline</p>
                                  <div className="relative border-l-2 border-white/10 ml-2 pl-4 space-y-3">
                                    {/* Purchase event */}
                                    <div className="relative">
                                      <div className="absolute -left-[23px] top-1 w-3 h-3 rounded-full bg-green-500 border-2 border-[#120d22]"></div>
                                      <p className="text-sm text-white/80 font-medium">Purchased</p>
                                      <p className="text-xs text-white/40">{formatDate(agent.purchased_at)}</p>
                                      {agent.purchased_by_name && (
                                        <p className="text-xs text-white/30">By: {agent.purchased_by_name}</p>
                                      )}
                                      {agent.price_paid != null && (
                                        <p className="text-xs text-white/30">Amount: ${agent.price_paid}</p>
                                      )}
                                      {agent.active_label && (
                                        <p className="text-xs text-blue-400 font-medium">
                                          {agent.active_label}
                                          {agent.time_remaining && <span> &middot; {agent.time_remaining}</span>}
                                        </p>
                                      )}
                                    </div>

                                    {/* Expiry event */}
                                    {agent.expires_at && (
                                      <div className="relative">
                                        <div className={`absolute -left-[23px] top-1 w-3 h-3 rounded-full border-2 border-[#120d22] ${isExpired ? 'bg-red-500' : 'bg-blue-500'}`}></div>
                                        <p className="text-sm text-white/80 font-medium">{isExpired ? 'Subscription Ended' : 'Expires'}</p>
                                        <p className="text-xs text-white/40">{formatDate(agent.expires_at)}</p>
                                        {agent.time_remaining && (
                                          <p className="text-xs text-green-400 font-medium mt-0.5">{agent.time_remaining}</p>
                                        )}
                                        {agent.time_ended_ago && (
                                          <p className="text-xs text-red-400 font-medium mt-0.5">{agent.time_ended_ago}</p>
                                        )}
                                      </div>
                                    )}

                                    {/* Cancelled / Deactivated event */}
                                    {agent.cancelled_at && (
                                      <div className="relative">
                                        <div className="absolute -left-[23px] top-1 w-3 h-3 rounded-full bg-red-500 border-2 border-[#120d22]"></div>
                                        <p className="text-sm text-white/80 font-medium">
                                          {isDeactivatedByAdmin ? 'Deactivated by Admin' : 'Cancelled'}
                                        </p>
                                        <p className="text-xs text-white/40">{formatDate(agent.cancelled_at)}</p>
                                      </div>
                                    )}

                                    {/* Current status */}
                                    <div className="relative flex items-baseline gap-2">
                                      <div className={`absolute -left-[23px] top-1 w-3 h-3 rounded-full border-2 border-[#120d22] ${
                                        isActive ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.4)]' : 'bg-gray-500'
                                      }`}></div>
                                      <p className="text-sm text-white/80 font-medium">Current Status</p>
                                      <p className={`text-xs font-semibold ${
                                        isActive ? 'text-green-400' : isDeactivatedByAdmin ? 'text-red-400' : isExpired ? 'text-yellow-400' : 'text-gray-400'
                                      }`}>
                                        {isActive ? 'Active' : isDeactivatedByAdmin ? 'Deactivated by Admin' : isExpired ? 'Expired' : 'Cancelled'}
                                      </p>
                                    </div>
                                  </div>
                                </div>
                              </div>

                              {/* Right: Actions */}
                              <div className="flex flex-col gap-2 lg:min-w-[160px]">
                                {isActive && (
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    className="border-green-500/30 text-green-400 hover:bg-green-500/10 w-full"
                                    disabled
                                  >
                                    <CheckCircle2 className="h-4 w-4 mr-2" />
                                    Active
                                  </Button>
                                )}
                                {canRepurchase && (
                                  <Button
                                    onClick={() => handlePurchaseAgain(agent.module_name)}
                                    disabled={purchasingModule === agent.module_name}
                                    className="bg-violet-600 hover:bg-violet-700 text-white w-full"
                                    size="sm"
                                  >
                                    {purchasingModule === agent.module_name ? (
                                      <Loader2 className="h-4 w-4 animate-spin mr-2" />
                                    ) : (
                                      <RotateCcw className="h-4 w-4 mr-2" />
                                    )}
                                    Purchase Again
                                  </Button>
                                )}
                              </div>
                            </div>
                          </motion.div>
                        );
                      })}
                    </div>
                  )}
                </CardContent>
              </Card>
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
                  placeholder="e.g. Senior Software Engineer"
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
                    placeholder="e.g. New York, NY"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="department">Department *</Label>
                  <Input
                    id="department"
                    value={jobForm.department}
                    onChange={(e) => setJobForm({ ...jobForm, department: e.target.value })}
                    required
                    placeholder="e.g. Engineering"
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
                  placeholder="Describe the job role, responsibilities, and what you're looking for..."
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="requirements">Requirements</Label>
                <Textarea
                  id="requirements"
                  value={jobForm.requirements}
                  onChange={(e) => setJobForm({ ...jobForm, requirements: e.target.value })}
                  className="min-h-[100px]"
                  placeholder="List the required skills, qualifications, and experience..."
                />
              </div>
              <div className="flex gap-2 pt-4">
                <Button type="submit" className="flex-1" disabled={jobSubmitting}>
                  {jobSubmitting ? <><Loader2 className="h-4 w-4 animate-spin mr-2" />Posting...</> : 'Post Job'}
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
                    placeholder="e.g. user@example.com"
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
                    minLength={8}
                    placeholder="Min 8 chars, uppercase, lowercase, digit, special"
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
                    minLength={8}
                  />
                </div>
              )}
              
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="fullName">Full Name *</Label>
                  <Input
                    id="fullName"
                    value={userForm.fullName}
                    onChange={(e) => setUserForm({ ...userForm, fullName: e.target.value })}
                    required
                    placeholder="e.g. John Doe"
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
                  <Label htmlFor="phoneNumber">Phone Number *</Label>
                  <Input
                    id="phoneNumber"
                    value={userForm.phoneNumber}
                    onChange={(e) => setUserForm({ ...userForm, phoneNumber: e.target.value })}
                    required
                    placeholder="e.g. +1 234 567 8900"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="location">Location</Label>
                  <Input
                    id="location"
                    value={userForm.location}
                    onChange={(e) => setUserForm({ ...userForm, location: e.target.value })}
                    placeholder="e.g. San Francisco, CA"
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
                  placeholder="Tell us about this user's background and expertise..."
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
                <Button type="submit" disabled={userSubmitting}>
                  {userSubmitting ? <><Loader2 className="h-4 w-4 animate-spin mr-2" />Submitting...</> : (editingUser ? 'Update User' : 'Create User')}
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

        {/* Task Description Modal */}
        <Dialog open={showDescriptionModal} onOpenChange={setShowDescriptionModal}>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>{selectedTaskDescription?.title || 'Task Description'}</DialogTitle>
            </DialogHeader>
            <div className="mt-4">
              {selectedTaskDescription?.description ? (
                <p className="text-sm whitespace-pre-wrap">{selectedTaskDescription.description}</p>
              ) : (
                <p className="text-sm text-muted-foreground">No description available</p>
              )}
            </div>
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
              due_date: '',
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
              
              <div className="space-y-2">
                <Label htmlFor="task-due-date">Due Date (Deadline)</Label>
                <Input
                  id="task-due-date"
                  type="datetime-local"
                  value={taskForm.due_date}
                  onChange={(e) => setTaskForm({ ...taskForm, due_date: e.target.value })}
                />
                <p className="text-xs text-muted-foreground">
                  Set the deadline for this task. This is when the task should be completed.
                </p>
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

