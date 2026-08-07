import React from 'react';
import { Headphones, Ticket } from 'lucide-react';
import { SubTabsShell, SubTabClickThrough, TabsContent } from './FrontlineSubTabs';
import { HandoffQueueTab } from './FrontlineDashboard';

/**
 * QueueView — Queue tab body: [Hand-offs | Tickets] sub-tabs.
 *
 * Hand-offs renders the existing HandoffQueueTab component inline (it was
 * already a self-contained top-level function — no extraction needed, just
 * exported from FrontlineDashboard).
 *
 * Tickets is still hosted by the hidden legacy `?tab=tickets` view; the
 * Tickets sub-tab shows a hand-off card that jumps there in one click.
 * Full inline extraction of the ~275-line Tickets JSX is deferred — same
 * pattern KnowledgeView used for QA before its extraction landed.
 */
export default function QueueView({ activeSubTab, onSubTabChange, onNavigateToTab }) {
  return (
    <SubTabsShell
      values={['handoffs', 'tickets']}
      defaultValue="handoffs"
      activeSubTab={activeSubTab}
      onSubTabChange={onSubTabChange}
    >
      {/* Internal sub-tab bar removed — users navigate via the global
          AgentSidebar which has Hand-offs + Tickets as sub-items. */}

      <TabsContent value="handoffs" className="mt-6">
        <HandoffQueueTab />
      </TabsContent>

      <TabsContent value="tickets" className="mt-6">
        <SubTabClickThrough
          icon={Ticket}
          title="Open Tickets"
          subtitle="Full 9-column ticket table with filters (status / priority / category / date), bulk actions, and per-row actions (customer 360, notes, snooze, SLA pause, re-triage)."
          hint="Inline extraction coming in a follow-up chunk — for now this opens the standalone Tickets view where the full experience still works."
          onOpen={() => onNavigateToTab && onNavigateToTab('tickets')}
        />
      </TabsContent>
    </SubTabsShell>
  );
}
