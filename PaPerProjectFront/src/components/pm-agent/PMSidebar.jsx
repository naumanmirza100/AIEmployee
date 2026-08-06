import React, { useState, useRef, useEffect } from 'react';
import { ChevronLeft, ChevronRight, ChevronDown } from 'lucide-react';

/**
 * PMSidebar — collapsible left rail for the PM dashboard.
 *
 * Sits alongside the main content on lg+; hidden below lg (mobile still uses
 * the existing hamburger dropdown at the top of the content area, so we
 * don't have to maintain a second responsive nav pattern here).
 *
 * Structure — the `items` prop drives everything:
 *   [{
 *     value: 'ask',
 *     label: 'Ask (Pilot)',
 *     icon: Target,
 *     subItems: [                    // optional
 *       { value: 'pilot', label: 'Project Pilot', icon: Target },
 *       { value: 'kqa',   label: 'Knowledge Q&A', icon: MessageSquare },
 *     ],
 *   }, ...]
 *
 * Sub-items are only shown when their parent is the active tab. Clicking a
 * sub-item calls onSubTabChange(parentValue, subValue). Clicking a parent
 * calls onTabChange(parentValue) — the parent view decides which default
 * sub-tab renders (we don't force one here).
 *
 * Collapse state is fully controlled by the parent via `collapsed` +
 * `onToggleCollapsed` so persistence (localStorage) can live at the top.
 */
export default function PMSidebar({
  items,
  activeTab,
  activeSubTab,
  onTabChange,
  onSubTabChange,
  collapsed = false,
  onToggleCollapsed,
}) {
  return (
    <aside
      // Hidden below `lg` — mobile users get the existing hamburger dropdown
      // at the top of the content area. Sticky so the sidebar scrolls with
      // the page but doesn't leave a visual gap when the content is short.
      className={`hidden lg:flex flex-col shrink-0 sticky top-4 self-start rounded-2xl border border-white/[0.06] transition-all duration-200 ${
        collapsed ? 'w-[64px]' : 'w-[220px]'
      }`}
      style={{
        background: 'linear-gradient(180deg, #0d0b1f 0%, #0f0a20 100%)',
        maxHeight: 'calc(100vh - 2rem)',
      }}
    >
      {/* Header — brand-ish label + collapse toggle. When collapsed we only
          show the toggle so the strip stays tight. */}
      <div className={`flex items-center h-12 ${collapsed ? 'justify-center' : 'justify-between px-3'} border-b border-white/[0.06]`}>
        {!collapsed && (
          <span className="text-xs font-semibold tracking-wider uppercase text-white/45">
            Project Pilot
          </span>
        )}
        <button
          type="button"
          onClick={onToggleCollapsed}
          className="h-7 w-7 inline-flex items-center justify-center rounded-md text-white/50 hover:text-white hover:bg-white/[0.06] transition"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </button>
      </div>

      {/* Nav list — scrolls internally if content overflows viewport */}
      <nav className="flex-1 overflow-y-auto py-2">
        <ul className="flex flex-col gap-0.5 px-2">
          {items.map((item) => (
            <SidebarItem
              key={item.value}
              item={item}
              collapsed={collapsed}
              activeTab={activeTab}
              activeSubTab={activeSubTab}
              onTabChange={onTabChange}
              onSubTabChange={onSubTabChange}
            />
          ))}
        </ul>
      </nav>
    </aside>
  );
}

// ─── SidebarItem ──────────────────────────────────────────────────────────
// One top-level nav row. If it has subItems and it's the active tab, the
// sub-items render indented below. When the sidebar is collapsed we show
// icon-only with a hover tooltip; sub-items are hidden entirely (the parent
// tab is still clickable — user expands the sidebar or uses the top hamburger
// to reach sub-tabs).

function SidebarItem({ item, collapsed, activeTab, activeSubTab, onTabChange, onSubTabChange }) {
  const isActive = item.value === activeTab;
  const Icon = item.icon;
  const hasSubs = Array.isArray(item.subItems) && item.subItems.length > 0;

  return (
    <li>
      <NavButton
        onClick={() => onTabChange(item.value)}
        active={isActive}
        collapsed={collapsed}
        icon={Icon}
        label={item.label}
        trailing={hasSubs && !collapsed
          ? <ChevronDown className={`h-3.5 w-3.5 text-white/40 transition-transform ${isActive ? '' : '-rotate-90'}`} />
          : null}
      />

      {/* Sub-items: only when this parent is active AND sidebar is expanded */}
      {hasSubs && isActive && !collapsed && (
        <ul className="mt-0.5 mb-1 flex flex-col gap-0.5">
          {item.subItems.map((sub) => {
            const SubIcon = sub.icon;
            const isSubActive = sub.value === activeSubTab;
            return (
              <li key={sub.value}>
                <button
                  type="button"
                  onClick={() => onSubTabChange(item.value, sub.value)}
                  className={`w-full inline-flex items-center gap-2 pl-9 pr-3 py-1.5 rounded-md text-xs transition ${
                    isSubActive
                      ? 'bg-amber-500/15 text-amber-200 font-medium'
                      : 'text-white/55 hover:text-white hover:bg-white/[0.04]'
                  }`}
                >
                  {SubIcon && <SubIcon className="h-3 w-3 opacity-70" />}
                  <span className="truncate">{sub.label}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </li>
  );
}

// ─── NavButton ────────────────────────────────────────────────────────────
// The top-level tab button with two visual modes. Collapsed mode uses a
// custom hover tooltip (we can't use `title="…"` because browser tooltips
// have a long delay and inconsistent styling — we render our own).

function NavButton({ onClick, active, collapsed, icon: Icon, label, trailing }) {
  const [hovering, setHovering] = useState(false);
  const buttonRef = useRef(null);

  // Auto-hide tooltip if the sidebar expands mid-hover.
  useEffect(() => {
    if (!collapsed) setHovering(false);
  }, [collapsed]);

  const baseCls = active
    ? 'bg-gradient-to-r from-amber-500 to-orange-500 text-white shadow-sm'
    : 'text-white/60 hover:text-white hover:bg-white/[0.05]';

  return (
    <div
      className="relative"
      onMouseEnter={() => collapsed && setHovering(true)}
      onMouseLeave={() => setHovering(false)}
    >
      <button
        ref={buttonRef}
        type="button"
        onClick={onClick}
        className={`w-full inline-flex items-center gap-2.5 rounded-md py-2 text-sm font-medium transition ${
          collapsed ? 'justify-center px-0' : 'px-3'
        } ${baseCls}`}
      >
        {Icon && <Icon className={`shrink-0 ${collapsed ? 'h-4 w-4' : 'h-4 w-4'}`} />}
        {!collapsed && <span className="flex-1 text-left truncate">{label}</span>}
        {!collapsed && trailing}
      </button>

      {/* Hover tooltip when collapsed — renders to the right of the icon */}
      {collapsed && hovering && (
        <div
          role="tooltip"
          className="absolute left-full top-1/2 -translate-y-1/2 ml-2 z-30 pointer-events-none whitespace-nowrap rounded-md border border-white/10 bg-[#161630] px-2.5 py-1.5 text-xs text-white/90 shadow-lg"
        >
          {label}
        </div>
      )}
    </div>
  );
}
