import React, { useEffect, useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import {
  Calendar,
  CalendarPlus,
  Clock,
  Loader2,
  CheckCircle,
  XCircle,
  ArrowRightLeft,
  RefreshCw,
} from 'lucide-react';
import { API_BASE_URL } from '@/config/apiConfig';

/**
 * MeetingsView — /me/meetings
 *
 * Redesigned meeting inbox extracted from UserDashboardPage's Meetings
 * tab. Fixes the audit's finding #9: the classic UI mashed "Reject" and
 * "Suggest Time" into one button labelled "Reject / Suggest Time" — two
 * disparate actions collapsed together. This version splits them into
 * three distinct primary actions: Accept, Reject, Suggest Time.
 *
 * The federated inbox (HR + PM + exec-meeting sources into one list) is
 * still Chunk D-follow-up backend work; for now this shows the same
 * /api/meetings source the classic dashboard uses.
 */
const STATUS_COLORS = {
  pending: 'text-yellow-400 bg-yellow-500/20',
  accepted: 'text-green-400 bg-green-500/20',
  rejected: 'text-red-400 bg-red-500/20',
  counter_proposed: 'text-blue-400 bg-blue-500/20',
  withdrawn: 'text-gray-400 bg-gray-500/20',
};

export default function MeetingsView() {
  const { toast } = useToast();

  const [meetings, setMeetings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [rejectFor, setRejectFor] = useState(null);
  const [suggestFor, setSuggestFor] = useState(null);
  const [rejectReason, setRejectReason] = useState('');
  const [counterDate, setCounterDate] = useState('');
  const [counterTime, setCounterTime] = useState('');
  const [respondLoading, setRespondLoading] = useState(false);

  useEffect(() => {
    fetchMeetings();
  }, []);

  const fetchMeetings = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('auth_token');
      const res = await fetch(`${API_BASE_URL}/meetings`, {
        headers: { 'Authorization': `Token ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setMeetings(data?.data?.meetings || []);
      }
    } catch (err) {
      toast({ title: 'Error', description: 'Could not load meetings', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const closeAllForms = () => {
    setRejectFor(null); setSuggestFor(null);
    setRejectReason(''); setCounterDate(''); setCounterTime('');
  };

  const respond = async (id, action, extra = {}) => {
    setRespondLoading(true);
    try {
      const token = localStorage.getItem('auth_token');
      const res = await fetch(`${API_BASE_URL}/meetings/${id}/respond`, {
        method: 'POST',
        headers: { 'Authorization': `Token ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, ...extra }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.message || 'Failed');
      }
      toast({
        title: action === 'accepted' ? 'Meeting accepted'
          : action === 'rejected' ? 'Meeting rejected'
          : 'New time proposed',
      });
      closeAllForms();
      fetchMeetings();
    } catch (err) {
      toast({ title: 'Error', description: err.message, variant: 'destructive' });
    } finally {
      setRespondLoading(false);
    }
  };

  const handleReject = (m) => {
    respond(m.id, 'rejected', { reason: rejectReason });
  };

  const handleSuggest = (m) => {
    if (!counterDate || !counterTime) {
      toast({ title: 'Pick a date and time first', variant: 'destructive' });
      return;
    }
    const counter_time = new Date(`${counterDate}T${counterTime}`).toISOString();
    respond(m.id, 'counter_proposed', { counter_time, reason: rejectReason });
  };

  const canAct = (m) =>
    (m.my_status === 'pending' || m.my_status === 'counter_proposed'
      || m.status === 'pending' || m.status === 'counter_proposed')
    && m.my_status !== 'accepted' && m.status !== 'withdrawn';

  const pendingCount = meetings.filter(canAct).length;

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 text-white">
          <Calendar className="h-6 w-6 text-violet-300" />
          <div>
            <h2 className="text-2xl font-bold">My Meetings</h2>
            <p className="text-xs text-white/50">
              {loading ? 'Loading…' : `${meetings.length} shown${pendingCount > 0 ? ` • ${pendingCount} awaiting response` : ''}`}
            </p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={fetchMeetings} className="border-white/15 text-white/70 hover:bg-white/[0.06] hover:text-white">
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-violet-300" /></div>
      ) : meetings.length === 0 ? (
        <Card className="bg-white/[0.02] border-white/10">
          <CardContent className="py-16 text-center">
            <CalendarPlus className="h-10 w-10 mx-auto mb-3 text-white/25" />
            <p className="text-sm text-white/60">No meeting requests yet.</p>
            <p className="text-[11px] text-white/40 mt-1">
              Invites will show up here as they come in.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {meetings.map((m) => {
            const sc = STATUS_COLORS[m.status] || STATUS_COLORS.pending;
            const showActions = canAct(m);
            const showReject = rejectFor === m.id;
            const showSuggest = suggestFor === m.id;

            return (
              <Card key={m.id} className="bg-white/[0.03] border-white/[0.08]">
                <CardContent className="p-4 space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3 className="text-sm font-semibold text-white truncate">{m.title}</h3>
                      <p className="text-[11px] text-white/50 mt-0.5 truncate">
                        From: {m.organizer_name} {m.organizer_email && <span className="text-white/30">({m.organizer_email})</span>}
                      </p>
                    </div>
                    <span className={`text-[10px] px-2 py-1 rounded-full font-medium capitalize shrink-0 ${sc}`}>
                      {(m.status || '').replace(/_/g, ' ')}
                    </span>
                  </div>

                  <div className="flex items-center gap-3 text-[11px] text-white/50 flex-wrap">
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {new Date(m.proposed_time).toLocaleString(undefined, {
                        weekday: 'short', month: 'short', day: 'numeric',
                        year: 'numeric', hour: 'numeric', minute: '2-digit',
                      })}
                    </span>
                    <span>{m.duration_minutes} min</span>
                  </div>

                  {m.description && <p className="text-xs text-white/50">{m.description}</p>}

                  {m.agenda?.length > 0 && (
                    <div className="space-y-1">
                      <span className="text-[10px] text-white/30 uppercase tracking-wide">Agenda</span>
                      {m.agenda.map((a, ai) => (
                        <div key={ai} className="flex items-start gap-2 text-xs text-white/60">
                          <span className="text-violet-300 mt-0.5">{a.done ? '✓' : '•'}</span>
                          <span className={a.done ? 'line-through text-white/30' : ''}>{a.item}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {m.responses?.length > 0 && (
                    <div className="space-y-1 pt-2 border-t border-white/5">
                      {m.responses.map((r, ri) => (
                        <div key={ri} className="text-[11px] text-white/50 flex items-center gap-2 flex-wrap">
                          <span className="font-medium text-white/70">{r.responder_name}</span>
                          <span className={`px-1.5 py-0.5 rounded text-[10px] ${STATUS_COLORS[r.action] || ''}`}>{r.action}</span>
                          {r.proposed_time && (
                            <span>→ {new Date(r.proposed_time).toLocaleString(undefined, {
                              month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
                            })}</span>
                          )}
                          {r.reason && <span className="italic">"{r.reason}"</span>}
                        </div>
                      ))}
                    </div>
                  )}

                  {m.participants?.length > 1 && (
                    <div className="flex flex-wrap gap-1.5">
                      {m.participants.map((p, pi) => (
                        <span key={pi} className={`text-[10px] px-2 py-0.5 rounded-full border border-white/10 ${
                          p.status === 'accepted' ? 'bg-green-500/20 text-green-400'
                            : p.status === 'rejected' ? 'bg-red-500/20 text-red-400'
                            : p.status === 'counter_proposed' ? 'bg-blue-500/20 text-blue-400'
                            : 'bg-gray-500/20 text-gray-400'
                        }`}>
                          {p.name}: {p.status}
                        </span>
                      ))}
                    </div>
                  )}

                  {showActions && (
                    <div className="pt-3 border-t border-white/5 space-y-2">
                      {/* Three distinct actions — no more "Reject / Suggest Time" combo. */}
                      {!showReject && !showSuggest && (
                        <div className="flex flex-wrap gap-2">
                          <Button
                            size="sm"
                            onClick={() => respond(m.id, 'accepted')}
                            disabled={respondLoading}
                            className="bg-green-600 hover:bg-green-700 text-xs h-8"
                          >
                            <CheckCircle className="h-3 w-3 mr-1" /> Accept
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => { closeAllForms(); setSuggestFor(m.id); }}
                            disabled={respondLoading}
                            className="text-xs h-8 border-blue-500/40 text-blue-300 hover:bg-blue-500/10"
                          >
                            <ArrowRightLeft className="h-3 w-3 mr-1" /> Suggest a different time
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => { closeAllForms(); setRejectFor(m.id); }}
                            disabled={respondLoading}
                            className="text-xs h-8 border-red-500/40 text-red-300 hover:bg-red-500/10"
                          >
                            <XCircle className="h-3 w-3 mr-1" /> Reject
                          </Button>
                        </div>
                      )}

                      {showReject && (
                        <div className="space-y-2 bg-white/[0.03] rounded-lg p-3">
                          <p className="text-[11px] text-white/60">Let the organizer know why (optional):</p>
                          <input
                            value={rejectReason}
                            onChange={(e) => setRejectReason(e.target.value)}
                            placeholder="Reason (optional)"
                            className="w-full bg-transparent border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder:text-white/30 focus:outline-none focus:ring-1 focus:ring-red-500/50"
                          />
                          <div className="flex gap-2">
                            <Button size="sm" onClick={() => handleReject(m)} disabled={respondLoading}
                              className="bg-red-600 hover:bg-red-700 text-xs h-8">
                              <XCircle className="h-3 w-3 mr-1" /> Confirm reject
                            </Button>
                            <Button size="sm" variant="ghost" onClick={closeAllForms} className="text-xs h-8 text-white/60">
                              Cancel
                            </Button>
                          </div>
                        </div>
                      )}

                      {showSuggest && (
                        <div className="space-y-2 bg-white/[0.03] rounded-lg p-3">
                          <p className="text-[11px] text-white/60">Propose a new time:</p>
                          <div className="flex flex-wrap items-center gap-2">
                            <input type="date" value={counterDate} onChange={(e) => setCounterDate(e.target.value)}
                              className="bg-transparent border border-white/10 rounded-lg px-2 py-1.5 text-xs text-white focus:outline-none focus:ring-1 focus:ring-blue-500/50" />
                            <input type="time" value={counterTime} onChange={(e) => setCounterTime(e.target.value)}
                              className="bg-transparent border border-white/10 rounded-lg px-2 py-1.5 text-xs text-white focus:outline-none focus:ring-1 focus:ring-blue-500/50" />
                          </div>
                          <input
                            value={rejectReason}
                            onChange={(e) => setRejectReason(e.target.value)}
                            placeholder="Note (optional)"
                            className="w-full bg-transparent border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder:text-white/30 focus:outline-none focus:ring-1 focus:ring-blue-500/50"
                          />
                          <div className="flex gap-2">
                            <Button size="sm" onClick={() => handleSuggest(m)} disabled={respondLoading || !counterDate || !counterTime}
                              className="bg-blue-600 hover:bg-blue-700 text-xs h-8">
                              <ArrowRightLeft className="h-3 w-3 mr-1" /> Propose time
                            </Button>
                            <Button size="sm" variant="ghost" onClick={closeAllForms} className="text-xs h-8 text-white/60">
                              Cancel
                            </Button>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
