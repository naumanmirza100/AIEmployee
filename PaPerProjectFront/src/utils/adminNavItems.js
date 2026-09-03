import {
  MessageSquare,
  BrainCircuit,
  FileCheck,
  Users as UsersIcon,
  DollarSign,
  LayoutDashboard,
  KeyRound,
  Server,
  Building2,
  Coins,
  History,
  Inbox,
  Bell,
} from 'lucide-react';

/**
 * Sidebar config for the admin shell.
 *
 * Both admin pages keep their own internal <Tabs>; the sidebar just drives the
 * `?tab=` in the URL. That way a click swaps the tab inside an already-mounted
 * page instead of remounting the whole route — the sidebar itself never
 * unmounts, so nothing flashes or re-fetches on navigation.
 *
 * Two groups plus Notifications, mirroring the company-side shell:
 *   Dashboard  → /admin/dashboard?tab=…
 *   API Keys   → /admin/api-keys?tab=…
 *
 * `pendingRequests` badges the API Keys group (and its Requests child) so the
 * admin can see outstanding key requests without opening the tab.
 */
export const getAdminNavItems = (navigate, { pendingRequests = 0 } = {}) => [
  {
    label: 'Dashboard',
    icon: LayoutDashboard,
    section: 'admin-dashboard',
    basePath: '/admin/dashboard',
    onClick: () => navigate('/admin/dashboard'),
    children: [
      { label: 'Contact Messages',    icon: MessageSquare, path: '/admin/dashboard', tab: 'contact' },
      { label: 'AI Predictions',      icon: BrainCircuit,  path: '/admin/dashboard', tab: 'predictions' },
      { label: 'Career Applications', icon: FileCheck,     path: '/admin/dashboard', tab: 'applications' },
      { label: 'Companies',           icon: UsersIcon,     path: '/admin/dashboard', tab: 'companies' },
      { label: 'AI Agents',           icon: BrainCircuit,  path: '/admin/dashboard', tab: 'agents' },
      { label: 'Agent Plans',         icon: DollarSign,    path: '/admin/dashboard', tab: 'agent-plans' },
    ],
  },
  {
    label: 'API Keys & Pricing',
    icon: KeyRound,
    section: 'admin-api-keys',
    basePath: '/admin/api-keys',
    badge: pendingRequests,
    badgeTone: 'danger',
    onClick: () => navigate('/admin/api-keys'),
    children: [
      { label: 'Overview',         icon: LayoutDashboard, path: '/admin/api-keys', tab: 'overview' },
      { label: 'Platform Keys',    icon: Server,          path: '/admin/api-keys', tab: 'platform' },
      { label: 'Per-Company Keys', icon: Building2,       path: '/admin/api-keys', tab: 'keys' },
      { label: 'Pricing',          icon: DollarSign,      path: '/admin/api-keys', tab: 'pricing' },
      { label: 'Quotas',           icon: Coins,           path: '/admin/api-keys', tab: 'quotas' },
      { label: 'Reset Logs',       icon: History,         path: '/admin/api-keys', tab: 'reset-logs' },
      // NOTE: AgentSidebar renders badges on parent items only, so the count
      // lives on the group above rather than here.
      { label: 'Requests', icon: Inbox, path: '/admin/api-keys', tab: 'requests' },
    ],
  },
  {
    label: 'Notifications',
    icon: Bell,
    section: 'admin-notifications',
    basePath: '/notifications',
    onClick: () => navigate('/notifications'),
  },
];

export default getAdminNavItems;
