import React, { useState, useEffect } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Label } from '@/components/ui/label';
import { useToast } from '@/components/ui/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import userTaskService from '@/services/userTaskService';
import userProjectManagerService from '@/services/userProjectManagerService';
import DashboardNavbar from '@/components/common/DashboardNavbar';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { 
  ListTodo, 
  FolderKanban, 
  Loader2, 
  Calendar, 
  Clock, 
  User, 
  CheckCircle2,
  Circle,
  PlayCircle,
  AlertCircle,
  FileCheck,
  TrendingUp,
  Plus,
  Users,
  Edit,
  ChevronDown,
  ChevronUp
} from 'lucide-react';

// Helper function to format role for display
const formatRole = (role) => {
  if (!role) return 'USER';
  return role
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
};

const UserDashboardPage = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { user, logout, isAuthenticated } = useAuth();
  
  const [tasks, setTasks] = useState([]);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('tasks');
  const [statusFilter, setStatusFilter] = useState('all');
  
  // Project Manager specific state
  const isProjectManager = user?.role === 'project_manager';
  const [allProjectTasks, setAllProjectTasks] = useState([]);
  const [allProjectTasksLoading, setAllProjectTasksLoading] = useState(false);
  const [pmProjects, setPmProjects] = useState([]);
  const [expandedProjects, setExpandedProjects] = useState(new Set());
  const [showCreateProjectModal, setShowCreateProjectModal] = useState(false);
  const [showCreateTaskModal, setShowCreateTaskModal] = useState(false);
  const [showEditProjectModal, setShowEditProjectModal] = useState(false);
  const [showEditTaskModal, setShowEditTaskModal] = useState(false);
  const [editingProject, setEditingProject] = useState(null);
  const [editingTask, setEditingTask] = useState(null);
  const [companyUsers, setCompanyUsers] = useState([]);
  const [projectForm, setProjectForm] = useState({
    name: '',
    description: '',
    status: 'planning',
    priority: 'medium',
    project_type: 'web_app',
  });
  const [taskForm, setTaskForm] = useState({
    project_id: '',
    title: '',
    description: '',
    priority: 'medium',
    status: 'todo',
    assignee_id: 'none',
  });

  useEffect(() => {
    // Check authentication
    if (!isAuthenticated) {
      toast({
        title: 'Not logged in',
        description: 'Please log in to access your dashboard',
        variant: 'destructive',
      });
      navigate('/login');
      return;
    }

    fetchTasks();
    fetchProjects();
    
    // Fetch project manager data if user is a project manager
    if (isProjectManager) {
      fetchAllProjectTasks();
      fetchPmProjects();
      fetchCompanyUsers();
    }
  }, [statusFilter, isProjectManager]);

  // Sync slider values when tasks are fetched
  useEffect(() => {
    const newSliderValues = {};
    tasks.forEach(task => {
      if (task.progress_percentage !== null && task.progress_percentage !== undefined) {
        newSliderValues[task.id] = task.progress_percentage;
      }
    });
    setSliderValues(newSliderValues);
  }, [tasks]);

  const fetchTasks = async () => {
    try {
      setLoading(true);
      const params = statusFilter !== 'all' ? { status: statusFilter } : {};
      const response = await userTaskService.getMyTasks(params);
      if (response.status === 'success') {
        setTasks(response.data || []);
      }
    } catch (error) {
      console.error('Error fetching tasks:', error);
      toast({
        title: 'Error',
        description: error.message || 'Failed to load tasks',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const fetchProjects = async () => {
    try {
      const response = await userTaskService.getMyProjects();
      if (response.status === 'success') {
        setProjects(response.data || []);
      }
    } catch (error) {
      console.error('Error fetching projects:', error);
    }
  };

  const handleStatusChange = async (taskId, newStatus) => {
    try {
      // Determine if we need to update progress based on status
      let progressUpdate = null;
      if (newStatus === 'done') {
        progressUpdate = 100;
      } else if (newStatus === 'todo') {
        progressUpdate = 0;
      }
      // For 'in_progress' and 'review', don't change progress
      // For 'blocked', don't change progress (slider will be disabled)
      
      // Update status (and progress if needed)
      const response = await userTaskService.updateTaskStatus(taskId, newStatus);
      if (response.status === 'success') {
        // If we need to update progress, do it
        if (progressUpdate !== null) {
          try {
            await userTaskService.updateTaskProgress(taskId, progressUpdate);
            // Update local state for both status and progress
            setTasks(prevTasks => 
              prevTasks.map(task => 
                task.id === taskId 
                  ? { ...task, status: newStatus, progress_percentage: progressUpdate }
                  : task
              )
            );
            setSliderValues(prev => ({
              ...prev,
              [taskId]: progressUpdate
            }));
          } catch (progressError) {
            console.error('Error updating progress:', progressError);
            // Status was updated, but progress update failed - still show success
          }
        } else {
          // Just update status
          setTasks(prevTasks => 
            prevTasks.map(task => 
              task.id === taskId 
                ? { ...task, status: newStatus }
                : task
            )
          );
        }
        
        toast({
          title: 'Success',
          description: progressUpdate !== null 
            ? 'Task status and progress updated successfully'
            : 'Task status updated successfully',
        });
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to update task status',
        variant: 'destructive',
      });
    }
  };

  // Local state for slider values to prevent glitching
  const [sliderValues, setSliderValues] = useState({});

  const handleProgressChange = (taskId, progress) => {
    // Update local state immediately for smooth slider movement
    setSliderValues(prev => ({
      ...prev,
      [taskId]: progress
    }));
    
    // Update tasks state for immediate UI feedback
    setTasks(prevTasks => 
      prevTasks.map(task => 
        task.id === taskId 
          ? { ...task, progress_percentage: progress }
          : task
      )
    );
  };

  const handleProgressCommit = async (taskId, progress) => {
    // Only make API call when user releases the slider
    try {
      // Determine if we need to update status based on progress
      let statusUpdate = null;
      if (progress === 0) {
        statusUpdate = 'todo';
      } else if (progress === 100) {
        statusUpdate = 'done';
      } else if (progress > 0 && progress < 100) {
        // Only update to in_progress if current status is not blocked
        // Get current task to check status
        const currentTask = tasks.find(t => t.id === taskId);
        if (currentTask && currentTask.status !== 'blocked') {
          statusUpdate = 'in_progress';
        }
      }
      
      // Update progress first
      const progressResponse = await userTaskService.updateTaskProgress(taskId, progress);
      if (progressResponse.status === 'success') {
        // If we need to update status, do it
        if (statusUpdate !== null) {
          try {
            await userTaskService.updateTaskStatus(taskId, statusUpdate);
            // Update local state for both progress and status
            setTasks(prevTasks => 
              prevTasks.map(task => 
                task.id === taskId 
                  ? { ...task, progress_percentage: progress, status: statusUpdate }
                  : task
              )
            );
          } catch (statusError) {
            console.error('Error updating status:', statusError);
            // Progress was updated, but status update failed - still update progress
            setTasks(prevTasks => 
              prevTasks.map(task => 
                task.id === taskId 
                  ? { ...task, progress_percentage: progress }
                  : task
              )
            );
          }
        } else {
          // Just update progress
          setTasks(prevTasks => 
            prevTasks.map(task => 
              task.id === taskId 
                ? { ...task, progress_percentage: progress }
                : task
            )
          );
        }
      } else {
        // Revert on error
        fetchTasks();
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to update task progress',
        variant: 'destructive',
      });
      // Revert on error
      fetchTasks();
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

  const getStatusColor = (status) => {
    switch (status) {
      case 'done':
        return 'bg-green-100 text-green-800';
      case 'in_progress':
        return 'bg-blue-100 text-blue-800';
      case 'review':
        return 'bg-purple-100 text-purple-800';
      case 'blocked':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
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

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  // Project Manager functions
  const fetchAllProjectTasks = async () => {
    if (!isProjectManager) return;
    try {
      setAllProjectTasksLoading(true);
      const response = await userProjectManagerService.getProjectsTasks();
      if (response.status === 'success') {
        setAllProjectTasks(response.data || []);
      }
    } catch (error) {
      console.error('Error fetching all project tasks:', error);
      toast({
        title: 'Error',
        description: error.message || 'Failed to load project tasks',
        variant: 'destructive',
      });
    } finally {
      setAllProjectTasksLoading(false);
    }
  };

  const fetchPmProjects = async () => {
    if (!isProjectManager) return;
    try {
      const response = await userProjectManagerService.getProjects();
      if (response.status === 'success') {
        setPmProjects(response.data || []);
      }
    } catch (error) {
      console.error('Error fetching PM projects:', error);
    }
  };

  const fetchCompanyUsers = async () => {
    if (!isProjectManager) return;
    try {
      const response = await userProjectManagerService.getCompanyUsers();
      if (response.status === 'success') {
        setCompanyUsers(response.data || []);
      }
    } catch (error) {
      console.error('Error fetching company users:', error);
    }
  };

  const handleCreateProject = async (e) => {
    e.preventDefault();
    try {
      const response = await userProjectManagerService.createProject(projectForm);
      if (response.status === 'success') {
        toast({
          title: 'Success',
          description: 'Project created successfully',
        });
        setShowCreateProjectModal(false);
        setProjectForm({
          name: '',
          description: '',
          status: 'planning',
          priority: 'medium',
          project_type: 'web_app',
        });
        fetchPmProjects();
        fetchAllProjectTasks();
        fetchProjects();
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to create project',
        variant: 'destructive',
      });
    }
  };

  const handleCreateTask = async (e) => {
    e.preventDefault();
    if (!taskForm.project_id || taskForm.project_id === 'none') {
      toast({
        title: 'Error',
        description: 'Please select a project',
        variant: 'destructive',
      });
      return;
    }
    try {
      const assigneeId = taskForm.assignee_id === 'none' ? null : taskForm.assignee_id;
      const response = await userProjectManagerService.createTask({
        ...taskForm,
        assignee_id: assigneeId,
      });
      if (response.status === 'success') {
        toast({
          title: 'Success',
          description: 'Task created successfully',
        });
        setShowCreateTaskModal(false);
        setTaskForm({
          project_id: '',
          title: '',
          description: '',
          priority: 'medium',
          status: 'todo',
          assignee_id: 'none',
        });
        fetchAllProjectTasks();
        fetchTasks();
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to create task',
        variant: 'destructive',
      });
    }
  };

  const handleEditProject = (project) => {
    setEditingProject(project);
    setProjectForm({
      name: project.name || '',
      description: project.description || '',
      status: project.status || 'planning',
      priority: project.priority || 'medium',
      project_type: project.project_type || 'web_app',
    });
    setShowEditProjectModal(true);
  };

  const handleUpdateProject = async (e) => {
    e.preventDefault();
    if (!editingProject) return;
    try {
      const response = await userProjectManagerService.updateProject(editingProject.id, projectForm);
      if (response.status === 'success') {
        toast({
          title: 'Success',
          description: 'Project updated successfully',
        });
        setShowEditProjectModal(false);
        setEditingProject(null);
        fetchPmProjects();
        fetchAllProjectTasks();
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

  const handleEditTask = (task, projectId) => {
    setEditingTask(task);
    const assigneeId = task.assignee_id ? task.assignee_id.toString() : 'none';
    setTaskForm({
      project_id: projectId ? projectId.toString() : '',
      title: task.title || '',
      description: task.description || '',
      priority: task.priority || 'medium',
      status: task.status || 'todo',
      assignee_id: assigneeId,
    });
    setShowEditTaskModal(true);
  };

  const handleUpdateTask = async (e) => {
    e.preventDefault();
    if (!editingTask) return;
    try {
      const assigneeId = taskForm.assignee_id === 'none' || taskForm.assignee_id === '' ? null : taskForm.assignee_id;
      // Don't send project_id in update - it shouldn't be changed
      const { project_id, ...updateData } = taskForm;
      const response = await userProjectManagerService.updateTask(editingTask.id, {
        ...updateData,
        assignee_id: assigneeId,
      });
      if (response.status === 'success') {
        toast({
          title: 'Success',
          description: 'Task updated successfully',
        });
        setShowEditTaskModal(false);
        setEditingTask(null);
        fetchAllProjectTasks();
        fetchTasks();
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to update task',
        variant: 'destructive',
      });
    }
  };

  const toggleProjectExpansion = (projectId) => {
    setExpandedProjects(prev => {
      const newSet = new Set(prev);
      if (newSet.has(projectId)) {
        newSet.delete(projectId);
      } else {
        newSet.add(projectId);
      }
      return newSet;
    });
  };

  // Get user role and format it for display
  const userRole = user?.role || 'user';
  const formattedRole = formatRole(userRole);
  const dashboardTitle = `THE ${formattedRole.toUpperCase()} DASHBOARD`;
  const dashboardSubtitle = 'Manage your tasks and projects';

  return (
    <>
      <Helmet>
        <title>{dashboardTitle} - Pay Per Project</title>
      </Helmet>

      <DashboardNavbar 
        icon={User}
        title={dashboardTitle}
        subtitle={dashboardSubtitle}
        user={user} 
        userRole={formattedRole}
        onLogout={handleLogout}
        showCompanyUserOptions={false}
      />

      <div className="container mx-auto px-4 py-8 max-w-7xl">
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="tasks">
              <ListTodo className="h-4 w-4 mr-2" />
              My Tasks
            </TabsTrigger>
            <TabsTrigger value="projects">
              <FolderKanban className="h-4 w-4 mr-2" />
              My Projects
            </TabsTrigger>
            {isProjectManager && (
              <>
                <TabsTrigger value="all-project-tasks">
                  <ListTodo className="h-4 w-4 mr-2" />
                  All Project Tasks
                </TabsTrigger>
                <TabsTrigger value="create-project">
                  <Plus className="h-4 w-4 mr-2" />
                  Create Project
                </TabsTrigger>
                <TabsTrigger value="create-task">
                  <Plus className="h-4 w-4 mr-2" />
                  Create Task
                </TabsTrigger>
              </>
            )}
          </TabsList>

          <TabsContent value="tasks" className="space-y-4 mt-6">
            {/* Status Filter */}
            <div className="flex items-center gap-4">
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder="Filter by status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Tasks</SelectItem>
                  <SelectItem value="todo">To Do</SelectItem>
                  <SelectItem value="in_progress">In Progress</SelectItem>
                  <SelectItem value="review">Review</SelectItem>
                  <SelectItem value="done">Done</SelectItem>
                  <SelectItem value="blocked">Blocked</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {loading ? (
              <div className="flex justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin" />
              </div>
            ) : tasks.length === 0 ? (
              <Card>
                <CardContent className="py-12 text-center">
                  <ListTodo className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                  <p className="text-lg font-medium mb-2">No tasks assigned</p>
                  <p className="text-sm text-muted-foreground">
                    {statusFilter !== 'all' 
                      ? `No tasks with status "${statusFilter}"`
                      : 'You don\'t have any tasks assigned yet'}
                  </p>
                </CardContent>
              </Card>
            ) : (
              <div className="grid gap-4">
                {tasks.map((task) => (
                  <Card key={task.id} className="hover:shadow-md transition-shadow">
                    <CardHeader>
                      <div className="flex justify-between items-start">
                        <div className="flex-1">
                          <CardTitle className="text-lg mb-2">{task.title}</CardTitle>
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
                            {task.due_date && (
                              <span className="text-sm text-muted-foreground flex items-center gap-1">
                                <Calendar className="h-4 w-4" />
                                {new Date(task.due_date).toLocaleDateString()}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {/* Progress Slider */}
                      <div className="space-y-2">
                        <div className="flex justify-between items-center">
                          <Label className="text-sm font-medium">Progress</Label>
                          <span className="text-sm text-muted-foreground">
                            {sliderValues[task.id] !== undefined ? sliderValues[task.id] : (task.progress_percentage || 0)}%
                          </span>
                        </div>
                        <Slider
                          value={[sliderValues[task.id] !== undefined ? sliderValues[task.id] : (task.progress_percentage || 0)]}
                          onValueChange={(value) => {
                            // Only allow changes if status is not blocked
                            if (task.status !== 'blocked') {
                              handleProgressChange(task.id, value[0]);
                            }
                          }}
                          onValueCommit={(value) => {
                            // Only allow changes if status is not blocked
                            if (task.status !== 'blocked') {
                              handleProgressCommit(task.id, value[0]);
                            }
                          }}
                          max={100}
                          step={1}
                          className="w-full"
                          disabled={task.status === 'blocked'}
                        />
                      </div>

                      {/* Status Update */}
                      <div className="flex items-center gap-2">
                        <Label className="text-sm font-medium w-20">Status:</Label>
                        <Select
                          value={task.status}
                          onValueChange={(value) => handleStatusChange(task.id, value)}
                        >
                          <SelectTrigger className="flex-1">
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

                      {/* Subtasks */}
                      {task.subtasks && task.subtasks.length > 0 && (
                        <div className="mt-4 pt-4 border-t">
                          <p className="text-sm font-medium mb-2">Subtasks ({task.subtasks.length}):</p>
                          <div className="space-y-1">
                            {task.subtasks.map((subtask) => (
                              <div key={subtask.id} className="flex items-center gap-2 text-sm">
                                {subtask.status === 'done' ? (
                                  <CheckCircle2 className="h-4 w-4 text-green-600" />
                                ) : (
                                  <Circle className="h-4 w-4 text-gray-400" />
                                )}
                                <span className={subtask.status === 'done' ? 'line-through text-muted-foreground' : ''}>
                                  {subtask.title}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>

          <TabsContent value="projects" className="space-y-4 mt-6">
            {loading ? (
              <div className="flex justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin" />
              </div>
            ) : projects.length === 0 ? (
              <Card>
                <CardContent className="py-12 text-center">
                  <FolderKanban className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                  <p className="text-lg font-medium mb-2">No projects assigned</p>
                  <p className="text-sm text-muted-foreground">
                    You don't have any projects assigned yet
                  </p>
                </CardContent>
              </Card>
            ) : (
              <div className="grid gap-4">
                {projects.map((project) => (
                  <Card key={project.id} className="hover:shadow-md transition-shadow">
                    <CardHeader>
                      <div className="flex justify-between items-start">
                        <div className="flex-1">
                          <CardTitle className="text-lg">{project.name}</CardTitle>
                          {project.description && (
                            <p className="text-sm text-muted-foreground mt-2 line-clamp-2">
                              {project.description}
                            </p>
                          )}
                          <div className="flex flex-wrap gap-2 mt-3">
                            <Badge variant="outline">{project.status}</Badge>
                            <Badge variant="secondary">{project.priority} Priority</Badge>
                            {project.my_task_count > 0 && (
                              <span className="text-sm text-muted-foreground flex items-center gap-1">
                                <ListTodo className="h-4 w-4" />
                                {project.my_task_count} task{project.my_task_count !== 1 ? 's' : ''}
                              </span>
                            )}
                            {project.completed_task_count > 0 && (
                              <span className="text-sm text-muted-foreground flex items-center gap-1">
                                <CheckCircle2 className="h-4 w-4 text-green-600" />
                                {project.completed_task_count} completed
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </CardHeader>
                    {project.start_date && (
                      <CardContent>
                        <div className="flex items-center gap-4 text-sm text-muted-foreground">
                          {project.start_date && (
                            <span className="flex items-center gap-1">
                              <Calendar className="h-4 w-4" />
                              Started: {new Date(project.start_date).toLocaleDateString()}
                            </span>
                          )}
                          {project.deadline && (
                            <span className="flex items-center gap-1">
                              <Clock className="h-4 w-4" />
                              Deadline: {new Date(project.deadline).toLocaleDateString()}
                            </span>
                          )}
                        </div>
                      </CardContent>
                    )}
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>

          {/* All Project Tasks Tab (Project Manager Only) */}
          {isProjectManager && (
            <TabsContent value="all-project-tasks" className="space-y-4 mt-6">
              {allProjectTasksLoading ? (
                <div className="flex justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin" />
                </div>
              ) : allProjectTasks.length === 0 ? (
                <Card>
                  <CardContent className="py-12 text-center">
                    <ListTodo className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                    <p className="text-lg font-medium mb-2">No projects found</p>
                    <p className="text-sm text-muted-foreground">
                      You need to have at least one task assigned in a project to see all tasks from that project
                    </p>
                  </CardContent>
                </Card>
              ) : (
                 <div className="space-y-6">
                   {allProjectTasks.map((project) => {
                     const isExpanded = expandedProjects.has(project.id);
                     return (
                       <Card key={project.id}>
                         <CardHeader>
                           <div className="flex items-center justify-between">
                             <div className="flex items-center gap-2 flex-1">
                               <Button
                                 variant="ghost"
                                 size="sm"
                                 onClick={() => toggleProjectExpansion(project.id)}
                                 className="h-8 w-8 p-0 hover:bg-muted"
                               >
                                 {isExpanded ? (
                                   <ChevronUp className="h-5 w-5" />
                                 ) : (
                                   <ChevronDown className="h-5 w-5" />
                                 )}
                               </Button>
                               <CardTitle className="text-xl cursor-pointer" onClick={() => toggleProjectExpansion(project.id)}>
                                 {project.name}
                               </CardTitle>
                             </div>
                             <Button
                               variant="ghost"
                               size="sm"
                               onClick={() => handleEditProject(project)}
                               className="h-8 w-8 p-0"
                             >
                               <Edit className="h-4 w-4" />
                             </Button>
                           </div>
                           {project.description && (
                             <p className="text-sm text-muted-foreground mt-2">{project.description}</p>
                           )}
                           <div className="flex gap-2 mt-3">
                             <Badge variant="outline">{project.status}</Badge>
                             <Badge variant="secondary">{project.priority}</Badge>
                             <Badge variant="outline">{project.tasks_count} tasks</Badge>
                           </div>
                         </CardHeader>
                         {isExpanded && (
                           <CardContent>
                             {project.tasks && project.tasks.length > 0 ? (
                               <div className="space-y-3">
                                 {project.tasks.map((task) => (
                                   <Card key={task.id} className="bg-muted/30">
                                     <CardContent className="pt-4">
                                       <div className="flex justify-between items-start">
                                         <div className="flex-1">
                                           <div className="flex items-center gap-2">
                                             <p className="font-medium">{task.title}</p>
                                             <Button
                                               variant="ghost"
                                               size="sm"
                                               onClick={() => handleEditTask({ ...task, project_id: project.id }, project.id)}
                                               className="h-6 w-6 p-0"
                                             >
                                               <Edit className="h-3 w-3" />
                                             </Button>
                                           </div>
                                           {task.description && (
                                             <p className="text-sm text-muted-foreground mt-1">{task.description}</p>
                                           )}
                                           <div className="flex flex-wrap gap-2 mt-2">
                                             <Badge className={getStatusColor(task.status)}>
                                               {getStatusIcon(task.status)}
                                               <span className="ml-1 capitalize">{task.status.replace('_', ' ')}</span>
                                             </Badge>
                                             <Badge variant="outline" className={getPriorityColor(task.priority)}>
                                               {task.priority} Priority
                                             </Badge>
                                             {task.assignee_name && (
                                               <span className="text-sm text-muted-foreground flex items-center gap-1">
                                                 <User className="h-3 w-3" />
                                                 {task.assignee_name}
                                               </span>
                                             )}
                                             {task.due_date && (
                                               <span className="text-sm text-muted-foreground flex items-center gap-1">
                                                 <Clock className="h-3 w-3" />
                                                 {new Date(task.due_date).toLocaleDateString()}
                                               </span>
                                             )}
                                             {task.progress_percentage !== null && (
                                               <span className="text-sm text-muted-foreground">
                                                 {task.progress_percentage}% complete
                                               </span>
                                             )}
                                           </div>
                                         </div>
                                       </div>
                                     </CardContent>
                                   </Card>
                                 ))}
                               </div>
                             ) : (
                               <p className="text-sm text-muted-foreground">No tasks in this project</p>
                             )}
                           </CardContent>
                         )}
                       </Card>
                     );
                   })}
                 </div>
              )}
            </TabsContent>
          )}

          {/* Create Project Tab (Project Manager Only) */}
          {isProjectManager && (
            <TabsContent value="create-project" className="space-y-4 mt-6">
              <Card>
                <CardHeader>
                  <CardTitle>Create New Project</CardTitle>
                </CardHeader>
                <CardContent>
                  <form onSubmit={handleCreateProject} className="space-y-4">
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
                    <Button type="submit" className="w-full">
                      Create Project
                    </Button>
                  </form>
                </CardContent>
              </Card>
            </TabsContent>
          )}

          {/* Create Task Tab (Project Manager Only) */}
          {isProjectManager && (
            <TabsContent value="create-task" className="space-y-4 mt-6">
              <Card>
                <CardHeader>
                  <CardTitle>Create New Task</CardTitle>
                </CardHeader>
                <CardContent>
                  <form onSubmit={handleCreateTask} className="space-y-4">
                    <div className="space-y-2">
                      <Label htmlFor="task-project">Project *</Label>
                      <Select
                        value={taskForm.project_id}
                        onValueChange={(value) => setTaskForm({ ...taskForm, project_id: value })}
                        required
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Select project" />
                        </SelectTrigger>
                        <SelectContent>
                          {pmProjects.map((project) => (
                            <SelectItem key={project.id} value={project.id.toString()}>
                              {project.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
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
                          {companyUsers.map((user) => (
                            <SelectItem key={user.id} value={user.id.toString()}>
                              {user.full_name} ({user.email}) - {user.role}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <Button type="submit" className="w-full">
                      Create Task
                    </Button>
                  </form>
                </CardContent>
              </Card>
            </TabsContent>
          )}
        </Tabs>

        {/* Edit Project Modal (Project Manager Only) */}
        {isProjectManager && (
          <Dialog open={showEditProjectModal} onOpenChange={(open) => {
            setShowEditProjectModal(open);
            if (!open) {
              setEditingProject(null);
              setProjectForm({
                name: '',
                description: '',
                status: 'planning',
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
                  <Label htmlFor="edit-project-name">Project Name *</Label>
                  <Input
                    id="edit-project-name"
                    value={projectForm.name}
                    onChange={(e) => setProjectForm({ ...projectForm, name: e.target.value })}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="edit-project-description">Description</Label>
                  <Textarea
                    id="edit-project-description"
                    value={projectForm.description}
                    onChange={(e) => setProjectForm({ ...projectForm, description: e.target.value })}
                    rows={4}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="edit-project-status">Status</Label>
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
                    <Label htmlFor="edit-project-priority">Priority</Label>
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
                  <Label htmlFor="edit-project-type">Project Type</Label>
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
        )}

        {/* Edit Task Modal (Project Manager Only) */}
        {isProjectManager && (
          <Dialog open={showEditTaskModal} onOpenChange={(open) => {
            setShowEditTaskModal(open);
            if (!open) {
              setEditingTask(null);
              setTaskForm({
                project_id: '',
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
                  <Label htmlFor="edit-task-title">Task Title *</Label>
                  <Input
                    id="edit-task-title"
                    value={taskForm.title}
                    onChange={(e) => setTaskForm({ ...taskForm, title: e.target.value })}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="edit-task-description">Description</Label>
                  <Textarea
                    id="edit-task-description"
                    value={taskForm.description}
                    onChange={(e) => setTaskForm({ ...taskForm, description: e.target.value })}
                    rows={4}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="edit-task-priority">Priority</Label>
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
                    <Label htmlFor="edit-task-status">Status</Label>
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
                  <Label htmlFor="edit-task-assignee">Assign To</Label>
                  <Select
                    value={taskForm.assignee_id || 'none'}
                    onValueChange={(value) => setTaskForm({ ...taskForm, assignee_id: value })}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select user (optional)" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">None (Unassign)</SelectItem>
                      {companyUsers.map((user) => (
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
        )}
      </div>
    </>
  );
};

export default UserDashboardPage;

