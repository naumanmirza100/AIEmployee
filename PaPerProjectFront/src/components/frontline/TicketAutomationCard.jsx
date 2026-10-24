// "Ticket automation" on Frontline's Chat widget tab: what Frontline does by itself with a ticket a customer opens
// (chat hand-off, web form, email). Both switches start off; only an admin can change them.
//
// - Classify incoming tickets: the triage staff tickets and Re-triage use sets category and priority.
// - Answer from the knowledge base: a web-form or email ticket it is sure about gets the answer by email and is
//   marked auto-resolved; the customer's reply reopens it. A chat hand-off is never answered this way.

import React, { useState } from 'react';
import { Loader2, Wand2 } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { useToast } from '@/components/ui/use-toast';
import frontlineAgentService from '@/services/frontlineAgentService';

const SWITCHES = [
  {
    key: 'classify_incoming',
    label: 'Classify incoming tickets automatically',
    help: 'Sets the category and priority of each new customer ticket, the way Re-triage does. The SLA deadline follows the priority.',
  },
  {
    key: 'resolve_from_knowledge',
    label: 'Answer simple tickets from the knowledge base',
    help: 'When a web-form or email ticket is answered by your documents with high confidence, the answer is emailed to the customer and the ticket is marked auto-resolved. Their reply reopens it. Chat hand-offs always go to a person.',
  },
];

export const TicketAutomationCard = ({ value, onChange }) => {
  const { toast } = useToast();
  const [saving, setSaving] = useState(null);
  const current = { classify_incoming: false, resolve_from_knowledge: false, ...(value || {}) };

  const toggle = async (key, on) => {
    const next = { ...current, [key]: on };
    setSaving(key);
    try {
      const res = await frontlineAgentService.updateFrontlineWidgetConfig({ config: { ticket_automation: next } });
      if (res?.status !== 'success') throw new Error(res?.message || 'Save failed');
      onChange?.(res?.data?.config?.ticket_automation || next);
      toast({ title: on ? 'Turned on' : 'Turned off', description: SWITCHES.find((s) => s.key === key)?.label });
    } catch (e) {
      toast({ title: 'Could not save', description: e?.message || 'Only an admin can change this.', variant: 'destructive' });
    } finally {
      setSaving(null);
    }
  };

  return (
    <Card className="w-full min-w-0" data-testid="FL-ticket-automation">
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Wand2 className="h-5 w-5" /> Ticket automation</CardTitle>
        <CardDescription>What Frontline does by itself with tickets your customers open. Both are off until you turn them on.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {value === null ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading...</div>
        ) : SWITCHES.map((s) => (
          <div key={s.key} className="flex items-start justify-between gap-4 rounded-lg border border-border p-3">
            <div className="min-w-0">
              <p className="text-sm font-medium text-foreground">{s.label}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">{s.help}</p>
            </div>
            <div className="flex shrink-0 items-center gap-2 pt-0.5">
              {saving === s.key && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
              <Switch
                checked={!!current[s.key]}
                disabled={!!saving}
                onCheckedChange={(on) => toggle(s.key, on)}
                aria-label={s.label}
                data-testid={`FL-ticket-automation-${s.key}`}
              />
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
};

export default TicketAutomationCard;
