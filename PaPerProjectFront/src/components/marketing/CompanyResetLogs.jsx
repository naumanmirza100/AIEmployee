// Company-side "Weekly Reset History" panel for the API Keys & Quota page.
//
// Shows this company's own weekly managed-token resets (read-only): when each
// (agent) reset happened, how many tokens were used that week, the new limit,
// and when the next reset is due. Optionally filtered by agent, paginated.

import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Loader2, History, RefreshCw, ChevronLeft, ChevronRight, Clock, AlertTriangle } from 'lucide-react';
import agentKeysService from '@/services/agentKeysService';

const fmtDateTime = (iso) => {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
    });
  } catch {
    return iso;
  }
};

// Props:
//   agents (optional): [{ agent_name, agent_label }] to populate the filter.
//   agentName (optional): lock to ONE agent — hides the filter (used in the
//     per-agent pop-up). agentLabel is that agent's display name.
//   bare (optional): render without the outer Card wrapper (for use inside a
//     dialog that already has its own header).
export const CompanyResetLogs = ({ agents = [], agentName = '', agentLabel = '', bare = false }) => {
  const [logs, setLogs] = useState([]);
  const [upcoming, setUpcoming] = useState([]);
  const [loading, setLoading] = useState(true);
  const [agent, setAgent] = useState(agentName || '');
  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState({ page: 1, total_pages: 1, total: 0 });
  const locked = !!agentName; // fixed to one agent → no filter shown

  const load = useCallback(async (p, agentFilter) => {
    setLoading(true);
    try {
      const params = { page: p, page_size: 15 };
      if (agentFilter) params.agent_name = agentFilter;
      const res = await agentKeysService.listResetLogs(params);
      const data = res?.data || res; // companyApi may wrap in { data }
      setLogs(data?.logs || []);
      setUpcoming(data?.upcoming || []);
      setMeta(data?.pagination || { page: p, total_pages: 1, total: 0 });
    } catch {
      setLogs([]);
      setUpcoming([]);
      setMeta({ page: 1, total_pages: 1, total: 0 });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { setPage(1); load(1, agent); }, [agent, load]);

  // Unique agent options — prefer the passed list, else derive from logs.
  const agentOptions = agents.length
    ? agents
    : Array.from(new Map(logs.map((l) => [l.agent_name, { agent_name: l.agent_name, agent_label: l.agent_label }])).values());

  // The table + pagination body, shared between the card and bare layouts.
  const body = (
    <>
      {/* Filter (hidden when locked to one agent) + refresh */}
      {!locked && (
        <div className="flex items-center justify-end gap-2 mb-3">
          <Select value={agent || 'all'} onValueChange={(v) => setAgent(v === 'all' ? '' : v)}>
            <SelectTrigger className="w-48 h-9">
              <SelectValue placeholder="All agents" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All agents</SelectItem>
              {agentOptions.map((a) => (
                <SelectItem key={a.agent_name} value={a.agent_name}>{a.agent_label || a.agent_name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" size="icon" className="h-9 w-9" onClick={() => load(page, agent)} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      )}

      {/* Upcoming resets banner — shows the next reset date(s), even when no
          reset has happened yet. */}
      {!loading && upcoming.length > 0 && (
        <div className="mb-3 rounded-lg border border-violet-400/25 bg-violet-500/[0.07] p-3 space-y-2">
          {upcoming.map((u) => (
            <div key={u.agent_name} className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
              {!locked && (
                <span className="inline-flex items-center gap-1.5">
                  <span className={u.is_expired ? 'text-white/50 font-medium' : 'text-white/90 font-medium'}>
                    {u.agent_label}
                  </span>
                  {u.is_expired && (
                    <span className="inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-red-500/15 text-red-300 border border-red-400/30">
                      <AlertTriangle className="h-2.5 w-2.5" /> Key expired
                    </span>
                  )}
                </span>
              )}
              {/* Last reset */}
              <span className="inline-flex items-center gap-1.5 text-white/60">
                <History className="h-3.5 w-3.5 text-white/40" /> Last reset:
                {u.last_reset_at
                  ? <span className="text-white/80">{fmtDateTime(u.last_reset_at)}</span>
                  : <span className="text-white/35">Not yet reset</span>}
              </span>
              {/* Next reset — an expired key's quota never resets, so showing a
                  date here would promise a refill that will not arrive. */}
              {u.is_expired ? (
                <span className="inline-flex items-center gap-1.5 text-red-300/80">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  Resets paused — renew this key to resume the schedule.
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 text-white/60">
                  <Clock className="h-3.5 w-3.5 text-violet-300" /> Next reset:
                  <span className="text-violet-200">{fmtDateTime(u.next_reset_at)}</span>
                  <span className="text-white/30">· every {u.reset_interval_days} day(s)</span>
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-12"><Loader2 className="h-7 w-7 animate-spin text-violet-400" /></div>
      ) : logs.length === 0 ? (
        <div className="text-center py-10 text-white/40">
          <History className="h-10 w-10 mx-auto mb-3 opacity-50" />
          <p className="text-sm">
            No resets have happened yet{agent ? ' for this agent' : ''}.
            {upcoming.length === 0
              ? " They'll appear here after the first reset cycle."
              : upcoming.every((u) => u.is_expired)
                ? ' The key has expired, so no reset is currently scheduled.'
                : ' The first one is scheduled above.'}
          </p>
        </div>
      ) : (
        <>
          <div className="overflow-x-auto scrollbar-violet rounded-lg border border-white/10">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-white/5 text-white/50 text-xs uppercase tracking-wide">
                  {/* Explicit widths: without them the date columns soaked up the
                      spare space and the two numeric headers wrapped onto two
                      lines while their values sat cramped. */}
                  {!locked && <th className="text-left font-semibold px-4 py-3">Agent</th>}
                  <th className="text-left font-semibold px-4 py-3 w-[22%] whitespace-nowrap">Reset at</th>
                  <th className="text-right font-semibold px-4 py-3 w-[20%] whitespace-nowrap">Used before reset</th>
                  <th className="text-right font-semibold px-4 py-3 w-[16%] whitespace-nowrap">New limit</th>
                  <th className="text-left font-semibold px-4 py-3 w-[22%] whitespace-nowrap">Next reset</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((l) => (
                  <tr key={l.id} className="border-t border-white/5 text-white/80 hover:bg-white/[0.02]">
                    {!locked && <td className="px-4 py-3">{l.agent_label}</td>}
                    <td className="px-4 py-3 whitespace-nowrap">{fmtDateTime(l.reset_at)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-amber-300 whitespace-nowrap">{Number(l.tokens_used_before_reset).toLocaleString()}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-emerald-300 whitespace-nowrap">{Number(l.new_included_limit).toLocaleString()}</td>
                    {/* The next-reset recorded at the time of this reset. */}
                    <td className="px-4 py-3 whitespace-nowrap text-white/50">{fmtDateTime(l.next_reset_at_then)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {meta.total_pages > 1 && (
            <div className="flex items-center justify-between mt-3 text-sm text-white/50">
              <span>Page {meta.page} of {meta.total_pages} · {meta.total} total</span>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" disabled={meta.page <= 1 || loading}
                  onClick={() => { const p = meta.page - 1; setPage(p); load(p, agent); }}>
                  <ChevronLeft className="h-4 w-4" /> Prev
                </Button>
                <Button variant="outline" size="sm" disabled={meta.page >= meta.total_pages || loading}
                  onClick={() => { const p = meta.page + 1; setPage(p); load(p, agent); }}>
                  Next <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </>
  );

  // Bare (inside a dialog that has its own header) or full card.
  if (bare) return body;

  return (
    <Card className="border-white/10 bg-black/20 backdrop-blur-sm">
      <CardHeader>
        <CardTitle className="text-white flex items-center gap-2">
          <History className="w-5 h-5 text-violet-400" />
          Weekly Reset History{agentLabel ? ` — ${agentLabel}` : ''}
        </CardTitle>
        <CardDescription className="text-white/50">
          When your agents' weekly managed-token quotas reset, and how much was used each cycle.
        </CardDescription>
      </CardHeader>
      <CardContent>{body}</CardContent>
    </Card>
  );
};

export default CompanyResetLogs;
