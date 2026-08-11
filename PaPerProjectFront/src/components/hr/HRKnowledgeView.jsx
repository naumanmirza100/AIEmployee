import React from 'react';
import { FileText } from 'lucide-react';
import { SubTabsShell, SubTabClickThrough, TabsContent } from './HRSubTabs';
import HRKnowledgeQAAgent from './HRKnowledgeQAAgent';

/**
 * HRKnowledgeView — Knowledge tab body: [Documents | Q&A] sub-tabs.
 *
 * Q&A renders the existing HRKnowledgeQAAgent standalone component inline
 * — no extraction needed. Documents is still hosted by the hidden legacy
 * `?tab=documents` view; the Documents sub-tab shows a hand-off card that
 * jumps there in one click. Full inline extraction of the ~394-line
 * Documents JSX is deferred (needs a big prop bundle for 5 modal dialogs).
 */
export default function HRKnowledgeView({ activeSubTab, onSubTabChange, onNavigateToTab, onGoToDocuments }) {
  const active = activeSubTab || 'qa';
  return (
    <SubTabsShell
      values={['documents', 'qa']}
      defaultValue="qa"
      activeSubTab={activeSubTab}
      onSubTabChange={onSubTabChange}
    >
      {/* Internal sub-tab bar removed — users navigate via the global
          AgentSidebar which has Documents + Q&A as sub-items. */}

      <TabsContent value="documents" className="mt-6">
        <SubTabClickThrough
          icon={FileText}
          title="Open Documents"
          subtitle="Card grid of all HR documents: upload, summarize, extract fields, mark outdated, re-ingest, version history, access log, delete. Five modal dialogs attached."
          hint="Inline extraction coming in a follow-up chunk — for now this opens the standalone Documents view where the full experience still works."
          onOpen={() => onNavigateToTab && onNavigateToTab('documents')}
        />
      </TabsContent>

      <TabsContent value="qa" className="mt-6">
        <HRKnowledgeQAAgent onGoToDocuments={onGoToDocuments} />
      </TabsContent>
    </SubTabsShell>
  );
}
