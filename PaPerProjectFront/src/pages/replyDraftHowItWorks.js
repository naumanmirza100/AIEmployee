// "How it works" steps for the Reply Draft Agent's onboarding modal (shown once
// on first visit). Icon names are string keys resolved in ReplyDraftAgentPage.
// Keep titles to ~1 line and bodies to ~2 lines so every card reads the same size.

// Bumped to _v2 when Compose / Drafts / sync-scope steps were added, so
// users who already dismissed the older 6-step version see the refreshed
// walkthrough once.
export const REPLY_DRAFT_HOWITWORKS_KEY = 'reply_draft_howitworks_seen_v2';

export const REPLY_DRAFT_HOWITWORKS_STEPS = [
  {
    icon: 'Link2',
    title: 'Connect your inbox',
    body: 'Attach an email account — the agent reads incoming replies from there.',
  },
  {
    icon: 'SettingsIcon',
    title: 'How much to sync',
    body: 'When connecting, pick how far back to sync and how many emails to fetch keeps your inbox fast.',
  },
  {
    icon: 'Inbox',
    title: 'Replies land in the inbox',
    body: 'New replies to your emails are synced automatically and listed for you to handle.',
  },
  {
    icon: 'Sparkles',
    title: 'AI drafts the reply',
    body: 'Open a reply and the AI writes a draft response pick the tone and length you want.',
  },
  {
    icon: 'PenSquare',
    title: 'Compose new emails',
    body: 'Use Compose to write a brand-new email from your connected inbox not just replies.',
  },
  {
    icon: 'Edit3',
    title: 'Review in Drafts',
    body: 'Every draft waits in the Drafts tab. Edit inline, preview how it will look, or regenerate with new instructions.',
  },
  {
    icon: 'CheckCircle2',
    title: 'Approve, then send',
    body: 'Nothing sends on its own — you approve first. It goes out on the correct email thread.',
  },
  {
    icon: 'BarChart3',
    title: 'Track it all',
    body: 'Version history of every regeneration, plus analytics on drafts and replies.',
  },
];
