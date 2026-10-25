// Red is for something that broke: the connection or the server failed, or a page or feature is not there.
// Everything else people are told (a wrong password, a missing field, a person who is not on the team, the AI
// allowance used up) is something for them to act on, and is shown in amber. Both used to be the same red.
const BROKE = [
  /network|connection|connect to|unreachable|offline|failed to fetch|timed? ?out|timeout/i,
  /server error|internal error|status:? ?5\d\d|\b50[0-4]\b|service unavailable|bad gateway/i,
  /status:? ?404|\b404\b|^\s*not found\.?\s*$|(page|feature|endpoint|resource|address|url)\b[^.]{0,30}\bnot found|not available on this server/i,
  /something went wrong|unexpected|crash|exception|traceback|did not respond|didn't respond|took too long|not responding/i,
  /(failed|unable|could not|couldn't) to load|(failed|unable|could not|couldn't) load/i,
];

// "Failed to save project." with no reason after it: the server gave nothing to act on, so something broke.
// "Failed to save project: name is required" gives one, and is judged by that reason.
// "Could not find ..." is about who or what was asked for, not a breakage.
const BARE_FAILURE = /^\s*((failed|unable) to|(could not|couldn't) (?!find\b)\w+)[^:]*$/i;

const asText = (value) => (typeof value === 'string' ? value : '');

// Messages the API clients just threw for a server failure (status 500 and up) or a lost connection. A server
// can fail with a message that reads like a refusal ("Scheduling failed: <detail>"); this keeps it red.
const recentFailures = new Map();

export function noteFailure(message) {
  if (!message) return;
  const now = Date.now();
  recentFailures.set(String(message).trim(), now);
  for (const [text, at] of recentFailures) if (now - at > 15000) recentFailures.delete(text);
}

const isRecentFailure = (...parts) => parts.some((part) => {
  const at = recentFailures.get(asText(part).trim());
  return at !== undefined && Date.now() - at < 15000;
});

export function isRealError(title, description) {
  const text = `${asText(title)} ${asText(description)}`.trim();
  if (!text || /^(error|oops)[!.]?$/i.test(text)) return true;   // nothing to judge by: keep it red
  if (isRecentFailure(title, description)) return true;
  if (BROKE.some((pattern) => pattern.test(text))) return true;
  return BARE_FAILURE.test(asText(description).trim() || asText(title).trim());
}

// Toast props with the right colour: a red toast that is not a real error becomes an amber warning, and a bare
// "Error" title on it becomes "Warning". `variant: 'error'` forces red.
export function withSeverity(props) {
  if (props.variant === 'error') return { ...props, variant: 'destructive' };
  if (props.variant !== 'destructive' || isRealError(props.title, props.description)) return props;
  const title = /^\s*(error|oops)[!.]?\s*$/i.test(asText(props.title)) ? 'Warning' : props.title;
  return { ...props, variant: 'warning', title };
}
