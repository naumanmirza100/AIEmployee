import React, { useCallback, useEffect, useState } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import {
  Loader2, FlaskConical, Plus, Trash2, RefreshCw, AlertTriangle, Copy, Eye, EyeOff, Building2, Users, Bot, KeyRound,
} from 'lucide-react';
import DashboardNavbar from '@/components/common/DashboardNavbar';
import { getAdminNavItems } from '@/utils/adminNavItems';
import { useAuth } from '@/contexts/AuthContext';
import { useBackgroundUpload } from '@/components/shared/BackgroundUploadManager';
import testDataService from '@/services/adminTestDataService';

const GRADIENT_BG = 'var(--app-page-bg)';
const fmt = (n) => Number(n || 0).toLocaleString();
const formatDate = (iso) => (iso ? new Date(iso).toLocaleString() : '—');
const isBusy = (run) => run && (run.status === 'queued' || run.status === 'running');

// Runs this browser tab already shows in the bottom-right pill, so coming back to the page doesn't add a second one.
const followed = new Set();

const JOB_LABELS = {
  load: {
    title: 'Adding test data',
    startedTitle: 'Adding test data',
    startedText: 'The demo companies are being added in the background. Click the pill at the bottom right to see how far it has got.',
    doneTitle: 'Test data added',
    doneText: 'The demo companies are ready. Their logins and password are on the Test data page.',
    failedTitle: 'The test data could not be added',
    pill: 'Adding test data',
    progress: (u) => (u.indexTotal ? `Adding ${fmt(u.indexDone)} of ${fmt(u.indexTotal)} records` : 'Starting…'),
  },
  remove: {
    title: 'Removing test data',
    startedTitle: 'Removing test data',
    startedText: 'The demo companies are being removed in the background.',
    doneTitle: 'Test data removed',
    doneText: 'The demo companies and everything in them have been removed.',
    failedTitle: 'The test data could not be removed',
    pill: 'Removing test data',
    progress: (u) => (u.indexTotal ? `Removed ${fmt(u.indexDone)} of ${fmt(u.indexTotal)} records` : 'Starting…'),
  },
};

const CopyButton = ({ value, label }) => {
  const { toast } = useToast();
  if (!value) return null;
  return (
    <Button
      type="button" size="sm" variant="ghost" className="h-7 w-7 p-0" title={`Copy ${label}`} aria-label={`Copy ${label}`}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          toast({ title: `${label[0].toUpperCase()}${label.slice(1)} copied` });
        } catch {
          toast({ title: 'Could not copy', description: 'Select it and copy it by hand.', variant: 'destructive' });
        }
      }}
    >
      <Copy className="w-3.5 h-3.5" />
    </Button>
  );
};

const LoginTable = ({ rows, showUsername }) => (
  <div className="overflow-x-auto">
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-xs text-muted-foreground border-b border-white/10">
          <th className="py-2 pr-3 font-medium">Name</th>
          <th className="py-2 pr-3 font-medium">Email</th>
          {showUsername && <th className="py-2 pr-3 font-medium">Username</th>}
          <th className="py-2 pr-3 font-medium">Role</th>
          <th className="py-2 font-medium">Status</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-white/5">
        {rows.map((r, i) => (
          <tr key={`${r.email}-${i}`}>
            <td className="py-2 pr-3 whitespace-nowrap">{r.name || '—'}</td>
            <td className="py-2 pr-3">
              <span className="inline-flex items-center gap-1 break-all">{r.email || '—'}<CopyButton value={r.email} label="email" /></span>
            </td>
            {showUsername && <td className="py-2 pr-3 text-muted-foreground break-all">{r.username}</td>}
            <td className="py-2 pr-3 whitespace-nowrap">{r.role || '—'}</td>
            <td className="py-2 whitespace-nowrap">
              {r.active ? 'Active' : <span className="text-muted-foreground">Switched off</span>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const CompanyCard = ({ snap }) => {
  const [showPassword, setShowPassword] = useState(false);
  const dashboard = snap.dashboard_logins || [];
  const employees = snap.employee_logins || [];
  const agents = snap.agents || [];
  return (
    <Card className="bg-white/[0.02]">
      <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0 flex-wrap">
        <div className="space-y-1 min-w-0">
          <CardTitle className="text-base flex items-center gap-2 flex-wrap">
            <Building2 className="w-4 h-4 text-violet-400 shrink-0" /> {snap.company_name}
            {snap.loaded
              ? <Badge variant="outline" className="rounded-md bg-emerald-500/15 text-emerald-400 border-emerald-500/30">Added</Badge>
              : <Badge variant="outline" className="rounded-md text-muted-foreground">Not added</Badge>}
          </CardTitle>
          <CardDescription>
            {snap.label}. {fmt(snap.rows)} records, saved {formatDate(snap.made_at)}
            {snap.loaded && snap.loaded_at ? ` · added ${formatDate(snap.loaded_at)}` : ''}
          </CardDescription>
        </div>
      </CardHeader>
      {snap.loaded && (
        <CardContent className="space-y-6">
          <div className="rounded-md border border-violet-500/25 bg-violet-500/[0.06] p-3 space-y-1">
            <div className="text-xs font-semibold flex items-center gap-1.5"><KeyRound className="w-3.5 h-3.5" /> Password for every login below</div>
            {snap.password ? (
              <div className="flex items-center gap-1 flex-wrap">
                <code className="font-mono text-sm break-all">{showPassword ? snap.password : '•'.repeat(snap.password.length)}</code>
                <Button type="button" size="sm" variant="ghost" className="h-7 w-7 p-0"
                  title={showPassword ? 'Hide' : 'Show'} aria-label={showPassword ? 'Hide password' : 'Show password'}
                  onClick={() => setShowPassword((v) => !v)}>
                  {showPassword ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                </Button>
                <CopyButton value={snap.password} label="password" />
              </div>
            ) : (
              <div className="text-sm text-muted-foreground">Not known on this server. Remove the test data and add it again to get a new one.</div>
            )}
            <div className="text-xs text-muted-foreground">
              It is new each time the test data is added. Company logins sign in at /company/login, employees at /login.
            </div>
          </div>

          <div className="space-y-2">
            <div className="text-sm font-semibold flex items-center gap-1.5"><Bot className="w-4 h-4" /> Agents bought ({agents.length})</div>
            {agents.length ? (
              <div className="flex flex-wrap gap-1.5">
                {agents.map((a) => <Badge key={a} variant="outline" className="rounded-md">{a}</Badge>)}
              </div>
            ) : <div className="text-sm text-muted-foreground">None.</div>}
          </div>

          <div className="space-y-2">
            <div className="text-sm font-semibold flex items-center gap-1.5"><Building2 className="w-4 h-4" /> Company logins ({dashboard.length})</div>
            <p className="text-xs text-muted-foreground">The company's own dashboard: owners, managers and members. Sign in at /company/login.</p>
            {dashboard.length ? <LoginTable rows={dashboard} /> : <div className="text-sm text-muted-foreground">None.</div>}
          </div>

          <div className="space-y-2">
            <div className="text-sm font-semibold flex items-center gap-1.5"><Users className="w-4 h-4" /> Employee logins ({employees.length})</div>
            <p className="text-xs text-muted-foreground">The company's people, who get tasks, leave and meetings. Sign in at /login with the email.</p>
            {employees.length ? <LoginTable rows={employees} showUsername={employees.some((r) => r.username && r.username !== r.email)} /> : <div className="text-sm text-muted-foreground">None.</div>}
          </div>
        </CardContent>
      )}
    </Card>
  );
};

// Super admin only: add the demo companies (the ones the agent videos and the client showcase were made with) to the
// database in the background, see their logins, and remove them again. See core/demo_data.py.
const AdminTestDataPage = () => {
  const navigate = useNavigate();
  const { logout, user } = useAuth();
  const { toast } = useToast();
  const { startUpload } = useBackgroundUpload();
  const [snapshots, setSnapshots] = useState([]);
  const [run, setRun] = useState(null);
  const [lastRun, setLastRun] = useState(null);
  const [loading, setLoading] = useState(true);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [starting, setStarting] = useState(false);

  const handleLogout = async () => {
    try {
      await logout();
      navigate('/login');
    } catch (error) {
      console.error('Logout error:', error);
    }
  };

  const load = useCallback(async () => {
    try {
      const resp = await testDataService.getTestData();
      setSnapshots(resp?.snapshots || []);
      setRun(resp?.running || null);
      setLastRun(resp?.last || null);
    } catch (e) {
      toast({ title: 'Could not load the test data', description: String(e.message || e), variant: 'destructive' });
    } finally { setLoading(false); }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  // Show a run in the bottom-right pill (also one already running when the page was opened).
  const follow = useCallback((action, existing) => {
    const labels = JOB_LABELS[action] || JOB_LABELS.load;
    if (existing) followed.add(existing.id);
    startUpload({
      kind: 'job',
      title: labels.title,
      agent: 'admin',
      labels,
      quiet: !!existing,
      upload: async () => {
        if (existing) return { data: existing };
        setStarting(true);
        try {
          const resp = await testDataService.startTestDataJob(action);
          followed.add(resp?.data?.id);
          setRun(resp?.data || null);
          return resp;
        } finally { setStarting(false); }
      },
      poll: (id) => testDataService.getTestDataRun(id),
      onDone: () => load(),
    });
  }, [startUpload, load]);

  useEffect(() => {
    if (run && isBusy(run) && !followed.has(run.id)) follow(run.action, run);
  }, [run, follow]);

  // While a run is going, keep the progress on this page current too; reload everything when it ends.
  const busy = isBusy(run);
  useEffect(() => {
    if (!busy) return undefined;
    const timer = setInterval(async () => {
      try {
        const resp = await testDataService.getTestDataRun(run.id);
        const next = resp?.data;
        if (!next) return;
        if (isBusy(next)) setRun(next); else { setRun(null); load(); }
      } catch { /* try again next time */ }
    }, 2000);
    return () => clearInterval(timer);
  }, [busy, run?.id, load]);

  const anyLoaded = snapshots.some((s) => s.loaded);
  const allLoaded = snapshots.length > 0 && snapshots.every((s) => s.loaded);
  const showLastError = !busy && lastRun?.status === 'failed' && lastRun?.processing_error;

  return (
    <>
      <Helmet><title>Super Admin — Test data</title></Helmet>
      <div className="min-h-screen overflow-x-hidden" style={{ background: GRADIENT_BG }}>
        <DashboardNavbar
          icon={FlaskConical}
          title="Test data"
          subtitle="The demo companies, their logins and their agents"
          user={user}
          userRole="Admin"
          onLogout={handleLogout}
          showNavTabs
          activeSection="admin-test-data"
          navItems={getAdminNavItems(navigate)}
        />

        <div className="container mx-auto px-4 py-8 max-w-5xl space-y-6">
          <Card className="border-violet-500/20 bg-white/[0.02]">
            <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0 flex-wrap">
              <div className="space-y-1.5 min-w-0">
                <CardTitle className="text-lg">Add or remove the test data</CardTitle>
                <CardDescription className="max-w-2xl">
                  Adds the demo companies the agent videos and the client showcase were made with, with their people,
                  projects and every agent's data. Dates are moved forward so it looks current. Each company gets one
                  new password, shown below. Their mailboxes, CRM connections and campaigns stay switched off, so
                  nothing is emailed or synced from them. Removing deletes the companies and everything in them,
                  including anything added to them since.
                </CardDescription>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <Button onClick={() => follow('load')} disabled={loading || starting || busy || allLoaded || !snapshots.length}
                  className="bg-gradient-to-r from-violet-600 to-fuchsia-600 text-white">
                  {busy && run?.action === 'load' ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />}
                  {busy && run?.action === 'load' ? 'Adding…' : 'Add test data'}
                </Button>
                <Button variant="outline" onClick={() => setConfirmRemove(true)} disabled={loading || starting || busy || !anyLoaded}
                  className="text-rose-400 hover:text-rose-300">
                  {busy && run?.action === 'remove' ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Trash2 className="w-4 h-4 mr-2" />}
                  {busy && run?.action === 'remove' ? 'Removing…' : 'Remove test data'}
                </Button>
              </div>
            </CardHeader>
            {(busy || showLastError) && (
              <CardContent className="space-y-2">
                {busy && (
                  <>
                    <div className="flex items-center justify-between text-xs text-muted-foreground gap-2">
                      <span className="flex items-center gap-1.5 min-w-0">
                        <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
                        <span className="truncate">
                          {run.status === 'queued'
                            ? 'Waiting to start…'
                            : `${run.action === 'remove' ? 'Removed' : 'Added'} ${fmt(run.chunks_processed)} of ${fmt(run.chunks_total)} records${run.step ? ` · ${run.step}` : ''}`}
                        </span>
                      </span>
                      <span className="font-mono">{run.percent || 0}%</span>
                    </div>
                    <div className="h-1.5 rounded bg-white/[0.06] overflow-hidden">
                      <div className="h-full bg-gradient-to-r from-violet-500 to-indigo-500 transition-all duration-300"
                        style={{ width: `${run.percent || 0}%` }} />
                    </div>
                  </>
                )}
                {showLastError && (
                  <div className="text-xs text-rose-400 flex items-start gap-1">
                    <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-px" />
                    <span>The last {lastRun.action === 'remove' ? 'removal' : 'add'} failed: {lastRun.processing_error}</span>
                  </div>
                )}
              </CardContent>
            )}
          </Card>

          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold">Demo companies</h2>
            <Button variant="ghost" size="sm" onClick={load} title="Refresh"><RefreshCw className="w-4 h-4" /></Button>
          </div>

          {loading ? (
            <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-violet-400" /></div>
          ) : snapshots.length === 0 ? (
            <Card className="bg-white/[0.02]">
              <CardContent className="py-8 text-sm text-muted-foreground text-center">
                There is no test data on this server yet. It is saved from a demo company with the
                {' '}<code>demo_snapshot</code> command.
              </CardContent>
            </Card>
          ) : (
            snapshots.map((s) => <CompanyCard key={s.key} snap={s} />)
          )}
        </div>
      </div>

      <Dialog open={confirmRemove} onOpenChange={setConfirmRemove}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove the test data?</DialogTitle>
            <DialogDescription>
              {snapshots.filter((s) => s.loaded).map((s) => s.company_name).join(' and ')} will be deleted with
              everything in them: their logins, people and every agent's data, including anything added since. You
              can add the test data again afterwards.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmRemove(false)}>Cancel</Button>
            <Button variant="destructive" onClick={() => { setConfirmRemove(false); follow('remove'); }}>Remove</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default AdminTestDataPage;
