import React from 'react';
import { Monitor } from 'lucide-react';
import { SubTabsShell, SubTabClickThrough, TabsContent } from './FrontlineSubTabs';

/**
 * SettingsView — Settings tab body: currently just [Chat widget].
 *
 * Widget is still hosted by the hidden legacy `?tab=widget` view; the sub-tab
 * shows a hand-off card that jumps there. Full inline extraction of the
 * widget config JSX (~180 lines) is deferred — small feature, low priority
 * next to Handoffs and Workflows.
 *
 * Notification preferences (end-user checkboxes) will land here as a second
 * sub-tab once we split them out of FrontlineNotificationsTab in a follow-up.
 */
export default function SettingsView({ activeSubTab, onSubTabChange, onNavigateToTab }) {
  return (
    <SubTabsShell
      values={['widget']}
      defaultValue="widget"
      activeSubTab={activeSubTab}
      onSubTabChange={onSubTabChange}
    >
      {/* Internal sub-tab bar removed — users navigate via the global
          AgentSidebar which has Chat widget as a sub-item. */}

      <TabsContent value="widget" className="mt-6">
        <SubTabClickThrough
          icon={Monitor}
          title="Open Chat widget settings"
          subtitle="Configure the public embeddable widget: widget key, allowed origins, theme knobs, CSS overrides, and copyable embed snippet."
          hint="Inline extraction coming in a follow-up chunk — for now this opens the standalone Widget view."
          onOpen={() => onNavigateToTab && onNavigateToTab('widget')}
        />
      </TabsContent>
    </SubTabsShell>
  );
}
