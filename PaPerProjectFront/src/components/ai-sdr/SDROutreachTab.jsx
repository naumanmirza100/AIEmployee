import React, { useState, useEffect, useCallback } from 'react';
import {
  Mail, Linkedin, Plus, Play, RefreshCw, Trash2, Users, ChevronLeft,
  Zap, Check, X, Loader2, Send, MessageSquare, Calendar, Edit2,
  Flame, Thermometer, Snowflake, AlertCircle, Clock, Inbox,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import {
  listCampaigns, createCampaign, deleteCampaign, updateCampaign,
  getCampaignDetail, getCampaignSteps, generateSequenceSteps,
  getCampaignContacts, enrollLeads, processOutreach, markReplied,
  resetEnrollment, checkReplies, updateCampaignStep, listLeads,
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
  generate_steps: true,
};

const fmtDate = (iso) => {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
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
  const [checkingReplies, setCheckingReplies] = useState(false);
  const [replyModal, setReplyModal] = useState(null);  // {enrollment} or null
  const [replyContent, setReplyContent] = useState('');
  const [analyzingSentiment, setAnalyzingSentiment] = useState(false);

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

  // ── Delete campaign ────────────────────────────────────────────────────
  const handleDeleteCampaign = async (id) => {
    try {
      await deleteCampaign(id);
      toast({ title: 'Campaign deleted' });
      if (selectedCampaign?.id === id) setSelectedCampaign(null);
      await loadCampaigns();
    } catch (e) {
      toast({ title: 'Delete failed', description: e.message, variant: 'destructive' });
    }
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

  // ── Mark replied (with reply content + AI sentiment) ─────────────────
  const handleSubmitReply = async () => {
    if (!replyModal) return;
    setAnalyzingSentiment(true);
    try {
      const resp = await markReplied(selectedCampaign.id, replyModal.id, {
        reply_content: replyContent,
      });
      const sentiment = resp.sentiment || 'positive';
      const isInterested = resp.is_interested;
      const sentimentLabel = isInterested ? '✓ Interested' : sentiment === 'negative' ? '✗ Not interested' : '~ Neutral';
      toast({
        title: `Reply recorded — ${sentimentLabel}`,
        description: isInterested
          ? 'Meeting created and scheduling email sent!'
          : 'Lead marked as replied.',
      });
      setReplyModal(null);
      setReplyContent('');
      await loadDetail(selectedCampaign);
    } catch (e) {
      toast({ title: 'Failed to record reply', description: e.message, variant: 'destructive' });
    } finally { setAnalyzingSentiment(false); }
  };

  // ── Check inbox for auto-detected replies ────────────────────────────
  const handleCheckReplies = async () => {
    setCheckingReplies(true);
    try {
      const resp = await checkReplies(selectedCampaign.id);
      if (resp.new_replies === 0) {
        toast({ title: 'No new replies found', description: `Checked ${resp.checked} contacts` });
      } else {
        const interested = resp.details?.filter(d => d.is_interested).length || 0;
        toast({
          title: `${resp.new_replies} new ${resp.new_replies === 1 ? 'reply' : 'replies'} detected!`,
          description: `${interested} interested${resp.meetings_created > 0 ? ` · ${resp.meetings_created} meeting${resp.meetings_created > 1 ? 's' : ''} created` : ''}`,
        });
        await loadDetail(selectedCampaign);
      }
    } catch (e) {
      toast({ title: 'Check replies failed', description: e.message, variant: 'destructive' });
    } finally { setCheckingReplies(false); }
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
                    <button onClick={e => { e.stopPropagation(); handleDeleteCampaign(c.id); }} style={{
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
                      <label style={labelStyle}>SMTP Password</label>
                      <input type="password" value={newCampaign.smtp_password} onChange={e => setNewCampaign(p => ({ ...p, smtp_password: e.target.value }))}
                        style={inputStyle} />
                    </div>
                    <div style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'center', gap: 8 }}>
                      <input type="checkbox" id="tls" checked={newCampaign.smtp_use_tls}
                        onChange={e => setNewCampaign(p => ({ ...p, smtp_use_tls: e.target.checked }))} />
                      <label htmlFor="tls" style={{ color: '#9ca3af', fontSize: 13 }}>Use TLS (recommended)</label>
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
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px',
              borderRadius: 10, fontSize: 11, fontWeight: 600, marginTop: 4,
              background: sc.bg, border: `1px solid ${sc.border}`, color: sc.color,
            }}>
              <span style={{ width: 5, height: 5, borderRadius: '50%', background: sc.color, display: 'inline-block' }} />
              {sc.label}
            </span>
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
          <Button onClick={handleCheckReplies} disabled={checkingReplies} variant="outline" style={{
            border: '1px solid rgba(16,185,129,0.4)', color: '#10b981', borderRadius: 8,
            display: 'flex', alignItems: 'center', gap: 6, fontSize: 13,
          }}>
            {checkingReplies ? <Loader2 size={14} className="animate-spin" /> : <Inbox size={14} />}
            {checkingReplies ? 'Checking…' : 'Check Replies'}
          </Button>
          <Button onClick={handleProcess} disabled={processing} style={{
            background: 'linear-gradient(90deg,#f43f5e 0%,#a855f7 100%)',
            color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600,
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            {processing ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            {processing ? 'Processing…' : 'Process Now'}
          </Button>
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

      {/* SMTP override note — only shown if campaign has custom SMTP */}
      {selectedCampaign.smtp_host && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px',
          borderRadius: 8, background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.2)',
          color: '#6ee7b7', fontSize: 12,
        }}>
          <Mail size={13} style={{ flexShrink: 0 }} />
          Using custom SMTP: <b style={{ marginLeft: 4 }}>{selectedCampaign.smtp_host}</b>
        </div>
      )}

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
            <button onClick={() => loadDetail(selectedCampaign)} style={{
              background: 'none', border: '1px solid #2d1f4a', borderRadius: 6, padding: '4px 8px', cursor: 'pointer', color: '#6b7280',
            }}>
              <RefreshCw size={12} />
            </button>
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
                  {['Lead', 'Score', 'Progress', 'Status', 'Next Action', 'Actions'].map(h => (
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
                      <td style={{ padding: '11px 14px' }}>
                        <span style={{
                          display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px',
                          borderRadius: 10, fontSize: 11, fontWeight: 600,
                          background: `${es.color}15`, color: es.color,
                          border: `1px solid ${es.color}30`,
                        }}>
                          {es.label}
                        </span>
                      </td>
                      <td style={{ padding: '11px 14px' }}>
                        {enr.next_action_at ? (
                          <div style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#6b7280', fontSize: 11 }}>
                            <Clock size={10} /> {fmtDate(enr.next_action_at)}
                          </div>
                        ) : <span style={{ color: '#2d1f4a', fontSize: 11 }}>—</span>}
                      </td>
                      <td style={{ padding: '11px 14px' }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'flex-start' }}>
                          {/* Sentiment badge */}
                          {enr.reply_sentiment && (
                            <span style={{
                              display: 'inline-flex', alignItems: 'center', gap: 3,
                              padding: '2px 7px', borderRadius: 8, fontSize: 10, fontWeight: 600,
                              background: enr.reply_sentiment === 'positive' ? 'rgba(16,185,129,0.12)' : enr.reply_sentiment === 'negative' ? 'rgba(244,63,94,0.12)' : 'rgba(107,114,128,0.12)',
                              color: enr.reply_sentiment === 'positive' ? '#10b981' : enr.reply_sentiment === 'negative' ? '#f43f5e' : '#9ca3af',
                              border: `1px solid ${enr.reply_sentiment === 'positive' ? 'rgba(16,185,129,0.3)' : enr.reply_sentiment === 'negative' ? 'rgba(244,63,94,0.3)' : 'rgba(107,114,128,0.3)'}`,
                            }}>
                              {enr.reply_sentiment === 'positive' ? '✓ Interested' : enr.reply_sentiment === 'negative' ? '✗ Not interested' : '~ Neutral'}
                            </span>
                          )}
                          {/* Meeting badge */}
                          {enr.meeting_id && (
                            <span style={{
                              display: 'inline-flex', alignItems: 'center', gap: 3,
                              padding: '2px 7px', borderRadius: 8, fontSize: 10, fontWeight: 600,
                              background: 'rgba(245,158,11,0.12)', color: '#f59e0b',
                              border: '1px solid rgba(245,158,11,0.3)',
                            }}>
                              <Calendar size={9} /> Meeting pending
                            </span>
                          )}
                          {/* Action buttons */}
                          <div style={{ display: 'flex', gap: 4, marginTop: 2 }}>
                            {enr.status === 'active' && (
                              <button onClick={() => { setReplyModal(enr); setReplyContent(''); }} title="Record a reply" style={{
                                background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.3)',
                                borderRadius: 6, padding: '3px 7px', cursor: 'pointer', color: '#10b981',
                                fontSize: 10, display: 'flex', alignItems: 'center', gap: 3,
                              }}>
                                <MessageSquare size={10} /> Reply
                              </button>
                            )}
                            {enr.status !== 'active' && (
                              <button onClick={() => handleResetEnrollment(enr)} title="Reset to active" style={{
                                background: 'rgba(168,85,247,0.1)', border: '1px solid rgba(168,85,247,0.3)',
                                borderRadius: 6, padding: '3px 7px', cursor: 'pointer', color: '#a855f7',
                                fontSize: 10, display: 'flex', alignItems: 'center', gap: 3,
                              }}>
                                <RefreshCw size={10} /> Reset
                              </button>
                            )}
                          </div>
                        </div>
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
        <Dialog open={showEditStepModal} onOpenChange={setShowEditStepModal}>
          <DialogContent style={{
            background: 'linear-gradient(135deg,#0f0a1f 0%,#14082a 100%)',
            border: '1px solid #2d1f4a', color: '#e2d9f3', maxWidth: 560,
          }}>
            <DialogHeader>
              <DialogTitle style={{ color: '#e2d9f3' }}>Edit Step {editingStep.step_order}</DialogTitle>
            </DialogHeader>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
                <div>
                  <label style={labelStyle}>Step Name</label>
                  <input value={editingStep.name} onChange={e => setEditingStep(p => ({ ...p, name: e.target.value }))} style={inputStyle} />
                </div>
                <div>
                  <label style={labelStyle}>Type</label>
                  <select value={editingStep.step_type} onChange={e => setEditingStep(p => ({ ...p, step_type: e.target.value }))} style={{ ...inputStyle }}>
                    <option value="email">Email</option>
                    <option value="linkedin">LinkedIn</option>
                  </select>
                </div>
                <div>
                  <label style={labelStyle}>Day (from start)</label>
                  <input type="number" value={editingStep.delay_days} onChange={e => setEditingStep(p => ({ ...p, delay_days: parseInt(e.target.value) || 1 }))} style={inputStyle} />
                </div>
              </div>
              {editingStep.step_type === 'email' && (
                <div>
                  <label style={labelStyle}>Subject Template</label>
                  <input value={editingStep.subject_template} onChange={e => setEditingStep(p => ({ ...p, subject_template: e.target.value }))}
                    placeholder="Use {first_name}, {company_name} as placeholders" style={inputStyle} />
                </div>
              )}
              <div>
                <label style={labelStyle}>Body Template</label>
                <textarea value={editingStep.body_template} onChange={e => setEditingStep(p => ({ ...p, body_template: e.target.value }))}
                  placeholder="Use {first_name}, {company_name}, {job_title}, {company_industry} as placeholders"
                  style={{ ...inputStyle, minHeight: 140, resize: 'vertical' }} />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input type="checkbox" id="ai_p" checked={editingStep.ai_personalize}
                  onChange={e => setEditingStep(p => ({ ...p, ai_personalize: e.target.checked }))} />
                <label htmlFor="ai_p" style={{ color: '#9ca3af', fontSize: 13, cursor: 'pointer' }}>
                  <Zap size={11} style={{ display: 'inline', marginRight: 4, color: '#c084fc' }} />
                  AI personalises this step using lead signals
                </label>
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => { setShowEditStepModal(false); setEditingStep(null); }} style={{ border: '1px solid #2d1f4a', color: '#9ca3af', borderRadius: 8 }}>Cancel</Button>
              <Button onClick={handleSaveStep} disabled={savingStep} style={{
                background: 'linear-gradient(90deg,#7c3aed,#a855f7)', color: '#fff',
                border: 'none', borderRadius: 8, fontWeight: 600,
                display: 'flex', alignItems: 'center', gap: 6,
              }}>
                {savingStep ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
                Save Step
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
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

              {/* SMTP */}
              <div style={{ borderTop: '1px solid #1e0f38', paddingTop: 14 }}>
                <p style={{ color: '#9ca3af', fontSize: 12, fontWeight: 600, marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Email / SMTP Settings
                </p>
                <div style={{ marginBottom: 10, padding: '8px 12px', borderRadius: 8, background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.2)', color: '#6ee7b7', fontSize: 12 }}>
                  <b>Optional override.</b> Leave blank to use the global email settings from .env (already configured). Fill only if this campaign needs a different sender account.
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
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

      {/* ── Reply Modal ────────────────────────────────────────────────── */}
      {replyModal && (
        <Dialog open onOpenChange={() => { setReplyModal(null); setReplyContent(''); }}>
          <DialogContent style={{ background: 'linear-gradient(135deg,#0f0a1f,#14082c)', border: '1px solid #2d1f4a', maxWidth: 520 }}>
            <DialogHeader>
              <DialogTitle style={{ color: '#e2d9f3' }}>
                Record Reply from {replyModal.lead_name}
              </DialogTitle>
            </DialogHeader>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '4px 0' }}>
              <p style={{ color: '#6b7280', fontSize: 13, margin: 0 }}>
                Paste the reply email content below. AI will automatically analyse the sentiment and determine if this lead is interested.
              </p>
              <div>
                <label style={labelStyle}>Reply Content</label>
                <textarea
                  value={replyContent}
                  onChange={e => setReplyContent(e.target.value)}
                  placeholder="Paste the reply email here... (e.g. 'Thanks for reaching out, I'd love to learn more!')"
                  rows={6}
                  style={{ ...inputStyle, resize: 'vertical', fontFamily: 'inherit' }}
                />
              </div>
              <div style={{
                padding: '10px 14px', borderRadius: 8,
                background: 'rgba(168,85,247,0.06)', border: '1px solid rgba(168,85,247,0.2)',
              }}>
                <p style={{ color: '#a855f7', fontSize: 12, margin: 0, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Zap size={12} />
                  AI will classify this as positive / neutral / negative. Positive replies automatically create a meeting and send a scheduling email.
                </p>
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => { setReplyModal(null); setReplyContent(''); }}
                style={{ border: '1px solid #2d1f4a', color: '#9ca3af', borderRadius: 8 }}>
                Cancel
              </Button>
              <Button onClick={handleSubmitReply} disabled={analyzingSentiment || !replyContent.trim()} style={{
                background: 'linear-gradient(90deg,#10b981,#059669)', color: '#fff',
                border: 'none', borderRadius: 8, fontWeight: 600,
                display: 'flex', alignItems: 'center', gap: 6,
              }}>
                {analyzingSentiment ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
                {analyzingSentiment ? 'Analysing…' : 'Record Reply'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
};

export default SDROutreachTab;
