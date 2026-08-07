import React, { useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight, ChevronDown } from 'lucide-react';

/**
 * FrontlineSidebar — collapsible left rail for the Frontline dashboard.
 *
 * Adapted from `pm-agent/PMSidebar.jsx` with one important behavioural
 * difference: sub-items route to *hidden legacy tabs* during the staged
 * rollout, not to `?sub=` sub-tabs of the parent (Chunk A doesn't yet
 * host the extracted content inside the new views). So the sidebar's
 * active-highlight logic needs to know each sub-item's tab value so it
 * can highlight the correct parent when the user is on a hidden child
 * tab.
 *
 * Structure — the `items` prop:
 *   [{
 *     value: 'queue',
 *     label: 'Queue',
 *     icon: Headphones,
 *     subItems: [
 *       { value: 'handoffs', label: 'Hand-offs', icon: Headphones },
 *       { value: 'tickets',  label: 'Tickets',   icon: Ticket },
 *     ],
 *   }, ...]
 *
 * Clicking a parent → onTabChange(parent.value). Clicking a sub-item →
 * onTabChange(sub.value). A parent is considered "active" when the
 * current activeTab matches the parent's value OR any of its sub-item
 * values — that keeps the correct group open when the user lands on a
 * hidden legacy tab via URL.
 */
export default function FrontlineSidebar({
  items,
  activeTab,
  onTabChange,
  collapsed = false,
  onToggleCollapsed,
}) {
  return (
    <aside
      className={`hidden lg:flex flex-col shrink-0 sticky top-4 self-start rounded-2xl border border-white/[0.06] transition-all duration-200 ${
        collapsed ? 'w-[64px]' : 'w-[220px]'
      }`}
      style={{
        background: 'linear-gradient(180deg, #0d0b1f 0%, #0f0a20 100%)',
        maxHeight: 'calc(100vh - 2rem)',
      }}
    >
      {/* Header — brand label + collapse toggle. Collapsed hides label. */}
      <div className={`flex items-center h-12 ${collapsed ? 'justify-center' : 'justify-between px-3'} border-b border-white/[0.06]`}>
        {!collapsed && (
          <span className="text-xs font-semibold tracking-wider uppercase text-white/45">
            Frontline
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

      <nav className="flex-1 overflow-y-auto py-2">
        <ul className="flex flex-col gap-0.5 px-2">
          {items.map((item) => (
            <SidebarItem
              key={item.value}
              item={item}
              collapsed={collapsed}
              activeTab={activeTab}
              onTabChange={onTabChange}
            />
          ))}
        </ul>
      </nav>
    </aside>
  );
}

// A parent counts as "the current group" if its own value matches activeTab
// or any of its sub-items' values matches. Sub-items only render when the
// group is current AND the sidebar isn't collapsed.
function isParentActive(item, activeTab) {
  if (item.value === activeTab) return true;
  if (!item.subItems) return false;
  return item.subItems.some((s) => s.value === activeTab);
}

function SidebarItem({ item, collapsed, activeTab, onTabChange }) {
  const isActive = isParentActive(item, activeTab);
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

      {hasSubs && isActive && !collapsed && (
        <ul className="mt-0.5 mb-1 flex flex-col gap-0.5">
          {item.subItems.map((sub) => {
            const SubIcon = sub.icon;
            const isSubActive = sub.value === activeTab;
            return (
              <li key={sub.value}>
                <button
                  type="button"
                  onClick={() => onTabChange(sub.value)}
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

function NavButton({ onClick, active, collapsed, icon: Icon, label, trailing }) {
  const [hovering, setHovering] = useState(false);

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
        type="button"
        onClick={onClick}
        className={`w-full inline-flex items-center gap-2.5 rounded-md py-2 text-sm font-medium transition ${
          collapsed ? 'justify-center px-0' : 'px-3'
        } ${baseCls}`}
      >
        {Icon && <Icon className="shrink-0 h-4 w-4" />}
        {!collapsed && <span className="flex-1 text-left truncate">{label}</span>}
        {!collapsed && trailing}
      </button>

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
