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
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Loader2, User, Briefcase, Building2, Mail, CalendarClock, FileText, ClipboardList, ChevronRight } from 'lucide-react';
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
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !employeeId) {
      setData(null);
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

  const e = data?.employee;
  const chain = data?.manager_chain || [];
  const balances = data?.leave_balances || [];
  const docs = data?.personal_documents || [];
  const leaves = data?.leave_requests || [];
  const meetings = data?.meetings || [];

  return (
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
                  <KV icon={Building2} label="Department" value={e.department} />
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
  );
}


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
