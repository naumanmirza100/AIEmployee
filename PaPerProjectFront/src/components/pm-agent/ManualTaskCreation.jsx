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
import { DateTimePicker } from '@/components/common/DatePicker';
import InfoHint from '../frontline/InfoHint';
import { PM_HINTS } from './pmTutorialSteps';

const ManualTaskCreation = ({ onTaskCreated, onSuccess, defaultProjectId }) => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [projects, setProjects] = useState([]);
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [users, setUsers] = useState([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [formData, setFormData] = useState({
    // Pre-fill the project when the caller (e.g. Tasks tab's "New Task"
    // dialog opened from within a project row) already knows which project
    // to add to. Empty string when not provided → user picks from dropdown.
    project_id: defaultProjectId ? String(defaultProjectId) : '',
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

  // `datetime-local` strings look like "2026-06-23T14:30" — comparing them as
  // ISO strings is a valid chronological compare. We use "now" rounded down to
  // the current minute as the lower bound so a value set "right now" is still
  // accepted instead of being rejected as a microsecond-old past time.
  const nowDatetimeLocal = () => {
    const d = new Date();
    const off = d.getTimezoneOffset() * 60_000;
    return new Date(d.getTime() - off).toISOString().slice(0, 16);
  };

  // BUG-06: parent project timeline drives the task due-date bounds.
  // Project dates come from the dashboard endpoint as YYYY-MM-DD; we convert
  // to datetime-local strings so DateTimePicker can compare against them.
  const selectedProject = projects.find(
    (p) => String(p.id) === String(formData.project_id),
  );
  const projectStartMin = selectedProject?.start_date
    ? `${selectedProject.start_date}T00:00`
    : null;
  const projectDeadlineMax = selectedProject?.deadline
    ? `${selectedProject.deadline}T23:59`
    : null;
  // Lower bound: the LATER of "now" and project start.
  const dueMin = projectStartMin && projectStartMin > nowDatetimeLocal()
    ? projectStartMin
    : nowDatetimeLocal();

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

    if (formData.due_date && formData.due_date < nowDatetimeLocal()) {
      toast({
        title: 'Invalid deadline',
        description: 'Task deadline cannot be in the past.',
        variant: 'destructive',
      });
      return;
    }

    // BUG-06: task deadline must be within parent project's timeline (only
    // enforced when the project actually has those dates set).
    if (formData.due_date && projectStartMin && formData.due_date < projectStartMin) {
      toast({
        title: 'Before project start',
        description: `This task is due before the project starts (${selectedProject.start_date}). Move it later or shift the project's start date.`,
        variant: 'destructive',
      });
      return;
    }
    if (formData.due_date && projectDeadlineMax && formData.due_date > projectDeadlineMax) {
      toast({
        title: 'After project deadline',
        description: `This task is due after the project deadline (${selectedProject.deadline}). Move it earlier or extend the project deadline first.`,
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

        // Notify parent component. `onTaskCreated` = legacy (parent
        // re-fetches its list). `onSuccess` = newer dialog wrapper hook so
        // it can close on submit. Both optional.
        if (onTaskCreated) {
          onTaskCreated();
        }
        if (onSuccess) {
          onSuccess();
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
            <div className="md:col-span-2" data-tour-pm-ct="project">
              <Label htmlFor="project_id" className="flex items-center gap-1.5">Project * <InfoHint {...PM_HINTS.pmCtProject} /></Label>
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
            <div className="md:col-span-2" data-tour-pm-ct="title">
              <Label htmlFor="title" className="flex items-center gap-1.5">Task Title * <InfoHint {...PM_HINTS.pmCtTitle} /></Label>
              <Input
                id="title"
                value={formData.title}
                onChange={(e) => handleChange('title', e.target.value)}
                placeholder="Enter task title"
                required
              />
            </div>

            {/* Description */}
            <div className="md:col-span-2" data-tour-pm-ct="desc">
              <Label htmlFor="description" className="flex items-center gap-1.5">Description <InfoHint {...PM_HINTS.pmCtDesc} /></Label>
              <Textarea
                id="description"
                value={formData.description}
                onChange={(e) => handleChange('description', e.target.value)}
                placeholder="Enter task description"
                rows={4}
              />
            </div>

            {/* Status */}
            <div data-tour-pm-ct="status">
              <Label htmlFor="status" className="flex items-center gap-1.5">Status <InfoHint {...PM_HINTS.pmCtStatus} /></Label>
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
            <div data-tour-pm-ct="priority">
              <Label htmlFor="priority" className="flex items-center gap-1.5">Priority <InfoHint {...PM_HINTS.pmCtPriority} /></Label>
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

            {/* Deadline — popover calendar + time picker (drop-in replacement for native datetime-local) */}
            <div data-tour-pm-ct="duedate">
              <Label htmlFor="due_date" className="flex items-center gap-1.5">Deadline <InfoHint {...PM_HINTS.pmCtDueDate} /></Label>
              <DateTimePicker
                id="due_date"
                value={formData.due_date}
                onChange={(v) => handleChange('due_date', v)}
                minValue={dueMin}
                maxValue={projectDeadlineMax || undefined}
                placeholder="Pick a deadline"
              />
              {/* BUG-06: surface the project's timeline so the user knows why
                  the picker is bounded. */}
              {(selectedProject?.start_date || selectedProject?.deadline) && (
                <p className="text-[11px] text-white/50 mt-1">
                  Project window:{' '}
                  {selectedProject.start_date || 'no start set'} →{' '}
                  {selectedProject.deadline || 'no deadline set'}
                </p>
              )}
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
            <div className="md:col-span-2" data-tour-pm-ct="assignee">
              <Label htmlFor="assignee_id" className="flex items-center gap-1.5">Assign To <InfoHint {...PM_HINTS.pmCtAssignee} /></Label>
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

          <div className="flex justify-end items-center gap-2" data-tour-pm-ct="submit">
            <InfoHint {...PM_HINTS.pmCtSubmit} />
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

