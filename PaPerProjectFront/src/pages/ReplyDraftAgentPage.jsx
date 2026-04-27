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
  X,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Plus, CheckCircle2, Settings as SettingsIcon, BarChart3 } from 'lucide-react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Filler,
} from 'chart.js';
import { Line } from 'react-chartjs-2';

// Safe to call more than once — Chart.js dedupes registrations, so the fact
// that CampaignDetail also registers these won't cause problems.
ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Filler);
import {
  listPendingReplies,
  listDrafts,
  generateDraft,
  regenerateDraft,
  approveDraft,
  rejectDraft,
  sendDraft,
  getReplyItem,
  listSyncAccounts,
  createReplyAccount,
  deleteReplyAccount,
  getReplyAnalytics,
} from '@/services/replyDraftService';

// Pure view filter for the inbox list — Celery pre-syncs the full 120-day
// window on a cron (see marketing_agent/management/commands/sync_inbox.py),
// so switching the dropdown just slices already-cached rows and is instant.
const TIME_WINDOW_OPTIONS = [
  { value: 30,  label: 'Last 30 days' },
  { value: 60,  label: 'Last 60 days' },
  { value: 90,  label: 'Last 90 days' },
  { value: 120, label: 'Last 120 days' },
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
  const [inboxLoading, setInboxLoading] = useState(false);  // shown during dropdown-triggered refetch so the user sees feedback
  const [syncAccounts, setSyncAccounts] = useState([]);     // the attached Reply Draft Agent account, if any (0 or 1 items)
  const [accountModalOpen, setAccountModalOpen] = useState(false);
  const [accountModalMode, setAccountModalMode] = useState('add'); // 'add' | 'edit'
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [syncDays, setSyncDays] = useState(30);       // view-only filter; Celery always pre-syncs the full 120-day window
  const [activeTab, setActiveTab] = useState('inbox'); // inbox | drafts | sent
  const [search, setSearch] = useState('');

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
    setInboxLoading(true);
    try {
      const res = await listPendingReplies({ days: String(syncDays) });
      setPendingReplies(res?.data || []);
    } catch (e) {
      toast({ title: 'Failed to load inbox', description: e.message, variant: 'destructive' });
    } finally {
      setInboxLoading(false);
    }
  }, [toast, syncDays]);

  const refreshDrafts = useCallback(async () => {
    try {
      const res = await listDrafts();
      setDrafts(res?.data || []);
    } catch (e) {
      toast({ title: 'Failed to load drafts', description: e.message, variant: 'destructive' });
    }
  }, [toast]);

  const refreshSyncAccounts = useCallback(async () => {
    try {
      const res = await listSyncAccounts();
      setSyncAccounts(res?.data || []);
    } catch (e) {
      // Non-fatal — the visibility card just won't render.
      console.error('Failed to load sync accounts', e);
    }
  }, []);

  const openAddAccountModal = useCallback(() => {
    setAccountModalMode('add');
    setAccountModalOpen(true);
  }, []);

  const openEditAccountModal = useCallback(() => {
    setAccountModalMode('edit');
    setAccountModalOpen(true);
  }, []);

  const refreshAll = useCallback(async () => {
    setRefreshing(true);
    try {
      await Promise.all([refreshInbox(), refreshDrafts()]);
    } finally {
      setRefreshing(false);
    }
  }, [refreshInbox, refreshDrafts]);

  useEffect(() => {
    if (hasAccess) {
      refreshAll();
      refreshSyncAccounts();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasAccess]);

  // Auto-refresh inbox + drafts every 30s (silent — no spinner flicker).
  // Matches the polling pattern used in CampaignDetail / EmailSendingStatusPage
  // so new incoming mail surfaced by the 5-min sync_inbox_task appears without
  // requiring a manual click.
  const POLL_INTERVAL_MS = 30 * 1000;
  useEffect(() => {
    if (!hasAccess) return;
    const interval = setInterval(() => {
      refreshInbox();
      refreshDrafts();
      // Keep sync-accounts fresh so the "Syncing your inbox…" banner
      // hides as soon as InboxEmail rows land from the Celery sync.
      refreshSyncAccounts();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [hasAccess, refreshInbox, refreshDrafts, refreshSyncAccounts]);

  // Re-fetch the inbox whenever the user changes a filter.
  useEffect(() => {
    if (hasAccess) refreshInbox();
  }, [hasAccess, syncDays, refreshInbox]);

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

  const handleSelectReply = async (r) => {
    // Show the row immediately with just preview content, then fetch the
    // full body in the background. List endpoint omits body for speed
    // (see backend _serialize_{reply,inbox_email}).
    setSelectedReply(r);
    setSelectedDraft(null);
    setEditedBody('');
    setEditedSubject('');
    setUserContext('');
    if (!r || r.body !== undefined) return;
    try {
      const res = await getReplyItem(r.source, r.id);
      const full = res?.data;
      if (full) {
        setSelectedReply((current) => (current && current.id === r.id && current.source === r.source ? { ...current, ...full } : current));
      }
    } catch (e) {
      console.error('Failed to load email body', e);
    }
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
          {/* Header: title + Refresh */}
          <div className="flex items-center justify-between gap-3 mb-5 flex-wrap">
            <div className="flex items-center gap-3 min-w-0">
              <div className="min-w-0">
                <h1 className="text-lg font-bold text-white truncate">Reply Draft Workspace</h1>
                <p className="text-xs text-gray-400">
                  {refreshing
                    ? 'Syncing from your mailbox…'
                    : 'Click refresh to pull the latest from your inbox and drafts.'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3 flex-wrap justify-end">
              <span className="text-xs text-gray-400 hidden sm:inline">Auto-refreshes every 30s</span>

              <AttachedAccountButton
                syncAccounts={syncAccounts}
                onAddNew={openAddAccountModal}
              />

              {syncAccounts.length > 0 && (
                <Button
                  variant="outline"
                  className="bg-white/5 border-white/10 text-white hover:bg-white/10 hover:text-white gap-2"
                  onClick={() => setSettingsOpen(true)}
                  title="Inbox analytics & account settings"
                >
                  <SettingsIcon className="h-4 w-4" />
                  <span className="hidden sm:inline text-xs font-medium">Settings</span>
                </Button>
              )}

              <Button
                onClick={refreshAll}
                disabled={refreshing}
                className="bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-semibold shadow-lg shadow-cyan-500/20 disabled:opacity-60"
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${refreshing ? 'animate-spin' : ''}`} />
                {refreshing ? 'Refreshing…' : 'Refresh'}
              </Button>
            </div>
          </div>

          {/* Contextual Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <StatCard icon={Inbox} label="Pending Replies" value={stats.pending} tint="from-cyan-500/20 to-blue-500/10" iconTint="text-cyan-300" />
            <StatCard icon={FileText} label="Drafts to Review" value={stats.draftsPending} tint="from-amber-500/20 to-orange-500/10" iconTint="text-amber-300" />
            <StatCard icon={Send} label="Sent" value={stats.sent} tint="from-emerald-500/20 to-teal-500/10" iconTint="text-emerald-300" />
            <StatCard icon={AlertCircle} label="Failed" value={stats.failed} tint="from-rose-500/20 to-red-500/10" iconTint="text-rose-300" />
          </div>

          {/* Sync Source card — tells the user exactly which mailbox feeds
              this inbox, or prompts them to configure one if it's empty. */}
          <SyncSourceCard
            accounts={syncAccounts}
            onConfigure={() => setAccountModalOpen(true)}
          />

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
                            : 'Search sent replies…'
                      }
                      className="w-full bg-white/5 border border-white/10 rounded-lg pl-9 pr-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500/50 focus:bg-white/10 transition"
                    />
                  </div>

                  {activeTab === 'inbox' && (
                    <select
                      value={syncDays}
                      onChange={(e) => setSyncDays(Number(e.target.value))}
                      title="Filter the inbox to a rolling time window. Mail is pre-synced in the background, so switching is instant."
                      className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-2 text-xs text-white focus:outline-none focus:border-cyan-500/50 focus:bg-white/10 transition"
                    >
                      {TIME_WINDOW_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value} className="bg-gray-900">
                          {o.label}
                        </option>
                      ))}
                    </select>
                  )}

                </div>

                {/* Loading strip — subtle indeterminate bar while the inbox refetches.
                    Triggered by dropdown changes + the 30s poll; sits above the list so
                    it doesn't push rows around. */}
                {inboxLoading && activeTab === 'inbox' && (
                  <div className="relative h-0.5 overflow-hidden bg-white/5">
                    <div className="absolute inset-y-0 w-1/3 bg-gradient-to-r from-transparent via-cyan-400/70 to-transparent animate-[inbox-loading_1.2s_ease-in-out_infinite]" />
                  </div>
                )}

                {/* List */}
                <div className="custom-scrollbar lg:flex-1 lg:min-h-0 lg:overflow-y-auto">
                  {activeTab === 'inbox' && (
                    <>
                      {filteredInbox.length === 0 ? (
                        <EmptyState
                          icon={Inbox}
                          title={search ? 'No matches' : 'Inbox is clear'}
                          subtitle={
                            search
                              ? 'Try a different search term.'
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

      <AccountConnectModal
        open={accountModalOpen}
        mode={accountModalMode}
        existingAccount={syncAccounts[0] || null}
        onClose={() => setAccountModalOpen(false)}
        onSaved={() => {
          setAccountModalOpen(false);
          refreshSyncAccounts();
          refreshInbox();
        }}
      />

      <SettingsModal
        open={settingsOpen}
        account={syncAccounts[0] || null}
        onClose={() => setSettingsOpen(false)}
        onEdit={() => {
          setSettingsOpen(false);
          openEditAccountModal();
        }}
        onDeleted={() => {
          setSettingsOpen(false);
          refreshSyncAccounts();
          refreshInbox();
        }}
      />

      <style>{`
        .custom-scrollbar::-webkit-scrollbar { width: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 3px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.15); }
        @keyframes inbox-loading {
          0%   { transform: translateX(-100%); }
          100% { transform: translateX(400%); }
        }
      `}</style>
    </>
  );
};

const EmailBody = ({ body, isIncomingReply }) => {
  const [showQuoted, setShowQuoted] = useState(false);
  // `body === undefined` means the list endpoint returned just a preview and
  // the detail fetch is still in flight. Show a gentle loading state instead
  // of "No content" to avoid misleading the user.
  if (body === undefined) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-500 italic">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading message…
      </div>
    );
  }
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

const FIRST_SYNC_WINDOW_MS = 5 * 60 * 1000;  // hard cap so a stuck sync doesn't leave a banner up forever
const ACTIVE_SYNC_WINDOW_MS = 2 * 60 * 1000; // show "Syncing in progress" chip for up to 2 min after IMAP config change

const SyncSourceCard = ({ accounts, onConfigure }) => {
  const total = accounts.length;
  const syncing = accounts.filter((a) => a.will_sync);
  const misconfigured = accounts.filter(
    (a) => a.is_active && a.enable_imap_sync && !a.imap_ready
  );

  // Live-ticking timer — anchored to each account's updated_at (the moment
  // its IMAP config was last touched, which is when the immediate Celery
  // sync got dispatched).
  const [now, setNow] = useState(() => Date.now());
  const earliestActivity = syncing.length > 0
    ? Math.max(...syncing.map((a) => new Date(a.updated_at || a.created_at || 0).getTime()))
    : 0;
  const elapsedMs = earliestActivity ? Math.max(0, now - earliestActivity) : 0;

  // "First sync" = will_sync but nothing has landed yet. "Active sync" = just
  // saved/updated config, rows may still be streaming in even if some have
  // already landed. Newest-first sync ordering (see sync_inbox.py) means the
  // 30-day view populates from the start, so we prefer showing the small
  // progress chip over the big empty banner once inbox_count > 0.
  const firstSync = syncing.filter((a) => (a.inbox_count || 0) === 0);
  const firstSyncActive = firstSync.length > 0 && elapsedMs < FIRST_SYNC_WINDOW_MS;
  const activelySyncing = syncing.length > 0 && elapsedMs < ACTIVE_SYNC_WINDOW_MS;
  const totalInboxCount = syncing.reduce((s, a) => s + (a.inbox_count || 0), 0);

  const showTimer = firstSyncActive || activelySyncing;
  useEffect(() => {
    if (!showTimer) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [showTimer]);

  const mmss = (ms) => {
    const s = Math.floor(ms / 1000);
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  };

  // No email accounts at all → hard block, user must add one.
  if (total === 0) {
    return (
      <div className="mb-4 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-5 py-4 flex items-start gap-4 flex-wrap">
        <div className="h-11 w-11 rounded-xl bg-amber-500/20 border border-amber-500/30 flex items-center justify-center shrink-0">
          <AlertCircle className="h-5 w-5 text-amber-300" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-amber-100">No email account connected</div>
          <div className="text-xs text-amber-200/80 mt-0.5">
            Add a mailbox in the Marketing Agent's <span className="font-medium">Email Accounts</span> settings to start syncing replies here. Without an account, this inbox stays empty.
          </div>
        </div>
        <Button
          onClick={onConfigure}
          className="bg-amber-500 hover:bg-amber-400 text-black font-semibold"
        >
          Add email account
        </Button>
      </div>
    );
  }

  // Account exists but IMAP is off or credentials are incomplete → warning.
  if (syncing.length === 0) {
    const reason = misconfigured.length > 0
      ? 'IMAP sync is enabled but credentials are incomplete — inbox won\'t sync until host / username / password are all filled in.'
      : 'None of your accounts have IMAP sync enabled. Turn it on in the Marketing Agent\'s Email Accounts settings.';
    return (
      <div className="mb-4 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-5 py-4 flex items-start gap-4 flex-wrap">
        <div className="h-11 w-11 rounded-xl bg-amber-500/20 border border-amber-500/30 flex items-center justify-center shrink-0">
          <AlertCircle className="h-5 w-5 text-amber-300" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-amber-100">Inbox sync isn't active</div>
          <div className="text-xs text-amber-200/80 mt-0.5">{reason}</div>
          <div className="mt-1 text-xs text-amber-200/60 truncate">
            {accounts.map((a) => a.email).join(', ')}
          </div>
        </div>
        <Button
          onClick={onConfigure}
          variant="outline"
          className="bg-transparent border-amber-500/40 text-amber-200 hover:bg-amber-500/20"
        >
          Fix in settings
        </Button>
      </div>
    );
  }

  // First-sync in progress — account just saved, IMAP running, nothing in DB yet.
  // Prominent cyan banner with a live elapsed timer.
  if (firstSyncActive) {
    return (
      <div className="mb-4 rounded-2xl border border-cyan-500/30 bg-cyan-500/10 px-5 py-4 flex items-start gap-4 flex-wrap">
        <div className="h-11 w-11 rounded-xl bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center shrink-0">
          <Loader2 className="h-5 w-5 text-cyan-300 animate-spin" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-cyan-100">
              Syncing your inbox…
            </span>
            <span className="text-xs font-mono text-cyan-200/80 bg-cyan-500/10 border border-cyan-500/30 rounded px-1.5 py-0.5">
              {mmss(elapsedMs)}
            </span>
          </div>
          <div className="text-xs text-cyan-200/80 mt-1">
            Pulling the last 120 days of mail from{' '}
            <span className="text-white font-medium">
              {firstSync.map((a) => a.email).join(', ')}
            </span>
            . Usually takes 30–90 seconds — emails will appear below automatically.
          </div>
        </div>
      </div>
    );
  }

  // Some emails already landed but sync is likely still running (recent config
  // change). Small cyan "in progress" chip so the user doesn't think the list
  // below is the final state — more mail may still be streaming in.
  if (activelySyncing) {
    return (
      <div className="mb-4 rounded-xl border border-cyan-500/25 bg-cyan-500/5 px-4 py-2.5 flex items-center gap-3 flex-wrap">
        <div className="h-8 w-8 rounded-lg bg-cyan-500/15 border border-cyan-500/25 flex items-center justify-center shrink-0">
          <Loader2 className="h-4 w-4 text-cyan-300 animate-spin" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-xs text-cyan-200/90">
            Syncing in progress —{' '}
            <span className="text-white font-medium">{totalInboxCount}</span>{' '}
            email{totalInboxCount === 1 ? '' : 's'} loaded so far from{' '}
            <span className="text-white font-medium">
              {syncing.map((a) => a.email).join(', ')}
            </span>
            . More may still be landing.
          </div>
        </div>
        <span className="text-xs font-mono text-cyan-200/80 bg-cyan-500/10 border border-cyan-500/30 rounded px-1.5 py-0.5 shrink-0">
          {mmss(elapsedMs)}
        </span>
      </div>
    );
  }

  // Steady-state happy path — sync is configured and settled. Small green chip.
  // Keep this terse: the header's email-accounts dropdown already lists each
  // account with its status, so repeating the list here was just noise.
  return (
    <div className="mb-4 rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-4 py-2.5 flex items-center gap-3 flex-wrap">
      <div className="h-8 w-8 rounded-lg bg-emerald-500/15 border border-emerald-500/25 flex items-center justify-center shrink-0">
        <Check className="h-4 w-4 text-emerald-300" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-xs text-emerald-200/90">
          Inbox sync active ·{' '}
          <span className="text-white font-medium">
            {syncing.length} account{syncing.length === 1 ? '' : 's'}
          </span>
        </div>
      </div>
      {misconfigured.length > 0 && (
        <span className="text-[11px] text-amber-200 bg-amber-500/10 border border-amber-500/30 rounded-full px-2 py-0.5">
          {misconfigured.length} need attention
        </span>
      )}
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

// Attached-account status button for the Reply Draft dashboard header.
// If no account is attached yet, renders an "Add email account" primary
// button. Once attached, renders a non-interactive status chip showing the
// connected email — we intentionally don't offer a change control, because
// swapping the inbox source while drafts and history are tied to it would
// cause confusing stale state.
const AttachedAccountButton = ({ syncAccounts, onAddNew }) => {
  const attached = Array.isArray(syncAccounts) && syncAccounts.length > 0 ? syncAccounts[0] : null;

  if (!attached) {
    return (
      <Button
        onClick={onAddNew}
        className="bg-amber-500 hover:bg-amber-400 text-black font-semibold gap-2"
        title="Connect an inbox to start pulling replies"
      >
        <Plus className="h-4 w-4" />
        Add email account
      </Button>
    );
  }

  const ready = attached.will_sync;
  const borderTint = ready ? 'border-emerald-500/30 bg-emerald-500/10' : 'border-amber-500/30 bg-amber-500/10';
  const textTint = ready ? 'text-emerald-200' : 'text-amber-200';

  return (
    <div
      className={`h-9 max-w-[260px] rounded-md border px-3 flex items-center gap-2 ${borderTint} ${textTint}`}
      title={ready ? 'Inbox sync active for this account' : 'Account connected but IMAP needs attention'}
    >
      {ready ? <CheckCircle2 className="h-4 w-4 shrink-0" /> : <AlertCircle className="h-4 w-4 shrink-0" />}
      <span className="truncate text-xs font-medium">{attached.email}</span>
    </div>
  );
};

// Reply-Draft-specific "Add account" modal. Creates the single EmailAccount
// attached to the Reply Draft Agent and fires an immediate Celery sync so the
// inbox populates within ~30s. Completely independent of the Marketing Agent
// email-accounts list.
const ACCOUNT_TYPE_OPTIONS = [
  { value: 'gmail',     label: 'Gmail',       smtp_host: 'smtp.gmail.com',     imap_host: 'imap.gmail.com'     },
  { value: 'hostinger', label: 'Hostinger',   smtp_host: 'smtp.hostinger.com', imap_host: 'imap.hostinger.com' },
  { value: 'smtp',      label: 'Custom SMTP', smtp_host: '',                   imap_host: ''                   },
];

const defaultNewForm = () => ({
  name: 'Reply Draft Inbox',
  account_type: 'gmail',
  email: '',
  smtp_host: 'smtp.gmail.com',
  smtp_port: 587,
  smtp_username: '',
  smtp_password: '',
  use_tls: true,
  use_ssl: false,
  is_gmail_app_password: true,
  imap_host: 'imap.gmail.com',
  imap_port: 993,
  imap_username: '',
  imap_password: '',
  imap_use_ssl: true,
});

const AccountConnectModal = ({ open, onClose, onSaved, mode = 'add', existingAccount = null }) => {
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(defaultNewForm());

  const isEdit = mode === 'edit' && existingAccount;

  useEffect(() => {
    if (!open) return;
    if (isEdit) {
      // Prefill from the server's account record. Passwords are never echoed
      // back from the list endpoint, so leave them blank — the backend treats
      // empty passwords as "keep existing" on re-attach.
      setForm({
        ...defaultNewForm(),
        name: existingAccount.name || 'Reply Draft Inbox',
        account_type: existingAccount.account_type || 'smtp',
        email: existingAccount.email || '',
        smtp_host: existingAccount.smtp_host || '',
        smtp_port: existingAccount.smtp_port || 587,
        smtp_username: existingAccount.smtp_username || existingAccount.email || '',
        smtp_password: '',
        use_tls: existingAccount.use_tls ?? true,
        use_ssl: existingAccount.use_ssl ?? false,
        is_gmail_app_password: existingAccount.is_gmail_app_password ?? (existingAccount.account_type === 'gmail'),
        imap_host: existingAccount.imap_host || '',
        imap_port: existingAccount.imap_port || 993,
        imap_username: existingAccount.imap_username || existingAccount.email || '',
        imap_password: '',
        imap_use_ssl: existingAccount.imap_use_ssl ?? true,
      });
    } else {
      setForm(defaultNewForm());
    }
  }, [open, isEdit, existingAccount]);

  const applyTypeDefaults = (typeValue) => {
    const t = ACCOUNT_TYPE_OPTIONS.find((x) => x.value === typeValue);
    if (!t) return;
    setForm((p) => ({
      ...p,
      account_type: typeValue,
      smtp_host: t.smtp_host,
      imap_host: t.imap_host,
      is_gmail_app_password: typeValue === 'gmail',
    }));
  };

  const handleSubmit = async () => {
    if (!form.email.trim()) {
      toast({ title: 'Missing email', description: 'Enter the email address.', variant: 'destructive' });
      return;
    }
    if (!form.smtp_host.trim()) {
      toast({ title: 'Missing SMTP host', description: 'SMTP host is required.', variant: 'destructive' });
      return;
    }
    if (!form.imap_host.trim()) {
      toast({ title: 'Missing IMAP host', description: 'IMAP host is required.', variant: 'destructive' });
      return;
    }
    // On create, passwords are required; on edit they're optional (empty ==
    // keep the stored password).
    if (!isEdit) {
      if (!form.smtp_password) {
        toast({ title: 'Missing SMTP password', description: 'SMTP password is required.', variant: 'destructive' });
        return;
      }
      if (!form.imap_password) {
        toast({ title: 'Missing IMAP password', description: 'IMAP password is required (needed to pull replies).', variant: 'destructive' });
        return;
      }
    }
    setSaving(true);
    try {
      const payload = {
        name: form.name.trim() || 'Reply Draft Inbox',
        account_type: form.account_type,
        email: form.email.trim(),
        smtp_host: form.smtp_host.trim(),
        smtp_port: Number(form.smtp_port) || 587,
        smtp_username: (form.smtp_username || '').trim() || form.email.trim(),
        use_tls: form.use_tls,
        use_ssl: form.use_ssl,
        is_gmail_app_password: form.is_gmail_app_password,
        imap_host: form.imap_host.trim(),
        imap_port: Number(form.imap_port) || 993,
        imap_username: (form.imap_username || '').trim() || form.email.trim(),
        imap_use_ssl: form.imap_use_ssl,
      };
      // Only include password fields when the user actually typed something,
      // so an edit that leaves them blank preserves what's stored.
      if (form.smtp_password) payload.smtp_password = form.smtp_password;
      if (form.imap_password) payload.imap_password = form.imap_password;

      const res = await createReplyAccount(payload);
      if (res?.status === 'success') {
        toast({
          title: isEdit ? 'Account updated' : 'Account connected',
          description: `${form.email} is syncing now — mail lands within ~30 seconds.`,
        });
        onSaved();
      } else {
        toast({ title: isEdit ? 'Save failed' : 'Create failed', description: res?.message || 'Could not save account.', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: isEdit ? 'Save failed' : 'Create failed', description: e?.message || 'Could not save account.', variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Inbox className="h-5 w-5 text-primary" />
            {isEdit ? 'Edit inbox account' : 'Connect an inbox'}
          </DialogTitle>
          <DialogDescription>
            {isEdit
              ? 'Update the connection settings. Leave password fields blank to keep what\'s stored.'
              : 'Add the email account the Reply Draft Agent will read replies from. Syncing starts automatically once you save.'}
          </DialogDescription>
        </DialogHeader>

        <div className="py-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Account name</Label>
              <Input
                value={form.name}
                onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                placeholder="e.g. Reply inbox"
                className="mt-1 h-9"
              />
            </div>
            <div>
              <Label className="text-xs">Provider</Label>
              <select
                value={form.account_type}
                onChange={(e) => applyTypeDefaults(e.target.value)}
                className="mt-1 w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              >
                {ACCOUNT_TYPE_OPTIONS.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <Label className="text-xs">Email address</Label>
            <Input
              type="email"
              value={form.email}
              onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))}
              placeholder="you@example.com"
              className="mt-1 h-9"
            />
          </div>

          <div className="pt-2 border-t">
            <div className="text-xs font-semibold text-muted-foreground mb-2">SMTP (for sending)</div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Host</Label>
                <Input
                  value={form.smtp_host}
                  onChange={(e) => setForm((p) => ({ ...p, smtp_host: e.target.value }))}
                  className="mt-1 h-9"
                />
              </div>
              <div>
                <Label className="text-xs">Port</Label>
                <Input
                  type="number"
                  value={form.smtp_port}
                  onChange={(e) => setForm((p) => ({ ...p, smtp_port: e.target.value }))}
                  className="mt-1 h-9"
                />
              </div>
            </div>
            <div className="mt-3">
              <Label className="text-xs">Password</Label>
              <Input
                type="password"
                value={form.smtp_password}
                onChange={(e) => setForm((p) => ({ ...p, smtp_password: e.target.value }))}
                placeholder="••••••••"
                className="mt-1 h-9"
              />
            </div>
          </div>

          <div className="pt-2 border-t">
            <div className="text-xs font-semibold text-muted-foreground mb-2">IMAP (for receiving replies)</div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Host</Label>
                <Input
                  value={form.imap_host}
                  onChange={(e) => setForm((p) => ({ ...p, imap_host: e.target.value }))}
                  className="mt-1 h-9"
                />
              </div>
              <div>
                <Label className="text-xs">Port</Label>
                <Input
                  type="number"
                  value={form.imap_port}
                  onChange={(e) => setForm((p) => ({ ...p, imap_port: e.target.value }))}
                  className="mt-1 h-9"
                />
              </div>
            </div>
            <div className="mt-3">
              <Label className="text-xs">Password</Label>
              <Input
                type="password"
                value={form.imap_password}
                onChange={(e) => setForm((p) => ({ ...p, imap_password: e.target.value }))}
                placeholder="••••••••"
                className="mt-1 h-9"
              />
            </div>
            <div className="flex items-center gap-2 mt-3">
              <Switch
                id="imap-ssl"
                checked={form.imap_use_ssl}
                onCheckedChange={(checked) => setForm((p) => ({ ...p, imap_use_ssl: checked }))}
              />
              <Label htmlFor="imap-ssl" className="text-xs cursor-pointer">Use SSL</Label>
            </div>
          </div>
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
            {isEdit ? 'Save changes' : 'Save & start sync'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

// Settings dialog surfaced from the header gear button once an account is
// attached. Shows account info with edit/disconnect actions and a single
// window-selectable bar chart of inbox volume (30/60/90/120 days).
const ANALYTICS_WINDOWS = [30, 60, 90, 120];

const SettingsModal = ({ open, account, onClose, onEdit, onDeleted }) => {
  const { toast } = useToast();
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(false);
  const [windowDays, setWindowDays] = useState(30);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setConfirmDelete(false);
    setWindowDays(30);
  }, [open]);

  // Refetch whenever the modal opens OR the user switches the window.
  useEffect(() => {
    if (!open) return;
    setLoading(true);
    getReplyAnalytics({ days: windowDays })
      .then((res) => setAnalytics(res?.status === 'success' ? res.data : null))
      .catch(() => setAnalytics(null))
      .finally(() => setLoading(false));
  }, [open, windowDays]);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      const res = await deleteReplyAccount();
      if (res?.status === 'success') {
        toast({ title: 'Account disconnected', description: res?.data?.message || 'Inbox cleared.' });
        onDeleted();
      } else {
        toast({ title: 'Delete failed', description: res?.message || 'Could not disconnect the account.', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Delete failed', description: e?.message || 'Could not disconnect the account.', variant: 'destructive' });
    } finally {
      setDeleting(false);
    }
  };

  const buckets = analytics?.buckets || [];
  const granularity = analytics?.granularity || 'day';  // 'day' | 'week'

  // Line chart config — daily buckets for 30d, weekly buckets above that.
  // Fewer buckets on longer windows means point dots + tooltip labels can
  // stay visible without overwhelming the chart.
  const chartData = {
    labels: buckets.map((b) => b.date),
    datasets: [
      {
        label: 'Emails received',
        data: buckets.map((b) => b.count || 0),
        borderColor: '#22d3ee',
        backgroundColor: 'rgba(34, 211, 238, 0.15)',
        fill: true,
        tension: 0.35,
        pointRadius: granularity === 'week' ? 3 : 2.5,
        pointHoverRadius: 5,
        borderWidth: 2,
      },
    ],
  };
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { intersect: false, mode: 'index' },
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          title: (items) => {
            const raw = items[0]?.label || '';
            return granularity === 'week' ? `Week of ${raw}` : raw;
          },
          label: (ctx) => ` ${ctx.parsed.y} email${ctx.parsed.y === 1 ? '' : 's'}`,
        },
      },
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: {
          autoSkip: true,
          maxTicksLimit: granularity === 'week' ? Math.min(buckets.length, 10) : 8,
          color: 'rgba(120,120,120,0.8)',
          font: { size: 10 },
          callback: function (value) {
            const label = this.getLabelForValue(value);
            return typeof label === 'string' ? label.slice(5) : label;
          },
        },
      },
      y: {
        beginAtZero: true,
        ticks: {
          precision: 0,
          color: 'rgba(120,120,120,0.8)',
          font: { size: 10 },
        },
        grid: { color: 'rgba(120,120,120,0.12)' },
      },
    },
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <SettingsIcon className="h-5 w-5 text-primary" />
            Inbox settings &amp; analytics
          </DialogTitle>
          <DialogDescription>
            Stats are scoped to the attached Reply Draft Agent account only.
          </DialogDescription>
        </DialogHeader>

        <div className="py-4 space-y-5">
          {/* Account info + actions */}
          <section className="rounded-lg border p-4 space-y-3">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <div className="text-xs text-muted-foreground">Connected account</div>
                <div className="text-sm font-semibold truncate">{account?.email || '—'}</div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  {account?.account_type || 'smtp'} · IMAP: {account?.imap_host || '—'}
                </div>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={onEdit} disabled={deleting}>
                  <Edit3 className="h-3.5 w-3.5 mr-2" />
                  Edit
                </Button>
                {!confirmDelete ? (
                  <Button variant="destructive" size="sm" onClick={() => setConfirmDelete(true)} disabled={deleting}>
                    <Trash2 className="h-3.5 w-3.5 mr-2" />
                    Disconnect
                  </Button>
                ) : (
                  <Button variant="destructive" size="sm" onClick={handleDelete} disabled={deleting}>
                    {deleting ? <Loader2 className="h-3.5 w-3.5 mr-2 animate-spin" /> : <Trash2 className="h-3.5 w-3.5 mr-2" />}
                    Really disconnect?
                  </Button>
                )}
              </div>
            </div>
            {confirmDelete && (
              <div className="rounded-md border border-rose-200 bg-rose-500/5 p-3 text-xs text-rose-700 dark:text-rose-400 dark:border-rose-800">
                Disconnecting deletes this account <strong>and all its synced inbox mail + drafts</strong>. This cannot be undone.{' '}
                <button type="button" onClick={() => setConfirmDelete(false)} className="underline">
                  Cancel
                </button>
              </div>
            )}
          </section>

          {/* Inbox volume chart */}
          <section className="rounded-lg border p-4 space-y-3">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <BarChart3 className="h-4 w-4 text-primary" />
                Emails received
              </div>
              <div className="flex gap-1 p-0.5 rounded-md bg-muted text-xs">
                {ANALYTICS_WINDOWS.map((w) => (
                  <button
                    key={w}
                    type="button"
                    onClick={() => setWindowDays(w)}
                    className={`px-2.5 py-1 rounded transition-colors ${
                      windowDays === w ? 'bg-background shadow-sm font-medium' : 'text-muted-foreground'
                    }`}
                  >
                    {w}d
                  </button>
                ))}
              </div>
            </div>

            {loading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : buckets.length === 0 ? (
              <div className="text-xs text-muted-foreground py-6 text-center">No data.</div>
            ) : (
              <>
                <div className="text-xs text-muted-foreground">
                  <span className="font-semibold text-foreground">{analytics?.total ?? 0}</span>{' '}
                  email{(analytics?.total ?? 0) === 1 ? '' : 's'} in the last {windowDays} days
                  {granularity === 'week' && (
                    <span className="ml-1 opacity-75">· grouped by week</span>
                  )}
                </div>
                <div className="h-48">
                  <Line data={chartData} options={chartOptions} />
                </div>
              </>
            )}
          </section>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ReplyDraftAgentPage;
