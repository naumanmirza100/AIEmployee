import React from 'react';
import { Users, UserCheck, Network } from 'lucide-react';
import { SubTabsShell, SubTabTrigger, SubTabClickThrough, TabsContent, TabsList } from './HRSubTabs';
import HRManagerTeamTab from './HRManagerTeamTab';
import HROrgChartTab from './HROrgChartTab';

/**
 * HRPeopleView — People tab body: [Employees | My team | Org chart] sub-tabs.
 *
 * My team and Org chart render existing standalone components inline. The
 * Employees sub-tab is still hosted by the hidden legacy `?tab=employees`
 * view; the sub-tab shows a hand-off card that jumps there. Full inline
 * extraction of the ~272-line Employees JSX (plus the Departments + Review
 * cycles dialogs) is deferred.
 */
export default function HRPeopleView({ activeSubTab, onSubTabChange, onNavigateToTab, onOpenEmployee }) {
  const active = activeSubTab || 'employees';
  return (
    <SubTabsShell
      values={['employees', 'my_team', 'org_chart']}
      defaultValue="employees"
      activeSubTab={activeSubTab}
      onSubTabChange={onSubTabChange}
    >
      <TabsList className="inline-flex h-auto p-1 gap-1 rounded-lg bg-[#1a1333] border border-[#3a295a]">
        <SubTabTrigger value="employees" active={active} icon={Users}     label="Employees" />
        <SubTabTrigger value="my_team"   active={active} icon={UserCheck} label="My team" />
        <SubTabTrigger value="org_chart" active={active} icon={Network}   label="Org chart" />
      </TabsList>

      <TabsContent value="employees" className="mt-6">
        <SubTabClickThrough
          icon={Users}
          title="Open Employees"
          subtitle="Filterable/searchable employee table with click-to-open profile drawer. Includes hidden Departments manager and Review cycles admin dialogs (reachable from the header)."
          hint="Inline extraction coming in a follow-up chunk — for now this opens the standalone Employees view."
          onOpen={() => onNavigateToTab && onNavigateToTab('employees')}
        />
      </TabsContent>

      <TabsContent value="my_team" className="mt-6">
        <HRManagerTeamTab onOpenEmployee={onOpenEmployee} />
      </TabsContent>

      <TabsContent value="org_chart" className="mt-6">
        <HROrgChartTab onOpenEmployee={onOpenEmployee} />
      </TabsContent>
    </SubTabsShell>
  );
}
