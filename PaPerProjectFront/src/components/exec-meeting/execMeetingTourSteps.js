// Guided-tour step definitions for the AI Executive Meeting Assistant.
// Reuses the generic FrontlineTutorial overlay component (open/onClose/
// setActiveTab/steps/storageKey). Each step optionally switches to a tab and
// highlights an element via a `data-tour-em="..."` selector.

export const EXEC_MEETING_TOUR_KEY = 'exec_meeting_tutorial_seen_v1';

// localStorage key for the auto "How it works" modal (shown once on first visit,
// before the guided tour). Kept separate from the tour key so the two are
// independent — resetting one doesn't reset the other.
export const EXEC_MEETING_HOWITWORKS_KEY = 'exec_meeting_howitworks_seen_v1';

// High-level "what this agent does for you" steps for the HowItWorksModal.
// Icon names are the string keys resolved in ExecMeetingDashboard (kept as
// strings here so this stays a plain data module with no React imports).
// Titles are kept to roughly one line and bodies to a similar length (~2 lines)
// so every card reads as the same size — an even, structured row rather than a
// ragged one. Keep new steps to this shape.
export const EXEC_MEETING_HOWITWORKS_STEPS = [
  {
    icon: 'Users',
    title: 'Add your team',
    body: 'Add users from the Dashboard they appear in the Users tab, ready to assign.',
  },
  {
    icon: 'CalendarClock',
    title: 'Schedule a meeting',
    body: 'Create a meeting and the AI drafts its description and agenda for you.',
  },
  {
    icon: 'Mail',
    title: 'Participants get invited',
    body: 'Everyone added to the meeting gets an email invite and updates if it changes.',
  },
  {
    icon: 'Sparkles',
    title: 'AI takes the notes',
    body: 'Paste the transcript and AI extracts the summary, decisions and action items.',
  },
  {
    icon: 'ListChecks',
    title: 'Tasks & subtasks',
    body: 'Action items become tasks. Add subtasks and assign an owner to each.',
  },
  {
    icon: 'Mail',
    title: 'Assignees get emailed',
    body: 'Whoever owns a task or subtask is emailed and again whenever it changes.',
  },
  {
    icon: 'CalendarDays',
    title: 'AI plans your week',
    body: '“Plan This Week” builds an optimised schedule with focus blocks, export as PDF.',
  },
  {
    icon: 'FileText',
    title: 'Generate documents',
    body: 'Pick a type and link a meeting to fill it in or start from a blank template.',
  },
  {
    icon: 'Bell',
    title: 'Proactive reminders',
    body: 'Reminders, overdue alerts and a daily digest land in Notifications for you.',
  },
];

export const EXEC_MEETING_TOUR_STEPS = [
  {
    title: 'Welcome to your Meeting Assistant 👋',
    body: "This quick tour walks you through every tab of the dashboard — scheduling meetings, tracking tasks, AI weekly planning, documents and notifications. You can skip anytime and replay it later from the 'Take the Tour' button.",
    placement: 'center',
  },
  {
    selector: '[data-tour-em="tabs"]',
    title: 'Everything lives in these tabs',
    body: 'Six tabs: Overview, Meetings, Tasks, Calendar, Documents and Notifications. We\'ll visit each one.',
    placement: 'bottom',
  },
  {
    tab: 'overview',
    selector: '[data-tour-em="stats"]',
    title: 'Overview — your daily snapshot',
    body: 'At-a-glance cards: upcoming meetings, total tasks, overdue tasks, pending action items and unread notifications. Below them, an AI "Daily Digest" summarises your day and top priorities.',
    placement: 'bottom',
  },
  {
    tab: 'meetings',
    selector: '[data-tour-em="tab-meetings"]',
    title: 'Meetings',
    body: 'Schedule and manage meetings. Click "Schedule" to create one (with an AI-written description & agenda), add participants, edit, and paste a transcript so the AI Notetaker extracts a summary, decisions and action items.',
    placement: 'bottom',
  },
  {
    tab: 'tasks',
    selector: '[data-tour-em="tab-tasks"]',
    title: 'Tasks',
    body: 'Track executive tasks with priority, status, due dates and assignees. Add subtasks (with a progress bar), or bulk-select and delete. Edit / add-subtask / delete are right on each row.',
    placement: 'bottom',
  },
  {
    tab: 'calendar',
    selector: '[data-tour-em="tab-calendar"]',
    title: 'Calendar — AI Weekly Planner',
    body: 'Click "Plan This Week" and the AI builds an optimised schedule from your meetings, tasks and subtasks — with suggested time slots, focus blocks and recommendations. Export it as a PDF.',
    placement: 'bottom',
  },
  {
    tab: 'documents',
    selector: '[data-tour-em="docs-create"]',
    title: 'Documents — create',
    body: 'The top half is the generator. Pick a document type (meeting agenda, minutes or executive briefing), optionally link a saved meeting to pull its topics in automatically, then hit "Generate & Save" and AI writes it for you.',
    placement: 'bottom',
  },
  {
    tab: 'documents',
    selector: '[data-tour-em="docs-saved"]',
    title: 'Documents — saved',
    body: 'The bottom half is your library of saved documents. Open any one, download it as a PDF, or bulk-select and delete. Everything you generate lands here.',
    placement: 'top',
  },
  {
    tab: 'notifications',
    selector: '[data-tour-em="tab-notifications"]',
    title: 'Notifications',
    body: 'Meeting reminders, overdue/due tasks, action items and participant responses land here. Click any notification to jump straight to the meeting or task it\'s about. The tab shows an unread count.',
    placement: 'bottom',
  },
  {
    selector: '[data-tour-em="replay"]',
    title: 'Need the tour again?',
    body: "Click 'Take the Tour' here anytime to replay this walkthrough. That's it — you're all set! 🎉",
    placement: 'bottom',
  },
];
