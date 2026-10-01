import { API_BASE_URL } from '@/config/apiConfig';

/**
 * "My work": one list of what the logged-in person has to do, across the
 * agents (backend: core/my_work.py).
 *
 * A dashboard login and an employee login authenticate different endpoints,
 * so pick the one for whichever is signed in — the same rule the bell uses.
 */
export function myWorkLogin() {
  const company = localStorage.getItem('company_auth_token');
  const employee = localStorage.getItem('auth_token');
  if (company && !employee) return { token: company, url: `${API_BASE_URL}/company/my-work`, page: '/my-work' };
  if (employee) return { token: employee, url: `${API_BASE_URL}/user/my-work`, page: '/me/work' };
  return null;
}

export async function fetchMyWork() {
  const login = myWorkLogin();
  if (!login) return [];
  const res = await fetch(login.url, { headers: { Authorization: `Token ${login.token}` } });
  if (!res.ok) throw new Error('Could not load your work.');
  const body = await res.json();
  return body?.data?.items || [];
}

const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());

/** When an item is due, as the viewer sees it. A date-only item (`all_day`)
 *  is due by the end of that day on the viewer's own calendar. */
export function dueAt(item) {
  if (!item?.due) return null;
  if (item.all_day) {
    const [y, m, d] = item.due.split('-').map(Number);
    return new Date(y, m - 1, d, 23, 59, 59);
  }
  return new Date(item.due);
}

export const DUE_GROUPS = [
  { key: 'overdue', label: 'Overdue' },
  { key: 'today', label: 'Today' },
  { key: 'week', label: 'Next 7 days' },
  { key: 'later', label: 'Later' },
  { key: 'none', label: 'No due date' },
];

export function dueGroup(item, now = new Date()) {
  const due = dueAt(item);
  if (!due) return 'none';
  if (due < now) return 'overdue';
  const today = startOfDay(now);
  const days = Math.round((startOfDay(due) - today) / 86400000);
  if (days <= 0) return 'today';
  if (days <= 7) return 'week';
  return 'later';
}

/** "Overdue since 3 Oct", "Today 14:30", "Tomorrow", "Fri 10 Oct". */
export function dueLabel(item, now = new Date()) {
  const due = dueAt(item);
  if (!due) return '';
  const group = dueGroup(item, now);
  const day = due.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
  const time = item.all_day ? '' : due.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  if (group === 'overdue') {
    return `Overdue since ${due.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}`;
  }
  if (group === 'today') return item.all_day ? 'Today' : `Today ${time}`;
  const days = Math.round((startOfDay(due) - startOfDay(now)) / 86400000);
  if (days === 1) return item.all_day ? 'Tomorrow' : `Tomorrow ${time}`;
  return item.all_day ? day : `${day} ${time}`;
}

/** How many need doing now: overdue, or due today. */
export function urgentCount(items, now = new Date()) {
  return items.filter((i) => ['overdue', 'today'].includes(dueGroup(i, now))).length;
}

export const AGENT_STYLE = {
  pm: 'bg-violet-500/15 text-violet-600 dark:text-violet-300 border-violet-500/30',
  hr: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30',
  frontline: 'bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-500/30',
  recruitment: 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30',
};
