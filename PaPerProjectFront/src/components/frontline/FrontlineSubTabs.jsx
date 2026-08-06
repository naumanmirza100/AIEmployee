import React, { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ArrowRight } from 'lucide-react';

/**
 * Small reusable primitives for the new consolidated Views (Queue, Insights,
 * Automation, Settings). Extracted so QueueView / InsightsView / etc. can
 * share the same amber-active-pill styling without each file redefining it.
 *
 * `SubTabsShell` — nested Tabs container with URL sub-tab state hookup.
 * `SubTabTrigger` — one amber-pill tab trigger.
 * `SubTabClickThrough` — big hero card that jumps to a legacy hidden tab
 *   (used until we extract Tickets and Widget inline).
 */

export function SubTabsShell({
  values,          // array of valid sub-tab string values
  defaultValue,    // sub-tab to fall back to when the URL has no `sub`
  activeSubTab,
  onSubTabChange,
  children,
}) {
  const [localActive, setLocalActive] = useState(defaultValue);
  const active = values.includes(activeSubTab)
    ? activeSubTab
    : (onSubTabChange ? defaultValue : localActive);
  const setActive = (v) => (onSubTabChange ? onSubTabChange(v) : setLocalActive(v));
  return (
    <Tabs value={active} onValueChange={setActive} className="w-full">
      {children}
    </Tabs>
  );
}

export function SubTabTrigger({ value, active, icon: Icon, label }) {
  const isActive = value === active;
  return (
    <TabsTrigger
      value={value}
      className="relative whitespace-nowrap shrink-0 px-3.5 py-1.5 text-sm font-medium rounded-md border transition-all duration-150"
      style={isActive
        ? { background: 'linear-gradient(90deg, #f59e0b 0%, #f97316 100%)', color: '#fff', borderColor: 'transparent' }
        : { background: 'transparent', color: 'rgba(255,255,255,0.55)', borderColor: 'transparent' }}
    >
      <span className="inline-flex items-center gap-1.5">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </span>
    </TabsTrigger>
  );
}

// Hero card that jumps to a hidden legacy tab. Used while the inline JSX
// for that tab is still not extracted (Tickets in Queue, Widget in Settings).
// Same visual language as PMEmptyState so both agents feel consistent.
export function SubTabClickThrough({ icon: Icon = ArrowRight, title, subtitle, hint, onOpen }) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onOpen && onOpen(); }}
      className="rounded-2xl border border-cyan-400/25 bg-gradient-to-br from-cyan-500/[0.06] to-violet-500/[0.04] p-8 md:p-10 cursor-pointer hover:border-cyan-400/40 transition-colors"
    >
      <div className="flex items-start gap-4 max-w-2xl">
        <div
          className="rounded-xl h-14 w-14 flex items-center justify-center shrink-0"
          style={{
            background: 'linear-gradient(135deg, rgba(6,182,212,0.18), rgba(139,92,246,0.12))',
            boxShadow: '0 0 20px rgba(6,182,212,0.15)',
          }}
        >
          <Icon className="h-7 w-7 text-cyan-300" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-lg md:text-xl font-semibold text-white">{title}</h3>
            <ArrowRight className="h-4 w-4 text-white/40" />
          </div>
          {subtitle && (
            <p className="text-white/60 mt-1.5 text-sm leading-relaxed">{subtitle}</p>
          )}
          {hint && <p className="text-white/40 mt-3 text-xs">{hint}</p>}
        </div>
      </div>
    </div>
  );
}

// Re-export TabsContent from the same primitives so consumers only import
// from this file, not from two places.
export { TabsContent, TabsList } from '@/components/ui/tabs';
