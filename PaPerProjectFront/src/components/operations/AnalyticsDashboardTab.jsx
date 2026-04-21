import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  ResponsiveContainer, AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, CartesianGrid, Legend, LineChart, Line,
} from 'recharts';
import {
  BarChart3, FileText, Sparkles, MessageSquare, Zap, TrendingUp,
  AlertTriangle, Target, CalendarClock, Loader2,
  RefreshCw, Hash,
} from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';
import * as operationsService from '@/services/operationsAgentService';

// ──────────────────────────────────────────────
// Theme (matches rest of Operations module — amber)
// ──────────────────────────────────────────────
const PALETTE = [
  '#f59e0b', '#f97316', '#eab308', '#fb923c',
  '#facc15', '#fdba74', '#fcd34d', '#fef3c7',
];
const ACCENT = '#f59e0b';
const GRID_COLOR = 'rgba(255,255,255,0.06)';
const AXIS_COLOR = 'rgba(255,255,255,0.45)';

const RANGES = [
  { value: '7d',  label: '7D' },
  { value: '30d', label: '30D' },
  { value: '90d', label: '90D' },
  { value: 'all', label: 'All' },
];

const formatBytes = (bytes = 0) => {
  if (!bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
};

const formatNumber = (n = 0) => Number(n || 0).toLocaleString();

// ──────────────────────────────────────────────
// Main component
// ──────────────────────────────────────────────
const AnalyticsDashboardTab = () => {
  const { toast } = useToast();
  const [range, setRange] = useState('30d');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (r, silent = false) => {
    try {
      if (!silent) setLoading(true);
      setRefreshing(true);
      const res = await operationsService.getOperationsAnalytics(r);
      if (res?.status === 'success') setData(res);
      else throw new Error(res?.message || 'Failed to load analytics');
    } catch (err) {
      toast({
        title: 'Analytics unavailable',
        description: err?.message || 'Please try again.',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [toast]);

  useEffect(() => { load(range); }, [range, load]);

  // KPIs (derived)
  const kpis = data?.kpis || {};

  return (
    <div
      className="w-full rounded-2xl border border-amber-500/10 overflow-hidden shadow-[0_8px_40px_-12px_rgba(245,158,11,0.15)] p-5 sm:p-6"
      style={{
        background: 'linear-gradient(135deg, #1a1333 0%, #1a1333 45%, rgba(64,40,10,0.55) 100%)',
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-3 mb-5 flex-wrap">
        <div className="flex items-center gap-3">
          <div
            className="flex items-center justify-center w-11 h-11 rounded-xl"
            style={{ backgroundColor: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.28)' }}
          >
            <BarChart3 className="h-5 w-5" style={{ color: ACCENT }} />
          </div>
          <div>
            <h2 className="text-white text-lg font-semibold">Operations Analytics</h2>
            <p className="text-white/55 text-xs">Insights across your documents, summaries, Q&A and AI-authored content.</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Time range */}
          <div className="flex rounded-lg border border-white/10 bg-black/30 p-0.5">
            {RANGES.map((r) => {
              const active = r.value === range;
              return (
                <button
                  key={r.value}
                  onClick={() => setRange(r.value)}
                  className={`px-3 py-1 text-[11px] font-semibold rounded-md transition-colors ${
                    active
                      ? 'bg-amber-500/20 text-amber-200 border border-amber-500/30'
                      : 'text-white/65 hover:text-white/90 border border-transparent'
                  }`}
                >
                  {r.label}
                </button>
              );
            })}
          </div>
          <button
            onClick={() => load(range, true)}
            disabled={refreshing}
            title="Refresh"
            className="h-8 w-8 flex items-center justify-center rounded-md border border-white/10 bg-black/30 hover:bg-white/5 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 text-white/70 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20 text-white/55 text-sm">
          <Loader2 className="h-5 w-5 animate-spin mr-2" style={{ color: ACCENT }} />
          Crunching numbers...
        </div>
      ) : !data ? (
        <div className="py-20 text-center text-white/55 text-sm">No data available yet.</div>
      ) : (
        <>
          {/* KPI grid */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
            <KpiCard icon={FileText}      label="Documents"       value={formatNumber(kpis.total_documents)}   sub={`${formatNumber(kpis.processed_documents)} processed`} />
            <KpiCard icon={Hash}          label="Pages processed" value={formatNumber(kpis.total_pages)}       sub={formatBytes(kpis.total_file_bytes)} />
            <KpiCard icon={Sparkles}      label="AI-authored"      value={formatNumber(kpis.total_generated)}   sub={`${formatNumber(kpis.total_summaries)} summaries`} />
            <KpiCard icon={MessageSquare} label="Q&A questions"    value={formatNumber(kpis.total_qa_messages)} sub={`${formatNumber(kpis.total_chats)} chats`} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mb-5">
            <KpiCard
              wide
              icon={Zap}
              label="AI tokens consumed"
              value={formatNumber(kpis.total_tokens_used)}
              sub="Across generated documents"
            />
            <KpiCard
              icon={AlertTriangle}
              label="Risks flagged"
              value={formatNumber(data.risks_vs_opportunities?.risks)}
              tint="#ef4444"
            />
            <KpiCard
              icon={Target}
              label="Opportunities"
              value={formatNumber(data.risks_vs_opportunities?.opportunities)}
              tint="#10b981"
            />
          </div>

          {/* Activity over time */}
          <ChartCard title="Activity over time" icon={TrendingUp} className="mb-5">
            {hasAnySeries(data.timeseries) ? (
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={mergeTimeseries(data.timeseries)} margin={{ top: 10, right: 12, left: -10, bottom: 0 }}>
                  <defs>
                    <linearGradient id="gDocs" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#f59e0b" stopOpacity={0.4} />
                      <stop offset="100%" stopColor="#f59e0b" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="gGen" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#fb923c" stopOpacity={0.4} />
                      <stop offset="100%" stopColor="#fb923c" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="gQa" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#fcd34d" stopOpacity={0.4} />
                      <stop offset="100%" stopColor="#fcd34d" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
                  <XAxis dataKey="label" stroke={AXIS_COLOR} fontSize={11} interval="preserveStartEnd" />
                  <YAxis stroke={AXIS_COLOR} fontSize={11} allowDecimals={false} />
                  <Tooltip content={<DarkTooltip />} />
                  <Legend wrapperStyle={{ fontSize: 11, color: 'rgba(255,255,255,0.65)' }} />
                  <Area type="monotone" dataKey="documents" stroke="#f59e0b" strokeWidth={2} fill="url(#gDocs)" name="Uploads" />
                  <Area type="monotone" dataKey="generated" stroke="#fb923c" strokeWidth={2} fill="url(#gGen)" name="Generated" />
                  <Area type="monotone" dataKey="qa"        stroke="#fcd34d" strokeWidth={2} fill="url(#gQa)"  name="Q&A" />
                </AreaChart>
              </ResponsiveContainer>
            ) : <EmptyChart />}
          </ChartCard>

          {/* Row: Doc types + File formats */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mb-5">
            <ChartCard title="Documents by category" icon={FileText}>
              {data.document_types?.length ? (
                <ResponsiveContainer width="100%" height={240}>
                  <PieChart>
                    <Pie
                      data={data.document_types}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      innerRadius={55}
                      outerRadius={90}
                      paddingAngle={2}
                      label={(e) => `${e.name} (${e.value})`}
                      labelLine={false}
                      style={{ fontSize: 11 }}
                    >
                      {data.document_types.map((_, i) => (
                        <Cell key={i} fill={PALETTE[i % PALETTE.length]} stroke="rgba(0,0,0,0.3)" />
                      ))}
                    </Pie>
                    <Tooltip content={<DarkTooltip />} />
                  </PieChart>
                </ResponsiveContainer>
              ) : <EmptyChart />}
            </ChartCard>

            <ChartCard title="Documents by file format" icon={Hash}>
              {data.file_types?.length ? (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={data.file_types} layout="vertical" margin={{ left: 30 }}>
                    <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
                    <XAxis type="number" stroke={AXIS_COLOR} fontSize={11} allowDecimals={false} />
                    <YAxis type="category" dataKey="name" stroke={AXIS_COLOR} fontSize={11} width={60} />
                    <Tooltip content={<DarkTooltip />} cursor={{ fill: 'rgba(245,158,11,0.06)' }} />
                    <Bar dataKey="value" fill={ACCENT} radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : <EmptyChart />}
            </ChartCard>
          </div>

          {/* Row: Sentiment + Importance */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mb-5">
            <ChartCard title="Sentiment across summaries" icon={TrendingUp}>
              {data.sentiment?.length ? (
                <ResponsiveContainer width="100%" height={240}>
                  <PieChart>
                    <Pie
                      data={data.sentiment}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={88}
                      label
                      labelLine={false}
                      style={{ fontSize: 11 }}
                    >
                      {data.sentiment.map((entry, i) => (
                        <Cell key={i} fill={sentimentColor(entry.name)} stroke="rgba(0,0,0,0.3)" />
                      ))}
                    </Pie>
                    <Tooltip content={<DarkTooltip />} />
                    <Legend wrapperStyle={{ fontSize: 11, color: 'rgba(255,255,255,0.65)' }} />
                  </PieChart>
                </ResponsiveContainer>
              ) : <EmptyChart />}
            </ChartCard>

            <ChartCard title="Document importance levels" icon={AlertTriangle}>
              {data.importance?.length ? (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={data.importance}>
                    <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
                    <XAxis dataKey="name" stroke={AXIS_COLOR} fontSize={11} />
                    <YAxis stroke={AXIS_COLOR} fontSize={11} allowDecimals={false} />
                    <Tooltip content={<DarkTooltip />} cursor={{ fill: 'rgba(245,158,11,0.06)' }} />
                    <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                      {data.importance.map((entry, i) => (
                        <Cell key={i} fill={importanceColor(entry.name)} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : <EmptyChart />}
            </ChartCard>
          </div>

          {/* AI authoring breakdown */}
          <ChartCard title="AI authoring — by template" icon={Sparkles} className="mb-5">
            {data.template_usage?.length ? (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={data.template_usage.map((t) => ({
                  name: prettyTemplate(t.template),
                  Documents: t.count,
                  Tokens: Math.round((t.tokens || 0) / 100) / 10, // k
                }))}>
                  <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
                  <XAxis dataKey="name" stroke={AXIS_COLOR} fontSize={11} interval={0} angle={-18} textAnchor="end" height={60} />
                  <YAxis stroke={AXIS_COLOR} fontSize={11} allowDecimals={false} />
                  <Tooltip content={<DarkTooltip suffixPerKey={{ Tokens: 'k' }} />} cursor={{ fill: 'rgba(245,158,11,0.06)' }} />
                  <Legend wrapperStyle={{ fontSize: 11, color: 'rgba(255,255,255,0.65)' }} />
                  <Bar dataKey="Documents" fill={ACCENT} radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Tokens" fill="#fcd34d" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : <EmptyChart message="No AI-authored documents yet" />}
          </ChartCard>

          {/* Deadlines */}
          <ChartCard title="Upcoming deadlines mentioned" icon={CalendarClock}>
            {data.upcoming_deadlines?.length ? (
              <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                {data.upcoming_deadlines.map((d, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-3 px-3 py-2 rounded-lg border border-white/10 bg-white/[0.02]"
                  >
                    <div
                      className="flex items-center justify-center w-8 h-8 rounded-md shrink-0"
                      style={{ backgroundColor: 'rgba(245,158,11,0.12)' }}
                    >
                      <CalendarClock className="h-4 w-4" style={{ color: ACCENT }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-white/90 truncate">{d.description || '—'}</div>
                      <div className="text-[11px] text-white/45 flex items-center gap-2 mt-0.5 truncate">
                        {d.date && <span className="text-amber-300">{d.date}</span>}
                        {d.date && d.source && <span>·</span>}
                        {d.source && <span className="truncate">{d.source}</span>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : <EmptyChart message="No deadlines extracted from summaries yet" />}
          </ChartCard>
        </>
      )}
    </div>
  );
};

// ──────────────────────────────────────────────
// Sub-components
// ──────────────────────────────────────────────

const KpiCard = ({ icon: Icon, label, value, sub, tint = ACCENT, wide = false }) => (
  <div className={`rounded-xl border border-white/10 bg-black/30 px-4 py-3 ${wide ? 'lg:col-span-1' : ''}`}>
    <div className="flex items-center gap-2 mb-2">
      <div
        className="w-7 h-7 rounded-md flex items-center justify-center"
        style={{ backgroundColor: `${tint}22`, border: `1px solid ${tint}44` }}
      >
        <Icon className="h-3.5 w-3.5" style={{ color: tint }} />
      </div>
      <span className="text-[11px] uppercase tracking-wider text-white/55 font-semibold">{label}</span>
    </div>
    <div className="text-2xl font-bold text-white/95 leading-tight">{value ?? '—'}</div>
    {sub && <div className="text-[11px] text-white/45 mt-0.5 truncate">{sub}</div>}
  </div>
);

const ChartCard = ({ title, icon: Icon, children, className = '' }) => (
  <div className={`rounded-xl border border-white/10 bg-black/25 p-4 ${className}`}>
    <div className="flex items-center gap-2 mb-3">
      {Icon && <Icon className="h-3.5 w-3.5 text-amber-300" />}
      <h3 className="text-sm font-semibold text-white/90">{title}</h3>
    </div>
    {children}
  </div>
);

const EmptyChart = ({ message = 'No data yet' }) => (
  <div className="flex items-center justify-center h-40 text-white/40 text-xs">
    {message}
  </div>
);

const DarkTooltip = ({ active, payload, label, suffixPerKey = {} }) => {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="rounded-lg border border-white/10 bg-[#1a1333]/95 backdrop-blur px-3 py-2 shadow-xl text-xs">
      {label !== undefined && label !== null && (
        <div className="text-white/70 font-semibold mb-1">{label}</div>
      )}
      {payload.map((p, i) => (
        <div key={i} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5 text-white/80">
            <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: p.color || p.payload?.fill }} />
            {p.name || p.dataKey}
          </span>
          <span className="font-semibold text-amber-200">
            {p.value}{suffixPerKey[p.name] || suffixPerKey[p.dataKey] || ''}
          </span>
        </div>
      ))}
    </div>
  );
};

// ──────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────

function hasAnySeries(ts) {
  if (!ts) return false;
  const all = [...(ts.documents || []), ...(ts.generated || []), ...(ts.qa || [])];
  return all.some((b) => (b?.value || 0) > 0);
}

function mergeTimeseries(ts) {
  const docs = ts?.documents || [];
  const gen = ts?.generated || [];
  const qa = ts?.qa || [];
  const len = Math.max(docs.length, gen.length, qa.length);
  const out = [];
  for (let i = 0; i < len; i++) {
    out.push({
      label: docs[i]?.label || gen[i]?.label || qa[i]?.label || '',
      documents: docs[i]?.value || 0,
      generated: gen[i]?.value || 0,
      qa: qa[i]?.value || 0,
    });
  }
  return out;
}

function sentimentColor(name) {
  switch ((name || '').toLowerCase()) {
    case 'positive': return '#10b981';
    case 'negative': return '#ef4444';
    case 'neutral':  return '#94a3b8';
    case 'mixed':    return '#f59e0b';
    default:         return '#8b5cf6';
  }
}

function importanceColor(name) {
  switch ((name || '').toLowerCase()) {
    case 'critical': return '#ef4444';
    case 'high':     return '#f97316';
    case 'medium':   return '#f59e0b';
    case 'low':      return '#10b981';
    default:         return '#94a3b8';
  }
}

function prettyTemplate(key) {
  if (!key) return '—';
  return key
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

export default AnalyticsDashboardTab;
