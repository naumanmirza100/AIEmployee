/**
 * FrontlineInsightsPanel — Overview-tab summary widget that surfaces four
 * admin signals shipped recently: SLA breach %, KB coverage gaps, DLQ
 * (background-task failures), and the audit log tail. Each tile lazy-fetches
 * when the Overview tab mounts. Each is collapsible — admins who don't care
 * about one signal can hide it without it eating screen space.
 *
 * Backend endpoints used (all read-only):
 *   GET /frontline/sla/dashboard
 *   GET /frontline/kb-coverage
 *   GET /frontline/dead-letters
 *   GET /frontline/audit-log
 */
import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import {
  Loader2, Shield, BarChart3, AlertOctagon, History, ChevronRight, RefreshCw,
  CheckCircle,
} from 'lucide-react';
import frontlineAgentService from '@/services/frontlineAgentService';


function TileShell({ icon: Icon, title, color, accent, isLoading, onRefresh, children, footer }) {
  return (
    <Card className="border-white/10 bg-black/30 backdrop-blur-sm w-full min-w-0">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-sm font-semibold">
            <span className="rounded-md p-1" style={{ backgroundColor: accent }}>
              <Icon className="h-4 w-4" style={{ color }} />
            </span>
            {title}
          </CardTitle>
          {onRefresh && (
            <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-white/40 hover:text-white/80"
              onClick={onRefresh} disabled={isLoading} title="Refresh">
              {isLoading
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <RefreshCw className="h-3.5 w-3.5" />}
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="text-sm space-y-2">
        {isLoading ? (
          <div className="flex items-center gap-2 text-white/45">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading…
          </div>
        ) : children}
      </CardContent>
      {footer}
    </Card>
  );
}


export default function FrontlineInsightsPanel() {
  const { toast } = useToast();
  const [sla, setSla] = useState({ data: null, loading: true });
  const [kb, setKb] = useState({ data: null, loading: true });
  const [dlq, setDlq] = useState({ rows: [], total: 0, loading: true });
  const [audit, setAudit] = useState({ rows: [], loading: true });
  const [resolvingId, setResolvingId] = useState(null);

  const loadSla = async () => {
    setSla((s) => ({ ...s, loading: true }));
    try {
      const res = await frontlineAgentService.getFrontlineSlaDashboard({ windowDays: 30 });
      setSla({ data: res?.data || null, loading: false });
    } catch (e) {
      setSla({ data: null, loading: false });
      console.warn('SLA tile load failed:', e.message);
    }
  };
  const loadKb = async () => {
    setKb((s) => ({ ...s, loading: true }));
    try {
      const res = await frontlineAgentService.getKbCoverageReport({ windowDays: 30, topN: 5 });
      setKb({ data: res?.data || null, loading: false });
    } catch (e) {
      setKb({ data: null, loading: false });
      console.warn('KB coverage tile load failed:', e.message);
    }
  };
  const loadDlq = async () => {
    setDlq((s) => ({ ...s, loading: true }));
    try {
      const res = await frontlineAgentService.listFrontlineDeadLetters({ limit: 5 });
      setDlq({
        rows: res?.data || [],
        total: res?.pagination?.total || 0,
        loading: false,
      });
    } catch (e) {
      setDlq({ rows: [], total: 0, loading: false });
      console.warn('DLQ tile load failed:', e.message);
    }
  };
  const loadAudit = async () => {
    setAudit((s) => ({ ...s, loading: true }));
    try {
      const res = await frontlineAgentService.listFrontlineAuditLog({ limit: 10 });
      setAudit({ rows: res?.data || [], loading: false });
    } catch (e) {
      setAudit({ rows: [], loading: false });
      console.warn('Audit log tile load failed:', e.message);
    }
  };

  useEffect(() => { loadSla(); loadKb(); loadDlq(); loadAudit(); }, []);

  const handleResolveDlq = async (row) => {
    setResolvingId(row.id);
    try {
      await frontlineAgentService.resolveFrontlineDeadLetter(row.id);
      setDlq((s) => ({
        ...s,
        rows: s.rows.filter((r) => r.id !== row.id),
        total: Math.max(0, s.total - 1),
      }));
      toast({ title: 'DLQ entry resolved' });
    } catch (e) {
      toast({ title: 'Resolve failed', description: e.message, variant: 'destructive' });
    } finally {
      setResolvingId(null);
    }
  };

  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-white/85 flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-violet-400" /> Admin insights
        </h3>
        <p className="text-xs text-white/45 mt-0.5">
          Last 30 days. Each tile pulls a separate endpoint — refresh icon next to each.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">

        {/* SLA */}
        <TileShell
          icon={Shield} title="SLA"
          color="#60a5fa" accent="rgba(96,165,250,0.15)"
          isLoading={sla.loading} onRefresh={loadSla}
        >
          {!sla.data ? (
            <div className="text-white/45 text-sm">No data.</div>
          ) : (
            <>
              <div className="flex items-baseline gap-3">
                <div>
                  <div className="text-2xl font-bold text-white">
                    {sla.data.breach_pct ?? 0}%
                  </div>
                  <div className="text-[10px] uppercase tracking-wider text-white/45">
                    breached
                  </div>
                </div>
                <div>
                  <div className="text-2xl font-bold text-amber-300">
                    {sla.data.at_risk ?? 0}
                  </div>
                  <div className="text-[10px] uppercase tracking-wider text-white/45">
                    at risk (≤2h)
                  </div>
                </div>
                <div>
                  <div className="text-2xl font-bold text-white/70">
                    {sla.data.total_tickets ?? 0}
                  </div>
                  <div className="text-[10px] uppercase tracking-wider text-white/45">
                    total
                  </div>
                </div>
              </div>
              {(sla.data.per_priority || []).length > 0 && (
                <div className="border-t border-white/[0.06] pt-2 mt-2">
                  <div className="text-[10px] uppercase tracking-wider text-white/45 mb-1">
                    By priority
                  </div>
                  <div className="space-y-0.5">
                    {sla.data.per_priority.map((p) => (
                      <div key={p.priority} className="flex items-center justify-between text-xs">
                        <span className="text-white/70 capitalize">{p.priority}</span>
                        <span className="text-white/60">
                          {p.breached}/{p.total}{' '}
                          <span className={p.breach_pct > 10 ? 'text-rose-300' : 'text-white/45'}>
                            ({p.breach_pct}%)
                          </span>
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </TileShell>

        {/* KB coverage */}
        <TileShell
          icon={AlertOctagon} title="Knowledge gaps"
          color="#f472b6" accent="rgba(244,114,182,0.15)"
          isLoading={kb.loading} onRefresh={loadKb}
        >
          {!kb.data || (kb.data.items || []).length === 0 ? (
            <div className="flex items-center gap-2 text-emerald-300/80 text-sm">
              <CheckCircle className="h-4 w-4" />
              No frequent unanswerable questions in this window.
            </div>
          ) : (
            <>
              <div className="text-xs text-white/55">
                Top questions retrieval struggled with — add KB content for these.
              </div>
              <div className="space-y-1 max-h-44 overflow-y-auto pr-1">
                {kb.data.items.slice(0, 5).map((item, idx) => (
                  <div key={idx} className="flex items-center justify-between gap-2 text-xs rounded-md border border-white/[0.06] bg-white/[0.02] px-2 py-1">
                    <span className="text-white/80 truncate flex-1" title={item.question}>
                      {item.question}
                    </span>
                    <Badge variant="outline" className="text-[10px] shrink-0">
                      {item.kb_gap_count + item.thumbs_down_count} hits
                    </Badge>
                  </div>
                ))}
              </div>
              <div className="text-[10px] text-white/40 pt-1">
                {kb.data.total_kb_gaps} gap tickets · {kb.data.total_thumbs_down} thumbs-down
              </div>
            </>
          )}
        </TileShell>

        {/* DLQ */}
        <TileShell
          icon={AlertOctagon} title="Background failures (DLQ)"
          color="#fb7185" accent="rgba(251,113,133,0.15)"
          isLoading={dlq.loading} onRefresh={loadDlq}
        >
          {dlq.rows.length === 0 ? (
            <div className="flex items-center gap-2 text-emerald-300/80 text-sm">
              <CheckCircle className="h-4 w-4" />
              No unresolved task failures.
            </div>
          ) : (
            <>
              <div className="text-xs text-white/55">
                Celery tasks that gave up after retries. Resolve once you've fixed the root cause.
              </div>
              <div className="space-y-1 max-h-44 overflow-y-auto pr-1">
                {dlq.rows.map((r) => (
                  <div key={r.id} className="rounded-md border border-white/[0.06] bg-white/[0.02] p-2">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="text-xs font-mono text-white/80 truncate">{r.task_name}</span>
                      <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px] text-emerald-300 hover:text-emerald-200"
                        disabled={resolvingId === r.id}
                        onClick={() => handleResolveDlq(r)}>
                        {resolvingId === r.id ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Resolve'}
                      </Button>
                    </div>
                    <div className="text-[10px] text-rose-200/70 mt-0.5 truncate" title={r.error_message}>
                      {r.error_type}: {r.error_message}
                    </div>
                    <div className="text-[10px] text-white/40 mt-0.5">
                      Last failed {r.last_failed_at?.slice(0, 19).replace('T', ' ')} · {r.retry_count} retries
                    </div>
                  </div>
                ))}
              </div>
              {dlq.total > dlq.rows.length && (
                <div className="text-[10px] text-white/40 pt-1">
                  Showing {dlq.rows.length} of {dlq.total} total.
                </div>
              )}
            </>
          )}
        </TileShell>

        {/* Audit log */}
        <TileShell
          icon={History} title="Recent audit log"
          color="#a78bfa" accent="rgba(167,139,250,0.15)"
          isLoading={audit.loading} onRefresh={loadAudit}
        >
          {audit.rows.length === 0 ? (
            <div className="text-white/45 text-sm">No audit entries yet.</div>
          ) : (
            <div className="space-y-1 max-h-44 overflow-y-auto pr-1">
              {audit.rows.slice(0, 10).map((r) => (
                <div key={r.id} className="flex items-center gap-2 text-xs rounded-md border border-white/[0.06] bg-white/[0.02] px-2 py-1">
                  <Badge variant="outline" className="text-[10px] shrink-0 bg-white/[0.04]">
                    {r.action}
                  </Badge>
                  <span className="text-white/70 truncate flex-1">
                    {r.target_type} #{r.target_id}
                    {r.actor_email && <span className="text-white/40"> · {r.actor_email}</span>}
                  </span>
                  <span className="text-[10px] text-white/40 shrink-0">
                    {r.created_at?.slice(11, 16)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </TileShell>

      </div>
    </div>
  );
}
