// What people see for the codes the API stores ("in_progress", "PENDING",
// "counter_proposed"): one place for all four agents, instead of each screen
// printing the code or tidying it its own way.

// Codes whose plain reading isn't just the words with spaces.
const WORDING = {
  todo: 'To do',
  in_progress: 'In progress',
  on_hold: 'On hold',
  auto_resolved: 'Auto-resolved',
  awaiting_approval: 'Waiting for approval',
  waiting_approval: 'Waiting for approval',
  counter_proposed: 'New time proposed',
  partially_accepted: 'Partly accepted',
  dead_lettered: 'Gave up',
  in_app: 'In-app',
  sms: 'SMS',
  llm: 'AI',
  sla_risk: 'SLA at risk',
  onsite_interview: 'Onsite interview',
  full_time: 'Full time',
  part_time: 'Part time',
  on_leave: 'On leave',
  ms_teams: 'MS Teams',
  teams: 'MS Teams',
  pto: 'PTO',
  hr: 'HR',
  pm: 'PM',
  ai: 'AI',
};

/** "leave_request_approved" -> "Leave request approved"; "PENDING" -> "Pending". */
export function humanize(code) {
  const text = String(code ?? '').replace(/[_.]+/g, ' ').replace(/\s+/g, ' ').trim().toLowerCase();
  return text ? text[0].toUpperCase() + text.slice(1) : '';
}

/** The words to show for a code; '' for none. */
export function labelOf(code) {
  if (code === null || code === undefined || code === '') return '';
  return WORDING[String(code).toLowerCase()] || humanize(code);
}

/** Each row with `key`'s code replaced by its words — for chart axes. */
export const labelled = (rows, key) => (rows || []).map((r) => ({ ...r, [key]: labelOf(r[key]) }));
