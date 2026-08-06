import React from 'react';
import { Card } from '@/components/ui/card';
import { ArrowRight } from 'lucide-react';

/**
 * FrontlinePlaceholderView — Chunk A scaffolding for the new consolidated
 * tabs (Queue / Knowledge / Insights / Automation / Settings).
 *
 * The tab bar has been restructured but the legacy tab content still lives
 * in FrontlineDashboard.jsx (hidden from the visible bar but URL-reachable).
 * Rather than block Chunk A on the full extraction of ~2400 lines of inline
 * tab code, each new view renders this placeholder — one big card per legacy
 * tab that lives inside it, with a click-to-open button that sets the tab
 * to the hidden legacy value. Users get the full feature in one click.
 *
 * In Chunks B–F we replace these placeholders with real nested sub-tabs
 * that host the extracted content directly.
 */
export default function FrontlinePlaceholderView({ title, subtitle, jumps = [], onNavigateToTab }) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-white">{title}</h2>
        {subtitle && <p className="text-sm text-white/55 mt-1">{subtitle}</p>}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {jumps.map((jump) => {
          const Icon = jump.icon;
          return (
            <Card
              key={jump.tab}
              className="border-white/[0.06] bg-white/[0.03] p-5 hover:border-cyan-400/30 transition-colors cursor-pointer"
              onClick={() => onNavigateToTab && onNavigateToTab(jump.tab)}
            >
              <div className="flex items-start gap-3">
                {Icon && (
                  <div className="rounded-lg p-2.5 shrink-0" style={{ backgroundColor: jump.bgColor || 'rgba(96,165,250,0.15)' }}>
                    <Icon className="h-5 w-5" style={{ color: jump.color || '#60a5fa' }} />
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="font-semibold text-sm text-white">{jump.label}</h3>
                    <ArrowRight className="h-4 w-4 text-white/40 shrink-0" />
                  </div>
                  {jump.desc && (
                    <p className="text-xs text-white/45 mt-1 leading-relaxed">{jump.desc}</p>
                  )}
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      <p className="text-xs text-white/40 italic">
        Sub-tabs will land here in the next chunk. For now these open the underlying tabs directly.
      </p>
    </div>
  );
}
