import React, { useState } from 'react';
import { Tabs, TabsContent } from '@/components/ui/tabs';
import ProjectPilotAgent from './ProjectPilotAgent';
import KnowledgeQAAgent from './KnowledgeQAAgent';
import MeetingScheduler from './MeetingScheduler';

// AskView — the top-level "Ask" tab body. Groups the THREE conversational
// surfaces under one tab so users don't have to hunt for them after the PM
// UX consolidation:
//   • Project Pilot   — natural-language project & task management (actions)
//   • Knowledge Q&A   — grounded lookups over your project data
//   • Meeting Scheduler — schedule meetings via chat + browse meetings list
//
// Nested sub-tabs mirror the pattern used by Tasks and Insights so the
// whole dashboard reads uniformly.
//
// Pilot is the default sub-tab because it's what the vast majority of
// user intents map to (create / update / analyze).
// Valid sub-tab values so an out-of-band `?sub=…` doesn't render a blank
// panel (which is what shadcn does when `value` doesn't match any content).
const ASK_SUB_VALUES = ['pilot', 'kqa', 'meetings'];
const ASK_DEFAULT_SUB = 'pilot';

export default function AskView({
  projects,
  onProjectUpdate,
  onNavigate,
  onOpenPilot,
  activeSubTab,       // optional controlled value from parent (sidebar-driven)
  onSubTabChange,     // parent's setter — called when user clicks a sub-tab
}) {
  // Fall back to a local state when the parent doesn't control us. Callers
  // that DO control pass a `sub` param; we normalise to a known value so
  // the tab bar always highlights something.
  const [localActive, setLocalActive] = useState(ASK_DEFAULT_SUB);
  const active = ASK_SUB_VALUES.includes(activeSubTab)
    ? activeSubTab
    : (onSubTabChange ? ASK_DEFAULT_SUB : localActive);
  const setActive = (v) => (onSubTabChange ? onSubTabChange(v) : setLocalActive(v));

  return (
    <div className="space-y-6">
      <Tabs value={active} onValueChange={setActive} className="w-full">
        {/* Internal sub-tab bar removed — users navigate between Pilot /
            KQA / Meetings via the global AgentSidebar. Tabs wrapper kept
            so old `?sub=kqa` / `?sub=meetings` bookmarks still resolve
            to the right pane; only one TabsContent renders at a time. */}
        <TabsContent value="pilot" className="mt-6">
          <ProjectPilotAgent
            projects={projects || []}
            onProjectUpdate={onProjectUpdate}
            onNavigate={onNavigate}
          />
        </TabsContent>
        <TabsContent value="kqa" className="mt-6">
          <KnowledgeQAAgent projects={projects || []} onOpenPilot={onOpenPilot} />
        </TabsContent>
        <TabsContent value="meetings" className="mt-6">
          <MeetingScheduler />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// SubTabTrigger removed — internal sub-tab bar no longer rendered.
