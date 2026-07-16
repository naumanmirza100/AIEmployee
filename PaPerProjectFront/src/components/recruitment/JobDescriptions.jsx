import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Plus, Edit, Trash2, Briefcase, CheckCircle, XCircle, Wand2, Settings, X, ArrowRight, ArrowDown, Copy, Check, Eye, MapPin, Building2, Clock, ExternalLink, Users, FileText, BrainCircuit, Download, ChevronDown, ChevronUp, Search, ChevronLeft, ChevronRight, Maximize2, Minimize2 } from 'lucide-react';
import { DatePicker } from '@/components/ui/date-picker';
import {
  getJobDescriptions,
  createJobDescription,
  updateJobDescription,
  deleteJobDescription,
  generateJobDescription,
  getInterviewSettings,
  getJobApplicationsByJob,
} from '@/services/recruitmentAgentService';

/** Convert a Date object to 'YYYY-MM-DD' using LOCAL date components — avoids
 *  timezone-shift bugs that occur with toLocaleDateString(). */
const toLocaleDateStr = (date) => {
  const d = date instanceof Date ? date : new Date(date);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
};

const JobDescriptions = ({ onUpdate, onGoToSettings }) => {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  // Full-screen toggle for the manual create modal.
  const [createFullScreen, setCreateFullScreen] = useState(false);
  // Full-screen toggle for the AI create modal (useful on its generated-form step).
  const [aiFullScreen, setAiFullScreen] = useState(false);
  // Auto-open the "Create Job with AI" modal the first time the page opens
  // this session. Using a lazy initializer avoids effect-timing issues.
  const [showCreateWithAiModal, setShowCreateWithAiModal] = useState(() => {
    if (typeof window !== 'undefined' && !sessionStorage.getItem('recruitment_ai_modal_shown')) {
      sessionStorage.setItem('recruitment_ai_modal_shown', '1');
      return true;
    }
    return false;
  });
  const [createWithAiStep, setCreateWithAiStep] = useState('prompt'); // 'prompt' | 'form'
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deletingJob, setDeletingJob] = useState(null);
  const [editingJob, setEditingJob] = useState(null);
  // Bulk delete
  const [selectedJobIds, setSelectedJobIds] = useState(new Set());
  const [showBulkDeleteModal, setShowBulkDeleteModal] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    location: '',
    department: '',
    type: 'Full-time',
    requirements: '',
    parse_keywords: true,
    is_active: true,
    application_open_date: '',
    application_close_date: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [aiPrompt, setAiPrompt] = useState('');
  const [generating, setGenerating] = useState(false);
  const [showSettingsBanner, setShowSettingsBanner] = useState(false);
  const [configuredJobIds, setConfiguredJobIds] = useState(new Set());
  // Id of a freshly created job whose "Setup" badge we pulse/point at until
  // the user opens its settings.
  const [highlightSetupJobId, setHighlightSetupJobId] = useState(null);
  const [copiedJobId, setCopiedJobId] = useState(null);
  const [viewingJob, setViewingJob] = useState(null);
  const [viewingApplicationsJob, setViewingApplicationsJob] = useState(null);
  const [applications, setApplications] = useState([]);
  const [applicationsLoading, setApplicationsLoading] = useState(false);
  const [expandedApp, setExpandedApp] = useState(null);

  // search / filter / pagination state
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 9;
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [fetching, setFetching] = useState(false); // subtle indicator for filter/search updates
  const isFirstFetch = useRef(true);
  const searchDebounceRef = useRef(null);

  const fetchJobs = useCallback(async (params = {}) => {
    try {
      if (isFirstFetch.current) {
        setLoading(true);
      } else {
        setFetching(true);
      }
      const response = await getJobDescriptions(params);
      if (response.status === 'success') {
        const jobList = response.data || [];
        setJobs(jobList);
        setTotal(response.total ?? jobList.length);
        setTotalPages(response.total_pages ?? 1);
        // Check which jobs have interview settings configured (non-blocking)
        if (jobList.length > 0) {
          Promise.allSettled(jobList.map((j) => getInterviewSettings(j.id))).then((results) => {
            const ids = new Set();
            results.forEach((r, idx) => {
              if (r.status === 'fulfilled' && r.value?.data?.schedule_from_date) {
                ids.add(jobList[idx].id);
              }
            });
            setConfiguredJobIds(ids);
            // If the freshly-created job is now configured, stop highlighting it.
            setHighlightSetupJobId((cur) => (cur != null && ids.has(cur) ? null : cur));
          });
        }
      }
    } catch (error) {
      console.error('Error fetching job descriptions:', error);
      toast({
        title: 'Error',
        description: 'Failed to load job descriptions',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
      setFetching(false);
      isFirstFetch.current = false;
    }
  }, [toast]);

  // Re-fetch whenever page / filters change; debounce search
  useEffect(() => {
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    searchDebounceRef.current = setTimeout(() => {
      fetchJobs({
        search,
        status: statusFilter,
        type: typeFilter,
        page,
        page_size: pageSize,
      });
    }, 350);
    return () => clearTimeout(searchDebounceRef.current);
  }, [search, statusFilter, typeFilter, page]);

  // Shared field validation for create & update. Returns true if valid,
  // otherwise shows a toast and returns false. On create, the open date may
  // not be in the past; on edit we allow an already-set past open date.
  const validateJobForm = ({ isCreate = false } = {}) => {
    if (!formData.title || !formData.description) {
      toast({ title: 'Validation Error', description: 'Title and description are required', variant: 'destructive' });
      return false;
    }
    if (!formData.application_open_date || !formData.application_close_date) {
      toast({ title: 'Validation Error', description: 'Applications open date and close date are required', variant: 'destructive' });
      return false;
    }
    if (isCreate) {
      const today = toLocaleDateStr(new Date());
      if (formData.application_open_date < today) {
        toast({ title: 'Validation Error', description: 'Applications open date cannot be in the past', variant: 'destructive' });
        return false;
      }
    }
    // Close date must be strictly after the open date.
    if (formData.application_close_date <= formData.application_open_date) {
      toast({ title: 'Validation Error', description: 'Applications close date must be after the open date', variant: 'destructive' });
      return false;
    }
    return true;
  };

  const handleCreate = async () => {
    if (!validateJobForm({ isCreate: true })) return;

    try {
      setSubmitting(true);
      const response = await createJobDescription(formData);
      if (response.status === 'success') {
        toast({
          title: 'Success',
          description: 'Job description created successfully',
        });
        setShowCreateModal(false);
        setShowCreateWithAiModal(false);
        setCreateWithAiStep('prompt');
        resetForm();
        refreshJobs();
        setShowSettingsBanner(true);
        // Highlight this new job's "Setup" badge with a pulse + arrow so the
        // user immediately sees where to configure its settings.
        const newJobId = response.data?.id ?? response.job_description?.id ?? null;
        if (newJobId != null) setHighlightSetupJobId(newJobId);
        if (onUpdate) onUpdate();
      }
    } catch (error) {
      console.error('Error creating job description:', error);
      toast({
        title: 'Error',
        description: error.message || 'Failed to create job description',
        variant: 'destructive',
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleEdit = (job) => {
    setEditingJob(job);
    setFormData({
      title: job.title,
      description: job.description,
      location: job.location || '',
      department: job.department || '',
      type: job.type || 'Full-time',
      requirements: job.requirements || '',
      parse_keywords: true,
      is_active: job.is_active !== false,
      application_open_date: job.application_open_date || '',
      application_close_date: job.application_close_date || '',
    });
    setShowEditModal(true);
  };

  const handleUpdate = async () => {
    if (!validateJobForm()) return;

    try {
      setSubmitting(true);
      const response = await updateJobDescription(editingJob.id, {
        ...formData,
        is_active: formData.is_active,
      });
      if (response.status === 'success') {
        toast({
          title: 'Success',
          description: 'Job description updated successfully',
        });
        setShowEditModal(false);
        setEditingJob(null);
        resetForm();
        refreshJobs();
        if (onUpdate) onUpdate();
      }
    } catch (error) {
      console.error('Error updating job description:', error);
      toast({
        title: 'Error',
        description: error.message || 'Failed to update job description',
        variant: 'destructive',
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteClick = (job) => {
    setDeletingJob(job);
    setShowDeleteModal(true);
  };

  const handleDeleteConfirm = async () => {
    if (!deletingJob) return;

    try {
      setSubmitting(true);
      const response = await deleteJobDescription(deletingJob.id);
      if (response.status === 'success') {
        toast({
          title: 'Success',
          description: 'Job description deleted successfully',
        });
        setShowDeleteModal(false);
        setDeletingJob(null);
        refreshJobs();
        if (onUpdate) onUpdate();
      }
    } catch (error) {
      console.error('Error deleting job description:', error);
      toast({
        title: 'Error',
        description: error.message || 'Failed to delete job description',
        variant: 'destructive',
      });
    } finally {
      setSubmitting(false);
    }
  };

  // ---- Bulk delete -------------------------------------------------------
  const toggleJobSelected = (jobId, checked) => {
    setSelectedJobIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(jobId);
      else next.delete(jobId);
      return next;
    });
  };

  const allJobsSelected = jobs.length > 0 && jobs.every((j) => selectedJobIds.has(j.id));

  const toggleSelectAllJobs = (checked) => {
    if (checked) setSelectedJobIds(new Set(jobs.map((j) => j.id)));
    else setSelectedJobIds(new Set());
  };

  const handleBulkDeleteConfirm = async () => {
    const ids = Array.from(selectedJobIds);
    if (ids.length === 0) return;
    try {
      setBulkDeleting(true);
      const results = await Promise.allSettled(ids.map((id) => deleteJobDescription(id)));
      const failed = results.filter(
        (r) => r.status === 'rejected' || r.value?.status !== 'success'
      ).length;
      const succeeded = ids.length - failed;

      if (succeeded > 0) {
        toast({
          title: 'Deleted',
          description: `${succeeded} job${succeeded > 1 ? 's' : ''} deleted${failed ? `, ${failed} failed` : ''}.`,
          variant: failed ? 'destructive' : undefined,
        });
      } else {
        toast({ title: 'Error', description: 'Failed to delete selected jobs', variant: 'destructive' });
      }

      setSelectedJobIds(new Set());
      setShowBulkDeleteModal(false);
      refreshJobs();
      if (onUpdate) onUpdate();
    } catch (error) {
      console.error('Bulk delete error:', error);
      toast({ title: 'Error', description: error?.message || 'Failed to delete selected jobs', variant: 'destructive' });
    } finally {
      setBulkDeleting(false);
    }
  };

  const resetForm = () => {
    setFormData({
      title: '',
      description: '',
      location: '',
      department: '',
      type: 'Full-time',
      requirements: '',
      parse_keywords: true,
      is_active: true,
    });
    setAiPrompt('');
  };

  const handleGenerateWithAi = async () => {
    const prompt = (aiPrompt || '').trim();
    if (!prompt) {
      toast({
        title: 'Validation',
        description: 'Enter a prompt to generate a job (e.g. role, skills, responsibilities).',
        variant: 'destructive',
      });
      return;
    }
    try {
      setGenerating(true);
      const response = await generateJobDescription(prompt);
      if (response.status === 'success' && response.data) {
        setFormData((prev) => ({
          ...prev,
          title: response.data.title ?? prev.title,
          description: response.data.description ?? prev.description,
          requirements: response.data.requirements ?? prev.requirements,
          location: response.data.location ?? prev.location,
          department: response.data.department ?? prev.department,
          type: response.data.type ?? prev.type,
        }));
        setCreateWithAiStep('form');
        toast({
          title: 'Generated',
          description: 'Review and edit below, then Save to create the job.',
        });
      }
    } catch (error) {
      console.error('Generate job error:', error);
      toast({
        title: 'Error',
        description: error.message || 'Failed to generate job description',
        variant: 'destructive',
      });
    } finally {
      setGenerating(false);
    }
  };

  const openCreateWithAi = () => {
    setAiPrompt('');
    setCreateWithAiStep('prompt');
    resetForm();
    setShowCreateWithAiModal(true);
  };

  const closeCreateWithAi = () => {
    setShowCreateWithAiModal(false);
    setCreateWithAiStep('prompt');
    setAiPrompt('');
    resetForm();
  };

  // Switch from the manual create modal to the AI modal.
  const switchToAiModal = () => {
    setShowCreateModal(false);
    setAiPrompt('');
    setCreateWithAiStep('prompt');
    resetForm();
    setShowCreateWithAiModal(true);
  };

  // Switch from the AI modal to the manual create modal.
  // Keeps any form data (e.g. AI-generated fields) so nothing is lost.
  const switchToManualModal = () => {
    setShowCreateWithAiModal(false);
    setShowCreateModal(true);
  };

  const handleViewApplications = async (job) => {
    setViewingApplicationsJob(job);
    setApplications([]);
    setExpandedApp(null);
    setApplicationsLoading(true);
    try {
      const res = await getJobApplicationsByJob(job.id);
      setApplications(res.data || []);
    } catch (e) {
      toast({ title: 'Error', description: 'Failed to load applications', variant: 'destructive' });
    } finally {
      setApplicationsLoading(false);
    }
  };

  const refreshJobs = () => fetchJobs({ search, status: statusFilter, type: typeFilter, page, page_size: pageSize });

  return (
    <div className="space-y-4 w-full max-w-full overflow-x-hidden">
      {showSettingsBanner && (
        <div
          className="flex items-start gap-3 rounded-xl px-4 py-3.5"
          style={{
            background: 'linear-gradient(90deg, rgba(167,139,250,0.10) 0%, rgba(96,165,250,0.07) 100%)',
            border: '1px solid rgba(167,139,250,0.30)',
          }}
        >
          <div className="shrink-0 mt-0.5 rounded-lg p-1.5" style={{ background: 'rgba(167,139,250,0.15)' }}>
            <Settings className="h-4 w-4 text-violet-400" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-white">Job created! Complete your Settings</p>
            <p className="text-xs text-white/60 mt-0.5">
              Configure email follow-ups, interview scheduling, and qualification thresholds in Settings to get the most out of the recruitment agent.
            </p>
            {onGoToSettings && (
              <button
                onClick={() => { setShowSettingsBanner(false); onGoToSettings(null); }}
                className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-violet-300 hover:text-violet-200 transition-colors"
              >
                Go to Settings <ArrowRight className="h-3 w-3" />
              </button>
            )}
          </div>
          <button
            onClick={() => setShowSettingsBanner(false)}
            className="shrink-0 text-white/30 hover:text-white/60 transition-colors mt-0.5"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      <div className="flex justify-between items-center flex-wrap gap-2">
        <div>
          <h2 className="text-2xl font-bold text-white">Job Descriptions</h2>
          <p className="text-sm text-white/60">
            Manage job descriptions for recruitment
          </p>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => setShowCreateModal(true)} variant="outline">
            <Plus className="h-4 w-4 mr-2" />
            Create Job Description
          </Button>
          <Button onClick={openCreateWithAi}>
            <Wand2 className="h-4 w-4 mr-2" />
            Create Job with AI
          </Button>
        </div>
      </div>

      {/* Bulk selection / delete bar */}
      {jobs.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/10 bg-black/20 px-3 py-2">
          <div className="flex items-center gap-2">
            <div className="relative inline-flex items-center justify-center">
              {selectedJobIds.size === 0 && (
                <span className="absolute left-1/2 -translate-x-1/2 -top-6 text-violet-400 animate-bounce pointer-events-none">
                  <ArrowDown className="h-4 w-4" />
                </span>
              )}
              <Checkbox
                checked={allJobsSelected ? true : selectedJobIds.size > 0 ? 'indeterminate' : false}
                onCheckedChange={(c) => toggleSelectAllJobs(!!c)}
                aria-label="Select all jobs"
              />
            </div>
            <span className="text-sm text-white/70">
              {selectedJobIds.size > 0
                ? `${selectedJobIds.size} selected`
                : 'Select all'}
            </span>
            {selectedJobIds.size === 0 && (
              <span className="text-xs text-violet-300/90">
                — tick jobs here to delete multiple at once
              </span>
            )}
          </div>
          {selectedJobIds.size > 0 && (
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="destructive"
                onClick={() => setShowBulkDeleteModal(true)}
              >
                <Trash2 className="h-4 w-4 mr-1" />
                Delete ({selectedJobIds.size})
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setSelectedJobIds(new Set())}>
                Clear
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Search + Filters */}
      <div className="flex flex-wrap gap-2 items-center">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/30 pointer-events-none" />
          <input
            type="text"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            placeholder="Search by title, location or department…"
            className="w-full pl-9 pr-10 py-2 text-sm rounded-lg bg-white/5 border border-white/10 text-white placeholder:text-white/30 focus:outline-none focus:border-violet-500/50 focus:ring-1 focus:ring-violet-500/30"
          />
          {fetching && (
            <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 animate-spin text-violet-400 pointer-events-none" />
          )}
        </div>

        <Select value={statusFilter || '_all'} onValueChange={(v) => { setStatusFilter(v === '_all' ? '' : v); setPage(1); }}>
          <SelectTrigger className="w-[130px] bg-white/5 border-white/10 text-white text-sm">
            <SelectValue placeholder="All Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="_all">All Status</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="inactive">Inactive</SelectItem>
          </SelectContent>
        </Select>

        <Select value={typeFilter || '_all'} onValueChange={(v) => { setTypeFilter(v === '_all' ? '' : v); setPage(1); }}>
          <SelectTrigger className="w-[140px] bg-white/5 border-white/10 text-white text-sm">
            <SelectValue placeholder="All Types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="_all">All Types</SelectItem>
            <SelectItem value="Full-time">Full-time</SelectItem>
            <SelectItem value="Part-time">Part-time</SelectItem>
            <SelectItem value="Contract">Contract</SelectItem>
            <SelectItem value="Internship">Internship</SelectItem>
          </SelectContent>
        </Select>

        {(search || statusFilter || typeFilter) && (
          <button
            onClick={() => { setSearch(''); setStatusFilter(''); setTypeFilter(''); setPage(1); }}
            className="inline-flex items-center justify-center h-9 w-9 rounded-lg border border-white/10 text-white/50 hover:text-white/80 hover:border-white/20 transition-colors"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}

        <span className="text-xs text-white/30 ml-1">{total} job{total !== 1 ? 's' : ''}</span>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-violet-400" />
        </div>
      ) : jobs.length === 0 ? (
        <Card className="border-white/10 bg-black/20 backdrop-blur-sm">
          <CardContent className="py-12 text-center">
            <Briefcase className="h-12 w-12 mx-auto text-white/40 mb-4" />
            {search || statusFilter || typeFilter ? (
              <>
                <p className="text-lg font-medium mb-2 text-white">No jobs match your filters</p>
                <p className="text-sm text-white/60 mb-4">Try adjusting your search or filters</p>
                <Button variant="outline" onClick={() => { setSearch(''); setStatusFilter(''); setTypeFilter(''); setPage(1); }}>
                  Clear filters
                </Button>
              </>
            ) : (
              <>
                <p className="text-lg font-medium mb-2 text-white">No job descriptions yet</p>
                <p className="text-sm text-white/60 mb-4">
                  Create your first job description to start recruiting
                </p>
                <div className="flex gap-2 justify-center">
                  <Button onClick={() => setShowCreateModal(true)} variant="outline">
                    <Plus className="h-4 w-4 mr-2" />
                    Create Job Description
                  </Button>
                  <Button onClick={openCreateWithAi}>
                    <Wand2 className="h-4 w-4 mr-2" />
                    Create Job with AI
                  </Button>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 w-full max-w-full">
          {jobs.map((job) => (
            <Card
              key={job.id}
              className={`border-white/10 bg-black/20 backdrop-blur-sm ${selectedJobIds.has(job.id) ? 'ring-1 ring-primary/60' : ''}`}
            >
              <CardHeader>
                <div className="flex justify-between items-start">
                  <div className="flex flex-1 items-start gap-2 min-w-0">
                    <Checkbox
                      checked={selectedJobIds.has(job.id)}
                      onCheckedChange={(c) => toggleJobSelected(job.id, !!c)}
                      onClick={(e) => e.stopPropagation()}
                      aria-label={`Select ${job.title}`}
                      className="mt-1 shrink-0"
                    />
                    <div className="min-w-0">
                      <CardTitle className="text-lg">{job.title}</CardTitle>
                      <CardDescription className="mt-1">
                        {job.location && `${job.location} • `}
                        {job.type}
                      </CardDescription>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap justify-end">
                    {onGoToSettings && (
                      configuredJobIds.has(job.id) ? (
                        <button
                          onClick={(e) => { e.stopPropagation(); onGoToSettings(job.id); }}
                          title="Interview settings configured — click to view"
                          className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border transition-all duration-150 cursor-pointer"
                          style={{ background: 'rgba(52,211,153,0.12)', borderColor: 'rgba(52,211,153,0.35)', color: '#34d399' }}
                          onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(52,211,153,0.24)'; }}
                          onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(52,211,153,0.12)'; }}
                        >
                          <CheckCircle className="h-3 w-3" />
                          Configured
                        </button>
                      ) : (
                        <span className="relative inline-flex">
                          {highlightSetupJobId === job.id && (
                            <>
                              {/* pulsing ring around the Setup badge */}
                              <span className="absolute inset-0 rounded-full animate-ping pointer-events-none" style={{ background: 'rgba(251,191,36,0.45)' }} />
                              {/* bouncing arrow pointing down at the badge */}
                              <span className="absolute left-1/2 -translate-x-1/2 -top-6 text-amber-400 animate-bounce pointer-events-none">
                                <ArrowDown className="h-4 w-4" />
                              </span>
                            </>
                          )}
                          <button
                            onClick={(e) => { e.stopPropagation(); setHighlightSetupJobId(null); onGoToSettings(job.id); }}
                            title="Complete email, interview & qualification settings"
                            className="relative inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border transition-all duration-150 cursor-pointer"
                            style={highlightSetupJobId === job.id
                              ? { background: 'rgba(251,191,36,0.28)', borderColor: '#fbbf24', color: '#fbbf24', boxShadow: '0 0 10px 0 rgba(251,191,36,0.6)' }
                              : { background: 'rgba(251,191,36,0.12)', borderColor: 'rgba(251,191,36,0.35)', color: '#fbbf24' }}
                            onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(251,191,36,0.24)'; }}
                            onMouseLeave={(e) => { e.currentTarget.style.background = highlightSetupJobId === job.id ? 'rgba(251,191,36,0.28)' : 'rgba(251,191,36,0.12)'; }}
                          >
                            <Settings className="h-3 w-3" />
                            Setup
                          </button>
                        </span>
                      )
                    )}
                    {job.is_active ? (
                      <Badge className="bg-green-500">
                        <CheckCircle className="h-3 w-3 mr-1" />
                        Active
                      </Badge>
                    ) : (
                      <Badge variant="outline">
                        <XCircle className="h-3 w-3 mr-1" />
                        Inactive
                      </Badge>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground line-clamp-3 mb-4">
                  {job.description}
                </p>
                <div className="flex gap-2 flex-wrap">
                  <Button
                    variant="outline"
                    size="sm"
                    title="View job details"
                    onClick={() => setViewingJob(job)}
                  >
                    <Eye className="h-3 w-3" />
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleViewApplications(job)}
                    className="flex-1 text-blue-400 border-blue-400/30 hover:bg-blue-400/10"
                  >
                    <Users className="h-3 w-3 mr-1" />
                    Applications
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleEdit(job)}
                  >
                    <Edit className="h-3 w-3" />
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    title="Copy application link"
                    onClick={() => {
                      const url = `${window.location.origin}/jobs/apply/${job.id}`;
                      navigator.clipboard.writeText(url).then(() => {
                        setCopiedJobId(job.id);
                        setTimeout(() => setCopiedJobId(null), 2000);
                      });
                    }}
                    className={copiedJobId === job.id ? 'text-green-500 border-green-500/40' : ''}
                  >
                    {copiedJobId === job.id ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleDeleteClick(job)}
                    className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-950"
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Pagination */}
      {!loading && totalPages > 1 && (
        <div className="flex items-center justify-between pt-2">
          <p className="text-xs text-white/40">
            Page {page} of {totalPages} &nbsp;·&nbsp; {total} total
          </p>
          <div className="flex items-center gap-1">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="inline-flex items-center justify-center h-8 w-8 rounded-lg border border-white/10 text-white/50 hover:text-white/80 hover:border-white/20 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1)
              .filter((n) => n === 1 || n === totalPages || Math.abs(n - page) <= 1)
              .reduce((acc, n, idx, arr) => {
                if (idx > 0 && n - arr[idx - 1] > 1) acc.push('…');
                acc.push(n);
                return acc;
              }, [])
              .map((item, idx) =>
                item === '…' ? (
                  <span key={`e${idx}`} className="text-white/30 text-xs px-1">…</span>
                ) : (
                  <button
                    key={item}
                    onClick={() => setPage(item)}
                    className={`inline-flex items-center justify-center h-8 w-8 rounded-lg text-xs font-medium border transition-colors ${
                      item === page
                        ? 'border-violet-500/60 bg-violet-500/15 text-violet-300'
                        : 'border-white/10 text-white/50 hover:text-white/80 hover:border-white/20'
                    }`}
                  >
                    {item}
                  </button>
                )
              )}
            <button
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              className="inline-flex items-center justify-center h-8 w-8 rounded-lg border border-white/10 text-white/50 hover:text-white/80 hover:border-white/20 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* View Applications Modal */}
      {viewingApplicationsJob && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.80)', backdropFilter: 'blur(4px)' }}
          onClick={() => setViewingApplicationsJob(null)}
        >
          <div
            className="relative w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-2xl"
            style={{ background: 'linear-gradient(135deg, #0d0d1a 0%, #0a1020 100%)', border: '1px solid rgba(96,165,250,0.25)' }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="sticky top-0 z-10 flex items-center justify-between gap-3 px-6 pt-6 pb-4"
              style={{ background: 'linear-gradient(135deg, #0d0d1a 0%, #0a1020 100%)', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
              <div className="flex items-center gap-3">
                <div className="shrink-0 rounded-xl p-2.5" style={{ background: 'rgba(96,165,250,0.15)' }}>
                  <Users className="h-5 w-5 text-blue-400" />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-white">Applications</h2>
                  <p className="text-xs text-white/50">{viewingApplicationsJob.title}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs px-2.5 py-1 rounded-full font-medium text-blue-300"
                  style={{ background: 'rgba(96,165,250,0.12)', border: '1px solid rgba(96,165,250,0.25)' }}>
                  {applications.length} total
                </span>
                <button onClick={() => setViewingApplicationsJob(null)} className="text-white/30 hover:text-white/70 transition-colors">
                  <X className="h-5 w-5" />
                </button>
              </div>
            </div>

            {/* Body */}
            <div className="px-6 py-5 space-y-3">
              {applicationsLoading ? (
                <div className="flex justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin text-blue-400" />
                </div>
              ) : applications.length === 0 ? (
                <div className="flex flex-col items-center py-14 gap-3">
                  <Users className="h-12 w-12 text-white/20" />
                  <p className="text-white/50 text-sm">No applications yet for this job</p>
                </div>
              ) : (
                applications.map((app) => (
                  <div key={app.id} className="rounded-xl overflow-hidden"
                    style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)' }}>
                    {/* Application Row */}
                    <div className="flex items-center gap-3 px-4 py-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-semibold text-white">
                            {app.first_name} {app.last_name}
                          </span>
                          {app.ai_analysed ? (
                            <span className="text-xs px-2 py-0.5 rounded-full font-medium text-emerald-300"
                              style={{ background: 'rgba(52,211,153,0.12)', border: '1px solid rgba(52,211,153,0.25)' }}>
                              <BrainCircuit className="h-3 w-3 inline mr-1" />AI Analysed
                            </span>
                          ) : (
                            <span className="text-xs px-2 py-0.5 rounded-full font-medium text-white/40"
                              style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}>
                              Pending AI
                            </span>
                          )}
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium
                            ${app.status === 'ACCEPTED' ? 'text-emerald-300 bg-emerald-400/10 border border-emerald-400/25'
                              : app.status === 'REJECTED' ? 'text-red-300 bg-red-400/10 border border-red-400/25'
                              : app.status === 'INTERVIEW' ? 'text-violet-300 bg-violet-400/10 border border-violet-400/25'
                              : 'text-white/40 bg-white/5 border border-white/10'}`}>
                            {app.status || 'PENDING'}
                          </span>
                        </div>
                        <div className="flex items-center gap-3 mt-0.5">
                          <span className="text-xs text-white/40">{app.email}</span>
                          {app.phone && <span className="text-xs text-white/30">{app.phone}</span>}
                          {app.applied_at && (
                            <span className="text-xs text-white/30">
                              {new Date(app.applied_at).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {app.cv_url && (
                          <a href={app.cv_url} target="_blank" rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg font-medium text-blue-300 transition-all"
                            style={{ background: 'rgba(96,165,250,0.10)', border: '1px solid rgba(96,165,250,0.20)' }}>
                            <Download className="h-3 w-3" />CV
                          </a>
                        )}
                        {app.ai_analysed && app.cv_record_id && (
                          <button
                            onClick={() => { setViewingApplicationsJob(null); navigate(`/recruitment/candidates/${app.cv_record_id}`); }}
                            className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg font-medium text-violet-300 transition-all"
                            style={{ background: 'rgba(167,139,250,0.10)', border: '1px solid rgba(167,139,250,0.20)' }}
                          >
                            <FileText className="h-3 w-3" />Report
                          </button>
                        )}
                        <button
                          onClick={() => setExpandedApp(expandedApp === app.id ? null : app.id)}
                          className="text-white/30 hover:text-white/60 transition-colors p-1"
                        >
                          {expandedApp === app.id ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                        </button>
                      </div>
                    </div>

                    {/* Expanded details */}
                    {expandedApp === app.id && (
                      <div className="px-4 pb-4 pt-1 border-t border-white/5 grid grid-cols-2 gap-3">
                        {app.current_location && (
                          <div className="rounded-lg px-3 py-2" style={{ background: 'rgba(255,255,255,0.03)' }}>
                            <p className="text-xs text-white/30 mb-0.5">Location</p>
                            <p className="text-sm text-white/70">{app.current_location}</p>
                          </div>
                        )}
                        {app.salary_expectation && (
                          <div className="rounded-lg px-3 py-2" style={{ background: 'rgba(255,255,255,0.03)' }}>
                            <p className="text-xs text-white/30 mb-0.5">Salary Expectation</p>
                            <p className="text-sm text-white/70">{app.salary_expectation}</p>
                          </div>
                        )}
                        {app.education && (
                          <div className="rounded-lg px-3 py-2" style={{ background: 'rgba(255,255,255,0.03)' }}>
                            <p className="text-xs text-white/30 mb-0.5">Education</p>
                            <p className="text-sm text-white/70">{app.education}</p>
                          </div>
                        )}
                        {app.previous_company && (
                          <div className="rounded-lg px-3 py-2" style={{ background: 'rgba(255,255,255,0.03)' }}>
                            <p className="text-xs text-white/30 mb-0.5">Previous Company</p>
                            <p className="text-sm text-white/70">{app.previous_company}</p>
                          </div>
                        )}
                        {app.linkedin_url && (
                          <div className="rounded-lg px-3 py-2 col-span-2" style={{ background: 'rgba(255,255,255,0.03)' }}>
                            <p className="text-xs text-white/30 mb-0.5">LinkedIn</p>
                            <a href={app.linkedin_url} target="_blank" rel="noopener noreferrer"
                              className="text-sm text-blue-400 hover:underline truncate block">{app.linkedin_url}</a>
                          </div>
                        )}
                        {app.cover_letter && (
                          <div className="rounded-lg px-3 py-2 col-span-2" style={{ background: 'rgba(255,255,255,0.03)' }}>
                            <p className="text-xs text-white/30 mb-0.5">Cover Letter</p>
                            <p className="text-sm text-white/60 leading-relaxed line-clamp-4">{app.cover_letter}</p>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* View Job Modal */}
      {viewingJob && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)' }}
          onClick={() => setViewingJob(null)}
        >
          <div
            className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl"
            style={{ background: 'linear-gradient(135deg, #0d0d1a 0%, #0a1020 100%)', border: '1px solid rgba(167,139,250,0.2)' }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="sticky top-0 z-10 flex items-start justify-between gap-3 px-6 pt-6 pb-4" style={{ background: 'linear-gradient(135deg, #0d0d1a 0%, #0a1020 100%)', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
              <div className="flex items-start gap-3 flex-1 min-w-0">
                <div className="shrink-0 rounded-xl p-2.5 mt-0.5" style={{ background: 'rgba(167,139,250,0.15)' }}>
                  <Briefcase className="h-5 w-5 text-violet-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <h2 className="text-lg font-bold text-white leading-tight">{viewingJob.title}</h2>
                  <div className="flex flex-wrap gap-3 mt-1.5">
                    {viewingJob.location && (
                      <span className="flex items-center gap-1 text-xs text-white/50"><MapPin className="h-3 w-3" />{viewingJob.location}</span>
                    )}
                    {viewingJob.type && (
                      <span className="flex items-center gap-1 text-xs text-white/50"><Clock className="h-3 w-3" />{viewingJob.type}</span>
                    )}
                    {viewingJob.department && (
                      <span className="flex items-center gap-1 text-xs text-white/50"><Building2 className="h-3 w-3" />{viewingJob.department}</span>
                    )}
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${viewingJob.is_active ? 'text-emerald-400' : 'text-white/40'}`} style={{ background: viewingJob.is_active ? 'rgba(52,211,153,0.12)' : 'rgba(255,255,255,0.06)', border: `1px solid ${viewingJob.is_active ? 'rgba(52,211,153,0.25)' : 'rgba(255,255,255,0.1)'}` }}>
                      {viewingJob.is_active ? '● Active' : '○ Inactive'}
                    </span>
                  </div>
                </div>
              </div>
              <button onClick={() => setViewingJob(null)} className="shrink-0 text-white/30 hover:text-white/70 transition-colors mt-1">
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Body */}
            <div className="px-6 py-5 space-y-5">
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: 'Applications Open', value: viewingJob.application_open_date },
                  { label: 'Applications Close', value: viewingJob.application_close_date },
                ].map(({ label, value }) => (
                  <div key={label} className="rounded-lg px-4 py-3" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)' }}>
                    <p className="text-xs text-white/40 mb-1">{label}</p>
                    <p className="text-sm font-semibold text-white">
                      {value ? new Date(value + 'T00:00:00').toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'}
                    </p>
                  </div>
                ))}
              </div>
              {viewingJob.description && (
                <div>
                  <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">Description</p>
                  <p className="text-sm text-white/70 leading-relaxed whitespace-pre-line">{viewingJob.description}</p>
                </div>
              )}
              {viewingJob.requirements && (
                <div>
                  <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">Requirements</p>
                  <p className="text-sm text-white/70 leading-relaxed whitespace-pre-line">{viewingJob.requirements}</p>
                </div>
              )}
            </div>

            {/* Footer actions */}
            <div className="flex items-center justify-between gap-3 px-6 pb-6 pt-2" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
              <button
                onClick={() => {
                  const url = `${window.location.origin}/jobs/apply/${viewingJob.id}`;
                  navigator.clipboard.writeText(url).then(() => {
                    setCopiedJobId(viewingJob.id);
                    setTimeout(() => setCopiedJobId(null), 2000);
                  });
                }}
                className="inline-flex items-center gap-2 text-xs px-3 py-2 rounded-lg border transition-all"
                style={{ background: 'rgba(255,255,255,0.04)', borderColor: 'rgba(255,255,255,0.1)', color: 'rgba(255,255,255,0.6)' }}
              >
                {copiedJobId === viewingJob.id ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                {copiedJobId === viewingJob.id ? 'Link Copied!' : 'Copy Application Link'}
              </button>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => { setViewingJob(null); handleEdit(viewingJob); }}>
                  <Edit className="h-3.5 w-3.5 mr-1.5" />Edit
                </Button>
                <a
                  href={`${window.location.origin}/jobs/apply/${viewingJob.id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs px-3 py-2 rounded-lg font-medium text-white transition-all"
                  style={{ background: 'linear-gradient(90deg, #7c3aed 0%, #a259ff 100%)' }}
                >
                  <ExternalLink className="h-3.5 w-3.5" />View Form
                </a>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Create Modal (manual) – reset form when closed by X or overlay too */}
      <Dialog open={showCreateModal} onOpenChange={(open) => { setShowCreateModal(open); if (!open) { resetForm(); setCreateFullScreen(false); } }}>
        <DialogContent className={createFullScreen
          ? "w-screen h-[100dvh] max-w-none max-h-[100dvh] rounded-none overflow-y-auto"
          : "max-w-2xl max-h-[90vh] overflow-y-auto"}>
          {/* Full-screen toggle, sitting right beside the dialog's close (X) button */}
          <button
            type="button"
            onClick={() => setCreateFullScreen((v) => !v)}
            title={createFullScreen ? 'Exit full screen' : 'Full screen'}
            aria-label={createFullScreen ? 'Exit full screen' : 'Full screen'}
            className="absolute right-14 top-4 z-10 inline-flex h-8 w-8 items-center justify-center rounded-md border border-white/25 text-muted-foreground transition-colors hover:bg-white/10 hover:text-white"
          >
            {createFullScreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </button>
          <DialogHeader>
            <div className="flex items-start justify-between gap-3 pr-24">
              <div>
                <DialogTitle>Create Job Description</DialogTitle>
                <DialogDescription>
                  Fill in the details below and save.
                </DialogDescription>
              </div>
              <button
                type="button"
                onClick={switchToAiModal}
                className="shrink-0 inline-flex items-center gap-1.5 rounded-md border border-violet-500/40 bg-violet-500/10 px-3 py-1.5 text-sm font-medium text-violet-300 transition-colors hover:bg-violet-500/20"
              >
                <Wand2 className="h-4 w-4" />
                Create with AI
              </button>
            </div>
          </DialogHeader>
          <JobForm
            formData={formData}
            setFormData={setFormData}
            onSubmit={handleCreate}
            submitting={submitting}
            onCancel={() => { setShowCreateModal(false); resetForm(); }}
          />
        </DialogContent>
      </Dialog>

      {/* Create Job with AI Modal: step 1 = prompt, step 2 = editable form */}
      <Dialog open={showCreateWithAiModal} onOpenChange={(open) => { if (!open) { closeCreateWithAi(); setAiFullScreen(false); } }}>
        <DialogContent className={(aiFullScreen && createWithAiStep === 'form')
          ? "w-screen h-[100dvh] max-w-none max-h-[100dvh] rounded-none overflow-y-auto"
          : "max-w-2xl max-h-[90vh] overflow-y-auto"}>
          {/* Full-screen toggle — only useful on the generated-form step */}
          {createWithAiStep === 'form' && (
            <button
              type="button"
              onClick={() => setAiFullScreen((v) => !v)}
              title={aiFullScreen ? 'Exit full screen' : 'Full screen'}
              aria-label={aiFullScreen ? 'Exit full screen' : 'Full screen'}
              className="absolute right-14 top-4 z-10 inline-flex h-8 w-8 items-center justify-center rounded-md border border-white/25 text-muted-foreground transition-colors hover:bg-white/10 hover:text-white"
            >
              {aiFullScreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            </button>
          )}
          <DialogHeader>
            <div className="flex items-start justify-between gap-3 pr-6">
              <div>
                <DialogTitle>Create Job with AI</DialogTitle>
                <DialogDescription>
                  {createWithAiStep === 'prompt'
                    ? 'Write a prompt to generate your job description (e.g. role, skills, responsibilities).'
                    : 'Review and edit the generated job, then Save to create it.'}
                </DialogDescription>
              </div>
              <button
                type="button"
                onClick={switchToManualModal}
                className={`shrink-0 inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/40 px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted ${createWithAiStep === 'form' ? 'mr-20' : 'mr-10'}`}
              >
                <FileText className="h-4 w-4" />
                Create manually
              </button>
            </div>
          </DialogHeader>

          {createWithAiStep === 'prompt' ? (
            <div className="space-y-4">
              <Textarea
                value={aiPrompt}
                onChange={(e) => setAiPrompt(e.target.value)}
                placeholder="e.g. MERN Stack Developer, 5+ years, MongoDB, Express, React, Node.js, RESTful APIs, remote..."
                className="min-h-[120px]"
                disabled={generating}
              />
              <DialogFooter>
                <Button variant="outline" onClick={closeCreateWithAi} disabled={generating}>
                  Cancel
                </Button>
                <Button onClick={handleGenerateWithAi} disabled={generating}>
                  {generating ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Creating job description...
                    </>
                  ) : (
                    <>
                      <Wand2 className="h-4 w-4 mr-2" />
                      Generate job description
                    </>
                  )}
                </Button>
              </DialogFooter>
            </div>
          ) : (
            <>
              <JobForm
                formData={formData}
                setFormData={setFormData}
                onSubmit={handleCreate}
                submitting={submitting}
                onCancel={closeCreateWithAi}
              />
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* Edit Modal – reset form and editingJob when closed by X, overlay, or Cancel */}
      <Dialog open={showEditModal} onOpenChange={(open) => { setShowEditModal(open); if (!open) { setEditingJob(null); resetForm(); } }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Edit Job Description</DialogTitle>
          </DialogHeader>
          <JobForm
            formData={formData}
            setFormData={setFormData}
            onSubmit={handleUpdate}
            submitting={submitting}
            onCancel={() => {
              setShowEditModal(false);
              setEditingJob(null);
              resetForm();
            }}
          />
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Modal */}
      <Dialog open={showDeleteModal} onOpenChange={setShowDeleteModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Job Description</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete "{deletingJob?.title}"? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setShowDeleteModal(false);
                setDeletingJob(null);
              }}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteConfirm}
              disabled={submitting}
            >
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Deleting...
                </>
              ) : (
                <>
                  <Trash2 className="h-4 w-4 mr-2" />
                  Delete
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Bulk delete confirmation */}
      <Dialog open={showBulkDeleteModal} onOpenChange={setShowBulkDeleteModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete {selectedJobIds.size} job{selectedJobIds.size > 1 ? 's' : ''}?</DialogTitle>
            <DialogDescription>
              This will permanently delete the selected job description{selectedJobIds.size > 1 ? 's' : ''}. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowBulkDeleteModal(false)} disabled={bulkDeleting}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleBulkDeleteConfirm} disabled={bulkDeleting}>
              {bulkDeleting ? (
                <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Deleting...</>
              ) : (
                <><Trash2 className="h-4 w-4 mr-2" />Delete {selectedJobIds.size}</>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

const JobForm = ({ formData, setFormData, onSubmit, submitting, onCancel }) => {
  const [durationDays, setDurationDays] = useState('');

  // Quick-set: open = today, close = today + N days.
  const applyDaysRange = (daysValue) => {
    const days = parseInt(daysValue, 10);
    if (!days || days < 1) return;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const closeDate = new Date(today.getTime() + days * 86400000);
    setFormData((prev) => ({
      ...prev,
      application_open_date: toLocaleDateStr(today),
      application_close_date: toLocaleDateStr(closeDate),
    }));
  };

  return (
    <div className="space-y-4 w-full max-w-3xl mx-auto">
      <div className="space-y-2">
        <Label htmlFor="title">Title *</Label>
        <Input
          id="title"
          value={formData.title}
          onChange={(e) => setFormData({ ...formData, title: e.target.value })}
          placeholder="e.g., Senior Software Engineer"
          required
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="location">Location</Label>
          <Input
            id="location"
            value={formData.location}
            onChange={(e) => setFormData({ ...formData, location: e.target.value })}
            placeholder="e.g., New York, NY"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="department">Department</Label>
          <Input
            id="department"
            value={formData.department}
            onChange={(e) => setFormData({ ...formData, department: e.target.value })}
            placeholder="e.g., Engineering"
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="type">Job Type</Label>
        <Select value={formData.type} onValueChange={(value) => setFormData({ ...formData, type: value })}>
          <SelectTrigger className="border-white/20">
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

      <div className="flex items-center justify-between rounded-lg border p-4">
        <div className="space-y-0.5">
          <Label htmlFor="is_active">Status</Label>
          <p className="text-sm text-muted-foreground">Active jobs are visible for CV matching and recruitment</p>
        </div>
        <Switch
          id="is_active"
          checked={formData.is_active !== false}
          onCheckedChange={(checked) => setFormData({ ...formData, is_active: checked })}
        />
      </div>

      {/* Quick-set: enter number of days → open = today, close = today + N days.
          Manual date pickers below still work independently. */}
      <div className="rounded-lg border border-white/15 bg-white/[0.03] p-3">
        <Label htmlFor="durationDays" className="text-sm">
          Quick set — open today for how many days?
        </Label>
        <div className="mt-2 flex items-center gap-2">
          <Input
            id="durationDays"
            type="number"
            min="1"
            value={durationDays}
            onChange={(e) => setDurationDays(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); applyDaysRange(durationDays); } }}
            placeholder="e.g. 30"
            className="w-28"
          />
          <Button type="button" variant="secondary" onClick={() => applyDaysRange(durationDays)}>
            Set dates
          </Button>
          <span className="text-xs text-muted-foreground">Sets open = today, close = today + days.</span>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label>Applications Open Date <span className="text-red-500">*</span></Label>
          <DatePicker
            date={formData.application_open_date ? new Date(formData.application_open_date + 'T00:00:00') : null}
            setDate={(date) => setFormData({
              ...formData,
              application_open_date: date ? toLocaleDateStr(date) : '',
            })}
            placeholder="Select open date"
            // Open date can't be in the past.
            fromDate={new Date(new Date().setHours(0, 0, 0, 0))}
          />
        </div>
        <div className="space-y-2">
          <Label>Applications Close Date <span className="text-red-500">*</span></Label>
          <DatePicker
            date={formData.application_close_date ? new Date(formData.application_close_date + 'T00:00:00') : null}
            setDate={(date) => setFormData({
              ...formData,
              application_close_date: date ? toLocaleDateStr(date) : '',
            })}
            placeholder="Select close date"
            // Disable any day on or before the open date — close must be after open.
            fromDate={formData.application_open_date
              ? new Date(new Date(formData.application_open_date + 'T00:00:00').getTime() + 86400000)
              : undefined}
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="description">Description *</Label>
        <Textarea
          id="description"
          value={formData.description}
          onChange={(e) => setFormData({ ...formData, description: e.target.value })}
          placeholder="Enter job description..."
          className="min-h-[150px]"
          required
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="requirements">Requirements</Label>
        <Textarea
          id="requirements"
          value={formData.requirements}
          onChange={(e) => setFormData({ ...formData, requirements: e.target.value })}
          placeholder="Enter job requirements..."
          className="min-h-[100px]"
        />
      </div>

      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
        <Button onClick={onSubmit} disabled={submitting}>
          {submitting ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Saving...
            </>
          ) : (
            'Save'
          )}
        </Button>
      </div>
    </div>
  );
};

export default JobDescriptions;


