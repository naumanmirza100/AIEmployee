import React from 'react';
import { GitBranch, ClipboardList, AlertTriangle } from 'lucide-react';
import { SubTabsShell, SubTabTrigger, SubTabClickThrough, TabsContent, TabsList } from './HRSubTabs';
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
      <TabsList className="inline-flex h-auto p-1 gap-1 rounded-lg bg-[#1a1333] border border-[#3a295a]">
        <SubTabTrigger value="workflows"     active={active} icon={GitBranch}      label="Workflows" />
        <SubTabTrigger value="leave"         active={active} icon={ClipboardList}  label="Leave" />
        <SubTabTrigger value="notifications" active={active} icon={AlertTriangle}  label="Notifications" />
      </TabsList>

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
