import React from 'react';
import { SubTabsShell, TabsContent } from './FrontlineSubTabs';
import { FrontlineWorkflowsTab, FrontlineNotificationsTab } from './FrontlineDashboard';

/**
 * AutomationView — Automation tab body: [Workflows | Notifications] sub-tabs.
 *
 * Both sub-tabs render existing top-level components inline. The
 * FrontlineNotificationsTab currently contains BOTH admin-facing content
 * (templates + scheduled sends) AND end-user preferences (checkboxes) —
 * a follow-up chunk splits preferences out to Settings. For now they
 * live together here under Automation.
 */
export default function AutomationView({ activeSubTab, onSubTabChange }) {
  return (
    <SubTabsShell
      values={['workflows', 'notifications']}
      defaultValue="workflows"
      activeSubTab={activeSubTab}
      onSubTabChange={onSubTabChange}
    >
      {/* Internal sub-tab bar removed — users navigate via the global
          AgentSidebar which has Workflows + Notifications as sub-items. */}

      <TabsContent value="workflows" className="mt-6">
        <FrontlineWorkflowsTab />
      </TabsContent>

      <TabsContent value="notifications" className="mt-6">
        <FrontlineNotificationsTab />
      </TabsContent>
    </SubTabsShell>
  );
}
