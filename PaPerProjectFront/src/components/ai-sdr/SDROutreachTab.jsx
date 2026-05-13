import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Mail, Linkedin, Plus, RefreshCw, Trash2, Users, ChevronLeft,
  Zap, Check, Loader2, Send, MessageSquare, Calendar, Edit2,
  Flame, Thermometer, Snowflake, Clock, Inbox, Pause, Play,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import {
  listCampaigns, createCampaign, deleteCampaign, updateCampaign,
  getCampaignDetail, getCampaignSteps, generateSequenceSteps,
  getCampaignContacts, enrollLeads, updateCampaignStep, listLeads,
  clearCampaignLeads,
} from '@/services/aiSdrService';

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------
const cardStyle = {
  background: 'linear-gradient(135deg, rgba(15,10,31,0.95) 0%, rgba(20,8,40,0.95) 100%)',
  border: '1px solid #2d1f4a', borderRadius: 12,
};
const inputStyle = {
  background: 'rgba(30,10,50,0.6)', border: '1px solid #2d1f4a',
  borderRadius: 8, padding: '8px 12px', color: '#e2d9f3',
  outline: 'none', fontSize: 14, width: '100%', boxSizing: 'border-box',
};
const labelStyle = { color: '#9ca3af', fontSize: 12, display: 'block', marginBottom: 4 };

const STATUS_COLORS = {
  draft:     { color: '#6b7280', bg: 'rgba(107,114,128,0.12)', border: 'rgba(107,114,128,0.3)', label: 'Draft' },
  scheduled: { color: '#60a5fa', bg: 'rgba(96,165,250,0.12)',  border: 'rgba(96,165,250,0.3)',  label: 'Scheduled' },
  active:    { color: '#10b981', bg: 'rgba(16,185,129,0.12)', border: 'rgba(16,185,129,0.3)',  label: 'Active' },
  paused:    { color: '#f59e0b', bg: 'rgba(245,158,11,0.12)', border: 'rgba(245,158,11,0.3)',  label: 'Paused' },
  completed: { color: '#a855f7', bg: 'rgba(168,85,247,0.12)', border: 'rgba(168,85,247,0.3)',  label: 'Completed' },
};
const ENROLL_STATUS = {
  active:       { color: '#60a5fa', label: 'Active' },
  replied:      { color: '#10b981', label: 'Replied' },
  completed:    { color: '#a855f7', label: 'Completed' },
  paused:       { color: '#f59e0b', label: 'Paused' },
  unsubscribed: { color: '#6b7280', label: 'Unsubscribed' },
  bounced:      { color: '#f43f5e', label: 'Bounced' },
};
const TEMP_ICON = { hot: Flame, warm: Thermometer, cold: Snowflake };
const TEMP_COLOR = { hot: '#f43f5e', warm: '#f59e0b', cold: '#60a5fa' };

const BLANK_CAMPAIGN = {
  name: '', description: '',
  sender_name: '', sender_title: '', sender_company: '',
  from_email: '', smtp_host: '', smtp_port: 587,
  smtp_username: '', smtp_password: '', smtp_use_tls: true,
  start_date: '', calendar_link: '',
  auto_check_replies: true,
  generate_steps: true,
};

// SMTP + IMAP provider presets
const SMTP_PROVIDERS = [
  { key: 'gmail',     label: 'Gmail',         smtp_host: 'smtp.gmail.com',     smtp_port: 587, smtp_use_tls: true, imap_host: 'imap.gmail.com',     imap_port: 993 },
  { key: 'hostinger', label: 'Hostinger',      smtp_host: 'smtp.hostinger.com', smtp_port: 587, smtp_use_tls: true, imap_host: 'imap.hostinger.com', imap_port: 993 },
  { key: 'custom',    label: 'Custom / Other', smtp_host: '',                   smtp_port: 587, smtp_use_tls: true, imap_host: '',                   imap_port: 993 },
];

const detectProvider = (host) => {
  if (!host) return '';
  if (host.includes('gmail'))     return 'gmail';
  if (host.includes('hostinger')) return 'hostinger';
  return 'custom';
};

const applySmtpProvider = (key, setter) => {
  const p = SMTP_PROVIDERS.find(x => x.key === key);
  if (!p) return;
  setter(prev => ({
    ...prev,
    smtp_host: p.smtp_host, smtp_port: p.smtp_port, smtp_use_tls: p.smtp_use_tls,
    imap_host: p.imap_host, imap_port: p.imap_port,
  }));
};

// Helper: today in YYYY-MM-DD (for date input min)
const todayStr = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

// Helper: add N days to a YYYY-MM-DD string
const addDays = (iso, days) => {
  if (!iso) return '';
  const d = new Date(iso);
  d.setDate(d.getDate() + days);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
};

const fmtDate = (iso) => {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
};

const fmtCountdown = (iso, now) => {
  if (!iso) return null;
  const diff = new Date(iso) - now;
  if (diff <= 0) return { label: 'sending soon', color: '#10b981' };
  const m = Math.floor(diff / 60000);
  const h = Math.floor(m / 60);
  const d = Math.floor(h / 24);
  if (d > 0) return { label: `in ${d}d ${h % 24}h`, color: '#6b7280' };
  if (h > 0) return { label: `in ${h}h ${m % 60}m`, color: '#f59e0b' };
  return { label: `in ${m}m`, color: '#10b981' };
};

// --------------------------------------------------------------------------
// Step type icon
// --------------------------------------------------------------------------
const StepIcon = ({ type, size = 16 }) =>
  type === 'email'
    ? <Mail size={size} style={{ color: '#a855f7' }} />
    : <Linkedin size={size} style={{ color: '#60a5fa' }} />;

// --------------------------------------------------------------------------
// Step timeline item
// --------------------------------------------------------------------------
const StepCard = ({ step, onEdit, onDelete, isLast }) => (
  <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
    {/* Day bubble + connector */}
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0 }}>
      <div style={{
        width: 44, height: 44, borderRadius: '50%', display: 'flex', alignItems: 'center',
        justifyContent: 'center', flexDirection: 'column',
        background: step.step_type === 'email' ? 'rgba(168,85,247,0.15)' : 'rgba(96,165,250,0.15)',
        border: `2px solid ${step.step_type === 'email' ? 'rgba(168,85,247,0.4)' : 'rgba(96,165,250,0.4)'}`,
      }}>
        <span style={{ color: '#9ca3af', fontSize: 9, lineHeight: 1 }}>Day</span>
        <span style={{ fontWeight: 700, fontSize: 14, color: step.step_type === 'email' ? '#c084fc' : '#93c5fd' }}>
          {step.delay_days}
        </span>
      </div>
      {!isLast && <div style={{ width: 2, height: 28, background: 'rgba(45,31,74,0.8)', margin: '4px 0' }} />}
    </div>

    {/* Step content */}
    <div style={{
      flex: 1, ...cardStyle, padding: '12px 14px', marginBottom: isLast ? 0 : 8,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <StepIcon type={step.step_type} />
          <div>
            <span style={{ color: '#e2d9f3', fontWeight: 600, fontSize: 13 }}>{step.name || `Step ${step.step_order}`}</span>
            <span style={{ color: '#4b5563', fontSize: 11, marginLeft: 8 }}>
              {step.step_type === 'email' ? 'Email' : 'LinkedIn'}
            </span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {onEdit && (
            <button onClick={() => onEdit(step)} style={{
              background: 'none', border: '1px solid #2d1f4a', borderRadius: 6,
              padding: '3px 7px', cursor: 'pointer', color: '#6b7280',
            }}>
              <Edit2 size={11} />
            </button>
          )}
          {onDelete && (
            <button onClick={() => onDelete(step.id)} style={{
              background: 'none', border: '1px solid rgba(244,63,94,0.2)', borderRadius: 6,
              padding: '3px 7px', cursor: 'pointer', color: '#f87171',
            }}>
              <Trash2 size={11} />
            </button>
          )}
        </div>
      </div>
      {step.subject_template && (
        <div style={{ marginTop: 6, color: '#6b7280', fontSize: 12 }}>
          <span style={{ color: '#4b5563' }}>Subject: </span>{step.subject_template.slice(0, 70)}{step.subject_template.length > 70 ? '…' : ''}
        </div>
      )}
      {step.body_template && (
        <div style={{ marginTop: 4, color: '#4b5563', fontSize: 11, lineHeight: 1.5 }}>
          {step.body_template.slice(0, 100)}{step.body_template.length > 100 ? '…' : ''}
        </div>
      )}
    </div>
  </div>
);

// --------------------------------------------------------------------------
// Lead variable definitions
// --------------------------------------------------------------------------
const LEAD_VARS = [
  { label: 'First Name',        token: '{first_name}' },
  { label: 'Last Name',         token: '{last_name}' },
  { label: 'Full Name',         token: '{full_name}' },
  { label: 'Job Title',         token: '{job_title}' },
  { label: 'Seniority',         token: '{seniority_level}' },
  { label: 'Department',        token: '{department}' },
  { label: 'Company',           token: '{company_name}' },
  { label: 'Industry',          token: '{company_industry}' },
  { label: 'Company Size',      token: '{company_size}' },
  { label: 'Location',          token: '{company_location}' },
  { label: 'Website',           token: '{company_website}' },
  { label: 'LinkedIn',          token: '{linkedin_url}' },
  { label: 'Company LinkedIn',  token: '{company_linkedin_url}' },
  { label: 'Email',             token: '{email}' },
  { label: 'Phone',             token: '{phone}' },
];

// --------------------------------------------------------------------------
// EditStepModal — edit a campaign step with an inline variable picker
// --------------------------------------------------------------------------
const EditStepModal = ({ step, onChange, onSave, onClose, saving }) => {
  const subjectRef = useRef(null);
  const bodyRef    = useRef(null);
  // track which field was last focused so variable inserts go to the right place
  const focusedRef = useRef('body');

  const insertToken = (token) => {
    const field = focusedRef.current;
    const ref   = field === 'subject' ? subjectRef : bodyRef;
    const el    = ref.current;
    if (!el) return;

    const start = el.selectionStart ?? el.value.length;
    const end   = el.selectionEnd   ?? el.value.length;
    const cur   = field === 'subject' ? (step.subject_template || '') : (step.body_template || '');
    const next  = cur.slice(0, start) + token + cur.slice(end);

    if (field === 'subject') {
      onChange(p => ({ ...p, subject_template: next }));
    } else {
      onChange(p => ({ ...p, body_template: next }));
    }

    // restore focus + move cursor after token
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(start + token.length, start + token.length);
    });
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent style={{
        background: 'linear-gradient(135deg,#0f0a1f 0%,#14082a 100%)',
        border: '1px solid #2d1f4a', color: '#e2d9f3', maxWidth: 620, maxHeight: '92vh', overflowY: 'auto',
      }}>
        <DialogHeader>
          <DialogTitle style={{ color: '#e2d9f3' }}>Edit Step {step.step_order}</DialogTitle>
        </DialogHeader>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Basic fields */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
            <div>
              <label style={labelStyle}>Step Name</label>
              <input value={step.name} onChange={e => onChange(p => ({ ...p, name: e.target.value }))} style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>Type</label>
              <select value={step.step_type} onChange={e => onChange(p => ({ ...p, step_type: e.target.value }))} style={inputStyle}>
                <option value="email">Email</option>
                <option value="linkedin">LinkedIn</option>
              </select>
            </div>
            <div>
              <label style={labelStyle}>Day (from start)</label>
              <input type="number" min={1} value={step.delay_days}
                onChange={e => onChange(p => ({ ...p, delay_days: parseInt(e.target.value) || 1 }))}
                style={inputStyle} />
            </div>
          </div>

          {/* Variable picker */}
          <div style={{
            padding: '10px 12px', borderRadius: 8,
            background: 'rgba(168,85,247,0.06)', border: '1px solid rgba(168,85,247,0.2)',
          }}>
            <p style={{ color: '#a855f7', fontSize: 11, fontWeight: 600, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Insert Lead Variable — click to insert at cursor
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {LEAD_VARS.map(({ label, token }) => (
                <button key={token} onClick={() => insertToken(token)} style={{
                  background: 'rgba(168,85,247,0.12)', border: '1px solid rgba(168,85,247,0.35)',
                  borderRadius: 6, padding: '3px 9px', cursor: 'pointer', color: '#c084fc',
                  fontSize: 11, fontWeight: 500, fontFamily: 'monospace',
                  transition: 'background 0.15s',
                }}
                  onMouseEnter={e => e.currentTarget.style.background = 'rgba(168,85,247,0.25)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'rgba(168,85,247,0.12)'}
                  title={`Inserts ${token}`}
                >
                  {token}
                  <span style={{ color: '#6b7280', fontFamily: 'sans-serif', fontWeight: 400, marginLeft: 4, fontSize: 10 }}>
                    {label}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Subject — only for email */}
          {step.step_type === 'email' && (
            <div>
              <label style={labelStyle}>Subject Template</label>
              <input
                ref={subjectRef}
                value={step.subject_template || ''}
                onChange={e => onChange(p => ({ ...p, subject_template: e.target.value }))}
                onFocus={() => { focusedRef.current = 'subject'; }}
                placeholder="e.g. Quick question for {first_name} at {company_name}"
                style={inputStyle}
              />
            </div>
          )}

          {/* Body */}
          <div>
            <label style={labelStyle}>Body Template</label>
            <textarea
              ref={bodyRef}
              value={step.body_template || ''}
              onChange={e => onChange(p => ({ ...p, body_template: e.target.value }))}
              onFocus={() => { focusedRef.current = 'body'; }}
              placeholder={`Hi {first_name},\n\nI noticed {company_name} is in the {company_industry} space...\n\nBest,\n{sender_name}`}
              style={{ ...inputStyle, minHeight: 180, resize: 'vertical', fontFamily: 'inherit', lineHeight: 1.6 }}
            />
          </div>

          {/* AI personalisation */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', borderRadius: 8, background: 'rgba(168,85,247,0.04)', border: '1px solid rgba(168,85,247,0.15)' }}>
            <input type="checkbox" id="ai_p" checked={step.ai_personalize}
              onChange={e => onChange(p => ({ ...p, ai_personalize: e.target.checked }))} />
            <label htmlFor="ai_p" style={{ color: '#9ca3af', fontSize: 13, cursor: 'pointer' }}>
              <Zap size={11} style={{ display: 'inline', marginRight: 4, color: '#c084fc' }} />
              AI personalises this step using lead signals (buying signals, recent news, etc.)
            </label>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} style={{ border: '1px solid #2d1f4a', color: '#9ca3af', borderRadius: 8 }}>Cancel</Button>
          <Button onClick={onSave} disabled={saving} style={{
            background: 'linear-gradient(90deg,#7c3aed,#a855f7)', color: '#fff',
            border: 'none', borderRadius: 8, fontWeight: 600,
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            {saving ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
            Save Step
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

// --------------------------------------------------------------------------
// Main component
// --------------------------------------------------------------------------
const SDROutreachTab = () => {
  const { toast } = useToast();

  // ── State ──────────────────────────────────────────────────────────────
  const [campaigns, setCampaigns] = useState([]);
  const [selectedCampaign, setSelectedCampaign] = useState(null);
  const [steps, setSteps] = useState([]);
  const [enrollments, setEnrollments] = useState([]);
  const [leads, setLeads] = useState([]);   // all leads for enroll modal

  const [loading, setLoading] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [generatingSteps, setGeneratingSteps] = useState(false);

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEnrollModal, setShowEnrollModal] = useState(false);
  const [showEditStepModal, setShowEditStepModal] = useState(false);
  const [showSmtpSection, setShowSmtpSection] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [settingsDraft, setSettingsDraft] = useState(null);
  const [savingSettings, setSavingSettings] = useState(false);

  const [newCampaign, setNewCampaign] = useState(BLANK_CAMPAIGN);
  const [creating, setCreating] = useState(false);
  const [selectedLeadIds, setSelectedLeadIds] = useState([]);
  const [enrolling, setEnrolling] = useState(false);
  const [editingStep, setEditingStep] = useState(null);
  const [savingStep, setSavingStep] = useState(false);
  const [viewReplyModal, setViewReplyModal] = useState(null); // view existing reply
  const [pausingCampaign, setPausingCampaign] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);   // campaign obj to delete
  const [clearLeadsConfirm, setClearLeadsConfirm] = useState(false);
  const [clearingLeads, setClearingLeads] = useState(false);
  const [now, setNow] = useState(new Date());

  // Tick every 30 s so countdown timers stay live
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30000);
    return () => clearInterval(id);
  }, []);

  // ── Loaders ────────────────────────────────────────────────────────────
  const loadCampaigns = useCallback(async () => {
    try {
      const resp = await listCampaigns();
      setCampaigns(resp.data || []);
    } catch (e) { console.error(e); }
  }, []);

  const loadDetail = useCallback(async (campaign) => {
    setLoadingDetail(true);
    try {
      const [detailResp, stepsResp, enrollResp] = await Promise.all([
        getCampaignDetail(campaign.id),
        getCampaignSteps(campaign.id),
        getCampaignContacts(campaign.id),
      ]);
      setSelectedCampaign(detailResp.data);
      setSteps(stepsResp.data || []);
      setEnrollments(enrollResp.data || []);
    } catch (e) {
      toast({ title: 'Load failed', description: e.message, variant: 'destructive' });
    } finally { setLoadingDetail(false); }
  }, []);

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await loadCampaigns();
      setLoading(false);
    };
    init();
  }, []);

  // Silent background refresh when viewing a campaign — picks up scheduler changes without page reload
  useEffect(() => {
    if (!selectedCampaign) return;
    const refresh = async () => {
      try {
        const [detailResp, enrollResp] = await Promise.all([
          getCampaignDetail(selectedCampaign.id),
          getCampaignContacts(selectedCampaign.id),
        ]);
        setSelectedCampaign(detailResp.data);
        setEnrollments(enrollResp.data || []);
      } catch (_) {}
    };
    const id = setInterval(refresh, 30000);   // every 30 s
    return () => clearInterval(id);
  }, [selectedCampaign?.id]);

  // ── Create campaign ────────────────────────────────────────────────────
  const handleCreate = async () => {
    if (!newCampaign.name.trim()) {
      toast({ title: 'Campaign name is required', variant: 'destructive' }); return;
    }
    setCreating(true);
    try {
      const resp = await createCampaign(newCampaign);
      toast({ title: 'Campaign created', description: resp.data?.name });
      setShowCreateModal(false);
      setNewCampaign(BLANK_CAMPAIGN);
      setShowSmtpSection(false);
      await loadCampaigns();
      // Open the new campaign detail
      await loadDetail(resp.data);
    } catch (e) {
      toast({ title: 'Create failed', description: e.message, variant: 'destructive' });
    } finally { setCreating(false); }
  };

  // ── Delete campaign (with confirmation) ───────────────────────────────
  const handleDeleteCampaign = async () => {
    if (!deleteConfirm) return;
    const id = deleteConfirm.id;
    setDeleteConfirm(null);
    try {
      await deleteCampaign(id);
      toast({ title: 'Campaign deleted' });
      if (selectedCampaign?.id === id) setSelectedCampaign(null);
      await loadCampaigns();
    } catch (e) {
      toast({ title: 'Delete failed', description: e.message, variant: 'destructive' });
    }
  };

  // ── Clear all leads from campaign ────────────────────────────────────
  const handleClearLeads = async () => {
    if (!selectedCampaign) return;
    setClearingLeads(true);
    setClearLeadsConfirm(false);
    try {
      const resp = await clearCampaignLeads(selectedCampaign.id);
      setSelectedCampaign(resp.data.data);
      setEnrollments([]);
      await loadCampaigns();
      toast({ title: 'All leads cleared', description: 'Enrollment data and counters reset.' });
    } catch (e) {
      toast({ title: 'Clear failed', description: e.message, variant: 'destructive' });
    } finally { setClearingLeads(false); }
  };

  // ── Regenerate steps ──────────────────────────────────────────────────
  const handleGenerateSteps = async () => {
    if (!selectedCampaign) return;
    setGeneratingSteps(true);
    try {
      const resp = await generateSequenceSteps(selectedCampaign.id);
      setSteps(resp.data || []);
      toast({ title: 'AI generated 4 sequence steps' });
    } catch (e) {
      toast({ title: 'Generate failed', description: e.message, variant: 'destructive' });
    } finally { setGeneratingSteps(false); }
  };

  // ── Save campaign settings ────────────────────────────────────────────
  const handleSaveSettings = async () => {
    setSavingSettings(true);
    try {
      const resp = await updateCampaign(selectedCampaign.id, settingsDraft);
      setSelectedCampaign(resp.data);
      setShowSettingsModal(false);
      toast({ title: 'Campaign settings saved' });
    } catch (e) {
      toast({ title: 'Save failed', description: e.message, variant: 'destructive' });
    } finally { setSavingSettings(false); }
  };

  // ── Save step edit ─────────────────────────────────────────────────────
  const handleSaveStep = async () => {
    if (!editingStep) return;
    setSavingStep(true);
    try {
      const resp = await updateCampaignStep(selectedCampaign.id, editingStep.id, editingStep);
      setSteps(prev => prev.map(s => s.id === editingStep.id ? resp.data : s));
      setShowEditStepModal(false);
      setEditingStep(null);
      toast({ title: 'Step updated' });
    } catch (e) {
      toast({ title: 'Update failed', description: e.message, variant: 'destructive' });
    } finally { setSavingStep(false); }
  };

  // ── Enroll leads ──────────────────────────────────────────────────────
  const openEnrollModal = async () => {
    try {
      const resp = await listLeads();
      setLeads(resp.data || []);
    } catch (e) { console.error(e); }
    setSelectedLeadIds([]);
    setShowEnrollModal(true);
  };

  const handleEnroll = async () => {
    if (!selectedLeadIds.length) {
      toast({ title: 'Select at least one lead', variant: 'destructive' }); return;
    }
    setEnrolling(true);
    try {
      const resp = await enrollLeads(selectedCampaign.id, selectedLeadIds);
      toast({ title: `Enrolled ${resp.enrolled} leads`, description: `${resp.skipped} already enrolled.` });
      setShowEnrollModal(false);
      setSelectedLeadIds([]);
      await loadDetail(selectedCampaign);
    } catch (e) {
      toast({ title: 'Enroll failed', description: e.message, variant: 'destructive' });
    } finally { setEnrolling(false); }
  };

  // ── Process outreach ──────────────────────────────────────────────────
  const handleProcess = async () => {
    setProcessing(true);
    try {
      const resp = await processOutreach(selectedCampaign.id);
      const hasErrors = resp.failed > 0 && resp.errors?.length > 0;
      toast({
        title: `Processed ${resp.processed} enrollment${resp.processed !== 1 ? 's' : ''}`,
        description: hasErrors
          ? `Sent: ${resp.sent} | Failed: ${resp.failed} | Skipped: ${resp.skipped}\nError: ${resp.errors[0]}`
          : `Sent: ${resp.sent} | Skipped: ${resp.skipped} | Failed: ${resp.failed}`,
        variant: hasErrors ? 'destructive' : 'default',
      });
      await loadDetail(selectedCampaign);
    } catch (e) {
      toast({ title: 'Process failed', description: e.message, variant: 'destructive' });
    } finally { setProcessing(false); }
  };

  // ── Pause / Resume campaign ──────────────────────────────────────────
  const handlePauseResume = async () => {
    if (!selectedCampaign) return;
    const isPaused = selectedCampaign.status === 'paused';
    const newStatus = isPaused ? 'active' : 'paused';
    setPausingCampaign(true);
    try {
      const resp = await updateCampaign(selectedCampaign.id, { status: newStatus });
      setSelectedCampaign(resp.data);
      await loadCampaigns();
      toast({ title: isPaused ? 'Campaign resumed — Celery will process it on next cycle' : 'Campaign paused' });
    } catch (e) {
      toast({ title: 'Failed to update campaign status', description: e.message, variant: 'destructive' });
    } finally { setPausingCampaign(false); }
  };

  // ── Reset enrollment ─────────────────────────────────────────────────
  const handleResetEnrollment = async (enrollment) => {
    try {
      await resetEnrollment(selectedCampaign.id, enrollment.id);
      toast({ title: `Reset — ${enrollment.lead_name} is active again` });
      await loadDetail(selectedCampaign);
    } catch (e) {
      toast({ title: 'Reset failed', description: e.message, variant: 'destructive' });
    }
  };

  // ── Campaign list view ─────────────────────────────────────────────────
  if (!selectedCampaign) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h2 style={{ color: '#e2d9f3', fontSize: 20, fontWeight: 700, margin: 0 }}>Outreach Campaigns</h2>
            <p style={{ color: '#4b5563', fontSize: 13, marginTop: 4 }}>
              Multi-step sequences: Day 1 email → Day 3 LinkedIn → Day 5 follow-up → Day 10 last touch
            </p>
          </div>
          <Button onClick={() => setShowCreateModal(true)} style={{
            background: 'linear-gradient(90deg,#f43f5e 0%,#a855f7 100%)',
            color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600,
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            <Plus size={15} /> New Campaign
          </Button>
        </div>

        {/* Campaign grid */}
        {loading ? (
          <div style={{ textAlign: 'center', padding: 60, color: '#6b7280' }}>
            <Loader2 size={28} className="animate-spin" style={{ margin: '0 auto 12px', color: '#a855f7' }} />
            <p>Loading campaigns…</p>
          </div>
        ) : campaigns.length === 0 ? (
          <div style={{ ...cardStyle, padding: 60, textAlign: 'center' }}>
            <Send size={40} style={{ color: '#1e0f38', margin: '0 auto 16px' }} />
            <p style={{ color: '#6b7280', marginBottom: 6 }}>No campaigns yet.</p>
            <p style={{ color: '#4b5563', fontSize: 13, marginBottom: 20 }}>
              Create your first campaign and AI will generate the full outreach sequence automatically.
            </p>
            <Button onClick={() => setShowCreateModal(true)} style={{
              background: 'linear-gradient(90deg,#f43f5e,#a855f7)', color: '#fff',
              border: 'none', borderRadius: 8, fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 6,
            }}>
              <Plus size={14} /> Create Campaign
            </Button>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
            {campaigns.map(c => {
              const sc = STATUS_COLORS[c.status] || STATUS_COLORS.draft;
              return (
                <div key={c.id} style={{ ...cardStyle, padding: 20, cursor: 'pointer', transition: 'border-color 0.2s' }}
                  onClick={() => loadDetail(c)}
                  onMouseEnter={e => e.currentTarget.style.borderColor = '#a855f7'}
                  onMouseLeave={e => e.currentTarget.style.borderColor = '#2d1f4a'}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                    <div style={{ flex: 1 }}>
                      <h3 style={{ color: '#e2d9f3', fontWeight: 700, fontSize: 15, margin: 0 }}>{c.name}</h3>
                      {c.description && (
                        <p style={{ color: '#6b7280', fontSize: 12, marginTop: 4, lineHeight: 1.4 }}>
                          {c.description.slice(0, 80)}{c.description.length > 80 ? '…' : ''}
                        </p>
                      )}
                    </div>
                    <button onClick={e => { e.stopPropagation(); setDeleteConfirm(c); }} style={{
                      background: 'none', border: 'none', cursor: 'pointer', color: '#4b5563', padding: 4,
                    }}>
                      <Trash2 size={13} />
                    </button>
                  </div>

                  {/* Status badge */}
                  <span style={{
                    display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 10px',
                    borderRadius: 12, fontSize: 11, fontWeight: 600,
                    background: sc.bg, border: `1px solid ${sc.border}`, color: sc.color,
                    marginBottom: 14,
                  }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: sc.color, display: 'inline-block' }} />
                    {sc.label}
                  </span>

                  {/* Stats */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                    {[
                      { label: 'Leads', value: c.total_leads, icon: Users },
                      { label: 'Sent', value: c.emails_sent, icon: Mail },
                      { label: 'Replies', value: c.replies_received, icon: MessageSquare },
                    ].map(({ label, value, icon: Icon }) => (
                      <div key={label} style={{
                        textAlign: 'center', padding: '8px 4px',
                        background: 'rgba(255,255,255,0.03)', borderRadius: 8,
                        border: '1px solid rgba(255,255,255,0.05)',
                      }}>
                        <div style={{ color: '#e2d9f3', fontWeight: 700, fontSize: 18 }}>{value || 0}</div>
                        <div style={{ color: '#4b5563', fontSize: 11, marginTop: 2 }}>{label}</div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Delete Campaign Confirmation */}
        <Dialog open={!!deleteConfirm} onOpenChange={open => { if (!open) setDeleteConfirm(null); }}>
          <DialogContent style={{ background: 'linear-gradient(135deg,#0f0a1f 0%,#14082a 100%)', border: '1px solid #2d1f4a', borderRadius: 14, maxWidth: 420 }}>
            <DialogHeader>
              <DialogTitle style={{ color: '#e2d9f3', fontSize: 16 }}>Delete Campaign?</DialogTitle>
            </DialogHeader>
            <p style={{ color: '#9ca3af', fontSize: 13, lineHeight: 1.6, marginTop: 4 }}>
              Are you sure you want to delete <b style={{ color: '#e2d9f3' }}>{deleteConfirm?.name}</b>?
              All enrollments, outreach logs, and meetings will be permanently removed.
            </p>
            <DialogFooter style={{ marginTop: 16 }}>
              <Button variant="outline" onClick={() => setDeleteConfirm(null)} style={{ border: '1px solid #2d1f4a', color: '#9ca3af', borderRadius: 8 }}>
                Cancel
              </Button>
              <Button onClick={handleDeleteCampaign} style={{ background: 'linear-gradient(90deg,#f43f5e,#dc2626)', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600 }}>
                <Trash2 size={13} style={{ marginRight: 6 }} /> Yes, Delete
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Create Campaign Modal */}
        <Dialog open={showCreateModal} onOpenChange={setShowCreateModal}>
          <DialogContent style={{
            background: 'linear-gradient(135deg,#0f0a1f 0%,#14082a 100%)',
            border: '1px solid #2d1f4a', color: '#e2d9f3', maxWidth: 580, maxHeight: '90vh', overflowY: 'auto',
          }}>
            <DialogHeader>
              <DialogTitle style={{ color: '#e2d9f3' }}>New Outreach Campaign</DialogTitle>
            </DialogHeader>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {/* Basic info */}
              <div>
                <label style={labelStyle}>Campaign Name *</label>
                <input value={newCampaign.name} onChange={e => setNewCampaign(p => ({ ...p, name: e.target.value }))}
                  placeholder="e.g. Q1 SaaS Founders Outreach" style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Description / Goal</label>
                <textarea value={newCampaign.description}
                  onChange={e => setNewCampaign(p => ({ ...p, description: e.target.value }))}
                  placeholder="Target SaaS founders who recently raised Series A…"
                  style={{ ...inputStyle, minHeight: 60, resize: 'vertical' }} />
              </div>

              {/* Sender info */}
              <div style={{ borderTop: '1px solid #1e0f38', paddingTop: 14 }}>
                <p style={{ color: '#9ca3af', fontSize: 12, fontWeight: 600, marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Sender Identity
                </p>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div>
                    <label style={labelStyle}>Your Name</label>
                    <input value={newCampaign.sender_name} onChange={e => setNewCampaign(p => ({ ...p, sender_name: e.target.value }))}
                      placeholder="Jane Smith" style={inputStyle} />
                  </div>
                  <div>
                    <label style={labelStyle}>Your Title</label>
                    <input value={newCampaign.sender_title} onChange={e => setNewCampaign(p => ({ ...p, sender_title: e.target.value }))}
                      placeholder="Account Executive" style={inputStyle} />
                  </div>
                  <div style={{ gridColumn: '1 / -1' }}>
                    <label style={labelStyle}>Company Name</label>
                    <input value={newCampaign.sender_company} onChange={e => setNewCampaign(p => ({ ...p, sender_company: e.target.value }))}
                      placeholder="Acme Corp" style={inputStyle} />
                  </div>
                </div>
              </div>

              {/* Schedule */}
              <div style={{ borderTop: '1px solid #1e0f38', paddingTop: 14 }}>
                <p style={{ color: '#9ca3af', fontSize: 12, fontWeight: 600, marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Schedule (auto-runs via background worker)
                </p>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div>
                    <label style={labelStyle}>Start Date</label>
                    <input type="date" min={todayStr()} value={newCampaign.start_date}
                      onChange={e => setNewCampaign(p => ({ ...p, start_date: e.target.value }))}
                      style={inputStyle} />
                  </div>
                  <div>
                    <label style={labelStyle}>Estimated End</label>
                    <div style={{ ...inputStyle, color: '#6b7280', display: 'flex', alignItems: 'center', minHeight: 38 }}>
                      {newCampaign.start_date ? addDays(newCampaign.start_date, 10) : '— set start date'}
                    </div>
                  </div>
                  <div style={{ gridColumn: '1 / -1' }}>
                    <label style={labelStyle}>Calendar Link (Calendly etc.) — sent on positive replies</label>
                    <input value={newCampaign.calendar_link}
                      onChange={e => setNewCampaign(p => ({ ...p, calendar_link: e.target.value }))}
                      placeholder="https://calendly.com/your-link" style={inputStyle} />
                  </div>
                  <div style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'center', gap: 8 }}>
                    <input type="checkbox" id="auto_replies" checked={newCampaign.auto_check_replies}
                      onChange={e => setNewCampaign(p => ({ ...p, auto_check_replies: e.target.checked }))} />
                    <label htmlFor="auto_replies" style={{ color: '#9ca3af', fontSize: 13 }}>
                      Auto-check inbox for replies every 5 min (recommended)
                    </label>
                  </div>
                </div>
                <p style={{ color: '#6b7280', fontSize: 11, marginTop: 8, lineHeight: 1.5 }}>
                  Sequence runs Day 1 (email) → Day 3 (LinkedIn) → Day 5 (follow-up) → Day 10 (last touch).
                  Background workers send each step automatically — no need to click "Process Now".
                </p>
              </div>

              {/* SMTP toggle */}
              <div>
                <button onClick={() => setShowSmtpSection(p => !p)} style={{
                  background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af',
                  fontSize: 12, padding: 0, display: 'flex', alignItems: 'center', gap: 6,
                }}>
                  <Mail size={13} />
                  {showSmtpSection ? 'Hide' : 'Configure'} Email Sending (SMTP) — optional
                </button>
                {showSmtpSection && (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 12 }}>
                    {/* Provider picker */}
                    <div style={{ gridColumn: '1 / -1' }}>
                      <label style={labelStyle}>Email Provider</label>
                      <select
                        value={detectProvider(newCampaign.smtp_host)}
                        onChange={e => applySmtpProvider(e.target.value, setNewCampaign)}
                        style={{ ...inputStyle, cursor: 'pointer', background: '#1a0a35', color: '#e2d9f3' }}
                      >
                        <option value="" disabled style={{ background: '#1a0a35', color: '#6b7280' }}>Select provider to auto-fill…</option>
                        {SMTP_PROVIDERS.map(p => <option key={p.key} value={p.key} style={{ background: '#1a0a35', color: '#e2d9f3' }}>{p.label}</option>)}
                      </select>
                    </div>
                    {/* Gmail App-Password hint */}
                    {detectProvider(newCampaign.smtp_host) === 'gmail' && (
                      <div style={{ gridColumn: '1 / -1', padding: '8px 12px', borderRadius: 8, background: 'rgba(96,165,250,0.08)', border: '1px solid rgba(96,165,250,0.25)', color: '#93c5fd', fontSize: 12 }}>
                        Gmail requires a 16-character <b>App Password</b> (not your regular password). Enable 2-Step Verification → Google Account → Security → App Passwords.
                      </div>
                    )}
                    <div style={{ gridColumn: '1 / -1' }}>
                      <label style={labelStyle}>From Email</label>
                      <input value={newCampaign.from_email} onChange={e => setNewCampaign(p => ({ ...p, from_email: e.target.value }))}
                        placeholder="you@company.com" style={inputStyle} />
                    </div>
                    <div>
                      <label style={labelStyle}>SMTP Host</label>
                      <input value={newCampaign.smtp_host} onChange={e => setNewCampaign(p => ({ ...p, smtp_host: e.target.value }))}
                        placeholder="smtp.gmail.com" style={inputStyle} />
                    </div>
                    <div>
                      <label style={labelStyle}>SMTP Port</label>
                      <input type="number" value={newCampaign.smtp_port} onChange={e => setNewCampaign(p => ({ ...p, smtp_port: e.target.value }))}
                        style={inputStyle} />
                    </div>
                    <div>
                      <label style={labelStyle}>SMTP Username</label>
                      <input value={newCampaign.smtp_username} onChange={e => setNewCampaign(p => ({ ...p, smtp_username: e.target.value }))}
                        style={inputStyle} />
                    </div>
                    <div>
                      <label style={labelStyle}>SMTP Password / App Password</label>
                      <input type="password" value={newCampaign.smtp_password} onChange={e => setNewCampaign(p => ({ ...p, smtp_password: e.target.value }))}
                        style={inputStyle} />
                    </div>
                    <div style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'center', gap: 8 }}>
                      <input type="checkbox" id="tls" checked={newCampaign.smtp_use_tls}
                        onChange={e => setNewCampaign(p => ({ ...p, smtp_use_tls: e.target.checked }))} />
                      <label htmlFor="tls" style={{ color: '#9ca3af', fontSize: 13 }}>Use TLS (recommended)</label>
                    </div>
                    {/* IMAP — for reply detection */}
                    <div style={{ gridColumn: '1 / -1', borderTop: '1px solid #1e0f38', paddingTop: 10, marginTop: 4 }}>
                      <p style={{ color: '#6b7280', fontSize: 11, margin: '0 0 8px', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>
                        IMAP Settings — reply detection
                      </p>
                    </div>
                    <div>
                      <label style={labelStyle}>IMAP Host</label>
                      <input value={newCampaign.imap_host || ''} onChange={e => setNewCampaign(p => ({ ...p, imap_host: e.target.value }))}
                        placeholder="imap.hostinger.com" style={inputStyle} />
                    </div>
                    <div>
                      <label style={labelStyle}>IMAP Port</label>
                      <input type="number" value={newCampaign.imap_port || 993} onChange={e => setNewCampaign(p => ({ ...p, imap_port: parseInt(e.target.value) }))}
                        style={inputStyle} />
                    </div>
                  </div>
                )}
              </div>

              {/* AI steps checkbox */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', borderRadius: 8, background: 'rgba(168,85,247,0.06)', border: '1px solid rgba(168,85,247,0.2)' }}>
                <input type="checkbox" id="gen_steps" checked={newCampaign.generate_steps}
                  onChange={e => setNewCampaign(p => ({ ...p, generate_steps: e.target.checked }))} />
                <label htmlFor="gen_steps" style={{ color: '#c084fc', fontSize: 13, cursor: 'pointer' }}>
                  <Zap size={12} style={{ display: 'inline', marginRight: 4 }} />
                  AI generates the 4-step sequence automatically on create
                </label>
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setShowCreateModal(false)} style={{ border: '1px solid #2d1f4a', color: '#9ca3af', borderRadius: 8 }}>Cancel</Button>
              <Button onClick={handleCreate} disabled={creating} style={{
                background: 'linear-gradient(90deg,#f43f5e,#a855f7)', color: '#fff',
                border: 'none', borderRadius: 8, fontWeight: 600,
                display: 'flex', alignItems: 'center', gap: 6,
              }}>
                {creating ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
                Create Campaign
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  // ── Campaign detail view ───────────────────────────────────────────────
  const sc = STATUS_COLORS[selectedCampaign.status] || STATUS_COLORS.draft;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Top bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button onClick={() => setSelectedCampaign(null)} style={{
            background: 'rgba(255,255,255,0.05)', border: '1px solid #2d1f4a',
            borderRadius: 8, padding: '6px 10px', cursor: 'pointer', color: '#9ca3af',
            display: 'flex', alignItems: 'center', gap: 6, fontSize: 13,
          }}>
            <ChevronLeft size={14} /> Campaigns
          </button>
          <div>
            <h2 style={{ color: '#e2d9f3', fontSize: 18, fontWeight: 700, margin: 0 }}>{selectedCampaign.name}</h2>
            <div style={{ display: 'flex', gap: 8, marginTop: 4, alignItems: 'center', flexWrap: 'wrap' }}>
              <span style={{
                display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px',
                borderRadius: 10, fontSize: 11, fontWeight: 600,
                background: sc.bg, border: `1px solid ${sc.border}`, color: sc.color,
              }}>
                <span style={{ width: 5, height: 5, borderRadius: '50%', background: sc.color, display: 'inline-block' }} />
                {sc.label}
              </span>
              {selectedCampaign.start_date && (
                <span style={{ color: '#6b7280', fontSize: 11, display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Calendar size={11} />
                  {selectedCampaign.start_date} → {selectedCampaign.end_date || addDays(selectedCampaign.start_date, 10)}
                </span>
              )}
              {selectedCampaign.auto_check_replies && (
                <span style={{ color: '#10b981', fontSize: 11, display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Inbox size={11} /> Auto-checking inbox
                </span>
              )}
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <Button onClick={() => { setSettingsDraft({ ...selectedCampaign, smtp_password: '' }); setShowSettingsModal(true); }} variant="outline" style={{
            border: '1px solid #2d1f4a', color: '#9ca3af', borderRadius: 8,
            display: 'flex', alignItems: 'center', gap: 6, fontSize: 13,
          }}>
            <Edit2 size={14} /> Settings
          </Button>
          <Button onClick={openEnrollModal} variant="outline" style={{
            border: '1px solid #2d1f4a', color: '#9ca3af', borderRadius: 8,
            display: 'flex', alignItems: 'center', gap: 6, fontSize: 13,
          }}>
            <Users size={14} /> Enroll Leads
          </Button>
          {enrollments.length > 0 && (
            <Button onClick={() => setClearLeadsConfirm(true)} disabled={clearingLeads} variant="outline" style={{
              border: '1px solid rgba(244,63,94,0.35)', color: '#f87171', borderRadius: 8,
              display: 'flex', alignItems: 'center', gap: 6, fontSize: 13,
            }}>
              {clearingLeads ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
              Clear Leads
            </Button>
          )}
          {/* Pause / Resume — only for active or paused campaigns */}
          {(selectedCampaign.status === 'active' || selectedCampaign.status === 'paused') && (
            <Button onClick={handlePauseResume} disabled={pausingCampaign} variant="outline" style={{
              border: selectedCampaign.status === 'active' ? '1px solid rgba(245,158,11,0.4)' : '1px solid rgba(16,185,129,0.4)',
              color: selectedCampaign.status === 'active' ? '#f59e0b' : '#10b981',
              borderRadius: 8, display: 'flex', alignItems: 'center', gap: 6, fontSize: 13,
            }}>
              {pausingCampaign
                ? <Loader2 size={14} className="animate-spin" />
                : selectedCampaign.status === 'active' ? <Pause size={14} /> : <Play size={14} />}
              {pausingCampaign ? '…' : selectedCampaign.status === 'active' ? 'Pause' : 'Resume'}
            </Button>
          )}
        </div>
      </div>

      {/* Stats row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        {[
          { label: 'Total Leads', value: selectedCampaign.total_leads, color: '#a855f7', icon: Users },
          { label: 'Emails Sent', value: selectedCampaign.emails_sent, color: '#60a5fa', icon: Mail },
          { label: 'Replies', value: selectedCampaign.replies_received, color: '#10b981', icon: MessageSquare },
          { label: 'Meetings', value: selectedCampaign.meetings_booked || 0, color: '#f59e0b', icon: Calendar },
        ].map(({ label, value, color, icon: Icon }) => (
          <div key={label} style={{ ...cardStyle, padding: '14px 18px', display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{ width: 40, height: 40, borderRadius: 10, background: `${color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <Icon size={18} style={{ color }} />
            </div>
            <div>
              <div style={{ color, fontSize: 24, fontWeight: 700 }}>{value || 0}</div>
              <div style={{ color: '#6b7280', fontSize: 12 }}>{label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* SMTP missing warning — shown prominently if credentials not set */}
      {!(selectedCampaign.smtp_host && selectedCampaign.smtp_username) && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px',
          borderRadius: 8, background: 'rgba(244,63,94,0.08)', border: '1px solid rgba(244,63,94,0.35)',
          color: '#f87171', fontSize: 12,
        }}>
          <Mail size={13} style={{ flexShrink: 0 }} />
          <span>
            <b>SMTP not configured.</b> Emails will NOT be sent and leads cannot be enrolled until you add email credentials.{' '}
            <button onClick={() => { setSettingsDraft({ ...selectedCampaign, smtp_password: '' }); setShowSettingsModal(true); }}
              style={{ background: 'none', border: 'none', color: '#f43f5e', cursor: 'pointer', fontWeight: 700, padding: 0, textDecoration: 'underline' }}>
              Open Settings →
            </button>
          </span>
        </div>
      )}

      {/* Automation status banner */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px',
        borderRadius: 8, background: 'rgba(96,165,250,0.06)', border: '1px solid rgba(96,165,250,0.2)',
        color: '#93c5fd', fontSize: 12,
      }}>
        <Zap size={13} style={{ flexShrink: 0, color: '#a855f7' }} />
        <span>
          <b style={{ color: '#c084fc' }}>Automation active</b> —
          {selectedCampaign.status === 'active'
            ? ' emails send automatically every 5 min · inbox checked every 5 min · no manual action needed.'
            : selectedCampaign.status === 'scheduled'
            ? ` campaign will auto-start on ${selectedCampaign.start_date} when Celery runs the 15-min check.`
            : selectedCampaign.status === 'paused'
            ? ' campaign is paused. Resume to let Celery continue sending.'
            : ' campaign is not active.'}
          {selectedCampaign.smtp_host && <span style={{ color: '#60a5fa' }}> · Using {selectedCampaign.smtp_host}</span>}
        </span>
      </div>

      {/* SMTP override note — only shown if campaign has custom SMTP */}
      {/* {selectedCampaign.smtp_host && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px',
          borderRadius: 8, background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.2)',
          color: '#6ee7b7', fontSize: 12,
        }}>
          <Mail size={13} style={{ flexShrink: 0 }} />
          Using custom SMTP: <b style={{ marginLeft: 4 }}>{selectedCampaign.smtp_host}</b>
        </div>
      )} */}

      {/* Main content: steps + enrollments */}
      <div style={{ display: 'grid', gridTemplateColumns: '340px 1fr', gap: 16, alignItems: 'flex-start' }}>

        {/* Sequence steps */}
        <div style={{ ...cardStyle, padding: 18 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h3 style={{ color: '#e2d9f3', fontWeight: 700, fontSize: 14, margin: 0 }}>Outreach Sequence</h3>
            <button onClick={handleGenerateSteps} disabled={generatingSteps} style={{
              background: 'rgba(168,85,247,0.1)', border: '1px solid rgba(168,85,247,0.3)',
              borderRadius: 6, padding: '4px 10px', cursor: 'pointer', color: '#c084fc',
              fontSize: 11, display: 'flex', alignItems: 'center', gap: 4,
            }}>
              {generatingSteps ? <Loader2 size={11} className="animate-spin" /> : <Zap size={11} />}
              {generatingSteps ? 'Generating…' : 'Regenerate'}
            </button>
          </div>

          {loadingDetail ? (
            <div style={{ textAlign: 'center', padding: 30, color: '#6b7280' }}>
              <Loader2 size={20} className="animate-spin" style={{ margin: '0 auto 8px', color: '#a855f7' }} />
            </div>
          ) : steps.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 24 }}>
              <p style={{ color: '#4b5563', fontSize: 13, marginBottom: 12 }}>No steps yet.</p>
              <button onClick={handleGenerateSteps} disabled={generatingSteps} style={{
                background: 'linear-gradient(90deg,#7c3aed,#a855f7)', color: '#fff',
                border: 'none', borderRadius: 8, padding: '8px 16px', cursor: 'pointer',
                fontWeight: 600, fontSize: 13, display: 'flex', alignItems: 'center', gap: 6, margin: '0 auto',
              }}>
                <Zap size={13} /> Generate Steps with AI
              </button>
            </div>
          ) : (
            steps.map((step, i) => (
              <StepCard
                key={step.id}
                step={step}
                isLast={i === steps.length - 1}
                onEdit={(s) => { setEditingStep({ ...s }); setShowEditStepModal(true); }}
              />
            ))
          )}
        </div>

        {/* Enrollments table */}
        <div style={{ ...cardStyle, overflow: 'hidden' }}>
          <div style={{ padding: '16px 18px', borderBottom: '1px solid #1e0f38', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ color: '#e2d9f3', fontWeight: 700, fontSize: 14, margin: 0 }}>
              Enrolled Leads <span style={{ color: '#4b5563', fontWeight: 400 }}>({enrollments.length})</span>
            </h3>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <span style={{ color: '#4b5563', fontSize: 11, display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#10b981', display: 'inline-block', animation: 'pulse 2s infinite' }} />
                Auto-checking replies every 5 min
              </span>
              <button onClick={() => loadDetail(selectedCampaign)} style={{
                background: 'none', border: '1px solid #2d1f4a', borderRadius: 6, padding: '4px 8px', cursor: 'pointer', color: '#6b7280',
              }}>
                <RefreshCw size={12} />
              </button>
            </div>
          </div>

          {enrollments.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <Users size={32} style={{ color: '#1e0f38', margin: '0 auto 10px' }} />
              <p style={{ color: '#6b7280', fontSize: 13 }}>No leads enrolled yet.</p>
              <p style={{ color: '#4b5563', fontSize: 12 }}>Click "Enroll Leads" to add leads to this campaign.</p>
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #1e0f38' }}>
                  {['Lead', 'Score', 'Progress', 'Status', 'Next Action / Reply', 'Meeting'].map(h => (
                    <th key={h} style={{ padding: '10px 14px', textAlign: 'left', color: '#4b5563', fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {enrollments.map(enr => {
                  const es = ENROLL_STATUS[enr.status] || ENROLL_STATUS.active;
                  const TIcon = TEMP_ICON[enr.lead_temperature];
                  return (
                    <tr key={enr.id}
                      style={{ borderBottom: '1px solid rgba(45,31,74,0.4)' }}
                      onMouseEnter={e => e.currentTarget.style.background = 'rgba(168,85,247,0.04)'}
                      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                    >
                      <td style={{ padding: '11px 14px' }}>
                        <div style={{ fontWeight: 600, color: '#e2d9f3', fontSize: 13 }}>{enr.lead_name}</div>
                        <div style={{ color: '#6b7280', fontSize: 11, marginTop: 2 }}>{enr.lead_company}</div>
                        {enr.lead_email && <div style={{ color: '#4b5563', fontSize: 11 }}>{enr.lead_email}</div>}
                      </td>
                      <td style={{ padding: '11px 14px' }}>
                        {enr.lead_score != null ? (
                          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            {TIcon && <TIcon size={11} style={{ color: TEMP_COLOR[enr.lead_temperature] }} />}
                            <span style={{ color: TEMP_COLOR[enr.lead_temperature] || '#6b7280', fontWeight: 600, fontSize: 13 }}>
                              {enr.lead_score}
                            </span>
                          </span>
                        ) : <span style={{ color: '#2d1f4a' }}>—</span>}
                      </td>
                      <td style={{ padding: '11px 14px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <div style={{ flex: 1, height: 5, borderRadius: 3, background: 'rgba(255,255,255,0.08)', maxWidth: 80 }}>
                            <div style={{
                              height: '100%', borderRadius: 3,
                              width: enr.total_steps > 0 ? `${(enr.current_step / enr.total_steps) * 100}%` : '0%',
                              background: 'linear-gradient(90deg,#7c3aed,#a855f7)',
                            }} />
                          </div>
                          <span style={{ color: '#6b7280', fontSize: 11 }}>
                            {enr.current_step}/{enr.total_steps}
                          </span>
                        </div>
                      </td>
                      {/* Status column */}
                      <td style={{ padding: '11px 14px' }}>
                        <span style={{
                          display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 9px',
                          borderRadius: 10, fontSize: 11, fontWeight: 600,
                          background: `${es.color}15`, color: es.color,
                          border: `1px solid ${es.color}30`,
                        }}>
                          {enr.status === 'replied' && <Mail size={10} />}
                          {es.label}
                        </span>
                      </td>

                      {/* Next Action / Reply column */}
                      <td style={{ padding: '11px 14px' }}>
                        {enr.status === 'replied' ? (
                          /* ── Replied lead: show reply preview + view button ── */
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                            <div style={{ color: '#9ca3af', fontSize: 11, display: 'flex', alignItems: 'center', gap: 4 }}>
                              <Clock size={10} />
                              {enr.replied_at ? fmtDate(enr.replied_at) : 'Date unknown'}
                            </div>
                            {enr.reply_content && (
                              <div style={{
                                color: '#6b7280', fontSize: 11, fontStyle: 'italic',
                                maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                              }}>
                                "{enr.reply_content.slice(0, 60)}{enr.reply_content.length > 60 ? '…' : ''}"
                              </div>
                            )}
                            <button
                              onClick={() => setViewReplyModal(enr)}
                              style={{
                                display: 'inline-flex', alignItems: 'center', gap: 4,
                                padding: '4px 10px', borderRadius: 8, fontSize: 11, fontWeight: 600,
                                background: enr.reply_sentiment === 'positive'
                                  ? 'rgba(16,185,129,0.15)'
                                  : enr.reply_sentiment === 'negative'
                                  ? 'rgba(244,63,94,0.15)'
                                  : 'rgba(96,165,250,0.15)',
                                color: enr.reply_sentiment === 'positive' ? '#10b981'
                                  : enr.reply_sentiment === 'negative' ? '#f43f5e' : '#60a5fa',
                                border: `1px solid ${enr.reply_sentiment === 'positive'
                                  ? 'rgba(16,185,129,0.4)'
                                  : enr.reply_sentiment === 'negative'
                                  ? 'rgba(244,63,94,0.4)'
                                  : 'rgba(96,165,250,0.4)'}`,
                                cursor: 'pointer', alignSelf: 'flex-start',
                              }}
                            >
                              <MessageSquare size={11} />
                              {enr.reply_sentiment === 'positive' ? '✓ Interested — View Reply'
                                : enr.reply_sentiment === 'negative' ? '✗ Not Interested — View Reply'
                                : 'View Reply →'}
                            </button>
                          </div>
                        ) : enr.next_action_at && enr.status === 'active' ? (() => {
                          const cd = fmtCountdown(enr.next_action_at, now);
                          return (
                            <div style={{ fontSize: 11 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#6b7280' }}>
                                <Clock size={10} /> {fmtDate(enr.next_action_at)}
                              </div>
                              {cd && (
                                <div style={{ marginTop: 3, fontWeight: 600, color: cd.color }}>
                                  {cd.label}
                                </div>
                              )}
                            </div>
                          );
                        })() : <span style={{ color: '#2d1f4a', fontSize: 11 }}>—</span>}
                      </td>

                      {/* Meeting column */}
                      <td style={{ padding: '11px 14px' }}>
                        {enr.meeting_id ? (
                          <span style={{
                            display: 'inline-flex', alignItems: 'center', gap: 3,
                            padding: '3px 8px', borderRadius: 8, fontSize: 10, fontWeight: 600,
                            background: 'rgba(245,158,11,0.12)', color: '#f59e0b',
                            border: '1px solid rgba(245,158,11,0.3)',
                          }}>
                            <Calendar size={9} /> Pending
                          </span>
                        ) : <span style={{ color: '#2d1f4a', fontSize: 11 }}>—</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Enroll Leads Modal */}
      <Dialog open={showEnrollModal} onOpenChange={setShowEnrollModal}>
        <DialogContent style={{
          background: 'linear-gradient(135deg,#0f0a1f 0%,#14082a 100%)',
          border: '1px solid #2d1f4a', color: '#e2d9f3', maxWidth: 620, maxHeight: '85vh',
        }}>
          <DialogHeader>
            <DialogTitle style={{ color: '#e2d9f3' }}>Enroll Leads into Campaign</DialogTitle>
          </DialogHeader>

          <div style={{ overflowY: 'auto', maxHeight: '55vh' }}>
            {leads.length === 0 ? (
              <p style={{ color: '#6b7280', textAlign: 'center', padding: 30 }}>No leads available. Add leads first from the Leads tab.</p>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #1e0f38' }}>
                    <th style={{ padding: '8px 12px', width: 36 }}>
                      <input type="checkbox"
                        onChange={e => setSelectedLeadIds(e.target.checked ? leads.map(l => l.id) : [])}
                        checked={selectedLeadIds.length === leads.length && leads.length > 0}
                      />
                    </th>
                    {['Name', 'Company', 'Score'].map(h => (
                      <th key={h} style={{ padding: '8px 12px', textAlign: 'left', color: '#4b5563', fontSize: 11, fontWeight: 600, textTransform: 'uppercase' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {leads.map(lead => {
                    const TIcon = TEMP_ICON[lead.temperature];
                    return (
                      <tr key={lead.id}
                        style={{ borderBottom: '1px solid rgba(45,31,74,0.4)', cursor: 'pointer' }}
                        onClick={() => setSelectedLeadIds(prev =>
                          prev.includes(lead.id) ? prev.filter(id => id !== lead.id) : [...prev, lead.id]
                        )}
                        onMouseEnter={e => e.currentTarget.style.background = 'rgba(168,85,247,0.05)'}
                        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                      >
                        <td style={{ padding: '10px 12px' }}>
                          <input type="checkbox" checked={selectedLeadIds.includes(lead.id)}
                            onChange={() => {}} onClick={e => e.stopPropagation()} />
                        </td>
                        <td style={{ padding: '10px 12px' }}>
                          <div style={{ color: '#e2d9f3', fontWeight: 600, fontSize: 13 }}>{lead.full_name}</div>
                          <div style={{ color: '#6b7280', fontSize: 11 }}>{lead.job_title}</div>
                        </td>
                        <td style={{ padding: '10px 12px', color: '#9ca3af', fontSize: 13 }}>{lead.company_name}</td>
                        <td style={{ padding: '10px 12px' }}>
                          {lead.score != null ? (
                            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                              {TIcon && <TIcon size={11} style={{ color: TEMP_COLOR[lead.temperature] }} />}
                              <span style={{ color: TEMP_COLOR[lead.temperature] || '#6b7280', fontWeight: 600 }}>{lead.score}</span>
                            </span>
                          ) : <span style={{ color: '#2d1f4a' }}>—</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          <div style={{ padding: '10px 0 0', borderTop: '1px solid #1e0f38', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: '#6b7280', fontSize: 13 }}>
              {selectedLeadIds.length} lead{selectedLeadIds.length !== 1 ? 's' : ''} selected
            </span>
            <div style={{ display: 'flex', gap: 8 }}>
              <Button variant="outline" onClick={() => setShowEnrollModal(false)} style={{ border: '1px solid #2d1f4a', color: '#9ca3af', borderRadius: 8 }}>Cancel</Button>
              <Button onClick={handleEnroll} disabled={enrolling || !selectedLeadIds.length} style={{
                background: 'linear-gradient(90deg,#f43f5e,#a855f7)', color: '#fff',
                border: 'none', borderRadius: 8, fontWeight: 600,
                display: 'flex', alignItems: 'center', gap: 6,
              }}>
                {enrolling ? <Loader2 size={13} className="animate-spin" /> : <Users size={13} />}
                Enroll Selected
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Step Modal */}
      {editingStep && (
        <EditStepModal
          step={editingStep}
          onChange={setEditingStep}
          onSave={handleSaveStep}
          onClose={() => { setShowEditStepModal(false); setEditingStep(null); }}
          saving={savingStep}
        />
      )}

      {/* Campaign Settings Modal */}
      {settingsDraft && (
        <Dialog open={showSettingsModal} onOpenChange={setShowSettingsModal}>
          <DialogContent style={{
            background: 'linear-gradient(135deg,#0f0a1f 0%,#14082a 100%)',
            border: '1px solid #2d1f4a', color: '#e2d9f3', maxWidth: 560, maxHeight: '90vh', overflowY: 'auto',
          }}>
            <DialogHeader>
              <DialogTitle style={{ color: '#e2d9f3' }}>Campaign Settings</DialogTitle>
            </DialogHeader>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {/* Sender info */}
              <div>
                <p style={{ color: '#9ca3af', fontSize: 12, fontWeight: 600, marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Sender Identity</p>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div>
                    <label style={labelStyle}>Your Name</label>
                    <input value={settingsDraft.sender_name || ''} onChange={e => setSettingsDraft(p => ({ ...p, sender_name: e.target.value }))} style={inputStyle} />
                  </div>
                  <div>
                    <label style={labelStyle}>Your Title</label>
                    <input value={settingsDraft.sender_title || ''} onChange={e => setSettingsDraft(p => ({ ...p, sender_title: e.target.value }))} style={inputStyle} />
                  </div>
                  <div style={{ gridColumn: '1 / -1' }}>
                    <label style={labelStyle}>Company Name</label>
                    <input value={settingsDraft.sender_company || ''} onChange={e => setSettingsDraft(p => ({ ...p, sender_company: e.target.value }))} style={inputStyle} />
                  </div>
                </div>
              </div>

              {/* Schedule */}
              <div style={{ borderTop: '1px solid #1e0f38', paddingTop: 14 }}>
                <p style={{ color: '#9ca3af', fontSize: 12, fontWeight: 600, marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Schedule</p>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div>
                    <label style={labelStyle}>Start Date</label>
                    <input type="date" value={settingsDraft.start_date || ''}
                      onChange={e => setSettingsDraft(p => ({ ...p, start_date: e.target.value || null }))}
                      style={inputStyle} />
                  </div>
                  <div>
                    <label style={labelStyle}>Calendar Link (Calendly etc.)</label>
                    <input value={settingsDraft.calendar_link || ''}
                      onChange={e => setSettingsDraft(p => ({ ...p, calendar_link: e.target.value }))}
                      placeholder="https://calendly.com/your-link" style={inputStyle} />
                  </div>
                  <div style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'center', gap: 8 }}>
                    <input type="checkbox" id="s_auto_replies" checked={!!settingsDraft.auto_check_replies}
                      onChange={e => setSettingsDraft(p => ({ ...p, auto_check_replies: e.target.checked }))} />
                    <label htmlFor="s_auto_replies" style={{ color: '#9ca3af', fontSize: 13 }}>
                      Auto-check inbox for replies every 5 min
                    </label>
                  </div>
                </div>
              </div>

              {/* SMTP */}
              <div style={{ borderTop: '1px solid #1e0f38', paddingTop: 14 }}>
                <p style={{ color: '#9ca3af', fontSize: 12, fontWeight: 600, marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Email / SMTP Settings
                </p>
                <div style={{ marginBottom: 10, padding: '8px 12px', borderRadius: 8, background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.2)', color: '#6ee7b7', fontSize: 12 }}>
                  <b>Optional override.</b> Leave blank to use the global email settings from .env (already configured). Fill only if this campaign needs a different sender account.
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  {/* Provider picker */}
                  <div style={{ gridColumn: '1 / -1' }}>
                    <label style={labelStyle}>Email Provider</label>
                    <select
                      value={detectProvider(settingsDraft.smtp_host || '')}
                      onChange={e => applySmtpProvider(e.target.value, setSettingsDraft)}
                      style={{ ...inputStyle, cursor: 'pointer', background: '#1a0a35', color: '#e2d9f3' }}
                    >
                      <option value="" disabled style={{ background: '#1a0a35', color: '#6b7280' }}>Select provider to auto-fill…</option>
                      {SMTP_PROVIDERS.map(p => <option key={p.key} value={p.key} style={{ background: '#1a0a35', color: '#e2d9f3' }}>{p.label}</option>)}
                    </select>
                  </div>
                  {/* Gmail App-Password hint */}
                  {detectProvider(settingsDraft.smtp_host || '') === 'gmail' && (
                    <div style={{ gridColumn: '1 / -1', padding: '8px 12px', borderRadius: 8, background: 'rgba(96,165,250,0.08)', border: '1px solid rgba(96,165,250,0.25)', color: '#93c5fd', fontSize: 12 }}>
                      Gmail requires a 16-character <b>App Password</b> (not your regular password). Enable 2-Step Verification → Google Account → Security → App Passwords.
                    </div>
                  )}
                  <div style={{ gridColumn: '1 / -1' }}>
                    <label style={labelStyle}>From Email</label>
                    <input value={settingsDraft.from_email || ''} onChange={e => setSettingsDraft(p => ({ ...p, from_email: e.target.value }))} placeholder="you@gmail.com" style={inputStyle} />
                  </div>
                  <div>
                    <label style={labelStyle}>SMTP Host</label>
                    <input value={settingsDraft.smtp_host || ''} onChange={e => setSettingsDraft(p => ({ ...p, smtp_host: e.target.value }))} placeholder="smtp.gmail.com" style={inputStyle} />
                  </div>
                  <div>
                    <label style={labelStyle}>SMTP Port</label>
                    <input type="number" value={settingsDraft.smtp_port || 587} onChange={e => setSettingsDraft(p => ({ ...p, smtp_port: parseInt(e.target.value) }))} style={inputStyle} />
                  </div>
                  <div>
                    <label style={labelStyle}>SMTP Username</label>
                    <input value={settingsDraft.smtp_username || ''} onChange={e => setSettingsDraft(p => ({ ...p, smtp_username: e.target.value }))} placeholder="you@gmail.com" style={inputStyle} />
                  </div>
                  <div>
                    <label style={labelStyle}>SMTP Password / App Password</label>
                    <input type="password" value={settingsDraft.smtp_password || ''} onChange={e => setSettingsDraft(p => ({ ...p, smtp_password: e.target.value }))} placeholder="Leave blank to keep existing" style={inputStyle} />
                  </div>
                  <div style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'center', gap: 8 }}>
                    <input type="checkbox" id="stls" checked={!!settingsDraft.smtp_use_tls} onChange={e => setSettingsDraft(p => ({ ...p, smtp_use_tls: e.target.checked }))} />
                    <label htmlFor="stls" style={{ color: '#9ca3af', fontSize: 13 }}>Use TLS (recommended)</label>
                  </div>
                  {/* IMAP — for reply detection */}
                  <div style={{ gridColumn: '1 / -1', borderTop: '1px solid #1e0f38', paddingTop: 10, marginTop: 4 }}>
                    <p style={{ color: '#6b7280', fontSize: 11, margin: '0 0 8px', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>
                      IMAP Settings — reply detection
                    </p>
                  </div>
                  <div>
                    <label style={labelStyle}>IMAP Host</label>
                    <input value={settingsDraft.imap_host || ''} onChange={e => setSettingsDraft(p => ({ ...p, imap_host: e.target.value }))} placeholder="imap.hostinger.com" style={inputStyle} />
                  </div>
                  <div>
                    <label style={labelStyle}>IMAP Port</label>
                    <input type="number" value={settingsDraft.imap_port || 993} onChange={e => setSettingsDraft(p => ({ ...p, imap_port: parseInt(e.target.value) }))} style={inputStyle} />
                  </div>
                </div>
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setShowSettingsModal(false)} style={{ border: '1px solid #2d1f4a', color: '#9ca3af', borderRadius: 8 }}>Cancel</Button>
              <Button onClick={handleSaveSettings} disabled={savingSettings} style={{
                background: 'linear-gradient(90deg,#7c3aed,#a855f7)', color: '#fff',
                border: 'none', borderRadius: 8, fontWeight: 600,
                display: 'flex', alignItems: 'center', gap: 6,
              }}>
                {savingSettings ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
                Save Settings
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {/* ── View Reply Modal ───────────────────────────────────────────── */}
      {viewReplyModal && (() => {
        const sentColor = viewReplyModal.reply_sentiment === 'positive' ? '#10b981'
          : viewReplyModal.reply_sentiment === 'negative' ? '#f43f5e' : '#9ca3af';
        const sentBg = viewReplyModal.reply_sentiment === 'positive' ? 'rgba(16,185,129,0.1)'
          : viewReplyModal.reply_sentiment === 'negative' ? 'rgba(244,63,94,0.1)' : 'rgba(107,114,128,0.1)';
        const sentLabel = viewReplyModal.reply_sentiment === 'positive' ? '✓ Interested — they want to connect!'
          : viewReplyModal.reply_sentiment === 'negative' ? '✗ Not interested'
          : '~ Neutral reply';
        return (
          <Dialog open onOpenChange={() => setViewReplyModal(null)}>
            <DialogContent style={{
              background: 'linear-gradient(135deg,#0f0a1f,#14082c)',
              border: '1px solid #2d1f4a', maxWidth: 560, color: '#e2d9f3',
            }}>
              <DialogHeader>
                <DialogTitle style={{ color: '#e2d9f3', display: 'flex', alignItems: 'center', gap: 8, fontSize: 16 }}>
                  <Mail size={17} style={{ color: sentColor }} />
                  Reply from {viewReplyModal.lead_name}
                </DialogTitle>
              </DialogHeader>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                {/* AI sentiment result */}
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '10px 14px', borderRadius: 10,
                  background: sentBg, border: `1px solid ${sentColor}40`,
                }}>
                  <span style={{ fontSize: 18 }}>
                    {viewReplyModal.reply_sentiment === 'positive' ? '🎉' : viewReplyModal.reply_sentiment === 'negative' ? '❌' : '💬'}
                  </span>
                  <div>
                    <div style={{ color: sentColor, fontWeight: 700, fontSize: 13 }}>{sentLabel}</div>
                    <div style={{ color: '#6b7280', fontSize: 11, marginTop: 2 }}>AI sentiment analysis</div>
                  </div>
                </div>

                {/* Email metadata */}
                <div style={{
                  background: 'rgba(255,255,255,0.02)', border: '1px solid #1e0f38',
                  borderRadius: 8, padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 5,
                }}>
                  <div style={{ display: 'flex', gap: 8, fontSize: 12 }}>
                    <span style={{ color: '#4b5563', minWidth: 40 }}>From</span>
                    <span style={{ color: '#e2d9f3', fontWeight: 600 }}>
                      {viewReplyModal.lead_name}
                      {viewReplyModal.lead_email && (
                        <span style={{ color: '#6b7280', fontWeight: 400, marginLeft: 6 }}>
                          &lt;{viewReplyModal.lead_email}&gt;
                        </span>
                      )}
                    </span>
                  </div>
                  {viewReplyModal.lead_company && (
                    <div style={{ display: 'flex', gap: 8, fontSize: 12 }}>
                      <span style={{ color: '#4b5563', minWidth: 40 }}>Co.</span>
                      <span style={{ color: '#9ca3af' }}>{viewReplyModal.lead_company}</span>
                    </div>
                  )}
                  {viewReplyModal.replied_at && (
                    <div style={{ display: 'flex', gap: 8, fontSize: 12 }}>
                      <span style={{ color: '#4b5563', minWidth: 40 }}>Date</span>
                      <span style={{ color: '#9ca3af' }}>{fmtDate(viewReplyModal.replied_at)}</span>
                    </div>
                  )}
                </div>

                {/* Reply body */}
                <div>
                  <div style={{ color: '#4b5563', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
                    Reply Content
                  </div>
                  <div style={{
                    background: 'rgba(255,255,255,0.03)', border: '1px solid #2d1f4a',
                    borderRadius: 8, padding: '14px 16px',
                    color: '#e2d9f3', fontSize: 13, lineHeight: 1.8,
                    whiteSpace: 'pre-wrap', maxHeight: 280, overflowY: 'auto',
                  }}>
                    {viewReplyModal.reply_content
                      ? viewReplyModal.reply_content
                      : <span style={{ color: '#4b5563', fontStyle: 'italic' }}>Reply content not available.</span>
                    }
                  </div>
                </div>

                {/* Meeting created? */}
                {viewReplyModal.meeting_id && (
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '8px 12px', borderRadius: 8,
                    background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.25)',
                  }}>
                    <Calendar size={14} style={{ color: '#f59e0b' }} />
                    <span style={{ color: '#fcd34d', fontSize: 12, fontWeight: 600 }}>
                      Meeting request sent — awaiting scheduling
                    </span>
                  </div>
                )}
              </div>

              <DialogFooter>
                <Button onClick={() => setViewReplyModal(null)} style={{
                  background: 'linear-gradient(90deg,#7c3aed,#a855f7)', color: '#fff',
                  border: 'none', borderRadius: 8, fontWeight: 600,
                }}>
                  Close
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        );
      })()}

      {/* Clear Leads Confirmation — detail view */}
      <Dialog open={clearLeadsConfirm} onOpenChange={setClearLeadsConfirm}>
        <DialogContent style={{ background: 'linear-gradient(135deg,#0f0a1f 0%,#14082a 100%)', border: '1px solid #2d1f4a', borderRadius: 14, maxWidth: 420 }}>
          <DialogHeader>
            <DialogTitle style={{ color: '#e2d9f3', fontSize: 16 }}>Clear All Leads?</DialogTitle>
          </DialogHeader>
          <p style={{ color: '#9ca3af', fontSize: 13, lineHeight: 1.6, marginTop: 4 }}>
            Are you sure you want to clear all <b style={{ color: '#e2d9f3' }}>{enrollments.length} enrolled lead{enrollments.length !== 1 ? 's' : ''}</b> from this campaign?
            All outreach logs and meetings will also be removed. Counters will reset to zero.
            <br /><br />
            <span style={{ color: '#6b7280', fontSize: 12 }}>
              The leads themselves will NOT be deleted — only their enrollment in this campaign.
            </span>
          </p>
          <DialogFooter style={{ marginTop: 16 }}>
            <Button variant="outline" onClick={() => setClearLeadsConfirm(false)} style={{ border: '1px solid #2d1f4a', color: '#9ca3af', borderRadius: 8 }}>
              Cancel
            </Button>
            <Button onClick={handleClearLeads} disabled={clearingLeads} style={{ background: 'linear-gradient(90deg,#f43f5e,#dc2626)', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
              {clearingLeads ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
              Yes, Clear All Leads
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </div>
  );
};

export default SDROutreachTab;
