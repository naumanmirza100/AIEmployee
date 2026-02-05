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
    end_date: '',
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
      if (formData.end_date) payload.end_date = formData.end_date;

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
          end_date: '',
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
    <Card>
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
            <div className="md:col-span-2">
              <Label htmlFor="name">Project Name *</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => handleChange('name', e.target.value)}
                placeholder="Enter project name"
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
                placeholder="Enter project description"
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
            <div>
              <Label htmlFor="industry_id">Industry</Label>
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
            <div>
              <Label htmlFor="budget_min">Budget Min</Label>
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

            {/* Start Date */}
            <div>
              <Label htmlFor="start_date">Start Date</Label>
              <Input
                id="start_date"
                type="date"
                value={formData.start_date}
                onChange={(e) => handleChange('start_date', e.target.value)}
              />
            </div>

            {/* End Date */}
            <div>
              <Label htmlFor="end_date">End Date</Label>
              <Input
                id="end_date"
                type="date"
                value={formData.end_date}
                onChange={(e) => handleChange('end_date', e.target.value)}
              />
            </div>

            {/* Deadline */}
            <div className="md:col-span-2">
              <Label htmlFor="deadline">Deadline</Label>
              <Input
                id="deadline"
                type="date"
                value={formData.deadline}
                onChange={(e) => handleChange('deadline', e.target.value)}
              />
            </div>
          </div>

          <div className="flex justify-end gap-2">
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

