/**
 * Employee (/me/*) tour steps.
 *
 * Consumed by the generic FrontlineTutorial component. The main tour
 * introduces the /me shell (Home + sidebar + tabs). Per-tab tours can be
 * appended later as we deepen each view.
 *
 * See USER_DASHBOARD_REDESIGN.md, Chunk H — first-run onboarding.
 */

export const USER_MAIN_TOUR_KEY = 'user_me_tutorial_seen_v1';

export const USER_MAIN_TOUR_STEPS = [
  {
    title: 'Welcome to your space 👋',
    body: "This is where everything assigned to you lives — tasks, meetings, notifications, and your profile. This quick tour covers the layout in about a minute. You can skip anytime and replay it from the header.",
    placement: 'center',
  },
  {
    selector: '[data-tour="me-summary"]',
    title: 'Your day at a glance',
    body: 'These four tiles are your daily snapshot: open tasks, anything overdue, what\'s due this week, and any pending meeting invites.',
    placement: 'bottom',
  },
  {
    selector: '[data-tour="me-action-items"]',
    title: 'Handle these first',
    body: 'The top few things worth your attention right now — overdue items and pending invites bubble to the top so you know exactly where to start.',
    placement: 'top',
  },
  {
    selector: '[data-tour="me-quick-jump"]',
    title: 'Jump anywhere',
    body: 'Shortcuts into each area. You can also use the left sidebar to move between sections at any time.',
    placement: 'top',
  },
  {
    title: 'My Tasks',
    body: 'The Tasks page lists everything assigned to you with a progress slider and a status dropdown. Overdue tasks get a red border so you can\'t miss them, and there\'s an "Overdue" quick-filter at the top.',
    placement: 'center',
  },
  {
    title: 'My Meetings',
    body: 'Meeting invites show up here. Three distinct actions: Accept (green), Suggest a different time (blue), Reject (red). Reason and counter-time fields are ready when you need them.',
    placement: 'center',
  },
  {
    title: 'Notifications',
    body: 'The Notifications page shows full-length alerts and lets you mark items read or clear everything with one click. The little pill on the sidebar tells you how many are unread.',
    placement: 'center',
  },
  {
    title: 'My Profile',
    body: 'Your account info lives here, plus a link into HR self-service (leave balances, goals, reviews) if your company has the HR module. Editable profile fields land in a follow-up.',
    placement: 'center',
  },
  {
    title: 'That\'s it — you\'re ready 🎉',
    body: "You can replay this tour anytime from the 'Take the Tour' button in the header. If anything's missing, tell your admin.",
    placement: 'center',
  },
];
