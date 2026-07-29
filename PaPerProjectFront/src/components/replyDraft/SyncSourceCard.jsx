import React, { useState, useEffect } from 'react';
import { AlertCircle, Loader2, Check, Plus, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import HoverTip from '@/components/common/HoverTip';
import { STAGE_LABEL } from './replyDraftConstants';

export const SyncSourceCard = ({ accounts, onConfigure }) => {
  const total = accounts.length;
  const syncing = accounts.filter((a) => a.will_sync);
  const misconfigured = accounts.filter(
    (a) => a.is_active && a.enable_imap_sync && !a.imap_ready
  );

  // Authoritative sync state from the backend. ``sync_in_progress`` is
  // True only while sync_inbox is actively running for an account, and
  // is cleared in a finally block — so a crashed or finished worker
  // never leaves a phantom "Syncing…" banner up. ``last_sync_stage``
  // advances 0 → 30 → 60 → 90 as each staged-window phase commits.
  const activeSyncAccounts = syncing.filter((a) => a.sync_in_progress);
  const isAnySyncRunning = activeSyncAccounts.length > 0;

  // Stage label for the headline. When multiple accounts are syncing
  // we surface the SMALLEST in-progress stage — that's the next chunk
  // about to be visible to the user. (Bigger stages happen later in
  // the same run.)
  const currentStageDays = (() => {
    if (!isAnySyncRunning) return 0;
    const stages = activeSyncAccounts
      .map((a) => Number(a.last_sync_stage || 0))
      .filter((n) => n > 0);
    // last_sync_stage advances AFTER a stage finishes, so the next one
    // currently running is the smallest stage greater than the latest
    // committed value. Default to 30 (the first stage) when nothing
    // has committed yet.
    const lastCommitted = stages.length > 0 ? Math.max(...stages) : 0;
    if (lastCommitted === 0) return 30;
    if (lastCommitted === 30) return 60;
    if (lastCommitted === 60) return 90;
    return lastCommitted; // already at 90 — sync is on the last slice
  })();

  // Live-ticking timer for an "elapsed" pill. Anchored to each
  // account's updated_at (when sync was kicked off) so it ticks
  // accurately while sync_in_progress=True; we only render it while
  // the backend says sync is actually running.
  const [now, setNow] = useState(() => Date.now());
  const earliestActivity = activeSyncAccounts.length > 0
    ? Math.min(...activeSyncAccounts.map((a) =>
      new Date(a.updated_at || a.created_at || 0).getTime()
    ))
    : 0;
  const elapsedMs = earliestActivity ? Math.max(0, now - earliestActivity) : 0;

  const totalInboxCount = syncing.reduce((s, a) => s + (a.inbox_count || 0), 0);
  const firstSync = activeSyncAccounts.filter((a) => (a.inbox_count || 0) === 0);
  const firstSyncActive = firstSync.length > 0;
  const activelySyncing = isAnySyncRunning && !firstSyncActive;

  useEffect(() => {
    if (!isAnySyncRunning) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [isAnySyncRunning]);

  const mmss = (ms) => {
    const s = Math.floor(ms / 1000);
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  };

  // Friendly "Last synced N min ago" label for the steady-state banner.
  const lastSyncedLabel = (() => {
    if (isAnySyncRunning) return null;
    const completedTimestamps = syncing
      .map((a) => a.last_sync_completed_at ? new Date(a.last_sync_completed_at).getTime() : 0)
      .filter((t) => t > 0);
    if (completedTimestamps.length === 0) return null;
    const mostRecent = Math.max(...completedTimestamps);
    const ageMs = Date.now() - mostRecent;
    const mins = Math.floor(ageMs / 60000);
    if (mins < 1) return 'Synced just now';
    if (mins < 60) return `Synced ${mins} min ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `Synced ${hours} hr ago`;
    return `Synced ${Math.floor(hours / 24)} day ago`;
  })();

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
            Add a mailbox in the Marketing Agent's <span className="font-medium">Email Accounts</span> settings to start syncing email and their replies here. Without an account, this inbox stays empty.
          </div>
        </div>
        <HoverTip tip="Connect an inbox account to start syncing email and their replies into this agent">
          <Button
            onClick={onConfigure}
            className="bg-amber-500 hover:bg-amber-400 text-black font-semibold"
          >
            Add email account
          </Button>
        </HoverTip>
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
  // Prominent cyan banner with a live elapsed timer. Stays up for as
  // long as the backend reports sync_in_progress=True; no time cap.
  if (firstSyncActive) {
    return (
      <div className="mb-4 rounded-2xl border border-cyan-500/30 bg-cyan-500/10 px-5 py-4 flex items-start gap-4 flex-wrap">
        <div className="h-11 w-11 rounded-xl bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center shrink-0">
          <Loader2 className="h-5 w-5 text-cyan-300 animate-spin" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-cyan-100">
              Syncing your inbox… ({STAGE_LABEL[currentStageDays] || `${currentStageDays} days`})
            </span>
            <span className="text-xs font-mono text-cyan-200/80 bg-cyan-500/10 border border-cyan-500/30 rounded px-1.5 py-0.5">
              {mmss(elapsedMs)}
            </span>
          </div>
          <div className="text-xs text-cyan-200/80 mt-1">
            Pulling mail from{' '}
            <span className="text-white font-medium">
              {firstSync.map((a) => a.email).join(', ')}
            </span>
            . The most recent 30 days arrive first; 60- and 90-day backfill
            continues in the background. The inbox below updates as each
            stage commits.
          </div>
        </div>
      </div>
    );
  }

  // Sync is running and rows have already started landing. Small cyan
  // chip so the user knows the list below isn't final yet — driven by
  // the backend's sync_in_progress flag, NOT a wall-clock timeout, so
  // it stays up through the full 90-day staged backfill.
  if (activelySyncing) {
    return (
      <div className="mb-4 rounded-xl border border-cyan-500/25 bg-cyan-500/5 px-4 py-2.5 flex items-center gap-3 flex-wrap">
        <div className="h-8 w-8 rounded-lg bg-cyan-500/15 border border-cyan-500/25 flex items-center justify-center shrink-0">
          <Loader2 className="h-4 w-4 text-cyan-300 animate-spin" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-xs text-cyan-200/90">
            Syncing {STAGE_LABEL[currentStageDays] || `${currentStageDays}-day window`} —{' '}
            <span className="text-white font-medium">{totalInboxCount}</span>{' '}
            email{totalInboxCount === 1 ? '' : 's'} loaded so far from{' '}
            <span className="text-white font-medium">
              {activeSyncAccounts.map((a) => a.email).join(', ')}
            </span>
            . More are still streaming in.
          </div>
        </div>
        <span className="text-xs font-mono text-cyan-200/80 bg-cyan-500/10 border border-cyan-500/30 rounded px-1.5 py-0.5 shrink-0">
          {mmss(elapsedMs)}
        </span>
      </div>
    );
  }

  // Steady-state happy path — sync is configured AND the backend has
  // confirmed it's not running right now. We surface "last synced" so
  // the user can tell at a glance how fresh the inbox is.
  return (
    <div className="mb-4 rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-4 py-2.5 flex items-center gap-3 flex-wrap">
      <div className="h-8 w-8 rounded-lg bg-emerald-500/15 border border-emerald-500/25 flex items-center justify-center shrink-0">
        <Check className="h-4 w-4 text-emerald-300" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-xs text-emerald-200/90">
          {lastSyncedLabel ? (
            <>
              <span className="text-white font-medium">{lastSyncedLabel}</span>
              {' · '}
              {syncing.length} account{syncing.length === 1 ? '' : 's'} active
            </>
          ) : (
            <>
              Inbox sync active ·{' '}
              <span className="text-white font-medium">
                {syncing.length} account{syncing.length === 1 ? '' : 's'}
              </span>
            </>
          )}
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

// Attached-account status button for the Reply Draft dashboard header.
// If no account is attached yet, renders an "Add email account" primary
// button. Once attached, renders a non-interactive status chip showing the
// connected email — we intentionally don't offer a change control, because
// swapping the inbox source while drafts and history are tied to it would
// cause confusing stale state.
export const AttachedAccountButton = ({ syncAccounts, onAddNew }) => {
  const attached = Array.isArray(syncAccounts) && syncAccounts.length > 0 ? syncAccounts[0] : null;

  if (!attached) {
    return (
      <HoverTip tip="Connect an inbox account to start syncing email and their replies into this agent">
        <Button
          onClick={onAddNew}
          className="bg-amber-500 hover:bg-amber-400 text-black font-semibold gap-2"
        >
          <Plus className="h-4 w-4" />
          Add email account
        </Button>
      </HoverTip>
    );
  }

  const ready = attached.will_sync;
  const borderTint = ready ? 'border-emerald-500/30 bg-emerald-500/10' : 'border-amber-500/30 bg-amber-500/10';
  const textTint = ready ? 'text-emerald-200' : 'text-amber-200';

  return (
    <HoverTip tip={ready ? 'Inbox sync is active for this account' : 'Account connected, but IMAP needs attention — check the account settings'}>
      <div
        className={`h-9 max-w-[260px] rounded-md border px-3 flex items-center gap-2 ${borderTint} ${textTint}`}
      >
        {ready ? <CheckCircle2 className="h-4 w-4 shrink-0" /> : <AlertCircle className="h-4 w-4 shrink-0" />}
        <span className="truncate text-xs font-medium">{attached.email}</span>
      </div>
    </HoverTip>
  );
};
