// Tour step definitions for each Frontline Agent tab.
// Each tour is triggered by a "Tour this tab" button inside the tab, and
// persisted separately in localStorage via a unique storage key.

export const OVERVIEW_TOUR = {
  key: 'frontline_tour_overview_v1',
  label: 'Overview',
  steps: [
    {
      title: 'Overview tab 🏠',
      body: "Your home base. Every important signal about your Frontline operations lives on this page — SLA health, knowledge gaps, background failures, and shortcuts to every tool.",
      placement: 'center',
    },
    {
      selector: '[data-tour-ov="insights"]',
      title: 'Admin insights',
      body: 'These tiles pull real data from the last 30 days: SLA status, knowledge base gaps, background failure queue (DLQ), and recent audit events. Click the refresh icon on any tile to re-fetch.',
      placement: 'bottom',
    },
    {
      selector: '[data-tour-ov="quicknav"]',
      title: 'Quick jump to any tool',
      body: 'These shortcut cards take you straight to the most-used tabs — Documents, Knowledge Q&A, Tickets, Chat widget, Workflows, or Analytics. Click any card to switch tabs instantly.',
      placement: 'top',
    },
  ],
};

export const DOCUMENTS_TOUR = {
  key: 'frontline_tour_documents_v1',
  label: 'Documents',
  steps: [
    {
      title: 'Documents tab 📄',
      body: "This is where you build the AI's knowledge. Upload files, watch them get indexed, and manage what the AI can reference in its answers.",
      placement: 'center',
    },
    {
      selector: '[data-tour-docs="upload"]',
      title: 'Upload Document',
      body: 'Click here to upload a PDF, Word doc, or text file. Once processed, the AI can answer questions using the content — no more copy-pasting into prompts.',
      placement: 'bottom',
    },
    {
      selector: '[data-tour-docs="grid"]',
      title: 'Your document library',
      body: 'Every uploaded file lives here as a card. A colored badge tells you its status: Indexed (ready to use), Processing, Queued, or Failed. Failed uploads can be retried.',
      placement: 'top',
    },
    {
      selector: '[data-tour-docs="card-actions"]',
      title: 'What you can do with each doc',
      body: 'Per-card actions: Summarize (AI writes a summary), Extract (pull key facts), Mark outdated (excludes from future answers), or Delete. Click "Show summary" to expand and inspect the AI\'s take.',
      placement: 'top',
    },
  ],
};

export const QA_TOUR = {
  key: 'frontline_tour_qa_v1',
  label: 'Knowledge Q&A',
  steps: [
    {
      title: 'Knowledge Q&A 💬',
      body: "Ask any question about your documents, procedures, or policies. The AI grounds every answer in your indexed content and shows the source it used — so you can trust and verify.",
      placement: 'center',
    },
    {
      selector: '[data-tour-qa="sidebar"]',
      title: 'Your chat history',
      body: 'Every conversation is saved here. Click any past chat to reopen it — the AI remembers the context so you can pick up where you left off.',
      placement: 'right',
    },
    {
      selector: '[data-tour-qa="new-chat"]',
      title: 'Start a fresh conversation',
      body: 'Click "+" to begin a new chat. Use this when you switch topics — a clean slate helps the AI focus on the new question.',
      placement: 'bottom',
    },
    {
      selector: '[data-tour-qa="scope"]',
      title: 'Choose what the AI searches',
      body: 'Narrow the AI\'s knowledge scope: search across all documents, only a specific document type (e.g. policies), or a hand-picked set. Narrower scope = more precise answers.',
      placement: 'top',
    },
    {
      selector: '[data-tour-qa="input"]',
      title: 'Ask your question',
      body: "Type a natural-language question here — 'What's our refund policy for enterprise plans?', 'Which SOP covers onboarding?', anything. Hit Enter or click Send to get an answer.",
      placement: 'top',
    },
    {
      selector: '[data-tour-qa="messages"]',
      title: 'Answers with citations',
      body: 'The AI\'s reply lands here, followed by the exact document(s) it cited. Thumbs-up / thumbs-down helps the system learn what a good answer looks like for your team.',
      placement: 'left',
    },
  ],
};

export const WIDGET_TOUR = {
  key: 'frontline_tour_widget_v1',
  label: 'Chat widget',
  steps: [
    {
      title: 'Chat widget 🖥️',
      body: "Configure and deploy the customer-facing chat widget — the pop-up chat that your end users see on your website.",
      placement: 'center',
    },
    {
      selector: '[data-tour-widget="key"]',
      title: 'Your widget key',
      body: 'This unique key ties the widget to your account. Copy it — you\'ll paste it into the embed snippet on your website. Never share this key publicly.',
      placement: 'bottom',
    },
    {
      selector: '[data-tour-widget="origins"]',
      title: 'Allowed origins',
      body: "A comma-separated list of domains where the widget is allowed to run (e.g. https://yoursite.com). Requests from anywhere else are blocked — this is your security perimeter.",
      placement: 'top',
    },
    {
      selector: '[data-tour-widget="theme"]',
      title: 'Match your brand',
      body: 'Tweak colors, fonts, border radius, header background, and bubble style so the widget blends into your site. Advanced users can inject custom CSS.',
      placement: 'top',
    },
    {
      selector: '[data-tour-widget="embed"]',
      title: 'The embed snippet',
      body: 'Copy this <script> tag and paste it into your website\'s HTML (just before </body>). That\'s literally all the installation needed.',
      placement: 'top',
    },
  ],
};

export const TICKETS_TOUR = {
  key: 'frontline_tour_tickets_v1',
  label: 'Tickets',
  steps: [
    {
      title: 'Tickets 🎫',
      body: "Every support request the AI can\'t auto-resolve turns into a ticket. Here you triage, filter, and act on the whole queue.",
      placement: 'center',
    },
    {
      selector: '[data-tour-tickets="create"]',
      title: 'Create a ticket manually',
      body: 'Sometimes issues arrive by phone, email, or chat. Click here to log them by hand — status, priority, and category all in one dialog.',
      placement: 'bottom',
    },
    {
      selector: '[data-tour-tickets="filters"]',
      title: 'Slice the queue',
      body: 'Filter by status, priority, category, or date. Great for triaging your day: "show me all urgent open tickets from this week".',
      placement: 'bottom',
    },
    {
      selector: '[data-tour-tickets="table"]',
      title: 'The ticket table',
      body: 'Every column is meaningful: SLA countdown, auto-resolved flag, priority badge. Click a row to open the detail drawer with the full thread.',
      placement: 'top',
    },
    {
      selector: '[data-tour-tickets="bulk-hint"]',
      title: 'Bulk actions',
      body: 'Tick multiple rows using the checkboxes and a bulk-action bar appears. Change status, priority, or category on many tickets at once — huge time saver for triage days.',
      placement: 'top',
    },
  ],
};

export const HANDOFFS_TOUR = {
  key: 'frontline_tour_handoffs_v1',
  label: 'Hand-offs',
  steps: [
    {
      title: 'Hand-offs 🎧',
      body: "When the AI isn't confident enough to auto-resolve, it hands the ticket to a human. This tab is your queue of AI-to-human escalations.",
      placement: 'center',
    },
    {
      selector: '[data-tour-handoffs="filters"]',
      title: 'Filter your queue',
      body: 'Switch between Pending, Accepted, and All. Tick "Only mine" to see just the hand-offs assigned to you. Refresh pulls the latest.',
      placement: 'bottom',
    },
    {
      selector: '[data-tour-handoffs="queue"]',
      title: 'The queue',
      body: 'Every row is one hand-off: title, customer, reason for escalation, request time, and priority. Click "Open" to see the full context and reply.',
      placement: 'top',
    },
    {
      title: 'Inside the drawer 💡',
      body: 'When you open a hand-off you get: the full ticket thread, the AI\'s draft answer (with a "Suggest reply" button to regenerate), and buttons to Accept, Release back to the pool, or Reassign to a colleague.',
      placement: 'center',
    },
  ],
};

export const NOTIFICATIONS_TOUR = {
  key: 'frontline_tour_notifications_v1',
  label: 'Notifications',
  steps: [
    {
      title: 'Notifications 🔔',
      body: "Control what your team gets notified about, and build reusable templates for outbound notifications.",
      placement: 'center',
    },
    {
      selector: '[data-tour-notif="prefs"]',
      title: 'Your notification preferences',
      body: 'Master toggles for email and in-app notifications, plus per-event switches (ticket created, updated, assigned, workflow emails). Turn off what you don\'t want — silence is a feature.',
      placement: 'bottom',
    },
    {
      selector: '[data-tour-notif="template-create"]',
      title: 'Create a template',
      body: 'Save recurring message formats (welcome emails, SLA warnings, escalations) as templates. You can even enable AI personalization so each send is tailored to the recipient.',
      placement: 'bottom',
    },
    {
      selector: '[data-tour-notif="send-form"]',
      title: 'Send a one-off notification',
      body: 'Pick a template, add a recipient (and optionally link a ticket), hit Send Now. Great for ad-hoc updates outside of workflow automation.',
      placement: 'top',
    },
    {
      selector: '[data-tour-notif="lists"]',
      title: 'Templates & scheduled sends',
      body: 'Your saved templates live above; scheduled/queued sends live below. Edit or delete templates anytime — changes apply to future sends only.',
      placement: 'top',
    },
  ],
};

export const WORKFLOWS_TOUR = {
  key: 'frontline_tour_workflows_v1',
  label: 'Workflows',
  steps: [
    {
      title: 'Workflows ⚙️',
      body: "Automate repetitive multi-step processes: send email → update ticket → post to Slack → assign, all triggered by rules. No code needed.",
      placement: 'center',
    },
    {
      selector: '[data-tour-workflows="create"]',
      title: 'Build a workflow',
      body: 'Click here to open the workflow builder. Give it a name, add ordered steps (email, update ticket, webhook, Slack, assign), and set trigger conditions like category=billing + priority=urgent.',
      placement: 'bottom',
    },
    {
      selector: '[data-tour-workflows="execute-form"]',
      title: 'Run one manually',
      body: 'Sometimes you want to fire a workflow on a specific ticket right now. Pick the workflow, optionally attach a ticket or recipient, and hit Execute.',
      placement: 'bottom',
    },
    {
      selector: '[data-tour-workflows="list"]',
      title: 'Your workflows',
      body: 'All saved workflows live here. Toggle Active/Inactive, click Dry Run to preview execution without side effects, or Edit to change steps and triggers.',
      placement: 'top',
    },
    {
      selector: '[data-tour-workflows="executions"]',
      title: 'Recent executions',
      body: 'A running log of what fired, when, and whether it succeeded, failed, or is awaiting your approval. Approve or reject pending ones right from this list.',
      placement: 'left',
    },
  ],
};

export const ANALYTICS_TOUR = {
  key: 'frontline_tour_analytics_v1',
  label: 'Analytics',
  steps: [
    {
      title: 'Analytics 📊',
      body: "Deep performance data on your Frontline operation — trends, per-agent breakdown, resolution times, and natural-language querying.",
      placement: 'center',
    },
    {
      selector: '[data-tour-analytics="nlq"]',
      title: 'Ask a question in plain English',
      body: 'Type things like "how many tickets did we close last week?" or "which category has the worst SLA?" The AI queries your data and answers with a written summary plus charts.',
      placement: 'bottom',
    },
    {
      selector: '[data-tour-analytics="range"]',
      title: 'Date range + Export',
      body: 'Pick a from/to date, click Load, and the whole page recomputes for that window. Export CSV gives you the raw ticket-level data for offline analysis.',
      placement: 'bottom',
    },
    {
      selector: '[data-tour-analytics="kpis"]',
      title: 'Headline numbers',
      body: 'At-a-glance KPI cards: total tickets, auto-resolved count, average resolution hours, and more. These reflect the date range above.',
      placement: 'top',
    },
    {
      selector: '[data-tour-analytics="charts"]',
      title: 'Charts & team performance',
      body: 'Tickets over time, by status, by category — plus a per-agent table showing who resolved how many, SLA breach rate, and median resolution time. Click column headers to sort.',
      placement: 'top',
    },
  ],
};

export const AI_GRAPHS_TOUR = {
  key: 'frontline_tour_ai_graphs_v1',
  label: 'AI Graphs',
  steps: [
    {
      title: 'AI Graphs ✨',
      body: "Describe a chart in plain English — the AI generates it. Great for exploring your data without building queries or picking chart types manually.",
      placement: 'center',
    },
    {
      selector: '[data-tour-aigraphs="prompt"]',
      title: 'Describe your chart',
      body: 'Type something like "show tickets by status as a pie chart" or "resolution time trend for the last quarter". The AI picks the chart type and generates it.',
      placement: 'bottom',
    },
    {
      selector: '[data-tour-aigraphs="examples"]',
      title: 'Or start from an example',
      body: 'Click any example prompt to try it instantly. Great for learning what kinds of questions the AI can chart.',
      placement: 'top',
    },
    {
      selector: '[data-tour-aigraphs="chart"]',
      title: 'Your generated chart',
      body: 'The AI renders the chart here, plus a written insight paragraph explaining what stands out in the data. Click Save to keep the chart for later.',
      placement: 'top',
    },
    {
      selector: '[data-tour-aigraphs="saved"]',
      title: 'Generate vs. Saved Prompts',
      body: 'Toggle between the two sections here. "Generate" is what you\'re seeing now; "Saved Prompts" is where the charts you\'ve saved live — search, favorite, or delete them from there.',
      placement: 'bottom',
    },
  ],
};

// Convenience map for quick lookup by tab value.
export const TAB_TOURS = {
  overview: OVERVIEW_TOUR,
  documents: DOCUMENTS_TOUR,
  qa: QA_TOUR,
  widget: WIDGET_TOUR,
  tickets: TICKETS_TOUR,
  handoffs: HANDOFFS_TOUR,
  notifications: NOTIFICATIONS_TOUR,
  workflows: WORKFLOWS_TOUR,
  analytics: ANALYTICS_TOUR,
  'ai-graphs': AI_GRAPHS_TOUR,
};
