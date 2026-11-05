import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import {
  Loader2, Play, PlayCircle, CheckCircle2, XCircle, AlertTriangle, MinusCircle, FlaskConical,
  ChevronDown, ChevronRight, Clock, ListChecks,
} from 'lucide-react';
import { CARD_CLASS, ROW_CLASS } from '@/components/admin/apiKeysShared';

const POLL_MS = 2000;

const STATUS_META = {
  passed:  { label: 'Passed',      icon: CheckCircle2,  cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' },
  failed:  { label: 'Failed',      icon: XCircle,       cls: 'bg-red-500/15 text-red-300 border-red-500/30' },
  error:   { label: "Couldn't run", icon: AlertTriangle, cls: 'bg-amber-500/15 text-amber-300 border-amber-500/30' },
  running: { label: 'Running',     icon: Loader2,       cls: 'bg-violet-500/15 text-violet-300 border-violet-500/30' },
  queued:  { label: 'Starting',    icon: Loader2,       cls: 'bg-violet-500/15 text-violet-300 border-violet-500/30' },
};

const OUTCOME_META = {
  passed:  { icon: CheckCircle2,  cls: 'text-emerald-400' },
  failed:  { icon: XCircle,       cls: 'text-red-400' },
  error:   { icon: AlertTriangle, cls: 'text-amber-400' },
  skipped: { icon: MinusCircle,   cls: 'text-white/40' },
};

const timeAgo = (iso) => {
  if (!iso) return '';
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return new Date(iso).toLocaleString();
};

const StatusBadge = ({ status }) => {
  const meta = STATUS_META[status];
  if (!meta) return <Badge variant="outline" className="border-[var(--line-3)] text-white/50">Not run yet</Badge>;
  const Icon = meta.icon;
  const spinning = status === 'running' || status === 'queued';
  return (
    <Badge variant="outline" className={`${meta.cls} gap-1`}>
      <Icon className={`w-3 h-3 ${spinning ? 'animate-spin' : ''}`} /> {meta.label}
    </Badge>
  );
};

const Counts = ({ run }) => {
  if (!run || !run.total) return null;
  const bad = (run.failed || 0) + (run.errors || 0);
  return (
    <span className="text-xs text-white/60">
      {run.passed}/{run.total} passed{bad ? <span className="text-red-300"> · {bad} failing</span> : null}
      {run.skipped ? ` · ${run.skipped} skipped` : ''}
    </span>
  );
};

const Progress = ({ run }) => {
  const pct = run.total ? Math.round((run.done / run.total) * 100) : 0;
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-xs text-white/60">
        <span>{run.total ? `${run.done} of ${run.total} tests` : 'Preparing the test database…'}</span>
        {run.total ? <span>{pct}%</span> : null}
      </div>
      <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
        <div className="h-full bg-violet-500 transition-all" style={{ width: `${run.total ? pct : 5}%` }} />
      </div>
    </div>
  );
};

const TestRow = ({ test }) => {
  const bad = test.outcome === 'failed' || test.outcome === 'error';
  const [open, setOpen] = useState(false);
  const meta = OUTCOME_META[test.outcome] || OUTCOME_META.skipped;
  const Icon = meta.icon;
  return (
    <div className={`${ROW_CLASS} rounded-lg px-3 py-2`}>
      <button
        type="button"
        className="w-full flex items-start gap-2 text-left disabled:cursor-default"
        onClick={() => setOpen((o) => !o)}
        disabled={!test.message}
      >
        <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${meta.cls}`} />
        <span className={`flex-1 text-sm ${bad ? 'text-white' : 'text-white/80'}`}>{test.title}</span>
        {test.message ? (open ? <ChevronDown className="w-4 h-4 text-white/40" /> : <ChevronRight className="w-4 h-4 text-white/40" />) : null}
      </button>
      {open && test.message ? (
        <pre className="mt-2 max-h-72 overflow-auto rounded bg-black/40 p-3 text-[11px] leading-relaxed text-white/70 whitespace-pre-wrap break-words">
          {test.message}
        </pre>
      ) : null}
    </div>
  );
};

const RunResults = ({ run }) => {
  // Failing tests first, then grouped by the area (test class) they check.
  const groups = useMemo(() => {
    const rank = { error: 0, failed: 0, skipped: 1, passed: 2 };
    const byClass = new Map();
    [...(run.tests || [])]
      .sort((a, b) => (rank[a.outcome] ?? 2) - (rank[b.outcome] ?? 2))
      .forEach((t) => {
        const key = t.class || 'Other';
        if (!byClass.has(key)) byClass.set(key, []);
        byClass.get(key).push(t);
      });
    return [...byClass.entries()];
  }, [run.tests]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <StatusBadge status={run.status} />
        <Counts run={run} />
        <span className="text-xs text-white/40">
          {run.started_by ? `by ${run.started_by} · ` : ''}{timeAgo(run.finished_at || run.created_at)}
        </span>
      </div>
      {run.status === 'running' || run.status === 'queued' ? <Progress run={run} /> : null}
      {run.error ? (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200">{run.error}</div>
      ) : null}
      {run.log_tail ? (
        <pre className="max-h-60 overflow-auto rounded bg-black/40 p-3 text-[11px] text-white/70 whitespace-pre-wrap">{run.log_tail}</pre>
      ) : null}
      {groups.map(([name, tests]) => (
        <div key={name} className="space-y-1.5">
          <p className="text-[11px] uppercase tracking-wider text-white/40">{name}</p>
          {tests.map((t) => <TestRow key={t.id} test={t} />)}
        </div>
      ))}
    </div>
  );
};

/**
 * The AI SDR's automated tests, one card per part of the agent, each with a Run button; the results open in a
 * dialog. Used by the Super Admin panel (/admin/sdr-checks) and by AI SDR → Tests for a company's owner or
 * admin. `api` is { getOverview, startRun, getRun } for the door in use. The tests themselves run on the server,
 * in a separate process on a throwaway database (ai_sdr_agent/admin_checks.py).
 */
const SDRChecksPanel = ({ api }) => {
  const { toast } = useToast();
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(null);
  // The results dialog: which run, seen through which part ('all' = the whole run).
  const [viewing, setViewing] = useState(null);
  const [viewRun, setViewRun] = useState(null);
  const watchedRun = useRef(null);

  const load = useCallback(async () => {
    try {
      const data = await api.getOverview();
      setOverview(data);
      return data;
    } catch (e) {
      toast({ title: 'Could not load the checks', description: String(e.message || e), variant: 'destructive' });
      return null;
    } finally {
      setLoading(false);
    }
  }, [api, toast]);

  useEffect(() => { load(); }, [load]);

  const current = overview?.current;

  // While a run is going, ask every two seconds; when it ends, say how it went.
  useEffect(() => {
    if (!current) return undefined;
    watchedRun.current = current;
    const timer = setInterval(async () => {
      const data = await load();
      if (data && !data.current && watchedRun.current) {
        const done = data.runs.find((r) => r.id === watchedRun.current.id);
        watchedRun.current = null;
        if (done) {
          const ok = done.status === 'passed';
          toast({
            title: `${done.suite_title}: ${ok ? 'all tests passed' : STATUS_META[done.status]?.label.toLowerCase()}`,
            description: done.total ? `${done.passed} of ${done.total} passed` : done.error || undefined,
            variant: ok ? undefined : 'destructive',
          });
        }
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [current?.id, load, toast]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep the open results dialog up to date while its run is going.
  useEffect(() => {
    if (!viewing) { setViewRun(null); return undefined; }
    let cancelled = false;
    const fetchRun = async () => {
      try {
        const run = await api.getRun(viewing.runId, viewing.suite === 'all' ? undefined : viewing.suite);
        if (!cancelled) setViewRun(run);
        return run;
      } catch (e) {
        if (!cancelled) toast({ title: 'Could not load the results', description: String(e.message || e), variant: 'destructive' });
        return null;
      }
    };
    fetchRun();
    const timer = setInterval(async () => {
      const run = await fetchRun();
      if (run && !['running', 'queued'].includes(run.status)) clearInterval(timer);
    }, POLL_MS);
    return () => { cancelled = true; clearInterval(timer); };
  }, [api, viewing, toast]);

  const run = async (suite) => {
    setStarting(suite);
    try {
      const started = await api.startRun(suite);
      await load();
      setViewing({ runId: started.id, suite, title: started.suite_title });
    } catch (e) {
      toast({ title: 'Could not start the tests', description: String(e.message || e), variant: 'destructive' });
    } finally {
      setStarting(null);
    }
  };

  const busy = Boolean(current) || Boolean(starting);
  const allLast = overview?.all_last;

  return (
    <>
        <div className="space-y-6">
          {loading ? (
            <div className="flex justify-center py-20"><Loader2 className="w-8 h-8 animate-spin text-violet-400" /></div>
          ) : (
            <>
              <Card className={CARD_CLASS}>
                <CardHeader className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between space-y-0">
                  <div className="space-y-1.5">
                    <CardTitle className="text-white flex items-center gap-2">
                      <ListChecks className="w-5 h-5 text-violet-400" /> Check the whole AI SDR
                    </CardTitle>
                    <CardDescription className="text-white/50 max-w-2xl">
                      Each check runs the automated tests for one part of the AI SDR on a separate, throwaway
                      database, so nothing is emailed, no CRM is called and no real data is touched.
                    </CardDescription>
                    <div className="flex flex-wrap items-center gap-3 pt-1">
                      <StatusBadge status={allLast?.status} />
                      <Counts run={allLast} />
                      {allLast ? <span className="text-xs text-white/40">{timeAgo(allLast.finished_at)}</span> : null}
                      {allLast ? (
                        <button type="button" className="text-xs text-violet-300 hover:underline"
                          onClick={() => setViewing({ runId: allLast.id, suite: 'all', title: 'Everything' })}>
                          View results
                        </button>
                      ) : null}
                    </div>
                  </div>
                  <Button onClick={() => run('all')} disabled={busy} className="bg-violet-600 hover:bg-violet-500 text-white shrink-0">
                    {starting === 'all' ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <PlayCircle className="w-4 h-4 mr-2" />}
                    Run all checks
                  </Button>
                </CardHeader>
                {current ? (
                  <CardContent className="pt-0">
                    <div className="rounded-lg border border-violet-500/30 bg-violet-500/10 p-3 space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm text-white flex items-center gap-2">
                          <Loader2 className="w-4 h-4 animate-spin text-violet-300" /> Running: {current.suite_title}
                        </span>
                        <button type="button" className="text-xs text-violet-300 hover:underline"
                          onClick={() => setViewing({ runId: current.id, suite: current.suite, title: current.suite_title })}>
                          Watch
                        </button>
                      </div>
                      <Progress run={current} />
                    </div>
                  </CardContent>
                ) : null}
              </Card>

              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {(overview?.suites || []).map((suite) => {
                  const runningThis = current && (current.suite === suite.key || current.suite === 'all');
                  return (
                    <div key={suite.key} className={`${CARD_CLASS} rounded-xl p-4 flex flex-col gap-3 hover:border-violet-500/30 transition-colors`}>
                      <div className="flex items-start justify-between gap-2">
                        <h3 className="text-white font-semibold">{suite.title}</h3>
                        <StatusBadge status={runningThis ? current.status : suite.last?.status} />
                      </div>
                      <p className="text-sm text-white/50 flex-1">{suite.description}</p>
                      <div className="flex items-center gap-2 text-xs text-white/40 min-h-[1rem]">
                        {suite.last && !runningThis ? (
                          <>
                            <Counts run={suite.last} />
                            <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{timeAgo(suite.last.finished_at)}</span>
                          </>
                        ) : null}
                      </div>
                      <div className="flex gap-2">
                        <Button size="sm" onClick={() => run(suite.key)} disabled={busy}
                          className="bg-violet-600 hover:bg-violet-500 text-white">
                          {starting === suite.key ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Play className="w-3.5 h-3.5 mr-1.5" />}
                          Run tests
                        </Button>
                        {suite.last ? (
                          <Button size="sm" variant="outline" className="border-[var(--line-3)] text-white/80 bg-transparent"
                            onClick={() => setViewing({ runId: suite.last.id, suite: suite.key, title: suite.title })}>
                            View results
                          </Button>
                        ) : null}
                      </div>
                    </div>
                  );
                })}
              </div>

              <Card className={CARD_CLASS}>
                <CardHeader>
                  <CardTitle className="text-white text-base">Recent runs</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {(overview?.runs || []).length === 0 ? (
                    <p className="text-sm text-white/50">No checks have been run yet.</p>
                  ) : overview.runs.map((r) => (
                    <button key={r.id} type="button"
                      className={`${ROW_CLASS} w-full rounded-lg px-3 py-2 flex flex-wrap items-center gap-3 text-left`}
                      onClick={() => setViewing({ runId: r.id, suite: r.suite, title: r.suite_title })}>
                      <span className="text-sm text-white min-w-[12rem]">{r.suite_title}</span>
                      <StatusBadge status={r.status} />
                      <Counts run={r} />
                      <span className="ml-auto text-xs text-white/40">
                        {r.started_by ? `${r.started_by} · ` : ''}{timeAgo(r.created_at)}
                      </span>
                    </button>
                  ))}
                </CardContent>
              </Card>
            </>
          )}
        </div>

      <Dialog open={Boolean(viewing)} onOpenChange={(open) => { if (!open) setViewing(null); }}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto bg-[var(--panel-1)] border-[var(--line-2)]">
          <DialogHeader>
            <DialogTitle className="text-white">{viewing?.title}</DialogTitle>
            <DialogDescription className="text-white/50">
              Click a failing test to see why it failed.
            </DialogDescription>
          </DialogHeader>
          {viewRun ? <RunResults run={viewRun} /> : (
            <div className="flex justify-center py-10"><Loader2 className="w-6 h-6 animate-spin text-violet-400" /></div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
};

export default SDRChecksPanel;
