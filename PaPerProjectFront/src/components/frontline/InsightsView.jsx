import React from 'react';
import { SubTabsShell, TabsContent } from './FrontlineSubTabs';
import { FrontlineAnalyticsTab } from './FrontlineDashboard';
import FrontlineAIGraphs from './FrontlineAIGraphs';

/**
 * InsightsView — Insights tab body: [Analytics | AI Graphs] sub-tabs.
 *
 * Overview is intentionally NOT a sub-tab here — it's kept as its own
 * top-level tab (the FrontlineInsightsPanel + Quick-Jump grid lives there).
 * Insights groups the two "look at data" surfaces that don't fit anywhere
 * else: KPI dashboards + AI-generated charts.
 *
 * Both sub-tabs render existing top-level components inline — no extraction
 * work needed.
 */
export default function InsightsView({ activeSubTab, onSubTabChange }) {
  return (
    <SubTabsShell
      values={['analytics', 'ai-graphs']}
      defaultValue="analytics"
      activeSubTab={activeSubTab}
      onSubTabChange={onSubTabChange}
    >
      {/* Internal sub-tab bar removed — users navigate via the global
          AgentSidebar which has Analytics + AI Graphs as sub-items. */}

      <TabsContent value="analytics" className="mt-6">
        <FrontlineAnalyticsTab />
      </TabsContent>

      <TabsContent value="ai-graphs" className="mt-6">
        <FrontlineAIGraphs />
      </TabsContent>
    </SubTabsShell>
  );
}
