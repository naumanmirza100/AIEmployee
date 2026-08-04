// Mirror the backend caps in api/views/reply_draft_agent.py — keeping these
// in sync lets us surface a clear, immediate error instead of waiting for
// the server to 400. If the backend caps change, update both sides.
export const DRAFT_ATTACHMENT_MAX_BYTES = 25 * 1024 * 1024;
export const DRAFT_ATTACHMENT_MAX_COUNT = 20;

// Pure view filter for the inbox list — Celery pre-syncs the rolling
// window on a cron (see marketing_agent/management/commands/sync_inbox.py),
// so switching the dropdown just slices already-cached rows and is instant.
// 120 was retired: the cost of fetching that much mail on a fresh account
// dwarfed the benefit, and 90 days already covers the longest practical
// reply window.
export const TIME_WINDOW_OPTIONS = [
  { value: 30, label: 'Last 30 days' },
  { value: 60, label: 'Last 60 days' },
  { value: 90, label: 'Last 90 days' },
];

export const TONES = [
  { value: 'professional', label: 'Professional' },
  { value: 'friendly', label: 'Friendly' },
  { value: 'formal', label: 'Formal' },
  { value: 'casual', label: 'Casual' },
  { value: 'apologetic', label: 'Apologetic' },
  { value: 'confident', label: 'Confident' },
  { value: 'empathetic', label: 'Empathetic' },
];

// Length presets — must mirror the backend LENGTH_GUIDANCE map in
// reply_draft_agent/agents/reply_draft_agent.py. Replaces the previous
// hard "<150 word" cap baked into the system prompt.
export const LENGTHS = [
  { value: 'short', label: 'Short (60-100 words)' },
  { value: 'medium', label: 'Medium (120-200 words)' },
  { value: 'long', label: 'Long (250-400 words)' },
];

export const INTEREST_STYLES = {
  positive: { label: 'Interested', className: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' },
  requested_info: { label: 'Needs Info', className: 'bg-sky-500/15 text-sky-300 border-sky-500/30' },
  objection: { label: 'Objection', className: 'bg-amber-500/15 text-amber-300 border-amber-500/30' },
  negative: { label: 'Not Interested', className: 'bg-rose-500/15 text-rose-300 border-rose-500/30' },
  unsubscribe: { label: 'Unsubscribe', className: 'bg-red-500/15 text-red-300 border-red-500/30' },
  neutral: { label: 'Neutral', className: 'bg-slate-500/15 text-slate-300 border-slate-500/30' },
  not_analyzed: { label: 'Not Analyzed', className: 'bg-white/5 text-gray-400 border-white/10' },
};

export const STATUS_STYLES = {
  pending: { label: 'Pending', className: 'bg-amber-500/15 text-amber-300 border-amber-500/30' },
  approved: { label: 'Approved', className: 'bg-sky-500/15 text-sky-300 border-sky-500/30' },
  sent: { label: 'Sent', className: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' },
  rejected: { label: 'Discarded', className: 'bg-rose-500/15 text-rose-300 border-rose-500/30' },
  failed: { label: 'Failed', className: 'bg-red-500/15 text-red-300 border-red-500/30' },
};

export const AVATAR_PALETTE = [
  'from-cyan-500 to-blue-600',
  'from-fuchsia-500 to-purple-600',
  'from-emerald-500 to-teal-600',
  'from-amber-500 to-orange-600',
  'from-rose-500 to-pink-600',
  'from-indigo-500 to-violet-600',
];

// How many list rows to show per page. Pagination replaced an earlier
// virtualized list: with a busy mailbox the list could hold hundreds of
// rows, and mounting them all made the tab hang. Paging keeps the DOM to
// at most PAGE_SIZE rows at once — simple, predictable, no measurement
// loop. 20 fills the panel without overwhelming it.
export const PAGE_SIZE = 20;

// Banner state is driven by the backend's authoritative sync flags
// (sync_in_progress, last_sync_stage, last_sync_completed_at) rather
// than wall-clock heuristics, so a slow 90-day backfill keeps the
// "Syncing…" banner up for as long as the worker is actually working —
// and drops it the moment the last stage commits. The old time-based
// caps would hide the banner before the sync finished, leaving the
// user thinking the inbox was final when more rows were still landing.
export const STAGE_LABEL = {
  0: 'Connecting…',
  30: 'last 30 days',
  60: 'last 60 days',
  90: 'last 90 days',
};

// Reply-Draft-specific "Add account" modal. Creates the single EmailAccount
// attached to the Reply Draft Agent and fires an immediate Celery sync so the
// inbox populates within ~30s. Completely independent of the Marketing Agent
// email-accounts list.
export const ACCOUNT_TYPE_OPTIONS = [
  { value: 'gmail', label: 'Gmail', smtp_host: 'smtp.gmail.com', imap_host: 'imap.gmail.com' },
  { value: 'hostinger', label: 'Hostinger', smtp_host: 'smtp.hostinger.com', imap_host: 'imap.hostinger.com' },
  { value: 'smtp', label: 'Custom SMTP', smtp_host: '', imap_host: '' },
];

// Sync-window and per-sweep email-count presets offered in the connect
// modal. Must mirror the allowed sets the backend clamps to in
// api/views/reply_draft_agent.py (create_reply_account). Defaults: 90 days,
// 200 emails.
export const SYNC_DAYS_OPTIONS = [
  { value: 30, label: 'Last 30 days' },
  { value: 60, label: 'Last 60 days' },
  { value: 90, label: 'Last 90 days' },
];
// The cap applies PER folder PER 30-day period — the sync sweeps in
// 30-day stages, and incoming (Inbox) and outgoing (Sent) each get their
// own budget. So "200" means up to 200 received AND up to 200 sent per
// 30 days. The labels below spell this out so the number isn't mistaken
// for a single grand total.
export const SYNC_EMAIL_LIMIT_OPTIONS = [
  { value: 50, label: 'Up to 50 per 30 days' },
  { value: 100, label: 'Up to 100 per 30 days' },
  { value: 200, label: 'Up to 200 per 30 days' },
];

export const defaultNewForm = () => ({
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
  // How much history to pull, and how many emails per sweep. Defaults match
  // the backend model defaults.
  imap_sync_days: 90,
  imap_sync_email_limit: 200,
});
