// Guided-tour step definitions for the Marketing Agent dashboard.
// Reuses the generic FrontlineTutorial overlay (open/onClose/setActiveTab/
// steps/storageKey). Each step optionally switches to a tab (`tab`) and
// highlights an element via a `data-tour-mkt="..."` selector.
//
// One step per tab: we highlight the WHOLE page for that tab (the
// `[data-tour-mkt="page-<tab>"]` container) and describe every important
// control inside it in the body — instead of a separate ring per button.

export const MARKETING_TOUR_KEY = 'marketing_tutorial_seen_v3';

// localStorage key for the auto "How it works" modal (shown once on first visit,
// before the guided tour). Separate from the tour key so the two are independent.
export const MARKETING_HOWITWORKS_KEY = 'marketing_howitworks_seen_v1';

// High-level "what this agent does for you" steps for the HowItWorksModal.
// Icon names are string keys resolved in MarketingDashboard. Keep titles to ~1
// line and bodies to ~2 lines so every card reads as the same size.
export const MARKETING_HOWITWORKS_STEPS = [
  {
    icon: 'Mail',
    title: 'Connect an email account',
    body: 'Add the account campaigns send from (SMTP or provider) test it and you\'re ready.',
  },
  {
    icon: 'Megaphone',
    title: 'Let AI build a campaign',
    body: 'Tell the Outreach Agent your goal and it drafts the whole email campaign for you.',
  },
  {
    icon: 'Users',
    title: 'Generate & enrich leads',
    body: 'The AI finds and enriches leads for your campaign so you\'re not starting from zero.',
  },
  {
    icon: 'Sparkles',
    title: 'AI builds the sequence',
    body: 'The AI drafts a multi-step email sequence the first touch plus timed follow-ups.',
  },
  {
    icon: 'Mail',
    title: 'Smart follow-ups by reply',
    body: 'AI reads each reply and picks the next email interested, not interested or a question all get the right follow-up.',
  },
  {
    icon: 'Send',
    title: 'Launch the campaign',
    body: 'Hit launch and every email in the sequence sends on schedule no manual sending.',
  },
  {
    icon: 'TrendingUp',
    title: 'Track performance live',
    body: 'Opens, clicks, replies and conversions update in real time on each campaign.',
  },
  {
    icon: 'Sparkles',
    title: 'Ask AI about your results',
    body: 'Type a question about your campaigns and AI answers in plain language from your campaign data.',
  },
  {
    icon: 'BarChart3',
    title: 'AI generates charts',
    body: 'Ask for a graph of any campaign stat and AI builds it save charts and pin them to your dashboard.',
  },
  {
    icon: 'FileText',
    title: 'Research & documents',
    body: 'Run AI market research and generate documents, all saved in a searchable library.',
  },
  {
    icon: 'Bell',
    title: 'Proactive health checks',
    body: 'AI monitors campaigns and raises alerts in Notifications when something needs you.',
  },
];

export const MARKETING_TOUR_STEPS = [
  // ── Intro ────────────────────────────────────────────────────────────────
  {
    title: 'Welcome to your Marketing Agent 👋',
    body: "This tour walks you through every tab and shows what each one does — creating campaigns, connecting email accounts, AI Q&A, research, documents and notifications. Skip anytime; replay later from 'Take the Tour'.",
    placement: 'center',
  },
  {
    selector: '[data-tour-mkt="stats"]',
    title: 'Your marketing snapshot',
    body: 'At-a-glance cards: total campaigns, active campaigns, total emails sent and unread alerts — a quick pulse of your outreach.',
    placement: 'bottom',
  },
  {
    selector: '[data-tour-mkt="tabs"]',
    title: 'Everything lives in these tabs',
    body: "Eight tabs cover the whole workflow. We'll open each one and explain what's on its page.",
    placement: 'bottom',
  },

  // ── One step per tab: highlight the whole page, describe everything on it ──
  {
    tab: 'dashboard',
    selector: '[data-tour-mkt="page-dashboard"]',
    title: 'Dashboard — your overview',
    body: 'Your home base. Up top, "Create campaign" jumps you into building a new campaign and "Email accounts" opens your sending accounts. Below, the "Your Campaigns" table lists everything with status, type and dates — search and filter it with the bar, tick rows to bulk-delete, or hit "Manage" to open a campaign. Any charts you pin appear here too.',
    placement: 'top',
  },
  {
    tab: 'campaigns',
    selector: '[data-tour-mkt="camp-create"]',
    title: 'Campaigns — create with AI',
    body: 'The "Outreach & Campaign Agent" form lets the AI draft a full campaign for you. Pick what you want, fill in the details (goal, audience, tone, schedule) and launch — the agent writes the emails and sets up the sequence.',
    placement: 'bottom',
  },
  {
    tab: 'campaigns',
    selector: '[data-tour-mkt="camp-list"]',
    title: 'Campaigns — manage your list',
    body: '"Your Campaigns" is the full list of everything you\'ve created. Search it, filter by status and date, and page through the results. Tick rows to bulk-delete, or click any card to open its details.',
    placement: 'top',
  },
  {
    tab: 'email',
    selector: '[data-tour-mkt="page-email"]',
    title: 'Email — sending accounts',
    body: 'Manage the accounts your campaigns send from. "Add email account" connects a new one (SMTP / provider). The table lists each account with its type, status, test result and sending stats — click a row to open its details in the sidebar.',
    placement: 'top',
  },
  {
    tab: 'qa',
    selector: '[data-tour-mkt="page-qa"]',
    title: 'Q&A — ask your data',
    body: 'Ask the AI anything about your marketing — type your question in the box and press Enter; answers are grounded in your own campaign data. Flip the mode selector to "Generate Graph" and the same box builds a chart instead. The example prompts are a quick way to start.',
    placement: 'top',
  },
  {
    tab: 'research',
    selector: '[data-tour-mkt="page-research"]',
    title: 'Research — market insights',
    body: 'Run AI market research to shape your next campaign. Choose a research type (General, Market Trend, Competitor, Customer Behavior…), enter your topic and send it. The filter icon opens extra context fields like industry and region, and past runs are saved in the History panel on the left.',
    placement: 'top',
  },
  {
    tab: 'documents',
    selector: '[data-tour-mkt="page-documents"]',
    title: 'Documents — generate & store',
    body: '"Create New Document" opens the AI generator — pick a type, add a title and instructions, and it writes a draft you can save. Below, your saved library is searchable by title or content and filterable by type and campaign; open, download or delete any document.',
    placement: 'top',
  },
  {
    tab: 'notifications',
    selector: '[data-tour-mkt="page-notifications"]',
    title: 'Notifications — alerts & health checks',
    body: 'The "Monitor Campaigns" panel runs an AI health check — pick a campaign, hit "Run Analysis", and it raises notifications for anything needing attention. Below is your inbox: filter by type, mark all read, or refresh. The unread count also shows on the tab.',
    placement: 'top',
  },
  {
    tab: 'saved-graphs',
    selector: '[data-tour-mkt="page-saved-graphs"]',
    title: 'Saved Graphs — reuse your charts',
    body: 'The AI charts you\'ve saved from Q&A live here. Each one can be previewed with "View Chart" (no regeneration needed), pinned to your dashboard, or deleted.',
    placement: 'top',
  },

  // ── Outro ─────────────────────────────────────────────────────────────────
  {
    selector: '[data-tour-mkt="replay"]',
    title: 'Need the tour again?',
    body: "Click 'Take the Tour' here anytime to replay this walkthrough. That's it — you're all set! 🎉",
    placement: 'bottom',
  },
];
