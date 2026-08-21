// Guided-tour steps for the Reply Draft Agent dashboard. Consumed by the
// shared FrontlineTutorial component (src/components/frontline/FrontlineTutorial.jsx).
//
// Each step targets an element by its `data-tour="…"` attribute (set on the
// matching node in ReplyDraftAgentPage.jsx). A step with `placement: 'center'`
// and no selector renders as a centered card (used for the intro/outro).
// Keep bodies to ~2 lines so every tooltip reads the same size.

export const REPLY_DRAFT_TOUR_KEY = 'reply_draft_tour_seen_v1';

// The Compose and Settings buttons only render once an inbox account is
// attached (they need account credentials to work). Highlighting a step
// whose target doesn't exist would leave the tour stuck on a centered
// fallback card, so we build the step list from the current account state
// and drop those two steps when there's no account yet.
// `view` is 'dashboard' or 'emails'. The tabs/search steps only exist on the
// Emails page, and the folder-tiles step only exists on the Dashboard, so the
// tail of the tour is built from whichever view is currently mounted.
export function buildReplyDraftTourSteps(hasAccount, view = 'dashboard') {
  const steps = [
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
      title: hasAccount ? 'Your connected inbox' : 'Connect your inbox first',
      body: hasAccount
        ? 'This is the email account the agent reads replies from. Use it to switch or re-connect an inbox.'
        : 'Start here — attach the email account the agent reads replies from. When connecting you also choose how far back to sync (30/60/90 days) and how many emails to fetch (50/100/200). Compose, Settings, and drafts unlock once an inbox is connected.',
      placement: 'bottom',
    },
  ];

  // Account-only steps — skipped entirely when no inbox is attached.
  if (hasAccount) {
    steps.push(
      {
        selector: '[data-tour="rd-compose"]',
        title: 'Compose new emails',
        body: 'Write a brand-new email from your connected inbox — not just replies.',
        placement: 'bottom',
      },
      {
        selector: '[data-tour="rd-settings"]',
        title: 'Settings & analytics',
        body: 'Edit the attached account, adjust the sync window/limit, and see inbox analytics.',
        placement: 'bottom',
      },
    );
  }

  steps.push(
    {
      selector: '[data-tour="rd-refresh"]',
      title: 'Refresh anytime',
      body: 'The workspace auto-refreshes every 30 seconds, but you can pull the latest manually here.',
      placement: 'bottom',
    },
    ...(view === 'emails'
      ? [
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
      ]
      : [
        {
          selector: '[data-tour="rd-folders"]',
          title: 'Your mail folders',
          body: 'Open any folder to jump into the Emails page with that tab already selected. The counts stay live while you work.',
          placement: 'bottom',
        },
        {
          selector: '[data-tour="rd-activity"]',
          title: 'Email activity',
          body: 'Received vs sent volume over the last 30, 60 or 90 days — the same chart the Settings dialog shows.',
          placement: 'top',
        },
        {
          selector: '[data-tour="rd-recent"]',
          title: 'Recent activity',
          body: 'The newest inbox mail and drafts waiting on review. Click any row to open it straight in the Emails page.',
          placement: 'top',
        },
      ]),
    {
      title: "You're all set 🎉",
      body: hasAccount
        ? "Pick a reply from the Inbox to generate an AI draft, review it in Drafts, preview how it'll look, then approve and send. Replay this tour anytime from 'Take the Tour'."
        : "Connect an inbox to get started — then Compose, Settings, and AI drafting all light up. Replay this tour anytime from 'Take the Tour'.",
      placement: 'center',
    },
  );

  return steps;
}

// Default (account-present) list, kept for any caller that imports it
// directly. The page passes a state-aware list built via the function above.
export const REPLY_DRAFT_TOUR_STEPS = buildReplyDraftTourSteps(true);
