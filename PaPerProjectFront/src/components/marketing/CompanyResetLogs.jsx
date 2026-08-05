// Company-side "Weekly Reset History" panel for the API Keys & Quota page.
//
// Shows this company's own weekly managed-token resets (read-only): when each
// (agent) reset happened, how many tokens were used that week, the new limit,
// and when the next reset is due. Optionally filtered by agent, paginated.

import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Loader2, History, RefreshCw, ChevronLeft, ChevronRight } from 'lucide-react';
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
      setMeta(data?.pagination || { page: p, total_pages: 1, total: 0 });
    } catch {
      setLogs([]);
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

      {loading ? (
        <div className="flex justify-center py-12"><Loader2 className="h-7 w-7 animate-spin text-violet-400" /></div>
      ) : logs.length === 0 ? (
        <div className="text-center py-12 text-white/40">
          <History className="h-10 w-10 mx-auto mb-3 opacity-50" />
          <p className="text-sm">No weekly resets yet{agent ? ' for this agent' : ''}. They'll appear here as your quota resets each week.</p>
        </div>
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-white/10">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-white/5 text-white/50 text-xs uppercase tracking-wide">
                  {!locked && <th className="text-left font-semibold px-4 py-3">Agent</th>}
                  <th className="text-left font-semibold px-4 py-3">Reset at</th>
                  <th className="text-right font-semibold px-4 py-3">Used before reset</th>
                  <th className="text-right font-semibold px-4 py-3">New limit</th>
                  <th className="text-left font-semibold px-4 py-3">Next reset</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((l) => (
                  <tr key={l.id} className="border-t border-white/5 text-white/80 hover:bg-white/[0.02]">
                    {!locked && <td className="px-4 py-3">{l.agent_label}</td>}
                    <td className="px-4 py-3 whitespace-nowrap">{fmtDateTime(l.reset_at)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-amber-300">{Number(l.tokens_used_before_reset).toLocaleString()}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-emerald-300">{Number(l.new_included_limit).toLocaleString()}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-white/50">{fmtDateTime(l.next_reset_at)}</td>
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
