// Frontline's Meetings, under Queue: book and list calls with customers.
//
// The server side (list, book, change, cancel) existed with no screen. Booking goes through the same busy-time
// table and clash rule as Project Manager and HR: a time when someone is already busy is refused with the times
// everyone is free, and a pending invitation counts as busy.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { CalendarDays, Loader2, Plus, Video, XCircle } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import frontlineAgentService from '@/services/frontlineAgentService';

const DAYS_BACK = 30;
const DURATIONS = [15, 30, 45, 60];
const STATUS_CLASS = {
  scheduled: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-300',
  rescheduled: 'bg-sky-500/15 text-sky-600 dark:text-sky-300',
  completed: 'bg-muted text-muted-foreground',
  cancelled: 'bg-red-500/10 text-red-600 dark:text-red-300',
};

const localZone = () => {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'; } catch { return 'UTC'; }
};

const when = (iso) => new Date(iso).toLocaleString(undefined, {
  weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit',
});

const EMPTY = {
  title: '', at: '', duration: 30, description: '', meetingLink: '', people: [],
  customerName: '', customerEmail: '', ticketId: null,
};

const MeetingRow = ({ m, onCancel, cancelling }) => {
  const active = m.status === 'scheduled' || m.status === 'rescheduled';
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border p-3">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-foreground">{m.title}</span>
          <Badge variant="secondary" className={STATUS_CLASS[m.status] || ''}>{m.status}</Badge>
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {when(m.scheduled_at)} · {m.duration_minutes} min
          {m.participant_user_ids?.length ? ` · ${m.participant_user_ids.length} from your team` : ''}
        </p>
        {(m.customer_name || m.customer_email) && (
          <p className="mt-0.5 text-xs text-muted-foreground" data-testid="FL-meeting-customer">
            With {m.customer_name || m.customer_email}
            {m.customer_name && m.customer_email ? ` (${m.customer_email})` : ''}
          </p>
        )}
        {m.description && <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{m.description}</p>}
      </div>
      <div className="flex shrink-0 gap-2">
        {active && m.meeting_link && (
          <Button size="sm" variant="outline" asChild>
            <a href={m.meeting_link} target="_blank" rel="noopener noreferrer"><Video className="mr-1.5 h-4 w-4" />Join</a>
          </Button>
        )}
        {active && (
          <Button size="sm" variant="ghost" className="text-destructive" disabled={cancelling} onClick={() => onCancel(m)}>
            {cancelling ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <XCircle className="mr-1.5 h-4 w-4" />}Cancel
          </Button>
        )}
      </div>
    </div>
  );
};

export const FrontlineMeetingsTab = () => {
  const { toast } = useToast();
  const [meetings, setMeetings] = useState(null);
  const [team, setTeam] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState('');
  const [cancellingId, setCancellingId] = useState(null);
  const [params, setParams] = useSearchParams();

  const load = useCallback(async () => {
    const from = new Date(Date.now() - DAYS_BACK * 24 * 3600 * 1000).toISOString();
    try {
      const res = await frontlineAgentService.listMeetings({ date_from: from, limit: 100 });
      setMeetings(Array.isArray(res?.data) ? res.data : []);
    } catch (e) {
      setMeetings([]);
      toast({ title: 'Could not load meetings', description: e?.message || '', variant: 'destructive' });
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const { upcoming, past } = useMemo(() => {
    const now = Date.now();
    const rows = meetings || [];
    return {
      upcoming: rows.filter((m) => new Date(m.scheduled_at).getTime() + m.duration_minutes * 60000 >= now)
        .sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at)),
      past: rows.filter((m) => new Date(m.scheduled_at).getTime() + m.duration_minutes * 60000 < now),
    };
  }, [meetings]);

  const startBooking = async (prefill = {}) => {
    setForm({ ...EMPTY, ...prefill });
    setProblem('');
    setOpen(true);
    if (!team.length) {
      try {
        const res = await frontlineAgentService.listWorkflowCompanyUsers();
        setTeam(Array.isArray(res?.data) ? res.data : []);
      } catch { /* booking without colleagues still works */ }
    }
  };

  // Opened from a hand-off's "Book the call": the form starts with the customer and what they asked about.
  useEffect(() => {
    if (params.get('book') !== '1') return;
    const topic = params.get('topic') || '';
    startBooking({
      title: params.get('customer_name') ? `Call with ${params.get('customer_name')}` : 'Call with a customer',
      description: topic,
      customerName: params.get('customer_name') || '',
      customerEmail: params.get('customer_email') || '',
      ticketId: params.get('ticket') ? Number(params.get('ticket')) : null,
    });
    const next = new URLSearchParams(params);
    ['book', 'ticket', 'customer_name', 'customer_email', 'topic'].forEach((k) => next.delete(k));
    setParams(next, { replace: true });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const book = async () => {
    if (!form.title.trim() || !form.at) {
      setProblem('Give the meeting a title and a time.');
      return;
    }
    setSaving(true);
    setProblem('');
    try {
      await frontlineAgentService.createMeeting({
        title: form.title.trim(),
        description: form.description.trim(),
        scheduled_at: new Date(form.at).toISOString(),
        duration_minutes: form.duration,
        timezone_name: localZone(),
        meeting_link: form.meetingLink.trim(),
        participant_company_user_ids: form.people,
        customer_name: form.customerName.trim(),
        customer_email: form.customerEmail.trim(),
        ...(form.ticketId ? { ticket_id: form.ticketId } : {}),
      });
      toast({
        title: 'Meeting booked',
        description: form.customerEmail.trim()
          ? `${form.customerEmail.trim()} has been emailed the invitation with the link; your colleagues on it have been told.`
          : 'Your colleagues on it have been told.',
      });
      setOpen(false);
      load();
    } catch (e) {
      // A clash says who is busy and when everyone is free; shown as the server words it.
      setProblem(e?.message || 'Could not book the meeting.');
    } finally {
      setSaving(false);
    }
  };

  const cancel = async (m) => {
    if (!window.confirm(`Cancel "${m.title}"?`)) return;
    setCancellingId(m.id);
    try {
      await frontlineAgentService.updateMeeting(m.id, { status: 'cancelled' });
      toast({ title: 'Meeting cancelled' });
      load();
    } catch (e) {
      toast({ title: 'Could not cancel', description: e?.message || '', variant: 'destructive' });
    } finally {
      setCancellingId(null);
    }
  };

  const togglePerson = (id, on) => setForm((f) => ({
    ...f, people: on ? [...f.people, id] : f.people.filter((p) => p !== id),
  }));

  return (
    <Card className="w-full min-w-0" data-testid="FL-meetings">
      <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2"><CalendarDays className="h-5 w-5" /> Meetings</CardTitle>
          <CardDescription>Calls with customers. A time when someone on the call is already busy is refused, with times everyone is free.</CardDescription>
        </div>
        <Button size="sm" onClick={() => startBooking()} data-testid="FL-meetings-book"><Plus className="mr-1.5 h-4 w-4" />Book a meeting</Button>
      </CardHeader>
      <CardContent className="space-y-6">
        {meetings === null ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading...</div>
        ) : (
          <>
            <section className="space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Upcoming</h3>
              {upcoming.length === 0
                ? <p className="text-sm text-muted-foreground">Nothing booked.</p>
                : upcoming.map((m) => <MeetingRow key={m.id} m={m} onCancel={cancel} cancelling={cancellingId === m.id} />)}
            </section>
            {past.length > 0 && (
              <section className="space-y-2">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Last {DAYS_BACK} days</h3>
                {past.map((m) => <MeetingRow key={m.id} m={m} onCancel={cancel} cancelling={false} />)}
              </section>
            )}
          </>
        )}
      </CardContent>

      <Dialog open={open} onOpenChange={(o) => { if (!saving) setOpen(o); }}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Book a meeting</DialogTitle>
            <DialogDescription>
              A video link is made for you unless you paste your own. The customer is emailed the invitation with the
              link, and everyone is reminded a day, an hour, 15 and 5 minutes before.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="fl-meeting-title">Title</Label>
              <Input id="fl-meeting-title" value={form.title} placeholder="Onboarding call with Northwind"
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} />
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
              <div className="space-y-1.5">
                <Label htmlFor="fl-meeting-at">When</Label>
                <Input id="fl-meeting-at" type="datetime-local" value={form.at}
                  onChange={(e) => setForm((f) => ({ ...f, at: e.target.value }))} />
              </div>
              <div className="space-y-1.5">
                <Label>Length</Label>
                <div className="flex gap-1">
                  {DURATIONS.map((d) => (
                    <Button key={d} type="button" size="sm" variant={form.duration === d ? 'default' : 'outline'}
                      onClick={() => setForm((f) => ({ ...f, duration: d }))}>{d}m</Button>
                  ))}
                </div>
              </div>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="fl-meeting-customer-name">Customer's name</Label>
                <Input id="fl-meeting-customer-name" value={form.customerName} placeholder="Farhan Qureshi"
                  data-testid="FL-meeting-customer-name"
                  onChange={(e) => setForm((f) => ({ ...f, customerName: e.target.value }))} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="fl-meeting-customer-email">Customer's email</Label>
                <Input id="fl-meeting-customer-email" type="email" value={form.customerEmail} placeholder="name@company.com"
                  data-testid="FL-meeting-customer-email"
                  onChange={(e) => setForm((f) => ({ ...f, customerEmail: e.target.value }))} />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="fl-meeting-about">What the call is about</Label>
              <Textarea id="fl-meeting-about" rows={3} value={form.description}
                placeholder="The customer's question or problem, and what to cover"
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="fl-meeting-link">Meeting link (optional)</Label>
              <Input id="fl-meeting-link" value={form.meetingLink} placeholder="https://..."
                onChange={(e) => setForm((f) => ({ ...f, meetingLink: e.target.value }))} />
            </div>
            {team.length > 0 && (
              <div className="space-y-1.5">
                <Label>Colleagues on the call</Label>
                <div className="max-h-36 space-y-1.5 overflow-y-auto rounded-md border border-border p-2">
                  {team.map((p) => (
                    <label key={p.id} className="flex cursor-pointer items-center gap-2 text-sm">
                      <Checkbox checked={form.people.includes(p.id)} onCheckedChange={(on) => togglePerson(p.id, !!on)} />
                      <span>{p.full_name || p.email}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}
            {problem && <p className="rounded-md bg-destructive/10 p-2 text-sm text-destructive" role="alert">{problem}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={saving}>Cancel</Button>
            <Button onClick={book} disabled={saving}>
              {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Book
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
};

export default FrontlineMeetingsTab;
