import React, { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ArrowRight } from 'lucide-react';

/**
 * HRSubTabs — small reusable primitives for the new consolidated HR Views
 * (People / Knowledge / Operations). Mirror of FrontlineSubTabs but with
 * HR's violet-fuchsia theme instead of Frontline's amber.
 */

export function SubTabsShell({ values, defaultValue, activeSubTab, onSubTabChange, children }) {
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
        ? { background: 'linear-gradient(90deg, #8b5cf6 0%, #d946ef 100%)', color: '#fff', borderColor: 'transparent' }
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
// for Documents/Employees/Workflows hasn't been extracted yet.
export function SubTabClickThrough({ icon: Icon = ArrowRight, title, subtitle, hint, onOpen }) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onOpen && onOpen(); }}
      className="rounded-2xl border border-violet-400/25 bg-gradient-to-br from-violet-500/[0.06] to-fuchsia-500/[0.04] p-8 md:p-10 cursor-pointer hover:border-violet-400/40 transition-colors"
    >
      <div className="flex items-start gap-4 max-w-2xl">
        <div
          className="rounded-xl h-14 w-14 flex items-center justify-center shrink-0"
          style={{
            background: 'linear-gradient(135deg, rgba(139,92,246,0.22), rgba(217,70,239,0.12))',
            boxShadow: '0 0 20px rgba(139,92,246,0.15)',
          }}
        >
          <Icon className="h-7 w-7 text-violet-300" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-lg md:text-xl font-semibold text-white">{title}</h3>
            <ArrowRight className="h-4 w-4 text-white/40" />
          </div>
          {subtitle && <p className="text-white/60 mt-1.5 text-sm leading-relaxed">{subtitle}</p>}
          {hint && <p className="text-white/40 mt-3 text-xs">{hint}</p>}
        </div>
      </div>
    </div>
  );
}

export { TabsContent, TabsList } from '@/components/ui/tabs';
