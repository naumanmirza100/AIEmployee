import React, { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { FileText, MessageSquare } from 'lucide-react';
import FrontlineDocumentsTab from './FrontlineDocumentsTab';
import FrontlineKnowledgeQATab from './FrontlineKnowledgeQATab';

// Sub-tab values live in the URL as `?sub=…` so the sidebar and view stay
// in lockstep and deep-links work.
const KNOWLEDGE_SUB_VALUES = ['documents', 'qa'];
const KNOWLEDGE_DEFAULT_SUB = 'documents';

/**
 * KnowledgeView — the Knowledge tab body.
 *
 * Documents AND Knowledge Q&A are now both fully extracted and render
 * inline as sub-tabs. Swapping between them keeps the URL on
 * `?tab=knowledge&sub=…` so the sidebar highlight stays coherent and
 * bookmarks work.
 *
 * Q&A takes A LOT of props because its whole 720-line UI is stateful
 * and the state must stay in the parent (chat history, streaming buffer,
 * scope picker, feedback) — mirrors the arrangement Documents uses,
 * just with more surface.
 */
export default function KnowledgeView({
  // Documents props
  documents,
  docSummaries,
  onOpenUpload,
  onToggleSummary,
  onSummarize,
  onExtract,
  onToggleOutdated,
  onDelete,
  // QA props — everything passed straight through; see FrontlineKnowledgeQATab.
  qa,
  // Navigation
  onNavigateToTab,
  activeSubTab,
  onSubTabChange,
}) {
  // Fall back to local state when parent isn't controlling us (rare — the
  // dashboard passes ?sub= through so the sidebar highlights correctly).
  const [localActive, setLocalActive] = useState(KNOWLEDGE_DEFAULT_SUB);
  const active = KNOWLEDGE_SUB_VALUES.includes(activeSubTab)
    ? activeSubTab
    : (onSubTabChange ? KNOWLEDGE_DEFAULT_SUB : localActive);
  const setActive = (v) => (onSubTabChange ? onSubTabChange(v) : setLocalActive(v));

  return (
    <div className="space-y-6">
      <Tabs value={active} onValueChange={setActive} className="w-full">
        <TabsList className="inline-flex h-auto p-1 gap-1 rounded-lg bg-[#1a1333] border border-[#3a295a]">
          <SubTabTrigger value="documents" active={active} icon={FileText} label="Documents" />
          <SubTabTrigger value="qa" active={active} icon={MessageSquare} label="Knowledge Q&A" />
        </TabsList>

        <TabsContent value="documents" className="mt-6">
          <FrontlineDocumentsTab
            documents={documents}
            docSummaries={docSummaries}
            onOpenUpload={onOpenUpload}
            onToggleSummary={onToggleSummary}
            onSummarize={onSummarize}
            onExtract={onExtract}
            onToggleOutdated={onToggleOutdated}
            onDelete={onDelete}
          />
        </TabsContent>

        <TabsContent value="qa" className="mt-6">
          <FrontlineKnowledgeQATab {...qa} />
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
