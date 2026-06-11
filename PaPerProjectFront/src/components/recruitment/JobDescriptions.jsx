import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Plus, Edit, Trash2, Briefcase, CheckCircle, XCircle, Wand2, Settings, X, ArrowRight, Copy, Check, Eye, MapPin, Building2, Clock, ExternalLink } from 'lucide-react';
import { DatePicker } from '@/components/ui/date-picker';
import {
  getJobDescriptions,
  createJobDescription,
  updateJobDescription,
  deleteJobDescription,
  generateJobDescription,
  getInterviewSettings,
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
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showCreateWithAiModal, setShowCreateWithAiModal] = useState(false);
  const [createWithAiStep, setCreateWithAiStep] = useState('prompt'); // 'prompt' | 'form'
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deletingJob, setDeletingJob] = useState(null);
  const [editingJob, setEditingJob] = useState(null);
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
  const [copiedJobId, setCopiedJobId] = useState(null);
  const [viewingJob, setViewingJob] = useState(null);

  useEffect(() => {
    fetchJobs();
  }, []);

  const fetchJobs = async () => {
    try {
      setLoading(true);
      const response = await getJobDescriptions();
      if (response.status === 'success') {
        const jobList = response.data || [];
        setJobs(jobList);
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
    }
  };

  const handleCreate = async () => {
    if (!formData.title || !formData.description) {
      toast({ title: 'Validation Error', description: 'Title and description are required', variant: 'destructive' });
      return;
    }
    if (!formData.application_open_date || !formData.application_close_date) {
      toast({ title: 'Validation Error', description: 'Applications open date and close date are required', variant: 'destructive' });
      return;
    }

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
        fetchJobs();
        setShowSettingsBanner(true);
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
    if (!formData.title || !formData.description) {
      toast({ title: 'Validation Error', description: 'Title and description are required', variant: 'destructive' });
      return;
    }
    if (!formData.application_open_date || !formData.application_close_date) {
      toast({ title: 'Validation Error', description: 'Applications open date and close date are required', variant: 'destructive' });
      return;
    }

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
        fetchJobs();
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
        fetchJobs();
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

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    );
  }

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

      {jobs.length === 0 ? (
        <Card className="border-white/10 bg-black/20 backdrop-blur-sm">
          <CardContent className="py-12 text-center">
            <Briefcase className="h-12 w-12 mx-auto text-white/40 mb-4" />
            <p className="text-lg font-medium mb-2 text-white">No job descriptions yet</p>
            <p className="text-sm text-white/60 mb-4">
              Create your first job description to start recruiting
            </p>
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
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 w-full max-w-full">
          {jobs.map((job) => (
            <Card key={job.id} className="border-white/10 bg-black/20 backdrop-blur-sm">
              <CardHeader>
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <CardTitle className="text-lg">{job.title}</CardTitle>
                    <CardDescription className="mt-1">
                      {job.location && `${job.location} • `}
                      {job.type}
                    </CardDescription>
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
                        <button
                          onClick={(e) => { e.stopPropagation(); onGoToSettings(job.id); }}
                          title="Complete email, interview & qualification settings"
                          className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border transition-all duration-150 cursor-pointer"
                          style={{ background: 'rgba(251,191,36,0.12)', borderColor: 'rgba(251,191,36,0.35)', color: '#fbbf24' }}
                          onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(251,191,36,0.24)'; }}
                          onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(251,191,36,0.12)'; }}
                        >
                          <Settings className="h-3 w-3" />
                          Setup
                        </button>
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
                <div className="flex gap-2">
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
                    onClick={() => handleEdit(job)}
                    className="flex-1"
                  >
                    <Edit className="h-3 w-3 mr-1" />
                    Edit
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
      <Dialog open={showCreateModal} onOpenChange={(open) => { setShowCreateModal(open); if (!open) resetForm(); }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Create Job Description</DialogTitle>
            <DialogDescription>
              Fill in the details below and save.
            </DialogDescription>
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
      <Dialog open={showCreateWithAiModal} onOpenChange={(open) => { if (!open) closeCreateWithAi(); }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Create Job with AI</DialogTitle>
            <DialogDescription>
              {createWithAiStep === 'prompt'
                ? 'Write a prompt to generate your job description (e.g. role, skills, responsibilities).'
                : 'Review and edit the generated job, then Save to create it.'}
            </DialogDescription>
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
    </div>
  );
};

const JobForm = ({ formData, setFormData, onSubmit, submitting, onCancel }) => {
  return (
    <div className="space-y-4">
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

      <div className="grid grid-cols-2 gap-4">
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

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label>Applications Open Date <span className="text-red-500">*</span></Label>
          <DatePicker
            date={formData.application_open_date ? new Date(formData.application_open_date + 'T00:00:00') : null}
            setDate={(date) => setFormData({
              ...formData,
              application_open_date: date ? toLocaleDateStr(date) : '',
            })}
            placeholder="Select open date"
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


