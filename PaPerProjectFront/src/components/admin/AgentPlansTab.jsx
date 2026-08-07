// Admin → "Agent Plans" tab.
//
// Frontend-only (no backend yet): the admin defines, per agent, one or more
// subscription plans — a duration (how long a company's purchase stays active)
// and its price. Companies would pick one of these when buying the agent.
//
// Plans are persisted to localStorage keyed by agent so they survive refreshes
// while the backend is still to be built. When the API lands, swap the
// load/save helpers for service calls and the UI stays the same.

import React, { useState, useEffect, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import {
  BrainCircuit, Plus, Trash2, Clock, DollarSign, Loader2, Save, Search,
} from 'lucide-react';

const STORAGE_KEY = 'admin_agent_plans_v1';

// Duration presets the admin can pick from when adding a plan. `days` is the
// canonical value stored; `label` is what the admin/company sees. "Custom"
// lets the admin type an arbitrary number of days.
const DURATION_PRESETS = [
  { value: '30',   label: '1 month (30 days)' },
  { value: '90',   label: '3 months (90 days)' },
  { value: '180',  label: '6 months (180 days)' },
  { value: '365',  label: '1 year (365 days)' },
  { value: 'custom', label: 'Custom…' },
];

const humanizeDays = (days) => {
  const d = Number(days) || 0;
  if (d === 30) return '1 month';
  if (d === 90) return '3 months';
  if (d === 180) return '6 months';
  if (d === 365) return '1 year';
  if (d % 365 === 0) return `${d / 365} years`;
  if (d % 30 === 0) return `${d / 30} months`;
  return `${d} days`;
};

// { [agentValue]: [ { id, days, price, label } ] }
const loadPlans = () => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
};
const savePlans = (plans) => {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(plans)); } catch { /* quota / private mode — non-fatal */ }
};

// Simple incrementing id without Date.now/Math.random dependence issues.
let _idSeq = 1;
const nextId = () => `p${_idSeq++}_${(Object.keys(loadPlans()).length)}`;

export const AgentPlansTab = ({ agents = [], loading = false }) => {
  const { toast } = useToast();
  const [plans, setPlans] = useState({});
  const [search, setSearch] = useState('');

  // Per-agent "add plan" draft state, keyed by agent value.
  const [drafts, setDrafts] = useState({}); // { [agentValue]: { duration, customDays, price } }

  useEffect(() => { setPlans(loadPlans()); }, []);

  const persist = (next) => { setPlans(next); savePlans(next); };

  const draftFor = (agentValue) =>
    drafts[agentValue] || { duration: '30', customDays: '', price: '' };
  const setDraft = (agentValue, patch) =>
    setDrafts((d) => ({ ...d, [agentValue]: { ...draftFor(agentValue), ...patch } }));

  const addPlan = (agentValue) => {
    const d = draftFor(agentValue);
    const days = d.duration === 'custom' ? Number(d.customDays) : Number(d.duration);
    const price = Number(d.price);
    if (!days || days <= 0) {
      toast({ title: 'Enter a valid duration', description: 'Duration must be a positive number of days.', variant: 'destructive' });
      return;
    }
    if (!(price >= 0)) {
      toast({ title: 'Enter a valid price', description: 'Price must be 0 or more.', variant: 'destructive' });
      return;
    }
    const existing = plans[agentValue] || [];
    if (existing.some((p) => Number(p.days) === days)) {
      toast({ title: 'Duplicate plan', description: `A ${humanizeDays(days)} plan already exists for this agent.`, variant: 'destructive' });
      return;
    }
    const plan = { id: nextId(), days, price, label: humanizeDays(days) };
    const next = { ...plans, [agentValue]: [...existing, plan].sort((a, b) => a.days - b.days) };
    persist(next);
    setDraft(agentValue, { duration: '30', customDays: '', price: '' });
    toast({ title: 'Plan added', description: `${humanizeDays(days)} · $${price} added.` });
  };

  const removePlan = (agentValue, planId) => {
    const next = { ...plans, [agentValue]: (plans[agentValue] || []).filter((p) => p.id !== planId) };
    persist(next);
  };

  const updatePlanPrice = (agentValue, planId, price) => {
    const next = {
      ...plans,
      [agentValue]: (plans[agentValue] || []).map((p) => (p.id === planId ? { ...p, price: Number(price) || 0 } : p)),
    };
    persist(next);
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
            For each agent, set the durations a company can buy it for and the price of each.
            These plans are what a company chooses from at purchase.
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

      {loading ? (
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
            const agentPlans = plans[agent.value] || [];
            const draft = draftFor(agent.value);
            return (
              <Card key={agent.value}>
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div className="min-w-0">
                      <CardTitle className="text-base">{agent.label || agent.name}</CardTitle>
                      {agent.description && (
                        <CardDescription className="mt-1 line-clamp-2 max-w-xl">{agent.description}</CardDescription>
                      )}
                    </div>
                    <Badge variant="secondary" className="shrink-0">
                      {agentPlans.length} plan{agentPlans.length === 1 ? '' : 's'}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* Existing plans */}
                  {agentPlans.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No plans yet — add one below.</p>
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                      {agentPlans.map((p) => (
                        <div key={p.id} className="border rounded-lg p-3 flex items-center justify-between gap-3">
                          <div className="min-w-0">
                            <div className="flex items-center gap-1.5 text-sm font-medium">
                              <Clock className="h-3.5 w-3.5 text-muted-foreground" />
                              {p.label}
                            </div>
                            <div className="text-xs text-muted-foreground mt-0.5">{p.days} days</div>
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <div className="relative w-24">
                              <DollarSign className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                              <Input
                                type="number"
                                min="0"
                                value={p.price}
                                onChange={(e) => updatePlanPrice(agent.value, p.id, e.target.value)}
                                className="pl-7 h-8 text-sm"
                              />
                            </div>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8 text-destructive hover:text-destructive"
                              onClick={() => removePlan(agent.value, p.id)}
                              title="Remove this plan"
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Add plan row */}
                  <div className="flex flex-col sm:flex-row sm:items-end gap-3 border-t pt-4">
                    <div className="space-y-1">
                      <Label className="text-xs">Duration</Label>
                      <Select
                        value={draft.duration}
                        onValueChange={(v) => setDraft(agent.value, { duration: v })}
                      >
                        <SelectTrigger className="w-full sm:w-[190px]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {DURATION_PRESETS.map((d) => (
                            <SelectItem key={d.value} value={d.value}>{d.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    {draft.duration === 'custom' && (
                      <div className="space-y-1">
                        <Label className="text-xs">Days</Label>
                        <Input
                          type="number"
                          min="1"
                          value={draft.customDays}
                          onChange={(e) => setDraft(agent.value, { customDays: e.target.value })}
                          placeholder="e.g. 45"
                          className="w-full sm:w-28"
                        />
                      </div>
                    )}

                    <div className="space-y-1">
                      <Label className="text-xs">Price (USD)</Label>
                      <div className="relative w-full sm:w-32">
                        <DollarSign className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                        <Input
                          type="number"
                          min="0"
                          value={draft.price}
                          onChange={(e) => setDraft(agent.value, { price: e.target.value })}
                          placeholder="0"
                          className="pl-7"
                        />
                      </div>
                    </div>

                    <Button onClick={() => addPlan(agent.value)} className="gap-1.5">
                      <Plus className="h-4 w-4" /> Add plan
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <p className="text-xs text-muted-foreground flex items-center gap-1.5">
        <Save className="h-3.5 w-3.5" />
        Plans are saved in this browser for now (frontend preview). They'll move to the server once the pricing API is ready.
      </p>
    </div>
  );
};

export default AgentPlansTab;
