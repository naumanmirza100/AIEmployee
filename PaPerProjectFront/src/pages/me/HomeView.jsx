import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  CheckSquare,
  Calendar,
  Bell,
  User,
  ArrowRight,
  AlertTriangle,
  Loader2,
  Clock,
  GraduationCap,
} from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useToast } from '@/components/ui/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import userTaskService from '@/services/userTaskService';
import { API_BASE_URL } from '@/config/apiConfig';
import { isOverdue, isDueThisWeek, getStatusColor, humanStatus } from '@/utils/taskHelpers';
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

  const firstName = (user?.fullName || user?.username || user?.email || 'there')
    .split(' ')[0].split('@')[0];

  // Look for missing profile fields to decide whether to nudge.
  const profileGaps = [];
  if (!user?.fullName && !user?.username) profileGaps.push('name');
  if (!user?.phone && !user?.phone_number) profileGaps.push('phone');
  if (!user?.timezone) profileGaps.push('timezone');
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
  const pendingInvites = meetings.filter((m) =>
    (m.my_status === 'pending' || m.my_status === 'counter_proposed' ||
     m.status === 'pending' || m.status === 'counter_proposed')
    && m.status !== 'withdrawn' && m.my_status !== 'accepted',
  );

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
      key: `m${m.id}`,
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

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="text-white">
          <h2 className="text-2xl font-bold">Hi {firstName} 👋</h2>
          <p className="text-white/60 mt-1 text-sm">Here's what needs your attention today.</p>
        </div>
        <div className="relative">
          <Button
            variant="outline"
            size="sm"
            onClick={replayTour}
            className={`border-violet-500/40 text-violet-200 hover:bg-violet-500/10 hover:text-violet-100 ${tourGlow ? 'me-tour-glow' : ''}`}
          >
            <GraduationCap className="h-3.5 w-3.5 mr-1.5" /> Take the Tour
          </Button>
          {tourTooltip && (
            <div className="absolute -bottom-11 right-0 z-10 rounded-md border border-violet-400/40 bg-[#161630] px-2.5 py-1.5 text-xs text-white/90 shadow-lg pointer-events-none whitespace-nowrap">
              👋 New here? Take a quick tour
              <span className="absolute -top-1 right-6 h-2 w-2 bg-[#161630] border-t border-l border-violet-400/40 rotate-45" />
            </div>
          )}
        </div>
      </div>
      <style>{`
        @keyframes meTourGlow {
          0%, 100% { box-shadow: 0 0 0 0 rgba(139, 92, 246, 0.4), 0 0 0 0 rgba(139, 92, 246, 0.2); }
          50%      { box-shadow: 0 0 0 6px rgba(139, 92, 246, 0.15), 0 0 0 12px rgba(139, 92, 246, 0.08); }
        }
        .me-tour-glow { animation: meTourGlow 1.6s ease-in-out infinite; }
      `}</style>

      {profileIncomplete && (
        <div className="rounded-lg border border-amber-500/25 bg-amber-500/[0.06] p-3 flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2 min-w-0">
            <User className="h-4 w-4 text-amber-300 shrink-0" />
            <p className="text-xs text-amber-100/90">
              Your profile is missing {profileGaps.join(', ')}. Filling it out helps teammates reach you.
            </p>
          </div>
          <Link to="/me/profile">
            <Button size="sm" variant="outline"
              className="border-amber-500/40 text-amber-200 hover:bg-amber-500/10 hover:text-amber-100 h-7 text-xs">
              Complete profile
            </Button>
          </Link>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-tour="me-summary">
        {tiles.map((tile) => (
          <Link key={tile.label} to={tile.to} className="group">
            <div className={`rounded-lg border p-3 transition-colors ${
              tile.danger
                ? 'border-red-500/30 bg-red-500/[0.06] group-hover:bg-red-500/[0.1]'
                : 'border-white/10 bg-white/[0.03] group-hover:bg-white/[0.06]'
            }`}>
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-2xl font-bold text-white">
                    {loading ? <span className="inline-block h-6 w-6 rounded bg-white/[0.06] animate-pulse" /> : tile.value}
                  </div>
                  <div className="text-[11px] text-white/50 mt-0.5">{tile.label}</div>
                </div>
                <tile.icon className={`h-5 w-5 ${tile.danger ? 'text-red-400' : 'text-white/40 group-hover:text-violet-300'}`} />
              </div>
            </div>
          </Link>
        ))}
      </div>

      <Card className="bg-white/[0.04] border-white/[0.08]" data-tour="me-action-items">
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-white text-base">Action items</CardTitle>
            <CardDescription className="text-white/50">
              The top few things worth handling right now
            </CardDescription>
          </div>
          {actionItems.length > 0 && (
            <Button variant="ghost" size="sm" onClick={() => navigate('/me/tasks')} className="text-white/60 hover:text-white">
              View all <ArrowRight className="h-3.5 w-3.5 ml-1" />
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center gap-2 text-white/50 text-sm py-8 justify-center">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </div>
          ) : actionItems.length === 0 ? (
            <div className="text-center py-8">
              <CheckSquare className="h-8 w-8 mx-auto text-white/25 mb-2" />
              <p className="text-sm text-white/60">You're all caught up. Nice.</p>
              <p className="text-[11px] text-white/40 mt-1">
                Nothing overdue, no pending meeting invites, nothing due this week.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-white/5">
              {actionItems.map((item) => (
                <button
                  key={item.key}
                  onClick={item.onClick}
                  className="w-full text-left flex items-center justify-between py-3 hover:bg-white/[0.03] px-2 -mx-2 rounded-md transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-white truncate">{item.title}</div>
                    <div className="text-[11px] text-white/50 mt-0.5 truncate">{item.subtitle}</div>
                  </div>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium capitalize shrink-0 ml-3 ${item.badgeClass}`}>
                    {item.badge}
                  </span>
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <div data-tour="me-quick-jump">
        <h3 className="text-sm font-semibold text-white/70 mb-2 px-1">Jump to</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {quickLinks.map((q) => (
            <Link key={q.to} to={q.to} className="group">
              <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 hover:bg-white/[0.06] hover:border-violet-500/30 transition-colors flex items-center gap-2">
                <q.icon className="h-4 w-4 text-violet-300" />
                <span className="text-sm text-white">{q.label}</span>
                <ArrowRight className="h-3.5 w-3.5 text-white/30 group-hover:text-violet-300 group-hover:translate-x-0.5 transition-all ml-auto" />
              </div>
            </Link>
          ))}
        </div>
      </div>

      <div className="text-[11px] text-white/40 text-center">
        Prefer the classic view? It still lives at{' '}
        <Link to="/user/dashboard/classic" className="text-violet-300 hover:text-violet-200 underline">/user/dashboard/classic</Link>.
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
