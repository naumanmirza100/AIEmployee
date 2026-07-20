// "How it works" steps for the Reply Draft Agent's onboarding modal (shown once
// on first visit). Icon names are string keys resolved in ReplyDraftAgentPage.
// Keep titles to ~1 line and bodies to ~2 lines so every card reads the same size.

export const REPLY_DRAFT_HOWITWORKS_KEY = 'reply_draft_howitworks_seen_v1';

export const REPLY_DRAFT_HOWITWORKS_STEPS = [
  {
    icon: 'Link2',
    title: 'Connect your inbox',
    body: 'Attach an email account in Settings — the agent reads incoming replies from there.',
  },
  {
    icon: 'Inbox',
    title: 'Replies land in the inbox',
    body: 'New replies to your emails are synced automatically and listed for you to handle.',
  },
  {
    icon: 'Sparkles',
    title: 'AI drafts the reply',
    body: 'Open a reply and the AI writes a draft response — pick the tone and length you want.',
  },
  {
    icon: 'RefreshCw',
    title: 'Regenerate or edit',
    body: 'Not quite right? Regenerate with custom instructions, or edit the draft inline yourself.',
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
