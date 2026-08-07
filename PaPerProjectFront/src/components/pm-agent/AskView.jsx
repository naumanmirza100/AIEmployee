import React, { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Target, MessageSquare } from 'lucide-react';
import ProjectPilotAgent from './ProjectPilotAgent';
import KnowledgeQAAgent from './KnowledgeQAAgent';

// AskView — the top-level "Ask" tab body. Groups the two conversational
// surfaces (Project Pilot for actions, Knowledge Q&A for grounded lookups)
// under one tab so users don't have to hunt for Q&A after the PM UX
// consolidation. Nested sub-tabs mirror the pattern used by Tasks and
// Insights so the whole dashboard reads uniformly.
//
// Pilot is the default sub-tab because it's what the vast majority of
// user intents map to (create / update / analyze). KQA is one click away
// when someone specifically wants to look something up.
// Valid sub-tab values so an out-of-band `?sub=…` doesn't render a blank
// panel (which is what shadcn does when `value` doesn't match any content).
const ASK_SUB_VALUES = ['pilot', 'kqa'];
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
        <TabsList className="inline-flex h-auto p-1 gap-1 rounded-lg bg-[#1a1333] border border-[#3a295a]">
          <SubTabTrigger value="pilot" active={active} icon={Target} label="Project Pilot" />
          <SubTabTrigger value="kqa" active={active} icon={MessageSquare} label="Knowledge Q&A" />
        </TabsList>

        {/* Both sub-tabs mount their component. shadcn's TabsContent hides
            inactive panels via CSS, which keeps conversation state (chat
            history, selected chat, in-progress draft) intact when the user
            flips back and forth between Pilot and KQA. */}
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
      </Tabs>
    </div>
  );
}

function SubTabTrigger({ value, active, icon: Icon, label }) {
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
