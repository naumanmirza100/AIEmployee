import React from 'react';
import { GitBranch, Bell } from 'lucide-react';
import { SubTabsShell, SubTabTrigger, TabsContent, TabsList } from './FrontlineSubTabs';
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
      <TabsList className="inline-flex h-auto p-1 gap-1 rounded-lg bg-[#1a1333] border border-[#3a295a]">
        <SubTabTrigger value="workflows"     active={activeSubTab || 'workflows'} icon={GitBranch} label="Workflows" />
        <SubTabTrigger value="notifications" active={activeSubTab || 'workflows'} icon={Bell}      label="Notifications" />
      </TabsList>

      <TabsContent value="workflows" className="mt-6">
        <FrontlineWorkflowsTab />
      </TabsContent>

      <TabsContent value="notifications" className="mt-6">
        <FrontlineNotificationsTab />
      </TabsContent>
    </SubTabsShell>
  );
}
