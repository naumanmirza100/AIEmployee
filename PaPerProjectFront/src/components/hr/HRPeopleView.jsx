import React from 'react';
import { Users } from 'lucide-react';
import { SubTabsShell, SubTabClickThrough, TabsContent } from './HRSubTabs';
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
      {/* Internal sub-tab bar removed — users navigate via the global
          AgentSidebar which has Employees + My team + Org chart as sub-items. */}

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
