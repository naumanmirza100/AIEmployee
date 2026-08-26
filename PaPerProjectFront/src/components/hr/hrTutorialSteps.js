// Tour step definitions + inline "!" hint content for the HR Support Agent
// dashboard. Mirrors the frontline structure but with HR-specific copy,
// storage keys (so tour progress in HR doesn't clobber Frontline), and
// slash-command hints for the HR floating chat.

// ---- Main "Take the Tour" tour ------------------------------------------

// Rewritten for the post-restructure tab shape (5 visible tabs). Uses the
// global AgentSidebar as the primary navigation. Employees / My team /
// Org chart / Documents / Q&A / Workflows / Leave / Notifications are all
// still reachable, but as sub-items of the consolidated People / Knowledge /
// Operations parent tabs.
export const HR_MAIN_TOUR_STEPS = [
  {
    title: 'Welcome to HR Support Agent 👋',
    body: "Quick tour of the 5 tabs on this dashboard. You can skip anytime, or replay it later from 'Take the Tour' in the header.",
    placement: 'center',
  },
  {
    selector: '[data-tour-hr="stats"]',
    title: 'Your HR snapshot',
    body: 'Live tiles: active employees, on leave, pending leave requests, upcoming meetings, indexed documents, and probation ending soon. Updates every time you land on the dashboard.',
    placement: 'bottom',
  },
  {
    selector: '[data-tour-hr="tabs"]',
    title: 'Navigation lives in the left sidebar',
    body: "Every tab you'll see below is reachable from the global sidebar on the left. Parent tabs (People / Knowledge / Operations) expand to show sub-items when you're on them.",
    placement: 'right',
  },
  { tab: 'overview', title: 'Overview',
    body: 'Home base: stats + quick-launch tiles for the tabs you use most. Come back here when you want a snapshot of what needs attention.',
    placement: 'center' },
  { tab: 'people', title: 'People',
    body: 'Everything on top of the employee record: the directory (Employees), your direct reports (My team), and the reporting structure (Org chart). Departments and Review Cycles admin lives here too — accessible from the Employees header.',
    placement: 'center' },
  { tab: 'knowledge', title: 'Knowledge',
    body: 'Feed the HR knowledge base (Documents) and ask questions of it (Knowledge Q&A). Documents feed the KB, Q&A answers from them. Ctrl+K opens the floating chat for quick asks from anywhere.',
    placement: 'center' },
  { tab: 'operations', title: 'Operations',
    body: 'The process-y HR features: Workflows (onboarding / offboarding / approvals), Leave (approve or submit requests), Notifications (templates + scheduled sends).',
    placement: 'center' },
  { tab: 'meetings', title: 'Meetings',
    body: "Schedule 1:1s and reviews in plain English. Export the invite as an .ics file and drop it in the participants' calendars.",
    placement: 'center' },
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
    { selector: '[data-tour-hrqa="sidebar"]',             title: 'Chat history sidebar',   body: 'Every conversation you have is saved on the left. Click any past chat to reopen it — the AI remembers the context so you can pick up where you left off.', placement: 'right' },
    { selector: '[data-tour-hrqa="search"]',              title: 'Search past chats',      body: "Click the magnifier to filter conversations by title. Fast way to jump back to that 'onboarding checklist' chat from last week.", placement: 'right' },
    { selector: '[data-tour-hrqa="new-chat"]',            title: 'Start a new chat',       body: 'The + button opens a fresh conversation. Use it when switching topics — a clean slate helps the AI focus on the new question.', placement: 'right' },
    { selector: '[data-tour-hrqa="sidebar-toggle-close"]', title: 'Collapse the sidebar',  body: 'Hide the sidebar to give the conversation more room. Bring it back with the chevron in the panel header.', placement: 'right' },
    { selector: '[data-tour-hrqa="messages"]',            title: 'Answers with citations', body: 'AI replies land here. Each response includes the source document(s) it cited, plus a warning banner when the answer is not grounded in verified data.', placement: 'left' },
    { selector: '[data-tour-hrqa="header-new-chat"]',     title: 'New chat, again',        body: 'Same as the sidebar + button — starts a fresh conversation. Handy shortcut when the sidebar is collapsed.', placement: 'bottom' },
    { selector: '[data-tour-hrqa="input"]',               title: 'Ask your question',      body: "Type a natural-language question — 'How many vacation days do I have?', 'What is our parental leave policy?', anything. Enter to send, Shift+Enter for a new line.", placement: 'top' },
    { selector: '[data-tour-hrqa="send"]',                title: 'Send',                   body: 'Submit your question. The AI searches your HR knowledge base and answers with citations you can verify.', placement: 'top' },
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
    { title: 'Meetings 📅', body: "Schedule HR meetings in plain English. Say 'schedule a review with Ana next Thursday at 3pm' and the AI books it, invites participants, and gives you an .ics you can drop into any calendar.", placement: 'center' },
    { selector: '[data-tour-hrmeet="sidebar"]',        title: 'Scheduling conversations', body: 'Every scheduling conversation is saved on the left. Click any past chat to reopen it — great for reviewing exactly what was booked and when.', placement: 'right' },
    { selector: '[data-tour-hrmeet="new-chat"]',       title: 'Start a new chat',         body: 'Open a fresh scheduling conversation. Use this when the meeting has nothing to do with the previous topic.', placement: 'right' },
    { selector: '[data-tour-hrmeet="tabs"]',           title: 'Chat vs. Meetings tabs',    body: "'Chat' is where you tell the AI what to schedule. 'Meetings' is the actual list of everything that\'s been booked. Switch between them here.", placement: 'bottom' },
    { selector: '[data-tour-hrmeet="chat-samples"]',   title: 'Try one of these',         body: "Sample prompts show what the scheduler understands. Click one to load it as your prompt — great for learning the phrasing that works best.", placement: 'bottom' },
    { selector: '[data-tour-hrmeet="chat-input"]',     title: 'Describe the meeting',     body: "Type in plain English. Include names, date/time, duration, and agenda — the more detail, the better the invite. Enter to send, Shift+Enter for a new line.", placement: 'top' },
    { selector: '[data-tour-hrmeet="chat-send"]',      title: 'Send',                     body: 'Submit your request. The AI parses it, finds the attendees, and either books the meeting or asks for missing info (like exact time).', placement: 'top' },
    // Post-restructure: the internal Chat/Meetings sub-tab bar was removed
    // (users navigate via the global sidebar now). Removed the onEnter DOM
    // clicks that used to switch to the Meetings sub-tab — they'd fail
    // silently now. The stats / refresh / per-meeting-actions steps stay
    // because their targets are still present when the Meetings list is
    // rendered inline (which it is by default).
    { selector: '[data-tour-hrmeet="stats"]',          title: 'Meetings snapshot',        body: 'Four counts at a glance: total, upcoming, completed, cancelled. Reflects everything the agent has scheduled for you and your team.', placement: 'bottom' },
    { selector: '[data-tour-hrmeet="refresh"]',        title: 'Refresh',                  body: 'Reload the meetings list from the backend. Handy if a colleague just scheduled something and you want to see it appear.', placement: 'left' },
    { selector: '[data-tour-hrmeet="meeting-actions"]', title: 'Per-meeting actions',     body: 'Every meeting has four quick actions: Export .ics (download the invite), Edit (change title/time/attendees), Extract action items (AI pulls tasks from the transcript), and Cancel.', placement: 'top' },
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
  hrOvQuicknav: { title: 'Quick jump to any tab', body: 'Shortcut tiles for the tabs you use most. The sidebar on the left has the full navigation including sub-items (Employees, Documents, Workflows, etc.).' },

  // Q&A
  hrQaPanel:              { title: 'Knowledge Q&A panel', body: 'Chat history on the left, conversation in the middle, input at the bottom. Everything is saved so you can pick up where you left off.' },
  hrQaSidebar:            { title: 'Chat history',        body: 'Every past conversation, saved. Click any entry to reopen it — the AI keeps the full context.' },
  hrQaSearch:             { title: 'Search chats',        body: 'Filter your conversations by title. Fast way to jump back to a specific topic.' },
  hrQaNewChat:            { title: 'Start a new chat',    body: 'Open a fresh conversation. Use this when switching topics — a clean slate helps the AI focus.' },
  hrQaSidebarToggleClose: { title: 'Collapse sidebar',    body: 'Hide the sidebar to give the conversation more room. Bring it back with the chevron in the panel header.' },
  hrQaMessages:           { title: 'Answers with citations', body: 'Each AI reply shows the sources it cited. A warning banner appears when the answer is not grounded in verified data.' },
  hrQaHeaderNewChat:      { title: 'New chat',            body: 'Same as the sidebar + button. Handy shortcut when the sidebar is collapsed.' },
  hrQaInput:              { title: 'Ask a question',      body: "Type your HR question in natural language. Enter to send, Shift+Enter for a new line." },
  hrQaSend:               { title: 'Send',                body: 'Submit your question. The AI searches your HR knowledge base and answers with citations.' },

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
  hrMeetChat:           { title: 'Chat scheduler',              body: "Describe the meeting in plain English. Include names, dates, times, agenda — the more detail, the better the invite." },
  hrMeetList:           { title: 'Scheduled meetings',          body: 'Every meeting scheduled through the agent. Click any row to see full details and participants.' },
  hrMeetExport:         { title: 'Export as .ics',              body: 'One-click .ics download. Drop it into Google, Outlook, or Apple Calendar and the event lands correctly.' },
  hrMeetSidebar:        { title: 'Scheduling conversations',    body: 'Your saved scheduling chats. Reopen any one to see exactly what was booked and when.' },
  hrMeetNewChat:        { title: 'Start a new chat',            body: "Open a fresh scheduling conversation — use when the meeting has nothing to do with the previous topic." },
  hrMeetTabs:           { title: 'Chat vs. Meetings',           body: "'Chat' is where you tell the AI what to schedule. 'Meetings' is the actual list of everything booked." },
  hrMeetChatSamples:    { title: 'Sample prompts',              body: "Example phrasings the scheduler understands. Click one to load it as your prompt." },
  hrMeetChatInput:      { title: 'Describe the meeting',        body: "Type in plain English. Include names, date/time, duration, and agenda. Enter to send, Shift+Enter for a new line." },
  hrMeetChatSend:       { title: 'Send',                        body: 'Submit your request. The AI books the meeting or asks for missing info (like exact time).' },
  hrMeetStats:          { title: 'Meetings snapshot',           body: 'Total, upcoming, completed, cancelled — at a glance.' },
  hrMeetRefresh:        { title: 'Refresh',                     body: 'Reload the meetings list from the backend. Handy if a colleague just scheduled something.' },
  hrMeetRowActions:     { title: 'Per-meeting actions',         body: 'Export .ics, Edit, Extract action items (AI pulls tasks from the transcript), or Cancel — right on each row.' },

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

// ---- Per-tab tours for the NEW consolidated tabs ------------------------
// Short, focused tours for the 3 new tabs added in the restructure. They
// live alongside the (untouched) legacy tab tours above — those still work
// if a user deep-links to a hidden tab like ?tab=documents.

export const HR_PEOPLE_TOUR = {
  key: 'hr_tour_people_v1',
  label: 'People',
  steps: [
    { title: 'People tab 👥', body: 'Everything that lives on top of the employee record — the directory (Employees), your direct reports (My team), the org chart, plus Departments + Review Cycles admin.', placement: 'center' },
    { title: 'Sub-items in the sidebar', body: 'Employees / My team / Org chart are indented under People in the left sidebar. Click any to jump straight to it.', placement: 'center' },
    { title: 'Departments & Review Cycles', body: 'Both are HR-admin objects reachable as buttons in the Employees header. Departments manage the org structure; Review Cycles run performance reviews with self / manager / released stages.', placement: 'center' },
  ],
};

export const HR_KNOWLEDGE_TOUR = {
  key: 'hr_tour_knowledge_v1',
  label: 'Knowledge',
  steps: [
    { title: 'Knowledge tab 💬', body: 'Feed the HR knowledge base (Documents) and ask questions of it (Knowledge Q&A). Documents feed the KB, Q&A answers from them.', placement: 'center' },
    { title: 'Documents vs. Q&A', body: 'Both are sub-items in the sidebar. Upload handbooks, policies, contracts to Documents; ask questions in Q&A — the AI cites which docs it used.', placement: 'center' },
    { title: 'Quick asks via Ctrl+K', body: 'The floating chat (bottom-right, Ctrl+K from anywhere) is a lighter Q&A surface. Same underlying agent — use it when you don\'t need chat history.', placement: 'center' },
  ],
};

export const HR_OPERATIONS_TOUR = {
  key: 'hr_tour_operations_v1',
  label: 'Operations',
  steps: [
    { title: 'Operations tab ⚙️', body: 'The process-y HR features: Workflows (SOP automation), Leave (approve/reject/submit), Notifications (templates + scheduled sends).', placement: 'center' },
    { title: 'Sub-items in the sidebar', body: 'Workflows / Leave / Notifications each get their own sub-item in the sidebar under Operations. Click any to jump in.', placement: 'center' },
    { title: 'Workflow templates', body: 'Onboarding / offboarding / approval flows have ready-made templates. Click "From template" in Workflows for a low-friction start instead of raw JSON.', placement: 'center' },
  ],
};

// ---- Convenience map ----------------------------------------------------
// Only include tours for VISIBLE tabs so the per-tab launcher UI doesn't
// offer tours for tabs the user can't reach through normal navigation.
// The hidden-tab tour constants above (HR_EMPLOYEES_TOUR, HR_DOCUMENTS_TOUR,
// etc.) are still exported so URL deep-links can still launch them.

export const HR_TAB_TOURS = {
  // Visible top-level tabs — reached from the sidebar directly.
  overview:   HR_OVERVIEW_TOUR,
  people:     HR_PEOPLE_TOUR,
  knowledge:  HR_KNOWLEDGE_TOUR,
  operations: HR_OPERATIONS_TOUR,
  meetings:   HR_MEETINGS_TOUR,
  // Hidden legacy tabs — reached via click-through from the visible tabs'
  // placeholder cards. Each still renders a "Tour this tab" button in its
  // TabsContent header; without these mappings the buttons were a silent
  // no-op (HR_TAB_TOURS[tabKey] → undefined → handler returns early).
  qa:            HR_QA_TOUR,
  employees:     HR_EMPLOYEES_TOUR,
  my_team:       HR_MY_TEAM_TOUR,
  org_chart:     HR_ORG_CHART_TOUR,
  documents:     HR_DOCUMENTS_TOUR,
  workflows:     HR_WORKFLOWS_TOUR,
  leave:         HR_LEAVE_TOUR,
  notifications: HR_NOTIFICATIONS_TOUR,
};

// Main-tour storage key (used by the "Take the Tour" auto-launch).
export const HR_MAIN_TOUR_KEY = 'hr_tutorial_seen_v1';
