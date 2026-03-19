import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Plus } from 'lucide-react';
import { companyApi } from '@/services/companyAuthService';

const ManualTaskCreation = ({ onTaskCreated }) => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [projects, setProjects] = useState([]);
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [users, setUsers] = useState([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [formData, setFormData] = useState({
    project_id: '',
    title: '',
    description: '',
    status: 'todo',
    priority: 'medium',
    assignee_id: '',
    due_date: '',
    estimated_hours: '',
  });

  useEffect(() => {
    fetchProjects();
    fetchUsers();
  }, []);

  useEffect(() => {
    // When project changes, fetch users for that project
    if (formData.project_id) {
      fetchUsers(formData.project_id);
    } else {
      fetchUsers();
    }
  }, [formData.project_id]);

  const fetchProjects = async () => {
    try {
      setLoadingProjects(true);
      const response = await companyApi.get('/project-manager/dashboard');
      if (response.status === 'success' && response.data.projects) {
        setProjects(response.data.projects || []);
      }
    } catch (error) {
      console.error('Error fetching projects:', error);
      toast({
        title: 'Error',
        description: 'Failed to load projects',
        variant: 'destructive',
      });
    } finally {
      setLoadingProjects(false);
    }
  };

  const fetchUsers = async (projectId = null) => {
    try {
      setLoadingUsers(true);
      const url = projectId 
        ? `/project-manager/users/?project_id=${projectId}`
        : '/project-manager/users/';
      const response = await companyApi.get(url);
      if (response.status === 'success' && response.data) {
        setUsers(response.data || []);
      }
    } catch (error) {
      console.error('Error fetching users:', error);
      // Don't show toast for user fetch errors as it's not critical
    } finally {
      setLoadingUsers(false);
    }
  };

  const handleChange = (field, value) => {
    setFormData(prev => ({
      ...prev,
      [field]: value
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!formData.project_id) {
      toast({
        title: 'Validation Error',
        description: 'Please select a project',
        variant: 'destructive',
      });
      return;
    }

    if (!formData.title.trim()) {
      toast({
        title: 'Validation Error',
        description: 'Task title is required',
        variant: 'destructive',
      });
      return;
    }

    try {
      setLoading(true);
      
      // Prepare data for API
      const payload = {
        project_id: parseInt(formData.project_id),
        title: formData.title,
        description: formData.description,
        status: formData.status,
        priority: formData.priority,
      };

      // Add optional fields if provided
      if (formData.assignee_id && formData.assignee_id !== "none") payload.assignee_id = parseInt(formData.assignee_id);
      if (formData.due_date) payload.due_date = formData.due_date;
      if (formData.estimated_hours) payload.estimated_hours = parseFloat(formData.estimated_hours);

      const response = await companyApi.post('/project-manager/tasks/create/', payload);
      
      if (response.status === 'success') {
        toast({
          title: 'Success',
          description: 'Task created successfully',
        });
        
        // Reset form
        setFormData({
          project_id: formData.project_id, // Keep project selected
          title: '',
          description: '',
          status: 'todo',
          priority: 'medium',
          assignee_id: '',
          due_date: '',
          estimated_hours: '',
        });

        // Notify parent component
        if (onTaskCreated) {
          onTaskCreated();
        }
      } else {
        throw new Error(response.message || 'Failed to create task');
      }
    } catch (error) {
      console.error('Error creating task:', error);
      toast({
        title: 'Error',
        description: error.message || 'Failed to create task',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="border-white/10 bg-black/20 backdrop-blur-sm">
      <CardHeader>
        <CardTitle>Create Task Manually</CardTitle>
        <CardDescription>
          Add a new task to a project by filling out the form below
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Project Selection */}
            <div className="md:col-span-2">
              <Label htmlFor="project_id">Project *</Label>
              <Select 
                value={formData.project_id} 
                onValueChange={(value) => handleChange('project_id', value)}
                disabled={loadingProjects}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select a project" />
                </SelectTrigger>
                <SelectContent>
                  {projects.map(project => (
                    <SelectItem key={project.id} value={project.id.toString()}>
                      {project.name} ({project.status})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Task Title */}
            <div className="md:col-span-2">
              <Label htmlFor="title">Task Title *</Label>
              <Input
                id="title"
                value={formData.title}
                onChange={(e) => handleChange('title', e.target.value)}
                placeholder="Enter task title"
                required
              />
            </div>

            {/* Description */}
            <div className="md:col-span-2">
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                value={formData.description}
                onChange={(e) => handleChange('description', e.target.value)}
                placeholder="Enter task description"
                rows={4}
              />
            </div>

            {/* Status */}
            <div>
              <Label htmlFor="status">Status</Label>
              <Select value={formData.status} onValueChange={(value) => handleChange('status', value)}>
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

            {/* Priority */}
            <div>
              <Label htmlFor="priority">Priority</Label>
              <Select value={formData.priority} onValueChange={(value) => handleChange('priority', value)}>
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

            {/* Deadline */}
            <div>
              <Label htmlFor="due_date">Deadline</Label>
              <Input
                id="due_date"
                type="datetime-local"
                value={formData.due_date}
                onChange={(e) => handleChange('due_date', e.target.value)}
              />
            </div>

            {/* Estimated Hours */}
            <div>
              <Label htmlFor="estimated_hours">Estimated Hours</Label>
              <Input
                id="estimated_hours"
                type="number"
                step="0.5"
                min="0"
                value={formData.estimated_hours}
                onChange={(e) => handleChange('estimated_hours', e.target.value)}
                placeholder="0.0"
              />
            </div>

            {/* Assignee */}
            <div className="md:col-span-2">
              <Label htmlFor="assignee_id">Assign To</Label>
              <Select 
                value={formData.assignee_id || "none"} 
                onValueChange={(value) => handleChange('assignee_id', value === "none" ? "" : value)}
                disabled={loadingUsers}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select a user (optional)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Unassigned</SelectItem>
                  {users.map(user => (
                    <SelectItem key={user.id} value={user.id.toString()}>
                      {user.name || user.username} {user.role ? `(${user.role})` : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex justify-end gap-2">
            <Button type="submit" disabled={loading || !formData.project_id}>
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <Plus className="h-4 w-4 mr-2" />
                  Create Task
                </>
              )}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
};

export default ManualTaskCreation;

