import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  CheckSquare,
  FolderKanban,
  Calendar,
  Bell,
  User,
  ArrowRight,
  AlertTriangle,
  Loader2,
  Clock,
  GraduationCap,
  ChevronRight,
} from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useToast } from '@/components/ui/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import userTaskService from '@/services/userTaskService';
import { API_BASE_URL } from '@/config/apiConfig';
import { isOverdue, isDueThisWeek, getStatusColor, humanStatus } from '@/utils/taskHelpers';
import { awaitsAnswer } from '@/utils/meetingAnswers';
import FrontlineTutorial, { resetTutorial } from '@/components/frontline/FrontlineTutorial';
import { useTutorialNudge } from '@/components/frontline/tourUtils';
import { USER_MAIN_TOUR_KEY, USER_MAIN_TOUR_STEPS } from '@/utils/userTutorialSteps';

/**
 * HomeView — /me/home landing.
 *
 * Real dashboard content: summary tiles, action-items list, quick-jump
 * grid, first-run welcome banner + tour, and a "complete your profile"
 * nudge for accounts that look empty.
 */
export default function HomeView() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { user } = useAuth();

  const [tasks, setTasks] = useState([]);
  const [meetings, setMeetings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tutorialOpen, setTutorialOpen] = useState(false);

  // No auto-launch — the tour button in the header glows until the user
  // takes it, and a short-lived tooltip nudges them the first time they
  // land here in a session. Matches the pattern PM/HR/Frontline use.
  const { glow: tourGlow, tooltip: tourTooltip, dismiss: dismissNudge } = useTutorialNudge(USER_MAIN_TOUR_KEY);

  // Sign-in sends firstName and lastName. It sends no phone or timezone, so
  // those are only asked for when the details carry the field and it is empty;
  // otherwise everyone was told, for good, that their profile was incomplete.
  const firstName = (user?.firstName || user?.fullName || user?.username || user?.email || 'there')
    .split(' ')[0].split('@')[0];

  // Look for missing profile fields to decide whether to nudge.
  const has = (key) => user && Object.prototype.hasOwnProperty.call(user, key);
  const profileGaps = [];
  if (!user?.firstName && !user?.fullName && !user?.username) profileGaps.push('name');
  if ((has('phone') || has('phone_number')) && !user?.phone && !user?.phone_number) profileGaps.push('phone');
  if (has('timezone') && !user?.timezone) profileGaps.push('timezone');
  const profileIncomplete = profileGaps.length > 0;

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const [tRes, mRes] = await Promise.all([
          userTaskService.getMyTasks().catch(() => ({ status: 'error' })),
          fetchMeetings().catch(() => []),
        ]);
        if (cancelled) return;
        if (tRes?.status === 'success') setTasks(tRes.data || []);
        setMeetings(mRes || []);
      } catch (err) {
        if (!cancelled) toast({ title: 'Could not load your dashboard', description: err.message, variant: 'destructive' });
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [toast]);

  const openTasks = tasks.filter((t) => t.status !== 'done');
  const overdueTasks = tasks.filter(isOverdue);
  const dueThisWeek = tasks.filter(isDueThisWeek);
  const pendingInvites = meetings.filter(awaitsAnswer);

  const tiles = [
    { label: 'Open tasks', value: openTasks.length, icon: CheckSquare, to: '/me/tasks' },
    { label: 'Overdue', value: overdueTasks.length, icon: AlertTriangle, to: '/me/tasks', danger: overdueTasks.length > 0 },
    { label: 'Due this week', value: dueThisWeek.length, icon: Clock, to: '/me/tasks' },
    { label: 'Pending invites', value: pendingInvites.length, icon: Calendar, to: '/me/meetings' },
  ];

  const actionItems = [
    ...overdueTasks.slice(0, 3).map((t) => ({
      key: `t${t.id}`,
      title: t.title,
      subtitle: `Overdue • ${t.project_name || 'no project'}`,
      badge: humanStatus(t.status),
      badgeClass: 'bg-red-500/15 text-red-300 border border-red-500/25',
      onClick: () => navigate('/me/tasks'),
    })),
    ...pendingInvites.slice(0, 3).map((m) => ({
      key: `m-${m.source || 'pm'}-${m.id}`,   // ids repeat across agents
      title: m.title,
      subtitle: `Meeting invite • ${m.organizer_name || m.organizer_email || 'organizer'}`,
      badge: 'Respond',
      badgeClass: 'bg-yellow-500/15 text-yellow-300 border border-yellow-500/25',
      onClick: () => navigate('/me/meetings'),
    })),
    ...dueThisWeek
      .filter((t) => !overdueTasks.includes(t))
      .slice(0, 5)
      .map((t) => ({
        key: `w${t.id}`,
        title: t.title,
        subtitle: `Due ${new Date(t.due_date).toLocaleDateString()} • ${t.project_name || 'no project'}`,
        badge: humanStatus(t.status),
        badgeClass: getStatusColor(t.status),
        onClick: () => navigate('/me/tasks'),
      })),
  ].slice(0, 6);

  const quickLinks = [
    // Project managers run their projects from the screen built on the
    // employee API; the company dashboard does not work with their login.
    ...(user?.role === 'project_manager'
      ? [{ to: '/user/dashboard/classic', icon: FolderKanban, label: 'My Projects' }]
      : []),
    { to: '/me/tasks', icon: CheckSquare, label: 'My Tasks' },
    { to: '/me/meetings', icon: Calendar, label: 'My Meetings' },
    { to: '/me/notifications', icon: Bell, label: 'Notifications' },
    { to: '/me/profile', icon: User, label: 'My Profile' },
  ];

  const replayTour = () => {
    dismissNudge();
    resetTutorial(USER_MAIN_TOUR_KEY);
    setTutorialOpen(true);
  };

  // The next seven days, open tasks due on each (UI refresh, 26 Nov 2026: the highlight card's strip). A date-only
  // due_date is read as a local day, not as UTC midnight, which shows the day before west of Greenwich.
  const localDay = (v) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(v || ''));
    const d = m ? new Date(+m[1], +m[2] - 1, +m[3]) : new Date(v);
    d.setHours(0, 0, 0, 0);
    return d;
  };
  const today = localDay(new Date());
  const week = Array.from({ length: 7 }, (_, i) => {
    const day = new Date(today);
    day.setDate(day.getDate() + i);
    const n = openTasks.filter((t) => t.due_date && localDay(t.due_date).getTime() === day.getTime()).length;
    return { key: i, label: i === 0 ? 'Today' : day.toLocaleDateString(undefined, { weekday: 'short' }), n };
  });
  const weekMax = Math.max(1, ...week.map((d) => d.n));
  const now = new Date();
  const dateLine = now.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' });
  const timeLine = now.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  const needs = [
    overdueTasks.length ? plural(overdueTasks.length, 'overdue task', 'overdue tasks') : null,
    pendingInvites.length ? plural(pendingInvites.length, 'meeting invite', 'meeting invites') : null,
  ].filter(Boolean);
  const dotFor = (key) => (key.startsWith('t') ? 'bg-red-500' : key.startsWith('m') ? 'bg-orange-400' : 'bg-primary');

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <style>{`
        @keyframes meTourGlow {
          0%, 100% { box-shadow: 0 0 0 0 hsl(var(--primary) / 0.4), 0 0 0 0 hsl(var(--primary) / 0.2); }
          50%      { box-shadow: 0 0 0 6px hsl(var(--primary) / 0.15), 0 0 0 12px hsl(var(--primary) / 0.08); }
        }
        .me-tour-glow { animation: meTourGlow 1.6s ease-in-out infinite; }
      `}</style>

      {profileIncomplete && (
        <div className="rounded-2xl border border-amber-500/25 bg-amber-500/[0.06] px-4 py-3 flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2 min-w-0">
            <User className="h-4 w-4 text-amber-600 dark:text-amber-300 shrink-0" />
            <p className="text-sm text-foreground/80">
              Your profile is missing {profileGaps.join(', ')}. Filling it out helps teammates reach you.
            </p>
          </div>
          <Link to="/me/profile">
            <Button size="sm" variant="outline" className="h-8 text-xs">Complete profile</Button>
          </Link>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 items-stretch">
        <Card className="lg:col-span-3" data-tour="me-action-items">
          <CardContent className="p-6 sm:p-8">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <p className="inline-flex items-center gap-2 text-sm text-muted-foreground">
                <span className="h-2 w-2 rounded-full bg-emerald-500 shadow-[0_0_0_3px_rgba(16,185,129,0.18)]" />
                {dateLine} · as of {timeLine}
              </p>
              <div className="relative">
                <Button variant="outline" size="sm" onClick={replayTour} className={tourGlow ? 'me-tour-glow' : ''}>
                  <GraduationCap className="h-3.5 w-3.5 mr-1.5" /> Take the Tour
                </Button>
                {tourTooltip && (
                  <div className="hidden sm:block absolute -bottom-11 right-0 z-10 rounded-md border border-primary/40 bg-[var(--panel-4)] px-2.5 py-1.5 text-xs text-foreground shadow-lg pointer-events-none whitespace-nowrap">
                    New here? Take a quick tour
                    <span className="absolute -top-1 right-6 h-2 w-2 bg-[var(--panel-4)] border-t border-l border-primary/40 rotate-45" />
                  </div>
                )}
              </div>
            </div>
            <h2 className="font-heading font-semibold tracking-tight text-5xl sm:text-6xl leading-none mt-5 text-foreground">Hi {firstName}.</h2>
            <p className="mt-4 text-lg text-foreground/80 max-w-xl">
              {loading
                ? 'Looking at your day…'
                : needs.length
                  ? <>Here's what needs your attention today: <b className="text-foreground">{needs.join(' and ')}</b>.</>
                  : dueThisWeek.length
                    ? <>Nothing is late. <b className="text-foreground">{plural(dueThisWeek.length, 'task', 'tasks')}</b> due this week.</>
                    : "You're all caught up. Nice."}
            </p>

            <div className="h-px bg-border my-6" />
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="font-heading font-semibold text-lg text-foreground">Action items</h3>
                <p className="text-sm text-muted-foreground">Most urgent first.</p>
              </div>
              {actionItems.length > 0 && (
                <Button variant="ghost" size="sm" onClick={() => navigate('/me/work')} className="text-muted-foreground">
                  View all <ArrowRight className="h-3.5 w-3.5 ml-1" />
                </Button>
              )}
            </div>
            {loading ? (
              <div className="space-y-3 mt-4">
                {[0, 1, 2].map((i) => <div key={i} className="h-12 rounded-xl bg-muted/60 animate-pulse" />)}
              </div>
            ) : actionItems.length === 0 ? (
              <div className="text-center py-8">
                <CheckSquare className="h-8 w-8 mx-auto text-muted-foreground/50 mb-2" />
                <p className="text-sm text-foreground/80">You're all caught up. Nice.</p>
                <p className="text-xs text-muted-foreground mt-1">Nothing overdue, no pending meeting invites, nothing due this week.</p>
              </div>
            ) : (
              <div className="mt-2 divide-y divide-border">
                {actionItems.map((item) => (
                  <div key={item.key} className="py-1">
                  <button
                    onClick={item.onClick}
                    className="w-full text-left flex items-center gap-4 py-2.5 hover:bg-muted/40 px-2 -mx-2 rounded-xl transition-colors"
                  >
                    <span className={`h-2 w-2 rounded-full shrink-0 ${dotFor(item.key)}`} />
                    <div className="flex-1 min-w-0">
                      <div className="text-[15px] font-semibold text-foreground truncate">{item.title}</div>
                      <div className="text-xs text-muted-foreground mt-0.5 truncate">{item.subtitle}</div>
                    </div>
                    <span className={`text-[11px] px-2.5 py-0.5 rounded-full font-medium capitalize shrink-0 ${item.badgeClass}`}>
                      {item.badge}
                    </span>
                    <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
                  </button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <section className="ui-ink lg:col-span-2 rounded-3xl p-6 sm:p-8 flex flex-col" data-tour="me-summary">
          <div className="flex items-center justify-between">
            <span className="text-base font-medium text-pure-white">My work</span>
            <Link to="/me/tasks" className="text-xs font-semibold text-pure-white/70 hover:text-pure-white">Open my tasks</Link>
          </div>
          <div className="text-sm text-pure-white/60 mt-7">Open tasks</div>
          <div className="font-heading font-semibold text-pure-white text-[88px] leading-none mt-2 tabular-nums">
            {loading ? <span className="inline-block h-16 w-14 rounded-xl bg-pure-white/10 animate-pulse" /> : openTasks.length}
          </div>
          <div className="mt-8 grid grid-cols-7 gap-2 items-end h-44" aria-label="Open tasks due in the next seven days">
            {week.map((d) => (
              <div key={d.key} className="flex flex-col items-center justify-end gap-1.5 h-full">
                <span className="text-[11px] font-semibold text-pure-white/80">{d.n || ''}</span>
                <div className={`w-full max-w-[34px] rounded-lg ${d.n ? 'ui-ink-chart' : 'bg-pure-white/10'}`}
                  style={{ height: `${Math.max(8, (d.n / weekMax) * 120)}px` }} />
                <span className="text-[11px] text-pure-white/55">{d.label}</span>
              </div>
            ))}
          </div>
          <div className="flex-1" />
          <div className="grid grid-cols-3 border-t border-pure-white/10 mt-7 pt-5">
            {tiles.slice(1).map((tile, i) => (
              <Link key={tile.label} to={tile.to} className={`px-3 ${i ? 'border-l border-pure-white/10' : ''}`}>
                <div className="text-xs text-pure-white/60">{tile.label}</div>
                <div className={`font-heading font-semibold text-3xl mt-1.5 tabular-nums ${tile.danger ? 'text-red-300' : 'text-pure-white'}`}>
                  {loading ? '–' : tile.value}
                </div>
              </Link>
            ))}
          </div>
        </section>
      </div>

      <Card data-tour="me-quick-jump">
        <CardContent className="p-6 sm:p-8">
          <h3 className="font-heading font-semibold text-lg text-foreground">Jump to</h3>
          <p className="text-sm text-muted-foreground">Everything that's yours, one click away.</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-5">
            {quickLinks.map((q) => (
              <Link key={q.to} to={q.to} className="group rounded-2xl border border-border/70 bg-card/70 p-4 flex flex-col gap-3 hover:border-primary/40 hover:shadow-md transition-all">
                <span className="h-10 w-10 rounded-xl bg-primary/10 text-primary dark:text-violet-300 flex items-center justify-center">
                  <q.icon className="h-[18px] w-[18px]" />
                </span>
                <span className="flex items-center justify-between text-sm font-semibold text-foreground">
                  {q.label}
                  <ArrowRight className="h-3.5 w-3.5 text-muted-foreground group-hover:text-primary group-hover:translate-x-0.5 transition-all" />
                </span>
              </Link>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="text-xs text-muted-foreground text-center">
        Prefer the classic view? It still lives at{' '}
        <Link to="/user/dashboard/classic" className="text-primary dark:text-violet-300 underline">/user/dashboard/classic</Link>.
      </div>

      <FrontlineTutorial
        open={tutorialOpen}
        onClose={() => setTutorialOpen(false)}
        steps={USER_MAIN_TOUR_STEPS}
        storageKey={USER_MAIN_TOUR_KEY}
      />
    </div>
  );
}

async function fetchMeetings() {
  const token = localStorage.getItem('auth_token');
  if (!token) return [];
  const res = await fetch(`${API_BASE_URL}/meetings`, {
    headers: { 'Authorization': `Token ${token}` },
  });
  if (!res.ok) return [];
  const data = await res.json();
  return data?.data?.meetings || [];
}

export { fetchMeetings };
