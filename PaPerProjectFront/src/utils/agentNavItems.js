import {
  Building2,
  BrainCircuit,
  UserCheck,
  Megaphone,
  Headphones,
  FileSearch,
  Reply,
  Target,
  Users,
  CalendarClock,
  // inner-item icons
  LayoutDashboard,
  BarChart3,
  Briefcase,
  Upload,
  HelpCircle,
  Calendar,
  Star,
  FlaskConical,
  Settings,
  FileText,
  MessageSquareText,
  PenTool,
  Bell,
  Mail,
  RefreshCw,
  MessageSquare,
  Monitor,
  Ticket,
  GitBranch,
  Sparkles,
  Network,
  ClipboardList,
  AlertTriangle,
  ListChecks,
  CalendarDays,
  // PM restructure additions
  CheckSquare,
  LineChart,
  FolderKanban,
  CalendarPlus,
  // Company dashboard sub-tabs
  ListTodo,
  KeyRound,
  CreditCard,
} from 'lucide-react';

/**
 * All agent modules with their nav config.
 * To add a new agent, just add an entry here — every dashboard picks it up automatically.
 *
 * `children` are the agent's inner navigation items, shown nested in the sidebar
 * under the active agent. Two link shapes:
 *   - path  : { label, icon, path: '/ai-sdr/leads' }
 *   - query : { label, icon, path: '/frontline/dashboard', tab: 'documents' }
 *             → navigates to '/frontline/dashboard?tab=documents'
 * `basePath` is the URL prefix used to tell which agent is active.
 * Mirrors each dashboard's TAB_ITEMS (verified against the components).
 */
const ALL_AGENTS = [
  {
    key: 'project_manager_agent', label: 'Project Manager Agent', icon: BrainCircuit,
    section: 'project-manager', path: '/project-manager/dashboard', basePath: '/project-manager',
    // Matches the restructured PM dashboard (?tab=-driven). Same shape as
    // Frontline: parent tabs carry their own sub-items (routing to the legacy
    // hidden tabs via ?tab=), so the former inner PMSidebar is folded into
    // this one global sidebar.
    children: [
      {
        label: 'Ask (Pilot)', icon: Target, path: '/project-manager/dashboard', tab: 'project-pilot',
        basePathTab: 'project-pilot',
        children: [
          { label: 'Project Pilot',     icon: Target,        path: '/project-manager/dashboard', tab: 'project-pilot' },
          { label: 'Knowledge Q&A',     icon: MessageSquare, path: '/project-manager/dashboard', tab: 'knowledge-qa' },
          { label: 'Meeting Scheduler', icon: CalendarPlus,  path: '/project-manager/dashboard', tab: 'meeting-scheduler' },
        ],
      },
      { label: 'Projects', icon: FolderKanban, path: '/project-manager/dashboard', tab: 'projects' },
      {
        label: 'Tasks', icon: CheckSquare, path: '/project-manager/dashboard', tab: 'tasks',
        basePathTab: 'tasks',
        // 'List' has no legacy hidden tab (it's the default inline sub-tab of
        // TasksListView), so only Prioritize + Timeline appear as grandchildren.
        children: [
          { label: 'Prioritize', icon: Target,   path: '/project-manager/dashboard', tab: 'task-prioritization' },
          { label: 'Timeline',   icon: Calendar, path: '/project-manager/dashboard', tab: 'timeline-gantt' },
        ],
      },
      // Insights + Overview have no per-sub-item legacy tabs — leave flat.
      { label: 'Insights', icon: LineChart,     path: '/project-manager/dashboard', tab: 'insights' },
      { label: 'Overview', icon: BrainCircuit,  path: '/project-manager/dashboard', tab: 'overview' },
    ],
  },
  {
    key: 'recruitment_agent', label: 'Recruitment Agent', icon: UserCheck,
    section: 'recruitment', path: '/recruitment/job-descriptions', basePath: '/recruitment',
    children: [
      { label: 'Dashboard',        icon: LayoutDashboard, path: '/recruitment/dashboard' },
      { label: 'Analytics',        icon: BarChart3,       path: '/recruitment/analytics' },
      { label: 'Job Descriptions', icon: Briefcase,       path: '/recruitment/job-descriptions' },
      { label: 'CV Processing',    icon: Upload,          path: '/recruitment/cvprocessing' },
      { label: 'AI Questions',     icon: HelpCircle,      path: '/recruitment/ai-interview-questions' },
      { label: 'Candidates',       icon: Users,           path: '/recruitment/candidates' },
      { label: 'Interviews',       icon: Calendar,        path: '/recruitment/interviews' },
      { label: 'Saved Prompts',    icon: Star,            path: '/recruitment/saved-prompts' },
      { label: 'API Tester',       icon: FlaskConical,    path: '/recruitment/api-tester' },
      {
        label: 'Settings', icon: Settings, path: '/recruitment/settings/email',
        basePath: '/recruitment/settings',
        children: [
          { label: 'Email',         icon: Mail,     path: '/recruitment/settings/email' },
          { label: 'Interview',     icon: Calendar, path: '/recruitment/settings/interview' },
          { label: 'Qualification', icon: Target,   path: '/recruitment/settings/qualification' },
        ],
      },
    ],
  },
  {
    key: 'marketing_agent', label: 'Marketing Agent', icon: Megaphone,
    section: 'marketing', path: '/marketing/dashboard', basePath: '/marketing',
    children: [
      { label: 'Dashboard',     icon: BarChart3,   path: '/marketing/dashboard', tab: 'dashboard' },
      { label: 'Campaigns',     icon: Megaphone,   path: '/marketing/dashboard', tab: 'campaigns' },
      { label: 'Email',         icon: Mail,        path: '/marketing/dashboard', tab: 'email' },
      { label: 'Q&A',           icon: MessageSquare, path: '/marketing/dashboard', tab: 'qa' },
      { label: 'Research',      icon: Sparkles,    path: '/marketing/dashboard', tab: 'research' },
      { label: 'Documents',     icon: FileText,    path: '/marketing/dashboard', tab: 'documents' },
      { label: 'Notifications', icon: Bell,        path: '/marketing/dashboard', tab: 'notifications' },
      { label: 'Saved Graphs',  icon: Sparkles,    path: '/marketing/dashboard', tab: 'saved-graphs' },
    ],
  },
  {
    key: 'frontline_agent', label: 'Frontline Agent', icon: Headphones,
    section: 'frontline', path: '/frontline/dashboard', basePath: '/frontline',
    // Matches the restructured Frontline (?tab=-driven). Parent tabs carry their
    // own sub-items (which route to the legacy hidden tabs via ?tab=), so the
    // former inner FrontlineSidebar is folded into this one global sidebar.
    children: [
      {
        label: 'Queue', icon: Headphones, path: '/frontline/dashboard', tab: 'queue',
        basePathTab: 'queue',
        children: [
          { label: 'Hand-offs', icon: Headphones, path: '/frontline/dashboard', tab: 'handoffs' },
          { label: 'Tickets',   icon: Ticket,     path: '/frontline/dashboard', tab: 'tickets' },
        ],
      },
      {
        label: 'Knowledge', icon: FileText, path: '/frontline/dashboard', tab: 'knowledge',
        basePathTab: 'knowledge',
        children: [
          { label: 'Documents',     icon: FileText,      path: '/frontline/dashboard', tab: 'documents' },
          { label: 'Knowledge Q&A', icon: MessageSquare, path: '/frontline/dashboard', tab: 'qa' },
        ],
      },
      {
        label: 'Insights', icon: BarChart3, path: '/frontline/dashboard', tab: 'insights',
        basePathTab: 'insights',
        children: [
          { label: 'Analytics', icon: BarChart3, path: '/frontline/dashboard', tab: 'analytics' },
          { label: 'AI Graphs', icon: Sparkles,  path: '/frontline/dashboard', tab: 'ai-graphs' },
        ],
      },
      {
        label: 'Automation', icon: GitBranch, path: '/frontline/dashboard', tab: 'automation',
        basePathTab: 'automation',
        children: [
          { label: 'Workflows',     icon: GitBranch, path: '/frontline/dashboard', tab: 'workflows' },
          { label: 'Notifications', icon: Bell,      path: '/frontline/dashboard', tab: 'notifications' },
        ],
      },
      {
        label: 'Settings', icon: Monitor, path: '/frontline/dashboard', tab: 'settings',
        basePathTab: 'settings',
        children: [
          { label: 'Chat widget', icon: Monitor, path: '/frontline/dashboard', tab: 'widget' },
        ],
      },
      { label: 'Overview', icon: LayoutDashboard, path: '/frontline/dashboard', tab: 'overview' },
    ],
  },
  {
    key: 'operations_agent', label: 'Operations Agent', icon: FileSearch,
    section: 'operations', path: '/operations/documents', basePath: '/operations',
    children: [
      { label: 'Dashboard',     icon: LayoutDashboard,   path: '/operations/dashboard' },
      { label: 'Documents',     icon: Upload,            path: '/operations/documents' },
      { label: 'Summarization', icon: FileText,          path: '/operations/summarization' },
      { label: 'Analytics',     icon: BarChart3,         path: '/operations/analytics' },
      { label: 'Knowledge Q&A', icon: MessageSquareText, path: '/operations/knowledge-qa' },
      { label: 'Authoring',     icon: PenTool,           path: '/operations/authoring' },
      { label: 'Notifications', icon: Bell,              path: '/operations/notifications' },
    ],
  },
  {
    key: 'reply_draft_agent', label: 'Reply Draft Agent', icon: Reply,
    section: 'reply-draft', path: '/reply-draft/dashboard', basePath: '/reply-draft',
    children: [
      { label: 'Dashboard', icon: LayoutDashboard, path: '/reply-draft/dashboard' },
      { label: 'Emails',    icon: Mail,            path: '/reply-draft/emails' },
    ],
  },
  {
    key: 'ai_sdr_agent', label: 'AI SDR Agent', icon: Target,
    section: 'ai-sdr', path: '/ai-sdr/dashboard', basePath: '/ai-sdr',
    children: [
      { label: 'Dashboard', icon: LayoutDashboard, path: '/ai-sdr/dashboard' },
      { label: 'Leads',     icon: Users,           path: '/ai-sdr/leads' },
      { label: 'Outreach',  icon: Mail,            path: '/ai-sdr/outreach' },
      { label: 'Meetings',  icon: Calendar,        path: '/ai-sdr/meetings' },
      { label: 'Analytics', icon: BarChart3,       path: '/ai-sdr/analytics' },
      { label: 'CRM Sync',  icon: RefreshCw,       path: '/ai-sdr/crm-sync' },
      { label: 'Settings',  icon: Settings,        path: '/ai-sdr/settings' },
    ],
  },
  {
    key: 'hr_agent', label: 'HR Support Agent', icon: Users,
    section: 'hr', path: '/hr/dashboard', basePath: '/hr',
    // Matches the restructured HR dashboard (?tab=-driven). Same shape as
    // Frontline: parent tabs carry their own sub-items (routing to the legacy
    // hidden tabs via ?tab=), so the former inner HRSidebar is folded into
    // this one global sidebar.
    children: [
      { label: 'Overview', icon: LayoutDashboard, path: '/hr/dashboard', tab: 'overview' },
      {
        label: 'People', icon: Users, path: '/hr/dashboard', tab: 'people',
        basePathTab: 'people',
        children: [
          { label: 'Employees', icon: Users,     path: '/hr/dashboard', tab: 'employees' },
          { label: 'My team',   icon: UserCheck, path: '/hr/dashboard', tab: 'my_team' },
          { label: 'Org chart', icon: Network,   path: '/hr/dashboard', tab: 'org_chart' },
        ],
      },
      {
        label: 'Knowledge', icon: MessageSquare, path: '/hr/dashboard', tab: 'knowledge',
        basePathTab: 'knowledge',
        children: [
          { label: 'Documents',     icon: FileText,      path: '/hr/dashboard', tab: 'documents' },
          { label: 'Knowledge Q&A', icon: MessageSquare, path: '/hr/dashboard', tab: 'qa' },
        ],
      },
      {
        label: 'Operations', icon: GitBranch, path: '/hr/dashboard', tab: 'operations',
        basePathTab: 'operations',
        children: [
          { label: 'Workflows',     icon: GitBranch,      path: '/hr/dashboard', tab: 'workflows' },
          { label: 'Leave',         icon: ClipboardList,  path: '/hr/dashboard', tab: 'leave' },
          { label: 'Notifications', icon: AlertTriangle,  path: '/hr/dashboard', tab: 'notifications' },
        ],
      },
      { label: 'Meetings', icon: CalendarClock, path: '/hr/dashboard', tab: 'meetings' },
    ],
  },
  {
    key: 'exec_meeting_agent', label: 'AI Executive Meeting Assistant', icon: CalendarClock,
    section: 'exec-meeting', path: '/exec-meeting/dashboard', basePath: '/exec-meeting',
    children: [
      { label: 'Overview',      icon: LayoutDashboard, path: '/exec-meeting/dashboard', tab: 'overview' },
      { label: 'Meetings',      icon: CalendarClock,   path: '/exec-meeting/dashboard', tab: 'meetings' },
      { label: 'Tasks',         icon: ListChecks,      path: '/exec-meeting/dashboard', tab: 'tasks' },
      { label: 'Calendar',      icon: CalendarDays,    path: '/exec-meeting/dashboard', tab: 'calendar' },
      { label: 'Documents',     icon: FileText,        path: '/exec-meeting/dashboard', tab: 'documents' },
      { label: 'Notifications', icon: Bell,            path: '/exec-meeting/dashboard', tab: 'notifications' },
    ],
  },
];

/**
 * Build the navItems array for DashboardNavbar / AgentSidebar.
 *
 * @param {string[]} purchasedModules - list of purchased module keys
 * @param {string}   currentSection   - the section key of the current page (e.g. 'marketing')
 * @param {Function} navigate         - react-router navigate function
 * @returns {Array}  navItems ready for the sidebar (each may carry `children`)
 */
export const getAgentNavItems = (purchasedModules, currentSection, navigate) => {
  // The company dashboard's own tabs, shown nested under "Dashboard" in the
  // sidebar (they used to live only as a horizontal tab bar on the page).
  // Each routes to /company/dashboard/<tab>; "Ticket Tasks" only appears when
  // the Frontline agent is purchased (mirrors the on-page tab bar), and
  // "API Keys" jumps to the settings route like its tab does.
  const dashboardChildren = [
    { label: 'My Jobs',         icon: Briefcase,    path: '/company/dashboard/jobs' },
    { label: 'Projects',        icon: FolderKanban, path: '/company/dashboard/projects' },
    { label: 'Applications',    icon: Users,        path: '/company/dashboard/applications' },
    { label: 'Users',           icon: UserCheck,    path: '/company/dashboard/users' },
    { label: 'All Users Tasks', icon: ListTodo,     path: '/company/dashboard/all-tasks' },
    ...(purchasedModules.includes('frontline_agent')
      ? [{ label: 'Ticket Tasks', icon: Ticket, path: '/company/dashboard/ticket-tasks' }]
      : []),
    { label: 'AI Agents',       icon: BrainCircuit, path: '/company/dashboard/ai-agents' },
    { label: 'Billing',         icon: CreditCard,   path: '/company/dashboard/billing' },
    { label: 'API Keys',        icon: KeyRound,     path: '/company/settings/api-keys' },
    { label: 'Notifications',   icon: Bell,         path: '/notifications' },
  ];

  const items = [
    {
      label: 'Dashboard',
      icon: Building2,
      section: 'dashboard',
      // Company pages that live OUTSIDE /company/dashboard (API Keys, and the
      // notifications page) still belong to this group. Without extraPaths the
      // sidebar could only match on `section`, so opening one of them collapsed
      // the whole Dashboard group.
      extraPaths: ['/company/settings', '/notifications'],
      children: dashboardChildren,
      onClick: () => navigate('/company/dashboard'),
    },
  ];

  for (const agent of ALL_AGENTS) {
    // Always show the current page's agent, otherwise only if purchased
    if (agent.section === currentSection || purchasedModules.includes(agent.key)) {
      items.push({
        label: agent.label,
        icon: agent.icon,
        section: agent.section,
        basePath: agent.basePath,
        children: agent.children || null,
        onClick: () => navigate(agent.path),
      });
    }
  }

  return items;
};
