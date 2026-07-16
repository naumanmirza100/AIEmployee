import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Plus, X } from 'lucide-react';
import { companyApi } from '@/services/companyAuthService';
import { API_BASE_URL } from '@/config/apiConfig';
import { DatePicker } from '@/components/common/DatePicker';
import InfoHint from '../frontline/InfoHint';
import { PM_HINTS } from './pmTutorialSteps';

const ManualProjectCreation = ({ onProjectCreated }) => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    status: 'planning',
    priority: 'medium',
    project_type: 'web_app',
    industry_id: '',
    budget_min: '',
    budget_max: '',
    deadline: '',
    start_date: '',
  });

  const [industries, setIndustries] = useState([]);
  const [loadingIndustries, setLoadingIndustries] = useState(false);

  useEffect(() => {
    fetchIndustries();
  }, []);

  const fetchIndustries = async () => {
    try {
      setLoadingIndustries(true);
      const response = await fetch(`${API_BASE_URL}/industries/`);
      if (response.ok) {
        const data = await response.json();
        setIndustries(data.data || []);
      }
    } catch (error) {
      console.error('Error fetching industries:', error);
    } finally {
      setLoadingIndustries(false);
    }
  };

  const handleChange = (field, value) => {
    setFormData(prev => ({
      ...prev,
      [field]: value
    }));
  };

  // Today as a YYYY-MM-DD string, in the user's local timezone. Used both as
  // the `min` attr on the date inputs and as the lower bound in the submit
  // validation. Computed each submit so the form stays correct across midnight.
  const todayIso = () => {
    const d = new Date();
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!formData.name.trim()) {
      toast({
        title: 'Validation Error',
        description: 'Project name is required',
        variant: 'destructive',
      });
      return;
    }

    // Date validation — past dates and inverted ranges are nonsensical for a
    // project being created right now.
    const today = todayIso();
    if (formData.start_date && formData.start_date < today) {
      toast({
        title: 'Invalid start date',
        description: 'Start date cannot be in the past.',
        variant: 'destructive',
      });
      return;
    }
    if (formData.deadline && formData.deadline < today) {
      toast({
        title: 'Invalid deadline',
        description: 'Deadline cannot be in the past.',
        variant: 'destructive',
      });
      return;
    }
    if (formData.start_date && formData.deadline && formData.deadline < formData.start_date) {
      toast({
        title: 'Invalid date range',
        description: 'Deadline must be on or after the start date.',
        variant: 'destructive',
      });
      return;
    }

    try {
      setLoading(true);
      
      // Prepare data for API
      const payload = {
        name: formData.name,
        description: formData.description,
        status: formData.status,
        priority: formData.priority,
        project_type: formData.project_type,
      };

      // Add optional fields if provided
      if (formData.industry_id && formData.industry_id !== "none") payload.industry_id = parseInt(formData.industry_id);
      if (formData.budget_min) payload.budget_min = parseFloat(formData.budget_min);
      if (formData.budget_max) payload.budget_max = parseFloat(formData.budget_max);
      if (formData.deadline) payload.deadline = formData.deadline;
      if (formData.start_date) payload.start_date = formData.start_date;

      const response = await companyApi.post('/project-manager/projects/create/', payload);
      
      if (response.status === 'success') {
        toast({
          title: 'Success',
          description: 'Project created successfully',
        });
        
        // Reset form
        setFormData({
          name: '',
          description: '',
          status: 'planning',
          priority: 'medium',
          project_type: 'web_app',
          industry_id: '',
          budget_min: '',
          budget_max: '',
          deadline: '',
          start_date: '',
        });

        // Notify parent component
        if (onProjectCreated) {
          onProjectCreated();
        }
      } else {
        throw new Error(response.message || 'Failed to create project');
      }
    } catch (error) {
      console.error('Error creating project:', error);
      toast({
        title: 'Error',
        description: error.message || 'Failed to create project',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="border-white/10 bg-black/20 backdrop-blur-sm">
      <CardHeader>
        <CardTitle>Create Project Manually</CardTitle>
        <CardDescription>
          Create a new project by filling out the form below
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Project Name */}
            <div className="md:col-span-2" data-tour-pm-cp="name">
              <Label htmlFor="name" className="flex items-center gap-1.5">Project Name * <InfoHint {...PM_HINTS.pmCpName} /></Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => handleChange('name', e.target.value)}
                placeholder="Enter project name"
                required
              />
            </div>

            {/* Description */}
            <div className="md:col-span-2" data-tour-pm-cp="desc">
              <Label htmlFor="description" className="flex items-center gap-1.5">Description <InfoHint {...PM_HINTS.pmCpDesc} /></Label>
              <Textarea
                id="description"
                value={formData.description}
                onChange={(e) => handleChange('description', e.target.value)}
                placeholder="Enter project description"
                rows={4}
              />
            </div>

            {/* Status */}
            <div data-tour-pm-cp="status">
              <Label htmlFor="status" className="flex items-center gap-1.5">Status <InfoHint {...PM_HINTS.pmCpStatus} /></Label>
              <Select value={formData.status} onValueChange={(value) => handleChange('status', value)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="planning">Planning</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="in_progress">In Progress</SelectItem>
                  <SelectItem value="on_hold">On Hold</SelectItem>
                  <SelectItem value="review">Review</SelectItem>
                  <SelectItem value="completed">Completed</SelectItem>
                  <SelectItem value="cancelled">Cancelled</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Priority */}
            <div data-tour-pm-cp="priority">
              <Label htmlFor="priority" className="flex items-center gap-1.5">Priority <InfoHint {...PM_HINTS.pmCpPriority} /></Label>
              <Select value={formData.priority} onValueChange={(value) => handleChange('priority', value)}>
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

            {/* Project Type */}
            <div>
              <Label htmlFor="project_type">Project Type</Label>
              <Select value={formData.project_type} onValueChange={(value) => handleChange('project_type', value)}>
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

            {/* Industry */}
            <div data-tour-pm-cp="industry">
              <Label htmlFor="industry_id" className="flex items-center gap-1.5">Industry <InfoHint {...PM_HINTS.pmCpIndustry} /></Label>
              <Select 
                value={formData.industry_id || "none"} 
                onValueChange={(value) => handleChange('industry_id', value === "none" ? "" : value)}
                disabled={loadingIndustries}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select industry" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {industries.map(industry => (
                    <SelectItem key={industry.id} value={industry.id.toString()}>
                      {industry.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Budget Min */}
            <div data-tour-pm-cp="budget">
              <Label htmlFor="budget_min" className="flex items-center gap-1.5">Budget Min <InfoHint {...PM_HINTS.pmCpBudget} /></Label>
              <Input
                id="budget_min"
                type="number"
                step="0.01"
                value={formData.budget_min}
                onChange={(e) => handleChange('budget_min', e.target.value)}
                placeholder="0.00"
              />
            </div>

            {/* Budget Max */}
            <div>
              <Label htmlFor="budget_max">Budget Max</Label>
              <Input
                id="budget_max"
                type="number"
                step="0.01"
                value={formData.budget_max}
                onChange={(e) => handleChange('budget_max', e.target.value)}
                placeholder="0.00"
              />
            </div>

            {/* Start Date — popover calendar (drop-in replacement for native date input) */}
            <div>
              <Label htmlFor="start_date">Start Date</Label>
              <DatePicker
                id="start_date"
                value={formData.start_date}
                onChange={(v) => handleChange('start_date', v)}
                minDate={todayIso()}
                placeholder="Pick a start date"
              />
            </div>

            {/* Deadline (the project's end / due date — single field) */}
            <div data-tour-pm-cp="deadline">
              <Label htmlFor="deadline" className="flex items-center gap-1.5">Deadline <InfoHint {...PM_HINTS.pmCpDeadline} /></Label>
              <DatePicker
                id="deadline"
                value={formData.deadline}
                onChange={(v) => handleChange('deadline', v)}
                minDate={formData.start_date || todayIso()}
                placeholder="Pick a deadline"
              />
            </div>
          </div>

          <div className="flex justify-end items-center gap-2" data-tour-pm-cp="submit">
            <InfoHint {...PM_HINTS.pmCpSubmit} />
            <Button type="submit" disabled={loading}>
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <Plus className="h-4 w-4 mr-2" />
                  Create Project
                </>
              )}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
};

export default ManualProjectCreation;

