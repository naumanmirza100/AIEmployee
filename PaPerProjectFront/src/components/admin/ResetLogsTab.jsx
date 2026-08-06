// SuperAdmin → "Reset Logs" tab.
//
// Shows the history of weekly managed-token resets: for each (company, agent)
// reset, when it happened, how many tokens had been used that week, the new
// limit it reset to, and when the next reset is due. Filterable by company
// search + agent, paginated. Read-only.

import React, { useState, useEffect, useCallback } from 'react';
import { Loader2, RefreshCw, History, Search, Building2, ChevronLeft, ChevronRight } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import adminApiKeysService from '@/services/adminApiKeysService';

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

export const ResetLogsTab = ({ agentOptions = [] }) => {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');       // company name filter (client-side)
  const [agent, setAgent] = useState('');         // agent_name filter (server-side)
  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState({ page: 1, total_pages: 1, total: 0 });

  const load = useCallback(async (p = page, agentFilter = agent) => {
    setLoading(true);
    try {
      const params = { page: p, page_size: 25 };
      if (agentFilter) params.agent_name = agentFilter;
      const res = await adminApiKeysService.listWeeklyResetLogs(params);
      setLogs(res?.logs || []);
      setMeta(res?.pagination || { page: p, total_pages: 1, total: 0 });
    } catch {
      setLogs([]);
      setMeta({ page: 1, total_pages: 1, total: 0 });
    } finally {
      setLoading(false);
    }
  }, [page, agent]);

  useEffect(() => { load(1, agent); setPage(1); /* eslint-disable-next-line */ }, [agent]);

  // Client-side company-name filter over the current page.
  const q = search.trim().toLowerCase();
  const visible = q
    ? logs.filter((l) => (l.company_name || '').toLowerCase().includes(q))
    : logs;

  return (
    <div className="space-y-4">
      {/* Header + filters */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="flex items-center gap-2 text-white font-semibold">
          <History className="h-5 w-5 text-violet-400" />
          Weekly Reset History
        </div>
        <div className="flex-1" />
        <div className="relative w-full sm:w-56">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/30" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter by company…"
            className="pl-9"
          />
        </div>
        <Select value={agent || 'all'} onValueChange={(v) => setAgent(v === 'all' ? '' : v)}>
          <SelectTrigger className="w-full sm:w-52">
            <SelectValue placeholder="All agents" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All agents</SelectItem>
            {agentOptions.map((a) => (
              <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant="outline" size="icon" onClick={() => load(page, agent)} disabled={loading}>
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-[#3a295a] bg-[#1a1333]/50 overflow-hidden">
        {loading ? (
          <div className="flex justify-center py-16"><Loader2 className="h-7 w-7 animate-spin text-violet-400" /></div>
        ) : visible.length === 0 ? (
          <div className="text-center py-16 text-white/40">
            <History className="h-10 w-10 mx-auto mb-3 opacity-50" />
            <p className="text-sm">No weekly resets logged{agent || search ? ' for this filter' : ' yet'}.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-[#231845] text-white/60 text-xs uppercase tracking-wide">
                  <th className="text-left font-semibold px-4 py-3">Company</th>
                  <th className="text-left font-semibold px-4 py-3">Agent</th>
                  <th className="text-left font-semibold px-4 py-3">Reset at</th>
                  <th className="text-right font-semibold px-4 py-3">Used before reset</th>
                  <th className="text-right font-semibold px-4 py-3">New limit</th>
                  <th className="text-left font-semibold px-4 py-3">Next reset</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((l) => (
                  <tr key={l.id} className="border-t border-[#3a295a]/60 text-white/80 hover:bg-white/[0.02]">
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center gap-1.5">
                        <Building2 className="h-3.5 w-3.5 text-white/30" />
                        {l.company_name || `#${l.company_id}`}
                      </span>
                    </td>
                    <td className="px-4 py-3">{l.agent_label}</td>
                    <td className="px-4 py-3 whitespace-nowrap">{fmtDateTime(l.reset_at)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-amber-300">{Number(l.tokens_used_before_reset).toLocaleString()}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-emerald-300">{Number(l.new_included_limit).toLocaleString()}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-white/50">{fmtDateTime(l.next_reset_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pagination (server-side) */}
      {meta.total_pages > 1 && (
        <div className="flex items-center justify-between text-sm text-white/50">
          <span>Page {meta.page} of {meta.total_pages} · {meta.total} total</span>
          <div className="flex gap-2">
            <Button
              variant="outline" size="sm"
              disabled={meta.page <= 1 || loading}
              onClick={() => { const p = meta.page - 1; setPage(p); load(p, agent); }}
            >
              <ChevronLeft className="h-4 w-4" /> Prev
            </Button>
            <Button
              variant="outline" size="sm"
              disabled={meta.page >= meta.total_pages || loading}
              onClick={() => { const p = meta.page + 1; setPage(p); load(p, agent); }}
            >
              Next <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      <p className="text-[11px] text-white/30">
        A row is logged automatically each time a company's managed-token quota resets on its weekly cycle.
      </p>
    </div>
  );
};

export default ResetLogsTab;
