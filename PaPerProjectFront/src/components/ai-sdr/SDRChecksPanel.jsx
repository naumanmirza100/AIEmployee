import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import {
  Loader2, PlayCircle, CheckCircle2, XCircle, AlertTriangle, MinusCircle,
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

const RANK = { error: 0, failed: 0, skipped: 1, passed: 2 };
const isBad = (t) => t.outcome === 'failed' || t.outcome === 'error';

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
  const bad = isBad(test);
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

// One area of the AI SDR in the results: collapsed when everything in it passed.
const AreaResults = ({ title, tests }) => {
  const bad = tests.filter(isBad).length;
  const passed = tests.filter((t) => t.outcome === 'passed').length;
  const [open, setOpen] = useState(bad > 0);
  const Icon = bad ? XCircle : CheckCircle2;
  return (
    <div className={`${ROW_CLASS} rounded-lg`}>
      <button type="button" className="w-full flex items-center gap-2 px-3 py-2 text-left" onClick={() => setOpen((o) => !o)}>
        {open ? <ChevronDown className="w-4 h-4 text-white/40" /> : <ChevronRight className="w-4 h-4 text-white/40" />}
        <Icon className={`w-4 h-4 shrink-0 ${bad ? 'text-red-400' : 'text-emerald-400'}`} />
        <span className="flex-1 text-sm text-white">{title}</span>
        <span className={`text-xs ${bad ? 'text-red-300' : 'text-white/50'}`}>
          {bad ? `${bad} failing · ` : ''}{passed}/{tests.length} passed
        </span>
      </button>
      {open ? (
        <div className="space-y-1.5 px-3 pb-3">
          {[...tests].sort((a, b) => (RANK[a.outcome] ?? 2) - (RANK[b.outcome] ?? 2)).map((t) => <TestRow key={t.id} test={t} />)}
        </div>
      ) : null}
    </div>
  );
};

const RunResults = ({ run, areas }) => {
  // Every test under the first area of the AI SDR it belongs to; areas with failures first.
  const groups = useMemo(() => {
    const titles = Object.fromEntries((areas || []).map((a) => [a.key, a.title]));
    const byArea = new Map();
    (run.tests || []).forEach((t) => {
      const key = (t.suites || [])[0] || 'other';
      if (!byArea.has(key)) byArea.set(key, []);
      byArea.get(key).push(t);
    });
    return [...byArea.entries()]
      .map(([key, tests]) => ({ key, title: titles[key] || 'Other', tests, bad: tests.some(isBad) }))
      .sort((a, b) => Number(b.bad) - Number(a.bad));
  }, [run.tests, areas]);

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
      <div className="space-y-2">
        {groups.map((g) => <AreaResults key={g.key} title={g.title} tests={g.tests} />)}
      </div>
    </div>
  );
};

/**
 * The AI SDR's automated tests as one field: Run all tests, the latest result, and the results by area in a
 * dialog. Used by the Super Admin panel (/admin/sdr-checks) and by AI SDR → Tests for a company's owner or admin.
 * `api` is { getOverview, startRun, getRun } for the door in use. The tests run on the server, in a separate
 * process on a throwaway database (ai_sdr_agent/admin_checks.py).
 */
const SDRChecksPanel = ({ api }) => {
  const { toast } = useToast();
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [viewingId, setViewingId] = useState(null);  // the run in the results dialog
  const [viewRun, setViewRun] = useState(null);
  const watchedRun = useRef(null);

  const load = useCallback(async () => {
    try {
      const data = await api.getOverview();
      setOverview(data);
      return data;
    } catch (e) {
      toast({ title: 'Could not load the tests', description: String(e.message || e), variant: 'destructive' });
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
            title: ok ? 'All tests passed' : `Tests: ${STATUS_META[done.status]?.label.toLowerCase()}`,
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
    if (!viewingId) { setViewRun(null); return undefined; }
    let cancelled = false;
    const fetchRun = async () => {
      try {
        const run = await api.getRun(viewingId);
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
  }, [api, viewingId, toast]);

  const runAll = async () => {
    setStarting(true);
    try {
      await api.startRun('all');
      await load();
    } catch (e) {
      toast({ title: 'Could not start the tests', description: String(e.message || e), variant: 'destructive' });
    } finally {
      setStarting(false);
    }
  };

  if (loading) {
    return <div className="flex justify-center py-10"><Loader2 className="w-6 h-6 animate-spin text-violet-400" /></div>;
  }

  const last = overview?.all_last;
  const shown = current || last;

  return (
    <>
      <div className={`${CARD_CLASS} rounded-xl p-4 sm:p-5 space-y-4`}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-3">
            <ListChecks className="w-5 h-5 text-violet-400" />
            <StatusBadge status={current ? current.status : last?.status} />
            {current ? (
              <span className="text-sm text-white/70">Running the tests…</span>
            ) : last ? (
              <>
                <Counts run={last} />
                <span className="flex items-center gap-1 text-xs text-white/40"><Clock className="w-3 h-3" />{timeAgo(last.finished_at)}</span>
              </>
            ) : (
              <span className="text-sm text-white/50">The tests have not been run yet.</span>
            )}
          </div>
          <div className="flex gap-2 shrink-0">
            {shown ? (
              <Button variant="outline" className="border-[var(--line-3)] text-white/80 bg-transparent" onClick={() => setViewingId(shown.id)}>
                View results
              </Button>
            ) : null}
            <Button onClick={runAll} disabled={Boolean(current) || starting} className="bg-violet-600 hover:bg-violet-500 text-white">
              {starting || current ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <PlayCircle className="w-4 h-4 mr-2" />}
              Run all tests
            </Button>
          </div>
        </div>
        {current ? <Progress run={current} /> : null}
      </div>

      <Dialog open={Boolean(viewingId)} onOpenChange={(open) => { if (!open) setViewingId(null); }}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto bg-[var(--panel-1)] border-[var(--line-2)]">
          <DialogHeader>
            <DialogTitle className="text-white">Automated test results</DialogTitle>
            <DialogDescription className="text-white/50">
              By area of the AI SDR. Open an area to see its tests; click a failing test to see why it failed.
            </DialogDescription>
          </DialogHeader>
          {viewRun ? <RunResults run={viewRun} areas={overview?.suites} /> : (
            <div className="flex justify-center py-10"><Loader2 className="w-6 h-6 animate-spin text-violet-400" /></div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
};

export default SDRChecksPanel;
