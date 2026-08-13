import { Home, CheckSquare, Calendar, User, Bell } from 'lucide-react';

/**
 * Nav items for the employee (individual user) sidebar shell.
 *
 * Peer to `getAgentNavItems` in agentNavItems.js, but targets the
 * `/me/*` route group used by regular employees (Django-token users
 * and company_user accounts that don't have an agent module purchased).
 *
 * Each item follows the same shape AgentSidebar expects:
 *   { section, label, icon, path, onClick, basePath?, badge?, badgeTone? }
 *
 * `counts` is optional; when provided, matching items get a badge:
 *   { overdueTasks, pendingMeetings, unreadNotifications }
 */
export function getEmployeeNavItems(navigate, counts = {}) {
  const { overdueTasks = 0, pendingMeetings = 0, unreadNotifications = 0 } = counts;
  return [
    {
      section: 'me-home',
      label: 'Home',
      icon: Home,
      path: '/me/home',
      basePath: '/me/home',
      onClick: () => navigate('/me/home'),
    },
    {
      section: 'me-tasks',
      label: 'My Tasks',
      icon: CheckSquare,
      path: '/me/tasks',
      basePath: '/me/tasks',
      onClick: () => navigate('/me/tasks'),
      badge: overdueTasks,
      badgeTone: overdueTasks > 0 ? 'danger' : undefined,
    },
    {
      section: 'me-meetings',
      label: 'My Meetings',
      icon: Calendar,
      path: '/me/meetings',
      basePath: '/me/meetings',
      onClick: () => navigate('/me/meetings'),
      badge: pendingMeetings,
    },
    {
      section: 'me-notifications',
      label: 'Notifications',
      icon: Bell,
      path: '/me/notifications',
      basePath: '/me/notifications',
      onClick: () => navigate('/me/notifications'),
      badge: unreadNotifications,
    },
    {
      section: 'me-profile',
      label: 'My Profile',
      icon: User,
      path: '/me/profile',
      basePath: '/me/profile',
      onClick: () => navigate('/me/profile'),
    },
  ];
}

export const EMPLOYEE_SECTION_FROM_PATH = (pathname) => {
  if (pathname.startsWith('/me/home')) return 'me-home';
  if (pathname.startsWith('/me/tasks')) return 'me-tasks';
  if (pathname.startsWith('/me/meetings')) return 'me-meetings';
  if (pathname.startsWith('/me/notifications')) return 'me-notifications';
  if (pathname.startsWith('/me/profile')) return 'me-profile';
  return 'me-home';
};
