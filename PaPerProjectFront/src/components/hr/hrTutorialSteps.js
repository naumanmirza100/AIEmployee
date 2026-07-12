// Tour step definitions + inline "!" hint content for the HR Support Agent
// dashboard. Mirrors the frontline structure but with HR-specific copy,
// storage keys (so tour progress in HR doesn't clobber Frontline), and
// slash-command hints for the HR floating chat.

// ---- Main "Take the Tour" tour ------------------------------------------

export const HR_MAIN_TOUR_STEPS = [
  {
    title: 'Welcome to HR Support Agent 👋',
    body: "This quick tour walks you through every tab and tool on this dashboard. You can skip anytime, or replay it later from the 'Take the Tour' button in the header.",
    placement: 'center',
  },
  {
    selector: '[data-tour-hr="stats"]',
    title: 'Your HR snapshot',
    body: 'Six live tiles: active employees, on leave, pending leave requests, upcoming meetings, indexed documents, and probation ending soon. Updates every time you land on the dashboard.',
    placement: 'bottom',
  },
  {
    selector: '[data-tour-hr="tabs"]',
    title: 'Everything lives in these tabs',
    body: "Each tab opens a different tool. We'll walk through them one by one.",
    placement: 'bottom',
  },
  { tab: 'overview',      selector: '[data-tour-hr-tab="overview"]',      title: 'Overview',       body: 'Your home base. Quick-launch tiles for the tools you use most: Q&A, Employees, Documents, Workflows, Meetings.', placement: 'bottom' },
  { tab: 'qa',            selector: '[data-tour-hr-tab="qa"]',            title: 'Knowledge Q&A',  body: 'Ask any HR question — leave policy, benefits, escalation SOPs, contracts. The AI answers grounded in your indexed HR documents.', placement: 'bottom' },
  { tab: 'employees',     selector: '[data-tour-hr-tab="employees"]',     title: 'Employees',      body: 'Browse and search everyone in the company. Filter by department, run review cycles, and manage the org structure.', placement: 'bottom' },
  { tab: 'my_team',       selector: '[data-tour-hr-tab="my_team"]',       title: 'My team',        body: "Manager view: your direct reports, their performance summaries, and quick actions on each report.", placement: 'bottom' },
  { tab: 'org_chart',     selector: '[data-tour-hr-tab="org_chart"]',     title: 'Org chart',      body: 'Interactive visualization of the reporting structure — who reports to whom, at a glance.', placement: 'bottom' },
  { tab: 'documents',     selector: '[data-tour-hr-tab="documents"]',     title: 'Documents',      body: 'Upload handbooks, policies, contracts. Once indexed, the AI can answer questions from their content.', placement: 'bottom' },
  { tab: 'workflows',     selector: '[data-tour-hr-tab="workflows"]',     title: 'Workflows',      body: 'Automate onboarding, offboarding, leave approvals, and more. Build once, run every time you need them.', placement: 'bottom' },
  { tab: 'meetings',      selector: '[data-tour-hr-tab="meetings"]',      title: 'Meetings',       body: "Schedule 1:1s and reviews in plain English. Export the invite as an .ics file and drop it in the participants' calendars.", placement: 'bottom' },
  { tab: 'leave',         selector: '[data-tour-hr-tab="leave"]',         title: 'Leave',          body: 'Review and approve pending leave requests, and see the calendar of who is out and when.', placement: 'bottom' },
  { tab: 'notifications', selector: '[data-tour-hr-tab="notifications"]', title: 'Notifications',  body: "HR event alerts — probation endings, leave conflicts, missed check-ins. You'll never miss a follow-up.", placement: 'bottom' },
  {
    selector: '[data-tour-hr="replay"]',
    title: 'Need the tour again?',
    body: "Click 'Take the Tour' here anytime to replay this walkthrough. That's it — you're all set! 🎉",
    placement: 'bottom',
  },
];

// ---- Per-tab tours ------------------------------------------------------

export const HR_OVERVIEW_TOUR = {
  key: 'hr_tour_overview_v1',
  label: 'Overview',
  steps: [
    { title: 'Overview tab 🏠', body: 'The fastest way to open the tool you need. Six quick-launch tiles that jump straight to the tabs you use most.', placement: 'center' },
    { selector: '[data-tour-hr-ov="quicknav"]', title: 'Quick jump to any tool', body: 'Click any tile to switch tabs instantly — Knowledge Q&A, Employees, Documents, Workflows, or Meetings.', placement: 'top' },
  ],
};

export const HR_QA_TOUR = {
  key: 'hr_tour_qa_v1',
  label: 'Knowledge Q&A',
  steps: [
    { title: 'Knowledge Q&A 💬', body: 'Ask any HR question — leave policy, benefits, contracts, escalation paths. The AI answers grounded in your indexed HR documents and shows the sources it used.', placement: 'center' },
    { selector: '[data-tour-hr-qa="panel"]', title: 'Chat panel', body: 'History sidebar on the left, conversation in the middle, input at the bottom. Everything you say is saved so you can pick up where you left off.', placement: 'left' },
  ],
};

export const HR_EMPLOYEES_TOUR = {
  key: 'hr_tour_employees_v1',
  label: 'Employees',
  steps: [
    { title: 'Employees 👥', body: 'One place to find, filter, and act on everyone in the company. Search by name, narrow by department, kick off review cycles.', placement: 'center' },
    { selector: '[data-tour-hr-emp="filter"]',        title: 'Department filter',    body: 'Narrow the list to a specific department. Great for scoping actions like sending a policy update to just Engineering.', placement: 'bottom' },
    { selector: '[data-tour-hr-emp="manage-depts"]',  title: 'Manage departments',   body: 'Add, rename, or delete departments here. Changes reflect everywhere departments are used across the app.', placement: 'bottom' },
    { selector: '[data-tour-hr-emp="review-cycles"]', title: 'Review cycles',        body: 'Kick off performance review cycles — pick employees, set a timeline, and the workflow handles the reminders.', placement: 'bottom' },
    { selector: '[data-tour-hr-emp="search"]',        title: 'Search',               body: 'Search by name, email, or title. Combines with the department filter, so you can find "all engineers named Sam".', placement: 'bottom' },
    { selector: '[data-tour-hr-emp="table"]',         title: 'Employee list',        body: 'Every row: name, email, title, department, status. Click a row to open the detail drawer with full profile + edit + remove.', placement: 'top' },
  ],
};

export const HR_MY_TEAM_TOUR = {
  key: 'hr_tour_my_team_v1',
  label: 'My team',
  steps: [
    { title: 'My team 👥', body: "Manager view: everyone who reports to you, with performance summaries and quick actions right on each row.", placement: 'center' },
    { selector: '[data-tour-hr-team="list"]', title: 'Your direct reports', body: "Each row is one direct report. Click to open their profile drawer for 1:1 notes, review history, and edit access.", placement: 'top' },
  ],
};

export const HR_ORG_CHART_TOUR = {
  key: 'hr_tour_org_chart_v1',
  label: 'Org chart',
  steps: [
    { title: 'Org chart 🧭', body: "Visualize the reporting structure. Zoom, pan, and click any node to jump straight to that employee's profile.", placement: 'center' },
    { selector: '[data-tour-hr-org="canvas"]', title: 'The org tree', body: 'Interactive canvas — drag to pan, scroll to zoom. Nodes are colored by department. Great for finding gaps in the structure.', placement: 'top' },
  ],
};

export const HR_DOCUMENTS_TOUR = {
  key: 'hr_tour_documents_v1',
  label: 'Documents',
  steps: [
    { title: 'Documents 📄', body: "Your HR knowledge library. Upload handbooks, policies, contracts. Once indexed, the AI can reference them in every answer.", placement: 'center' },
    { selector: '[data-tour-hr-docs="upload"]',       title: 'Upload document',       body: 'Add a PDF, Word doc, or text file. Confidentiality tag lets you restrict who can query it (e.g. contracts).', placement: 'bottom' },
    { selector: '[data-tour-hr-docs="grid"]',         title: 'Your document library', body: 'Each card shows format, status (Indexed / Processing / Failed), version, and confidentiality. Failed uploads can be retried.', placement: 'top' },
    { selector: '[data-tour-hr-docs="card-actions"]', title: 'Per-doc actions',       body: 'Summarize (AI writes a summary), Extract (pull key facts), Mark outdated (excludes from answers), View versions, or Delete.', placement: 'top' },
  ],
};

export const HR_WORKFLOWS_TOUR = {
  key: 'hr_tour_workflows_v1',
  label: 'Workflows',
  steps: [
    { title: 'Workflows ⚙️', body: "Automate onboarding, offboarding, leave approvals, and any repeatable HR process. Build once, run every time.", placement: 'center' },
    { selector: '[data-tour-hr-wf="template"]', title: 'Start from a template', body: 'Pre-built templates for common HR processes — onboarding, offboarding, probation review. Fastest way to get productive.', placement: 'bottom' },
    { selector: '[data-tour-hr-wf="create"]',   title: 'New workflow',          body: 'Build a custom workflow from scratch. Add ordered steps (email, update status, assign a task, wait for approval) and set the trigger.', placement: 'bottom' },
    { selector: '[data-tour-hr-wf="list"]',     title: 'Your workflows',        body: 'Every saved workflow with status badge and trigger event. Row actions: Run, Edit, View history, or Delete.', placement: 'top' },
  ],
};

export const HR_MEETINGS_TOUR = {
  key: 'hr_tour_meetings_v1',
  label: 'Meetings',
  steps: [
    { title: 'Meetings 📅', body: "Schedule HR meetings in plain English. Say 'schedule a review with Ana next Thursday at 3pm' and the AI books it, invites participants, and generates an .ics file.", placement: 'center' },
    { selector: '[data-tour-hr-meet="chat"]',   title: 'Chat scheduler',        body: 'Describe the meeting in plain English. Include names, dates, times, agenda — the more detail, the better the invite.', placement: 'right' },
    { selector: '[data-tour-hr-meet="list"]',   title: 'Scheduled meetings',    body: 'Every meeting you and your team have scheduled through the agent. Click any row to see the full details and participants.', placement: 'left' },
    { selector: '[data-tour-hr-meet="export"]', title: 'Export as .ics',        body: 'One click to download the calendar invite. Drop it into any calendar app — Google, Outlook, Apple — and the event lands correctly.', placement: 'top' },
  ],
};

export const HR_LEAVE_TOUR = {
  key: 'hr_tour_leave_v1',
  label: 'Leave',
  steps: [
    { title: 'Leave 🏖️', body: "Everything about time off — requests, approvals, and the team calendar of who is out and when.", placement: 'center' },
    { selector: '[data-tour-hr-leave="list"]', title: 'Leave requests',    body: "Pending, approved, and rejected requests all in one list. Approve or reject inline; the requester is notified automatically.", placement: 'top' },
    { selector: '[data-tour-hr-leave="new"]',  title: 'New request',       body: "File a request on behalf of an employee — pick dates, type, and reason. Great for retro entries or when someone can't log in.", placement: 'bottom' },
  ],
};

export const HR_NOTIFICATIONS_TOUR = {
  key: 'hr_tour_notifications_v1',
  label: 'Notifications',
  steps: [
    { title: 'Notifications 🔔', body: "HR-specific alerts: probation endings, leave conflicts, review cycle deadlines, missed check-ins. Nothing slips through.", placement: 'center' },
    { selector: '[data-tour-hr-notif="list"]', title: 'Event log', body: 'Every HR event as it happens. Click any row for full context and a jump link back to the source (employee, workflow, meeting).', placement: 'top' },
  ],
};

// ---- Floating "Quick Chat" tour + hints -----------------------------------

export const HR_FLOATING_CHAT_TOUR = {
  key: 'hr_tour_floating_chat_v1',
  label: 'Quick Chat',
  steps: [
    { title: 'Meet HR Quick Chat ✨',                  body: "The fastest way to answer any HR question. Ask about policies, look up a benefit, check a leave balance — grounded in your indexed HR documents.", placement: 'center' },
    { selector: '[data-tour-hrfc="input"]',    title: 'Ask any HR question',       body: "Natural language works. Try 'What's our maternity leave policy?', 'How many PTO days do I have left?', or type / for slash commands.", placement: 'top' },
    { selector: '[data-tour-hrfc="send"]',     title: 'Send',                       body: 'Click or press Enter. The AI searches your HR knowledge base and returns an answer with the sources it cited.', placement: 'top' },
    { selector: '[data-tour-hrfc="messages"]', title: 'Answers with citations',    body: 'Every AI response shows the source document(s) it referenced, so you can verify. Errors show as a red bubble.', placement: 'top' },
    { selector: '[data-tour-hrfc="header"]',   title: 'Header actions',            body: 'History icon for past conversations, + for a new chat, graduation cap to replay this tour, X to close. Ctrl+K reopens Quick Chat from anywhere.', placement: 'bottom' },
  ],
};

// ---- Inline "!" hint content --------------------------------------------

export const HR_HINTS = {
  // Overview
  hrOvQuicknav: { title: 'Quick jump to any tool', body: 'Six shortcut tiles that jump straight to the tabs you use most. Click any tile to switch tabs instantly.' },

  // Q&A
  hrQaPanel: { title: 'Knowledge Q&A panel', body: 'Chat history on the left, conversation in the middle, input at the bottom. Everything is saved so you can pick up where you left off.' },

  // Employees
  hrEmpFilter:       { title: 'Department filter',   body: 'Narrow the list to a specific department. Combines with search — great for scoping actions like sending a policy update to just Engineering.' },
  hrEmpManageDepts:  { title: 'Manage departments',  body: 'Add, rename, or delete departments. Changes reflect everywhere departments are used across the app.' },
  hrEmpReviewCycles: { title: 'Review cycles',       body: 'Kick off performance review cycles — pick employees, set a timeline, and the workflow handles the reminders.' },
  hrEmpSearch:       { title: 'Search',              body: 'Search by name, email, or title. Combines with the department filter above.' },
  hrEmpTable:        { title: 'Employee list',       body: 'Every row: name, email, title, department, status. Click any row to open the detail drawer with full profile, edit, and remove.' },

  // My team / Org chart
  hrTeamList: { title: 'Your direct reports', body: 'Everyone who reports to you. Click a row to open their profile for 1:1 notes, review history, and edit access.' },
  hrOrgCanvas: { title: 'The org tree', body: 'Interactive canvas — drag to pan, scroll to zoom. Nodes are colored by department.' },

  // Documents
  hrDocsUpload:      { title: 'Upload document',    body: 'Add PDFs, Word docs, or text files. Set confidentiality to restrict who can query it (e.g. contracts).' },
  hrDocsGrid:        { title: 'Document library',   body: 'Cards show format, status (Indexed / Processing / Failed), version, and confidentiality. Failed uploads can be retried.' },
  hrDocsCardActions: { title: 'Per-doc actions',    body: 'Summarize, Extract, Mark outdated, View versions, or Delete.' },

  // Workflows
  hrWfTemplate: { title: 'From template', body: 'Pre-built templates for common HR processes — onboarding, offboarding, probation review. Fastest way to get productive.' },
  hrWfCreate:   { title: 'New workflow',  body: 'Build a custom workflow. Add ordered steps (email, update status, assign a task, wait for approval) and set the trigger event.' },
  hrWfList:     { title: 'Workflows list', body: 'Every saved workflow with status badge and trigger event. Row actions: Run, Edit, View history, or Delete.' },

  // Meetings
  hrMeetChat:   { title: 'Chat scheduler',     body: "Describe the meeting in plain English. Include names, dates, times, agenda — the more detail, the better the invite." },
  hrMeetList:   { title: 'Scheduled meetings', body: 'Every meeting scheduled through the agent. Click any row to see full details and participants.' },
  hrMeetExport: { title: 'Export as .ics',     body: 'One-click .ics download. Drop it into Google, Outlook, or Apple Calendar and the event lands correctly.' },

  // Leave
  hrLeaveList: { title: 'Leave requests', body: 'Pending, approved, and rejected requests all in one list. Approve or reject inline; the requester is notified automatically.' },
  hrLeaveNew:  { title: 'New request',    body: 'File a request on behalf of an employee — pick dates, type, and reason. Great for retro entries.' },

  // Notifications
  hrNotifList: { title: 'HR event log', body: 'Every HR event as it happens. Click a row for full context and a jump link back to the source (employee, workflow, meeting).' },

  // Floating Quick Chat
  hrFcLauncher: { title: 'HR Quick Chat launcher', body: 'One-click AI assistant for HR questions. Grounded in your HR document library. Press Ctrl+K anywhere.' },
  hrFcInput:    { title: 'Ask any HR question',    body: "Type in plain English. Examples: 'What's our parental leave policy?', 'How do I file an expense?'. Enter = send, Shift+Enter = new line. Try / for commands." },
  hrFcSend:     { title: 'Send',                    body: 'Submit your question. The AI searches your HR knowledge base and answers with citations.' },
  hrFcMessages: { title: 'Chat area',               body: 'Your conversation lives here. Each AI answer includes the sources it cited. Errors show as a red bubble.' },
  hrFcHeader:   { title: 'Header actions',          body: 'Graduation cap replays this tour. History icon shows past conversations. X closes the chat.' },
};

// ---- Convenience map ----------------------------------------------------

export const HR_TAB_TOURS = {
  overview:      HR_OVERVIEW_TOUR,
  qa:            HR_QA_TOUR,
  employees:     HR_EMPLOYEES_TOUR,
  my_team:       HR_MY_TEAM_TOUR,
  org_chart:     HR_ORG_CHART_TOUR,
  documents:     HR_DOCUMENTS_TOUR,
  workflows:     HR_WORKFLOWS_TOUR,
  meetings:      HR_MEETINGS_TOUR,
  leave:         HR_LEAVE_TOUR,
  notifications: HR_NOTIFICATIONS_TOUR,
};

// Main-tour storage key (used by the "Take the Tour" auto-launch).
export const HR_MAIN_TOUR_KEY = 'hr_tutorial_seen_v1';
