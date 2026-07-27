// Guided-tour steps for the Reply Draft Agent dashboard. Consumed by the
// shared FrontlineTutorial component (src/components/frontline/FrontlineTutorial.jsx).
//
// Each step targets an element by its `data-tour="…"` attribute (set on the
// matching node in ReplyDraftAgentPage.jsx). A step with `placement: 'center'`
// and no selector renders as a centered card (used for the intro/outro).
// Keep bodies to ~2 lines so every tooltip reads the same size.

export const REPLY_DRAFT_TOUR_KEY = 'reply_draft_tour_seen_v1';

export const REPLY_DRAFT_TOUR_STEPS = [
  {
    title: 'Welcome to the Reply Draft Agent 👋',
    body: "This quick tour shows you how to connect an inbox, let the AI draft replies, and send them. You can skip anytime, or replay it later from the 'Take the Tour' button.",
    placement: 'center',
  },
  {
    selector: '[data-tour="rd-stats"]',
    title: 'Your snapshot',
    body: 'At a glance: replies waiting for you, drafts to review, how many you\'ve sent, and any that failed to send.',
    placement: 'bottom',
  },
  {
    selector: '[data-tour="rd-account"]',
    title: 'Connect your inbox',
    body: 'Attach the email account the agent reads replies from. When connecting you also choose how far back to sync (30/60/90 days) and how many emails to fetch (50/100/200).',
    placement: 'bottom',
  },
  {
    selector: '[data-tour="rd-compose"]',
    title: 'Compose new emails',
    body: 'Write a brand-new email from your connected inbox — not just replies. Appears once an inbox is attached.',
    placement: 'bottom',
  },
  {
    selector: '[data-tour="rd-settings"]',
    title: 'Settings & analytics',
    body: 'Edit the attached account, adjust the sync window/limit, and see inbox analytics.',
    placement: 'bottom',
  },
  {
    selector: '[data-tour="rd-refresh"]',
    title: 'Refresh anytime',
    body: 'The workspace auto-refreshes every 30 seconds, but you can pull the latest manually here.',
    placement: 'bottom',
  },
  {
    selector: '[data-tour="rd-tabs"]',
    title: 'Inbox · Drafts · Sent',
    body: 'Inbox holds incoming replies. Drafts holds AI replies you haven\'t sent yet. Sent shows everything already sent.',
    placement: 'right',
  },
  {
    selector: '[data-tour="rd-search"]',
    title: 'Search & filter',
    body: 'Search within the current tab, and filter Inbox/Sent to a rolling time window. Long lists are paged so the page stays fast.',
    placement: 'right',
  },
  {
    title: "You're all set 🎉",
    body: "Pick a reply from the Inbox to generate an AI draft, review it in Drafts, preview how it'll look, then approve and send. Replay this tour anytime from 'Take the Tour'.",
    placement: 'center',
  },
];
