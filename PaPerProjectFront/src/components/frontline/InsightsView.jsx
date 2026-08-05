import React from 'react';
import { BarChart3, Sparkles } from 'lucide-react';
import { SubTabsShell, SubTabTrigger, TabsContent, TabsList } from './FrontlineSubTabs';
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
      <TabsList className="inline-flex h-auto p-1 gap-1 rounded-lg bg-[#1a1333] border border-[#3a295a]">
        <SubTabTrigger value="analytics" active={activeSubTab || 'analytics'} icon={BarChart3} label="Analytics" />
        <SubTabTrigger value="ai-graphs" active={activeSubTab || 'analytics'} icon={Sparkles}   label="AI Graphs" />
      </TabsList>

      <TabsContent value="analytics" className="mt-6">
        <FrontlineAnalyticsTab />
      </TabsContent>

      <TabsContent value="ai-graphs" className="mt-6">
        <FrontlineAIGraphs />
      </TabsContent>
    </SubTabsShell>
  );
}
