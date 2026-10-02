// Plain-language names for HR's internal codes. The codes are what the API
// stores and checks (hr_agent/signals.py WORKFLOW_EVENTS, hr_agent/tasks.py);
// people only see these. Other codes: utils/labels.
import { humanize } from '@/utils/labels';

export { humanize };

// What can start a workflow, in the order the editor offers them.
export const WORKFLOW_EVENTS = [
  { value: 'employee_hired', label: 'When someone joins' },
  { value: 'employee_offboarding_started', label: 'When someone starts serving notice' },
  { value: 'employee_leaving', label: 'When someone leaves' },
  { value: 'employee_on_leave', label: 'When someone goes on leave' },
  { value: 'employee_on_probation', label: 'When someone is put on probation' },
  { value: 'employee_30_days', label: '30 days after someone starts' },
  { value: 'leave_request_submitted', label: 'When leave is requested' },
  { value: 'leave_request_approved', label: 'When leave is approved' },
  { value: 'leave_request_rejected', label: 'When leave is declined' },
];

// What the daily check can send a notification template for.
export const NOTIFICATION_EVENTS = [
  { value: 'probation_ending', label: 'Probation is ending' },
  { value: 'birthday', label: "Someone's birthday" },
  { value: 'work_anniversary', label: 'A work anniversary' },
  { value: 'document_expiring', label: 'A document is expiring' },
  { value: 'review_due', label: 'A performance review is due' },
];

// Conditions a workflow can also require.
export const FILTER_LABELS = { leave_type: 'Leave type', department: 'Department' };

export const CHANNEL_LABELS = {
  email: 'Email', sms: 'SMS', in_app: 'In-app', slack: 'Slack', teams: 'MS Teams',
};

export const SEND_STATUS_LABELS = {
  pending: 'Waiting', sent: 'Sent', failed: 'Failed', cancelled: 'Cancelled', dead_lettered: 'Gave up',
};

const LABELS = Object.fromEntries([...WORKFLOW_EVENTS, ...NOTIFICATION_EVENTS].map((e) => [e.value, e.label]));

export const eventLabel = (code) => LABELS[code] || humanize(code);
