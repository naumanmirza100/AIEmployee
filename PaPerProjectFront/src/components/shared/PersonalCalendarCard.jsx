import React, { useEffect, useState } from 'react';
import { AlertTriangle, CalendarClock, CheckCircle2, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { useToast } from '@/components/ui/use-toast';
import { api } from '@/services/api';
import { companyApi } from '@/services/companyAuthService';

/**
 * A person's own Google or Outlook calendar (core/personal_calendars.py, 24 Nov 2026).
 *
 * Its busy times (times only) count when any agent books a meeting, and the meetings the agents book for the
 * person go into it. `side` says who is signed in: 'company' (a dashboard login, through the employee login it
 * maps to) or 'employee' (My Space).
 */
const PATHS = {
  company: { base: '/company/my-calendar', client: companyApi },
  employee: { base: '/me/calendar', client: api },
};

const PROVIDERS = [
  { key: 'google', label: 'Google Calendar' },
  { key: 'microsoft', label: 'Outlook' },
];

const ago = (iso) => {
  if (!iso) return 'not yet';
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  return hours < 24 ? `${hours} h ago` : new Date(iso).toLocaleString();
};

export default function PersonalCalendarCard({ side = 'employee', returnTo, className = '' }) {
  const { toast } = useToast();
  const { base, client } = PATHS[side] || PATHS.employee;
  const [state, setState] = useState(null);
  const [working, setWorking] = useState('');

  const load = async () => {
    try {
      const res = await client.get(base);
      setState(res?.data || null);
    } catch (e) {
      setState({ error: e?.data?.message || e?.message || 'Could not load your calendar.' });
    }
  };

  useEffect(() => {
    load();
    // Back from the sign-in: say how it went once, then tidy the address.
    const params = new URLSearchParams(window.location.search);
    if (params.get('mycal') === 'connected' || params.get('mycal_error')) {
      if (params.get('mycal') === 'connected') {
        toast({ title: 'Your calendar is connected', description: 'Its busy times now count when meetings are booked.' });
      } else {
        toast({ title: 'Calendar not connected', description: params.get('mycal_error'), variant: 'destructive' });
      }
      params.delete('mycal');
      params.delete('mycal_error');
      const rest = params.toString();
      window.history.replaceState({}, '', window.location.pathname + (rest ? `?${rest}` : ''));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const run = async (what, call, done) => {
    setWorking(what);
    try {
      const res = await call();
      if (res?.data) setState(res.data);
      if (done) done(res);
    } catch (e) {
      toast({ title: 'That did not work', description: e?.data?.message || e?.message, variant: 'destructive' });
    } finally {
      setWorking('');
    }
  };

  const connect = (provider) => run(provider, () => client.post(`${base}/connect`, {
    provider, return_to: returnTo || window.location.pathname,
  }), (res) => { if (res?.data?.authUrl) window.location.href = res.data.authUrl; });

  const change = (patch) => run('patch', () => client.patch(base, patch));
  const syncNow = () => run('sync', () => client.post(`${base}/sync`), (res) => {
    if (res?.message) toast({ title: res.message });
  });
  const disconnect = () => {
    if (!window.confirm('Disconnect your calendar? Its busy times stop counting, and the meetings the agents put in it are taken out.')) return;
    run('delete', () => client.delete(base), () => toast({ title: 'Your calendar is disconnected' }));
  };

  const offered = state?.offered || {};
  const noneOffered = state && !state.error && !offered.google && !offered.microsoft;

  return (
    <div className={`rounded-2xl border border-white/[0.08] p-5 flex flex-col ${className}`}
         style={{ background: 'hsl(var(--sfr-0e0a1a) / 0.7)' }} data-testid="personal-calendar">
      <div className="flex items-start gap-3">
        <div className="flex items-center justify-center w-11 h-11 rounded-xl shrink-0 bg-violet-500/80">
          <CalendarClock className="h-6 w-6 text-white" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold text-white">My own calendar</h3>
            {state?.connected && (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-400/10 border border-emerald-400/30 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
                <CheckCircle2 className="h-3 w-3" /> {state.providerLabel}
              </span>
            )}
          </div>
          <p className="text-sm text-white/55 mt-1 leading-relaxed">
            Your Google or Outlook calendar. Its busy times (times only, no titles) count when any agent books a
            meeting, and the meetings the agents book for you go into it.
          </p>
        </div>
      </div>

      <div className="mt-4 pt-4 border-t border-white/[0.06] space-y-3">
        {!state ? (
          <Loader2 className="h-4 w-4 animate-spin text-white/50" />
        ) : state.error ? (
          <p className="text-xs text-red-300">{state.error}</p>
        ) : !state.linked ? (
          <p className="flex items-start gap-1.5 text-xs text-amber-300" data-testid="personal-calendar-not-linked">
            <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" /> {state.notLinkedReason}
          </p>
        ) : !state.connected ? (
          <>
            <div className="flex flex-wrap gap-2">
              {PROVIDERS.map((p) => (
                <Button key={p.key} size="sm" variant="outline" disabled={!!working || !offered[p.key]}
                        onClick={() => connect(p.key)} data-testid={`personal-calendar-connect-${p.key}`}
                        className="rounded-full border-white/15 text-white/85 hover:text-white">
                  {working === p.key ? <Loader2 className="h-4 w-4 animate-spin" /> : `Connect ${p.label}`}
                </Button>
              ))}
            </div>
            {noneOffered ? (
              <p className="text-[11px] text-amber-400/80">Not set up on this server yet. Contact support to enable it.</p>
            ) : (!offered.google || !offered.microsoft) && (
              <p className="text-[11px] text-white/40">
                {offered.google ? 'Outlook' : 'Google Calendar'} isn't set up on this server yet.
              </p>
            )}
          </>
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
              <span className="text-white/70 truncate">{state.accountEmail || state.providerLabel}</span>
              <span className="text-white/45">Synced {ago(state.lastSyncedAt)} · every 15 minutes</span>
            </div>
            {state.lastError && (
              <p className="flex items-start gap-1.5 text-xs text-amber-300">
                <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" /> {state.lastError}
              </p>
            )}
            <label className="flex items-center justify-between gap-3 text-sm text-white/80">
              <span>Count its busy times <span className="text-white/40">({state.busyCount} ahead)</span></span>
              <Switch checked={!!state.readBusy} disabled={!!working} onCheckedChange={(v) => change({ readBusy: v })} />
            </label>
            <label className="flex items-center justify-between gap-3 text-sm text-white/80">
              <span>Add the agents' meetings to it <span className="text-white/40">({state.pushedCount} in it)</span></span>
              <Switch checked={!!state.pushEvents} disabled={!!working} onCheckedChange={(v) => change({ pushEvents: v })} />
            </label>
            <div className="flex flex-wrap gap-2 pt-1">
              <Button size="sm" variant="outline" onClick={syncNow} disabled={!!working}
                      className="rounded-full border-white/15 text-white/80 hover:text-white">
                {working === 'sync' ? <Loader2 className="h-4 w-4 animate-spin" /> : <><RefreshCw className="h-3.5 w-3.5 mr-1" /> Sync now</>}
              </Button>
              <Button size="sm" variant="outline" onClick={disconnect} disabled={!!working}
                      className="rounded-full border-white/15 text-white/60 hover:text-white">
                {working === 'delete' ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Disconnect'}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
