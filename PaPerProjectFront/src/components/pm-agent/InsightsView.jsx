import React from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Activity, Calendar as CalendarIcon, Users } from 'lucide-react';
import ProjectHealthDashboard from './ProjectHealthDashboard';
import DailyStandupAgent from './DailyStandupAgent';
import TeamPerformanceDashboard from './TeamPerformanceDashboard';

// Insights tab body (Chunk B of PM_AGENT_UX_REDESIGN.md).
//
// Consolidates the three "report-shaped" sub-tools that previously lived
// inside the AI Tools hub. Each was already fully standalone — this view
// just gives them a shared home with a nested tab bar so users don't have
// to hunt for them inside a hub-of-hubs.
//
// If we add more report-style tools later (retro summaries, velocity charts,
// etc.), just import + append to INSIGHTS_SECTIONS.
const INSIGHTS_SECTIONS = [
  {
    value: 'health',
    label: 'Project Health',
    icon: Activity,
    Component: ProjectHealthDashboard,
    color: '#fb923c',
  },
  {
    value: 'standup',
    label: 'Daily Standup',
    icon: CalendarIcon,
    Component: DailyStandupAgent,
    color: '#f472b6',
  },
  {
    value: 'team',
    label: 'Team Performance',
    icon: Users,
    Component: TeamPerformanceDashboard,
    color: '#22d3ee',
  },
];

const INSIGHTS_VALUES = INSIGHTS_SECTIONS.map((s) => s.value);
const INSIGHTS_DEFAULT = INSIGHTS_SECTIONS[0].value;

export default function InsightsView({ onOpenPilot, activeSubTab, onSubTabChange }) {
  const [localActive, setLocalActive] = React.useState(INSIGHTS_DEFAULT);
  const active = INSIGHTS_VALUES.includes(activeSubTab)
    ? activeSubTab
    : (onSubTabChange ? INSIGHTS_DEFAULT : localActive);
  const setActive = (v) => (onSubTabChange ? onSubTabChange(v) : setLocalActive(v));
  const ActiveComponent = INSIGHTS_SECTIONS.find((s) => s.value === active)?.Component;

  return (
    <div className="space-y-6">
      <Tabs value={active} onValueChange={setActive} className="w-full">
        <TabsList className="inline-flex h-auto p-1 gap-1 rounded-lg bg-[#1a1333] border border-[#3a295a]">
          {INSIGHTS_SECTIONS.map((s) => {
            const Icon = s.icon;
            const isActive = s.value === active;
            return (
              <TabsTrigger
                key={s.value}
                value={s.value}
                className="relative whitespace-nowrap shrink-0 px-3.5 py-1.5 text-sm font-medium rounded-md border transition-all duration-150"
                style={isActive
                  ? {
                      background: 'linear-gradient(90deg, #f59e0b 0%, #f97316 100%)',
                      color: '#fff',
                      borderColor: 'transparent',
                    }
                  : {
                      background: 'transparent',
                      color: 'rgba(255,255,255,0.55)',
                      borderColor: 'transparent',
                    }}
              >
                <span className="inline-flex items-center gap-1.5">
                  <Icon className="h-3.5 w-3.5" style={{ color: isActive ? '#fff' : s.color }} />
                  {s.label}
                </span>
              </TabsTrigger>
            );
          })}
        </TabsList>

        {/* One TabsContent per section so shadcn manages mount/unmount for us.
            Each sub-tool fetches its own project list on mount — mounting only
            the active section keeps unrelated network calls / model loads
            from happening in the background. */}
        {INSIGHTS_SECTIONS.map((s) => {
          const C = s.Component;
          return (
            <TabsContent key={s.value} value={s.value} className="mt-6">
              <C onOpenPilot={onOpenPilot} />
            </TabsContent>
          );
        })}
      </Tabs>
    </div>
  );
}
