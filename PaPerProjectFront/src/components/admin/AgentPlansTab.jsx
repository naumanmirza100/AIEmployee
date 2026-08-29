// Admin → "Agent Plans" tab.
//
// Every agent has exactly two plans: Monthly and Yearly. The admin sets the price
// of each and can turn either one off. There is no duration any more — Stripe bills
// on the interval and the subscription runs until cancelled, so "how many days" is
// not something the customer buys. Several monthly plans at different durations
// were the same subscription at different prices, wearing labels that misdescribed
// the charge (a "6 months / $9000" plan billed $9000 EVERY month).
//
// Prices are edited locally and committed with Save. They are deliberately NOT
// saved per keystroke: a save mints a new Stripe Price, so typing "99" used to
// create one Price for "9" and another for "99".

import React, { useState, useEffect, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { useToast } from '@/components/ui/use-toast';
import {
  BrainCircuit, DollarSign, Loader2, Save, Search, Calendar, CalendarDays,
} from 'lucide-react';
import adminApiKeysService from '@/services/adminApiKeysService';

const INTERVALS = [
  { key: 'month', label: 'Monthly', suffix: '/month', icon: Calendar },
  { key: 'year', label: 'Yearly', suffix: '/year', icon: CalendarDays },
];

// One editable row per interval, whether or not a plan row exists yet server-side.
const toRows = (plansForAgent = []) =>
  INTERVALS.map(({ key }) => {
    const found = plansForAgent.find((p) => (p.billing_interval || 'month') === key);
    return {
      billing_interval: key,
      price: found ? String(found.price ?? '') : '',
      is_active: found ? found.is_active !== false : false,
      exists: Boolean(found),
    };
  });

export const AgentPlansTab = ({ agents = [], loading: agentsLoading = false }) => {
  const { toast } = useToast();
  // { [agentValue]: [ {billing_interval, price, is_active, exists} x2 ] }
  const [rows, setRows] = useState({});
  const [saved, setSaved] = useState({});   // last-committed copy, for dirty checks
  const [loading, setLoading] = useState(true);
  const [savingAgent, setSavingAgent] = useState(null);
  const [search, setSearch] = useState('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const res = await adminApiKeysService.listAgentPlans();
        const grouped = {};
        for (const p of (res?.plans || [])) {
          (grouped[p.agent_name] = grouped[p.agent_name] || []).push({
            price: p.price_usd,
            is_active: p.is_active,
            billing_interval: p.billing_interval || 'month',
          });
        }
        const built = {};
        for (const agent of Object.keys(grouped)) built[agent] = toRows(grouped[agent]);
        if (!cancelled) { setRows(built); setSaved(built); }
      } catch {
        if (!cancelled) { setRows({}); setSaved({}); }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const rowsFor = (agentValue) => rows[agentValue] || toRows([]);

  const patchRow = (agentValue, interval, patch) => {
    setRows((prev) => {
      const current = prev[agentValue] || toRows([]);
      return {
        ...prev,
        [agentValue]: current.map((r) =>
          r.billing_interval === interval ? { ...r, ...patch } : r
        ),
      };
    });
  };

  const isDirty = (agentValue) =>
    JSON.stringify(rowsFor(agentValue)) !== JSON.stringify(saved[agentValue] || toRows([]));

  const saveAgent = async (agentValue) => {
    const current = rowsFor(agentValue);

    // Only enabled rows are sent. An interval the admin switched off is simply
    // absent from the payload, and the backend deletes that row for us.
    const enabled = current.filter((r) => r.is_active);
    for (const r of enabled) {
      const price = Number(r.price);
      if (!Number.isFinite(price) || price <= 0) {
        toast({
          title: 'Enter a valid price',
          description: `The ${r.billing_interval === 'year' ? 'yearly' : 'monthly'} price must be greater than 0. `
            + 'A $0 recurring plan renews forever without ever charging.',
          variant: 'destructive',
        });
        return;
      }
    }

    setSavingAgent(agentValue);
    try {
      const payload = enabled.map((r, i) => ({
        billing_interval: r.billing_interval,
        price_usd: Number(r.price),
        is_active: true,
        sort_order: i,
      }));
      const res = await adminApiKeysService.saveAgentPlans(agentValue, payload);
      const next = toRows(
        (res?.plans || []).map((p) => ({
          price: p.price_usd,
          is_active: p.is_active,
          billing_interval: p.billing_interval || 'month',
        }))
      );
      setRows((prev) => ({ ...prev, [agentValue]: next }));
      setSaved((prev) => ({ ...prev, [agentValue]: next }));
      toast({
        title: 'Plans saved',
        description: 'Stripe prices updated. Existing subscribers keep the price they signed up at.',
      });
    } catch (e) {
      toast({
        title: 'Could not save plans',
        description: e?.message || 'Please try again.',
        variant: 'destructive',
      });
    } finally {
      setSavingAgent(null);
    }
  };

  const filteredAgents = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return agents;
    return agents.filter((a) =>
      [a.label, a.name, a.description].some((v) => (v || '').toLowerCase().includes(q))
    );
  }, [agents, search]);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BrainCircuit className="h-5 w-5 text-primary" />
            Agent Subscription Plans
          </CardTitle>
          <CardDescription>
            Each agent can be sold monthly, yearly, or both. Set the price for each and
            switch off any you don&apos;t want to offer. Changing a price creates a new
            Stripe price for new subscribers — existing customers keep the price they
            signed up at.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="relative max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search agents…"
              className="pl-9"
            />
          </div>
        </CardContent>
      </Card>

      {loading || agentsLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      ) : filteredAgents.length === 0 ? (
        <div className="text-center py-12">
          <BrainCircuit className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
          <p className="text-lg font-medium">No agents found</p>
          <p className="text-sm text-muted-foreground mt-2">
            {search ? 'Try a different search term.' : 'No agents are configured yet.'}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredAgents.map((agent) => {
            const agentRows = rowsFor(agent.value);
            const activeCount = agentRows.filter((r) => r.is_active).length;
            const dirty = isDirty(agent.value);
            const busy = savingAgent === agent.value;

            return (
              <Card key={agent.value}>
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div className="min-w-0">
                      <CardTitle className="text-base">{agent.label || agent.name}</CardTitle>
                      {agent.description && (
                        <CardDescription className="mt-1 line-clamp-2 max-w-xl">
                          {agent.description}
                        </CardDescription>
                      )}
                    </div>
                    <Badge variant={activeCount ? 'secondary' : 'outline'} className="shrink-0">
                      {activeCount === 0
                        ? 'Not for sale'
                        : `${activeCount} plan${activeCount === 1 ? '' : 's'} live`}
                    </Badge>
                  </div>
                </CardHeader>

                <CardContent className="space-y-3">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {agentRows.map((row) => {
                      const meta = INTERVALS.find((i) => i.key === row.billing_interval);
                      const Icon = meta.icon;
                      return (
                        <div
                          key={row.billing_interval}
                          className={`border rounded-lg p-3 transition-opacity ${row.is_active ? '' : 'opacity-60'}`}
                        >
                          <div className="flex items-center justify-between gap-2 mb-2">
                            <div className="flex items-center gap-1.5 text-sm font-medium">
                              <Icon className="h-3.5 w-3.5 text-muted-foreground" />
                              {meta.label}
                            </div>
                            <Switch
                              checked={row.is_active}
                              onCheckedChange={(v) =>
                                patchRow(agent.value, row.billing_interval, { is_active: v })
                              }
                              aria-label={`Offer ${meta.label} plan`}
                            />
                          </div>
                          <Label className="text-xs text-muted-foreground">Price (USD)</Label>
                          <div className="relative mt-1">
                            <DollarSign className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                            <Input
                              type="number"
                              min="0"
                              step="0.01"
                              value={row.price}
                              disabled={!row.is_active}
                              onChange={(e) =>
                                patchRow(agent.value, row.billing_interval, { price: e.target.value })
                              }
                              placeholder="0.00"
                              className="pl-7 h-9"
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">
                              {meta.suffix}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  <div className="flex items-center justify-end gap-2 pt-1">
                    {dirty && !busy && (
                      <span className="text-xs text-amber-500">Unsaved changes</span>
                    )}
                    <Button
                      size="sm"
                      onClick={() => saveAgent(agent.value)}
                      disabled={!dirty || busy}
                      className="gap-1.5"
                    >
                      {busy ? (
                        <><Loader2 className="h-4 w-4 animate-spin" /> Saving…</>
                      ) : (
                        <><Save className="h-4 w-4" /> Save</>
                      )}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default AgentPlansTab;
