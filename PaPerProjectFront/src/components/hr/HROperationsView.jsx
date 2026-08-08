import React from 'react';
import { GitBranch } from 'lucide-react';
import { SubTabsShell, SubTabClickThrough, TabsContent } from './HRSubTabs';
import HRLeaveTab from './HRLeaveTab';
import HRNotificationsTab from './HRNotificationsTab';

/**
 * HROperationsView — Operations tab body:
 *   [Workflows | Leave | Notifications] sub-tabs.
 *
 * Leave and Notifications render existing standalone components inline.
 * Workflows is still hosted by the hidden legacy `?tab=workflows` view;
 * the sub-tab shows a hand-off card that jumps there. Full inline
 * extraction of the ~385-line Workflows JSX (with 4 modal dialogs) is
 * deferred.
 */
export default function HROperationsView({ activeSubTab, onSubTabChange, onNavigateToTab }) {
  const active = activeSubTab || 'workflows';
  return (
    <SubTabsShell
      values={['workflows', 'leave', 'notifications']}
      defaultValue="workflows"
      activeSubTab={activeSubTab}
      onSubTabChange={onSubTabChange}
    >
      {/* Internal sub-tab bar removed — users navigate via the global
          AgentSidebar which has Workflows + Leave + Notifications as sub-items. */}

      <TabsContent value="workflows" className="mt-6">
        <SubTabClickThrough
          icon={GitBranch}
          title="Open Workflows"
          subtitle="HR SOP workflows: onboarding, offboarding, approvals. Trigger-based automation with a step builder, dry-run, and run history including approve/reject on paused executions. Four modal dialogs attached."
          hint="Inline extraction coming in a follow-up chunk — for now this opens the standalone Workflows view."
          onOpen={() => onNavigateToTab && onNavigateToTab('workflows')}
        />
      </TabsContent>

      <TabsContent value="leave" className="mt-6">
        <HRLeaveTab />
      </TabsContent>

      <TabsContent value="notifications" className="mt-6">
        <HRNotificationsTab />
      </TabsContent>
    </SubTabsShell>
  );
}
