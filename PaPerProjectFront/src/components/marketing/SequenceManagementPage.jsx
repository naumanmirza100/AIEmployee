import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, ArrowLeft, ListOrdered, Mail, Plus, Pencil, Trash2, BarChart3, Eye, Send } from 'lucide-react';
import {
  getSequences,
  createSequence,
  updateSequence,
  deleteSequence,
  getSequenceDetails,
  createTemplate,
  updateTemplate,
  deleteTemplate,
  testEmailTemplate,
  getCampaign,
} from '@/services/marketingAgentService';

const MIN_STEP_GAP_MINUTES = 5;

/** Merge fields for email templates (lead data). Keys match placeholders e.g. {{first_name}}. */
const TEMPLATE_MERGE_FIELDS = [
  { key: 'first_name', label: 'First name' },
  { key: 'last_name', label: 'Last name' },
  { key: 'email', label: 'Email' },
  { key: 'company', label: 'Company' },
  { key: 'job_title', label: 'Job title' },
  // { key: 'phone', label: 'Phone' },
];

const INTEREST_LEVEL_OPTIONS = [
  { value: 'any', label: 'Any Reply (catches all replies)' },
  { value: 'positive', label: 'Interested / Positive' },
  { value: 'negative', label: 'Not Interested / Negative' },
  { value: 'neutral', label: 'Neutral / Acknowledgment' },
  { value: 'requested_info', label: 'Requested More Information' },
  { value: 'objection', label: 'Has Objection / Concern' },
  { value: 'unsubscribe', label: 'Unsubscribe Request' },
];

function stepTotalMinutes(step) {
  const d = Number(step?.delay_days) || 0;
  const h = Number(step?.delay_hours) || 0;
  const m = Number(step?.delay_minutes) || 0;
  return d * 24 * 60 + h * 60 + m;
}

function delayFromTotalMinutes(totalMinutes) {
  const m = totalMinutes % 60;
  const h = Math.floor((totalMinutes / 60) % 24);
  const d = Math.floor(totalMinutes / (24 * 60));
  return { delay_days: d, delay_hours: h, delay_minutes: m };
}

/** Validate step delays: first >= 5 min, each next >= previous total + 5 min. Returns { valid, errors[] }. */
function validateStepDelays(steps) {
  const errors = [];
  let prevTotal = 0;
  for (let i = 0; i < steps.length; i++) {
    const total = stepTotalMinutes(steps[i]);
    if (i === 0) {
      if (total < MIN_STEP_GAP_MINUTES) {
        errors[i] = `Step 1 delay must be at least ${MIN_STEP_GAP_MINUTES} minutes.`;
      } else {
        errors[i] = null;
      }
    } else {
      const minRequired = prevTotal + MIN_STEP_GAP_MINUTES;
      if (total < minRequired) {
        errors[i] = `Step ${i + 1} must be at least ${MIN_STEP_GAP_MINUTES} min after previous (min ${minRequired} min total).`;
      } else {
        errors[i] = null;
      }
    }
    prevTotal = total;
  }
  const valid = errors.every((e) => e == null);
  return { valid, errors };
}

const SequenceManagementPage = ({ embedded = false }) => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [createTemplateOpen, setCreateTemplateOpen] = useState(false);
  const [viewTemplateOpen, setViewTemplateOpen] = useState(false);
  const [viewTemplate, setViewTemplate] = useState(null);
  const [editingTemplateId, setEditingTemplateId] = useState(null);
  const [createSequenceOpen, setCreateSequenceOpen] = useState(false);
  const [editSequenceOpen, setEditSequenceOpen] = useState(false);
  const [detailsSequenceOpen, setDetailsSequenceOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [testTemplateOpen, setTestTemplateOpen] = useState(false);
  const [testTemplate, setTestTemplate] = useState(null);
  const [testEmail, setTestEmail] = useState('');
  const [testLeadId, setTestLeadId] = useState('');
  const [testLeads, setTestLeads] = useState([]);
  const [testSending, setTestSending] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [templateForm, setTemplateForm] = useState({ name: '', subject: '', html_content: '' });
  const [sequenceForm, setSequenceForm] = useState({
    name: '',
    email_account_id: '',
    parent_sequence_id: '',
    interest_level: 'any',
    is_sub_sequence: false,
    steps: [{ template_id: '', delay_days: 0, delay_hours: 0, delay_minutes: MIN_STEP_GAP_MINUTES }],
  });
  const [stepErrors, setStepErrors] = useState([]);
  const [editingSequenceId, setEditingSequenceId] = useState(null);
  const [detailsSequence, setDetailsSequence] = useState(null);
  const templateHtmlRef = useRef(null);
  const templateSubjectRef = useRef(null);

  /** Insert {{key}} into Subject or Body. Use mousedown so field keeps focus and we can read selection. */
  const insertMergeField = useCallback((key) => {
    const placeholder = `{{${key}}}`;
    const subjectEl = templateSubjectRef.current;
    const bodyEl = templateHtmlRef.current;
    const active = document.activeElement;

    if (active === subjectEl && subjectEl && typeof subjectEl.selectionStart === 'number') {
      const current = templateForm.subject || '';
      const start = subjectEl.selectionStart;
      const end = subjectEl.selectionEnd ?? start;
      const newContent = current.slice(0, start) + placeholder + current.slice(end);
      const newCursor = start + placeholder.length;
      setTemplateForm((p) => ({ ...p, subject: newContent }));
      setTimeout(() => {
        if (templateSubjectRef.current) {
          templateSubjectRef.current.focus();
          templateSubjectRef.current.setSelectionRange(newCursor, newCursor);
        }
      }, 0);
      return;
    }

    if (active === bodyEl && bodyEl && typeof bodyEl.selectionStart === 'number') {
      const current = templateForm.html_content || '';
      const start = bodyEl.selectionStart;
      const end = bodyEl.selectionEnd ?? start;
      const newContent = current.slice(0, start) + placeholder + current.slice(end);
      const newCursor = start + placeholder.length;
      setTemplateForm((p) => ({ ...p, html_content: newContent }));
      setTimeout(() => {
        if (templateHtmlRef.current) {
          templateHtmlRef.current.focus();
          templateHtmlRef.current.setSelectionRange(newCursor, newCursor);
        }
      }, 0);
      return;
    }

    // Neither focused: append to body
    const current = templateForm.html_content || '';
    const newContent = current + placeholder;
    setTemplateForm((p) => ({ ...p, html_content: newContent }));
    setTimeout(() => {
      if (templateHtmlRef.current) {
        templateHtmlRef.current.focus();
        templateHtmlRef.current.setSelectionRange(newContent.length, newContent.length);
      }
    }, 0);
  }, [templateForm.subject, templateForm.html_content]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getSequences(id);
      if (res?.status === 'success' && res?.data) {
        setData(res.data);
      } else {
        setData({ campaign: null, sequences: [], templates: [], email_accounts: [], has_main_sequence: false });
      }
    } catch {
      setData({ campaign: null, sequences: [], templates: [], email_accounts: [], has_main_sequence: false });
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const { campaign, sequences = [], templates = [], email_accounts = [], has_main_sequence } = data || {};

  const handleCreateTemplate = async (e) => {
    e.preventDefault();
    if (!templateForm.name?.trim() || !templateForm.subject?.trim()) {
      toast({ title: 'Validation', description: 'Name and subject are required.', variant: 'destructive' });
      return;
    }
    setActionLoading(true);
    try {
      const res = await createTemplate(id, {
        name: templateForm.name.trim(),
        subject: templateForm.subject.trim(),
        html_content: templateForm.html_content || '',
      });
      if (res?.status === 'success') {
        toast({ title: 'Success', description: res?.data?.message || 'Template created.' });
        setCreateTemplateOpen(false);
        setTemplateForm({ name: '', subject: '', html_content: '' });
        fetchData();
      } else {
        toast({ title: 'Error', description: res?.message || 'Failed to create template.', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Error', description: e?.message || 'Failed to create template.', variant: 'destructive' });
    } finally {
      setActionLoading(false);
    }
  };

  const openViewTemplate = (t) => {
    setViewTemplate(t);
    setViewTemplateOpen(true);
  };

  const openEditTemplate = (t) => {
    setTemplateForm({
      name: t.name || '',
      subject: t.subject || '',
      html_content: t.html_content || '',
    });
    setEditingTemplateId(t.id);
    setCreateTemplateOpen(true);
  };

  const openTestTemplate = async (t) => {
    setTestTemplate(t);
    setTestEmail('');
    setTestLeadId('');
    setTestLeads([]);
    setTestTemplateOpen(true);
    try {
      const res = await getCampaign(id, { detail: 1 });
      const leads = res?.data?.leads ?? [];
      setTestLeads(Array.isArray(leads) ? leads : []);
    } catch {
      setTestLeads([]);
    }
  };

  const handleSendTestEmail = async (e) => {
    e.preventDefault();
    const email = (testEmail || '').trim();
    if (!email) {
      toast({ title: 'Validation', description: 'Enter an email address to send the test to.', variant: 'destructive' });
      return;
    }
    if (!testTemplate?.id) return;
    setTestSending(true);
    try {
      const payload = { test_email: email };
      if (testLeadId) payload.lead_id = Number(testLeadId);
      const res = await testEmailTemplate(id, testTemplate.id, payload);
      if (res?.status === 'success') {
        toast({ title: 'Success', description: res?.data?.message || 'Test email sent.' });
        setTestTemplateOpen(false);
        setTestTemplate(null);
        setTestEmail('');
        setTestLeadId('');
      } else {
        toast({ title: 'Error', description: res?.message || 'Failed to send test email.', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Error', description: e?.message || 'Failed to send test email.', variant: 'destructive' });
    } finally {
      setTestSending(false);
    }
  };

  const handleUpdateTemplate = async (e) => {
    e.preventDefault();
    if (!editingTemplateId || !templateForm.name?.trim() || !templateForm.subject?.trim()) {
      toast({ title: 'Validation', description: 'Name and subject are required.', variant: 'destructive' });
      return;
    }
    setActionLoading(true);
    try {
      const res = await updateTemplate(id, editingTemplateId, {
        name: templateForm.name.trim(),
        subject: templateForm.subject.trim(),
        html_content: templateForm.html_content || '',
      });
      if (res?.status === 'success') {
        toast({ title: 'Success', description: res?.data?.message || 'Template updated.' });
        setCreateTemplateOpen(false);
        setEditingTemplateId(null);
        setTemplateForm({ name: '', subject: '', html_content: '' });
        fetchData();
      } else {
        toast({ title: 'Error', description: res?.message || 'Failed to update template.', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Error', description: e?.message || 'Failed to update template.', variant: 'destructive' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteTemplate = async (templateId, name) => {
    setActionLoading(true);
    try {
      const res = await deleteTemplate(id, templateId);
      if (res?.status === 'success') {
        toast({ title: 'Success', description: res?.data?.message || 'Template deleted.' });
        setDeleteConfirm(null);
        fetchData();
      } else {
        toast({ title: 'Error', description: res?.message || 'Failed to delete.', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Error', description: e?.message || 'Failed to delete.', variant: 'destructive' });
    } finally {
      setActionLoading(false);
    }
  };

  const addStep = () => {
    setSequenceForm((prev) => {
      const last = prev.steps[prev.steps.length - 1];
      const prevTotal = stepTotalMinutes(last);
      const nextTotal = prevTotal + MIN_STEP_GAP_MINUTES;
      const delay = delayFromTotalMinutes(nextTotal);
      return {
        ...prev,
        steps: [...prev.steps, { template_id: '', ...delay }],
      };
    });
    setStepErrors([]);
  };

  const removeStep = (idx) => {
    if (sequenceForm.steps.length <= 1) return;
    setSequenceForm((prev) => {
      const nextSteps = prev.steps.filter((_, i) => i !== idx);
      const { errors } = validateStepDelays(nextSteps);
      setStepErrors(errors);
      return { ...prev, steps: nextSteps };
    });
  };

  const updateStep = (idx, field, value) => {
    setSequenceForm((prev) => {
      const next = {
        ...prev,
        steps: prev.steps.map((s, i) => (i === idx ? { ...s, [field]: value } : s)),
      };
      const { errors } = validateStepDelays(next.steps);
      setStepErrors(errors);
      return next;
    });
  };

  const handleCreateSequence = async (e) => {
    e.preventDefault();
    if (!sequenceForm.name?.trim()) {
      toast({ title: 'Validation', description: 'Sequence name is required.', variant: 'destructive' });
      return;
    }
    const steps = sequenceForm.steps
      .map((s) => ({ ...s, template_id: Number(s.template_id) || null }))
      .filter((s) => s.template_id);
    if (steps.length === 0) {
      toast({ title: 'Validation', description: 'Add at least one step with a template.', variant: 'destructive' });
      return;
    }
    const { valid, errors } = validateStepDelays(sequenceForm.steps);
    if (!valid) {
      setStepErrors(errors);
      const firstMsg = errors.find((e) => e);
      toast({ title: 'Step delay invalid', description: firstMsg || 'Each step must be at least 5 min after the previous (first step: 5 min min).', variant: 'destructive' });
      return;
    }
    setStepErrors([]);
    setActionLoading(true);
    try {
      const isSub = !!sequenceForm.parent_sequence_id;
      const payload = {
        name: sequenceForm.name.trim(),
        email_account_id: sequenceForm.email_account_id ? Number(sequenceForm.email_account_id) : null,
        is_active: true,
        steps: steps,
      };
      if (isSub) {
        payload.is_sub_sequence = true;
        payload.parent_sequence_id = Number(sequenceForm.parent_sequence_id);
        payload.interest_level = sequenceForm.interest_level || 'any';
      }
      const res = await createSequence(id, payload);
      if (res?.status === 'success') {
        toast({ title: 'Success', description: res?.data?.message || 'Sequence created.' });
        setCreateSequenceOpen(false);
        setSequenceForm({
          name: '',
          email_account_id: '',
          parent_sequence_id: '',
          interest_level: 'any',
          is_sub_sequence: false,
          steps: [{ template_id: '', delay_days: 0, delay_hours: 0, delay_minutes: MIN_STEP_GAP_MINUTES }],
        });
        setStepErrors([]);
        fetchData();
      } else {
        toast({ title: 'Error', description: res?.message || 'Failed to create sequence.', variant: 'destructive' });
      }
    } catch (e) {
      const msg = e?.response?.data?.message || e?.message || 'Failed to create sequence.';
      toast({ title: 'Error', description: msg, variant: 'destructive' });
    } finally {
      setActionLoading(false);
    }
  };

  const openEditSequence = async (sequenceId) => {
    setEditingSequenceId(sequenceId);
    setEditSequenceOpen(true);
    setStepErrors([]);
    try {
      const res = await getSequenceDetails(id, sequenceId);
      if (res?.status === 'success' && res?.data?.sequence) {
        const seq = res.data.sequence;
        const steps =
          seq.steps?.length > 0
            ? seq.steps.map((s) => ({
              template_id: String(s.template_id),
              delay_days: s.delay_days ?? 0,
              delay_hours: s.delay_hours ?? 0,
              delay_minutes: s.delay_minutes ?? 0,
            }))
            : [{ template_id: '', delay_days: 0, delay_hours: 0, delay_minutes: MIN_STEP_GAP_MINUTES }];
        setSequenceForm({
          name: seq.name,
          email_account_id: seq.email_account_id ? String(seq.email_account_id) : '',
          parent_sequence_id: seq.parent_sequence_id ? String(seq.parent_sequence_id) : '',
          interest_level: seq.interest_level || 'any',
          is_sub_sequence: !!seq.is_sub_sequence,
          steps,
        });
      }
    } catch (e) {
      toast({ title: 'Error', description: e?.message || 'Failed to load sequence.', variant: 'destructive' });
    }
  };

  const handleUpdateSequence = async (e) => {
    e.preventDefault();
    if (!editingSequenceId || !sequenceForm.name?.trim()) {
      toast({ title: 'Validation', description: 'Sequence name is required.', variant: 'destructive' });
      return;
    }
    const steps = sequenceForm.steps
      .map((s) => ({ ...s, template_id: Number(s.template_id) || null }))
      .filter((s) => s.template_id);
    if (steps.length === 0) {
      toast({ title: 'Validation', description: 'Add at least one step with a template.', variant: 'destructive' });
      return;
    }
    const { valid, errors } = validateStepDelays(sequenceForm.steps);
    if (!valid) {
      setStepErrors(errors);
      const firstMsg = errors.find((e) => e);
      toast({ title: 'Step delay invalid', description: firstMsg || 'Each step must be at least 5 min after the previous (first step: 5 min min).', variant: 'destructive' });
      return;
    }
    setStepErrors([]);
    setActionLoading(true);
    try {
      const payload = {
        name: sequenceForm.name.trim(),
        email_account_id: sequenceForm.email_account_id ? Number(sequenceForm.email_account_id) : null,
        is_active: true,
        steps: steps,
      };
      if (sequenceForm.is_sub_sequence) {
        payload.interest_level = sequenceForm.interest_level || 'any';
      }
      const res = await updateSequence(id, editingSequenceId, payload);
      if (res?.status === 'success') {
        toast({ title: 'Success', description: res?.data?.message || 'Sequence updated.' });
        setEditSequenceOpen(false);
        setEditingSequenceId(null);
        fetchData();
      } else {
        toast({ title: 'Error', description: res?.message || 'Failed to update.', variant: 'destructive' });
      }
    } catch (e) {
      const msg = e?.response?.data?.message || e?.message || 'Failed to update.';
      toast({ title: 'Error', description: msg, variant: 'destructive' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteSequence = async (sequenceId, name) => {
    setActionLoading(true);
    try {
      const res = await deleteSequence(id, sequenceId);
      if (res?.status === 'success') {
        toast({ title: 'Success', description: res?.data?.message || 'Sequence deleted.' });
        setDeleteConfirm(null);
        fetchData();
      } else {
        toast({ title: 'Error', description: res?.message || 'Failed to delete.', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Error', description: e?.message || 'Failed to delete.', variant: 'destructive' });
    } finally {
      setActionLoading(false);
    }
  };

  const openDetails = async (seq) => {
    setDetailsSequence(seq);
    setDetailsSequenceOpen(true);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[320px]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const noData = !loading && !campaign;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          {!embedded && (
            <Button variant="ghost" asChild>
              <Link to={`/marketing/dashboard/campaign/${id}`}>
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back to {campaign?.name || 'Campaign'}
              </Link>
            </Button>
          )}
          <h1 className={`flex items-center gap-2 ${embedded ? 'text-lg font-semibold' : 'text-2xl font-semibold mt-2'}`}>
            <ListOrdered className="h-6 w-6" />
            Email sequences
          </h1>
          <CardDescription>Create and manage email sequences for this campaign.</CardDescription>
        </div>
        {!noData && (
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setCreateTemplateOpen(true)}>
              <Mail className="mr-2 h-4 w-4" />
              Create email template
            </Button>
            <Button
              variant="default"
              onClick={() => {
                setSequenceForm({
                  name: '',
                  email_account_id: email_accounts?.[0]?.id ? String(email_accounts[0].id) : '',
                  parent_sequence_id: '',
                  interest_level: 'any',
                  is_sub_sequence: false,
                  steps: [{ template_id: '', delay_days: 0, delay_hours: 0, delay_minutes: MIN_STEP_GAP_MINUTES }],
                });
                setStepErrors([]);
                setCreateSequenceOpen(true);
              }}
              disabled={has_main_sequence}
              title={has_main_sequence ? 'Only one main sequence per campaign. Edit or delete the existing one first.' : ''}
            >
              <Plus className="mr-2 h-4 w-4" />
              Create sequence
            </Button>
          </div>
        )}
      </div>

      {noData ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-muted-foreground mb-4">
              {id ? 'No campaign found for this link, or no data is available yet.' : 'No data available.'}
            </p>
            {!embedded && (
              <Button asChild variant="outline">
                <Link to="/marketing/dashboard">
                  <ArrowLeft className="mr-2 h-4 w-4" />
                  Back to Dashboard
                </Link>
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Email templates */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Email templates</CardTitle>
              <CardDescription>Templates used in sequence steps. Create one before creating a sequence.</CardDescription>
            </CardHeader>
            <CardContent>
              {templates.length === 0 ? (
                <p className="text-muted-foreground text-sm py-4">No templates yet. Create one to build sequences.</p>
              ) : (
                <ul className="space-y-2">
                  {templates.map((t) => (
                    <li
                      key={t.id}
                      className="flex items-center justify-between gap-2 rounded-lg border p-3 bg-muted/20"
                    >
                      <div className="min-w-0 flex-1">
                        <span className="font-medium">{t.name}</span>
                        <span className="text-muted-foreground text-sm ml-2">— {t.subject}</span>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        <Button
                          variant="ghost"
                          size="sm"
                          title="View template"
                          onClick={() => openViewTemplate(t)}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          title="Edit template"
                          onClick={() => openEditTemplate(t)}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          title="Send test email"
                          onClick={() => openTestTemplate(t)}
                        >
                          <Send className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-destructive hover:text-destructive"
                          title="Delete template"
                          onClick={() => setDeleteConfirm({ type: 'template', id: t.id, name: t.name })}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          {/* Sequences */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Sequences</CardTitle>
              <CardDescription>One main sequence per campaign. Each step uses a template and a delay.</CardDescription>
            </CardHeader>
            <CardContent>
              {sequences.length === 0 ? (
                <p className="text-muted-foreground text-sm py-4">No sequence yet. Create a template first, then create a sequence.</p>
              ) : (
                <div className="space-y-4">
                  {sequences.map((seq) => (
                    <div key={seq.id} className="rounded-lg border p-4 bg-muted/10">
                      <div className="flex flex-wrap items-start justify-between gap-4">
                        <div>
                          <div className="flex items-center gap-2">
                            <h3 className="font-semibold">{seq.name}</h3>
                            <Badge variant={seq.effective_is_active ? 'default' : 'secondary'} className="text-xs py-0 ml-3">
                              {seq.effective_is_active ? 'Active' : 'Inactive'}
                            </Badge>
                          </div>
                          <p className="text-sm text-muted-foreground mt-1">
                            {seq.email_account ? `From: ${seq.email_account}` : 'No email account'}
                          </p>
                          {/* <div className="flex gap-4 mt-2 text-sm">
                        <span>Sent: {seq.total_sent}</span>
                        <span>Opened: {seq.total_opened}</span>
                        <span>Clicked: {seq.total_clicked}</span>
                        <span>Open rate: {seq.open_rate}%</span>
                        <span>Click rate: {seq.click_rate}%</span>
                      </div> */}
                        </div>
                        <div className="flex gap-2 flex-wrap">
                          <Button variant="outline" size="sm" onClick={() => openDetails(seq)}>
                            <BarChart3 className="h-4 w-4 mr-1" />
                            Details
                          </Button>
                          <Button variant="outline" size="sm" onClick={() => openEditSequence(seq.id)}>
                            <Pencil className="h-4 w-4 mr-1" />
                            Edit
                          </Button>
                          {/* <Button
                            variant="secondary"
                            size="sm"
                            className="border-violet-500 text-violet-700 hover:bg-violet-50"
                            onClick={() => {
                              setSequenceForm({
                                name: '',
                                email_account_id: email_accounts?.[0]?.id ? String(email_accounts[0].id) : '',
                                parent_sequence_id: String(seq.id),
                                interest_level: 'any',
                                is_sub_sequence: true,
                                steps: [{ template_id: '', delay_days: 0, delay_hours: 0, delay_minutes: MIN_STEP_GAP_MINUTES }],
                              });
                              setStepErrors([]);
                              setCreateSequenceOpen(true);
                            }}
                          >
                            <Plus className="h-4 w-4 mr-1" />
                            Sub-Sequence
                          </Button> */}
                          <Button
                            variant="outline"
                            size="sm"
                            className="text-destructive hover:text-destructive"
                            onClick={() => setDeleteConfirm({ type: 'sequence', id: seq.id, name: seq.name })}
                          >
                            <Trash2 className="h-4 w-4 mr-1" />
                            Delete
                          </Button>
                        </div>
                      </div>
                      <div className="mt-4">
                        <h4 className="text-sm font-medium mb-2">Steps</h4>
                        <ul className="space-y-2">
                          {seq.steps?.map((step) => (
                            <li key={step.id} className="flex items-center gap-3 rounded border p-2 bg-background">
                              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-medium">
                                {step.step_order}
                              </span>
                              <span className="min-w-[7rem] shrink-0 whitespace-nowrap font-medium text-sm">{step.template_name || step.template_subject || '—'}</span>
                              <div className="flex min-w-0 flex-1 gap-2 justify-between">
                                <span className="text-xs text-muted-foreground truncate">
                                  {step.template_subject}
                                </span>
                                <span className="text-xs text-muted-foreground shrink-0">
                                  Delay: {step.delay_days}d {step.delay_hours}h {step.delay_minutes}m
                                </span>
                              </div>
                            </li>
                          ))}
                        </ul>
                      </div>
                      {(seq.sub_sequences?.length ?? 0) > 0 && (
                        <div className="mt-4 pt-4 border-t border-border">
                          <h4 className="text-sm font-medium text-foreground mb-2">Sub-sequences (triggered by replies)</h4>
                          <div className="space-y-3">
                            {seq.sub_sequences.map((sub) => (
                              <div key={sub.id} className="rounded-lg border-l-4 border-violet-500 bg-[rgba(245,255,255,0.14)] p-3">
                                <div className="flex flex-wrap items-start justify-between gap-2">
                                  <div>
                                    <span className="font-medium text-sm text-foreground">{sub.name}</span>
                                    {/* <Badge variant={sub.effective_is_active ? 'default' : 'secondary'} className="ml-2 text-xs">
                                      {sub.effective_is_active ? 'Active' : 'Inactive'}
                                    </Badge> */}
                                    <span className="text-xs text-muted-foreground ml-2">
                                      Interest: {INTEREST_LEVEL_OPTIONS.find((o) => o.value === sub.interest_level)?.label ?? sub.interest_level}
                                    </span>
                                    <span className="text-xs text-muted-foreground ml-2">Steps: {sub.steps?.length ?? 0}</span>
                                  </div>
                                  <div className="flex gap-1">
                                    <Button variant="ghost" size="sm" onClick={() => openDetails(sub)}>
                                      <BarChart3 className="h-3 w-3 mr-1" /> Details
                                    </Button>
                                    <Button variant="ghost" size="sm" onClick={() => openEditSequence(sub.id)}>
                                      <Pencil className="h-3 w-3 mr-1" /> Edit
                                    </Button>
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      className="text-destructive hover:text-destructive"
                                      onClick={() => setDeleteConfirm({ type: 'sequence', id: sub.id, name: sub.name })}
                                    >
                                      <Trash2 className="h-4 w-4" />
                                    </Button>
                                  </div>
                                </div>
                                <ul className="mt-2 space-y-1">
                                  {sub.steps?.slice(0, 5).map((step) => (
                                    <li key={step.id} className="flex items-center gap-2 text-xs">
                                      <span className="shrink-0 font-medium">{step.step_order}.</span>
                                      <span className="min-w-[6rem] shrink-0 whitespace-nowrap">{step.template_name || step.template_subject || '—'}</span>
                                      <span className="text-muted-foreground shrink-0">Delay: {step.delay_days}d {step.delay_hours}h {step.delay_minutes}m</span>
                                    </li>
                                  ))}
                                  {(sub.steps?.length ?? 0) > 5 && (
                                    <li className="text-xs text-muted-foreground">+{(sub.steps?.length ?? 0) - 5} more</li>
                                  )}
                                </ul>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                      {seq.id && !seq.is_sub_sequence && (
                        <div className="mt-3">
                          <Button
                            variant="outline"
                            size="sm"
                            className="border-violet-500 text-violet-700 hover:bg-violet-50 text-xs"
                            onClick={() => {
                              setSequenceForm({
                                name: '',
                                email_account_id: email_accounts?.[0]?.id ? String(email_accounts[0].id) : '',
                                parent_sequence_id: String(seq.id),
                                interest_level: 'any',
                                is_sub_sequence: true,
                                steps: [{ template_id: '', delay_days: 0, delay_hours: 0, delay_minutes: MIN_STEP_GAP_MINUTES }],
                              });
                              setStepErrors([]);
                              setCreateSequenceOpen(true);
                            }}
                          >
                            <Plus className="h-3 w-3 mr-1" />
                            Add Sub-Sequence
                          </Button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {/* View template modal */}
      <Dialog open={viewTemplateOpen} onOpenChange={(open) => { if (!open) setViewTemplate(null); setViewTemplateOpen(open); }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Email template</DialogTitle>
            <DialogDescription>View template content.</DialogDescription>
          </DialogHeader>
          {viewTemplate && (
            <div className="space-y-4 py-2">
              <div>
                <Label className="text-muted-foreground text-xs">Name</Label>
                <p className="font-medium mt-0.5">{viewTemplate.name}</p>
              </div>
              <div>
                <Label className="text-muted-foreground text-xs">Subject</Label>
                <p className="mt-0.5 break-words">{viewTemplate.subject}</p>
              </div>
              <div>
                <Label className="text-muted-foreground text-xs">Body (HTML)</Label>
                <div className="mt-1 rounded border bg-muted/20 p-3 max-h-64 overflow-y-auto text-sm font-mono whitespace-pre-wrap break-words">
                  {viewTemplate.html_content || <span className="text-muted-foreground">(empty)</span>}
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setViewTemplateOpen(false)}>Close</Button>
                <Button onClick={() => { setViewTemplateOpen(false); openEditTemplate(viewTemplate); }}>Edit</Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Send test email dialog */}
      <Dialog open={testTemplateOpen} onOpenChange={(open) => { if (!open) { setTestTemplate(null); setTestEmail(''); setTestLeadId(''); } setTestTemplateOpen(open); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Send test email</DialogTitle>
            <DialogDescription>
              {testTemplate?.name
                ? `Send a test of "${testTemplate.name}" to verify subject and body (e.g. {{first_name}}). Use sample data or pick a lead.`
                : 'Send a test email for this template.'}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSendTestEmail} className="space-y-4 py-4">
            <div>
              <Label htmlFor="test-email">Email address *</Label>
              <Input
                id="test-email"
                type="email"
                value={testEmail}
                onChange={(e) => setTestEmail(e.target.value)}
                placeholder="you@example.com"
                disabled={testSending}
              />
            </div>
            <div>
              <Label htmlFor="test-lead">Lead (optional)</Label>
              <Select value={testLeadId || 'none'} onValueChange={(v) => setTestLeadId(v === 'none' ? '' : v)} disabled={testSending}>
                <SelectTrigger id="test-lead">
                  <SelectValue placeholder="Use sample data" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Use sample data (Test User)</SelectItem>
                  {testLeads.map((lead) => (
                    <SelectItem key={lead.id} value={String(lead.id)}>
                      {lead.first_name || lead.last_name ? [lead.first_name, lead.last_name].filter(Boolean).join(' ') : lead.email}
                      {lead.email ? ` (${lead.email})` : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground mt-1">Pick a lead to fill placeholders with their data; otherwise sample values are used.</p>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setTestTemplateOpen(false)} disabled={testSending}>Cancel</Button>
              <Button type="submit" disabled={testSending}>
                {testSending ? <><Loader2 className="h-4 w-4 animate-spin mr-2" /> Sending…</> : 'Send test'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Create / Edit template modal */}
      <Dialog open={createTemplateOpen} onOpenChange={(open) => { if (!open) { setEditingTemplateId(null); setTemplateForm({ name: '', subject: '', html_content: '' }); } setCreateTemplateOpen(open); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingTemplateId ? 'Edit email template' : 'Create email template'}</DialogTitle>
            <DialogDescription>{editingTemplateId ? 'Update the template. Changes apply to sequence steps using it.' : 'Add a template to use in sequence steps.'}</DialogDescription>
          </DialogHeader>
          <form onSubmit={editingTemplateId ? handleUpdateTemplate : handleCreateTemplate}>
            <div className="space-y-4 py-4">
              <div>
                <Label htmlFor="t-name">Name</Label>
                <Input
                  id="t-name"
                  value={templateForm.name}
                  onChange={(e) => setTemplateForm((p) => ({ ...p, name: e.target.value }))}
                  placeholder="e.g. Welcome email"
                />
              </div>
              <div>
                <Label htmlFor="t-subject">Subject</Label>
                <Input
                  id="t-subject"
                  ref={templateSubjectRef}
                  value={templateForm.subject}
                  onChange={(e) => setTemplateForm((p) => ({ ...p, subject: e.target.value }))}
                  placeholder="e.g. Hello {{first_name}}"
                />
              </div>
              <div>
                <p className="text-xs text-muted-foreground mb-1.5">Insert lead field into Subject or Body (click in the field first, then click a button).</p>
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {TEMPLATE_MERGE_FIELDS.map(({ key, label }) => (
                    <Button
                      key={key}
                      type="button"
                      variant="outline"
                      size="sm"
                      className="text-xs h-7"
                      onMouseDown={(e) => {
                        e.preventDefault();
                        insertMergeField(key);
                      }}
                    >
                      {label}
                    </Button>
                  ))}
                </div>
              </div>
              <div>
                <Label htmlFor="t-html">HTML content (optional)</Label>
                <textarea
                  id="t-html"
                  ref={templateHtmlRef}
                  className="flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono resize-y"
                  value={templateForm.html_content}
                  onChange={(e) => setTemplateForm((p) => ({ ...p, html_content: e.target.value }))}
                  placeholder="<p>Hello {{first_name}},</p><p>...</p>"
                />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCreateTemplateOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={actionLoading}>
                {actionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : editingTemplateId ? 'Update' : 'Create'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Create sequence modal */}
      <Dialog open={createSequenceOpen} onOpenChange={(open) => { if (!open) setSequenceForm((p) => ({ ...p, parent_sequence_id: '', interest_level: 'any', is_sub_sequence: false })); setCreateSequenceOpen(open); }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{sequenceForm.parent_sequence_id ? 'Create Sub-Sequence (Reply Triggered)' : 'Create sequence'}</DialogTitle>
            <DialogDescription>
              {sequenceForm.parent_sequence_id
                ? 'This sub-sequence starts when a lead replies to the main sequence. Choose which reply type to handle. First step: min 5 min; each step at least 5 min after the previous.'
                : 'One main sequence per campaign. Add steps with template and delay. First step: min 5 min; each step at least 5 min after the previous.'}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreateSequence}>
            <div className="space-y-4 py-4">
              {sequenceForm.parent_sequence_id && (
                <div className="rounded-lg border border-border bg-muted/30 p-4 space-y-3">
                  <div>
                    <p className="text-sm font-medium text-foreground">Sub-sequence</p>
                    <p className="text-sm text-muted-foreground mt-1">
                      Starts when a lead replies to the main sequence. Main sequence stops; this sequence runs per the delays below.
                    </p>
                  </div>
                  <div>
                    <Label className="text-foreground">Reply interest level *</Label>
                    <Select
                      value={sequenceForm.interest_level || 'any'}
                      onValueChange={(v) => setSequenceForm((p) => ({ ...p, interest_level: v }))}
                    >
                      <SelectTrigger className="mt-1.5">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {INTEREST_LEVEL_OPTIONS.map((o) => (
                          <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground mt-1.5">Replies are routed to the matching sub-sequence by interest level.</p>
                  </div>
                </div>
              )}
              <div>
                <Label>Sequence name</Label>
                <Input
                  value={sequenceForm.name}
                  onChange={(e) => setSequenceForm((p) => ({ ...p, name: e.target.value }))}
                  placeholder={sequenceForm.parent_sequence_id ? 'e.g. Interested follow-up' : 'e.g. Main follow-up sequence'}
                />
              </div>
              <div>
                <Label>Send from (email account)</Label>
                <Select
                  value={sequenceForm.email_account_id || '__none__'}
                  onValueChange={(v) => setSequenceForm((p) => ({ ...p, email_account_id: v === '__none__' ? '' : v }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select account" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">No account</SelectItem>
                    {email_accounts.map((a) => (
                      <SelectItem key={a.id} value={String(a.id)}>
                        {a.email} {a.is_default ? '(default)' : ''}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <Label>Steps</Label>
                  <Button type="button" variant="outline" size="sm" onClick={addStep}>
                    Add step
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground mb-2">First step: min 5 min total. Each step: at least 5 min after the previous.</p>
                {sequenceForm.steps.map((step, idx) => (
                  <div key={idx} className="flex items-end gap-2 mb-3 p-3 rounded border bg-muted/20">
                    <div className='flex items-center gap-2'>
                      <div className="w-[180px]">
                        <Label className="text-xs">Template</Label>
                        <Select
                          value={step.template_id || '__none__'}
                          onValueChange={(v) => updateStep(idx, 'template_id', v === '__none__' ? '' : v)}
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Template" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="__none__">—</SelectItem>
                            {templates.map((t) => (
                              <SelectItem key={t.id} value={String(t.id)}>{t.name}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="w-20">
                        <Label className="text-xs">Days</Label>
                        <Input
                          type="number"
                          min={0}
                          value={step.delay_days}
                          onChange={(e) => updateStep(idx, 'delay_days', parseInt(e.target.value, 10) || 0)}
                        />
                      </div>
                      <div className="w-20">
                        <Label className="text-xs">Hours</Label>
                        <Input
                          type="number"
                          min={0}
                          value={step.delay_hours}
                          onChange={(e) => updateStep(idx, 'delay_hours', parseInt(e.target.value, 10) || 0)}
                        />
                      </div>
                      <div className="w-20">
                        <Label className="text-xs">Mins (≥5)</Label>
                        <Input
                          type="number"
                          min={0}
                          value={step.delay_minutes}
                          onChange={(e) => updateStep(idx, 'delay_minutes', parseInt(e.target.value, 10) || 0)}
                        />
                      </div>
                    </div>
                    <div className='flex justify-end w-full'>
                      <Button type="button" variant="destructive"  size="sm" onClick={() => removeStep(idx)} disabled={sequenceForm.steps.length <= 1}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                    {stepErrors[idx] && (
                      <p className="w-full text-xs text-destructive mt-1" role="alert">{stepErrors[idx]}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCreateSequenceOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={actionLoading}>
                {actionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : (sequenceForm.parent_sequence_id ? 'Create sub-sequence' : 'Create sequence')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit sequence modal */}
      <Dialog open={editSequenceOpen} onOpenChange={(open) => { if (!open) setEditingSequenceId(null); setEditSequenceOpen(open); }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{sequenceForm.is_sub_sequence ? 'Edit sub-sequence' : 'Edit sequence'}</DialogTitle>
            <DialogDescription>
              {sequenceForm.is_sub_sequence
                ? 'Sub-sequence runs when leads reply to the main sequence. Update name, interest level, and steps.'
                : 'Update name, email account, and steps. First step: min 5 min; each step at least 5 min after the previous.'}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleUpdateSequence}>
            <div className="space-y-4 py-4">
              {sequenceForm.is_sub_sequence && (
                <div className="rounded-lg border border-border bg-muted/30 p-4">
                  <p className="text-sm font-medium text-foreground">Sub-sequence</p>
                  <p className="text-xs text-muted-foreground mt-1 mb-3">Parent: main sequence (triggered by replies).</p>
                  <div>
                    <Label className="text-foreground">Reply interest level</Label>
                    <Select
                      value={sequenceForm.interest_level || 'any'}
                      onValueChange={(v) => setSequenceForm((p) => ({ ...p, interest_level: v }))}
                    >
                      <SelectTrigger className="mt-1">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {INTEREST_LEVEL_OPTIONS.map((o) => (
                          <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              )}
              <div>
                <Label>Sequence name</Label>
                <Input
                  value={sequenceForm.name}
                  onChange={(e) => setSequenceForm((p) => ({ ...p, name: e.target.value }))}
                  placeholder="Sequence name"
                />
              </div>
              <div>
                <Label>Send from (email account)</Label>
                <Select
                  value={sequenceForm.email_account_id || '__none__'}
                  onValueChange={(v) => setSequenceForm((p) => ({ ...p, email_account_id: v === '__none__' ? '' : v }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select account" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">No account</SelectItem>
                    {email_accounts.map((a) => (
                      <SelectItem key={a.id} value={String(a.id)}>{a.email}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <Label>Steps</Label>
                  <Button type="button" variant="outline" size="sm" onClick={addStep}>
                    Add step
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground mb-2">First step: min 5 min total. Each step: at least 5 min after the previous.</p>
                {sequenceForm.steps.map((step, idx) => (
                  <div key={idx} className="flex flex-wrap items-end gap-2 mb-3 p-3 rounded border bg-muted/20">
                    <div className="w-[180px]">
                      <Label className="text-xs">Template</Label>
                      <Select
                        value={step.template_id || '__none__'}
                        onValueChange={(v) => updateStep(idx, 'template_id', v === '__none__' ? '' : v)}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Template" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__none__">—</SelectItem>
                          {templates.map((t) => (
                            <SelectItem key={t.id} value={String(t.id)}>{t.name}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="w-20">
                      <Label className="text-xs">Days</Label>
                      <Input
                        type="number"
                        min={0}
                        value={step.delay_days}
                        onChange={(e) => updateStep(idx, 'delay_days', parseInt(e.target.value, 10) || 0)}
                      />
                    </div>
                    <div className="w-20">
                      <Label className="text-xs">Hours</Label>
                      <Input
                        type="number"
                        min={0}
                        value={step.delay_hours}
                        onChange={(e) => updateStep(idx, 'delay_hours', parseInt(e.target.value, 10) || 0)}
                      />
                    </div>
                    <div className="w-20">
                      <Label className="text-xs">Mins (≥5)</Label>
                      <Input
                        type="number"
                        min={0}
                        value={step.delay_minutes}
                        onChange={(e) => updateStep(idx, 'delay_minutes', parseInt(e.target.value, 10) || 0)}
                      />
                    </div>
                    <Button type="button" variant="ghost" size="sm" onClick={() => removeStep(idx)} disabled={sequenceForm.steps.length <= 1}>
                      Remove
                    </Button>
                    {stepErrors[idx] && (
                      <p className="w-full text-xs text-destructive mt-1" role="alert">{stepErrors[idx]}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setEditSequenceOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={actionLoading}>
                {actionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Save'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Sequence details dialog */}
      <Dialog open={detailsSequenceOpen} onOpenChange={setDetailsSequenceOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{detailsSequence?.name} — Details</DialogTitle>
          </DialogHeader>
          {detailsSequence && (
            <div className="space-y-2 text-sm">
              {detailsSequence.is_sub_sequence && (
                <p className="text-violet-700 dark:text-violet-300 font-medium">
                  Sub-sequence · Interest: {INTEREST_LEVEL_OPTIONS.find((o) => o.value === detailsSequence.interest_level)?.label ?? detailsSequence.interest_level}
                </p>
              )}
              <p>Sent: {detailsSequence.total_sent}</p>
              <p>Opened: {detailsSequence.total_opened} ({detailsSequence.open_rate}% rate)</p>
              <p>Clicked: {detailsSequence.total_clicked} ({detailsSequence.click_rate}% rate)</p>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <Dialog open={!!deleteConfirm} onOpenChange={() => setDeleteConfirm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete {deleteConfirm?.type === 'template' ? 'template' : 'sequence'}?</DialogTitle>
            <DialogDescription>
              This will permanently delete &quot;{deleteConfirm?.name}&quot;. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="outline" onClick={() => setDeleteConfirm(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={actionLoading}
              onClick={() => {
                if (deleteConfirm?.type === 'template') {
                  handleDeleteTemplate(deleteConfirm.id, deleteConfirm.name);
                } else if (deleteConfirm?.type === 'sequence') {
                  handleDeleteSequence(deleteConfirm.id, deleteConfirm.name);
                }
              }}
            >
              {actionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Delete'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default SequenceManagementPage;
