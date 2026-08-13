import React from 'react';
import {
  CheckCircle2,
  Circle,
  PlayCircle,
  FileCheck,
  AlertCircle,
} from 'lucide-react';

/**
 * Shared task/meeting display helpers used by /me/* views (and eventually
 * by the legacy UserDashboardPage until it's fully deprecated). Extracted
 * from UserDashboardPage.jsx during the /me shell rollout.
 */

export const getStatusIcon = (status) => {
  switch (status) {
    case 'done':
      return <CheckCircle2 className="h-4 w-4 text-green-500" />;
    case 'in_progress':
      return <PlayCircle className="h-4 w-4 text-blue-500" />;
    case 'review':
      return <FileCheck className="h-4 w-4 text-purple-500" />;
    case 'blocked':
      return <AlertCircle className="h-4 w-4 text-red-500" />;
    default:
      return <Circle className="h-4 w-4 text-gray-400" />;
  }
};

export const getStatusColor = (status) => {
  switch (status) {
    case 'done':
      return 'bg-green-500/15 text-green-300 border border-green-500/25';
    case 'in_progress':
      return 'bg-blue-500/15 text-blue-300 border border-blue-500/25';
    case 'review':
      return 'bg-purple-500/15 text-purple-300 border border-purple-500/25';
    case 'blocked':
      return 'bg-red-500/15 text-red-300 border border-red-500/25';
    default:
      return 'bg-white/[0.06] text-white/70 border border-white/10';
  }
};

export const getPriorityColor = (priority) => {
  switch (priority) {
    case 'high':
      return 'bg-red-500/15 text-red-300 border-red-500/25';
    case 'medium':
      return 'bg-yellow-500/15 text-yellow-300 border-yellow-500/25';
    default:
      return 'bg-white/[0.06] text-white/60 border-white/10';
  }
};

export const humanStatus = (status) => (status || '').replace(/_/g, ' ');

/** Days until due (negative if overdue). null if no due date. */
export const daysUntilDue = (dueIso) => {
  if (!dueIso) return null;
  try {
    const due = new Date(dueIso);
    const now = new Date();
    const ms = due.setHours(23, 59, 59, 999) - now.getTime();
    return Math.floor(ms / (1000 * 60 * 60 * 24));
  } catch { return null; }
};

export const isOverdue = (task) => {
  const days = daysUntilDue(task?.due_date);
  return days !== null && days < 0 && task?.status !== 'done';
};

export const isDueThisWeek = (task) => {
  const days = daysUntilDue(task?.due_date);
  return days !== null && days >= 0 && days <= 7 && task?.status !== 'done';
};
