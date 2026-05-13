/**
 * HREmployeeDetailDrawer — slide-in dialog showing one employee's full HR
 * profile in one round-trip. Calls `GET /api/hr/employees/<id>/`.
 *
 * Sections:
 *   * Profile + manager chain
 *   * Leave balances (per leave_type, with remaining)
 *   * Personal documents (extracted_fields surfaced if available)
 *   * Recent leave requests
 *   * Recent meetings
 */
import React, { useEffect, useState } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import {
  Loader2, User, Briefcase, Building2, Mail, CalendarClock, FileText,
  ClipboardList, ChevronRight, DollarSign, Plus, Trash2, Star,
} from 'lucide-react';
import hrAgentService from '@/services/hrAgentService';

const STAT_BG = 'rgba(167,139,250,0.2)';
const STAT_FG = '#a78bfa';

const STATUS_BADGE = {
  pending: 'bg-amber-500/10 text-amber-300 border-amber-400/30',
  approved: 'bg-emerald-500/10 text-emerald-300 border-emerald-400/30',
  rejected: 'bg-rose-500/10 text-rose-300 border-rose-400/30',
  cancelled: 'bg-slate-500/10 text-slate-300 border-slate-400/30',
};


export default function HREmployeeDetailDrawer({ open, employeeId, onOpenChange }) {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  // Compensation state — fetched lazily; 403 means caller isn't HR-admin.
  const [comp, setComp] = useState({ rows: [], loading: false, allowed: true });
  const [compForm, setCompForm] = useState({ open: false, saving: false, payload: {} });

  // Performance reviews — also lazy-fetched per drawer open.
  const [reviews, setReviews] = useState({ rows: [], loading: false });

  useEffect(() => {
    if (!open || !employeeId) {
      setData(null);
      setComp({ rows: [], loading: false, allowed: true });
      setReviews({ rows: [], loading: false });
      return;
    }
    let cancelled = false;
    setLoading(true);
    hrAgentService.getHREmployeeDetail(employeeId)
      .then((res) => { if (!cancelled) setData(res?.data || null); })
      .catch(() => { if (!cancelled) setData(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, employeeId]);

  // Lazy load compensation when the drawer opens. 403 is the expected
  // result for non-HR-admins — switch the section to a "restricted" state.
  useEffect(() => {
    if (!open || !employeeId) return;
    let cancelled = false;
    setComp((s) => ({ ...s, loading: true }));
    hrAgentService.listCompensationHistory(employeeId)
      .then((res) => {
        if (!cancelled) setComp({ rows: res?.data || [], loading: false, allowed: true });
      })
      .catch((e) => {
        if (cancelled) return;
        const restricted = /HR-admin/i.test(e.message || '') || /403/.test(e.message || '');
        setComp({ rows: [], loading: false, allowed: !restricted });
      });
    return () => { cancelled = true; };
  }, [open, employeeId]);

  // Lazy load performance reviews — always returns 200 but filtered by visibility.
  useEffect(() => {
    if (!open || !employeeId) return;
    let cancelled = false;
    setReviews((s) => ({ ...s, loading: true }));
    hrAgentService.listHREmployeeReviews(employeeId)
      .then((res) => { if (!cancelled) setReviews({ rows: res?.data || [], loading: false }); })
      .catch(() => { if (!cancelled) setReviews({ rows: [], loading: false }); });
    return () => { cancelled = true; };
  }, [open, employeeId]);

  const openCompForm = () => setCompForm({
    open: true, saving: false,
    payload: {
      effective_date: new Date().toISOString().slice(0, 10),
      base_salary: '', currency: 'USD', pay_frequency: 'annual',
      grade: '', reason: 'annual_raise', notes: '',
      bonus_target_pct: '', equity_grant_value: '',
    },
  });

  const handleSaveComp = async () => {
    const p = compForm.payload;
    if (!p.base_salary || !p.effective_date) {
      toast({ title: 'effective_date and base_salary are required', variant: 'destructive' });
      return;
    }
    setCompForm((s) => ({ ...s, saving: true }));
    try {
      const res = await hrAgentService.createCompensation(employeeId, {
        effective_date: p.effective_date,
        base_salary: Number(p.base_salary),
        currency: (p.currency || 'USD').toUpperCase(),
        pay_frequency: p.pay_frequency || 'annual',
        grade: p.grade || '',
        reason: p.reason || 'other',
        notes: p.notes || '',
        bonus_target_pct: p.bonus_target_pct ? Number(p.bonus_target_pct) : null,
        equity_grant_value: p.equity_grant_value ? Number(p.equity_grant_value) : null,
      });
      const row = res?.data;
      if (row) setComp((s) => ({ ...s, rows: [row, ...s.rows] }));
      toast({ title: 'Compensation recorded' });
      setCompForm({ open: false, saving: false, payload: {} });
    } catch (e) {
      toast({ title: 'Save failed', description: e.message, variant: 'destructive' });
      setCompForm((s) => ({ ...s, saving: false }));
    }
  };

  const handleDeleteComp = async (row) => {
    if (!confirm(`Delete the comp row dated ${row.effective_date}?`)) return;
    try {
      await hrAgentService.deleteCompensation(row.id);
      setComp((s) => ({ ...s, rows: s.rows.filter((r) => r.id !== row.id) }));
    } catch (e) {
      toast({ title: 'Delete failed', description: e.message, variant: 'destructive' });
    }
  };

  const e = data?.employee;
  const chain = data?.manager_chain || [];
  const balances = data?.leave_balances || [];
  const docs = data?.personal_documents || [];
  const leaves = data?.leave_requests || [];
  const meetings = data?.meetings || [];

  const setCompField = (k, v) => setCompForm((s) => ({ ...s, payload: { ...s.payload, [k]: v } }));

  return (
    <>
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[92vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>{e?.full_name || 'Employee'}</DialogTitle>
          <DialogDescription>
            {e ? (<>
              <span className="font-mono text-xs">user_id={e.user_id ?? '—'}</span>
              {e.username && <> · @{e.username}</>}
            </>) : '—'}
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-white/40" /></div>
        ) : !data ? (
          <div className="text-center py-10 text-white/50">Couldn't load this employee.</div>
        ) : (
          <div className="flex-1 overflow-y-auto space-y-5">
            {/* PROFILE */}
            <section className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
              <div className="flex items-start gap-4">
                <div className="h-12 w-12 rounded-full flex items-center justify-center shrink-0"
                     style={{ backgroundColor: STAT_BG }}>
                  <span className="text-base font-semibold" style={{ color: STAT_FG }}>
                    {(e.full_name || e.work_email || '?').slice(0, 1).toUpperCase()}
                  </span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-y-1 gap-x-4 flex-1 text-sm">
                  <KV icon={Mail} label="Email" value={e.work_email} />
                  <KV icon={Briefcase} label="Title" value={e.job_title} />
                  <KV icon={Building2} label="Department" value={e.department_name || e.department} />
                  <KV icon={User} label="Status" value={e.employment_status} />
                  <KV icon={CalendarClock} label="Type" value={e.employment_type?.replace(/_/g, ' ')} />
                  <KV icon={CalendarClock} label="Start" value={e.start_date} />
                  {e.probation_end_date && <KV icon={CalendarClock} label="Probation ends" value={e.probation_end_date} />}
                  {e.timezone_name && <KV icon={CalendarClock} label="Timezone" value={e.timezone_name} />}
                </div>
              </div>
              {chain.length > 0 && (
                <div className="mt-3 pt-3 border-t border-white/[0.06]">
                  <div className="text-[10px] uppercase tracking-wider text-white/50 mb-1.5">Reports up to</div>
                  <div className="flex items-center flex-wrap gap-1 text-sm">
                    {chain.map((m, i) => (
                      <React.Fragment key={m.id}>
                        {i > 0 && <ChevronRight className="h-3 w-3 text-white/40" />}
                        <span className="text-white/85">{m.full_name}</span>
                        {m.job_title && <span className="text-white/45 text-xs">· {m.job_title}</span>}
                      </React.Fragment>
                    ))}
                  </div>
                </div>
              )}
            </section>

            {/* LEAVE BALANCES */}
            <section>
              <SectionTitle icon={ClipboardList} title="Leave balances" count={balances.length} />
              {balances.length === 0 ? (
                <Empty text="No balances tracked yet — set up an accrual policy to populate." />
              ) : (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {balances.map((b, i) => (
                    <div key={i} className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-3">
                      <div className="text-[10px] uppercase tracking-wider text-white/50">{b.leave_type}</div>
                      <div className="text-xl font-bold text-white mt-0.5">{b.remaining}</div>
                      <div className="text-[10px] text-white/40 mt-0.5">
                        {b.accrued_days} accrued · {b.used_days} used
                        {b.carried_over_days ? ` · ${b.carried_over_days} carry` : ''}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* COMPENSATION */}
            <section>
              <div className="flex items-center justify-between mb-2">
                <SectionTitle icon={DollarSign} title="Compensation history" count={comp.allowed ? comp.rows.length : null} />
                {comp.allowed && (
                  <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={openCompForm}>
                    <Plus className="h-3 w-3 mr-1" /> Add
                  </Button>
                )}
              </div>
              {!comp.allowed ? (
                <Empty text="Compensation history is restricted to HR admins." />
              ) : comp.loading ? (
                <div className="flex justify-center py-4"><Loader2 className="h-4 w-4 animate-spin text-white/40" /></div>
              ) : comp.rows.length === 0 ? (
                <Empty text="No compensation records yet. Add one to start tracking pay history." />
              ) : (
                <div className="space-y-1.5">
                  {comp.rows.map((row) => (
                    <div key={row.id} className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-2.5 flex items-center justify-between gap-2 text-sm">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-baseline gap-2 flex-wrap">
                          <span className="text-white font-semibold">
                            {fmtMoney(row.base_salary, row.currency)}
                          </span>
                          <span className="text-[10px] text-white/45">/ {row.pay_frequency}</span>
                          {row.grade && <Badge variant="outline" className="text-[10px]">{row.grade}</Badge>}
                          {row.reason && (
                            <span className="text-[10px] text-white/50">{String(row.reason).replace(/_/g, ' ')}</span>
                          )}
                        </div>
                        <div className="text-xs text-white/50 mt-0.5">
                          effective {row.effective_date}
                          {row.bonus_target_pct != null && row.bonus_target_pct !== '' && <> · bonus {row.bonus_target_pct}%</>}
                          {row.equity_grant_value != null && row.equity_grant_value !== '' && <> · equity {fmtMoney(row.equity_grant_value, row.currency)}</>}
                        </div>
                        {row.notes && <div className="text-xs text-white/40 truncate mt-0.5">{row.notes}</div>}
                      </div>
                      <Button size="sm" variant="ghost" className="h-7 w-7 p-0 shrink-0 text-white/40 hover:text-rose-300"
                              onClick={() => handleDeleteComp(row)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* PERFORMANCE REVIEWS */}
            <section>
              <SectionTitle icon={Star} title="Performance reviews" count={reviews.rows.length} />
              {reviews.loading ? (
                <div className="flex justify-center py-4"><Loader2 className="h-4 w-4 animate-spin text-white/40" /></div>
              ) : reviews.rows.length === 0 ? (
                <Empty text="No performance reviews on file. Activate a review cycle to generate one." />
              ) : (
                <div className="space-y-1.5">
                  {reviews.rows.map((row) => (
                    <div key={row.id} className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-2.5 text-sm">
                      <div className="flex items-baseline justify-between gap-2 flex-wrap">
                        <div className="flex items-baseline gap-2 flex-wrap min-w-0">
                          <span className="text-white font-semibold truncate">{row.cycle_name || `Cycle #${row.cycle_id}`}</span>
                          {row.overall_rating != null && (
                            <span className="text-amber-300 text-xs">{'★'.repeat(row.overall_rating)}{'☆'.repeat(Math.max(0, 5 - row.overall_rating))}</span>
                          )}
                        </div>
                        <Badge variant="outline" className={`text-[10px] ${STATUS_BADGE[row.status === 'closed' ? 'approved' : (row.visible_to_employee ? 'approved' : 'pending')] || ''}`}>
                          {String(row.status || '').replace(/_/g, ' ')}
                        </Badge>
                      </div>
                      {row.reviewer_name && (
                        <div className="text-xs text-white/45 mt-0.5">Reviewer: {row.reviewer_name}</div>
                      )}
                      {row.manager_summary && (
                        <div className="text-xs text-white/70 mt-1 line-clamp-3 whitespace-pre-line">{row.manager_summary}</div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* PERSONAL DOCS */}
            <section>
              <SectionTitle icon={FileText} title="Personal documents" count={docs.length} />
              {docs.length === 0 ? (
                <Empty text="No personal docs. Offer letters, payslips, ID proofs uploaded with employee_id will show here." />
              ) : (
                <div className="space-y-2">
                  {docs.map((d) => {
                    const fields = d.extracted_fields || {};
                    const fieldEntries = Object.entries(fields).filter(([, v]) => v !== null && v !== undefined && v !== '');
                    return (
                      <div key={d.id} className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-3">
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <div className="font-medium text-sm text-white/90 truncate">{d.title}</div>
                          <div className="flex gap-1 flex-wrap">
                            <Badge variant="outline" className="text-[10px]">{d.document_type}</Badge>
                            <Badge variant="outline" className="text-[10px]">{d.confidentiality}</Badge>
                            {d.processing_status === 'failed' && (
                              <Badge variant="outline" className="text-[10px] bg-rose-500/10 text-rose-300 border-rose-400/30">failed</Badge>
                            )}
                          </div>
                        </div>
                        {fieldEntries.length > 0 && (
                          <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-0.5 text-xs">
                            {fieldEntries.slice(0, 8).map(([k, v]) => (
                              <div key={k} className="flex items-baseline gap-1.5 min-w-0">
                                <span className="text-white/45">{k.replace(/_/g, ' ')}:</span>
                                <span className="text-white/85 truncate">{String(v)}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </section>

            {/* LEAVE REQUESTS */}
            <section>
              <SectionTitle icon={ClipboardList} title="Recent leave requests" count={leaves.length} />
              {leaves.length === 0 ? (
                <Empty text="No leave requests on file." />
              ) : (
                <div className="space-y-1.5">
                  {leaves.map((lr) => (
                    <div key={lr.id} className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-2.5 flex items-center justify-between gap-2 text-sm">
                      <div className="min-w-0">
                        <div className="text-white/85">
                          {lr.leave_type} · {lr.start_date} → {lr.end_date}
                          <span className="text-white/45"> · {lr.days_requested}d</span>
                        </div>
                        {lr.reason && <div className="text-xs text-white/50 truncate">{lr.reason}</div>}
                      </div>
                      <Badge variant="outline" className={`text-[10px] shrink-0 ${STATUS_BADGE[lr.status] || ''}`}>
                        {lr.status}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* MEETINGS */}
            <section>
              <SectionTitle icon={CalendarClock} title="Recent HR meetings" count={meetings.length} />
              {meetings.length === 0 ? (
                <Empty text="No HR meetings booked." />
              ) : (
                <div className="space-y-1.5">
                  {meetings.map((m) => (
                    <div key={m.id} className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-2.5 flex items-center justify-between gap-2 text-sm">
                      <div className="min-w-0">
                        <div className="text-white/85 truncate">{m.title}</div>
                        <div className="text-xs text-white/50">
                          {m.meeting_type} · {m.scheduled_at ? new Date(m.scheduled_at).toLocaleString() : 'unscheduled'}
                        </div>
                      </div>
                      <Badge variant="outline" className="text-[10px] shrink-0">{m.status}</Badge>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>
        )}
      </DialogContent>
    </Dialog>

    {/* Create compensation dialog */}
    <Dialog open={compForm.open} onOpenChange={(o) => setCompForm((s) => ({ ...s, open: o }))}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Record compensation change</DialogTitle>
          <DialogDescription>
            New rows are stamped at <code>effective_date</code>. Older rows are kept as history.
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3 py-2">
          <div className="col-span-1">
            <Label className="text-xs">Effective date *</Label>
            <Input type="date" value={compForm.payload.effective_date || ''}
                   onChange={(ev) => setCompField('effective_date', ev.target.value)} />
          </div>
          <div className="col-span-1">
            <Label className="text-xs">Reason</Label>
            <Select value={compForm.payload.reason || 'annual_raise'}
                    onValueChange={(v) => setCompField('reason', v)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="initial">initial</SelectItem>
                <SelectItem value="annual_raise">annual raise</SelectItem>
                <SelectItem value="promotion">promotion</SelectItem>
                <SelectItem value="market_adjustment">market adjustment</SelectItem>
                <SelectItem value="contract_renewal">contract renewal</SelectItem>
                <SelectItem value="correction">correction</SelectItem>
                <SelectItem value="other">other</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="col-span-1">
            <Label className="text-xs">Base salary *</Label>
            <Input type="number" step="0.01" min="0"
                   value={compForm.payload.base_salary || ''}
                   onChange={(ev) => setCompField('base_salary', ev.target.value)} />
          </div>
          <div className="col-span-1">
            <Label className="text-xs">Currency</Label>
            <Input maxLength={3} placeholder="USD"
                   value={compForm.payload.currency || ''}
                   onChange={(ev) => setCompField('currency', ev.target.value.toUpperCase())} />
          </div>
          <div className="col-span-1">
            <Label className="text-xs">Pay frequency</Label>
            <Select value={compForm.payload.pay_frequency || 'annual'}
                    onValueChange={(v) => setCompField('pay_frequency', v)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="annual">annual</SelectItem>
                <SelectItem value="monthly">monthly</SelectItem>
                <SelectItem value="biweekly">biweekly</SelectItem>
                <SelectItem value="weekly">weekly</SelectItem>
                <SelectItem value="hourly">hourly</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="col-span-1">
            <Label className="text-xs">Grade / band</Label>
            <Input value={compForm.payload.grade || ''}
                   onChange={(ev) => setCompField('grade', ev.target.value)} />
          </div>
          <div className="col-span-1">
            <Label className="text-xs">Bonus target %</Label>
            <Input type="number" step="0.01" min="0"
                   value={compForm.payload.bonus_target_pct || ''}
                   onChange={(ev) => setCompField('bonus_target_pct', ev.target.value)} />
          </div>
          <div className="col-span-1">
            <Label className="text-xs">Equity grant value</Label>
            <Input type="number" step="0.01" min="0"
                   value={compForm.payload.equity_grant_value || ''}
                   onChange={(ev) => setCompField('equity_grant_value', ev.target.value)} />
          </div>
          <div className="col-span-2">
            <Label className="text-xs">Notes</Label>
            <Textarea rows={2} value={compForm.payload.notes || ''}
                      onChange={(ev) => setCompField('notes', ev.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setCompForm((s) => ({ ...s, open: false }))}
                  disabled={compForm.saving}>
            Cancel
          </Button>
          <Button onClick={handleSaveComp} disabled={compForm.saving}>
            {compForm.saving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : null}
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    </>
  );
}

const fmtMoney = (amount, currency) => {
  if (amount == null || amount === '') return '—';
  const n = Number(amount);
  if (Number.isNaN(n)) return String(amount);
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency: currency || 'USD', maximumFractionDigits: 0 }).format(n);
  } catch {
    return `${n.toLocaleString()} ${currency || ''}`.trim();
  }
};


// ----- little helpers -----

const KV = ({ icon: Icon, label, value }) => (
  <div className="flex items-baseline gap-2 min-w-0">
    <Icon className="h-3.5 w-3.5 text-white/40 shrink-0 self-center" />
    <span className="text-[10px] uppercase tracking-wider text-white/45">{label}</span>
    <span className="text-white/85 truncate">{value || '—'}</span>
  </div>
);

const SectionTitle = ({ icon: Icon, title, count }) => (
  <div className="flex items-center gap-2 mb-2">
    <Icon className="h-4 w-4 text-violet-400" />
    <span className="text-sm font-medium text-white/90">{title}</span>
    {count != null && <span className="text-[10px] text-white/40">({count})</span>}
  </div>
);

const Empty = ({ text }) => (
  <div className="rounded-lg border border-white/[0.06] bg-white/[0.01] p-3 text-xs text-white/45">{text}</div>
);
