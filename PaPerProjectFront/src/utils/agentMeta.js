import {
  Target,
  UserCheck,
  Megaphone,
  FileSearch,
  Headphones,
  Users,
  CalendarClock,
  Reply,
} from 'lucide-react';

/**
 * Per-agent metadata used by the shared AgentLayout to render the right title,
 * icon, active section, and module gate for whichever agent the URL points at.
 *
 * `basePath` — URL prefix that identifies this agent (matched against the
 *   current pathname).
 * `moduleKey` — the purchased-module key to gate on; `null` means always granted
 *   (AI SDR historically grants access unconditionally).
 *
 * Keyed by section (same section string used by getAgentNavItems / AgentSidebar).
 */
export const AGENT_META = {
  'ai-sdr':       { section: 'ai-sdr',       basePath: '/ai-sdr',       icon: Target,       title: 'AI SDR Agent',                    moduleKey: null },
  'recruitment':  { section: 'recruitment',  basePath: '/recruitment',  icon: UserCheck,    title: 'Recruitment Agent',               moduleKey: 'recruitment_agent' },
  'marketing':    { section: 'marketing',    basePath: '/marketing',    icon: Megaphone,    title: 'Marketing Agent',                 moduleKey: 'marketing_agent' },
  'operations':   { section: 'operations',   basePath: '/operations',   icon: FileSearch,   title: 'Operations Agent',                moduleKey: 'operations_agent' },
  'frontline':    { section: 'frontline',    basePath: '/frontline',    icon: Headphones,   title: 'Frontline Agent',                 moduleKey: 'frontline_agent' },
  'hr':           { section: 'hr',           basePath: '/hr',           icon: Users,        title: 'HR Support Agent',                moduleKey: 'hr_agent' },
  'exec-meeting': { section: 'exec-meeting', basePath: '/exec-meeting', icon: CalendarClock, title: 'AI Executive Meeting Assistant', moduleKey: 'exec_meeting_agent' },
  'reply-draft':  { section: 'reply-draft',  basePath: '/reply-draft',  icon: Reply,        title: 'Reply Draft Agent',               moduleKey: 'reply_draft_agent' },
};

// Ordered longest-basePath-first so the match is unambiguous.
const META_LIST = Object.values(AGENT_META).sort((a, b) => b.basePath.length - a.basePath.length);

/** Resolve the agent meta for a given pathname, or null if none matches. */
export function agentMetaForPath(pathname) {
  return META_LIST.find((m) => pathname === m.basePath || pathname.startsWith(m.basePath + '/')) || null;
}
