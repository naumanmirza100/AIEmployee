/**
 * HRManagerTeamTab — direct-reports rollup for the calling manager.
 * Backend: GET /hr/manager/team.
 *
 * Each report card shows leave balances, pending requests waiting on the
 * manager, upcoming meetings in the next 14 days, and open goals. Empty state
 * = caller isn't a manager.
 */
import React, { useEffect, useState } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import {
  Loader2, Users, RefreshCw, ClipboardList, CalendarClock, Target, AlertCircle,
} from 'lucide-react';
import hrAgentService from '@/services/hrAgentService';


const STATUS_DOT = {
  active: 'bg-emerald-400',
  on_leave: 'bg-amber-400',
  probation: 'bg-sky-400',
  notice: 'bg-rose-400',
  offboarded: 'bg-slate-400',
};


export default function HRManagerTeamTab({ onOpenEmployee }) {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const res = await hrAgentService.getManagerTeamSummary();
      setData(res?.data || null);
    } catch (e) {
      setError(e.message || 'Failed to load team');
      toast({ title: 'Failed to load team', description: e.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-white/40" />
      </div>
    );
  }
  if (error) {
    return (
      <Card className="border-white/10 bg-black/20">
        <CardContent className="py-10 text-center">
          <AlertCircle className="h-8 w-8 text-rose-400 mx-auto mb-2" />
          <div className="text-white/80 text-sm">{error}</div>
        </CardContent>
      </Card>
    );
  }
  if (!data) return null;

  return (
    <div className="space-y-4">
      <Card className="border-white/10 bg-black/20 backdrop-blur-sm">
        <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-5 w-5 text-violet-400" /> My team
            </CardTitle>
            <CardDescription>
              {data.team_size === 0
                ? "You don't have any direct reports yet."
                : `${data.team_size} direct report${data.team_size === 1 ? '' : 's'} reporting to ${data.manager?.full_name || 'you'}.`}
            </CardDescription>
          </div>
          <Button variant="outline" onClick={load} disabled={loading}>
            <RefreshCw className="h-3.5 w-3.5 mr-1" /> Refresh
          </Button>
        </CardHeader>
        <CardContent>
          {data.team.length === 0 ? (
            <div className="text-center py-10 text-white/50 text-sm">
              No direct reports. If this is wrong, ask HR to set you as manager on each employee record.
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              {data.team.map((m) => (
                <div key={m.id}
                  className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4 hover:bg-white/[0.05] cursor-pointer transition-colors"
                  onClick={() => onOpenEmployee && onOpenEmployee(m.id)}>
                  <div className="flex items-start justify-between gap-2 mb-3">
                    <div className="min-w-0">
                      <div className="font-semibold text-white truncate">{m.full_name}</div>
                      <div className="text-xs text-white/55">{m.job_title || '—'}</div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <span className={`inline-block h-2 w-2 rounded-full ${STATUS_DOT[m.employment_status] || 'bg-slate-400'}`} />
                      <span className="text-[10px] text-white/55 uppercase tracking-wider">{m.employment_status}</span>
                    </div>
                  </div>

                  {m.probation_ending_in_days !== null && m.probation_ending_in_days <= 14 && (
                    <Badge variant="outline" className="text-[10px] bg-amber-500/10 text-amber-300 border-amber-400/30 mb-2">
                      Probation ends in {m.probation_ending_in_days}d
                    </Badge>
                  )}

                  {/* Leave balances */}
                  {m.leave_balances.length > 0 && (
                    <div className="mb-2">
                      <div className="text-[10px] uppercase tracking-wider text-white/45 mb-1">Leave remaining</div>
                      <div className="flex flex-wrap gap-1">
                        {m.leave_balances.map((b, idx) => (
                          <Badge key={idx} variant="outline" className="text-[10px]">
                            {b.leave_type}: {b.remaining.toFixed(1)}d
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Pending leave requests awaiting decision */}
                  {m.pending_leave_requests.length > 0 && (
                    <div className="mb-2 rounded-lg border border-amber-400/20 bg-amber-500/5 p-2">
                      <div className="flex items-center gap-1.5 text-amber-300 text-xs font-medium mb-1">
                        <ClipboardList className="h-3 w-3" />
                        {m.pending_leave_requests.length} pending leave request{m.pending_leave_requests.length === 1 ? '' : 's'}
                      </div>
                      {m.pending_leave_requests.slice(0, 3).map((lr) => (
                        <div key={lr.id} className="text-[11px] text-white/70">
                          {lr.leave_type} · {lr.start_date} → {lr.end_date} ({lr.days_requested}d)
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Upcoming meetings */}
                  {m.upcoming_meetings.length > 0 && (
                    <div className="mb-2">
                      <div className="text-[10px] uppercase tracking-wider text-white/45 mb-1 flex items-center gap-1">
                        <CalendarClock className="h-3 w-3" /> Upcoming (14d)
                      </div>
                      {m.upcoming_meetings.slice(0, 2).map((mtg) => (
                        <div key={mtg.id} className="text-[11px] text-white/70 truncate">
                          {mtg.title} — {(mtg.scheduled_at || '').slice(0, 16).replace('T', ' ')}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Open goals */}
                  {m.open_goals.length > 0 && (
                    <div>
                      <div className="text-[10px] uppercase tracking-wider text-white/45 mb-1 flex items-center gap-1">
                        <Target className="h-3 w-3" /> Open goals
                      </div>
                      {m.open_goals.slice(0, 2).map((g) => (
                        <div key={g.id} className="text-[11px] text-white/70 flex items-center justify-between gap-2">
                          <span className="truncate">{g.title}</span>
                          <span className="text-white/50 shrink-0">{g.progress_pct}%</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
