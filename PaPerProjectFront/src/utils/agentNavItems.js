import {
  Building2,
  BrainCircuit,
  UserCheck,
  Megaphone,
  Headphones,
  FileSearch,
  Reply,
  Target,
} from 'lucide-react';

/**
 * All agent modules with their nav config.
 * To add a new agent, just add an entry here — every dashboard picks it up automatically.
 */
const ALL_AGENTS = [
  { key: 'project_manager_agent', label: 'Project Manager Agent', icon: BrainCircuit, section: 'project-manager', path: '/project-manager/dashboard' },
  { key: 'recruitment_agent',     label: 'Recruitment Agent',     icon: UserCheck,    section: 'recruitment',      path: '/recruitment/dashboard' },
  { key: 'marketing_agent',       label: 'Marketing Agent',       icon: Megaphone,    section: 'marketing',        path: '/marketing/dashboard' },
  { key: 'frontline_agent',       label: 'Frontline Agent',       icon: Headphones,   section: 'frontline',        path: '/frontline/dashboard' },
  { key: 'operations_agent',      label: 'Operations Agent',      icon: FileSearch,   section: 'operations',       path: '/operations/dashboard' },
  { key: 'reply_draft_agent',     label: 'Reply Draft Agent',     icon: Reply,        section: 'reply-draft',      path: '/reply-draft/dashboard' },
  { key: 'ai_sdr_agent',          label: 'AI SDR Agent',          icon: Target,       section: 'ai-sdr',           path: '/ai-sdr/dashboard' },
];

/**
 * Build the navItems array for DashboardNavbar.
 *
 * @param {string[]} purchasedModules - list of purchased module keys
 * @param {string}   currentSection   - the section key of the current page (e.g. 'marketing')
 * @param {Function} navigate         - react-router navigate function
 * @returns {Array}  navItems ready for DashboardNavbar
 */
export const getAgentNavItems = (purchasedModules, currentSection, navigate) => {
  const items = [
    {
      label: 'Dashboard',
      icon: Building2,
      section: 'dashboard',
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
        onClick: () => navigate(agent.path),
      });
    }
  }

  return items;
};
