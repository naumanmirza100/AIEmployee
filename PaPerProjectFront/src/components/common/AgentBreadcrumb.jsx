import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { ChevronRight, Home } from 'lucide-react';

/**
 * Breadcrumb trail for the agent workspace. Derived entirely from the same
 * `navItems` hierarchy the left sidebar uses (agent → children → grandchildren),
 * so it stays in sync automatically and needs no extra config.
 *
 * Renders: Home › <Agent> › <Child> › <Grandchild>
 * Every crumb except the last is a link to its route (path or ?tab=).
 *
 * Props:
 *   navItems      — from getAgentNavItems(...) (each may carry basePath/children)
 *   activeSection — the current agent's section key
 */
const AgentBreadcrumb = ({ navItems = [], activeSection }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const here = location.pathname.replace(/\/$/, '');
  const curTab = searchParams.get('tab');

  // ── Find the active agent ──
  const agent = navItems.find(
    (n) => n.section === activeSection || (n.basePath && here.startsWith(n.basePath)),
  );
  if (!agent) return null;

  const tabFor = (child) => curTab || defaultTabFor(child?.path);

  const childMatches = (child) => {
    const there = (child.path || '').replace(/\/$/, '');
    if (child.tab != null) return here === there && tabFor(child) === child.tab;
    // For a group parent, "matches" if the URL is under its basePath OR its
    // ?tab= belongs to it / one of its grandchildren.
    if (child.basePath) return here === child.basePath || here.startsWith(child.basePath + '/');
    if (child.basePathTab != null) {
      const cur = tabFor(child);
      return cur === child.basePathTab || (child.children || []).some((g) => g.tab === cur);
    }
    return here === there;
  };

  // ── Walk the trail: agent → child → grandchild ──
  const trail = [{ label: agent.label, onClick: () => agent.onClick?.() }];

  const child = (agent.children || []).find(childMatches);
  if (child) {
    trail.push({ label: child.label, onClick: () => goTo(navigate, child) });

    const grand = (child.children || []).find((g) => {
      const there = (g.path || '').replace(/\/$/, '');
      if (g.tab != null) return here === there && tabFor(g) === g.tab;
      return here === there;
    });
    if (grand) {
      trail.push({ label: grand.label, onClick: () => goTo(navigate, grand) });
    }
  } else {
    // URL not represented in the sidebar config (e.g. a detail page like
    // /recruitment/candidates/32). Show a readable label from the last path
    // segment so the breadcrumb is never broken.
    const detail = detailCrumb(here, agent);
    if (detail) trail.push({ label: detail, onClick: null });
  }

  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-[13px] text-white/45 mb-4 flex-wrap">
      <button
        onClick={() => navigate('/company/dashboard')}
        className="inline-flex items-center gap-1 hover:text-white/80 transition-colors"
        title="Dashboard"
      >
        <Home className="h-3.5 w-3.5" />
      </button>
      {trail.map((c, i) => {
        const isLast = i === trail.length - 1;
        return (
          <span key={i} className="inline-flex items-center gap-1.5">
            <ChevronRight className="h-3.5 w-3.5 text-white/25" />
            {isLast || !c.onClick ? (
              <span className={isLast ? 'text-white/90 font-medium' : 'text-white/45'}>{c.label}</span>
            ) : (
              <button onClick={c.onClick} className="hover:text-white/80 transition-colors">
                {c.label}
              </button>
            )}
          </span>
        );
      })}
    </nav>
  );
};

function goTo(navigate, item) {
  const url = item.tab != null ? `${item.path}?tab=${encodeURIComponent(item.tab)}` : item.path;
  navigate(url);
}

// Same defaults the sidebar uses so a bare /frontline or /marketing highlights
// the first tab.
function defaultTabFor(path) {
  if (path?.startsWith('/frontline')) return 'queue';
  if (path?.startsWith('/marketing')) return 'dashboard';
  if (path?.startsWith('/project-manager')) return 'overview';
  return '';
}

// Turn the last URL segment of a non-config page into a human label.
function detailCrumb(here, agent) {
  const rest = here.replace(agent.basePath || '', '').replace(/^\/+/, '');
  if (!rest) return null;
  const segs = rest.split('/');
  // For "candidates/32" show "Candidate Detail"; for a bare "candidates" the
  // sidebar child would have matched, so this only fires on deeper URLs.
  const last = segs[segs.length - 1];
  const parent = segs.length >= 2 ? segs[segs.length - 2] : segs[0];
  const titleize = (s) => s.replace(/[-_]/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase());
  if (/^\d+$/.test(last)) {
    // numeric id → singularise the parent collection: candidates → Candidate Detail
    const singular = parent.replace(/s$/, '');
    return `${titleize(singular)} Detail`;
  }
  return titleize(last);
}

export default AgentBreadcrumb;
