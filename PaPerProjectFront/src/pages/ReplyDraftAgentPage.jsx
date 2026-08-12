import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate } from 'react-router-dom';
import { useToast } from '@/components/ui/use-toast';
import { checkModuleAccess } from '@/services/modulePurchaseService';
import usePurchasedModules from '@/hooks/usePurchasedModules';
import {
  Reply,
  Loader2,
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
  CornerUpLeft,
  X,
  PenSquare,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { CheckCircle2, Settings as SettingsIcon, BarChart3, Link2 } from 'lucide-react';
// Sparkles, RefreshCw and Inbox are already imported in the main lucide block above.
import HoverTip from '@/components/common/HoverTip';
import HowItWorksModal from '@/components/common/HowItWorksModal';
import FrontlineTutorial, { hasSeenTutorial, markTutorialSeen } from '@/components/frontline/FrontlineTutorial';
import { GraduationCap } from 'lucide-react';
import { REPLY_DRAFT_HOWITWORKS_STEPS, REPLY_DRAFT_HOWITWORKS_KEY } from './replyDraftHowItWorks';
import { buildReplyDraftTourSteps, REPLY_DRAFT_TOUR_KEY } from './replyDraftTourSteps';

// Resolve the how-it-works step icon names (strings) to real components.
const RD_HOWITWORKS_ICONS = { Link2, Inbox, Sparkles, RefreshCw, CheckCircle2, BarChart3, PenSquare, SettingsIcon, Edit3 };
const RD_HOWITWORKS_STEPS = REPLY_DRAFT_HOWITWORKS_STEPS.map((s) => ({
  ...s,
  icon: RD_HOWITWORKS_ICONS[s.icon],
}));
import {
  listPendingReplies,
  listDrafts,
  generateDraft,
  regenerateDraft,
  approveDraft,
  rejectDraft,
  sendDraft,
  getReplyItem,
  fetchInboxAttachments,
  listSyncAccounts,
  uploadDraftAttachment,
  deleteDraftAttachment,
} from '@/services/replyDraftService';
import {
  DRAFT_ATTACHMENT_MAX_BYTES,
  DRAFT_ATTACHMENT_MAX_COUNT,
  TIME_WINDOW_OPTIONS,
  TONES,
  LENGTHS,
  INTEREST_STYLES,
  STATUS_STYLES,
  PAGE_SIZE,
} from '@/components/replyDraft/replyDraftConstants';
import { humanizeSendError, humanizeAiError, formatRelative, formatDateTime, looksLikeHtml } from '@/components/replyDraft/replyDraftHelpers';
import { Avatar, EmptyState, Paginator, StatCard } from '@/components/replyDraft/SharedUI';
import { HtmlBody } from '@/components/replyDraft/HtmlBody';
import { AttachmentLoading, AttachmentList, DraftAttachmentsSection } from '@/components/replyDraft/Attachments';
import { EmailBody } from '@/components/replyDraft/EmailBody';
import { InboxItem, DraftItem } from '@/components/replyDraft/ListItems';
import { SyncSourceCard, AttachedAccountButton } from '@/components/replyDraft/SyncSourceCard';
import { ComposeModal } from '@/components/replyDraft/ComposeModal';
import { AccountConnectModal } from '@/components/replyDraft/AccountConnectModal';
import { SettingsModal } from '@/components/replyDraft/SettingsModal';

const ReplyDraftAgentPage = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [companyUser, setCompanyUser] = useState(null);
  const [loading, setLoading] = useState(true);
  // "How it works" onboarding modal — auto-shown once on first visit.
  const [howItWorksOpen, setHowItWorksOpen] = useState(false);
  // Interactive guided tour (shared FrontlineTutorial). Auto-launches once
  // after the How-it-works modal is dismissed on first visit; replayable
  // from the header "Take the Tour" button.
  const [tourOpen, setTourOpen] = useState(false);
  const [hasAccess, setHasAccess] = useState(false);
  const [checkingAccess, setCheckingAccess] = useState(true);
  const { modulesLoaded } = usePurchasedModules();

  const [pendingReplies, setPendingReplies] = useState([]);
  // Synced Sent-folder mail (InboxEmail rows where direction='out'), shown
  // in the Sent tab. Kept separate from pendingReplies so the inbox list
  // doesn't get polluted with outgoing mail.
  const [sentEmails, setSentEmails] = useState([]);
  const [drafts, setDrafts] = useState([]);
  const [selectedReply, setSelectedReply] = useState(null);
  const [selectedDraft, setSelectedDraft] = useState(null);
  const [tone, setTone] = useState('professional');
  const [length, setLength] = useState('medium');
  const [userContext, setUserContext] = useState('');
  const [editedSubject, setEditedSubject] = useState('');
  const [editedBody, setEditedBody] = useState('');
  const [busy, setBusy] = useState(false);
  const [uploadingAttachment, setUploadingAttachment] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [inboxLoading, setInboxLoading] = useState(false);  // shown during dropdown-triggered refetch so the user sees feedback
  const [sentLoading, setSentLoading] = useState(false);    // mirrors inboxLoading but for the Sent tab's days-window refetch
  const [syncAccounts, setSyncAccounts] = useState([]);     // the attached Reply Draft Agent account, if any (0 or 1 items)
  const [accountModalOpen, setAccountModalOpen] = useState(false);
  const [accountModalMode, setAccountModalMode] = useState('add'); // 'add' | 'edit'
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [composeOpen, setComposeOpen] = useState(false);
  const [syncDays, setSyncDays] = useState(30);       // view-only filter; Celery always pre-syncs the full 120-day window
  const [activeTab, setActiveTab] = useState('inbox'); // inbox | drafts | sent
  const [search, setSearch] = useState('');
  // 1-based current page for the active list. Reset to 1 whenever the tab
  // or search changes (below) so the user never lands on an out-of-range
  // page after the result set shrinks.
  const [listPage, setListPage] = useState(1);
  // Reply composer is hidden by default for inbox rows — the user has to
  // click the "Reply" button to reveal the AI-draft generator. Drafts on
  // the other hand land straight in the composer (the user came to review
  // it). Reset to false on every new selection.
  const [composerOpen, setComposerOpen] = useState(false);
  // Toggles the Message Body between the raw editor (default) and a
  // rendered preview of how the email will look when sent — useful when
  // the draft body is HTML and the raw markup is unreadable.
  const [showBodyPreview, setShowBodyPreview] = useState(false);

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
      const res = await listPendingReplies({ days: String(syncDays), direction: 'in' });
      setPendingReplies(res?.data || []);
    } catch (e) {
      toast({ title: 'Failed to load inbox', description: e.message, variant: 'destructive' });
    } finally {
      setInboxLoading(false);
    }
  }, [toast, syncDays]);

  const refreshSent = useCallback(async () => {
    setSentLoading(true);
    try {
      const res = await listPendingReplies({ days: String(syncDays), direction: 'out' });
      setSentEmails(res?.data || []);
    } catch (e) {
      // Non-fatal — Sent tab will just show its empty state.
      console.error('Failed to load sent emails', e);
    } finally {
      setSentLoading(false);
    }
  }, [syncDays]);

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
      await Promise.all([refreshInbox(), refreshSent(), refreshDrafts()]);
    } finally {
      setRefreshing(false);
    }
  }, [refreshInbox, refreshSent, refreshDrafts]);

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

  // Guards against the two failure modes that make this page freeze / get
  // killed by the browser when left open a long time:
  //   1. Overlapping polls — if the previous round's 4 requests haven't
  //      resolved yet (slow network, big mailbox), a new setInterval tick
  //      would pile another 4 on top. Under load this compounds until the
  //      tab exhausts memory and the browser terminates it. `pollInFlight`
  //      makes a tick a no-op while the prior round is still running.
  //   2. Background polling — a hidden tab has no reason to keep hitting the
  //      API every 30s; we skip the tick when document.hidden and fire one
  //      immediate catch-up refresh when the tab becomes visible again.
  const pollInFlight = useRef(false);
  const runPollRound = useCallback(async () => {
    if (pollInFlight.current) return;
    if (typeof document !== 'undefined' && document.hidden) return;
    pollInFlight.current = true;
    try {
      await Promise.all([
        refreshInbox(),
        refreshSent(),
        refreshDrafts(),
        // Keep sync-accounts fresh so the "Syncing your inbox…" banner
        // hides as soon as InboxEmail rows land from the Celery sync.
        refreshSyncAccounts(),
      ]);
    } finally {
      pollInFlight.current = false;
    }
  }, [refreshInbox, refreshSent, refreshDrafts, refreshSyncAccounts]);

  useEffect(() => {
    if (!hasAccess) return;
    const interval = setInterval(runPollRound, POLL_INTERVAL_MS);
    // Immediately catch up when the user returns to the tab, since we
    // deliberately skipped ticks while it was hidden.
    const onVisible = () => { if (!document.hidden) runPollRound(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [hasAccess, runPollRound]);

  // First visit (once access is confirmed): auto-show the "How it works" modal.
  useEffect(() => {
    if (!hasAccess) return;
    if (!hasSeenTutorial(REPLY_DRAFT_HOWITWORKS_KEY)) {
      const t = setTimeout(() => setHowItWorksOpen(true), 500);
      return () => clearTimeout(t);
    }
  }, [hasAccess]);

  const handleCloseHowItWorks = () => {
    setHowItWorksOpen(false);
    markTutorialSeen(REPLY_DRAFT_HOWITWORKS_KEY);
    // First visit: right after the summary modal, offer the interactive
    // walkthrough once. Guarded on the tour's own key so a returning user
    // who already saw (or skipped) it isn't nagged again.
    if (!hasSeenTutorial(REPLY_DRAFT_TOUR_KEY)) {
      setTimeout(() => setTourOpen(true), 300);
    }
  };

  // While sync is actively running, poll the sync-accounts endpoint more
  // aggressively (every 5s) so the staged-progress banner advances
  // 30 → 60 → 90 promptly and we drop the banner the moment the worker
  // finishes. The 30s inbox/sent/drafts cadence above is unchanged —
  // only sync state needs sub-half-minute resolution.
  const isSyncRunning = (syncAccounts || []).some((a) => a.sync_in_progress);
  useEffect(() => {
    if (!hasAccess || !isSyncRunning) return;
    // Skip the fast poll while the tab is backgrounded — same rationale as
    // the 30s round above; a hidden tab doesn't need 5s sync resolution.
    const id = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      refreshSyncAccounts();
    }, 5 * 1000);
    return () => clearInterval(id);
  }, [hasAccess, isSyncRunning, refreshSyncAccounts]);

  // Re-fetch inbox + sent whenever the user changes the time-window filter
  // — both lists honour the same `days` slice.
  useEffect(() => {
    if (hasAccess) {
      refreshInbox();
      refreshSent();
    }
  }, [hasAccess, syncDays, refreshInbox, refreshSent]);

  const clearSelection = () => {
    setSelectedReply(null);
    setSelectedDraft(null);
    setEditedSubject('');
    setEditedBody('');
    setUserContext('');
    setComposerOpen(false);
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
    setComposerOpen(false);
    if (!r || r.body !== undefined) return;
    try {
      const res = await getReplyItem(r.source, r.id);
      const full = res?.data;
      if (full) {
        setSelectedReply((current) => (current && current.id === r.id && current.source === r.source ? { ...current, ...full } : current));

        // Lazy attachment fetch. Sync writes InboxEmail rows with
        // attachments_fetched=false (skipping attachment extraction
        // kept fresh syncs fast on big mailboxes); when the user
        // opens the email the first time we pull the actual files
        // from IMAP and merge them into the selection. Only inbox
        // rows have this flag — campaign-Reply rows always include
        // their attachments inline. While this is running the email
        // pane shows AttachmentLoading (skeleton + "Loading
        // attachments…" tag) so the user knows files are streaming.
        if (r.source === 'inbox' && full.attachments_fetched === false) {
          try {
            const attRes = await fetchInboxAttachments(r.id);
            const attData = attRes?.data;
            if (Array.isArray(attData)) {
              setSelectedReply((current) => {
                if (!current || current.id !== r.id || current.source !== r.source) return current;
                return { ...current, attachments: attData, attachments_fetched: true };
              });
            } else {
              // Server returned something we can't render — flip the
              // flag locally so the skeleton stops spinning. The DB
              // flag stays whatever the server set; next open will
              // retry the IMAP fetch if it's still false there.
              setSelectedReply((current) => {
                if (!current || current.id !== r.id || current.source !== r.source) return current;
                return { ...current, attachments_fetched: true };
              });
            }
          } catch (attErr) {
            // Non-fatal — body is already shown. Mark fetched=true
            // locally so the skeleton stops spinning instead of
            // hanging there forever; user sees "no attachments" until
            // they reopen the email and the next attempt succeeds.
            console.error('Failed to fetch attachments lazily', attErr);
            setSelectedReply((current) => {
              if (!current || current.id !== r.id || current.source !== r.source) return current;
              return { ...current, attachments_fetched: true };
            });
          }
        }
      }
    } catch (e) {
      console.error('Failed to load email body', e);
    }
  };

  // Jump from a Sent row's "In reply to" chip to the parent inbox email.
  // We try the cached inbox list first to avoid an extra round-trip; if
  // the parent isn't loaded (e.g. it's outside the current days-window),
  // fetch it directly. Switches the left list to the Inbox tab so the
  // selection is reflected there too.
  const handleOpenParentEmail = useCallback(async (parent) => {
    if (!parent?.id) return;
    setActiveTab('inbox');
    const cached = pendingReplies.find(
      (r) => r.id === parent.id && r.source === 'inbox'
    );
    if (cached) {
      handleSelectReply(cached);
      return;
    }
    try {
      const res = await getReplyItem('inbox', parent.id);
      const full = res?.data;
      if (full) {
        // Synthesize a list-shaped row so handleSelectReply's contract
        // (it expects a list row + lazy body fetch) still works.
        const synth = { ...full, source: 'inbox' };
        setSelectedReply(synth);
        setSelectedDraft(null);
        setEditedBody('');
        setEditedSubject('');
        setUserContext('');
        setComposerOpen(false);

        // Same lazy attachment fetch as handleSelectReply, since the
        // user can land on this code path without ever clicking a row
        // (jumping from a Sent-tab "in reply to" chip). Same loading
        // skeleton + error fallback as the primary path.
        if (full.attachments_fetched === false) {
          try {
            const attRes = await fetchInboxAttachments(parent.id);
            const attData = attRes?.data;
            if (Array.isArray(attData)) {
              setSelectedReply((current) => {
                if (!current || current.id !== parent.id || current.source !== 'inbox') return current;
                return { ...current, attachments: attData, attachments_fetched: true };
              });
            } else {
              setSelectedReply((current) => {
                if (!current || current.id !== parent.id || current.source !== 'inbox') return current;
                return { ...current, attachments_fetched: true };
              });
            }
          } catch (attErr) {
            console.error('Failed to fetch attachments lazily (parent)', attErr);
            setSelectedReply((current) => {
              if (!current || current.id !== parent.id || current.source !== 'inbox') return current;
              return { ...current, attachments_fetched: true };
            });
          }
        }
      }
    } catch (e) {
      toast({
        title: 'Could not open original message',
        description: e.message,
        variant: 'destructive',
      });
    }
  }, [pendingReplies, toast]);

  const handleSelectDraft = (d) => {
    setSelectedDraft(d);
    setSelectedReply(null);
    setEditedSubject(d.subject || '');
    setEditedBody(d.body || '');
    setTone(d.tone || 'professional');
    // Every new draft opens in the editor, not the preview.
    setShowBodyPreview(false);
    // Drafts always land in the composer — the user came to review/edit.
    setComposerOpen(true);
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
        length,
      });
      const d = res?.data;
      if (d?.draft_id) {
        toast({ title: 'Draft generated', description: 'Review it below — you can also attach files before sending.' });
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
          // Fresh draft starts with no attachments. The user can add them
          // from the composer below before approving + sending.
          attachments: [],
        });
        refreshAll();
      }
    } catch (e) {
      console.error('Generate draft failed', e);
      const isHardBlock = e?.status === 402 || e?.status === 403 || e?.data?.hard_block;
      toast({
        title: isHardBlock ? 'Generation blocked' : 'Could not generate draft',
        description: isHardBlock ? (e?.data?.message || e?.message || 'API key or quota issue. Check your API Keys settings.') : humanizeAiError(e?.message),
        variant: 'destructive',
      });
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
        length,
      });
      const d = res?.data;
      if (d?.draft_id) {
        toast({ title: 'Regenerated' });
        setEditedSubject(d.subject);
        setEditedBody(d.body);
        // Attachments come along automatically: the backend reassigns the
        // parent draft's attachment rows to the new child (see
        // ReplyDraftAgent.regenerate_draft), but we also need to update the
        // local attachment URLs so they point at the new draft id.
        const oldAttachments = Array.isArray(selectedDraft.attachments) ? selectedDraft.attachments : [];
        const carriedAttachments = oldAttachments.map((a) => ({
          ...a,
          download_url: `/api/reply-draft/drafts/${d.draft_id}/attachments/${a.id}/download`,
        }));
        setSelectedDraft({
          ...selectedDraft,
          id: d.draft_id,
          subject: d.subject,
          body: d.body,
          ai_notes: d.reasoning,
          attachments: carriedAttachments,
        });
        refreshDrafts();
      }
    } catch (e) {
      console.error('Regenerate draft failed', e);
      const isHardBlock = e?.status === 402 || e?.status === 403 || e?.data?.hard_block;
      toast({
        title: isHardBlock ? 'Generation blocked' : 'Could not regenerate draft',
        description: isHardBlock ? (e?.data?.message || e?.message || 'API key or quota issue. Check your API Keys settings.') : humanizeAiError(e?.message),
        variant: 'destructive',
      });
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
        // refreshAll already pulls inbox + sent + drafts; the agent's
        // _mirror_sent_to_inbox writes a Sent-row at send time so this
        // refresh picks it up instantly instead of waiting for the next
        // 5-minute IMAP sync.
        refreshAll();
      } else {
        throw new Error(sent.message || 'Send failed');
      }
    } catch (e) {
      // No toast on failure — the inline "Send failed" banner inside the
      // draft pane (gated on selectedDraft.status === 'failed' &&
      // selectedDraft.send_error) renders the same humanized message and
      // persists until the user fixes the issue or discards. Toasts pop
      // out of the modal and dismiss themselves; for SMTP rejections we
      // want the error visible while the user edits attachments / body.
      // Backend already called mark_failed; mirror that state locally so
      // the banner renders immediately instead of after a refresh.
      console.error('Approve+send failed', e);
      setSelectedDraft((curr) => (
        curr && curr.id === selectedDraft.id
          ? { ...curr, status: 'failed', send_error: e?.message || 'Send failed' }
          : curr
      ));
      // Keep the Drafts list in sync with the new 'failed' status so the
      // status pill on the row matches what the pane shows.
      refreshDrafts();
    } finally {
      setBusy(false);
    }
  };

  const handleAttachFiles = async (fileList) => {
    if (!selectedDraft?.id) {
      toast({
        title: 'Generate a draft first',
        description: 'Files attach to a specific draft — click Generate AI Draft, then add attachments.',
        variant: 'destructive',
      });
      return;
    }
    const files = Array.from(fileList || []).filter(Boolean);
    if (files.length === 0) return;

    const existing = Array.isArray(selectedDraft.attachments) ? selectedDraft.attachments : [];
    if (existing.length + files.length > DRAFT_ATTACHMENT_MAX_COUNT) {
      toast({
        title: 'Too many attachments',
        description: `A draft can have at most ${DRAFT_ATTACHMENT_MAX_COUNT} files.`,
        variant: 'destructive',
      });
      return;
    }

    setUploadingAttachment(true);
    try {
      // Upload sequentially so the backend's per-draft count check sees
      // each prior file before deciding on the next one. Parallel POSTs
      // would race past the cap when many files are picked at once.
      const added = [];
      for (const file of files) {
        if ((file.size || 0) > DRAFT_ATTACHMENT_MAX_BYTES) {
          toast({
            title: 'File too large',
            description: `${file.name} is over ${Math.floor(DRAFT_ATTACHMENT_MAX_BYTES / (1024 * 1024))} MB and was skipped.`,
            variant: 'destructive',
          });
          continue;
        }
        try {
          const res = await uploadDraftAttachment(selectedDraft.id, file);
          if (res?.data) added.push(res.data);
        } catch (e) {
          toast({ title: `Upload failed: ${file.name}`, description: e.message, variant: 'destructive' });
        }
      }
      if (added.length > 0) {
        setSelectedDraft((current) => (
          current && current.id === selectedDraft.id
            ? { ...current, attachments: [...(current.attachments || []), ...added] }
            : current
        ));
      }
    } finally {
      setUploadingAttachment(false);
    }
  };

  const handleRemoveAttachment = async (attachmentId) => {
    if (!selectedDraft?.id) return;
    try {
      await deleteDraftAttachment(selectedDraft.id, attachmentId);
      setSelectedDraft((current) => (
        current && current.id === selectedDraft.id
          ? { ...current, attachments: (current.attachments || []).filter((a) => a.id !== attachmentId) }
          : current
      ));
    } catch (e) {
      toast({ title: 'Could not remove attachment', description: e.message, variant: 'destructive' });
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

  // Sent tab now lists every message synced from the mailbox's Sent
  // folder, not just drafts the user pushed through this tool. Search
  // matches recipient + subject (sender is always us, so it's omitted).
  const filteredSentEmails = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return sentEmails;
    return sentEmails.filter((m) =>
      [m.to_email, m.subject].some((v) => (v || '').toLowerCase().includes(q))
    );
  }, [sentEmails, search]);

  // Reset to the first page whenever the tab or search term changes — the
  // visible list is different, so keeping the old page number would show a
  // blank/wrong slice.
  useEffect(() => { setListPage(1); }, [activeTab, search]);

  // The current list's items and its page slice. Derived from the active
  // tab so the pager + render below share one source of truth.
  const activeListItems = activeTab === 'inbox'
    ? filteredInbox
    : activeTab === 'drafts'
      ? filteredUnsentDrafts
      : filteredSentEmails;
  const pagedListItems = useMemo(() => {
    const start = (listPage - 1) * PAGE_SIZE;
    return activeListItems.slice(start, start + PAGE_SIZE);
  }, [activeListItems, listPage]);

  // Tour steps depend on whether an inbox is attached (Compose/Settings
  // steps are dropped when it isn't). Memoized on the boolean, not the
  // array, so a background sync-accounts poll doesn't rebuild the list
  // mid-tour and reset the user's step.
  const hasAttachedAccount = syncAccounts.length > 0;
  const tourSteps = useMemo(
    () => buildReplyDraftTourSteps(hasAttachedAccount),
    [hasAttachedAccount]
  );

  const stats = useMemo(() => ({
    pending: pendingReplies.length,
    draftsPending: drafts.filter((d) => d.status === 'pending').length,
    // Sent stat now mirrors the Sent tab — total synced Sent-folder mail
    // for the active time window. Sent drafts (status='sent') are folded
    // into Failed if they errored, otherwise they're already in this list
    // because the agent dispatches via the same mailbox.
    sent: sentEmails.length,
    failed: drafts.filter((d) => d.status === 'failed').length,
  }), [pendingReplies, sentEmails, drafts]);

  // Auth, module-access gate, and loading spinner are handled by the shared
  // AgentLayout shell that wraps this route — this component renders only its
  // own workspace content. The page's own effects still set `hasAccess`, which
  // gates the data-fetch/polling effects below.
  if (loading || checkingAccess || !modulesLoaded || !companyUser || !hasAccess) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  // Sent-folder rows store our own address in from_*, so flip to the
  // recipient (to_email) when showing an outgoing message — otherwise
  // the header would just say "to: me".
  const selectedContact = selectedReply
    ? (selectedReply.direction === 'out'
      ? { name: selectedReply.to_email, email: selectedReply.to_email, company: '', jobTitle: '' }
      : { name: selectedReply.from_name, email: selectedReply.from_email, company: selectedReply.from_company, jobTitle: selectedReply.from_job_title })
    : selectedDraft
      ? { name: selectedDraft.to_name, email: selectedDraft.to_email, company: selectedDraft.to_company }
      : null;

  // `body_html` is forwarded so EmailBody can render the original markup
  // for synced messages. The draft serializer now ships `original_body_html`
  // for inbox-sourced drafts (IMAP-synced HTML mail), so newsletter /
  // marketing emails render the same way they do in the Inbox tab. Falls
  // back to empty when the source had no HTML (e.g. campaign-Reply rows).
  const originalEmail = selectedReply
    ? { ...selectedReply }
    : (selectedDraft
      ? {
        subject: selectedDraft.original_subject,
        body: selectedDraft.original_body,
        body_html: selectedDraft.original_body_html || '',
        replied_at: selectedDraft.created_at,
      }
      : null);

  const isReadOnly = selectedDraft?.status === 'sent' || selectedDraft?.status === 'rejected';
  // Fresh-compose drafts have no source email — `original_subject` and
  // `original_body` come back empty from the serializer. Without this
  // flag we'd render the big "Original Email Viewer" card with nothing
  // inside it sitting above the composer, which looks broken. Detected
  // by the backend's `source` field (set to 'compose' when the draft
  // was created via the New Message modal) with a content-empty
  // fallback for older drafts that predate the field.
  const isComposeDraft = !selectedReply && !!selectedDraft && (
    selectedDraft.source === 'compose'
    || (!selectedDraft.original_subject && !selectedDraft.original_body)
  );

  return (
    <>
      <Helmet><title>Reply Draft Agent | Pay Per Project</title></Helmet>
      {/* Navbar + left sidebar are provided by the shared AgentLayout shell that
          wraps this route, so it stays mounted while navigating between agents. */}

        {/* First-visit "how it works" summary — same modal as Marketing / Exec Meeting */}
        <HowItWorksModal
          open={howItWorksOpen}
          onClose={handleCloseHowItWorks}
          title="How the Reply Draft Agent works"
          subtitle="What it does for you, automatically"
          steps={RD_HOWITWORKS_STEPS}
          primaryLabel="Got it"
        />

        {/* Interactive guided tour — highlights each part of the workspace
            step by step. Reuses the shared FrontlineTutorial engine. */}
        <FrontlineTutorial
          open={tourOpen}
          onClose={() => setTourOpen(false)}
          steps={tourSteps}
          storageKey={REPLY_DRAFT_TOUR_KEY}
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
              <span className="text-xs text-gray-400 hidden sm:inline">
                {isSyncRunning ? 'Polling every 5s while syncing' : 'Auto-refreshes every 30s'}
              </span>

              {/* How it works — re-open the onboarding summary any time */}
              <HoverTip tip="See how this agent works — a quick walkthrough of drafting and sending replies">
                <Button
                  variant="outline"
                  className="bg-white/5 border-white/15 text-white/80 hover:bg-white/10 hover:text-white gap-2"
                  onClick={() => setHowItWorksOpen(true)}
                >
                  <Sparkles className="h-4 w-4" />
                  <span className="hidden sm:inline text-xs font-medium">How it works</span>
                </Button>
              </HoverTip>

              {/* Take the Tour — replay the interactive step-by-step walkthrough */}
              <HoverTip tip="Take an interactive tour that highlights each part of the workspace">
                <Button
                  data-tour="rd-replay"
                  variant="outline"
                  className="bg-white/5 border-amber-500/30 text-amber-200 hover:bg-amber-500/10 hover:text-amber-100 gap-2"
                  onClick={() => setTourOpen(true)}
                >
                  <GraduationCap className="h-4 w-4" />
                  <span className="hidden sm:inline text-xs font-medium">Take the Tour</span>
                </Button>
              </HoverTip>

              <span data-tour="rd-account" className="inline-flex">
                <AttachedAccountButton
                  syncAccounts={syncAccounts}
                  onAddNew={openAddAccountModal}
                />
              </span>

              {/* Compose: opens a Gmail-style new-email modal. Hidden
                  until the user attaches an inbox account, since the
                  send pipeline picks credentials off that account. */}
              {syncAccounts.length > 0 && (
                <HoverTip tip="Write a brand-new email from your attached inbox account">
                  <Button
                    data-tour="rd-compose"
                    variant="outline"
                    className="bg-white/5 border-fuchsia-500/30 text-fuchsia-200 hover:bg-fuchsia-500/10 hover:text-fuchsia-100 gap-2"
                    onClick={() => setComposeOpen(true)}
                  >
                    <PenSquare className="h-4 w-4" />
                    <span className="hidden sm:inline text-xs font-medium">Compose</span>
                  </Button>
                </HoverTip>
              )}

              {syncAccounts.length > 0 && (
                <HoverTip tip="Inbox analytics and attached-account settings">
                  <Button
                    data-tour="rd-settings"
                    variant="outline"
                    className="bg-white/5 border-white/10 text-white hover:bg-white/10 hover:text-white gap-2"
                    onClick={() => setSettingsOpen(true)}
                  >
                    <SettingsIcon className="h-4 w-4" />
                    <span className="hidden sm:inline text-xs font-medium">Settings</span>
                  </Button>
                </HoverTip>
              )}

              <Button
                data-tour="rd-refresh"
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
          <div data-tour="rd-stats" className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
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
                <div data-tour="rd-tabs" className="p-2 border-b border-white/10 flex items-center gap-2">
                  <div className="flex-1 flex">
                    <HoverTip tip="Incoming replies waiting for you to draft an answer" className="flex-1">
                      <button
                        onClick={() => setActiveTab('inbox')}
                        className={`w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === 'inbox'
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
                    </HoverTip>
                    <HoverTip tip="AI-written reply drafts you haven't sent yet" className="flex-1">
                      <button
                        onClick={() => setActiveTab('drafts')}
                        className={`w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === 'drafts'
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
                    </HoverTip>
                    <HoverTip tip="Replies you've already approved and sent" className="flex-1">
                      <button
                        onClick={() => setActiveTab('sent')}
                        className={`w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === 'sent'
                            ? 'bg-gradient-to-r from-emerald-500/20 to-teal-500/20 text-emerald-200 border border-emerald-500/30'
                            : 'text-gray-400 hover:text-white hover:bg-white/5'
                          }`}
                      >
                        <Check className="h-4 w-4" />
                        Sent
                        {sentEmails.length > 0 && (
                          <span className={`ml-1 text-[10px] font-bold px-1.5 py-0.5 rounded-full ${activeTab === 'sent' ? 'bg-emerald-500/30 text-emerald-100' : 'bg-white/10 text-gray-300'}`}>
                            {sentEmails.length}
                          </span>
                        )}
                      </button>
                    </HoverTip>
                  </div>
                </div>

                {/* Search */}
                <div data-tour="rd-search" className="p-3 border-b border-white/10 space-y-2">
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
                            : 'Search sent emails…'
                      }
                      className="w-full bg-white/5 border border-white/10 rounded-lg pl-9 pr-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500/50 focus:bg-white/10 transition"
                    />
                  </div>

                  {(activeTab === 'inbox' || activeTab === 'sent') && (
                    <select
                      value={syncDays}
                      onChange={(e) => setSyncDays(Number(e.target.value))}
                      title="Filter to a rolling time window. Mail is pre-synced in the background, so switching is instant."
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

                {/* Loading strip — subtle indeterminate bar while the inbox or
                    sent list refetches. Triggered by dropdown changes + the
                    30s poll; sits above the list so rows don't shift. */}
                {((inboxLoading && activeTab === 'inbox') || (sentLoading && activeTab === 'sent')) && (
                  <div className="relative h-0.5 overflow-hidden bg-white/5">
                    <div className={`absolute inset-y-0 w-1/3 bg-gradient-to-r from-transparent ${activeTab === 'sent' ? 'via-emerald-400/70' : 'via-cyan-400/70'} to-transparent animate-[inbox-loading_1.2s_ease-in-out_infinite]`} />
                  </div>
                )}

                {/* List — paginated (PAGE_SIZE rows per page). Only the
                    current page's rows are mounted, so a busy mailbox never
                    puts hundreds of nodes in the DOM at once. The scroll
                    area holds the rows; the pager sits pinned below it. */}
                <div className="lg:flex-1 lg:min-h-0 flex flex-col h-[60vh] lg:h-auto">
                  <div className="custom-scrollbar flex-1 min-h-0 overflow-y-auto">
                    {activeTab === 'inbox' && (
                      filteredInbox.length === 0 ? (
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
                        pagedListItems.map((r) => (
                          <InboxItem
                            key={r.id}
                            reply={r}
                            active={selectedReply?.id === r.id}
                            onClick={() => handleSelectReply(r)}
                          />
                        ))
                      )
                    )}
                    {activeTab === 'drafts' && (
                      filteredUnsentDrafts.length === 0 ? (
                        <EmptyState
                          icon={FileText}
                          title={search ? 'No matches' : 'No drafts yet'}
                          subtitle={search ? 'Try a different search term.' : 'Drafts generated and not sent will appear here.'}
                        />
                      ) : (
                        pagedListItems.map((d) => (
                          <DraftItem
                            key={d.id}
                            draft={d}
                            active={selectedDraft?.id === d.id}
                            onClick={() => handleSelectDraft(d)}
                          />
                        ))
                      )
                    )}
                    {activeTab === 'sent' && (
                      filteredSentEmails.length === 0 ? (
                        <EmptyState
                          icon={Send}
                          title={search ? 'No matches' : 'No sent emails yet'}
                          subtitle={search ? 'Try a different search term.' : 'Mail synced from your Sent folder will appear here.'}
                        />
                      ) : (
                        pagedListItems.map((m) => (
                          <InboxItem
                            key={m.id}
                            reply={m}
                            active={selectedReply?.id === m.id}
                            onClick={() => handleSelectReply(m)}
                          />
                        ))
                      )
                    )}
                  </div>
                  <Paginator
                    page={listPage}
                    totalItems={activeListItems.length}
                    pageSize={PAGE_SIZE}
                    onPage={setListPage}
                  />
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

              {/* Original Email Viewer — always stretched to match the
                  left list panel's exact height (calc(100vh-220px)).
                  Using `h-` (not `min-h-`) so the card forces the full
                  height even when the email body is short. When the
                  composer opens it appears *below* this card and the
                  right pane scrolls, so the viewer keeps its full
                  height instead of shrinking. */}
              {(selectedReply || selectedDraft) && originalEmail && (
                // Compose drafts get a compact "To: <recipient>" header
                // instead of the full email viewer — there's no source
                // message to show, so the body / attachments / AI-analysis
                // section below would just render as empty whitespace.
                // Fixed-height layout (`lg:h-[calc(...)]`) is also dropped
                // for compose so the composer underneath rises up to the
                // top of the pane like a Gmail compose window.
                <div className={`rounded-2xl bg-black/40 border border-white/10 backdrop-blur-sm overflow-hidden flex flex-col lg:flex-shrink-0 ${isComposeDraft ? '' : 'lg:h-[calc(100vh-220px)]'
                  }`}>
                  <div className={isComposeDraft ? 'p-4' : 'p-5 border-b border-white/10'}>
                    <div className="flex items-start justify-between gap-4 mb-4">
                      <div className="flex items-start gap-3 min-w-0 flex-1">
                        <Avatar name={selectedContact?.name} email={selectedContact?.email} size="lg" />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-base font-semibold text-white truncate">
                              {selectedContact?.name || selectedContact?.email || 'Unknown sender'}
                            </span>
                            {/* {selectedReply?.interest_level && INTEREST_STYLES[selectedReply.interest_level] && (
                              <Badge variant="outline" className={`${INTEREST_STYLES[selectedReply.interest_level].className} border`}>
                                {INTEREST_STYLES[selectedReply.interest_level].label}
                              </Badge>
                            )} */}
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
                      {/* Right-aligned header chips: close (X) + "New message" + "In reply to" + campaign. */}
                      <div className="flex flex-col items-end gap-2 shrink-0">
                        {/* Close the open message and return to the empty
                            "Select a message" state (same as clicking away). */}
                        <button
                          type="button"
                          onClick={clearSelection}
                          aria-label="Close message"
                          title="Close message"
                          className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/10 transition"
                        >
                          <X className="h-4 w-4" />
                        </button>
                        {isComposeDraft && (
                          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-fuchsia-500/10 border border-fuchsia-500/30 text-xs text-fuchsia-200">
                            <PenSquare className="h-3 w-3 shrink-0" />
                            <span className="font-semibold">New message</span>
                            <span className="hidden sm:inline text-fuchsia-300/70">— edit and send below</span>
                          </div>
                        )}
                        {/* "In reply to" chip — only on Sent-tab rows whose
                            backend payload included a `replies_to` lookup.
                            Clicking it jumps to the original inbound message
                            so the user can see what they were replying to. */}
                        {selectedReply?.replies_to && (
                          <button
                            type="button"
                            onClick={() => handleOpenParentEmail(selectedReply.replies_to)}
                            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-xs text-cyan-200 hover:bg-cyan-500/20 hover:border-cyan-500/50 transition group max-w-[320px]"
                            title="Open the message this reply was sent in response to"
                          >
                            <CornerUpLeft className="h-3 w-3 shrink-0" />
                            <span className="text-cyan-300/80 font-semibold shrink-0">In reply to:</span>
                            <span className="truncate text-white/90 group-hover:text-white">
                              {selectedReply.replies_to.subject || '(no subject)'}
                            </span>
                            {selectedReply.replies_to.from_email && (
                              <span className="hidden sm:inline text-cyan-300/60 shrink-0">
                                · {selectedReply.replies_to.from_name || selectedReply.replies_to.from_email}
                              </span>
                            )}
                          </button>
                        )}
                        {selectedReply?.campaign && (
                          <div className="hidden md:flex items-center gap-1.5 text-xs text-gray-400 bg-white/5 border border-white/10 rounded-full px-3 py-1">
                            <Zap className="h-3 w-3" />
                            {selectedReply.campaign}
                          </div>
                        )}
                      </div>
                    </div>
                    {!isComposeDraft && (
                      <h2 className="text-lg font-bold text-white leading-snug">
                        {originalEmail.subject || '(no subject)'}
                      </h2>
                    )}



                  </div>

                  {!isComposeDraft && (
                    <div className="p-5 flex-1 overflow-y-auto custom-scrollbar">
                      <EmailBody
                        body={originalEmail.body}
                        bodyHtml={originalEmail.body_html}
                        direction={
                          // For inbox/sent rows, trust the row's own direction.
                          // For draft-context views (selectedDraft path), the
                          // pane shows the *source* incoming email being
                          // replied to, so it's always 'in'.
                          selectedReply ? (selectedReply.direction || 'in') : 'in'
                        }
                      />
                      {/* Attachment strip with three states:
                          1. attachments_fetched=false → still pulling
                             from IMAP (lazy fetch in progress) →
                             skeleton + spinner so the user knows it's
                             loading, not broken or done.
                          2. attachments_fetched=true + empty list →
                             email genuinely has no attachments → render
                             nothing.
                          3. has attachments → render the list. */}
                      {originalEmail.attachments_fetched === false ? (
                        <AttachmentLoading />
                      ) : (
                        Array.isArray(originalEmail.attachments)
                        && originalEmail.attachments.length > 0
                        && <AttachmentList attachments={originalEmail.attachments} />
                      )}
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
                  )}

                  {/* Reply CTA — sticks to the bottom of the viewer card
                      and reveals the AI-draft composer below on click.
                      Hidden for sent (direction='out') rows since
                      replying to your own outgoing mail isn't a flow,
                      and hidden once the composer is already open. */}
                  {selectedReply && !selectedDraft && selectedReply.direction !== 'out' && !composerOpen && (
                    <div className="border-t border-white/10 px-5 py-3 flex justify-end">
                      <HoverTip tip="Draft a reply to this email with AI">
                        <Button
                          onClick={() => setComposerOpen(true)}
                          className="bg-gradient-to-r from-fuchsia-500 to-purple-600 hover:from-fuchsia-600 hover:to-purple-700 text-white"
                        >
                          <CornerUpLeft className="h-4 w-4 mr-2" />
                          Reply
                        </Button>
                      </HoverTip>
                    </div>
                  )}
                </div>
              )}

              {/* Composer / Draft Editor */}
              {/* Compose panel — hidden for selected Sent-tab rows. They're
                  outgoing mail we already sent, so the "generate a reply"
                  flow doesn't apply; the right pane shows the message body
                  in the section above and stops there.
                  Also gated behind `composerOpen`: inbox rows start with
                  the panel collapsed and only show it once the user
                  clicks the Reply button on the email viewer above.
                  Drafts open it automatically (see handleSelectDraft). */}
              {(selectedReply || selectedDraft) && selectedReply?.direction !== 'out' && composerOpen && (
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
                    <div className="flex items-center gap-2">
                      {selectedDraft && STATUS_STYLES[selectedDraft.status] && (
                        <Badge variant="outline" className={`${STATUS_STYLES[selectedDraft.status].className} border`}>
                          {STATUS_STYLES[selectedDraft.status].label}
                        </Badge>
                      )}
                      {selectedDraft && selectedDraft.regeneration_count > 0 && (
                        <Badge variant="outline" className="bg-white/5 text-gray-300 border-white/10">
                          Regen ×{selectedDraft.regeneration_count}
                        </Badge>
                      )}
                      {/* Hide / collapse the composer. Only meaningful for
                          inbox rows — drafts come from the Drafts tab
                          specifically to be edited, so don't let the
                          user accidentally collapse them. */}
                      {selectedReply && !selectedDraft && (
                        <button
                          type="button"
                          onClick={() => setComposerOpen(false)}
                          title="Hide reply composer"
                          className="h-8 w-8 flex items-center justify-center rounded-lg text-gray-400 hover:text-white hover:bg-white/10 transition"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="p-5 space-y-4">
                    {/* Tone + Length + Instructions — only meaningful for
                        AI-drafted replies. Compose drafts are user-typed
                        from scratch with no source email; the AI doesn't
                        regenerate them, so these controls just confuse
                        the user (and Regenerate would 400 with
                        "original_email_id or inbox_email_id is required"). */}
                    {!isReadOnly && !isComposeDraft && (
                      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
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
                        <div>
                          <label className="text-xs font-medium text-gray-300 mb-1.5 block">Length</label>
                          <select
                            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-500/50 focus:bg-white/10 transition"
                            value={length}
                            onChange={(e) => setLength(e.target.value)}
                            disabled={busy}
                          >
                            {LENGTHS.map((l) => (<option key={l.value} value={l.value} className="bg-gray-900">{l.label}</option>))}
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
                      <HoverTip tip="Let AI write a reply draft to this email for you to review" className="w-full">
                        <Button
                          onClick={handleGenerate}
                          disabled={busy}
                          className="w-full bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-semibold shadow-lg shadow-cyan-500/20 h-11"
                        >
                          {busy ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Sparkles className="h-4 w-4 mr-2" />}
                          {busy ? 'Drafting reply…' : 'Generate AI Draft'}
                        </Button>
                      </HoverTip>
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
                          <div className="flex items-center justify-between mb-1.5">
                            <label className="text-xs font-medium text-gray-300 block">Message Body</label>
                            {/* Edit ⇄ Preview toggle. Preview renders the body
                                the way it'll be sent — HTML mail in a sandboxed
                                frame, plain text as-is — so the user can check
                                the result without reading raw markup. */}
                            <div className="inline-flex rounded-lg border border-white/10 overflow-hidden text-[11px] font-medium">
                              <button
                                type="button"
                                onClick={() => setShowBodyPreview(false)}
                                className={`px-2.5 py-1 transition ${!showBodyPreview ? 'bg-cyan-500/20 text-cyan-200' : 'text-gray-400 hover:text-white hover:bg-white/5'}`}
                              >
                                Edit
                              </button>
                              <button
                                type="button"
                                onClick={() => setShowBodyPreview(true)}
                                className={`px-2.5 py-1 transition border-l border-white/10 ${showBodyPreview ? 'bg-cyan-500/20 text-cyan-200' : 'text-gray-400 hover:text-white hover:bg-white/5'}`}
                              >
                                Preview
                              </button>
                            </div>
                          </div>
                          {showBodyPreview ? (
                            <div className="w-full bg-white/5 border border-white/10 rounded-lg p-3 min-h-[180px] max-h-[48vh] overflow-y-auto custom-scrollbar">
                              {!editedBody.trim() ? (
                                <div className="text-sm text-gray-500 italic">Nothing to preview yet.</div>
                              ) : looksLikeHtml(editedBody) ? (
                                <HtmlBody html={editedBody} />
                              ) : (
                                <div className="text-sm text-gray-100 whitespace-pre-wrap leading-relaxed">
                                  {editedBody}
                                </div>
                              )}
                            </div>
                          ) : (
                            <textarea
                              className="w-full bg-white/5 border border-white/10 rounded-lg p-3 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500/50 focus:bg-white/10 transition disabled:opacity-60 font-sans leading-relaxed min-h-[180px] max-h-[48vh] overflow-y-auto resize-y"
                              rows={9}
                              value={editedBody}
                              onChange={(e) => setEditedBody(e.target.value)}
                              disabled={busy || isReadOnly}
                            />
                          )}
                          <div className="text-xs text-gray-500 mt-1.5 flex items-center justify-between">
                            <span>{editedBody.length} characters · ~{editedBody.trim().split(/\s+/).filter(Boolean).length} words</span>
                            {selectedDraft.updated_at && (
                              <span>Last updated {formatRelative(selectedDraft.updated_at)}</span>
                            )}
                          </div>
                        </div>

                        <DraftAttachmentsSection
                          draft={selectedDraft}
                          uploading={uploadingAttachment}
                          isReadOnly={isReadOnly}
                          onPickFiles={handleAttachFiles}
                          onRemove={handleRemoveAttachment}
                        />

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
                              {/* Run the stored backend error through the
                                  same humanizer the Compose modal uses, so
                                  the user reads "blocked for security
                                  reasons" instead of a raw 552 / 5.7.0
                                  SMTP response dump. The original string
                                  is still logged on the server side. */}
                              <div className="text-red-300/80">{humanizeSendError(selectedDraft.send_error)}</div>
                            </div>
                          </div>
                        )}

                        {!isReadOnly && (
                          <div className="flex items-center justify-between gap-2 flex-wrap pt-2 border-t border-white/10">
                            <HoverTip tip="Delete this draft without sending">
                              <Button
                                onClick={handleReject}
                                disabled={busy}
                                variant="outline"
                                className="bg-transparent border-rose-500/30 text-rose-300 hover:bg-rose-500/10 hover:text-rose-200"
                              >
                                <Trash2 className="h-4 w-4 mr-2" />
                                Discard
                              </Button>
                            </HoverTip>
                            <div className="flex items-center gap-2">
                              {/* Regenerate is an AI flow that needs a
                                  source message (Reply or InboxEmail) to
                                  riff off. Compose drafts have neither —
                                  hiding the button avoids the confusing
                                  "original_email_id or inbox_email_id is
                                  required" error and matches user intent
                                  (compose = manual writing, not AI). */}
                              {!isComposeDraft && (
                                <HoverTip tip="Ask AI to write a fresh version of this draft">
                                  <Button
                                    onClick={handleRegenerate}
                                    disabled={busy}
                                    variant="outline"
                                    className="bg-white/5 border-white/10 text-white hover:bg-white/10"
                                  >
                                    {busy ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <RefreshCw className="h-4 w-4 mr-2" />}
                                    Regenerate
                                  </Button>
                                </HoverTip>
                              )}
                              <HoverTip tip="Send this reply from your attached inbox account">
                                <Button
                                  onClick={handleApproveAndSend}
                                  disabled={busy || !editedBody.trim() || !editedSubject.trim()}
                                  className="bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white font-semibold shadow-lg shadow-emerald-500/20"
                                >
                                  {busy ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Send className="h-4 w-4 mr-2" />}
                                  Approve & Send
                                </Button>
                              </HoverTip>
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
          clearSelection();
          refreshSyncAccounts();
          refreshAll();
        }}
      />

      <ComposeModal
        open={composeOpen}
        onClose={() => {
          setComposeOpen(false);
          // ComposeModal autosaves on close so a half-finished compose
          // lands in the Drafts tab. Refresh the drafts list immediately
          // so the new/updated row appears without waiting for the next
          // tab switch or manual refresh.
          refreshDrafts();
        }}
        onSent={() => {
          setComposeOpen(false);
          // refreshAll picks up the sent-mirror row + drafts list change
          // (the compose draft transitions to status='sent' on success).
          refreshAll();
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

export default ReplyDraftAgentPage;
