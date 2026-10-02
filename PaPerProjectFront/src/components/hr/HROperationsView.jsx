import React from 'react';
import { SubTabsShell, TabsContent } from './HRSubTabs';
import HRWorkflowsTab from './HRWorkflowsTab';
import HRLeaveTab from './HRLeaveTab';
import HRNotificationsTab from './HRNotificationsTab';

/**
 * HROperationsView — Operations tab body:
 *   [Workflows | Leave | Notifications] sub-tabs.
 *
 * Each sub-tab renders its standalone component inline.
 */
export default function HROperationsView({ activeSubTab, onSubTabChange }) {
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
        <HRWorkflowsTab />
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
