import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, CheckCircle2, Loader2, RefreshCw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { AGENT_STYLE, DUE_GROUPS, dueGroup, dueLabel, fetchMyWork } from '@/utils/myWork';

/**
 * "My work": everything the signed-in person has to do across the agents —
 * PM tasks, tickets, leave and workflow decisions, interview feedback, meeting
 * replies — in one list, soonest first. Each row says which agent it comes
 * from and opens the screen in that agent where it gets done.
 */
export default function MyWorkList() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [agent, setAgent] = useState('all');

  const load = useCallback(async () => {
    setError('');
    try {
      setItems(await fetchMyWork());
    } catch (e) {
      setError(e?.message || 'Could not load your work.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const agents = useMemo(() => {
    const seen = new Map();
    items.forEach((i) => seen.set(i.agent, { label: i.agent_label, count: (seen.get(i.agent)?.count || 0) + 1 }));
    return [...seen.entries()];
  }, [items]);

  const groups = useMemo(() => {
    const now = new Date();
    const shown = agent === 'all' ? items : items.filter((i) => i.agent === agent);
    return DUE_GROUPS
      .map((g) => ({ ...g, items: shown.filter((i) => dueGroup(i, now) === g.key) }))
      .filter((g) => g.items.length > 0);
  }, [items, agent]);

  if (loading) {
    return (
      <p className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading your work…
      </p>
    );
  }

  const chip = (key, label, count) => (
    <button
      key={key}
      type="button"
      aria-pressed={agent === key}
      onClick={() => setAgent(key)}
      className={`rounded-full border px-3 py-1 text-xs transition-colors ${
        agent === key
          ? 'border-violet-500/60 bg-violet-500/15 text-foreground'
          : 'border-border text-muted-foreground hover:text-foreground hover:bg-accent'
      }`}
    >
      {label} <span className="opacity-70">{count}</span>
    </button>
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        {chip('all', 'All', items.length)}
        {agents.map(([key, a]) => chip(key, a.label, a.count))}
        <Button
          variant="ghost"
          size="icon"
          className="ml-auto h-8 w-8 text-muted-foreground"
          title="Refresh"
          disabled={refreshing}
          onClick={() => { setRefreshing(true); load(); }}
        >
          {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
        </Button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {!error && items.length === 0 && (
        <div className="rounded-xl border border-border py-14 text-center">
          <CheckCircle2 className="mx-auto mb-2 h-8 w-8 text-emerald-500/70" />
          <p className="text-sm text-foreground">Nothing waiting for you.</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Tasks, tickets, approvals and replies from every agent show up here.
          </p>
        </div>
      )}

      {groups.map((g) => (
        <section key={g.key}>
          <h3 className={`mb-2 px-1 text-xs font-semibold uppercase tracking-wider ${
            g.key === 'overdue' ? 'text-red-500 dark:text-red-400' : 'text-muted-foreground'
          }`}>
            {g.label} <span className="font-normal opacity-70">{g.items.length}</span>
          </h3>
          <div className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-[var(--panel-2)]">
            {g.items.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => item.link && navigate(item.link)}
                className="group flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-accent"
              >
                <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium ${AGENT_STYLE[item.agent] || ''}`}>
                  {item.agent_label}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-foreground">{item.title}</p>
                  {item.detail && <p className="truncate text-xs text-muted-foreground">{item.detail}</p>}
                  {item.due && (
                    <p className={`text-xs sm:hidden ${g.key === 'overdue' ? 'text-red-500 dark:text-red-400' : 'text-muted-foreground'}`}>
                      {dueLabel(item)}
                    </p>
                  )}
                </div>
                {item.due && (
                  <span className={`hidden shrink-0 text-xs sm:inline ${
                    g.key === 'overdue' ? 'text-red-500 dark:text-red-400' : 'text-muted-foreground'
                  }`}>
                    {dueLabel(item)}
                  </span>
                )}
                <span className="flex shrink-0 items-center gap-1 text-xs text-violet-600 dark:text-violet-300">
                  <span className="hidden md:inline">{item.action}</span>
                  <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
                </span>
              </button>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
