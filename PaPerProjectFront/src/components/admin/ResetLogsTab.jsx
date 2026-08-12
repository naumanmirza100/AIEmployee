// SuperAdmin → "Reset Logs" tab.
//
// Shows the history of weekly managed-token resets: for each (company, agent)
// reset, when it happened, how many tokens had been used that week, the new
// limit it reset to, and when the next reset is due. Filterable by company
// search + agent, paginated. Read-only.

import React, { useState, useEffect, useCallback } from 'react';
import { Loader2, RefreshCw, History, Search, Building2, ChevronLeft, ChevronRight, Clock, Pencil, AlertTriangle } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import adminApiKeysService from '@/services/adminApiKeysService';

// Interval presets the admin can pick from when changing a reset schedule.
const INTERVAL_PRESETS = ['7', '10', '14', '30', 'custom'];

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

// True when the scheduled next reset is meaningfully further out than the
// interval implies (e.g. interval=1 day but next reset is 3 days away) — a sign
// the interval was changed without recomputing next_reset. Editing realigns it.
const scheduleDrifted = (row) => {
  if (!row?.next_reset_at || !row?.reset_interval_days) return false;
  const daysUntil = (new Date(row.next_reset_at).getTime() - Date.now()) / 86400000;
  if (daysUntil <= 0) return false;
  return daysUntil > row.reset_interval_days + 0.5; // half-day tolerance
};

export const ResetLogsTab = ({ agentOptions = [] }) => {
  const { toast } = useToast();
  const [logs, setLogs] = useState([]);
  const [upcoming, setUpcoming] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');       // company name filter (client-side)
  const [agent, setAgent] = useState('');         // agent_name filter (server-side)
  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState({ page: 1, total_pages: 1, total: 0 });

  // Inline "change reset schedule" editor for one upcoming key.
  const [editRow, setEditRow] = useState(null);   // the upcoming row being edited
  const [editPreset, setEditPreset] = useState('7');
  const [editCustom, setEditCustom] = useState('');
  const [editTokens, setEditTokens] = useState(''); // new tokens-per-reset amount
  const [saving, setSaving] = useState(false);

  const openEdit = (row) => {
    const days = String(row.reset_interval_days || 7);
    const isPreset = INTERVAL_PRESETS.includes(days);
    setEditPreset(isPreset ? days : 'custom');
    setEditCustom(isPreset ? '' : days);
    setEditTokens(row.tokens_per_period != null ? String(row.tokens_per_period) : '');
    setEditRow(row);
  };

  const saveSchedule = async () => {
    const days = editPreset === 'custom' ? Number(editCustom) : Number(editPreset);
    if (!days || days < 1 || days > 365) {
      toast({ title: 'Invalid interval', description: 'Enter a number of days between 1 and 365.', variant: 'destructive' });
      return;
    }
    const tokensTrimmed = String(editTokens).trim();
    if (tokensTrimmed !== '' && (isNaN(Number(tokensTrimmed)) || Number(tokensTrimmed) < 0)) {
      toast({ title: 'Invalid token amount', description: 'Tokens per reset must be 0 or more.', variant: 'destructive' });
      return;
    }
    setSaving(true);
    try {
      await adminApiKeysService.updateResetSchedule({
        key_id: editRow.key_id,
        reset_interval_days: days,
        tokens_per_period: tokensTrimmed === '' ? undefined : Number(tokensTrimmed),
        recompute_next: true,
      });
      const tokenNote = tokensTrimmed !== '' ? `, ${Number(tokensTrimmed).toLocaleString()} tokens/reset` : '';
      toast({ title: 'Reset schedule updated', description: `${editRow.company_name} · ${editRow.agent_label} now resets every ${days} days${tokenNote}.` });
      setEditRow(null);
      load(page, agent);
    } catch (e) {
      toast({ title: 'Could not update', description: e?.message || 'Please try again.', variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const load = useCallback(async (p = page, agentFilter = agent) => {
    setLoading(true);
    try {
      const params = { page: p, page_size: 25 };
      if (agentFilter) params.agent_name = agentFilter;
      const res = await adminApiKeysService.listWeeklyResetLogs(params);
      setLogs(res?.logs || []);
      setUpcoming(res?.upcoming || []);
      setMeta(res?.pagination || { page: p, total_pages: 1, total: 0 });
    } catch {
      setLogs([]);
      setUpcoming([]);
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

      {/* Upcoming resets — same table shape as the history below, so the
          "before" (scheduled) and "after" (logged) views read consistently. */}
      {!loading && upcoming.length > 0 && (
        <div className="rounded-xl border border-violet-400/25 bg-violet-500/[0.06] overflow-hidden">
          <div className="flex items-center gap-1.5 px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-violet-300 border-b border-violet-400/20">
            <Clock className="h-3.5 w-3.5" /> Upcoming resets
            <span className="text-white/30 normal-case font-normal tracking-normal">· scheduled, not yet run</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-violet-500/[0.08] text-white/60 text-xs uppercase tracking-wide">
                  <th className="text-left font-semibold px-4 py-3">Company</th>
                  <th className="text-left font-semibold px-4 py-3">Agent</th>
                  <th className="text-left font-semibold px-4 py-3">Last reset</th>
                  <th className="text-left font-semibold px-4 py-3">Next reset</th>
                  <th className="text-left font-semibold px-4 py-3">Interval</th>
                  <th className="text-right font-semibold px-4 py-3">Tokens per reset</th>
                  <th className="text-right font-semibold px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {upcoming.slice(0, 20).map((u, i) => (
                  <tr
                    key={`${u.company_id}-${u.agent_name}-${i}`}
                    className="border-t border-violet-400/15 text-white/80 hover:bg-white/[0.02]"
                  >
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center gap-1.5">
                        <Building2 className="h-3.5 w-3.5 text-white/30" />
                        {u.company_name || `#${u.company_id}`}
                      </span>
                    </td>
                    <td className="px-4 py-3">{u.agent_label}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-white/50">
                      {u.last_reset_at ? fmtDateTime(u.last_reset_at) : <span className="text-white/30">Not yet reset</span>}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-violet-200">{fmtDateTime(u.next_reset_at)}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-white/50">
                      <span className="inline-flex items-center gap-1.5">
                        every {u.reset_interval_days || 7} days
                        {scheduleDrifted(u) && (
                          <span
                            title="Next reset is further out than the interval. Click Edit → Save to realign it from now."
                            className="inline-flex items-center gap-0.5 text-amber-400/90 text-[11px]"
                          >
                            <AlertTriangle className="h-3 w-3" /> off
                          </span>
                        )}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-emerald-300">
                      {u.tokens_per_period != null ? Number(u.tokens_per_period).toLocaleString() : '—'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 gap-1 border-violet-400/30 text-violet-200 hover:bg-violet-500/10"
                        onClick={() => openEdit(u)}
                        title="Change reset schedule"
                      >
                        <Pencil className="h-3 w-3" /> Edit
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {upcoming.length > 20 && (
            <div className="px-4 py-2 text-[11px] text-white/40 border-t border-violet-400/15">
              +{upcoming.length - 20} more scheduled
            </div>
          )}
        </div>
      )}

      {/* Past resets (logged history) */}
      <div className="rounded-xl border border-[#3a295a] bg-[#1a1333]/50 overflow-hidden">
        <div className="flex items-center gap-1.5 px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-white/50 border-b border-[#3a295a]">
          <History className="h-3.5 w-3.5" /> Past resets
          <span className="text-white/25 normal-case font-normal tracking-normal">· already run</span>
        </div>
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

      {/* Change reset schedule dialog */}
      <Dialog open={!!editRow} onOpenChange={(o) => !o && setEditRow(null)}>
        <DialogContent className="bg-[#120d22] border border-[#2d2342] text-white max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-white flex items-center gap-2">
              <Clock className="w-5 h-5 text-violet-400" /> Change reset schedule
            </DialogTitle>
            <DialogDescription className="text-white/60">
              {editRow && (
                <>{editRow.company_name} · {editRow.agent_label} — set how often the managed-token quota resets.</>
              )}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label className="text-white/70 text-sm">Reset every</Label>
              <Select value={editPreset} onValueChange={setEditPreset}>
                <SelectTrigger className="bg-[#1a1333] border-[#3a295a] text-white"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-[#1a1333] border-[#3a295a] text-white">
                  <SelectItem value="7">7 days (weekly)</SelectItem>
                  <SelectItem value="10">10 days</SelectItem>
                  <SelectItem value="14">14 days (bi-weekly)</SelectItem>
                  <SelectItem value="30">30 days (monthly)</SelectItem>
                  <SelectItem value="custom">Custom…</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {editPreset === 'custom' && (
              <div className="space-y-1.5">
                <Label className="text-white/70 text-sm">Custom days</Label>
                <Input
                  type="number"
                  min="1"
                  max="365"
                  value={editCustom}
                  onChange={(e) => setEditCustom(e.target.value)}
                  placeholder="e.g. 21"
                  className="bg-[#1a1333] border-[#3a295a] text-white placeholder:text-white/30"
                />
              </div>
            )}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <Label className="text-white/70 text-sm">Tokens per reset</Label>
                {editTokens && !isNaN(Number(editTokens)) && Number(editTokens) > 0 && (
                  <span className="text-xs text-violet-300 font-medium">{Number(editTokens).toLocaleString()} tokens</span>
                )}
              </div>
              <Input
                type="number"
                min="0"
                value={editTokens}
                onChange={(e) => setEditTokens(e.target.value)}
                placeholder="Leave blank to keep current"
                className="bg-[#1a1333] border-[#3a295a] text-white placeholder:text-white/30"
              />
              <p className="text-[11px] text-white/40">How many managed tokens the quota refills to on each reset.</p>
            </div>
            <p className="text-[11px] text-emerald-400/80 flex items-center gap-1">
              <Clock className="w-3 h-3" /> Next reset is recalculated from now; a new token amount applies immediately.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" className="border-white/15 text-white/80 hover:bg-white/5" onClick={() => setEditRow(null)}>Cancel</Button>
            <Button className="bg-violet-600 hover:bg-violet-700 text-white" onClick={saveSchedule} disabled={saving}>
              {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ResetLogsTab;
