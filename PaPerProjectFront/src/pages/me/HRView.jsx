import React, { useCallback, useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import { Briefcase, Loader2, Send, CalendarPlus, MessageCircleQuestion, FileText } from 'lucide-react';
import myHrService from '@/services/myHrService';

/**
 * HRView — /me/hr ("My HR")
 *
 * An employee's own HR, from their own login: their leave balance, a question to
 * HR answered from the company's HR documents and their own record, asking for
 * leave, and their requests with HR's answers. Every HR screen used to need a
 * dashboard login, so an employee could do none of this.
 */
const FIELD = 'w-full rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-white/30 focus:outline-none focus:ring-2 focus:ring-violet-400/50';

const STATUS_STYLE = {
  pending: 'bg-amber-500/15 text-amber-200 border-amber-500/30',
  approved: 'bg-emerald-500/15 text-emerald-200 border-emerald-500/30',
  rejected: 'bg-red-500/15 text-red-200 border-red-500/30',
  cancelled: 'bg-white/10 text-white/50 border-white/15',
  withdrawn: 'bg-white/10 text-white/50 border-white/15',
};

const days = (n) => `${Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })} day${Number(n) === 1 ? '' : 's'}`;
const dateText = (iso) => (iso ? new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '');

export default function HRView() {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const [question, setQuestion] = useState('');
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState(null);

  const [form, setForm] = useState({ leave_type: 'vacation', start_date: '', end_date: '', partial_day_period: '', reason: '' });
  const [sending, setSending] = useState(false);
  const [cancelling, setCancelling] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await myHrService.get();
      setData(res.data || null);
    } catch (err) {
      setData({ available: false, message: err.message });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const ask = async (e) => {
    e.preventDefault();
    const q = question.trim();
    if (!q) return;
    setAsking(true);
    setAnswer(null);
    try {
      const res = await myHrService.ask(q);
      setAnswer({ question: q, ...(res.data || {}) });
    } catch (err) {
      setAnswer({ question: q, answer: err.message, failed: true });
    } finally {
      setAsking(false);
    }
  };

  const requestLeave = async (e) => {
    e.preventDefault();
    setSending(true);
    try {
      const sameDay = form.start_date && form.start_date === form.end_date;
      await myHrService.requestLeave({ ...form, partial_day_period: sameDay ? form.partial_day_period : '' });
      toast({ title: 'Leave requested', description: 'HR has been told. You will hear back here and by email.' });
      setForm((f) => ({ ...f, start_date: '', end_date: '', partial_day_period: '', reason: '' }));
      load();
    } catch (err) {
      toast({ title: 'Could not request leave', description: err.message, variant: 'destructive' });
    } finally {
      setSending(false);
    }
  };

  const cancel = async (id) => {
    setCancelling(id);
    try {
      await myHrService.cancelLeave(id);
      toast({ title: 'Request cancelled' });
      load();
    } catch (err) {
      toast({ title: 'Could not cancel', description: err.message, variant: 'destructive' });
    } finally {
      setCancelling(null);
    }
  };

  if (loading) {
    return <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-violet-300" /></div>;
  }

  const sameDay = form.start_date && form.start_date === form.end_date;

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      <div className="flex items-center gap-3 text-white">
        <Briefcase className="h-6 w-6 text-violet-300" />
        <h2 className="text-2xl font-bold">My HR</h2>
      </div>

      {!data?.available ? (
        <Card className="bg-white/[0.03] border-white/[0.08]">
          <CardContent className="py-8 text-center text-white/60 text-sm">
            {data?.message || 'HR is not available here.'}
          </CardContent>
        </Card>
      ) : (
        <>
          <Card className="bg-white/[0.03] border-white/[0.08]">
            <CardHeader>
              <CardTitle className="text-white text-base">Leave balance</CardTitle>
              <CardDescription className="text-white/50">
                {[data.employee.job_title, data.employee.department].filter(Boolean).join(' · ')}
                {data.employee.manager ? ` · Manager: ${data.employee.manager}` : ''}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {data.balances.length === 0 ? (
                <p className="text-sm text-white/50">HR has not set up your leave balance yet.</p>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {data.balances.map((b) => (
                    <div key={b.leave_type} className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                      <p className="text-xs text-white/50">{b.label}</p>
                      <p className="mt-1 text-2xl font-bold text-white">{days(b.remaining)}</p>
                      <p className="mt-1 text-[11px] text-white/40">
                        left of {days(b.accrued_days + b.carried_over_days)}
                        {b.carried_over_days ? ` (${days(b.carried_over_days)} carried over)` : ''}, {days(b.used_days)} used
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="bg-white/[0.03] border-white/[0.08]">
            <CardHeader>
              <CardTitle className="text-white text-base flex items-center gap-2">
                <MessageCircleQuestion className="h-4 w-4 text-violet-300" /> Ask HR
              </CardTitle>
              <CardDescription className="text-white/50">
                Answered from your company's HR documents and your own record.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <form onSubmit={ask} className="flex gap-2">
                <input className={FIELD} value={question} onChange={(e) => setQuestion(e.target.value)}
                  placeholder="e.g. How many days of annual leave can I carry into next year?" maxLength={2000} />
                <Button type="submit" disabled={asking || !question.trim()} className="shrink-0">
                  {asking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </Button>
              </form>
              {answer && (
                <div className={`rounded-xl border p-4 text-sm ${answer.failed ? 'border-red-500/30 bg-red-500/10 text-red-200' : 'border-white/10 bg-white/[0.03] text-white/80'}`}>
                  <p className="mb-2 text-xs text-white/40">{answer.question}</p>
                  <div className="space-y-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5">
                    <ReactMarkdown>{answer.answer || ''}</ReactMarkdown>
                  </div>
                  {Array.isArray(answer.sources) && answer.sources.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {answer.sources.map((s) => (
                        <span key={s.title} className="inline-flex items-center gap-1 rounded-full border border-white/15 px-2 py-0.5 text-[11px] text-white/60">
                          <FileText className="h-3 w-3" /> {s.title}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="bg-white/[0.03] border-white/[0.08]">
            <CardHeader>
              <CardTitle className="text-white text-base flex items-center gap-2">
                <CalendarPlus className="h-4 w-4 text-violet-300" /> Ask for leave
              </CardTitle>
              <CardDescription className="text-white/50">
                Weekends and company holidays are not counted. Whoever approves your leave is told at once.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={requestLeave} className="grid gap-3 sm:grid-cols-2">
                <label className="text-xs text-white/50 space-y-1">
                  <span>Kind of leave</span>
                  <select className={FIELD} value={form.leave_type}
                    onChange={(e) => setForm((f) => ({ ...f, leave_type: e.target.value }))}>
                    {data.leave_types.map((t) => (
                      <option key={t.value} value={t.value} className="bg-[var(--sfc-0d0b1f)]">{t.label}</option>
                    ))}
                  </select>
                </label>
                <label className="text-xs text-white/50 space-y-1">
                  <span>Reason (HR and your approver see it)</span>
                  <input className={FIELD} value={form.reason} maxLength={2000}
                    onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))} />
                </label>
                <label className="text-xs text-white/50 space-y-1">
                  <span>From</span>
                  <input type="date" required className={FIELD} value={form.start_date}
                    onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value, end_date: f.end_date || e.target.value }))} />
                </label>
                <label className="text-xs text-white/50 space-y-1">
                  <span>To</span>
                  <input type="date" required className={FIELD} value={form.end_date} min={form.start_date || undefined}
                    onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value }))} />
                </label>
                {sameDay && (
                  <label className="text-xs text-white/50 space-y-1">
                    <span>Part of the day</span>
                    <select className={FIELD} value={form.partial_day_period}
                      onChange={(e) => setForm((f) => ({ ...f, partial_day_period: e.target.value }))}>
                      <option value="" className="bg-[var(--sfc-0d0b1f)]">The whole day</option>
                      <option value="morning" className="bg-[var(--sfc-0d0b1f)]">Morning</option>
                      <option value="afternoon" className="bg-[var(--sfc-0d0b1f)]">Afternoon</option>
                    </select>
                  </label>
                )}
                <div className="sm:col-span-2 flex justify-end">
                  <Button type="submit" disabled={sending || !form.start_date || !form.end_date}>
                    {sending ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : null}
                    Request leave
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>

          <Card className="bg-white/[0.03] border-white/[0.08]">
            <CardHeader>
              <CardTitle className="text-white text-base">My leave requests</CardTitle>
            </CardHeader>
            <CardContent>
              {data.leave_requests.length === 0 ? (
                <p className="text-sm text-white/50">You have not asked for leave yet.</p>
              ) : (
                <ul className="divide-y divide-white/[0.06]">
                  {data.leave_requests.map((lr) => (
                    <li key={lr.id} className="flex flex-wrap items-center gap-3 py-3">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-white">
                          {lr.leave_type_label}: {dateText(lr.start_date)}
                          {lr.end_date !== lr.start_date ? ` – ${dateText(lr.end_date)}` : ''} ({days(lr.days_requested)})
                        </p>
                        <p className="text-xs text-white/40">
                          {lr.approver_name ? `Approver: ${lr.approver_name}` : 'Approver: HR'}
                          {lr.approval_note ? ` · "${lr.approval_note}"` : ''}
                        </p>
                      </div>
                      <span className={`rounded-full border px-2 py-0.5 text-[11px] ${STATUS_STYLE[lr.status] || STATUS_STYLE.cancelled}`}>
                        {lr.status_label}
                      </span>
                      {lr.status === 'pending' && (
                        <Button variant="outline" size="sm" disabled={cancelling === lr.id} onClick={() => cancel(lr.id)}
                          className="border-white/15 text-white/70 hover:bg-white/[0.06] hover:text-white">
                          {cancelling === lr.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Cancel'}
                        </Button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
