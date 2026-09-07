import { useState } from 'react';
import { useLocation, useNavigate, useSearchParams, matchPath } from 'react-router-dom';
import {
  ChevronsLeft, ChevronsRight, ChevronDown, ChevronRight, X,
  Target, BarChart3, ListOrdered, FileText, Users,
} from 'lucide-react';

// Campaign-detail tabs (mirrors CampaignDetail.jsx). Injected under "Campaigns"
// as nested sub-tabs while a campaign detail page is open, each linking to that
// campaign's ?tab=. Shown only in that context.
const CAMPAIGN_TABS = [
  { label: 'Overview',               icon: Target,      tab: 'overview' },
  { label: 'Analytics & dashboard',  icon: BarChart3,   tab: 'analytics' },
  { label: 'Email sequences',        icon: ListOrdered, tab: 'sequences' },
  { label: 'Email sending activity', icon: FileText,    tab: 'email-activity' },
  { label: 'Campaign leads',         icon: Users,       tab: 'leads' },
];

// Return the Marketing agent's children with a campaign-context group injected
// under "Campaigns" when a campaign detail page is open. Other agents unchanged.
function childrenWithCampaignTabs(item, pathname) {
  if (item.section !== 'marketing' || !item.children?.length) return item.children;
  const match = matchPath('/marketing/dashboard/campaign/:id/*', pathname)
    || matchPath('/marketing/dashboard/campaign/:id', pathname);
  const campaignId = match?.params?.id;
  if (!campaignId) return item.children; // not on a campaign → normal children

  const detailPath = `/marketing/dashboard/campaign/${campaignId}`;
  return item.children.map((child) => {
    if (child.tab !== 'campaigns') return child;
    return {
      ...child,
      path: detailPath,
      tab: 'overview',
      basePath: detailPath, // group active while on any campaign-detail URL
      children: CAMPAIGN_TABS.map((t) => ({
        label: t.label, icon: t.icon, path: detailPath, tab: t.tab,
      })),
    };
  });
}

/**
 * Collapsible left sidebar for agent navigation. Lists agents (Dashboard,
 * Recruitment, SDR, …) and — nested under the active agent — that agent's own
 * inner items (SDR: Leads / Meetings / Settings, …).
 *
 * The agent list + each agent's `children` come from getAgentNavItems, so
 * purchased-module filtering and "add a new agent" keep working unchanged.
 *
 * Child link shapes (from agentNavItems.js):
 *   path : { label, icon, path: '/ai-sdr/leads' }
 *   query: { label, icon, path: '/frontline/dashboard', tab: 'documents' }
 *
 * Props:
 *   navItems, activeSection, collapsed, onToggle, mobileOpen, onMobileClose
 */
const EXPANDED_W = 240;
const COLLAPSED_W = 64;

const AgentSidebar = ({
  navItems = [],
  activeSection,
  collapsed = false,
  onToggle,
  mobileOpen = false,
  onMobileClose,
  loading = false,
}) => {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const width = collapsed ? COLLAPSED_W : EXPANDED_W;

  // Which agents the user has manually expanded (in addition to the active one).
  // Accordion: only ONE agent's sub-tabs are open at a time.
  //   null            → default (the active agent is expanded)
  //   '<section>'     → that agent is the one manually expanded
  //   '__none__'      → the user explicitly collapsed everything
  const [openSection, setOpenSection] = useState(null);

  const isAgentActive = (item) =>
    item.section === activeSection ||
    (item.basePath && location.pathname.startsWith(item.basePath)) ||
    // Routes that belong to a group but sit outside its basePath (e.g. the
    // company Dashboard group owning /company/settings/api-keys).
    (item.extraPaths || []).some((p) => location.pathname.startsWith(p));

  const isAgentExpanded = (item) => {
    if (!item.children?.length) return false;
    if (openSection === null) return isAgentActive(item); // default: active one open
    return openSection === item.section;                  // exactly one open
  };

  const toggleExpand = (e, item) => {
    e.stopPropagation();
    // Opening this agent closes any other; toggling the open one collapses all.
    setOpenSection((cur) => {
      const currentlyOpen = cur === null ? (isAgentActive(item) ? item.section : null) : cur;
      return currentlyOpen === item.section ? '__none__' : item.section;
    });
  };

  const isChildActive = (child) => {
    // Normalise trailing slashes for path comparison.
    const here = location.pathname.replace(/\/$/, '');
    const there = (child.path || '').replace(/\/$/, '');
    if (here !== there) return false;
    if (child.tab != null) return (searchParams.get('tab') || defaultTabFor(child.path)) === child.tab;
    return true;
  };

  // A child that itself has sub-items (e.g. Settings → Email/Interview/…, or
  // Frontline's Knowledge → Documents/Q&A) is "active" when the current URL
  // matches it. Two shapes:
  //   basePath   — path-based group (URL falls under that path)
  //   basePathTab — ?tab=-based group: active when the current ?tab= equals the
  //     parent's own tab OR any of its grandchildren's tabs.
  const isChildGroupActive = (child) => {
    if (child.basePath) {
      const here = location.pathname.replace(/\/$/, '');
      return here === child.basePath || here.startsWith(child.basePath + '/');
    }
    if (child.basePathTab != null) {
      const cur = searchParams.get('tab') || defaultTabFor(child.path);
      if (cur === child.basePathTab) return true;
      return (child.children || []).some((gc) => gc.tab === cur);
    }
    return false;
  };

  const goToChild = (child) => {
    const url = child.tab != null ? `${child.path}?tab=${encodeURIComponent(child.tab)}` : child.path;
    navigate(url);
    onMobileClose?.();
  };

  const handleAgentClick = (item) => {
    // Navigating to an agent makes it active; reset the accordion so the newly
    // active agent expands (and any previously-opened one closes).
    setOpenSection(null);
    item.onClick?.();
    onMobileClose?.();
  };

  const List = ({ mobile }) => (
    <nav
      className="flex-1 overflow-y-auto overflow-x-hidden py-3 px-2 space-y-1 scrollbar-none"
      style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
    >
      {/* Skeleton while purchased agents load from the DB */}
      {/* Skeletons only when there is genuinely nothing to show yet. A cached
          module list already yields agent entries, so keep those on screen
          while the refresh completes — swapping real items for skeletons on
          every navigation is what made these pages look like a full reload.
          The Dashboard group is always present, so it cannot be the signal;
          the agent entries are. */}
      {loading && !navItems.some((i) => i.section && i.section !== 'dashboard') ? (
        Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className={`flex items-center rounded-lg h-11 ${collapsed ? 'justify-center px-0' : 'gap-3 px-3'}`}>
            <span className="h-5 w-5 rounded-md bg-white/[0.06] animate-pulse shrink-0" />
            {!collapsed && <span className="h-3 rounded bg-white/[0.06] animate-pulse" style={{ width: `${55 + (i % 3) * 12}%` }} />}
          </div>
        ))
      ) : (
        navItems.map((item) => {
          const active = isAgentActive(item);
          const Icon = item.icon;
          const hasChildren = item.children?.length > 0;
          const open = isAgentExpanded(item);
          const showChildren = open && !collapsed && hasChildren;

          return (
            <div key={item.section || item.path || item.label}>
              {/* Agent row */}
              <div
                className={`group relative w-full flex items-center rounded-lg transition-colors ${
                  collapsed ? 'justify-center h-11 px-0' : 'h-11 pl-3 pr-1.5'
                } ${
                  active
                    ? 'bg-violet-600/90 text-white shadow-[0_0_14px_rgba(139,92,246,0.35)]'
                    : 'text-white/60 hover:text-white hover:bg-white/[0.06]'
                }`}
              >
                {active && !collapsed && (
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 h-6 w-1 rounded-r bg-white/90" />
                )}
                {/* Label/icon → navigate to the agent */}
                <button
                  onClick={() => handleAgentClick(item)}
                  title={collapsed ? item.label : undefined}
                  className={`flex items-center min-w-0 flex-1 ${collapsed ? 'justify-center' : 'gap-3'}`}
                >
                  <span className="relative shrink-0">
                    {Icon && <Icon className={`${collapsed ? 'h-5 w-5' : 'h-[18px] w-[18px]'}`} />}
                    {/* Collapsed sidebar: badge sits on the icon so it stays visible. */}
                    {collapsed && item.badge > 0 && (
                      <span
                        className={`absolute -top-1 -right-1.5 min-w-[16px] h-[16px] px-1 rounded-full text-[9px] font-bold flex items-center justify-center ${
                          item.badgeTone === 'danger' ? 'bg-red-500 text-white' : 'bg-violet-500 text-white'
                        }`}
                      >
                        {item.badge > 9 ? '9+' : item.badge}
                      </span>
                    )}
                  </span>
                  {!collapsed && <span className="text-sm font-medium truncate">{item.label}</span>}
                  {/* Expanded sidebar: badge sits at the end of the row. */}
                  {!collapsed && item.badge > 0 && (
                    <span
                      className={`ml-auto min-w-[20px] h-[18px] px-1.5 rounded-full text-[10px] font-bold flex items-center justify-center ${
                        item.badgeTone === 'danger'
                          ? 'bg-red-500/90 text-white'
                          : active ? 'bg-white/20 text-white' : 'bg-violet-500/80 text-white'
                      }`}
                    >
                      {item.badge > 99 ? '99+' : item.badge}
                    </span>
                  )}
                </button>
                {/* Expand/collapse chevron — only when there are children */}
                {!collapsed && hasChildren && (
                  <button
                    onClick={(e) => toggleExpand(e, item)}
                    title={open ? 'Collapse' : 'Expand'}
                    className={`shrink-0 h-7 w-7 flex items-center justify-center rounded-md transition-colors ${
                      active ? 'hover:bg-white/15 text-white/80' : 'hover:bg-white/10 text-white/40'
                    }`}
                  >
                    {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                  </button>
                )}
              </div>

              {/* Nested children (Marketing gets campaign tabs injected under
                  "Campaigns" while a campaign detail page is open). */}
              {showChildren && (
                <div className="mt-1 mb-1 ml-4 pl-2 border-l border-white/10 space-y-0.5">
                  {childrenWithCampaignTabs(item, location.pathname).map((child) => {
                    const hasGrand = child.children?.length > 0;
                    const groupActive = hasGrand && isChildGroupActive(child);
                    const cActive = hasGrand ? groupActive : isChildActive(child);
                    const CIcon = child.icon;
                    return (
                      <div key={child.path + (child.tab || '')}>
                        <button
                          onClick={() => goToChild(child)}
                          className={`w-full flex items-center gap-2.5 rounded-md h-9 px-2.5 text-[13px] transition-colors ${
                            cActive
                              ? 'bg-violet-500/15 text-violet-200 font-medium'
                              : 'text-white/50 hover:text-white/90 hover:bg-white/[0.05]'
                          }`}
                        >
                          {CIcon && <CIcon className={`h-4 w-4 shrink-0 ${cActive ? 'text-violet-300' : ''}`} />}
                          <span className="truncate">{child.label}</span>
                        </button>

                        {/* Third level (e.g. Settings → Email / Interview / …),
                            shown when that group is active. */}
                        {hasGrand && groupActive && (
                          <div className="mt-0.5 mb-1 ml-3.5 pl-2 border-l border-white/10 space-y-0.5">
                            {child.children.map((gc) => {
                              const gActive = isChildActive(gc);
                              const GIcon = gc.icon;
                              return (
                                <button
                                  key={gc.path + (gc.tab || '')}
                                  onClick={() => goToChild(gc)}
                                  className={`w-full flex items-center gap-2 rounded-md h-8 px-2.5 text-[12.5px] transition-colors ${
                                    gActive
                                      ? 'bg-violet-500/15 text-violet-200 font-medium'
                                      : 'text-white/45 hover:text-white/85 hover:bg-white/[0.05]'
                                  }`}
                                >
                                  {GIcon && <GIcon className={`h-3.5 w-3.5 shrink-0 ${gActive ? 'text-violet-300' : ''}`} />}
                                  <span className="truncate">{gc.label}</span>
                                </button>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })
      )}
    </nav>
  );

  const panel = (mobile) => (
    <aside
      className="flex flex-col h-full border-r border-white/[0.08]"
      style={{
        width,
        background: 'linear-gradient(180deg, #0b0a16 0%, #0d0b1a 45%, #110e1f 100%)',
        transition: mobile ? undefined : 'width 180ms ease',
      }}
    >
      {/* Header row: brand + close (mobile) */}
      <div className={`flex items-center h-14 border-b border-white/[0.08] shrink-0 ${collapsed && !mobile ? 'justify-center px-0' : 'justify-between px-3'}`}>
        {(!collapsed || mobile) && (
          <div className="flex items-center gap-2 min-w-0">
            <img src="/logo.png" alt="" className="h-8 w-8 rounded-md object-contain shrink-0" />
            <span className="text-sm font-bold text-white truncate">Pay Per Project</span>
          </div>
        )}
        {collapsed && !mobile && (
          <img src="/logo.png" alt="" className="h-8 w-8 rounded-md object-contain" />
        )}
        {mobile && (
          <button
            onClick={onMobileClose}
            className="h-8 w-8 flex items-center justify-center rounded-md text-white/60 hover:text-white hover:bg-white/10"
            title="Close menu"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      <List mobile={mobile} />

      {/* Collapse toggle — desktop only */}
      {!mobile && (
        <div className="border-t border-white/[0.08] p-2 shrink-0">
          <button
            onClick={onToggle}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className={`w-full flex items-center rounded-lg h-9 text-white/50 hover:text-white hover:bg-white/[0.06] transition-colors ${
              collapsed ? 'justify-center' : 'gap-2 px-3'
            }`}
          >
            {collapsed ? <ChevronsRight className="h-4 w-4" /> : <><ChevronsLeft className="h-4 w-4" /><span className="text-xs font-medium">Collapse</span></>}
          </button>
        </div>
      )}
    </aside>
  );

  return (
    <>
      {/* ── Desktop: fixed sidebar ── */}
      <div
        className="hidden md:flex fixed top-0 left-0 z-40 h-screen"
        style={{ width, transition: 'width 180ms ease' }}
      >
        {panel(false)}
      </div>

      {/* ── Mobile: overlay drawer ── */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex">
          <div className="h-full shrink-0" style={{ width: EXPANDED_W }}>
            {panel(true)}
          </div>
          <div className="flex-1 bg-black/60" onClick={onMobileClose} />
        </div>
      )}
    </>
  );
};

// Default tab when the URL has no ?tab= yet, so the first child highlights on a
// bare /marketing/dashboard or /frontline/dashboard.
function defaultTabFor(path) {
  // Admin shell: each page's own default tab, so the sidebar highlights the
  // right child when the URL carries no ?tab= yet.
  if (path === '/admin/dashboard') return 'contact';
  if (path === '/admin/api-keys') return 'overview';
  if (path?.startsWith('/frontline')) return 'queue';
  // Campaign-detail tabs default to Overview; the marketing dashboard to Dashboard.
  if (path?.includes('/marketing/dashboard/campaign/')) return 'overview';
  if (path?.startsWith('/marketing')) return 'dashboard';
  // PM dashboard lands on Ask (Pilot) by default — matches the restructured
  // ProjectManagerDashboardPage default of 'project-pilot'.
  if (path?.startsWith('/project-manager')) return 'project-pilot';
  // HR dashboard lands on Overview by default — matches HRDashboard.jsx.
  if (path?.startsWith('/hr')) return 'overview';
  return '';
}

export { EXPANDED_W, COLLAPSED_W };
export default AgentSidebar;
