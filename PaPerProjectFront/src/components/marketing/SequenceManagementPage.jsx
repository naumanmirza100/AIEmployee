import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
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
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, ArrowLeft, ListOrdered, Mail, Plus, Pencil, Trash2, BarChart3, Eye, Send, AlertCircle, Sparkles, Upload, ChevronUp, ChevronDown } from 'lucide-react';
import {
  getSequences,
  createSequence,
  updateSequence,
  deleteSequence,
  getSequenceDetails,
  createTemplate,
  generateTemplateContent,
  classifyInterestLevel,
  updateTemplate,
  deleteTemplate,
  testEmailTemplate,
  getCampaign,
  uploadCampaignLeads,
} from '@/services/marketingAgentService';
import AddEmailAccountModal from './AddEmailAccountModal';
import LeadsUploadFields from './LeadsUploadFields';
import HoverTip from '../common/HoverTip';

const MIN_STEP_GAP_MINUTES = 5;
const DEFAULT_SEQUENCE_EMAIL_COUNT = 3;

/** Merge fields for email templates (lead data). Keys match placeholders e.g. {{first_name}}. */
const TEMPLATE_MERGE_FIELDS = [
  { key: 'first_name', label: 'First name' },
  { key: 'last_name', label: 'Last name' },
  { key: 'email', label: 'Email' },
  { key: 'company', label: 'Company' },
  { key: 'job_title', label: 'Job title' },
  // { key: 'phone', label: 'Phone' },
];

/** Sample values shown in the rendered preview so {{merge_fields}} aren't left as raw placeholders. */
const TEMPLATE_PREVIEW_SAMPLE_VALUES = {
  first_name: 'Alex',
  last_name: 'Morgan',
  email: 'alex.morgan@example.com',
  company: 'Acme Inc.',
  job_title: 'Marketing Manager',
};

/** Replace {{key}} placeholders with sample lead data for a human-readable preview. */
function fillTemplatePreviewValues(text) {
  if (!text) return '';
  return text.replace(/\{\{\s*([a-zA-Z_]+)\s*\}\}/g, (match, key) => {
    return TEMPLATE_PREVIEW_SAMPLE_VALUES[key] ?? match;
  });
}

const INTEREST_LEVEL_OPTIONS = [
  { value: 'any', label: 'Any Reply (catches all replies)' },
  { value: 'positive', label: 'Interested / Positive' },
  { value: 'negative', label: 'Not Interested / Negative' },
  { value: 'neutral', label: 'Neutral / Acknowledgment' },
  { value: 'requested_info', label: 'Requested More Information' },
  { value: 'objection', label: 'Has Objection / Concern' },
  { value: 'unsubscribe', label: 'Unsubscribe Request' },
];

// Auto-derives the sub-sequence's name and the AI generation goal from the
// reply interest level, so the user only has to pick the level — no separate
// name or goal-description input needed.
const INTEREST_LEVEL_DEFAULTS = {
  any: {
    name: 'Any reply follow-up',
    goal: 'Reply to a lead who responded to our outreach in some way. Acknowledge their reply warmly and move the conversation forward.',
  },
  positive: {
    name: 'Positive reply follow-up',
    goal: 'Reply to a lead who responded positively / expressed interest. Thank them, build on their enthusiasm, and guide them toward the next step (e.g. a call or demo).',
  },
  negative: {
    name: 'Negative reply follow-up',
    goal: 'Reply to a lead who responded negatively / said they are not interested. Be gracious, leave the door open for the future, and avoid being pushy.',
  },
  neutral: {
    name: 'Neutral reply follow-up',
    goal: 'Reply to a lead who gave a neutral or non-committal acknowledgment. Gently re-engage them and invite a clearer response without being pushy.',
  },
  requested_info: {
    name: 'Requested-info follow-up',
    goal: 'Reply to a lead who asked for more information. Provide clear, helpful detail and make it easy for them to take the next step.',
  },
  objection: {
    name: 'Objection follow-up',
    goal: 'Reply to a lead who raised an objection or concern. Address the concern directly and respectfully, reassure them, and keep the conversation open.',
  },
  unsubscribe: {
    name: 'Unsubscribe acknowledgment',
    goal: 'Reply to a lead who asked to unsubscribe or stop receiving emails. Confirm politely that they will not receive further emails — no sales pitch.',
  },
};


/** Badge className for interest-level (sub-sequence) – color the badge only, not the card. */
function interestBadgeClass(interestLevel) {
  const base = 'text-xs font-medium ml-2 shrink-0';
  switch (interestLevel) {
    case 'positive':
      return `${base} bg-emerald-500/90 text-white border-0 hover:bg-emerald-500/90`;
    case 'negative':
      return `${base} bg-red-500/90 text-white border-0 hover:bg-red-500/90`;
    case 'neutral':
      return `${base} bg-slate-500/90 text-white border-0 hover:bg-slate-500/90`;
    case 'requested_info':
      return `${base} bg-blue-500/90 text-white border-0 hover:bg-blue-500/90`;
    case 'objection':
      return `${base} bg-amber-500/90 text-white border-0 hover:bg-amber-500/90`;
    case 'unsubscribe':
      return `${base} bg-rose-600/90 text-white border-0 hover:bg-rose-600/90`;
    case 'any':
    default:
      return `${base} bg-violet-500/90 text-white border-0 hover:bg-violet-500/90`;
  }
}

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
  const [noEmailAccountDialogOpen, setNoEmailAccountDialogOpen] = useState(false);
  const [addEmailAccountOpen, setAddEmailAccountOpen] = useState(false);
  const [leadsCount, setLeadsCount] = useState(null);
  const [uploadLeadsOpen, setUploadLeadsOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadMessage, setUploadMessage] = useState('');
  const [uploadLoading, setUploadLoading] = useState(false);
  const [createTemplateOpen, setCreateTemplateOpen] = useState(false);
  const [viewTemplateOpen, setViewTemplateOpen] = useState(false);
  const [viewTemplate, setViewTemplate] = useState(null);
  const [showRawHtml, setShowRawHtml] = useState(false);
  const [editingTemplateId, setEditingTemplateId] = useState(null);
  const [createSequenceOpen, setCreateSequenceOpen] = useState(false);
  const [editSequenceOpen, setEditSequenceOpen] = useState(false);
  const [detailsSequenceOpen, setDetailsSequenceOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  // Bulk-select checkboxes — templates, main sequences, and sub-sequences
  // each have their own independent selection set and "delete selected" flow.
  const [selectedTemplateIds, setSelectedTemplateIds] = useState(() => new Set());
  const [selectedSequenceIds, setSelectedSequenceIds] = useState(() => new Set());
  const [selectedSubSequenceIds, setSelectedSubSequenceIds] = useState(() => new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [testTemplateOpen, setTestTemplateOpen] = useState(false);
  const [testTemplate, setTestTemplate] = useState(null);
  const [testEmail, setTestEmail] = useState('');
  const [testLeadId, setTestLeadId] = useState('');
  const [testLeads, setTestLeads] = useState([]);
  const [testSending, setTestSending] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [templateForm, setTemplateForm] = useState({ name: '', subject: '', html_content: '' });
  const [templateDescription, setTemplateDescription] = useState('');
  const [generatingTemplate, setGeneratingTemplate] = useState(false);
  const [sequenceForm, setSequenceForm] = useState({
    name: '',
    email_account_id: '',
    parent_sequence_id: '',
    interest_level: 'any',
    is_sub_sequence: false,
    steps: [{ template_id: '', delay_days: 0, delay_hours: 0, delay_minutes: MIN_STEP_GAP_MINUTES }],
  });
  const [stepErrors, setStepErrors] = useState([]);
  const [sequenceDescription, setSequenceDescription] = useState('');
  const [sequenceEmailCount, setSequenceEmailCount] = useState(String(DEFAULT_SEQUENCE_EMAIL_COUNT));
  const [generatingSequence, setGeneratingSequence] = useState(false);
  const [sequenceStepLimit, setSequenceStepLimit] = useState(null);
  // One entry per email slot in the count above. '' means "generate a new
  // template with AI"; any other value is an existing template's id to reuse
  // for that slot instead of generating.
  const [sequenceSlotTemplates, setSequenceSlotTemplates] = useState(
    Array(DEFAULT_SEQUENCE_EMAIL_COUNT).fill('')
  );
  // Once steps are generated, collapse the input panel behind an arrow so the
  // generated sequence is easy to review — still reopenable to tweak inputs.
  const [inputPanelOpen, setInputPanelOpen] = useState(true);
  // Preview of each step's template content (subject/HTML) — each step has its
  // own independent expand/collapse arrow, tracked by step index.
  const [expandedStepPreviews, setExpandedStepPreviews] = useState(() => new Set());
  // Same collapse/expand pattern for the Edit sequence modal — name/account
  // inputs vs. steps, never shown together.
  const [editInputPanelOpen, setEditInputPanelOpen] = useState(false);
  // When generating with AI from the Edit modal: add the new steps after the
  // existing ones, or replace the existing steps entirely.
  const [editGenerateMode, setEditGenerateMode] = useState('append');
  // Sub-sequence: user describes the reply scenario in plain language, AI
  // classifies it into the matching interest_level instead of the user
  // picking from the dropdown manually.
  const [subSequenceScenario, setSubSequenceScenario] = useState('');
  const [classifyingInterestLevel, setClassifyingInterestLevel] = useState(false);
  // When a single description names more than one reply type (e.g. "interested
  // leads and negative leads"), we can't route one sub-sequence to two types —
  // instead offer to create one sub-sequence per detected type in one go.
  const [detectedInterestLevels, setDetectedInterestLevels] = useState(null);
  const [creatingMultiSequences, setCreatingMultiSequences] = useState(false);
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
        if ((res.data.email_accounts?.length ?? 0) === 0) {
          setNoEmailAccountDialogOpen(true);
        }
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

  // Keep one slot-template selector per requested email, preserving existing
  // choices when the count grows/shrinks.
  useEffect(() => {
    const count = parseInt(sequenceEmailCount, 10);
    if (!Number.isFinite(count) || count < 1) return;
    setSequenceSlotTemplates((prev) => {
      if (prev.length === count) return prev;
      const next = prev.slice(0, count);
      while (next.length < count) next.push('');
      return next;
    });
  }, [sequenceEmailCount]);

  const fetchLeadsCount = useCallback(async () => {
    try {
      const res = await getCampaign(id, { detail: 1 });
      if (res?.status === 'success' && res?.data) {
        setLeadsCount(res.data.leads_count ?? res.data.campaign?.leads_count ?? (res.data.leads?.length ?? 0));
      }
    } catch {
      // Non-critical — the "add leads" prompt just won't show if this fails.
    }
  }, [id]);

  useEffect(() => {
    fetchLeadsCount();
  }, [fetchLeadsCount]);

  const handleUploadLeads = async () => {
    if (!uploadFile) {
      setUploadMessage('Please select a file');
      return;
    }
    setUploadMessage('');
    setUploadLoading(true);
    try {
      const res = await uploadCampaignLeads(id, uploadFile);
      const d = res?.data;
      if (d && typeof d.total_rows === 'number') {
        const reasons = d.rejected_reasons || {};
        const reasonParts = [];
        if (reasons.missing_email) reasonParts.push(`${reasons.missing_email} missing email`);
        if (reasons.missing_name) reasonParts.push(`${reasons.missing_name} missing name`);
        if (reasons.other) reasonParts.push(`${reasons.other} error(s)`);
        toast({
          title: d.rejected_count ? 'Leads uploaded with some rejected' : 'Leads uploaded',
          description: `${d.total_rows} row(s) found — ${d.created_count} added as lead(s)${
            d.rejected_count ? `, ${d.rejected_count} rejected (${reasonParts.join(', ')}).` : '.'
          }`,
        });
      } else {
        toast({ title: 'Success', description: 'Leads uploaded' });
      }
      setUploadLeadsOpen(false);
      setUploadFile(null);
      fetchLeadsCount();
    } catch (e) {
      setUploadMessage(e.message || 'Upload failed');
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    } finally {
      setUploadLoading(false);
    }
  };

  const { campaign, sequences = [], templates = [], email_accounts = [], has_main_sequence } = data || {};

  // Steps panel/column stays hidden — for both main sequences and
  // sub-sequences — until AI has generated them, keeping the create-sequence
  // modal to just the input fields until then.
  const stepsVisible = sequenceStepLimit != null;

  const handleGenerateTemplateContent = async () => {
    if (!templateDescription?.trim()) {
      toast({ title: 'Validation', description: 'Describe what the email should say first.', variant: 'destructive' });
      return;
    }
    setGeneratingTemplate(true);
    try {
      const res = await generateTemplateContent(id, {
        name: templateForm.name?.trim() || '',
        description: templateDescription.trim(),
      });
      if (res?.status === 'success' && res?.data) {
        setTemplateForm((p) => ({
          ...p,
          subject: res.data.subject || p.subject,
          html_content: res.data.html_content || '',
        }));
        toast({ title: 'Generated', description: 'Review and edit the subject/content, then save.' });
      } else {
        toast({ title: 'Error', description: res?.message || 'Failed to generate content.', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Error', description: e?.message || 'Failed to generate content.', variant: 'destructive' });
    } finally {
      setGeneratingTemplate(false);
    }
  };

  const resetTemplateForm = () => {
    setEditingTemplateId(null);
    setTemplateForm({ name: '', subject: '', html_content: '' });
    setTemplateDescription('');
  };

  const handleClassifyInterestLevel = async () => {
    if (!subSequenceScenario.trim()) {
      toast({ title: 'Validation', description: 'Describe the reply scenario first.', variant: 'destructive' });
      return null;
    }
    setClassifyingInterestLevel(true);
    setDetectedInterestLevels(null);
    try {
      const res = await classifyInterestLevel(id, { description: subSequenceScenario.trim() });
      if (res?.status === 'success' && res?.data?.interest_level) {
        const levels = res.data.interest_levels?.length ? res.data.interest_levels : [res.data.interest_level];
        if (levels.length > 1) {
          // Description names more than one reply type — a single sub-sequence
          // can only route on one, so let the user create all of them at once
          // instead of silently collapsing to "any" or picking one for them.
          setDetectedInterestLevels(levels);
          const labels = levels.map((l) => INTEREST_LEVEL_OPTIONS.find((o) => o.value === l)?.label || l);
          toast({ title: 'Multiple reply types detected', description: `Found: ${labels.join(', ')}. Create one sub-sequence per type below.` });
          return null;
        }
        const level = levels[0];
        const defaults = INTEREST_LEVEL_DEFAULTS[level] || INTEREST_LEVEL_DEFAULTS.any;
        setSequenceForm((p) => ({ ...p, interest_level: level, name: defaults.name }));
        setSequenceDescription(defaults.goal);
        const label = INTEREST_LEVEL_OPTIONS.find((o) => o.value === level)?.label || level;
        toast({ title: 'Type detected', description: `Matched to: ${label}` });
        return level;
      }
      toast({ title: 'Error', description: res?.message || 'Failed to detect reply type.', variant: 'destructive' });
      return null;
    } catch (e) {
      toast({ title: 'Error', description: e?.message || 'Failed to detect reply type.', variant: 'destructive' });
      return null;
    } finally {
      setClassifyingInterestLevel(false);
    }
  };

  // Create one sub-sequence per detected interest level in one go — each gets
  // its own AI-generated templates/steps, using the same generation logic as
  // a single sub-sequence, just looped and posted independently.
  const handleCreateMultipleSubSequences = async () => {
    if (!detectedInterestLevels?.length) {
      toast({ title: 'Error', description: 'No reply types detected — click "Detect type" again first.', variant: 'destructive' });
      return;
    }
    const parentId = sequenceForm.parent_sequence_id;
    const emailAccountId = sequenceForm.email_account_id;
    setCreatingMultiSequences(true);
    let createdCount = 0;
    try {
      for (const level of detectedInterestLevels) {
        const defaults = INTEREST_LEVEL_DEFAULTS[level] || INTEREST_LEVEL_DEFAULTS.any;
        const goal = defaults.goal;
        // Sub-sequences are always exactly one reply email.
        const genRes = await generateTemplateContent(id, {
          name: '',
          description: `A single reply email in a sub-sequence. Sequence goal: ${goal}.`,
        });
        if (genRes?.status !== 'success' || !genRes?.data) {
          throw new Error(genRes?.message || `Failed to generate email for ${defaults.name}.`);
        }
        const suggestedSubject = (genRes.data.subject || '').trim();
        const suggestedName = suggestedSubject ? suggestedSubject.slice(0, 60) : defaults.name;
        const createRes = await createTemplate(id, {
          name: suggestedName,
          subject: suggestedSubject || defaults.name,
          html_content: genRes.data.html_content || '',
        });
        if (createRes?.status !== 'success' || !createRes?.data?.template_id) {
          throw new Error(createRes?.message || `Failed to save template for ${defaults.name}.`);
        }
        const delay = delayFromTotalMinutes(MIN_STEP_GAP_MINUTES);
        const newSteps = [{ template_id: String(createRes.data.template_id), ...delay }];

        const res = await createSequence(id, {
          name: defaults.name,
          email_account_id: emailAccountId ? Number(emailAccountId) : null,
          is_active: true,
          steps: newSteps,
          is_sub_sequence: true,
          parent_sequence_id: Number(parentId),
          interest_level: level,
        });
        if (res?.status !== 'success') {
          throw new Error(res?.message || `Failed to create sub-sequence for ${defaults.name}.`);
        }
        createdCount += 1;
      }
      toast({ title: 'Success', description: `Created ${createdCount} sub-sequence${createdCount === 1 ? '' : 's'}.` });
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
      setSequenceDescription('');
      setSequenceEmailCount(String(DEFAULT_SEQUENCE_EMAIL_COUNT));
      setSequenceStepLimit(null);
      setSequenceSlotTemplates(Array(DEFAULT_SEQUENCE_EMAIL_COUNT).fill(''));
      setInputPanelOpen(true);
      setExpandedStepPreviews(new Set());
      setSubSequenceScenario('');
      setDetectedInterestLevels(null);
      fetchData();
    } catch (e) {
      toast({ title: 'Error', description: e?.message || 'Failed to create sub-sequences.', variant: 'destructive' });
    } finally {
      setCreatingMultiSequences(false);
    }
  };

  const handleGenerateSequence = async ({ mode = 'replace', silent = false } = {}) => {
    if (!sequenceForm.name?.trim()) {
      toast({ title: 'Validation', description: 'Sequence name is required.', variant: 'destructive' });
      return null;
    }
    // Sub-sequences are always exactly one email — only main sequences use
    // the user-entered "Number of emails" count.
    const count = sequenceForm.parent_sequence_id ? 1 : parseInt(sequenceEmailCount, 10);
    if (!Number.isFinite(count) || count < 1) {
      toast({ title: 'Validation', description: 'Enter how many emails this sequence should have.', variant: 'destructive' });
      return null;
    }
    setGeneratingSequence(true);
    try {
      const seqName = sequenceForm.name.trim();
      const goal = sequenceDescription.trim() || seqName;
      const existingSteps = mode === 'append' ? sequenceForm.steps : [];
      const newSteps = [];
      let cumulativeMinutes = existingSteps.length > 0 ? stepTotalMinutes(existingSteps[existingSteps.length - 1]) : 0;

      for (let i = 0; i < count; i++) {
        const stepLabel = `Email ${i + 1} of ${count}`;
        const chosenExistingId = sequenceSlotTemplates[i];

        let templateId;
        if (chosenExistingId) {
          // User picked an existing template for this slot — reuse it as-is,
          // no AI call, no new template created.
          templateId = chosenExistingId;
        } else {
          const genRes = await generateTemplateContent(id, {
            name: '',
            description: sequenceForm.parent_sequence_id
              ? `A single reply email in a sub-sequence. Sequence goal: ${goal}.`
              : `${stepLabel} in an email follow-up sequence. Sequence goal: ${goal}. ${
                  i === 0
                    ? 'This is the opening email — introduce the topic.'
                    : i === count - 1
                      ? 'This is the final email — a last, polite call to action.'
                      : 'This is a follow-up/reminder email — build on the previous ones without repeating them verbatim.'
                }`,
          });
          if (genRes?.status !== 'success' || !genRes?.data) {
            throw new Error(genRes?.message || `Failed to generate ${stepLabel}.`);
          }

          // Derive the template's name from the AI-written subject (same as a
          // user naming a template after seeing its subject) rather than a
          // generic sequence-based label — editable afterward either way.
          const suggestedSubject = (genRes.data.subject || '').trim();
          const suggestedName = suggestedSubject
            ? suggestedSubject.slice(0, 60)
            : `${seqName} — ${stepLabel}`;

          const createRes = await createTemplate(id, {
            name: suggestedName,
            subject: suggestedSubject || seqName,
            html_content: genRes.data.html_content || '',
          });
          if (createRes?.status !== 'success' || !createRes?.data?.template_id) {
            throw new Error(createRes?.message || `Failed to save template for ${stepLabel}.`);
          }
          templateId = createRes.data.template_id;
        }

        cumulativeMinutes += MIN_STEP_GAP_MINUTES;
        const delay = delayFromTotalMinutes(cumulativeMinutes);
        newSteps.push({ template_id: String(templateId), ...delay });
      }

      const combinedSteps = [...existingSteps, ...newSteps];
      const defaultAccountId = email_accounts.find((a) => a.is_default)?.id ?? email_accounts?.[0]?.id;
      const resolvedAccountId = sequenceForm.email_account_id || (defaultAccountId ? String(defaultAccountId) : '');
      setSequenceForm((p) => ({
        ...p,
        email_account_id: resolvedAccountId,
        steps: combinedSteps,
      }));
      if (mode === 'replace') {
        setSequenceStepLimit(count);
        setInputPanelOpen(false);
      } else {
        setEditInputPanelOpen(false);
      }
      setStepErrors([]);
      await fetchData();
      if (!silent) {
        toast({ title: 'Generated', description: 'Review the steps below, then save.' });
      }
      return { steps: combinedSteps, email_account_id: resolvedAccountId };
    } catch (e) {
      toast({ title: 'Error', description: e?.message || 'Failed to generate sequence.', variant: 'destructive' });
      return null;
    } finally {
      setGeneratingSequence(false);
    }
  };

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
        resetTemplateForm();
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
    setTemplateDescription('');
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
        resetTemplateForm();
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
    if (sequenceStepLimit != null && sequenceForm.steps.length >= sequenceStepLimit) return;
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
    const rawSteps = sequenceForm.steps;
    const rawEmailAccountId = sequenceForm.email_account_id;
    const steps = rawSteps
      .map((s) => ({ ...s, template_id: Number(s.template_id) || null }))
      .filter((s) => s.template_id);

    if (steps.length === 0) {
      toast({ title: 'Validation', description: 'Click "Generate with AI" first to create the email content.', variant: 'destructive' });
      return;
    }
    const { valid, errors } = validateStepDelays(rawSteps);
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
        email_account_id: rawEmailAccountId ? Number(rawEmailAccountId) : null,
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
        setSequenceDescription('');
        setSequenceEmailCount(String(DEFAULT_SEQUENCE_EMAIL_COUNT));
        setSequenceStepLimit(null);
        setSequenceSlotTemplates(Array(DEFAULT_SEQUENCE_EMAIL_COUNT).fill(''));
        setInputPanelOpen(true);
        setExpandedStepPreviews(new Set());
        setSubSequenceScenario('');
        setDetectedInterestLevels(null);
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
    setEditInputPanelOpen(false);
    setEditGenerateMode('append');
    setSequenceDescription('');
    setSequenceEmailCount(String(DEFAULT_SEQUENCE_EMAIL_COUNT));
    setSequenceSlotTemplates(Array(DEFAULT_SEQUENCE_EMAIL_COUNT).fill(''));
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
    let rawSteps = sequenceForm.steps;
    let rawEmailAccountId = sequenceForm.email_account_id;

    // The per-slot "use existing template" pickers only ever get applied when
    // "Generate with AI" is clicked — but any slot pointed at an existing
    // template needs no AI call at all. Apply those picks directly here so
    // hitting Save alone (without Generate) still uses them, instead of
    // silently discarding the selection.
    const chosenExistingIds = sequenceSlotTemplates.filter(Boolean);
    if (chosenExistingIds.length > 0 && !sequenceForm.is_sub_sequence) {
      const existingSteps = editGenerateMode === 'append' ? rawSteps.filter((s) => s.template_id) : [];
      let cumulativeMinutes = existingSteps.length > 0 ? stepTotalMinutes(existingSteps[existingSteps.length - 1]) : 0;
      const pickedSteps = chosenExistingIds.map((templateId) => {
        cumulativeMinutes += MIN_STEP_GAP_MINUTES;
        return { template_id: templateId, ...delayFromTotalMinutes(cumulativeMinutes) };
      });
      rawSteps = [...existingSteps, ...pickedSteps];
    }

    let steps = rawSteps
      .map((s) => ({ ...s, template_id: Number(s.template_id) || null }))
      .filter((s) => s.template_id);

    // Still nothing to save — auto-generate (AI writes new templates) using
    // whatever goal/count is already filled in, then continue into saving.
    if (steps.length === 0 && !sequenceForm.is_sub_sequence) {
      const generated = await handleGenerateSequence({ mode: 'append', silent: true });
      if (!generated) return;
      rawSteps = generated.steps;
      rawEmailAccountId = generated.email_account_id;
      steps = rawSteps
        .map((s) => ({ ...s, template_id: Number(s.template_id) || null }))
        .filter((s) => s.template_id);
    }

    if (steps.length === 0) {
      toast({ title: 'Validation', description: 'Add at least one step with a template.', variant: 'destructive' });
      return;
    }
    const { valid, errors } = validateStepDelays(rawSteps);
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
        email_account_id: rawEmailAccountId ? Number(rawEmailAccountId) : null,
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

  const toggleSelected = (setFn, itemId) => {
    setFn((prev) => {
      const next = new Set(prev);
      if (next.has(itemId)) next.delete(itemId);
      else next.add(itemId);
      return next;
    });
  };

  const toggleSelectAll = (setFn, allIds, currentSelected) => {
    setFn(currentSelected.size === allIds.length ? new Set() : new Set(allIds));
  };

  // Like toggleSelectAll, but only adds/removes this group's ids — safe when
  // the same selection Set is shared across multiple independent groups
  // (e.g. sub-sequences nested under different parent sequences).
  const toggleSelectAllInGroup = (setFn, groupIds) => {
    setFn((prev) => {
      const allSelected = groupIds.length > 0 && groupIds.every((id) => prev.has(id));
      const next = new Set(prev);
      if (allSelected) groupIds.forEach((id) => next.delete(id));
      else groupIds.forEach((id) => next.add(id));
      return next;
    });
  };

  const handleBulkDeleteTemplates = async () => {
    if (selectedTemplateIds.size === 0) return;
    setBulkDeleting(true);
    let deletedCount = 0;
    try {
      for (const templateId of selectedTemplateIds) {
        const res = await deleteTemplate(id, templateId);
        if (res?.status === 'success') deletedCount += 1;
      }
      toast({
        title: deletedCount === selectedTemplateIds.size ? 'Success' : 'Partially completed',
        description: `Deleted ${deletedCount} of ${selectedTemplateIds.size} template${selectedTemplateIds.size === 1 ? '' : 's'}.`,
        variant: deletedCount === selectedTemplateIds.size ? 'default' : 'destructive',
      });
      setSelectedTemplateIds(new Set());
      fetchData();
    } catch (e) {
      toast({ title: 'Error', description: e?.message || 'Failed to delete templates.', variant: 'destructive' });
    } finally {
      setBulkDeleting(false);
    }
  };

  const handleBulkDeleteSequences = async (idsSet, setFn) => {
    if (idsSet.size === 0) return;
    setBulkDeleting(true);
    let deletedCount = 0;
    try {
      for (const sequenceId of idsSet) {
        const res = await deleteSequence(id, sequenceId);
        if (res?.status === 'success') deletedCount += 1;
      }
      toast({
        title: deletedCount === idsSet.size ? 'Success' : 'Partially completed',
        description: `Deleted ${deletedCount} of ${idsSet.size} sequence${idsSet.size === 1 ? '' : 's'}.`,
        variant: deletedCount === idsSet.size ? 'default' : 'destructive',
      });
      setFn(new Set());
      fetchData();
    } catch (e) {
      toast({ title: 'Error', description: e?.message || 'Failed to delete sequences.', variant: 'destructive' });
    } finally {
      setBulkDeleting(false);
    }
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
            <HoverTip tip="Email templates are used in sequence steps. Create one here separately, or generate with AI while creating sequences.">
            <Button
              variant="secondary"
              onClick={() => {
                if (email_accounts.length === 0) {
                  setNoEmailAccountDialogOpen(true);
                  return;
                }
                resetTemplateForm();
                setCreateTemplateOpen(true);
              }}
              disabled={email_accounts.length === 0}
            >
              <Mail className="mr-2 h-4 w-4" />
              Create email template
            </Button>
            </HoverTip>
            <HoverTip tip="Build the main email sequence, email Templates and their steps and delays. One per campaign.">
            <Button
              variant="default"
              onClick={() => {
                if (email_accounts.length === 0) {
                  setNoEmailAccountDialogOpen(true);
                  return;
                }
                setSequenceForm({
                  name: '',
                  email_account_id: email_accounts?.[0]?.id ? String(email_accounts[0].id) : '',
                  parent_sequence_id: '',
                  interest_level: 'any',
                  is_sub_sequence: false,
                  steps: [{ template_id: '', delay_days: 0, delay_hours: 0, delay_minutes: MIN_STEP_GAP_MINUTES }],
                });
                setStepErrors([]);
                setSequenceDescription('');
                setSequenceEmailCount(String(DEFAULT_SEQUENCE_EMAIL_COUNT));
                setSequenceStepLimit(null);
                setSequenceSlotTemplates(Array(DEFAULT_SEQUENCE_EMAIL_COUNT).fill(''));
                setInputPanelOpen(true);
                setExpandedStepPreviews(new Set());
                setSubSequenceScenario('');
        setDetectedInterestLevels(null);
                setCreateSequenceOpen(true);
              }}
              disabled={has_main_sequence || email_accounts.length === 0}
              title={
                email_accounts.length === 0
                  ? 'Add an email account before creating a sequence.'
                  : has_main_sequence
                    ? 'Only one main sequence per campaign. Edit or delete the existing one first.'
                    : ''
              }
            >
              <Plus className="mr-2 h-4 w-4" />
              Create sequence
            </Button>
            </HoverTip>
          </div>
        )}
      </div>

      {!noData && leadsCount === 0 && (
        <Card className="border-amber-500/30 bg-amber-500/5">
          <CardContent className="py-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm">
              <AlertCircle className="h-4 w-4 text-amber-500 shrink-0" />
              <span>This campaign has no leads yet — sequences won't have anyone to send to.</span>
            </div>
            <Button size="sm" onClick={() => { setUploadLeadsOpen(true); setUploadMessage(''); setUploadFile(null); }}>
              <Upload className="mr-2 h-4 w-4" />
              Add leads
            </Button>
          </CardContent>
        </Card>
      )}

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
          {/* No sending account yet — shown after the user dismisses the dialog
              with "Not now", so the requirement stays visible on the tab. */}
          {email_accounts.length === 0 && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4">
              <div className="flex items-start gap-2.5 min-w-0">
                <AlertCircle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-white">First add an email account to continue</p>
                  <p className="text-xs text-white/60 mt-0.5">
                    Templates and sequences need a sending account before they can go out.
                  </p>
                </div>
              </div>
              <Button size="sm" onClick={() => setAddEmailAccountOpen(true)} className="shrink-0">
                <Mail className="mr-2 h-4 w-4" />
                Add email account
              </Button>
            </div>
          )}

          {/* Email templates */}
          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <CardTitle className="text-base">Email templates</CardTitle>
                  <CardDescription>Templates used in sequence steps. Create one before creating a sequence.</CardDescription>
                </div>
                {selectedTemplateIds.size > 0 && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={handleBulkDeleteTemplates}
                    disabled={bulkDeleting}
                  >
                    {bulkDeleting ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Trash2 className="h-4 w-4 mr-1" />}
                    Delete selected ({selectedTemplateIds.size})
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {templates.length === 0 ? (
                <p className="text-muted-foreground text-sm py-4">No templates yet. Create one to build sequences.</p>
              ) : (
                <>
                  <div className="flex items-center gap-2 mb-2">
                    <Checkbox
                      checked={templates.length > 0 && selectedTemplateIds.size === templates.length}
                      onCheckedChange={() => toggleSelectAll(setSelectedTemplateIds, templates.map((t) => t.id), selectedTemplateIds)}
                      id="select-all-templates"
                    />
                    <Label htmlFor="select-all-templates" className="text-xs text-muted-foreground cursor-pointer">Select all</Label>
                  </div>
                  <ul className="space-y-2">
                    {templates.map((t) => (
                      <li
                        key={t.id}
                        className="flex items-center justify-between gap-2 rounded-lg border p-3 bg-muted/20"
                      >
                        <div className="flex items-center gap-3 min-w-0 flex-1">
                          <Checkbox
                            checked={selectedTemplateIds.has(t.id)}
                            onCheckedChange={() => toggleSelected(setSelectedTemplateIds, t.id)}
                          />
                          <div className="min-w-0 flex-1">
                            <span className="font-medium">{t.name}</span>
                            <span className="text-muted-foreground text-sm ml-2">— {t.subject}</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          <HoverTip tip="View this template">
                            <Button variant="ghost" size="sm" onClick={() => openViewTemplate(t)}>
                              <Eye className="h-4 w-4" />
                            </Button>
                          </HoverTip>
                          <HoverTip tip="Edit this template">
                            <Button variant="ghost" size="sm" onClick={() => openEditTemplate(t)}>
                              <Pencil className="h-4 w-4" />
                            </Button>
                          </HoverTip>
                          <HoverTip tip="Send yourself a test email">
                            <Button variant="ghost" size="sm" onClick={() => openTestTemplate(t)}>
                              <Send className="h-4 w-4" />
                            </Button>
                          </HoverTip>
                          <HoverTip tip="Delete this template">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-destructive hover:text-destructive"
                              onClick={() => setDeleteConfirm({ type: 'template', id: t.id, name: t.name })}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </HoverTip>
                        </div>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </CardContent>
          </Card>

          {/* Sequences */}
          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <CardTitle className="text-base">Sequences</CardTitle>
                  <CardDescription>One main sequence per campaign. Each step uses a template and a delay.</CardDescription>
                </div>
                <div className="flex gap-2">
                  {selectedSequenceIds.size > 0 && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      onClick={() => handleBulkDeleteSequences(selectedSequenceIds, setSelectedSequenceIds)}
                      disabled={bulkDeleting}
                    >
                      {bulkDeleting ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Trash2 className="h-4 w-4 mr-1" />}
                      Delete selected ({selectedSequenceIds.size})
                    </Button>
                  )}
                  {selectedSubSequenceIds.size > 0 && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      onClick={() => handleBulkDeleteSequences(selectedSubSequenceIds, setSelectedSubSequenceIds)}
                      disabled={bulkDeleting}
                    >
                      {bulkDeleting ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Trash2 className="h-4 w-4 mr-1" />}
                      Delete selected sub-sequences ({selectedSubSequenceIds.size})
                    </Button>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {sequences.length === 0 ? (
                <p className="text-muted-foreground text-sm py-4">No sequence yet. Create a template first, then create a sequence.</p>
              ) : (
                <div className="space-y-4">
                  {sequences.map((seq) => (
                    <div key={seq.id} className="rounded-lg border p-4 bg-muted/10">
                      <div className="flex flex-wrap items-start justify-between gap-4">
                        <div className="flex items-start gap-3">
                          <Checkbox
                            className="mt-1"
                            checked={selectedSequenceIds.has(seq.id)}
                            onCheckedChange={() => toggleSelected(setSelectedSequenceIds, seq.id)}
                          />
                          <div>
                          <div className="flex items-center gap-2">
                            <h3 className="font-semibold">{seq.name}</h3>
                            <Badge variant={seq.effective_is_active ? 'default' : 'secondary'} className="text-xs py-0 ml-3">
                              {seq.effective_is_active ? 'Active' : 'Inactive'}
                            </Badge>
                          </div>
                          <p className="text-sm text-muted-foreground mt-1">
                            {seq.email_account
                              ? `From: ${seq.email_account}`
                              : campaign?.email_account_email
                                ? `From: ${campaign.email_account_email} (campaign default)`
                                : 'No email account'}
                          </p>
                          {/* <div className="flex gap-4 mt-2 text-sm">
                        <span>Sent: {seq.total_sent}</span>
                        <span>Opened: {seq.total_opened}</span>
                        <span>Clicked: {seq.total_clicked}</span>
                        <span>Open rate: {seq.open_rate}%</span>
                        <span>Click rate: {seq.click_rate}%</span>
                      </div> */}
                          </div>
                        </div>
                        <div className="flex gap-2 flex-wrap">
                          <HoverTip tip="View this sequence's stats and steps">
                            <Button variant="outline" size="sm" onClick={() => openDetails(seq)}>
                              <BarChart3 className="h-4 w-4 mr-1" />
                              Details
                            </Button>
                          </HoverTip>
                          <HoverTip tip="Edit this sequence — its steps, templates and delays">
                            <Button variant="outline" size="sm" onClick={() => openEditSequence(seq.id)}>
                              <Pencil className="h-4 w-4 mr-1" />
                              Edit
                            </Button>
                          </HoverTip>
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
                          <HoverTip tip="Delete this sequence and all its steps">
                            <Button
                              variant="outline"
                              size="sm"
                              className="text-destructive hover:text-destructive"
                              onClick={() => setDeleteConfirm({ type: 'sequence', id: seq.id, name: seq.name })}
                            >
                              <Trash2 className="h-4 w-4 mr-1" />
                              Delete
                            </Button>
                          </HoverTip>
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
                          <div className="flex items-center justify-between mb-2">
                            <h4 className="text-sm font-medium text-foreground">Sub-sequences (triggered by replies)</h4>
                            <div className="flex items-center gap-2">
                              <Checkbox
                                checked={seq.sub_sequences.length > 0 && seq.sub_sequences.every((sub) => selectedSubSequenceIds.has(sub.id))}
                                onCheckedChange={() => toggleSelectAllInGroup(setSelectedSubSequenceIds, seq.sub_sequences.map((sub) => sub.id))}
                                id={`select-all-sub-sequences-${seq.id}`}
                              />
                              <Label htmlFor={`select-all-sub-sequences-${seq.id}`} className="text-xs text-muted-foreground cursor-pointer">Select all</Label>
                            </div>
                          </div>
                          <div className="space-y-3">
                            {seq.sub_sequences.map((sub) => (
                              <div key={sub.id} className="rounded-lg border-l-4 border-violet-500 bg-[rgba(245,255,255,0.14)] p-3">
                                <div className="flex flex-wrap items-start justify-between gap-2">
                                  <div className="flex items-start gap-2">
                                    <Checkbox
                                      className="mt-0.5"
                                      checked={selectedSubSequenceIds.has(sub.id)}
                                      onCheckedChange={() => toggleSelected(setSelectedSubSequenceIds, sub.id)}
                                    />
                                    <div>
                                    <span className="font-medium text-sm text-foreground">{sub.name}</span>
                                    <Badge style={{padding: '0.05rem 0.5rem', marginLeft: '1.5rem'}} className={interestBadgeClass(sub.interest_level)} variant="secondary">
                                      {INTEREST_LEVEL_OPTIONS.find((o) => o.value === sub.interest_level)?.label ?? sub.interest_level}
                                    </Badge>
                                    <span className="text-xs text-muted-foreground ml-2">Steps: {sub.steps?.length ?? 0}</span>
                                    </div>
                                  </div>
                                  <div className="flex gap-1">
                                    <HoverTip tip="View this sub-sequence's stats and steps">
                                      <Button variant="ghost" size="sm" onClick={() => openDetails(sub)}>
                                        <BarChart3 className="h-3 w-3 mr-1" /> Details
                                      </Button>
                                    </HoverTip>
                                    <HoverTip tip="Edit this reply sub-sequence">
                                      <Button variant="ghost" size="sm" onClick={() => openEditSequence(sub.id)}>
                                        <Pencil className="h-3 w-3 mr-1" /> Edit
                                      </Button>
                                    </HoverTip>
                                    <HoverTip tip="Delete this sub-sequence">
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        className="text-destructive hover:text-destructive"
                                        onClick={() => setDeleteConfirm({ type: 'sequence', id: sub.id, name: sub.name })}
                                      >
                                        <Trash2 className="h-4 w-4" />
                                      </Button>
                                    </HoverTip>
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
                          <HoverTip tip="Add a reply sub-sequence — sent to leads based on how they reply">
                          <Button
                            variant="outline"
                            size="sm"
                            className="border-violet-500/50 text-violet-300 hover:bg-violet-500/15 hover:text-violet-200 text-xs"
                            onClick={() => {
                              const defaults = INTEREST_LEVEL_DEFAULTS.any;
                              setSequenceForm({
                                name: defaults.name,
                                email_account_id: email_accounts?.[0]?.id ? String(email_accounts[0].id) : '',
                                parent_sequence_id: String(seq.id),
                                interest_level: 'any',
                                is_sub_sequence: true,
                                steps: [{ template_id: '', delay_days: 0, delay_hours: 0, delay_minutes: MIN_STEP_GAP_MINUTES }],
                              });
                              setStepErrors([]);
                              setSequenceDescription(defaults.goal);
                              setSequenceEmailCount(String(DEFAULT_SEQUENCE_EMAIL_COUNT));
                              setSequenceStepLimit(null);
                              setSequenceSlotTemplates(Array(DEFAULT_SEQUENCE_EMAIL_COUNT).fill(''));
                              setInputPanelOpen(true);
                              setExpandedStepPreviews(new Set());
                              setSubSequenceScenario('');
        setDetectedInterestLevels(null);
                              setCreateSequenceOpen(true);
                            }}
                          >
                            <Plus className="h-3 w-3 mr-1" />
                            Add Sub-Sequence
                          </Button>
                          </HoverTip>
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

      {/* View template modal — rendered preview, not raw HTML */}
      <Dialog open={viewTemplateOpen} onOpenChange={(open) => { if (!open) { setViewTemplate(null); setShowRawHtml(false); } setViewTemplateOpen(open); }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto no-scrollbar">
          <DialogHeader>
            <DialogTitle>Email template</DialogTitle>
            <DialogDescription>Preview with sample lead data — this is how the compiled email will look.</DialogDescription>
          </DialogHeader>
          {viewTemplate && (
            <div className="space-y-4 py-2">
              <div>
                <Label className="text-muted-foreground text-xs">Name</Label>
                <p className="font-medium mt-0.5">{viewTemplate.name}</p>
              </div>
              <div>
                <Label className="text-muted-foreground text-xs">Subject</Label>
                <p className="mt-0.5 break-words">{fillTemplatePreviewValues(viewTemplate.subject)}</p>
              </div>
              <div>
                <div className="flex items-center justify-between">
                  <Label className="text-muted-foreground text-xs">Preview</Label>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => setShowRawHtml((v) => !v)}
                  >
                    {showRawHtml ? 'Show preview' : 'View raw HTML'}
                  </Button>
                </div>
                {showRawHtml ? (
                  <div className="mt-1 rounded border bg-muted/20 p-3 max-h-80 overflow-y-auto no-scrollbar text-sm font-mono whitespace-pre-wrap break-words">
                    {viewTemplate.html_content || <span className="text-muted-foreground">(empty)</span>}
                  </div>
                ) : viewTemplate.html_content ? (
                  <iframe
                    title="Email preview"
                    sandbox=""
                    className="mt-1 w-full rounded border bg-white"
                    style={{ height: '360px' }}
                    srcDoc={`<!doctype html><html><head><meta charset="utf-8"><style>html{scrollbar-width:none;-ms-overflow-style:none;}::-webkit-scrollbar{display:none;width:0;height:0;}body{font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#1a1a1a;margin:16px;}</style></head><body>${fillTemplatePreviewValues(viewTemplate.html_content)}</body></html>`}
                  />
                ) : (
                  <p className="mt-1 text-sm text-muted-foreground">(empty)</p>
                )}
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
      <Dialog open={createTemplateOpen} onOpenChange={(open) => { if (!open) resetTemplateForm(); setCreateTemplateOpen(open); }}>
        <DialogContent className="max-w-4xl w-[95vw]">
          <DialogHeader>
            <DialogTitle>{editingTemplateId ? 'Edit email template' : 'Create email template'}</DialogTitle>
            <DialogDescription>
              {editingTemplateId
                ? 'Update the template. Changes apply to sequence steps using it.'
                : 'Name the template and describe what the email should say — AI generates the subject and content for you to review and edit.'}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={editingTemplateId ? handleUpdateTemplate : handleCreateTemplate}>
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 py-4">
              {/* Left: name + description + generate */}
              <div className="space-y-4 lg:col-span-2">
                <div>
                  <Label htmlFor="t-name">Name</Label>
                  <Input
                    id="t-name"
                    value={templateForm.name}
                    onChange={(e) => setTemplateForm((p) => ({ ...p, name: e.target.value }))}
                    placeholder="e.g. Welcome email"
                  />
                </div>
                <div className="rounded-lg border bg-muted/20 p-3 space-y-2">
                  <Label htmlFor="t-description">Describe what the email should say</Label>
                  <Textarea
                    id="t-description"
                    value={templateDescription}
                    onChange={(e) => setTemplateDescription(e.target.value)}
                    placeholder="e.g. Friendly welcome email introducing our product, highlight the free trial, end with a call to book a demo."
                    rows={6}
                  />
                  <div className="flex justify-end">
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={handleGenerateTemplateContent}
                      disabled={generatingTemplate}
                    >
                      {generatingTemplate ? (
                        <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Generating…</>
                      ) : (
                        <><Sparkles className="h-4 w-4 mr-2" /> Generate with AI</>
                      )}
                    </Button>
                  </div>
                </div>
              </div>

              {/* Right: AI-generated subject + body, editable */}
              <div className="space-y-4 lg:col-span-3 lg:border-l lg:pl-6">
                <div>
                  <Label htmlFor="t-subject">Subject</Label>
                  <Input
                    id="t-subject"
                    ref={templateSubjectRef}
                    value={templateForm.subject}
                    onChange={(e) => setTemplateForm((p) => ({ ...p, subject: e.target.value }))}
                    placeholder="Generated by AI, or write your own — e.g. Hello {{first_name}}"
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
                  <Label htmlFor="t-html">HTML content</Label>
                  <textarea
                    id="t-html"
                    ref={templateHtmlRef}
                    className="flex min-h-[160px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono resize-y no-scrollbar"
                    value={templateForm.html_content}
                    onChange={(e) => setTemplateForm((p) => ({ ...p, html_content: e.target.value }))}
                    placeholder="Generated by AI, or write your own — e.g. <p>Hello {{first_name}},</p><p>...</p>"
                  />
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => { resetTemplateForm(); setCreateTemplateOpen(false); }}>
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
      <Dialog
        open={createSequenceOpen}
        onOpenChange={(open) => {
          if (!open) {
            setSequenceForm((p) => ({ ...p, parent_sequence_id: '', interest_level: 'any', is_sub_sequence: false }));
            setSequenceDescription('');
            setSequenceEmailCount(String(DEFAULT_SEQUENCE_EMAIL_COUNT));
            setSequenceStepLimit(null);
            setSequenceSlotTemplates(Array(DEFAULT_SEQUENCE_EMAIL_COUNT).fill(''));
            setInputPanelOpen(true);
            setExpandedStepPreviews(new Set());
            setSubSequenceScenario('');
        setDetectedInterestLevels(null);
          }
          setCreateSequenceOpen(open);
        }}
      >
        <DialogContent className="max-w-5xl w-[95vw] max-h-[90vh] overflow-y-auto no-scrollbar">
          <DialogHeader>
            <DialogTitle>{sequenceForm.parent_sequence_id ? 'Create Sub-Sequence (Reply Triggered)' : 'Create sequence'}</DialogTitle>
            <DialogDescription>
              {sequenceForm.parent_sequence_id
                ? 'This sub-sequence starts when a lead replies to the main sequence. Choose which reply type to handle. First step: min 5 min; each step at least 5 min after the previous.'
                : 'One main sequence per campaign. Add steps with template and delay. First step: min 5 min; each step at least 5 min after the previous.'}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreateSequence}>
            <div className="grid grid-cols-1 gap-6 py-4">
              {/* Left: name, account, AI generation — collapses behind an
                  arrow once steps are generated, so the generated sequence
                  is easy to review. Reopening it shows the inputs full-width
                  again (same as before generation) and hides the steps, so
                  the two never share the row. */}
              {stepsVisible && (
                <div className="-mb-2">
                  <button
                    type="button"
                    onClick={() => setInputPanelOpen((v) => !v)}
                    className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {inputPanelOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                    {inputPanelOpen ? 'Hide inputs' : 'Show inputs'}
                  </button>
                </div>
              )}
              <div className={`space-y-4 ${stepsVisible && !inputPanelOpen ? 'hidden' : ''}`}>
                {sequenceForm.parent_sequence_id && (
                  <div className="rounded-lg border border-border bg-muted/30 p-4 space-y-3">
                    <div>
                      <p className="text-sm font-medium text-foreground">Sub-sequence</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Starts when a lead replies to the main sequence. Main sequence stops; this sequence runs per the delays below.
                      </p>
                    </div>
                    <div>
                      <Label htmlFor="sub-seq-scenario">Describe the reply this sub-sequence handles *</Label>
                      <div className="flex items-start gap-2 mt-1.5">
                        <Input
                          id="sub-seq-scenario"
                          value={subSequenceScenario}
                          onChange={(e) => {
                            setSubSequenceScenario(e.target.value);
                            if (detectedInterestLevels) setDetectedInterestLevels(null);
                          }}
                          placeholder="e.g. when the lead says they're not interested right now"
                        />
                        <Button
                          type="button"
                          variant="secondary"
                          size="sm"
                          onClick={handleClassifyInterestLevel}
                          disabled={classifyingInterestLevel}
                          className="shrink-0"
                        >
                          {classifyingInterestLevel ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <><Sparkles className="h-3.5 w-3.5 mr-1.5" /> Detect type</>
                          )}
                        </Button>
                      </div>
                      {!detectedInterestLevels && (
                        <p className="text-xs text-muted-foreground mt-1.5">
                          AI matches this to a reply type — currently: <span className="font-medium text-foreground">{INTEREST_LEVEL_OPTIONS.find((o) => o.value === (sequenceForm.interest_level || 'any'))?.label}</span>.
                          {' '}Replies are routed to the matching sub-sequence by type.
                        </p>
                      )}
                      {detectedInterestLevels && (
                        <div className="mt-2 rounded-md border border-border bg-background p-3 space-y-2">
                          <p className="text-xs text-foreground">
                            Your description names multiple reply types — a sub-sequence can only handle one, so create them separately:
                            {' '}
                            <span className="font-medium">
                              {detectedInterestLevels.map((l) => INTEREST_LEVEL_OPTIONS.find((o) => o.value === l)?.label || l).join(', ')}
                            </span>
                          </p>
                          <div className="flex justify-end">
                            <Button
                              type="button"
                              variant="default"
                              size="sm"
                              onClick={handleCreateMultipleSubSequences}
                              disabled={creatingMultiSequences}
                            >
                              {creatingMultiSequences ? (
                                <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Creating sub-sequences…</>
                              ) : (
                                <><Sparkles className="h-4 w-4 mr-2" /> Create sub-sequences</>
                              )}
                            </Button>
                          </div>
                          <p className="text-xs text-muted-foreground">
                            Each gets one AI-generated email using the "Send from" setting below.
                          </p>
                        </div>
                      )}
                      <details className="mt-1.5">
                        <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground w-fit">Or pick the reply type manually</summary>
                        <Select
                          value={sequenceForm.interest_level || 'any'}
                          onValueChange={(v) => {
                            const defaults = INTEREST_LEVEL_DEFAULTS[v] || INTEREST_LEVEL_DEFAULTS.any;
                            setSequenceForm((p) => ({ ...p, interest_level: v, name: defaults.name }));
                            setSequenceDescription(defaults.goal);
                            setDetectedInterestLevels(null);
                          }}
                        >
                          <SelectTrigger className="mt-2">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {INTEREST_LEVEL_OPTIONS.map((o) => (
                              <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </details>
                    </div>
                  </div>
                )}
                {!sequenceForm.parent_sequence_id && (
                  <div>
                    <Label>Sequence name</Label>
                    <Input
                      value={sequenceForm.name}
                      onChange={(e) => setSequenceForm((p) => ({ ...p, name: e.target.value }))}
                      placeholder="e.g. Main follow-up sequence"
                    />
                  </div>
                )}
                <div className={sequenceForm.parent_sequence_id ? '' : 'grid grid-cols-2 gap-3'}>
                  {!sequenceForm.parent_sequence_id && (
                    <div>
                      <Label htmlFor="seq-email-count">Number of emails</Label>
                      <Input
                        id="seq-email-count"
                        type="number"
                        min={1}
                        max={10}
                        value={sequenceEmailCount}
                        onChange={(e) => {
                          const raw = e.target.value;
                          if (raw === '') { setSequenceEmailCount(raw); return; }
                          const n = parseInt(raw, 10);
                          if (Number.isFinite(n)) setSequenceEmailCount(String(Math.min(10, Math.max(1, n))));
                        }}
                      />
                    </div>
                  )}
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
                        <SelectItem value="__none__">
                          {campaign?.email_account_email
                            ? `Use campaign default (${campaign.email_account_email})`
                            : 'No account'}
                        </SelectItem>
                        {email_accounts.map((a) => (
                          <SelectItem key={a.id} value={String(a.id)}>
                            {a.email} {a.is_default ? '(default)' : ''}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                {!sequenceForm.parent_sequence_id && (
                  <div className="rounded-lg border bg-muted/20 p-3 space-y-3">
                    <div>
                      <Label htmlFor="seq-description">Sequence goal (optional — for AI generation)</Label>
                      <Textarea
                        id="seq-description"
                        value={sequenceDescription}
                        onChange={(e) => setSequenceDescription(e.target.value)}
                        placeholder="e.g. Onboarding follow-up encouraging new users to complete setup and book a demo."
                        rows={4}
                      />
                    </div>


                    {templates.length > 0 && (
                      <div className="space-y-1.5">
                        <Label className="text-xs">For each email, use an existing template or let AI write a new one</Label>
                        {sequenceSlotTemplates.map((slotValue, i) => (
                          <div key={i} className="flex items-center gap-2">
                            <span className="text-xs text-muted-foreground w-14 shrink-0">Email {i + 1}</span>
                            <Select
                              value={slotValue || '__generate_new__'}
                              onValueChange={(v) =>
                                setSequenceSlotTemplates((prev) =>
                                  prev.map((s, idx) => (idx === i ? (v === '__generate_new__' ? '' : v) : s))
                                )
                              }
                            >
                              <SelectTrigger className="h-8 text-xs">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="__generate_new__">✨ Generate new with AI</SelectItem>
                                {templates.map((t) => (
                                  <SelectItem key={t.id} value={String(t.id)}>{t.name}</SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                        ))}
                      </div>
                    )}

                    <div className="flex justify-end">
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={() => handleGenerateSequence({ mode: 'replace' })}
                        disabled={generatingSequence}
                      >
                        {generatingSequence ? (
                          <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Generating…</>
                        ) : sequenceSlotTemplates.every((s) => s) ? (
                          'Use selected templates'
                        ) : sequenceStepLimit != null ? (
                          <><Sparkles className="h-4 w-4 mr-2" /> Re-generate with AI</>
                        ) : (
                          <><Sparkles className="h-4 w-4 mr-2" /> Generate with AI</>
                        )}
                      </Button>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      For any email left on "Generate new", AI writes and saves a template, then assembles the steps with standard spacing. Review and edit before creating.
                    </p>
                  </div>
                )}

                {/* Sub-sequence: minimal — no name or goal input, both are
                    auto-derived from the interest level picked above. Just
                    confirm the count and generate. Hidden while a multi-type
                    detection is pending — "Create N sub-sequences" above is
                    the CTA in that case. */}
                {sequenceForm.parent_sequence_id && !detectedInterestLevels && (
                  <div className="space-y-2">
                    <div className="flex justify-end">
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={async () => {
                          // Classify first if the user typed a scenario but never
                          // clicked "Detect type" — one click does both steps.
                          if (subSequenceScenario.trim() && sequenceForm.interest_level === 'any') {
                            const level = await handleClassifyInterestLevel();
                            if (!level) return;
                          }
                          handleGenerateSequence({ mode: 'replace' });
                        }}
                        disabled={generatingSequence || classifyingInterestLevel}
                      >
                        {generatingSequence || classifyingInterestLevel ? (
                          <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> {classifyingInterestLevel ? 'Detecting type…' : 'Generating…'}</>
                        ) : sequenceStepLimit != null ? (
                          <><Sparkles className="h-4 w-4 mr-2" /> Re-generate with AI</>
                        ) : (
                          <><Sparkles className="h-4 w-4 mr-2" /> Generate with AI</>
                        )}
                      </Button>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      AI writes and saves one email — tailored to the reply type above. Review and edit before creating.
                    </p>
                  </div>
                )}
              </div>

              {/* Steps list — absent for a fresh main sequence until AI has
                  generated them, and hidden again whenever the input panel is
                  reopened via "Show inputs" (the two are never shown together,
                  each takes the full width in turn). */}
              {stepsVisible && !inputPanelOpen && (
                <div className="space-y-2">
                    <div className="flex items-center justify-between mb-2">
                      <Label>Steps</Label>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={addStep}
                        disabled={sequenceStepLimit != null && sequenceForm.steps.length >= sequenceStepLimit}
                        title={sequenceStepLimit != null && sequenceForm.steps.length >= sequenceStepLimit ? `Limited to ${sequenceStepLimit} emails (as generated).` : ''}
                      >
                        Add step
                      </Button>
                    </div>
                    <p className="text-xs text-muted-foreground mb-2">First step: min 5 min total. Each step: at least 5 min after the previous.</p>
                    <div className="max-h-[480px] overflow-y-auto no-scrollbar pr-1 space-y-3">
                      {sequenceForm.steps.map((step, idx) => {
                        const stepTemplate = templates.find((t) => String(t.id) === String(step.template_id));
                        const isExpanded = expandedStepPreviews.has(idx);
                        const toggleExpanded = () =>
                          setExpandedStepPreviews((prev) => {
                            const next = new Set(prev);
                            if (next.has(idx)) next.delete(idx);
                            else next.add(idx);
                            return next;
                          });
                        return (
                        <div key={idx} className="p-3 rounded border bg-muted/20">
                          <div className="flex items-end gap-2">
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center justify-between gap-2">
                                <Label className="text-xs">Template</Label>
                                {stepTemplate && (
                                  <button
                                    type="button"
                                    onClick={toggleExpanded}
                                    className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                                  >
                                    {isExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                                    {isExpanded ? 'Hide' : 'Show'} content
                                  </button>
                                )}
                              </div>
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
                            <div className="w-14 shrink-0">
                              <Label className="text-xs">Days</Label>
                              <Input
                                type="number"
                                min={0}
                                value={step.delay_days}
                                onChange={(e) => updateStep(idx, 'delay_days', parseInt(e.target.value, 10) || 0)}
                              />
                            </div>
                            <div className="w-14 shrink-0">
                              <Label className="text-xs">Hours</Label>
                              <Input
                                type="number"
                                min={0}
                                value={step.delay_hours}
                                onChange={(e) => updateStep(idx, 'delay_hours', parseInt(e.target.value, 10) || 0)}
                              />
                            </div>
                            <div className="w-16 shrink-0">
                              <Label className="text-xs">Mins (≥5)</Label>
                              <Input
                                type="number"
                                min={0}
                                value={step.delay_minutes}
                                onChange={(e) => updateStep(idx, 'delay_minutes', parseInt(e.target.value, 10) || 0)}
                              />
                            </div>
                            <div className="shrink-0">
                              <Button type="button" variant="destructive" size="sm" onClick={() => removeStep(idx)} disabled={sequenceForm.steps.length <= 1}>
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          </div>
                          {stepErrors[idx] && (
                            <p className="text-xs text-destructive mt-1" role="alert">{stepErrors[idx]}</p>
                          )}
                          {isExpanded && stepTemplate && (
                            <div className="mt-2 pt-2 border-t border-border text-xs space-y-1">
                              <p><span className="text-muted-foreground">Subject:</span> {stepTemplate.subject}</p>
                              <div className="rounded bg-background/50 p-2 max-h-32 overflow-y-auto no-scrollbar font-mono whitespace-pre-wrap break-words text-muted-foreground">
                                {stepTemplate.html_content || '(empty)'}
                              </div>
                            </div>
                          )}
                        </div>
                        );
                      })}
                    </div>
                </div>
              )}
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setSequenceForm((p) => ({ ...p, parent_sequence_id: '', interest_level: 'any', is_sub_sequence: false }));
                  setSequenceDescription('');
                  setSequenceEmailCount(String(DEFAULT_SEQUENCE_EMAIL_COUNT));
                  setSequenceStepLimit(null);
                  setSequenceSlotTemplates(Array(DEFAULT_SEQUENCE_EMAIL_COUNT).fill(''));
                  setInputPanelOpen(true);
                  setExpandedStepPreviews(new Set());
                  setSubSequenceScenario('');
        setDetectedInterestLevels(null);
                  setCreateSequenceOpen(false);
                }}
              >
                Cancel
              </Button>
              {!(sequenceForm.parent_sequence_id && (detectedInterestLevels?.length > 1 || !subSequenceScenario.trim())) && (
                <Button type="submit" disabled={actionLoading}>
                  {actionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : (sequenceForm.parent_sequence_id ? 'Create sub-sequence' : 'Create sequence')}
                </Button>
              )}
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit sequence modal */}
      <Dialog
        open={editSequenceOpen}
        onOpenChange={(open) => {
          if (!open) { setEditingSequenceId(null); setEditInputPanelOpen(false); }
          setEditSequenceOpen(open);
        }}
      >
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
              {/* Inputs vs. steps toggle — same collapse pattern as Create
                  sequence: only one of the two shows at a time, full width. */}
              <button
                type="button"
                onClick={() => setEditInputPanelOpen((v) => !v)}
                className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                {editInputPanelOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                {editInputPanelOpen ? 'Hide inputs' : 'Show inputs'}
              </button>

              <div className={editInputPanelOpen ? 'space-y-4' : 'hidden'}>
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
                {sequenceForm.is_sub_sequence && (
                  <div className="rounded-lg border bg-muted/20 p-3 space-y-3">
                    <div>
                      <Label htmlFor="edit-sub-seq-description">Describe the reply this sub-sequence handles (optional — for AI generation)</Label>
                      <Textarea
                        id="edit-sub-seq-description"
                        value={sequenceDescription}
                        onChange={(e) => setSequenceDescription(e.target.value)}
                        placeholder="e.g. when the lead says they're not interested right now"
                        rows={4}
                      />
                    </div>
                    <div className="flex justify-end">
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={() => handleGenerateSequence({ mode: 'replace' })}
                        disabled={generatingSequence}
                      >
                        {generatingSequence ? (
                          <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Generating…</>
                        ) : (
                          <><Sparkles className="h-4 w-4 mr-2" /> Generate with AI</>
                        )}
                      </Button>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Replaces this sub-sequence's single email. Review and edit before saving.
                    </p>
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
                      <SelectItem value="__none__">
                        {campaign?.email_account_email
                          ? `Use campaign default (${campaign.email_account_email})`
                          : 'No account'}
                      </SelectItem>
                      {email_accounts.map((a) => (
                        <SelectItem key={a.id} value={String(a.id)}>{a.email}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {!sequenceForm.is_sub_sequence && (
                  <div className="rounded-lg border bg-muted/20 p-3 space-y-3">
                    <div>
                      <Label htmlFor="edit-seq-description">Sequence goal (optional — for AI generation)</Label>
                      <Textarea
                        id="edit-seq-description"
                        value={sequenceDescription}
                        onChange={(e) => setSequenceDescription(e.target.value)}
                        placeholder="e.g. Onboarding follow-up encouraging new users to complete setup and book a demo."
                        rows={4}
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <Label htmlFor="edit-seq-email-count">Number of new emails</Label>
                        <Input
                          id="edit-seq-email-count"
                          type="number"
                          min={1}
                          max={10}
                          value={sequenceEmailCount}
                          onChange={(e) => {
                            const raw = e.target.value;
                            if (raw === '') { setSequenceEmailCount(raw); return; }
                            const n = parseInt(raw, 10);
                            if (Number.isFinite(n)) setSequenceEmailCount(String(Math.min(10, Math.max(1, n))));
                          }}
                        />
                      </div>
                      <div>
                        <Label htmlFor="edit-seq-mode">Add or replace</Label>
                        <Select value={editGenerateMode} onValueChange={setEditGenerateMode}>
                          <SelectTrigger id="edit-seq-mode">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="append">Add after existing steps</SelectItem>
                            <SelectItem value="replace">Replace existing steps</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>

                    <div className="flex justify-end">
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={() => handleGenerateSequence({ mode: editGenerateMode })}
                        disabled={generatingSequence}
                      >
                        {generatingSequence ? (
                          <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Generating…</>
                        ) : (
                          <><Sparkles className="h-4 w-4 mr-2" /> Generate with AI</>
                        )}
                      </Button>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      AI writes and saves a new template for each email, then assembles the steps with standard spacing. Review and edit before saving.
                    </p>
                  </div>
                )}
              </div>

              <div className={editInputPanelOpen ? 'hidden' : ''}>
                <div className="flex items-center justify-between mb-2">
                  <Label>Steps</Label>
                  <Button type="button" variant="outline" size="sm" onClick={addStep}>
                    Add step
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground mb-2">First step: min 5 min total. Each step: at least 5 min after the previous.</p>
                {sequenceForm.steps.map((step, idx) => (
                  <div key={idx} className="flex items-end gap-2 mb-3 p-3 rounded border bg-muted/20">
                    <div className="min-w-0 flex-1">
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
                    <div className="w-14 shrink-0">
                      <Label className="text-xs">Days</Label>
                      <Input
                        type="number"
                        min={0}
                        value={step.delay_days}
                        onChange={(e) => updateStep(idx, 'delay_days', parseInt(e.target.value, 10) || 0)}
                      />
                    </div>
                    <div className="w-14 shrink-0">
                      <Label className="text-xs">Hours</Label>
                      <Input
                        type="number"
                        min={0}
                        value={step.delay_hours}
                        onChange={(e) => updateStep(idx, 'delay_hours', parseInt(e.target.value, 10) || 0)}
                      />
                    </div>
                    <div className="w-16 shrink-0">
                      <Label className="text-xs">Mins (≥5)</Label>
                      <Input
                        type="number"
                        min={0}
                        value={step.delay_minutes}
                        onChange={(e) => updateStep(idx, 'delay_minutes', parseInt(e.target.value, 10) || 0)}
                      />
                    </div>
                    <div className="shrink-0">
                      <Button type="button" variant="destructive" size="sm" onClick={() => removeStep(idx)} disabled={sequenceForm.steps.length <= 1}>
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
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setEditingSequenceId(null);
                  setEditInputPanelOpen(false);
                  setEditSequenceOpen(false);
                }}
              >
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

      {/* No email accounts — prompt to add one. Dismissable ("Not now"): the tab
          itself then shows a persistent banner (see below) so the user isn't stuck. */}
      <Dialog
        open={noEmailAccountDialogOpen}
        onOpenChange={setNoEmailAccountDialogOpen}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-amber-500" />
              Add an email account first
            </DialogTitle>
            <DialogDescription>
              This campaign has no sender email accounts yet. Add one before creating email
              templates or sequences — sends need an account to go out from.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setNoEmailAccountDialogOpen(false)}>
              Not now
            </Button>
            <Button onClick={() => setAddEmailAccountOpen(true)}>
              <Mail className="mr-2 h-4 w-4" />
              Add email account
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AddEmailAccountModal
        open={addEmailAccountOpen}
        onOpenChange={setAddEmailAccountOpen}
        onCreated={() => {
          setNoEmailAccountDialogOpen(false);
          fetchData();
        }}
      />

      {/* Upload leads modal */}
      <Dialog open={uploadLeadsOpen} onOpenChange={setUploadLeadsOpen}>
        <DialogContent className="max-w-5xl w-[95vw] max-h-[90vh] overflow-y-auto no-scrollbar">
          <DialogHeader>
            <DialogTitle>Upload leads</DialogTitle>
            <DialogDescription>
              Upload a CSV or Excel file. Match the column headers below — names are
              case-insensitive and a single space is treated the same as an underscore
              (so both <code className="font-mono text-[11px] bg-muted px-1 rounded">first_name</code>
              {' '}and <code className="font-mono text-[11px] bg-muted px-1 rounded">First Name</code> work).
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <LeadsUploadFields />
            <div>
              <Label>File (CSV, XLSX, XLS)</Label>
              <Input
                type="file"
                accept=".csv,.xlsx,.xls"
                onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                className="mt-1"
              />
              {uploadFile && (
                <p className="mt-1.5 text-xs text-muted-foreground">
                  Selected: <span className="font-medium text-foreground">{uploadFile.name}</span>
                </p>
              )}
            </div>
            {uploadMessage && <p className="text-sm text-destructive">{uploadMessage}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setUploadLeadsOpen(false)}>Cancel</Button>
            <Button onClick={handleUploadLeads} disabled={uploadLoading}>
              {uploadLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Upload
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default SequenceManagementPage;
