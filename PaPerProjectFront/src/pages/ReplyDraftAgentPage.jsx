import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate } from 'react-router-dom';
import { useToast } from '@/components/ui/use-toast';
import DashboardNavbar from '@/components/common/DashboardNavbar';
import { checkModuleAccess } from '@/services/modulePurchaseService';
import usePurchasedModules from '@/hooks/usePurchasedModules';
import { getAgentNavItems } from '@/utils/agentNavItems';
import {
  Reply,
  Loader2,
  Lock,
  Send,
  RefreshCw,
  Check,
  Edit3,
  Inbox,
  MailOpen,
  Sparkles,
  Search,
  FileText,
  Clock,
  Building2,
  AtSign,
  AlertCircle,
  Trash2,
  Zap,
  ChevronDown,
  CornerUpLeft,
  Quote,
  Users,
  TrendingUp,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  listPendingReplies,
  listDrafts,
  listReplyDraftCampaigns,
  listReplyDraftLeads,
  generateDraft,
  regenerateDraft,
  approveDraft,
  rejectDraft,
  sendDraft,
} from '@/services/replyDraftService';

const DAYS_FILTERS = [
  { value: '',   label: 'All time' },
  { value: '1',  label: 'Last 24h' },
  { value: '7',  label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
];

const TONES = [
  { value: 'professional', label: 'Professional' },
  { value: 'friendly',     label: 'Friendly' },
  { value: 'formal',       label: 'Formal' },
  { value: 'casual',       label: 'Casual' },
  { value: 'apologetic',   label: 'Apologetic' },
  { value: 'confident',    label: 'Confident' },
  { value: 'empathetic',   label: 'Empathetic' },
];

const INTEREST_STYLES = {
  positive:       { label: 'Interested',       className: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' },
  requested_info: { label: 'Needs Info',       className: 'bg-sky-500/15 text-sky-300 border-sky-500/30' },
  objection:      { label: 'Objection',        className: 'bg-amber-500/15 text-amber-300 border-amber-500/30' },
  negative:       { label: 'Not Interested',   className: 'bg-rose-500/15 text-rose-300 border-rose-500/30' },
  unsubscribe:    { label: 'Unsubscribe',      className: 'bg-red-500/15 text-red-300 border-red-500/30' },
  neutral:        { label: 'Neutral',          className: 'bg-slate-500/15 text-slate-300 border-slate-500/30' },
  not_analyzed:   { label: 'Not Analyzed',     className: 'bg-white/5 text-gray-400 border-white/10' },
};

const STATUS_STYLES = {
  pending:  { label: 'Pending',  className: 'bg-amber-500/15 text-amber-300 border-amber-500/30' },
  approved: { label: 'Approved', className: 'bg-sky-500/15 text-sky-300 border-sky-500/30' },
  sent:     { label: 'Sent',     className: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' },
  rejected: { label: 'Discarded',className: 'bg-rose-500/15 text-rose-300 border-rose-500/30' },
  failed:   { label: 'Failed',   className: 'bg-red-500/15 text-red-300 border-red-500/30' },
};

const AVATAR_PALETTE = [
  'from-cyan-500 to-blue-600',
  'from-fuchsia-500 to-purple-600',
  'from-emerald-500 to-teal-600',
  'from-amber-500 to-orange-600',
  'from-rose-500 to-pink-600',
  'from-indigo-500 to-violet-600',
];

const initialsOf = (name, email) => {
  const base = (name || email || '?').trim();
  if (!base) return '?';
  const parts = base.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
};

const paletteFor = (seed = '') => {
  let sum = 0;
  for (let i = 0; i < seed.length; i++) sum = (sum + seed.charCodeAt(i)) % AVATAR_PALETTE.length;
  return AVATAR_PALETTE[sum];
};

const formatRelative = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
};

const formatDateTime = (iso) => {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
  });
};

// Split an email body into the sender's new reply vs. the quoted original thread.
// Handles "On <date>, <addr> wrote:", "-----Original Message-----", "From: ... Sent: ..."
// headers, and leading `>` quoted blocks.
const parseReplyBody = (body) => {
  const empty = { reply: '', quoted: '' };
  if (!body) return empty;
  const text = body.replace(/\r\n/g, '\n');
  const lines = text.split('\n');
  let splitIdx = -1;
  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i].trim();
    if (/^on\s.+\swrote:\s*$/i.test(ln)) { splitIdx = i; break; }
    if (/^-{2,}\s*original message\s*-{2,}\s*$/i.test(ln)) { splitIdx = i; break; }
    if (/^from:\s/i.test(ln)) {
      const next = (lines[i + 1] || '').trim();
      if (/^(sent|date|to):\s/i.test(next)) { splitIdx = i; break; }
    }
    if (ln.startsWith('>')) {
      let j = i - 1;
      while (j >= 0 && !lines[j].trim()) j--;
      splitIdx = (j >= 0 && /wrote:\s*$/i.test(lines[j].trim())) ? j : i;
      break;
    }
  }
  if (splitIdx === -1) return { reply: text.trim(), quoted: '' };
  const reply = lines.slice(0, splitIdx).join('\n').replace(/\n+$/g, '').trim();
  const quoted = lines.slice(splitIdx).join('\n').trim();
  return { reply, quoted };
};

// Strip leading '> ' markers so quoted text reads naturally.
const cleanQuoted = (quoted) =>
  quoted
    .split('\n')
    .map((l) => l.replace(/^>+\s?/, ''))
    .join('\n')
    .trim();

const Avatar = ({ name, email, size = 'md' }) => {
  const dim = size === 'lg' ? 'h-11 w-11 text-sm' : size === 'sm' ? 'h-8 w-8 text-[11px]' : 'h-10 w-10 text-xs';
  const palette = paletteFor(email || name || '');
  return (
    <div className={`${dim} shrink-0 rounded-full bg-gradient-to-br ${palette} flex items-center justify-center font-bold text-white shadow-md ring-1 ring-white/10`}>
      {initialsOf(name, email)}
    </div>
  );
};

const EmptyState = ({ icon: Icon, title, subtitle }) => (
  <div className="flex flex-col items-center justify-center text-center py-16 px-6">
    <div className="h-14 w-14 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center mb-4">
      <Icon className="h-7 w-7 text-gray-400" />
    </div>
    <div className="text-sm font-semibold text-white">{title}</div>
    {subtitle && <div className="text-xs text-gray-400 mt-1 max-w-xs">{subtitle}</div>}
  </div>
);

const ReplyDraftAgentPage = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [companyUser, setCompanyUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [hasAccess, setHasAccess] = useState(false);
  const [checkingAccess, setCheckingAccess] = useState(true);
  const [activeSection] = useState('reply-draft');
  const { purchasedModules, modulesLoaded } = usePurchasedModules();

  const [pendingReplies, setPendingReplies] = useState([]);
  const [drafts, setDrafts] = useState([]);
  const [selectedReply, setSelectedReply] = useState(null);
  const [selectedDraft, setSelectedDraft] = useState(null);
  const [tone, setTone] = useState('professional');
  const [userContext, setUserContext] = useState('');
  const [editedSubject, setEditedSubject] = useState('');
  const [editedBody, setEditedBody] = useState('');
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState('inbox'); // inbox | drafts | sent
  const [search, setSearch] = useState('');
  const [campaigns, setCampaigns] = useState([]);
  const [campaignFilter, setCampaignFilter] = useState(''); // '' = all, 'none' = generic only, or campaign id
  const [daysFilter, setDaysFilter] = useState('');           // '' = all, '1' | '7' | '30'
  const [leads, setLeads] = useState([]);
  const [leadsHasRepliedFilter, setLeadsHasRepliedFilter] = useState(''); // '' | 'yes' | 'no'

  useEffect(() => {
    const companyUserStr = localStorage.getItem('company_user');
    if (!companyUserStr) {
      toast({ title: 'Not logged in', description: 'Please log in to access the reply draft agent', variant: 'destructive' });
      navigate('/company/login');
      return;
    }
    try {
      setCompanyUser(JSON.parse(companyUserStr));
      (async () => {
        try {
          const res = await checkModuleAccess('reply_draft_agent');
          if (res.status === 'success') setHasAccess(res.has_access);
        } catch {
          setHasAccess(true);
        } finally {
          setCheckingAccess(false);
          setLoading(false);
        }
      })();
    } catch {
      localStorage.removeItem('company_user');
      navigate('/company/login');
    }
  }, [navigate, toast]);

  const refreshInbox = useCallback(async () => {
    try {
      const res = await listPendingReplies({ campaign: campaignFilter, days: daysFilter });
      setPendingReplies(res?.data || []);
    } catch (e) {
      toast({ title: 'Failed to load inbox', description: e.message, variant: 'destructive' });
    }
  }, [toast, campaignFilter, daysFilter]);

  const refreshDrafts = useCallback(async () => {
    try {
      const res = await listDrafts();
      setDrafts(res?.data || []);
    } catch (e) {
      toast({ title: 'Failed to load drafts', description: e.message, variant: 'destructive' });
    }
  }, [toast]);

  const refreshCampaigns = useCallback(async () => {
    try {
      const res = await listReplyDraftCampaigns();
      setCampaigns(res?.data || []);
    } catch (e) {
      // Non-fatal — filter dropdown just shows no campaigns.
      console.error('Failed to load campaigns', e);
    }
  }, []);

  const refreshLeads = useCallback(async () => {
    try {
      const res = await listReplyDraftLeads({
        hasReplied: leadsHasRepliedFilter,
        campaign: campaignFilter && campaignFilter !== 'none' ? campaignFilter : '',
      });
      setLeads(res?.data || []);
    } catch (e) {
      console.error('Failed to load leads', e);
    }
  }, [leadsHasRepliedFilter, campaignFilter]);

  const refreshAll = useCallback(async () => {
    setRefreshing(true);
    try {
      await Promise.all([refreshInbox(), refreshDrafts(), refreshLeads()]);
    } finally {
      setRefreshing(false);
    }
  }, [refreshInbox, refreshDrafts, refreshLeads]);

  useEffect(() => {
    if (hasAccess) {
      refreshCampaigns();
      refreshAll();
    }
  }, [hasAccess, refreshCampaigns, refreshAll]);

  // Re-fetch the inbox whenever the user changes a filter.
  useEffect(() => {
    if (hasAccess) refreshInbox();
  }, [hasAccess, campaignFilter, daysFilter, refreshInbox]);

  // Re-fetch leads whenever the leads-scoped filters change.
  useEffect(() => {
    if (hasAccess && activeTab === 'leads') refreshLeads();
  }, [hasAccess, activeTab, leadsHasRepliedFilter, campaignFilter, refreshLeads]);

  const handleLogout = () => {
    localStorage.removeItem('company_auth_token');
    localStorage.removeItem('company_user');
    localStorage.removeItem('company_purchased_modules');
    navigate('/company/login');
  };

  const clearSelection = () => {
    setSelectedReply(null);
    setSelectedDraft(null);
    setEditedSubject('');
    setEditedBody('');
    setUserContext('');
  };

  const handleSelectReply = (r) => {
    setSelectedReply(r);
    setSelectedDraft(null);
    setEditedBody('');
    setEditedSubject('');
    setUserContext('');
  };

  const handleSelectDraft = (d) => {
    setSelectedDraft(d);
    setSelectedReply(null);
    setEditedSubject(d.subject || '');
    setEditedBody(d.body || '');
    setTone(d.tone || 'professional');
  };

  const handleGenerate = async () => {
    if (!selectedReply) return;
    setBusy(true);
    try {
      const isInbox = selectedReply.source === 'inbox';
      const res = await generateDraft({
        originalEmailId: isInbox ? null : selectedReply.id,
        inboxEmailId: isInbox ? selectedReply.id : null,
        userContext,
        tone,
      });
      const d = res?.data;
      if (d?.draft_id) {
        toast({ title: 'Draft generated', description: 'Review it below before sending.' });
        setEditedSubject(d.subject);
        setEditedBody(d.body);
        setSelectedDraft({
          id: d.draft_id,
          status: 'pending',
          source: d.source || (isInbox ? 'inbox' : 'reply'),
          subject: d.subject,
          body: d.body,
          tone,
          ai_notes: d.reasoning,
          to_email: selectedReply.from_email,
          to_name: selectedReply.from_name,
          to_company: selectedReply.from_company,
          original_subject: selectedReply.subject,
          original_body: selectedReply.body,
        });
        refreshAll();
      }
    } catch (e) {
      toast({ title: 'Generation failed', description: e.message, variant: 'destructive' });
    } finally {
      setBusy(false);
    }
  };

  const handleRegenerate = async () => {
    if (!selectedDraft) return;
    setBusy(true);
    try {
      const res = await regenerateDraft(selectedDraft.id, {
        newInstructions: userContext,
        tone,
      });
      const d = res?.data;
      if (d?.draft_id) {
        toast({ title: 'Regenerated' });
        setEditedSubject(d.subject);
        setEditedBody(d.body);
        setSelectedDraft({ ...selectedDraft, id: d.draft_id, subject: d.subject, body: d.body, ai_notes: d.reasoning });
        refreshDrafts();
      }
    } catch (e) {
      toast({ title: 'Regeneration failed', description: e.message, variant: 'destructive' });
    } finally {
      setBusy(false);
    }
  };

  const handleApproveAndSend = async () => {
    if (!selectedDraft) return;
    setBusy(true);
    try {
      const ap = await approveDraft(selectedDraft.id, {
        editedSubject,
        editedBody,
      });
      if (ap.status !== 'success') throw new Error(ap.message || 'Approve failed');
      const sent = await sendDraft(selectedDraft.id);
      if (sent.status === 'success') {
        toast({ title: 'Reply sent', description: `Delivered to ${selectedDraft.to_email || 'recipient'}.` });
        clearSelection();
        refreshAll();
      } else {
        throw new Error(sent.message || 'Send failed');
      }
    } catch (e) {
      toast({ title: 'Send failed', description: e.message, variant: 'destructive' });
    } finally {
      setBusy(false);
    }
  };

  const handleReject = async () => {
    if (!selectedDraft) return;
    setBusy(true);
    try {
      await rejectDraft(selectedDraft.id);
      toast({ title: 'Draft discarded', description: 'The original message is back in your inbox.' });
      clearSelection();
      // Refresh BOTH lists — inbox picks the original back up, drafts loses this row.
      refreshAll();
    } catch (e) {
      toast({ title: 'Discard failed', description: e.message, variant: 'destructive' });
    } finally {
      setBusy(false);
    }
  };

  const filteredInbox = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return pendingReplies;
    return pendingReplies.filter((r) =>
      [r.from_name, r.from_email, r.subject, r.from_company].some((v) => (v || '').toLowerCase().includes(q))
    );
  }, [pendingReplies, search]);

  const unsentDrafts = useMemo(
    () => drafts.filter((d) => d.status !== 'sent' && d.status !== 'rejected'),
    [drafts]
  );

  const sentDrafts = useMemo(
    () => drafts.filter((d) => d.status === 'sent'),
    [drafts]
  );

  const filteredUnsentDrafts = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return unsentDrafts;
    return unsentDrafts.filter((d) =>
      [d.to_name, d.to_email, d.subject, d.to_company].some((v) => (v || '').toLowerCase().includes(q))
    );
  }, [unsentDrafts, search]);

  const filteredSentDrafts = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return sentDrafts;
    return sentDrafts.filter((d) =>
      [d.to_name, d.to_email, d.subject, d.to_company].some((v) => (v || '').toLowerCase().includes(q))
    );
  }, [sentDrafts, search]);

  const filteredLeads = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return leads;
    return leads.filter((l) =>
      [l.full_name, l.email, l.company, l.job_title].some((v) => (v || '').toLowerCase().includes(q))
    );
  }, [leads, search]);

  const stats = useMemo(() => ({
    pending: pendingReplies.length,
    draftsPending: drafts.filter((d) => d.status === 'pending').length,
    sent: drafts.filter((d) => d.status === 'sent').length,
    failed: drafts.filter((d) => d.status === 'failed').length,
  }), [pendingReplies, drafts]);

  if (loading || checkingAccess || !modulesLoaded) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!companyUser) return null;

  if (!hasAccess) {
    return (
      <>
        <Helmet><title>Access Denied | Reply Draft Agent</title></Helmet>
        <div className="min-h-screen bg-background flex items-center justify-center p-4">
          <Card className="max-w-md w-full">
            <CardHeader>
              <div className="flex items-center justify-center mb-4">
                <Lock className="h-12 w-12 text-muted-foreground" />
              </div>
              <CardTitle className="text-center">Module Not Purchased</CardTitle>
              <CardDescription className="text-center">
                You need to purchase the Reply Draft Agent module to access this dashboard.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Button onClick={() => navigate('/')} className="w-full">Go to Home to Purchase</Button>
              <Button onClick={() => navigate('/company/dashboard')} variant="outline" className="w-full">Back to Dashboard</Button>
            </CardContent>
          </Card>
        </div>
      </>
    );
  }

  const selectedContact = selectedReply
    ? { name: selectedReply.from_name, email: selectedReply.from_email, company: selectedReply.from_company, jobTitle: selectedReply.from_job_title }
    : selectedDraft
      ? { name: selectedDraft.to_name, email: selectedDraft.to_email, company: selectedDraft.to_company }
      : null;

  const originalEmail = selectedReply || (selectedDraft
    ? { subject: selectedDraft.original_subject, body: selectedDraft.original_body, replied_at: selectedDraft.created_at }
    : null);

  const isReadOnly = selectedDraft?.status === 'sent' || selectedDraft?.status === 'rejected';

  return (
    <>
      <Helmet><title>Reply Draft Agent | Pay Per Project</title></Helmet>
      <div
        className="min-h-screen"
        style={{ background: 'linear-gradient(135deg, #020308 0%, #0a0a1a 25%, #0d0b1f 50%, #0f0a20 75%, #020308 100%)' }}
      >
        <DashboardNavbar
          icon={Reply}
          title={companyUser.companyName || 'Reply Draft Agent'}
          subtitle={companyUser.fullName}
          user={companyUser}
          userRole="Company User"
          showNavTabs={true}
          activeSection={activeSection}
          onLogout={handleLogout}
          navItems={getAgentNavItems(purchasedModules, 'reply-draft', navigate)}
        />

        <div className="container mx-auto px-4 sm:px-6 py-6 max-w-[1500px]">
          {/* Page Header with Refresh */}
          <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
            <div>
              <h1 className="text-lg font-bold text-white">Reply Draft Workspace</h1>
              <p className="text-xs text-gray-400">
                {refreshing ? 'Syncing from your mailbox…' : 'Click refresh to pull the latest from your inbox and drafts.'}
              </p>
            </div>
            <Button
              onClick={refreshAll}
              disabled={refreshing}
              className="bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-semibold shadow-lg shadow-cyan-500/20 disabled:opacity-60"
            >
              <RefreshCw className={`h-4 w-4 mr-2 ${refreshing ? 'animate-spin' : ''}`} />
              {refreshing ? 'Refreshing…' : 'Refresh'}
            </Button>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <StatCard icon={Inbox} label="Pending Replies" value={stats.pending} tint="from-cyan-500/20 to-blue-500/10" iconTint="text-cyan-300" />
            <StatCard icon={FileText} label="Drafts to Review" value={stats.draftsPending} tint="from-amber-500/20 to-orange-500/10" iconTint="text-amber-300" />
            <StatCard icon={Send} label="Sent" value={stats.sent} tint="from-emerald-500/20 to-teal-500/10" iconTint="text-emerald-300" />
            <StatCard icon={AlertCircle} label="Failed" value={stats.failed} tint="from-rose-500/20 to-red-500/10" iconTint="text-rose-300" />
          </div>

          {/* Main Workspace */}
          <div className="grid grid-cols-12 gap-4 items-stretch">
            {/* LEFT: List */}
            <div className="col-span-12 lg:col-span-4 xl:col-span-3">
              <div className="rounded-2xl bg-black/40 border border-white/10 backdrop-blur-sm overflow-hidden flex flex-col lg:h-[calc(100vh-220px)]">
                {/* Tabs */}
                <div className="p-2 border-b border-white/10 flex items-center gap-2">
                  <div className="flex-1 flex gap-1">
                    <button
                      onClick={() => setActiveTab('inbox')}
                      className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                      activeTab === 'inbox'
                        ? 'bg-gradient-to-r from-cyan-500/20 to-blue-500/20 text-cyan-200 border border-cyan-500/30'
                        : 'text-gray-400 hover:text-white hover:bg-white/5'
                    }`}
                    >
                      <Inbox className="h-4 w-4" />
                      Inbox
                      {pendingReplies.length > 0 && (
                        <span className={`ml-1 text-[10px] font-bold px-1.5 py-0.5 rounded-full ${activeTab === 'inbox' ? 'bg-cyan-500/30 text-cyan-100' : 'bg-white/10 text-gray-300'}`}>
                          {pendingReplies.length}
                        </span>
                      )}
                    </button>
                    <button
                      onClick={() => setActiveTab('drafts')}
                      className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                      activeTab === 'drafts'
                        ? 'bg-gradient-to-r from-fuchsia-500/20 to-purple-500/20 text-fuchsia-200 border border-fuchsia-500/30'
                        : 'text-gray-400 hover:text-white hover:bg-white/5'
                    }`}
                    >
                      <Edit3 className="h-4 w-4" />
                      Drafts
                      {unsentDrafts.length > 0 && (
                        <span className={`ml-1 text-[10px] font-bold px-1.5 py-0.5 rounded-full ${activeTab === 'drafts' ? 'bg-fuchsia-500/30 text-fuchsia-100' : 'bg-white/10 text-gray-300'}`}>
                          {unsentDrafts.length}
                        </span>
                      )}
                    </button>
                    <button
                      onClick={() => setActiveTab('sent')}
                      className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                        activeTab === 'sent'
                          ? 'bg-gradient-to-r from-emerald-500/20 to-teal-500/20 text-emerald-200 border border-emerald-500/30'
                          : 'text-gray-400 hover:text-white hover:bg-white/5'
                      }`}
                    >
                      <Check className="h-4 w-4" />
                      Sent
                      {sentDrafts.length > 0 && (
                        <span className={`ml-1 text-[10px] font-bold px-1.5 py-0.5 rounded-full ${activeTab === 'sent' ? 'bg-emerald-500/30 text-emerald-100' : 'bg-white/10 text-gray-300'}`}>
                          {sentDrafts.length}
                        </span>
                      )}
                    </button>
                    <button
                      onClick={() => setActiveTab('leads')}
                      className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                        activeTab === 'leads'
                          ? 'bg-gradient-to-r from-indigo-500/20 to-violet-500/20 text-indigo-200 border border-indigo-500/30'
                          : 'text-gray-400 hover:text-white hover:bg-white/5'
                      }`}
                    >
                      <Users className="h-4 w-4" />
                      Leads
                      {leads.length > 0 && (
                        <span className={`ml-1 text-[10px] font-bold px-1.5 py-0.5 rounded-full ${activeTab === 'leads' ? 'bg-indigo-500/30 text-indigo-100' : 'bg-white/10 text-gray-300'}`}>
                          {leads.length}
                        </span>
                      )}
                    </button>
                  </div>
                </div>

                {/* Search */}
                <div className="p-3 border-b border-white/10 space-y-2">
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
                    <input
                      type="text"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder={
                        activeTab === 'inbox'
                          ? 'Search replies…'
                          : activeTab === 'drafts'
                            ? 'Search unsent drafts…'
                            : activeTab === 'sent'
                              ? 'Search sent replies…'
                              : 'Search leads…'
                      }
                      className="w-full bg-white/5 border border-white/10 rounded-lg pl-9 pr-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500/50 focus:bg-white/10 transition"
                    />
                  </div>

                  {activeTab === 'inbox' && (
                    <div className="grid grid-cols-2 gap-2">
                      <select
                        value={campaignFilter}
                        onChange={(e) => setCampaignFilter(e.target.value)}
                        title="Filter by campaign"
                        className="bg-white/5 border border-white/10 rounded-lg px-2 py-2 text-xs text-white focus:outline-none focus:border-cyan-500/50 focus:bg-white/10 transition"
                      >
                        <option value="" className="bg-gray-900">All campaigns</option>
                        <option value="none" className="bg-gray-900">No campaign (inbox)</option>
                        {campaigns.map((c) => (
                          <option key={c.id} value={String(c.id)} className="bg-gray-900">
                            {c.name}
                          </option>
                        ))}
                      </select>
                      <select
                        value={daysFilter}
                        onChange={(e) => setDaysFilter(e.target.value)}
                        title="Filter by time"
                        className="bg-white/5 border border-white/10 rounded-lg px-2 py-2 text-xs text-white focus:outline-none focus:border-cyan-500/50 focus:bg-white/10 transition"
                      >
                        {DAYS_FILTERS.map((d) => (
                          <option key={d.value || 'all'} value={d.value} className="bg-gray-900">
                            {d.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}

                  {activeTab === 'leads' && (
                    <div className="grid grid-cols-2 gap-2">
                      <select
                        value={campaignFilter}
                        onChange={(e) => setCampaignFilter(e.target.value)}
                        title="Filter by campaign"
                        className="bg-white/5 border border-white/10 rounded-lg px-2 py-2 text-xs text-white focus:outline-none focus:border-cyan-500/50 focus:bg-white/10 transition"
                      >
                        <option value="" className="bg-gray-900">All campaigns</option>
                        {campaigns.map((c) => (
                          <option key={c.id} value={String(c.id)} className="bg-gray-900">
                            {c.name}
                          </option>
                        ))}
                      </select>
                      <select
                        value={leadsHasRepliedFilter}
                        onChange={(e) => setLeadsHasRepliedFilter(e.target.value)}
                        title="Filter by reply status"
                        className="bg-white/5 border border-white/10 rounded-lg px-2 py-2 text-xs text-white focus:outline-none focus:border-cyan-500/50 focus:bg-white/10 transition"
                      >
                        <option value="" className="bg-gray-900">All leads</option>
                        <option value="yes" className="bg-gray-900">Replied</option>
                        <option value="no" className="bg-gray-900">Not replied</option>
                      </select>
                    </div>
                  )}
                </div>

                {/* List */}
                <div className="custom-scrollbar lg:flex-1 lg:min-h-0 lg:overflow-y-auto">
                  {activeTab === 'inbox' && (
                    <>
                      {filteredInbox.length === 0 ? (
                        <EmptyState
                          icon={Inbox}
                          title={search ? 'No matches' : (campaignFilter || daysFilter ? 'Nothing in this filter' : 'Inbox is clear')}
                          subtitle={
                            search
                              ? 'Try a different search term.'
                              : (campaignFilter || daysFilter)
                                ? 'Try widening the campaign or time range.'
                                : 'Replies and inbox mail will appear here.'
                          }
                        />
                      ) : (
                        filteredInbox.map((r) => (
                          <InboxItem
                            key={r.id}
                            reply={r}
                            active={selectedReply?.id === r.id}
                            onClick={() => handleSelectReply(r)}
                          />
                        ))
                      )}
                    </>
                  )}
                  {activeTab === 'drafts' && (
                    <>
                      {filteredUnsentDrafts.length === 0 ? (
                        <EmptyState
                          icon={FileText}
                          title={search ? 'No matches' : 'No drafts yet'}
                          subtitle={search ? 'Try a different search term.' : 'Drafts generated and not sent will appear here.'}
                        />
                      ) : (
                        filteredUnsentDrafts.map((d) => (
                          <DraftItem
                            key={d.id}
                            draft={d}
                            active={selectedDraft?.id === d.id}
                            onClick={() => handleSelectDraft(d)}
                          />
                        ))
                      )}
                    </>
                  )}
                  {activeTab === 'sent' && (
                    <>
                      {filteredSentDrafts.length === 0 ? (
                        <EmptyState
                          icon={Send}
                          title={search ? 'No matches' : 'No sent replies yet'}
                          subtitle={search ? 'Try a different search term.' : 'Approved drafts that were sent will appear here.'}
                        />
                      ) : (
                        filteredSentDrafts.map((d) => (
                          <DraftItem
                            key={d.id}
                            draft={d}
                            active={selectedDraft?.id === d.id}
                            onClick={() => handleSelectDraft(d)}
                          />
                        ))
                      )}
                    </>
                  )}
                </div>
              </div>
            </div>

            {/* RIGHT: Detail + Composer */}
            <div className="col-span-12 lg:col-span-8 xl:col-span-9 space-y-4 pr-1 lg:h-[calc(100vh-220px)] lg:overflow-y-auto custom-scrollbar">
              {!selectedReply && !selectedDraft && (
                <div className="rounded-2xl bg-black/40 border border-white/10 backdrop-blur-sm min-h-[68vh] flex items-center justify-center">
                  <div className="text-center max-w-md px-6">
                    <div className="h-20 w-20 mx-auto rounded-2xl bg-gradient-to-br from-cyan-500/20 to-fuchsia-500/20 border border-white/10 flex items-center justify-center mb-5">
                      <MailOpen className="h-10 w-10 text-cyan-300" />
                    </div>
                    <h3 className="text-xl font-bold text-white mb-2">Select a message to begin</h3>
                    <p className="text-sm text-gray-400">
                      Pick an incoming reply from the <span className="text-cyan-300 font-medium">Inbox</span> to generate an AI draft,
                      or open an existing <span className="text-fuchsia-300 font-medium">Draft</span> to review and send it.
                    </p>
                  </div>
                </div>
              )}

              {/* Original Email Viewer */}
              {(selectedReply || selectedDraft) && originalEmail && (
                <div className="rounded-2xl bg-black/40 border border-white/10 backdrop-blur-sm overflow-hidden">
                  <div className="p-5 border-b border-white/10">
                    <div className="flex items-start justify-between gap-4 mb-4">
                      <div className="flex items-start gap-3 min-w-0 flex-1">
                        <Avatar name={selectedContact?.name} email={selectedContact?.email} size="lg" />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-base font-semibold text-white truncate">
                              {selectedContact?.name || selectedContact?.email || 'Unknown sender'}
                            </span>
                            {selectedReply?.interest_level && INTEREST_STYLES[selectedReply.interest_level] && (
                              <Badge variant="outline" className={`${INTEREST_STYLES[selectedReply.interest_level].className} border`}>
                                {INTEREST_STYLES[selectedReply.interest_level].label}
                              </Badge>
                            )}
                          </div>
                          <div className="flex items-center gap-3 mt-1 text-xs text-gray-400 flex-wrap">
                            <span className="flex items-center gap-1">
                              <AtSign className="h-3 w-3" />
                              {selectedContact?.email || '—'}
                            </span>
                            {selectedContact?.company && (
                              <span className="flex items-center gap-1">
                                <Building2 className="h-3 w-3" />
                                {selectedContact.company}
                                {selectedContact.jobTitle && <span className="text-gray-500"> · {selectedContact.jobTitle}</span>}
                              </span>
                            )}
                            {originalEmail.replied_at && (
                              <span className="flex items-center gap-1">
                                <Clock className="h-3 w-3" />
                                {formatDateTime(originalEmail.replied_at)}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                      {selectedReply?.campaign && (
                        <div className="hidden md:flex items-center gap-1.5 text-xs text-gray-400 bg-white/5 border border-white/10 rounded-full px-3 py-1">
                          <Zap className="h-3 w-3" />
                          {selectedReply.campaign}
                        </div>
                      )}
                    </div>
                    <h2 className="text-lg font-bold text-white leading-snug">
                      {originalEmail.subject || '(no subject)'}
                    </h2>
                  </div>

                  <div className="p-5">
                    <EmailBody body={originalEmail.body} isIncomingReply={!!selectedReply} />
                    {selectedReply?.analysis && (
                      <div className="mt-4 p-3 rounded-lg bg-cyan-500/5 border border-cyan-500/20 flex gap-2.5">
                        <Sparkles className="h-4 w-4 text-cyan-300 shrink-0 mt-0.5" />
                        <div>
                          <div className="text-xs font-semibold text-cyan-200 mb-0.5">AI Analysis</div>
                          <div className="text-xs text-gray-300 leading-relaxed">{selectedReply.analysis}</div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Composer / Draft Editor */}
              {(selectedReply || selectedDraft) && (
                <div className="rounded-2xl bg-black/40 border border-white/10 backdrop-blur-sm overflow-hidden">
                  <div className="p-5 border-b border-white/10 flex items-center justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-3">
                      <div className="h-9 w-9 rounded-lg bg-gradient-to-br from-fuchsia-500/30 to-purple-600/30 border border-fuchsia-500/30 flex items-center justify-center">
                        <Sparkles className="h-4 w-4 text-fuchsia-200" />
                      </div>
                      <div>
                        <h3 className="text-sm font-bold text-white">
                          {selectedReply && !selectedDraft
                            ? 'Generate AI Draft'
                            : isReadOnly
                              ? 'Draft Details'
                              : 'Review & Send Draft'}
                        </h3>
                        <p className="text-xs text-gray-400">
                          {selectedReply && !selectedDraft
                            ? 'Pick a tone, add guidance, and let the agent draft the reply.'
                            : isReadOnly
                              ? 'This draft is read-only.'
                              : 'Edit the draft below — your changes are what gets sent.'}
                        </p>
                      </div>
                    </div>
                    {selectedDraft && (
                      <div className="flex items-center gap-2">
                        {STATUS_STYLES[selectedDraft.status] && (
                          <Badge variant="outline" className={`${STATUS_STYLES[selectedDraft.status].className} border`}>
                            {STATUS_STYLES[selectedDraft.status].label}
                          </Badge>
                        )}
                        {selectedDraft.regeneration_count > 0 && (
                          <Badge variant="outline" className="bg-white/5 text-gray-300 border-white/10">
                            Regen ×{selectedDraft.regeneration_count}
                          </Badge>
                        )}
                      </div>
                    )}
                  </div>

                  <div className="p-5 space-y-4">
                    {/* Tone + Instructions */}
                    {!isReadOnly && (
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div>
                          <label className="text-xs font-medium text-gray-300 mb-1.5 block">Tone</label>
                          <select
                            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-500/50 focus:bg-white/10 transition"
                            value={tone}
                            onChange={(e) => setTone(e.target.value)}
                            disabled={busy}
                          >
                            {TONES.map((t) => (<option key={t.value} value={t.value} className="bg-gray-900">{t.label}</option>))}
                          </select>
                        </div>
                        <div className="md:col-span-2">
                          <label className="text-xs font-medium text-gray-300 mb-1.5 block">
                            {selectedDraft ? 'Additional instructions (regenerate)' : 'Instructions for AI'}
                            <span className="text-gray-500 font-normal"> — optional</span>
                          </label>
                          <input
                            type="text"
                            value={userContext}
                            onChange={(e) => setUserContext(e.target.value)}
                            disabled={busy}
                            placeholder="e.g. keep it brief, propose a demo next Tuesday…"
                            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500/50 focus:bg-white/10 transition"
                          />
                        </div>
                      </div>
                    )}

                    {/* Generate button when no draft yet */}
                    {selectedReply && !selectedDraft && (
                      <Button
                        onClick={handleGenerate}
                        disabled={busy}
                        className="w-full bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-semibold shadow-lg shadow-cyan-500/20 h-11"
                      >
                        {busy ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Sparkles className="h-4 w-4 mr-2" />}
                        {busy ? 'Drafting reply…' : 'Generate AI Draft'}
                      </Button>
                    )}

                    {/* Draft editor */}
                    {selectedDraft && (
                      <>
                        <div>
                          <label className="text-xs font-medium text-gray-300 mb-1.5 block">Subject</label>
                          <input
                            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500/50 focus:bg-white/10 transition disabled:opacity-60"
                            value={editedSubject}
                            onChange={(e) => setEditedSubject(e.target.value)}
                            disabled={busy || isReadOnly}
                          />
                        </div>
                        <div>
                          <label className="text-xs font-medium text-gray-300 mb-1.5 block">Message Body</label>
                          <textarea
                            className="w-full bg-white/5 border border-white/10 rounded-lg p-3 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500/50 focus:bg-white/10 transition disabled:opacity-60 font-sans leading-relaxed min-h-[180px] max-h-[48vh] overflow-y-auto resize-y"
                            rows={9}
                            value={editedBody}
                            onChange={(e) => setEditedBody(e.target.value)}
                            disabled={busy || isReadOnly}
                          />
                          <div className="text-xs text-gray-500 mt-1.5 flex items-center justify-between">
                            <span>{editedBody.length} characters · ~{editedBody.trim().split(/\s+/).filter(Boolean).length} words</span>
                            {selectedDraft.updated_at && (
                              <span>Last updated {formatRelative(selectedDraft.updated_at)}</span>
                            )}
                          </div>
                        </div>

                        {selectedDraft.ai_notes && (
                          <div className="p-3 rounded-lg bg-fuchsia-500/5 border border-fuchsia-500/20 flex gap-2.5">
                            <Sparkles className="h-4 w-4 text-fuchsia-300 shrink-0 mt-0.5" />
                            <div>
                              <div className="text-xs font-semibold text-fuchsia-200 mb-0.5">AI Reasoning</div>
                              <div className="text-xs text-gray-300 leading-relaxed italic">{selectedDraft.ai_notes}</div>
                            </div>
                          </div>
                        )}

                        {selectedDraft.status === 'sent' && (
                          <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-200 text-sm flex items-center gap-2">
                            <Check className="h-4 w-4" />
                            Sent on {formatDateTime(selectedDraft.sent_at)} to {selectedDraft.to_email}
                          </div>
                        )}

                        {selectedDraft.status === 'failed' && selectedDraft.send_error && (
                          <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-200 text-xs flex gap-2">
                            <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                            <div>
                              <div className="font-semibold mb-0.5">Send failed</div>
                              <div className="text-red-300/80">{selectedDraft.send_error}</div>
                            </div>
                          </div>
                        )}

                        {!isReadOnly && (
                          <div className="flex items-center justify-between gap-2 flex-wrap pt-2 border-t border-white/10">
                            <Button
                              onClick={handleReject}
                              disabled={busy}
                              variant="outline"
                              className="bg-transparent border-rose-500/30 text-rose-300 hover:bg-rose-500/10 hover:text-rose-200"
                            >
                              <Trash2 className="h-4 w-4 mr-2" />
                              Discard
                            </Button>
                            <div className="flex items-center gap-2">
                              <Button
                                onClick={handleRegenerate}
                                disabled={busy}
                                variant="outline"
                                className="bg-white/5 border-white/10 text-white hover:bg-white/10"
                              >
                                {busy ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <RefreshCw className="h-4 w-4 mr-2" />}
                                Regenerate
                              </Button>
                              <Button
                                onClick={handleApproveAndSend}
                                disabled={busy || !editedBody.trim() || !editedSubject.trim()}
                                className="bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white font-semibold shadow-lg shadow-emerald-500/20"
                              >
                                {busy ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Send className="h-4 w-4 mr-2" />}
                                Approve & Send
                              </Button>
                            </div>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <style>{`
        .custom-scrollbar::-webkit-scrollbar { width: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 3px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.15); }
      `}</style>
    </>
  );
};

const EmailBody = ({ body, isIncomingReply }) => {
  const [showQuoted, setShowQuoted] = useState(false);
  if (!body || !body.trim()) {
    return <div className="text-sm text-gray-500 italic">No content.</div>;
  }
  const { reply, quoted } = parseReplyBody(body);
  const replyLabel = isIncomingReply ? "Their reply" : "Message";

  // Nothing was detected as a quote — render the whole body as the message.
  if (!quoted) {
    return (
      <div>
        <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-cyan-300 mb-2">
          <CornerUpLeft className="h-3 w-3" />
          {replyLabel}
        </div>
        <div className="text-sm text-gray-100 whitespace-pre-wrap leading-relaxed">
          {reply}
        </div>
      </div>
    );
  }

  const cleanedQuote = cleanQuoted(quoted);

  return (
    <div className="space-y-3">
      {reply && (
        <div>
          <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-cyan-300 mb-2">
            <CornerUpLeft className="h-3 w-3" />
            {replyLabel}
          </div>
          <div className="text-sm text-gray-100 whitespace-pre-wrap leading-relaxed bg-cyan-500/5 border border-cyan-500/15 rounded-lg p-3">
            {reply}
          </div>
        </div>
      )}
      <div>
        <button
          type="button"
          onClick={() => setShowQuoted((v) => !v)}
          className="w-full flex items-center justify-between gap-2 text-left px-3 py-2 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 transition"
        >
          <span className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-gray-400">
            <Quote className="h-3 w-3" />
            Original email (quoted)
          </span>
          <ChevronDown className={`h-4 w-4 text-gray-400 transition-transform ${showQuoted ? 'rotate-180' : ''}`} />
        </button>
        {showQuoted && (
          <div className="mt-2 pl-4 border-l-2 border-white/15 text-sm text-gray-400 whitespace-pre-wrap leading-relaxed">
            {cleanedQuote}
          </div>
        )}
      </div>
    </div>
  );
};

const StatCard = ({ icon: Icon, label, value, tint, iconTint }) => (
  <div className={`rounded-xl bg-gradient-to-br ${tint} border border-white/10 p-4 flex items-center gap-3 backdrop-blur-sm`}>
    <div className="h-10 w-10 rounded-lg bg-black/30 border border-white/10 flex items-center justify-center">
      <Icon className={`h-5 w-5 ${iconTint}`} />
    </div>
    <div className="min-w-0">
      <div className="text-xs text-gray-400 font-medium truncate">{label}</div>
      <div className="text-xl font-bold text-white leading-tight">{value}</div>
    </div>
  </div>
);

const InboxItem = ({ reply, active, onClick }) => {
  const style = INTEREST_STYLES[reply.interest_level] || INTEREST_STYLES.not_analyzed;
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-3 border-b border-white/5 flex gap-3 transition-all ${
        active ? 'bg-gradient-to-r from-cyan-500/10 to-transparent border-l-2 border-l-cyan-400' : 'hover:bg-white/5 border-l-2 border-l-transparent'
      }`}
    >
      <Avatar name={reply.from_name} email={reply.from_email} size="md" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2 mb-0.5">
          <span className={`text-sm font-semibold truncate ${active ? 'text-white' : 'text-gray-100'}`}>
            {reply.from_name || reply.from_email || 'Unknown'}
          </span>
          <span className="text-[10px] text-gray-500 shrink-0">{formatRelative(reply.replied_at)}</span>
        </div>
        <div className="text-xs text-gray-300 truncate font-medium mb-1">
          {reply.subject || '(no subject)'}
        </div>
        <div className="text-xs text-gray-500 line-clamp-2 leading-snug mb-1.5">
          {reply.preview || 'No preview available'}
        </div>
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className={`inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full border ${style.className}`}>
            {style.label}
          </span>
          {reply.campaign && (
            <span className="inline-flex items-center gap-1 text-[10px] text-gray-400 px-2 py-0.5 rounded-full bg-white/5 border border-white/10 truncate max-w-[120px]">
              <Zap className="h-2.5 w-2.5" />
              {reply.campaign}
            </span>
          )}
        </div>
      </div>
    </button>
  );
};

const DraftItem = ({ draft, active, onClick }) => {
  const style = STATUS_STYLES[draft.status] || STATUS_STYLES.pending;
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-3 border-b border-white/5 flex gap-3 transition-all ${
        active ? 'bg-gradient-to-r from-fuchsia-500/10 to-transparent border-l-2 border-l-fuchsia-400' : 'hover:bg-white/5 border-l-2 border-l-transparent'
      }`}
    >
      <Avatar name={draft.to_name} email={draft.to_email} size="md" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2 mb-0.5">
          <span className="text-sm font-semibold truncate text-gray-100">
            To: {draft.to_name || draft.to_email || 'Unknown'}
          </span>
          <span className="text-[10px] text-gray-500 shrink-0">{formatRelative(draft.created_at)}</span>
        </div>
        <div className="text-xs text-gray-300 truncate font-medium mb-1">
          {draft.subject || '(no subject)'}
        </div>
        <div className="text-xs text-gray-500 line-clamp-2 leading-snug mb-1.5">
          {(draft.body || '').slice(0, 120) || 'Empty draft'}
        </div>
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className={`inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full border ${style.className}`}>
            {style.label}
          </span>
          <span className="inline-flex items-center text-[10px] text-gray-400 px-2 py-0.5 rounded-full bg-white/5 border border-white/10 capitalize">
            {draft.tone}
          </span>
        </div>
      </div>
    </button>
  );
};

export default ReplyDraftAgentPage;
