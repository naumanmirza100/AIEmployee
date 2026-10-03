import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { labelOf, labelled } from '@/utils/labels';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/components/ui/use-toast';
import { Badge } from '@/components/ui/badge';
import { Loader2, BarChart3, RefreshCw } from 'lucide-react';
import { HINTS } from './frontlineTutorialSteps';
import InfoHint from './InfoHint';
import frontlineAgentService from '@/services/frontlineAgentService';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const CHART_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];

export function FrontlineAnalyticsTab() {
  const { toast } = useToast();
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [nlQuestion, setNlQuestion] = useState('');
  const [nlLoading, setNlLoading] = useState(false);
  const [nlResult, setNlResult] = useState(null);
  // Team performance drill-down (per-agent). Loaded alongside analytics
  // so the same date range applies to both. State is separate from `data`
  // so a slow team-perf fetch doesn't block the summary cards from rendering.
  const [perfRows, setPerfRows] = useState(null);
  const [perfLoading, setPerfLoading] = useState(false);
  // Column the perf table is sorted by (defaults to tickets_assigned desc,
  // matching the backend order but rebindable client-side).
  const [perfSort, setPerfSort] = useState({ col: 'tickets_assigned', dir: 'desc' });
  // CSAT drill-down — same fetch strategy as team perf, requests the
  // opt-in `by_agent` + `by_month` add-ons.
  const [csatDetail, setCsatDetail] = useState(null);
  const [csatLoading, setCsatLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await frontlineAgentService.getFrontlineAnalytics(dateFrom || undefined, dateTo || undefined);
      setData((res.status === 'success' && res.data) ? res.data : null);
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to load analytics', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };
  const loadPerf = async () => {
    setPerfLoading(true);
    try {
      const res = await frontlineAgentService.getFrontlineAgentPerformance(
        dateFrom || undefined, dateTo || undefined,
      );
      setPerfRows((res.status === 'success' && Array.isArray(res.data)) ? res.data : []);
    } catch (e) {
      setPerfRows([]);
      console.warn('Team performance load failed:', e.message);
    } finally {
      setPerfLoading(false);
    }
  };
  const loadCsat = async () => {
    setCsatLoading(true);
    try {
      // The date-range inputs above are ticket-created dates. CSAT's
      // window_days param counts back from now. As a pragmatic compromise:
      // if a date-range is set, size the window from the earlier of the
      // two — imperfect but consistent with how the SLA tile works.
      const daysFromRange = dateFrom
        ? Math.max(1, Math.ceil((Date.now() - new Date(dateFrom).getTime()) / 86400000))
        : 90;
      const res = await frontlineAgentService.getFrontlineSatisfactionSummary({
        windowDays: Math.min(daysFromRange, 365),
        byAgent: true, byMonth: true,
      });
      setCsatDetail((res.status === 'success' && res.data) ? res.data : null);
    } catch (e) {
      setCsatDetail(null);
      console.warn('CSAT detail load failed:', e.message);
    } finally {
      setCsatLoading(false);
    }
  };
  useEffect(() => { load(); loadPerf(); loadCsat(); }, [dateFrom, dateTo]);
  const handleExport = async () => {
    setExporting(true);
    try {
      await frontlineAgentService.downloadFrontlineAnalyticsExport(dateFrom || undefined, dateTo || undefined);
      toast({ title: 'Export started', description: 'CSV download should start.' });
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Export failed', variant: 'destructive' });
    } finally {
      setExporting(false);
    }
  };
  const handleAskAnalytics = async (e) => {
    e?.preventDefault?.();
    const q = nlQuestion.trim();
    if (!q) {
      toast({ title: 'Error', description: 'Enter a question', variant: 'destructive' });
      return;
    }
    setNlLoading(true);
    setNlResult(null);
    try {
      const res = await frontlineAgentService.askFrontlineAnalytics(q, dateFrom || undefined, dateTo || undefined);
      if (res.status === 'success' && res.data) {
        setNlResult(res.data);
      } else {
        throw new Error(res.message || 'Failed to get answer');
      }
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Ask failed', variant: 'destructive' });
    } finally {
      setNlLoading(false);
    }
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><BarChart3 className="h-5 w-5" /> Analytics</CardTitle>
        <CardDescription>Tickets trends and export. Ask in plain language or set date range and load.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* NL analytics - ask in plain language */}
        <div data-tour-analytics="nlq" className="rounded-lg border bg-muted/30 p-4 space-y-2">
          <div className="flex items-center gap-1.5">
            <Label className="text-sm font-medium">Ask in plain language</Label>
            <InfoHint {...HINTS.analyticsNlq} />
          </div>
          <p className="text-xs text-muted-foreground">e.g. &quot;How many tickets were resolved?&quot; or &quot;Breakdown by status&quot;</p>
          <form onSubmit={handleAskAnalytics} className="flex flex-wrap gap-2">
            <Input
              placeholder="Ask a question about your tickets..."
              value={nlQuestion}
              onChange={(e) => setNlQuestion(e.target.value)}
              disabled={nlLoading}
              className="max-w-md"
            />
            <Button type="submit" disabled={nlLoading}>
              {nlLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {nlLoading ? 'Asking...' : 'Ask'}
            </Button>
          </form>
          {nlResult && (
            <div className="mt-3 space-y-3">
              <div className="p-3 rounded-lg bg-background border text-sm whitespace-pre-wrap">{nlResult.answer}</div>
              {nlResult.chart_type && nlResult.analytics_data && (
                <div className="mt-2">
                  {nlResult.chart_type === 'by_date' && (nlResult.analytics_data.tickets_by_date || []).length > 0 && (
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm">Tickets over time</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <ResponsiveContainer width="100%" height={220}>
                          <BarChart data={nlResult.analytics_data.tickets_by_date} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                            <Tooltip contentStyle={{ borderRadius: 8 }} />
                            <Bar dataKey="count" name="Tickets" fill={CHART_COLORS[0]} radius={[4, 4, 0, 0]} />
                          </BarChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>
                  )}
                  {nlResult.chart_type === 'by_status' && (nlResult.analytics_data.tickets_by_status || []).length > 0 && (
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm">By status</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <ResponsiveContainer width="100%" height={220}>
                          <BarChart data={labelled(nlResult.analytics_data.tickets_by_status, 'status')} layout="vertical" margin={{ top: 8, right: 8, left: 60, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                            <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                            <YAxis type="category" dataKey="status" width={56} tick={{ fontSize: 11 }} />
                            <Tooltip contentStyle={{ borderRadius: 8 }} />
                            <Bar dataKey="count" name="Tickets" fill={CHART_COLORS[1]} radius={[0, 4, 4, 0]} />
                          </BarChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>
                  )}
                  {nlResult.chart_type === 'by_category' && (nlResult.analytics_data.tickets_by_category || []).length > 0 && (
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm">By category</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <ResponsiveContainer width="100%" height={220}>
                          <BarChart data={labelled(nlResult.analytics_data.tickets_by_category, 'category')} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                            <XAxis dataKey="category" tick={{ fontSize: 11 }} />
                            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                            <Tooltip contentStyle={{ borderRadius: 8 }} />
                            <Bar dataKey="count" name="Tickets" fill={CHART_COLORS[2]} radius={[4, 4, 0, 0]} />
                          </BarChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        <div data-tour-analytics="range" className="flex flex-wrap items-end gap-3">
          <div className="pb-2"><InfoHint {...HINTS.analyticsRange} /></div>
          <div className="space-y-1">
            <Label>From</Label>
            {/* FRONTLINE-BUG-08: reject impossible dates + future dates.
                Native `type="date"` blocks Feb-31-style calendar values;
                `max={today}` prevents future dates; also cap `To` at
                `today` and lower-bound it by the current `From`. */}
            <Input
              type="date"
              value={dateFrom}
              max={dateTo || new Date().toISOString().slice(0, 10)}
              onChange={(e) => setDateFrom(e.target.value)}
              className="w-[160px]"
            />
          </div>
          <div className="space-y-1">
            <Label>To</Label>
            <Input
              type="date"
              value={dateTo}
              min={dateFrom || undefined}
              max={new Date().toISOString().slice(0, 10)}
              onChange={(e) => setDateTo(e.target.value)}
              className="w-[160px]"
            />
          </div>
          <Button variant="outline" onClick={load} disabled={loading}>Load</Button>
          <Button variant="outline" onClick={handleExport} disabled={exporting}>Export CSV</Button>
        </div>
        {loading ? <div className="flex justify-center py-4"><Loader2 className="h-6 w-6 animate-spin" /></div> : data && (
          <div className="space-y-4">
            {data.narrative && (
              <div className="p-3 rounded-lg bg-muted/50 border text-sm text-foreground">
                <p className="font-medium text-muted-foreground mb-1">Summary</p>
                <p className="whitespace-pre-wrap">{data.narrative}</p>
              </div>
            )}
            <div className="flex items-center gap-1.5">
              <span className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">KPIs</span>
              <InfoHint {...HINTS.analyticsKpis} />
            </div>
            <div data-tour-analytics="kpis" className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="p-3 border rounded">
                <p className="text-sm text-muted-foreground">Total tickets</p>
                <p className="text-2xl font-semibold">{data.total_tickets}</p>
              </div>
              <div className="p-3 border rounded">
                <p className="text-sm text-muted-foreground">Auto-resolved</p>
                <p className="text-2xl font-semibold">{data.auto_resolved_count ?? 0}</p>
              </div>
              <div className="p-3 border rounded">
                <p className="text-sm text-muted-foreground">Avg resolution (hours)</p>
                <p className="text-2xl font-semibold">{data.avg_resolution_hours ?? '—'}</p>
              </div>
            </div>

            {/* Charts */}
            <div className="flex items-center gap-1.5">
              <span className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">Charts & team</span>
              <InfoHint {...HINTS.analyticsCharts} />
            </div>
            <div data-tour-analytics="charts" className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Tickets over time */}
              {(data.tickets_by_date || []).length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">Tickets over time</CardTitle>
                    <CardDescription>Daily ticket count</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={260}>
                      <BarChart data={data.tickets_by_date} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                        <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                        <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                        <Tooltip contentStyle={{ borderRadius: 8 }} />
                        <Bar dataKey="count" name="Tickets" fill={CHART_COLORS[0]} radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              )}
              {/* By status */}
              {(data.tickets_by_status || []).length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">By status</CardTitle>
                    <CardDescription>Ticket distribution by status</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={260}>
                      <BarChart data={labelled(data.tickets_by_status, 'status')} layout="vertical" margin={{ top: 8, right: 8, left: 60, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                        <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                        <YAxis type="category" dataKey="status" width={56} tick={{ fontSize: 11 }} />
                        <Tooltip contentStyle={{ borderRadius: 8 }} />
                        <Bar dataKey="count" name="Tickets" fill={CHART_COLORS[1]} radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              )}
            </div>

            {/* By category - full width bar or pie */}
            {(data.tickets_by_category || []).length > 0 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">By category</CardTitle>
                  <CardDescription>Ticket distribution by category</CardDescription>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={labelled(data.tickets_by_category, 'category')} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                      <XAxis dataKey="category" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                      <Tooltip contentStyle={{ borderRadius: 8 }} />
                      <Bar dataKey="count" name="Tickets" fill={CHART_COLORS[2]} radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            )}

            <div>
              <h4 className="font-medium mb-2">By status</h4>
              <div className="flex flex-wrap gap-2">
                {(data.tickets_by_status || []).map((s) => (
                  <Badge key={s.status} variant="outline">{labelOf(s.status)}: {s.count}</Badge>
                ))}
              </div>
            </div>
            <div>
              <h4 className="font-medium mb-2">By category</h4>
              <div className="flex flex-wrap gap-2">
                {(data.tickets_by_category || []).map((c) => (
                  <Badge key={c.category} variant="secondary">{labelOf(c.category)}: {c.count}</Badge>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Team performance — per-agent breakdown. Sortable columns +
            outlier highlighting so a manager can spot who needs help
            (high SLA breach %) or who's carrying more than their share
            (high tickets_assigned relative to the team average). */}
        <div className="rounded-lg border bg-muted/20 p-4 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div>
              <h4 className="font-medium text-sm">Team performance</h4>
              <p className="text-xs text-muted-foreground">
                Per-agent stats over the selected date range. Click a column
                to sort. Median is more robust than mean for skewed data.
              </p>
            </div>
            <Button variant="ghost" size="sm" onClick={loadPerf} disabled={perfLoading}>
              {perfLoading
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <RefreshCw className="h-3.5 w-3.5" />}
            </Button>
          </div>

          {perfLoading && !perfRows ? (
            <div className="flex justify-center py-6">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : !perfRows || perfRows.length === 0 ? (
            <p className="text-xs text-muted-foreground py-3">
              No agents with assigned tickets in this window.
            </p>
          ) : (() => {
            // Compute team averages for outlier highlighting. Uses the
            // subset of agents who resolved anything — computing a mean
            // over agents who never resolved would just skew everything.
            const withResolved = perfRows.filter((r) => r.resolved > 0);
            const avgBreachPct = withResolved.length
              ? withResolved.reduce((s, r) => s + (r.sla_breach_pct || 0), 0) / withResolved.length
              : 0;
            const avgMedianRes = withResolved.length
              ? withResolved.reduce((s, r) => s + (r.median_resolution_seconds || 0), 0) / withResolved.length
              : 0;

            const sorted = [...perfRows].sort((a, b) => {
              const av = a[perfSort.col] ?? -Infinity;
              const bv = b[perfSort.col] ?? -Infinity;
              const cmp = av === bv ? 0 : (av < bv ? -1 : 1);
              return perfSort.dir === 'asc' ? cmp : -cmp;
            });
            const setSort = (col) => setPerfSort((s) =>
              s.col === col
                ? { col, dir: s.dir === 'asc' ? 'desc' : 'asc' }
                : { col, dir: 'desc' },
            );
            const hdr = (col, label) => (
              <th
                onClick={() => setSort(col)}
                className={`px-2 py-1.5 text-left font-medium cursor-pointer select-none ${
                  perfSort.col === col ? 'text-white' : 'text-white/60'
                } hover:text-white`}
              >
                {label}{perfSort.col === col ? (perfSort.dir === 'asc' ? ' ↑' : ' ↓') : ''}
              </th>
            );
            const fmtSecs = (s) => {
              if (s == null) return '—';
              if (s < 60) return `${Math.round(s)}s`;
              if (s < 3600) return `${Math.round(s / 60)}m`;
              if (s < 86400) return `${(s / 3600).toFixed(1)}h`;
              return `${(s / 86400).toFixed(1)}d`;
            };
            return (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="border-b border-white/[0.06]">
                    <tr>
                      {hdr('assigned_to_name', 'Agent')}
                      {hdr('tickets_assigned', 'Assigned')}
                      {hdr('resolved', 'Resolved')}
                      {hdr('resolution_rate', 'Rate')}
                      {hdr('median_resolution_seconds', 'Median resolve')}
                      {hdr('sla_breach_pct', 'SLA breach %')}
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map((r) => {
                      // Flag as outlier if this agent's breach % is at least
                      // 15 percentage points above the team's average AND they
                      // resolved enough to be statistically meaningful (>= 3).
                      // 15pp is a rule-of-thumb, not gospel — tune later.
                      const isBreachOutlier = r.resolved >= 3
                        && (r.sla_breach_pct - avgBreachPct) >= 0.15;
                      // Similarly for slow median resolution — flag if ≥1.5×
                      // the team median AND at least 3 resolved tickets.
                      const isSlowOutlier = r.resolved >= 3
                        && avgMedianRes > 0
                        && r.median_resolution_seconds
                        && r.median_resolution_seconds >= 1.5 * avgMedianRes;
                      const bg = isBreachOutlier
                        ? 'bg-rose-500/[0.05]'
                        : isSlowOutlier ? 'bg-amber-500/[0.05]' : '';
                      return (
                        <tr key={r.assigned_to_id} className={`border-b border-white/[0.04] ${bg}`}>
                          <td className="px-2 py-1.5 text-white/85">
                            {r.assigned_to_name || `User #${r.assigned_to_id}`}
                          </td>
                          <td className="px-2 py-1.5 text-white/70">{r.tickets_assigned}</td>
                          <td className="px-2 py-1.5 text-white/70">
                            {r.resolved}
                            {r.auto_resolved > 0 && (
                              <span className="text-white/40"> ({r.auto_resolved} auto)</span>
                            )}
                          </td>
                          <td className="px-2 py-1.5 text-white/70">
                            {r.tickets_assigned > 0 ? `${Math.round(r.resolution_rate * 100)}%` : '—'}
                          </td>
                          <td className={`px-2 py-1.5 ${isSlowOutlier ? 'text-amber-300' : 'text-white/70'}`}>
                            {fmtSecs(r.median_resolution_seconds)}
                          </td>
                          <td className={`px-2 py-1.5 ${isBreachOutlier ? 'text-rose-300 font-medium' : 'text-white/70'}`}>
                            {r.resolved > 0
                              ? `${Math.round(r.sla_breach_pct * 100)}%`
                              : '—'}
                            {r.sla_breached_count > 0 && (
                              <span className="text-white/40"> ({r.sla_breached_count})</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {(withResolved.length > 0) && (
                  <p className="text-[10px] text-muted-foreground pt-2">
                    Team average: median resolve <span className="text-white/70">{fmtSecs(avgMedianRes)}</span>
                    {' · '}
                    SLA breach <span className="text-white/70">{Math.round(avgBreachPct * 100)}%</span>.
                    <span className="text-rose-300"> Rose </span>rows = breach % ≥ 15pp over team avg.
                    <span className="text-amber-300"> Amber </span>rows = median resolve ≥ 1.5× team median.
                  </p>
                )}
              </div>
            );
          })()}
        </div>

        {/* CSAT drill-down — per-agent breakdown + monthly trend. The tile
            on the Overview shows only the roll-up; this section adds the
            "who's getting the good ratings" and "are we trending up or
            down" dimensions the reporting was missing. */}
        <div className="rounded-lg border bg-muted/20 p-4 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <div>
              <h4 className="font-medium text-sm">CSAT drill-down</h4>
              <p className="text-xs text-muted-foreground">
                Per-agent and monthly trend for customer satisfaction.
              </p>
            </div>
            <Button variant="ghost" size="sm" onClick={loadCsat} disabled={csatLoading}>
              {csatLoading
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <RefreshCw className="h-3.5 w-3.5" />}
            </Button>
          </div>

          {csatLoading && !csatDetail ? (
            <div className="flex justify-center py-6">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : !csatDetail || csatDetail.response_count === 0 ? (
            <p className="text-xs text-muted-foreground py-3">
              No CSAT responses in this window.
            </p>
          ) : (
            <div className="space-y-4">
              {/* Header stats */}
              <div className="flex items-baseline gap-4 flex-wrap">
                <div>
                  <div className="text-2xl font-semibold text-white">
                    {csatDetail.average != null ? csatDetail.average.toFixed(2) : '—'}
                    <span className="text-sm text-white/40 font-normal"> / 5</span>
                  </div>
                  <div className="text-[10px] text-white/40">
                    {csatDetail.response_count} responses over {csatDetail.window_days}d
                  </div>
                </div>
                {/* Distribution — inline horizontal bar (no chart lib). */}
                <div className="flex-1 min-w-[200px] space-y-0.5">
                  {[5, 4, 3, 2, 1].map((star) => {
                    const c = csatDetail.distribution?.[String(star)] || 0;
                    const pct = csatDetail.response_count
                      ? Math.round((c / csatDetail.response_count) * 100)
                      : 0;
                    return (
                      <div key={star} className="flex items-center gap-2 text-[11px]">
                        <span className="w-4 text-white/50 text-right">{star}</span>
                        <div className="flex-1 h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
                          <div
                            className={`h-full ${star >= 4 ? 'bg-emerald-500' : star === 3 ? 'bg-amber-500' : 'bg-rose-500'}`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <span className="w-8 text-white/50 text-right">{c}</span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Monthly trend */}
              {Array.isArray(csatDetail.trend) && csatDetail.trend.length > 0 && (
                <div>
                  <div className="text-[11px] uppercase tracking-wide text-white/40 mb-1">Monthly trend</div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead className="border-b border-white/[0.06]">
                        <tr className="text-white/60">
                          <th className="px-2 py-1.5 text-left font-medium">Month</th>
                          <th className="px-2 py-1.5 text-left font-medium">Responses</th>
                          <th className="px-2 py-1.5 text-left font-medium">Average</th>
                          <th className="px-2 py-1.5 text-left font-medium">vs prev</th>
                        </tr>
                      </thead>
                      <tbody>
                        {csatDetail.trend.map((m, i) => {
                          const prev = csatDetail.trend[i - 1];
                          const delta = prev && prev.average != null && m.average != null
                            ? m.average - prev.average
                            : null;
                          const deltaColor = delta == null
                            ? 'text-white/40'
                            : delta > 0.05 ? 'text-emerald-400'
                              : delta < -0.05 ? 'text-rose-400'
                                : 'text-white/50';
                          return (
                            <tr key={m.month} className="border-b border-white/[0.04]">
                              <td className="px-2 py-1.5 text-white/80">{m.month}</td>
                              <td className="px-2 py-1.5 text-white/70">{m.response_count}</td>
                              <td className="px-2 py-1.5 text-white/80">
                                {m.average != null ? m.average.toFixed(2) : '—'}
                              </td>
                              <td className={`px-2 py-1.5 ${deltaColor}`}>
                                {delta == null ? '—' : `${delta > 0 ? '+' : ''}${delta.toFixed(2)}`}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Per-agent breakdown */}
              {Array.isArray(csatDetail.by_agent) && csatDetail.by_agent.length > 0 && (
                <div>
                  <div className="text-[11px] uppercase tracking-wide text-white/40 mb-1">By agent</div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead className="border-b border-white/[0.06]">
                        <tr className="text-white/60">
                          <th className="px-2 py-1.5 text-left font-medium">Agent</th>
                          <th className="px-2 py-1.5 text-left font-medium">Responses</th>
                          <th className="px-2 py-1.5 text-left font-medium">Average</th>
                          <th className="px-2 py-1.5 text-left font-medium">5★</th>
                          <th className="px-2 py-1.5 text-left font-medium">1★</th>
                        </tr>
                      </thead>
                      <tbody>
                        {csatDetail.by_agent.map((a) => {
                          const low = a.average != null && a.average < 3.5 && a.response_count >= 3;
                          const good = a.average != null && a.average >= 4.5 && a.response_count >= 3;
                          return (
                            <tr key={a.assigned_to_id ?? 'unassigned'}
                                className={`border-b border-white/[0.04] ${low ? 'bg-rose-500/[0.05]' : good ? 'bg-emerald-500/[0.05]' : ''}`}>
                              <td className="px-2 py-1.5 text-white/85">{a.assigned_to_name || `User #${a.assigned_to_id}`}</td>
                              <td className="px-2 py-1.5 text-white/70">{a.response_count}</td>
                              <td className={`px-2 py-1.5 ${low ? 'text-rose-300' : good ? 'text-emerald-300' : 'text-white/85'}`}>
                                {a.average != null ? a.average.toFixed(2) : '—'}
                              </td>
                              <td className="px-2 py-1.5 text-white/70">{a.distribution?.['5'] || 0}</td>
                              <td className="px-2 py-1.5 text-white/70">{a.distribution?.['1'] || 0}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    <p className="text-[10px] text-muted-foreground pt-2">
                      Highlighted: <span className="text-emerald-300">green</span> = avg ≥ 4.5 with 3+ responses;
                      <span className="text-rose-300"> red</span> = avg &lt; 3.5 with 3+ responses.
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
