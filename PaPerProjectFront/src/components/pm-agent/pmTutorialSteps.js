// Tour step definitions + inline "!" hint content for the Project Manager
// Agent dashboard. Mirrors the HR / Frontline structure but with PM-specific
// copy, storage keys (so tour progress doesn't clobber the other dashboards),
// and dual-mode chat hints for the PM floating chat.

// ---- Main "Take the Tour" tour ------------------------------------------

// Rewritten for the post-restructure tab shape (5 visible tabs). Uses the
// global AgentSidebar selector [data-tour-pm="tabs"] since the horizontal
// desktop tab bar has been removed. Steps that previously targeted hidden
// legacy tabs (create-project, create-task, task-prioritization,
// knowledge-qa, timeline-gantt, meeting-scheduler, ai-tools) are gone —
// those features now live inside their consolidated parent tab.
export const PM_MAIN_TOUR_STEPS = [
  {
    title: 'Welcome to Project Pilot 👋',
    body: "Quick tour of the 5 tabs on this dashboard. You can skip anytime, or replay it later from 'Take the Tour' in the header.",
    placement: 'center',
  },
  {
    selector: '[data-tour-pm="stats"]',
    title: 'Your project snapshot',
    body: 'Four stat cards give you an at-a-glance view: total projects, active, planning, and completed. Updates whenever project statuses change.',
    placement: 'bottom',
  },
  {
    selector: '[data-tour-pm="tabs"]',
    title: 'Navigation lives in the left sidebar',
    body: "Every tab you'll see below is reachable from the global sidebar on the left. Sub-items expand under their parent when active. Ctrl+K opens the Quick Chat from anywhere.",
    placement: 'right',
  },
  { tab: 'project-pilot', title: 'Ask (Pilot)',
    body: "The chat-based hero. Project Pilot creates and manages projects/tasks in plain English (\"add a design task to marketing\"), Knowledge Q&A answers questions about your project data, Meeting Scheduler books meetings via chat. All three share this tab.",
    placement: 'center' },
  { tab: 'projects', title: 'Projects',
    body: 'Searchable list of every project. Click a card to expand its details and recent tasks. "New Project" button opens the manual create form in a dialog.',
    placement: 'center' },
  { tab: 'tasks', title: 'Tasks',
    body: 'A task list with filters + Prioritize + Timeline/Gantt views. Prioritize ranks work + finds bottlenecks; Timeline builds schedules and Gantt charts. Old Prioritize / Timeline top-level tabs are folded here as sidebar sub-items.',
    placement: 'center' },
  { tab: 'insights', title: 'Insights',
    body: 'The report-y tools: Project Health, Daily Standup, Team Performance. Previously buried inside AI Tools — now surfaced here as sub-tabs of Insights.',
    placement: 'center' },
  { tab: 'overview', title: 'Overview',
    body: 'Stats grid + shortcut cards to every tab. Comes in handy once you have a few projects — feels a bit sparse when starting fresh, in which case Ask (Pilot) is the better entry point.',
    placement: 'center' },
  {
    selector: '[data-tour-pm="replay"]',
    title: 'Need the tour again?',
    body: "Click 'Take the Tour' here anytime to replay this walkthrough. Ctrl+K opens the Quick Chat from anywhere. That's it — you're set! 🎉",
    placement: 'bottom',
  },
];

// ---- Per-tab tours ------------------------------------------------------

export const PM_OVERVIEW_TOUR = {
  key: 'pm_tour_overview_v1',
  label: 'Overview',
  steps: [
    { title: 'Overview tab 🏠', body: 'Quick-launch cards to the tools you use most. Click any card to jump straight to that agent — no tab hunting required.', placement: 'center' },
    { selector: '[data-tour-pm-ov="quicknav"]', title: 'Quick jump to any agent', body: 'Five shortcut cards: Project Pilot, Task Prioritization, Knowledge Q&A, Timeline & Gantt, AI Tools. Click a card to switch tabs.', placement: 'top' },
  ],
};

export const PM_CREATE_PROJECT_TOUR = {
  key: 'pm_tour_create_project_v1',
  label: 'Create Project',
  steps: [
    { title: 'Create Project ➕', body: 'Manual project creation form. Perfect for when you know exactly what you want and don\'t need the AI to generate it for you.', placement: 'center' },
    { selector: '[data-tour-pm-cp="name"]',     title: 'Project name',   body: 'Give the project a clear, short name. This is what shows up in every list and chart later.', placement: 'right' },
    { selector: '[data-tour-pm-cp="desc"]',     title: 'Description',    body: 'What is this project about? A one-paragraph summary here helps the AI answer questions about the project later.', placement: 'right' },
    { selector: '[data-tour-pm-cp="status"]',   title: 'Status',         body: 'Planning, Active, On Hold, or Completed. New projects usually start as Planning.', placement: 'right' },
    { selector: '[data-tour-pm-cp="priority"]', title: 'Priority',       body: 'Low, Medium, High, or Critical. Drives how the AI prioritizes tasks inside this project.', placement: 'right' },
    { selector: '[data-tour-pm-cp="budget"]',   title: 'Budget range',   body: 'Min and max budget (optional). Used by cost tracking and the workflow-suggestions agent.', placement: 'right' },
    { selector: '[data-tour-pm-cp="deadline"]', title: 'Deadline',       body: 'Target completion date. Feeds the Timeline & Gantt agent and drives the "check deadlines" alerts.', placement: 'right' },
    { selector: '[data-tour-pm-cp="industry"]', title: 'Industry',       body: 'Optional industry tag — helps the AI apply the right templates and workflow suggestions.', placement: 'right' },
    { selector: '[data-tour-pm-cp="submit"]',   title: 'Create project', body: 'One click and the project is created. You can add tasks to it right away from the Create Task tab.', placement: 'top' },
  ],
};

export const PM_CREATE_TASK_TOUR = {
  key: 'pm_tour_create_task_v1',
  label: 'Create Task',
  steps: [
    { title: 'Create Task ➕', body: 'Manual task creation form. Assign, prioritize, and set a due date in under a minute.', placement: 'center' },
    { selector: '[data-tour-pm-ct="project"]',  title: 'Which project?',  body: 'Pick the project this task belongs to. Every task must live under a project.', placement: 'right' },
    { selector: '[data-tour-pm-ct="title"]',    title: 'Task title',      body: 'A short, action-oriented title. "Design landing page" beats "Landing page stuff".', placement: 'right' },
    { selector: '[data-tour-pm-ct="desc"]',     title: 'Description',     body: 'What needs doing? Include acceptance criteria if you have them — the AI uses this when generating subtasks.', placement: 'right' },
    { selector: '[data-tour-pm-ct="status"]',   title: 'Status',          body: 'To Do, In Progress, Review, Done, or Blocked. New tasks usually start as To Do.', placement: 'right' },
    { selector: '[data-tour-pm-ct="priority"]', title: 'Priority',        body: 'Low, Medium, High, or Critical. Drives the Task Prioritization agent\'s ranking.', placement: 'right' },
    { selector: '[data-tour-pm-ct="assignee"]', title: 'Assignee',        body: 'Who owns this task? Optional — you can assign later. Delegation suggestions use this field.', placement: 'right' },
    { selector: '[data-tour-pm-ct="duedate"]',  title: 'Due date',        body: 'When it needs doing. Drives deadline alerts and Gantt bar placement.', placement: 'right' },
    { selector: '[data-tour-pm-ct="submit"]',   title: 'Create task',     body: 'Save it. The task appears in the project instantly and every prioritization / timeline view updates.', placement: 'top' },
  ],
};

export const PM_PROJECT_PILOT_TOUR = {
  key: 'pm_tour_project_pilot_v1',
  label: 'Project Pilot',
  steps: [
    { title: 'Project Pilot 🎯', body: "Your natural-language project manager. Ask it to create projects, add tasks, update statuses, generate subtasks, upload requirements — anything a PM would do.", placement: 'center' },
    { selector: '[data-tour-pm-pp="sidebar"]',      title: 'Chat history sidebar', body: 'Every past conversation lives here. Click any chat to reopen it — the AI keeps the full context.', placement: 'right' },
    { selector: '[data-tour-pm-pp="new-chat"]',    title: 'Start a new chat',     body: 'Open a fresh conversation. Use this when switching projects or topics.', placement: 'right' },
    { selector: '[data-tour-pm-pp="history-toggle"]', title: 'Collapse sidebar',   body: 'Hide the sidebar to focus on the conversation. Bring it back with the same button.', placement: 'right' },
    { selector: '[data-tour-pm-pp="project-select"]', title: 'Project context',   body: 'Pick which project this chat is about. Scopes every question and action to that project.', placement: 'top' },
    { selector: '[data-tour-pm-pp="file-upload"]',  title: 'Upload requirements',  body: 'Drop in a spec, brief, or requirements doc. The Pilot reads it and can generate tasks / a timeline directly from the file.', placement: 'top' },
    { selector: '[data-tour-pm-pp="input"]',        title: 'Ask anything PM-related', body: '"Add a design task to marketing", "What\'s blocking the launch?", "Generate subtasks for the API integration". Enter to send, Shift+Enter for a new line.', placement: 'top' },
    { selector: '[data-tour-pm-pp="send"]',         title: 'Send',                 body: 'Submit your request. The Pilot parses it, takes action if it can, or asks you a clarifying question.', placement: 'top' },
  ],
};

export const PM_TASK_PRIO_TOUR = {
  key: 'pm_tour_task_prio_v1',
  label: 'Task Prioritization',
  steps: [
    { title: 'Task Prioritization 📊', body: 'AI-driven task ranking. Pick a project, hit an action, get a data-backed recommendation.', placement: 'center' },
    { selector: '[data-tour-pm-tp="project-select"]', title: 'Pick a project',        body: 'Every action below scopes to whichever project you select here.', placement: 'bottom' },
    { selector: '[data-tour-pm-tp="action-prioritize"]', title: 'Prioritize & order tasks', body: 'Ranks every task in the project by urgency + impact, and suggests the ideal execution order.', placement: 'bottom' },
    { selector: '[data-tour-pm-tp="action-bottlenecks"]', title: 'Find bottlenecks',   body: 'Spot the tasks that are blocking everything else. Great when a sprint feels stuck and you can\'t tell why.', placement: 'bottom' },
    { selector: '[data-tour-pm-tp="action-delegation"]',  title: 'Suggest delegation', body: 'Given each team member\'s skills and workload, the AI suggests who should own which tasks.', placement: 'bottom' },
    { selector: '[data-tour-pm-tp="generate-subtasks"]',  title: 'Generate subtasks',  body: 'Given the current task list, the AI breaks big tasks into smaller subtasks so nothing feels overwhelming.', placement: 'bottom' },
    { selector: '[data-tour-pm-tp="results"]',            title: 'Results panel',      body: 'Every action\'s output shows up here — ranked task lists, bottleneck reasoning, or delegation suggestions.', placement: 'top' },
  ],
};

export const PM_KNOWLEDGE_QA_TOUR = {
  key: 'pm_tour_knowledge_qa_v1',
  label: 'Knowledge Q&A',
  steps: [
    { title: 'Knowledge Q&A 💬', body: "Ask any question about your projects, tasks, or team. The AI answers with citations — or generates a chart if you'd rather see it as a graph.", placement: 'center' },
    { selector: '[data-tour-pm-kqa="sidebar"]',       title: 'Chat history sidebar', body: 'Every past conversation. Click any chat to reopen — the AI remembers the full context.', placement: 'right' },
    { selector: '[data-tour-pm-kqa="new-chat"]',      title: 'Start a new chat',     body: 'Open a fresh conversation. Use when switching topics.', placement: 'right' },
    { selector: '[data-tour-pm-kqa="input-mode"]',    title: 'Search vs. Graph mode', body: '"Search" answers with text + citations. "Graph" generates a chart from your project data — great for "show me tasks by status".', placement: 'top' },
    { selector: '[data-tour-pm-kqa="project-select"]', title: 'Project context',      body: 'Optional — pick a project to scope every question to just that project\'s data.', placement: 'top' },
    { selector: '[data-tour-pm-kqa="input"]',         title: 'Ask any question',     body: "'How many tasks are blocked?', 'Which projects are behind schedule?', 'Break down tasks by assignee'. Enter to send, Shift+Enter for a new line.", placement: 'top' },
    { selector: '[data-tour-pm-kqa="send"]',          title: 'Send',                 body: 'Submit your question. In Graph mode it renders a chart; in Search mode it answers with citations.', placement: 'top' },
    { selector: '[data-tour-pm-kqa="results"]',       title: 'Answers here',         body: 'AI replies appear here. Each Search answer cites its source; each Graph answer includes a chart plus an insight paragraph.', placement: 'left' },
  ],
};

export const PM_TIMELINE_TOUR = {
  key: 'pm_tour_timeline_v1',
  label: 'Timeline & Gantt',
  steps: [
    { title: 'Timeline & Gantt 📅', body: 'Every scheduling tool in one place. Build a timeline, render a Gantt, check deadlines, calculate durations, manage phases.', placement: 'center' },
    { selector: '[data-tour-pm-tl="project-select"]',    title: 'Pick a project',           body: 'Every action below scopes to whichever project you select here.', placement: 'bottom' },
    { selector: '[data-tour-pm-tl="action-create"]',     title: 'Create timeline',          body: 'Given the project\'s tasks and deadlines, the AI proposes a full timeline you can accept or tweak.', placement: 'bottom' },
    { selector: '[data-tour-pm-tl="action-gantt"]',      title: 'Generate Gantt chart',     body: 'Renders an interactive Gantt for the project — tasks as bars, dependencies as arrows.', placement: 'bottom' },
    { selector: '[data-tour-pm-tl="action-check"]',      title: 'Check deadlines',          body: 'Flags anything due in the next N days (see "Days ahead" below) or already overdue.', placement: 'bottom' },
    { selector: '[data-tour-pm-tl="action-suggest"]',    title: 'Suggest adjustments',      body: 'AI proposes schedule changes to hit your deadlines — moving tasks, changing durations, resequencing.', placement: 'bottom' },
    { selector: '[data-tour-pm-tl="action-duration"]',   title: 'Calculate duration',       body: 'Given historical data and task complexity, the AI estimates how long the project realistically takes.', placement: 'bottom' },
    { selector: '[data-tour-pm-tl="action-phases"]',     title: 'Manage phases',            body: 'Group tasks into phases (Discovery, Build, Launch…) so the timeline reads as a story, not a task dump.', placement: 'bottom' },
    { selector: '[data-tour-pm-tl="days-ahead"]',        title: 'Days ahead',               body: 'Controls the "Check deadlines" window. Default is 7 — bump to 30 for a monthly view.', placement: 'top' },
    { selector: '[data-tour-pm-tl="scale"]',             title: 'Timeline scale',           body: 'Auto, Days, Weeks, or Months. Controls the granularity of the rendered timeline / Gantt.', placement: 'top' },
    { selector: '[data-tour-pm-tl="results"]',           title: 'Rendered timeline / Gantt', body: 'Every action\'s output shows up here — interactive timeline, Gantt chart, deadline table, or suggestion list.', placement: 'top' },
  ],
};

export const PM_MEETING_TOUR = {
  key: 'pm_tour_meeting_v1',
  label: 'Meeting Scheduler',
  steps: [
    { title: 'Meeting Scheduler 📅', body: "Schedule meetings in plain English. Accept, reject, or counter-propose invites. Full history of every meeting you're in.", placement: 'center' },
    { selector: '[data-tour-pm-ms="tab-toggle"]', title: 'Chat vs. Meetings tabs',    body: "'Chat' is where you tell the AI what to schedule. 'Meetings' is the list of every meeting you\'re invited to.", placement: 'bottom' },
    { selector: '[data-tour-pm-ms="sidebar"]',    title: 'Scheduling conversations',  body: 'Every past scheduling chat. Reopen any one to see what was booked and when.', placement: 'right' },
    { selector: '[data-tour-pm-ms="new-chat"]',   title: 'Start a new chat',          body: 'Open a fresh scheduling conversation — use when the meeting is unrelated to the previous topic.', placement: 'right' },
    { selector: '[data-tour-pm-ms="input"]',      title: 'Describe the meeting',      body: 'Include names, date/time, duration, agenda — the more detail, the better the invite. Enter to send.', placement: 'top' },
    { selector: '[data-tour-pm-ms="send"]',       title: 'Send',                      body: 'Submit your request. The AI parses it, invites participants, and either books it or asks for missing info.', placement: 'top' },
    { selector: '[data-tour-pm-ms="list"]',       title: 'Your meetings list',        body: 'Every meeting you\'re in — as organizer or attendee. Includes status, role, and inline response buttons.', placement: 'top' },
    { selector: '[data-tour-pm-ms="status-filter"]', title: 'Filter by status',       body: 'Show only pending / accepted / rejected / completed. Great for daily triage.', placement: 'bottom' },
    { selector: '[data-tour-pm-ms="role-filter"]',   title: 'Filter by role',        body: 'Show only meetings where you\'re the organizer, or only ones where you\'re an attendee.', placement: 'bottom' },
    { selector: '[data-tour-pm-ms="respond"]',     title: 'Respond to invites',       body: 'Accept, reject with a reason, or counter-propose a different time — right on each meeting row.', placement: 'left' },
  ],
};

export const PM_AI_TOOLS_TOUR = {
  key: 'pm_tour_ai_tools_v1',
  label: 'AI Tools',
  steps: [
    { title: 'AI Tools 🧰', body: 'A hub for 9 more specialized agents. Each tool solves one specific PM problem, from daily standups to team performance analytics.', placement: 'center' },
    { selector: '[data-tour-pm-tools="grid"]', title: 'Tool grid', body: 'Click any card to open that tool. Some are chat-based (Standup, Notes), others are dashboards (Health, Team Performance, Calendar). All are AI-powered.', placement: 'bottom' },
  ],
};

// ---- Floating "Quick Chat" tour + hints -----------------------------------

export const PM_FLOATING_CHAT_TOUR = {
  key: 'pm_tour_floating_chat_v1',
  label: 'Quick Chat',
  steps: [
    { title: 'PM Quick Chat ✨', body: "Two agents in one chat. Switch between Project Pilot (creates & manages projects/tasks) and Knowledge Q&A (answers questions about your project data). Ctrl+K opens it from anywhere.", placement: 'center' },
    { selector: '[data-tour-pmfc="mode-switch"]', title: 'Pilot ↔ Q&A switcher',    body: 'Toggle between two agents. Project Pilot takes actions; Knowledge Q&A answers questions. Each has its own conversation history.', placement: 'bottom' },
    { selector: '[data-tour-pmfc="input"]',       title: 'Ask or command',          body: "In Pilot mode: 'create a task in marketing'. In Q&A mode: 'which projects are behind schedule?'. Type / for slash commands.", placement: 'top' },
    { selector: '[data-tour-pmfc="send"]',        title: 'Send',                    body: 'Submit. In Pilot mode, an action gets taken. In Q&A mode, an answer with citations comes back.', placement: 'top' },
    { selector: '[data-tour-pmfc="messages"]',    title: 'Answers & confirmations', body: 'Pilot confirms every action it takes. Q&A shows citations. Errors show as a red bubble.', placement: 'top' },
    { selector: '[data-tour-pmfc="header"]',      title: 'Header actions',          body: 'Mode switch on the left. Then history (per mode), + new chat, 🎓 replay this tour, and X to close. Ctrl+K reopens.', placement: 'bottom' },
  ],
};

// ---- Inline "!" hint content --------------------------------------------

export const PM_HINTS = {
  // Overview — post-restructure this is a stats grid + optional quick-jump
  // cards; the sidebar is the primary navigation.
  pmOvQuicknav: { title: 'Quick jump to any tab', body: 'Shortcut cards for each tab. The sidebar on the left has the same navigation plus sub-items.' },

  // Create Project
  pmCpName:     { title: 'Project name',    body: 'A clear, short name. Shows up in every list and chart later.' },
  pmCpDesc:     { title: 'Description',     body: 'One paragraph is enough. Helps the AI answer questions about this project later.' },
  pmCpStatus:   { title: 'Status',          body: 'Planning, Active, On Hold, or Completed. New projects usually start as Planning.' },
  pmCpPriority: { title: 'Priority',        body: 'Low, Medium, High, or Critical. Drives how the AI prioritizes tasks inside this project.' },
  pmCpBudget:   { title: 'Budget range',    body: 'Min and max budget (optional). Used by cost tracking and workflow-suggestions.' },
  pmCpDeadline: { title: 'Deadline',        body: 'Target completion date. Feeds Timeline & Gantt and the deadline-check tool.' },
  pmCpIndustry: { title: 'Industry',        body: 'Optional tag — helps the AI apply the right templates.' },
  pmCpSubmit:   { title: 'Create project',  body: 'Save it. You can start adding tasks from the Create Task tab.' },

  // Create Task
  pmCtProject:  { title: 'Which project?',  body: 'Every task must live under a project. Pick it here.' },
  pmCtTitle:    { title: 'Task title',      body: 'Action-oriented. "Design landing page" beats "Landing page stuff".' },
  pmCtDesc:     { title: 'Description',     body: 'Include acceptance criteria if you have them — the AI uses this to generate subtasks.' },
  pmCtStatus:   { title: 'Status',          body: 'To Do, In Progress, Review, Done, or Blocked. New tasks usually start as To Do.' },
  pmCtPriority: { title: 'Priority',        body: 'Drives the Task Prioritization ranking.' },
  pmCtAssignee: { title: 'Assignee',        body: 'Who owns this task? Optional — delegation suggestions can help here.' },
  pmCtDueDate:  { title: 'Due date',        body: 'Drives deadline alerts and Gantt bar placement.' },
  pmCtSubmit:   { title: 'Create task',     body: 'Save it. Every prioritization and timeline view updates instantly.' },

  // Project Pilot
  pmPpSidebar:       { title: 'Chat history',       body: 'Every past Pilot conversation. Click to reopen.' },
  pmPpNewChat:       { title: 'New chat',           body: 'Open a fresh Pilot conversation.' },
  pmPpHistoryToggle: { title: 'Collapse sidebar',   body: 'Hide the sidebar to focus on the conversation.' },
  pmPpProjectSelect: { title: 'Project context',    body: 'Scopes every question and action to the selected project.' },
  pmPpFileUpload:    { title: 'Upload requirements', body: 'Drop in a spec or brief — the Pilot reads it and can generate tasks / a timeline from it.' },
  pmPpInput:         { title: 'Ask or command',     body: "'Add a design task to marketing', 'Generate subtasks for the API'. Enter = send, Shift+Enter = newline." },
  pmPpSend:          { title: 'Send',               body: 'Submit. The Pilot takes the action or asks a clarifying question.' },

  // Task Prioritization
  pmTpProjectSelect:      { title: 'Pick a project',        body: 'Every action below scopes to this project.' },
  pmTpActionPrioritize:   { title: 'Prioritize & order',    body: 'Ranks tasks by urgency + impact and suggests execution order.' },
  pmTpActionBottlenecks:  { title: 'Find bottlenecks',      body: 'Highlights tasks blocking everything else.' },
  pmTpActionDelegation:   { title: 'Suggest delegation',    body: 'Given skills + workload, suggests who owns what.' },
  pmTpGenerateSubtasks:   { title: 'Generate subtasks',     body: 'Breaks big tasks into smaller subtasks so nothing feels overwhelming.' },
  pmTpResults:            { title: 'Results panel',         body: 'Ranked lists, bottleneck reasoning, delegation suggestions — all land here.' },

  // Knowledge Q&A
  pmKqaSidebar:        { title: 'Chat history',     body: 'Every past Q&A conversation. Click to reopen.' },
  pmKqaNewChat:        { title: 'New chat',         body: 'Open a fresh Q&A conversation.' },
  pmKqaInputMode:      { title: 'Search vs. Graph', body: '"Search" answers with text + citations. "Graph" generates a chart.' },
  pmKqaProjectSelect:  { title: 'Project context',  body: 'Optional — scope to one project or search across all.' },
  pmKqaInput:          { title: 'Ask a question',   body: "'How many tasks are blocked?', 'Break down tasks by assignee'. Enter = send." },
  pmKqaSend:           { title: 'Send',             body: 'Submit. Search returns text+citations; Graph returns a chart.' },
  pmKqaResults:        { title: 'Answers',          body: 'Each Search answer cites its source; each Graph includes an insight paragraph.' },

  // Timeline & Gantt
  pmTlProjectSelect:   { title: 'Pick a project',           body: 'Every action below scopes to this project.' },
  pmTlActionCreate:    { title: 'Create timeline',          body: 'AI proposes a full timeline you can accept or tweak.' },
  pmTlActionGantt:     { title: 'Generate Gantt',           body: 'Renders an interactive Gantt for the project.' },
  pmTlActionCheck:     { title: 'Check deadlines',          body: 'Flags anything due in the next N days or overdue.' },
  pmTlActionSuggest:   { title: 'Suggest adjustments',      body: 'AI proposes schedule changes to hit your deadlines.' },
  pmTlActionDuration:  { title: 'Calculate duration',       body: 'AI estimates how long the project realistically takes.' },
  pmTlActionPhases:    { title: 'Manage phases',            body: 'Group tasks into phases so the timeline reads as a story.' },
  pmTlDaysAhead:       { title: 'Days ahead',               body: 'Controls the "Check deadlines" window. Default 7.' },
  pmTlScale:           { title: 'Timeline scale',           body: 'Auto, Days, Weeks, or Months. Sets the granularity.' },
  pmTlResults:         { title: 'Rendered timeline / Gantt', body: 'Interactive timeline, Gantt chart, deadline table, or suggestion list — all land here.' },

  // Meeting Scheduler
  pmMsTabToggle:     { title: 'Chat vs. Meetings',      body: "'Chat' schedules; 'Meetings' lists everything you're invited to." },
  pmMsSidebar:       { title: 'Scheduling conversations', body: 'Every past scheduling chat. Reopen any one to see what was booked.' },
  pmMsNewChat:       { title: 'New chat',               body: 'Open a fresh scheduling conversation.' },
  pmMsInput:         { title: 'Describe the meeting',   body: 'Include names, date/time, duration, agenda.' },
  pmMsSend:          { title: 'Send',                   body: 'Submit. AI parses it, invites participants, books it or asks for missing info.' },
  pmMsList:          { title: 'Your meetings',          body: "Every meeting you're in — as organizer or attendee." },
  pmMsStatusFilter:  { title: 'Filter by status',       body: 'Pending / accepted / rejected / completed.' },
  pmMsRoleFilter:    { title: 'Filter by role',         body: 'Show only meetings where you organize, or only ones where you attend.' },
  pmMsRespond:       { title: 'Respond',                body: 'Accept, reject with a reason, or counter-propose a different time — inline.' },

  // AI Tools
  pmToolsGrid: { title: 'Tool hub', body: 'Click any card to open that tool. 9 more specialized agents live here.' },

  // Floating Quick Chat
  pmFcLauncher:    { title: 'PM Quick Chat launcher', body: 'Dual-mode AI: Project Pilot for actions, Knowledge Q&A for questions. Ctrl+K opens it from anywhere.' },
  pmFcModeSwitch:  { title: 'Pilot ↔ Q&A',            body: 'Toggle between the two agents. Each has its own conversation history.' },
  pmFcInput:       { title: 'Ask or command',         body: "In Pilot: 'create a task'. In Q&A: 'which projects are behind?'. Enter = send, Shift+Enter = newline. Type / for commands." },
  pmFcSend:        { title: 'Send',                   body: 'Submit. In Pilot mode an action happens; in Q&A mode an answer comes back.' },
  pmFcMessages:    { title: 'Answers & confirmations', body: 'Pilot confirms every action; Q&A cites its sources. Errors show as red bubbles.' },
  pmFcHeader:      { title: 'Header actions',         body: 'Mode switch, history (per mode), + new chat, 🎓 replay tour, X to close.' },
};

// ---- Per-tab tours for the NEW consolidated tabs ------------------------
// Short, focused tours for the 3 new tabs added in the restructure. They
// live alongside the (untouched) legacy tab tours above — those still work
// if a user deep-links to a hidden tab like ?tab=knowledge-qa.

export const PM_PROJECTS_TOUR = {
  key: 'pm_tour_projects_v1',
  label: 'Projects',
  steps: [
    { title: 'Projects tab 🗂️', body: 'Every project in one searchable list. Card-per-project with status, priority, task count, and expand-to-see-details.', placement: 'center' },
    { title: 'Search & filter', body: 'Filter the list with the search box at the top. As you type, the list narrows to matching names and descriptions.', placement: 'center' },
    { title: 'Create a new project', body: 'The "New Project" button on the top-right opens the manual create form in a dialog. Prefer to describe it? Use Ask (Pilot) instead — same result, less clicking.', placement: 'center' },
  ],
};

export const PM_TASKS_TOUR = {
  key: 'pm_tour_tasks_v1',
  label: 'Tasks',
  steps: [
    { title: 'Tasks tab ✅', body: 'Everything task-related lives here — the list of tasks across your projects, plus the Prioritize and Timeline sub-tools (accessible from the sidebar).', placement: 'center' },
    { title: 'Task list', body: 'Search + filter by project or status. Click "New Task" to add one manually; if a project filter is active, the dialog pre-selects it.', placement: 'center' },
    { title: 'Prioritize & Timeline', body: 'Two more sub-items under Tasks in the sidebar: Prioritize (AI ranking + bottleneck detection) and Timeline (Gantt / phases / duration calc). Click either to open.', placement: 'center' },
  ],
};

export const PM_INSIGHTS_TOUR = {
  key: 'pm_tour_insights_v1',
  label: 'Insights',
  steps: [
    { title: 'Insights tab 📊', body: 'Report-shaped tools: Project Health, Daily Standup, Team Performance. Previously buried inside AI Tools — now surfaced here.', placement: 'center' },
    { title: 'Switching between reports', body: 'Each report has its own view. Default is Project Health; the other two are reachable by URL (?tab=insights&sub=standup or &sub=team) for now.', placement: 'center' },
  ],
};

// ---- Convenience map ----------------------------------------------------
// Only include tours for VISIBLE tabs so the per-tab launcher UI doesn't
// offer tours for tabs the user can't reach through normal navigation.
// The hidden-tab tour constants above (PM_CREATE_PROJECT_TOUR, etc.) are
// still exported so URL deep-links can still launch them if needed.

export const PM_TAB_TOURS = {
  // Visible top-level tabs — reached from the sidebar directly.
  'project-pilot': PM_PROJECT_PILOT_TOUR,
  projects:        PM_PROJECTS_TOUR,
  tasks:           PM_TASKS_TOUR,
  insights:        PM_INSIGHTS_TOUR,
  overview:        PM_OVERVIEW_TOUR,
  // Hidden legacy tabs — reached via click-through from the visible tabs'
  // placeholder cards. Each still renders a "Tour this tab" button in its
  // TabsContent header; without these mappings the buttons were a silent
  // no-op (PM_TAB_TOURS[tabKey] → undefined → handler returns early).
  'create-project':     PM_CREATE_PROJECT_TOUR,
  'create-task':        PM_CREATE_TASK_TOUR,
  'task-prioritization': PM_TASK_PRIO_TOUR,
  'knowledge-qa':       PM_KNOWLEDGE_QA_TOUR,
  'timeline-gantt':     PM_TIMELINE_TOUR,
  'meeting-scheduler':  PM_MEETING_TOUR,
  'ai-tools':           PM_AI_TOOLS_TOUR,
};

// Main-tour storage key
export const PM_MAIN_TOUR_KEY = 'pm_tutorial_seen_v1';
