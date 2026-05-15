/**
 * HRMyProfilePage — employee self-service entry point.
 *
 * Calls GET /hr/me — the backend resolves the caller's Employee row by
 * company_user FK (or work_email fallback). Shows profile, leave balances,
 * personal docs, recent leave requests, and upcoming meetings. Employees can
 * self-edit phone + timezone (enforced backend-side) and submit a new leave
 * request inline without bouncing through the admin tabs.
 */
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import {
  Loader2, User, Mail, Briefcase, Building2, CalendarClock, PlaneTakeoff,
  FileText, Pencil, Plus, ClipboardList, LayoutDashboard, AlertCircle,
} from 'lucide-react';
import hrAgentService from '@/services/hrAgentService';


const STATUS_BADGE = {
  pending: 'bg-amber-500/10 text-amber-300 border-amber-400/30',
  approved: 'bg-emerald-500/10 text-emerald-300 border-emerald-400/30',
  rejected: 'bg-rose-500/10 text-rose-300 border-rose-400/30',
  cancelled: 'bg-slate-500/10 text-slate-300 border-slate-400/30',
};


export default function HRMyProfilePage() {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [editOpen, setEditOpen] = useState(false);
  const [editPayload, setEditPayload] = useState({ phone: '', timezone_name: '' });
  const [editSaving, setEditSaving] = useState(false);

  const [leaveOpen, setLeaveOpen] = useState(false);
  const [leaveForm, setLeaveForm] = useState({ leave_type: 'vacation', start_date: '', end_date: '', reason: '' });
  const [leaveSaving, setLeaveSaving] = useState(false);

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const res = await hrAgentService.getMyHRProfile();
      setData(res?.data || null);
    } catch (e) {
      setError(e.message || 'Failed to load profile');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const openEdit = () => {
    const e = data?.employee || {};
    setEditPayload({ phone: e.phone || '', timezone_name: e.timezone_name || 'UTC' });
    setEditOpen(true);
  };

  const handleSaveEdit = async () => {
    if (!data?.employee?.id) return;
    setEditSaving(true);
    try {
      const res = await hrAgentService.updateHREmployee(data.employee.id, editPayload);
      if (res?.data) setData((s) => ({ ...s, employee: res.data }));
      toast({ title: 'Profile updated' });
      setEditOpen(false);
    } catch (e) {
      toast({ title: 'Save failed', description: e.message, variant: 'destructive' });
    } finally {
      setEditSaving(false);
    }
  };

  const handleSubmitLeave = async () => {
    if (!data?.employee?.id) return;
    if (!leaveForm.start_date || !leaveForm.end_date) {
      toast({ title: 'Pick a start and end date', variant: 'destructive' });
      return;
    }
    if (leaveForm.end_date < leaveForm.start_date) {
      toast({ title: 'End must be on or after start', variant: 'destructive' });
      return;
    }
    setLeaveSaving(true);
    try {
      await hrAgentService.submitLeaveRequest({ ...leaveForm, employee_id: data.employee.id });
      toast({ title: 'Leave request submitted' });
      setLeaveOpen(false);
      setLeaveForm({ leave_type: 'vacation', start_date: '', end_date: '', reason: '' });
      load();
    } catch (e) {
      toast({ title: 'Submit failed', description: e.message, variant: 'destructive' });
    } finally {
      setLeaveSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-white/40" />
      </div>
    );
  }
  if (error) {
    return (
      <Card className="border-white/10 bg-black/20 max-w-2xl mx-auto mt-8">
        <CardContent className="py-12 text-center">
          <AlertCircle className="h-10 w-10 text-rose-400 mx-auto mb-3" />
          <div className="text-white/90 mb-2">Couldn't load your profile</div>
          <div className="text-white/55 text-sm mb-4">{error}</div>
          <Button asChild variant="outline">
            <Link to="/hr/dashboard"><LayoutDashboard className="h-4 w-4 mr-1" /> HR dashboard</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }
  if (!data) return null;

  const e = data.employee || {};
  const balances = data.leave_balances || [];
  const docs = data.personal_documents || [];
  const leaves = data.leave_requests || [];
  const meetings = data.meetings || [];

  return (
    <div className="space-y-4 max-w-5xl mx-auto p-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <User className="h-6 w-6 text-violet-400" /> My profile
          </h1>
          <p className="text-sm text-white/55">{e.full_name} · {e.job_title || '—'}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={openEdit}>
            <Pencil className="h-4 w-4 mr-1" /> Edit profile
          </Button>
          <Button onClick={() => setLeaveOpen(true)}>
            <PlaneTakeoff className="h-4 w-4 mr-1" /> Request leave
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Profile */}
        <Card className="border-white/10 bg-black/20 lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Briefcase className="h-4 w-4 text-violet-400" /> Profile
            </CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 sm:grid-cols-2 gap-y-2 gap-x-6 text-sm">
            <Field icon={Mail} label="Email" value={e.work_email} />
            <Field icon={Briefcase} label="Title" value={e.job_title} />
            <Field icon={Building2} label="Department" value={e.department_name || e.department} />
            <Field icon={CalendarClock} label="Start date" value={e.start_date} />
            <Field icon={User} label="Manager" value={e.manager_name || '—'} />
            <Field icon={User} label="Phone" value={e.phone || '—'} />
            <Field icon={User} label="Timezone" value={e.timezone_name || 'UTC'} />
            <Field icon={User} label="Status" value={e.employment_status} />
          </CardContent>
        </Card>

        {/* Leave balances */}
        <Card className="border-white/10 bg-black/20">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <PlaneTakeoff className="h-4 w-4 text-violet-400" /> Leave balances
            </CardTitle>
            <CardDescription className="text-xs">Days remaining for this period.</CardDescription>
          </CardHeader>
          <CardContent>
            {balances.length === 0 ? (
              <div className="text-white/45 text-sm">No balances on file.</div>
            ) : (
              <div className="space-y-1.5">
                {balances.map((b, idx) => (
                  <div key={idx} className="flex items-baseline justify-between text-sm">
                    <span className="text-white/75 capitalize">{b.leave_type.replace(/_/g, ' ')}</span>
                    <span className="font-mono text-violet-300">{b.remaining.toFixed(1)}d</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* My leave requests */}
      <Card className="border-white/10 bg-black/20">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ClipboardList className="h-4 w-4 text-violet-400" /> Recent leave requests
          </CardTitle>
        </CardHeader>
        <CardContent>
          {leaves.length === 0 ? (
            <div className="text-white/45 text-sm">No leave requests yet.</div>
          ) : (
            <div className="space-y-1.5">
              {leaves.slice(0, 10).map((lr) => (
                <div key={lr.id} className="flex items-baseline justify-between gap-2 flex-wrap rounded-lg border border-white/[0.08] bg-white/[0.02] p-2 text-sm">
                  <div className="flex items-baseline gap-2 min-w-0">
                    <Badge variant="outline" className="text-[10px]">{lr.leave_type}</Badge>
                    <span className="text-white/75">{lr.start_date} → {lr.end_date}</span>
                    <span className="text-white/45 text-xs">({lr.days_requested}d)</span>
                  </div>
                  <Badge variant="outline" className={`text-[10px] ${STATUS_BADGE[lr.status] || ''}`}>
                    {lr.status}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Personal docs */}
      <Card className="border-white/10 bg-black/20">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileText className="h-4 w-4 text-violet-400" /> My documents
          </CardTitle>
          <CardDescription className="text-xs">Offer letters, contracts, payslips, ID proofs filed against your record.</CardDescription>
        </CardHeader>
        <CardContent>
          {docs.length === 0 ? (
            <div className="text-white/45 text-sm">No personal documents on file.</div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {docs.map((d) => (
                <div key={d.id} className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-2.5 text-sm">
                  <div className="font-medium text-white/90 truncate">{d.title}</div>
                  <div className="flex gap-1 mt-1 flex-wrap">
                    <Badge variant="outline" className="text-[10px]">{d.document_type}</Badge>
                    <Badge variant="outline" className="text-[10px]">{d.confidentiality}</Badge>
                    {d.version > 1 && (
                      <Badge variant="outline" className="text-[10px] bg-sky-500/10 text-sky-300 border-sky-400/30">v{d.version}</Badge>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Upcoming meetings */}
      <Card className="border-white/10 bg-black/20">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <CalendarClock className="h-4 w-4 text-violet-400" /> Recent / upcoming meetings
          </CardTitle>
        </CardHeader>
        <CardContent>
          {meetings.length === 0 ? (
            <div className="text-white/45 text-sm">Nothing scheduled.</div>
          ) : (
            <div className="space-y-1.5">
              {meetings.map((m) => (
                <div key={m.id} className="flex items-baseline justify-between gap-2 flex-wrap rounded-lg border border-white/[0.08] bg-white/[0.02] p-2 text-sm">
                  <div className="min-w-0">
                    <div className="text-white/85 truncate">{m.title}</div>
                    <div className="text-[11px] text-white/45">
                      {m.meeting_type} · {(m.scheduled_at || '').slice(0, 16).replace('T', ' ')}
                    </div>
                  </div>
                  <Badge variant="outline" className="text-[10px]">{m.status}</Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Edit dialog (phone + timezone only) */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Edit profile</DialogTitle>
            <DialogDescription>You can update your phone number and timezone. For other changes, contact HR.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Phone</Label>
              <Input value={editPayload.phone}
                onChange={(ev) => setEditPayload((s) => ({ ...s, phone: ev.target.value }))} />
            </div>
            <div>
              <Label>Timezone</Label>
              <Input placeholder="UTC" value={editPayload.timezone_name}
                onChange={(ev) => setEditPayload((s) => ({ ...s, timezone_name: ev.target.value }))} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditOpen(false)} disabled={editSaving}>Cancel</Button>
            <Button onClick={handleSaveEdit} disabled={editSaving}>
              {editSaving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Submit leave dialog */}
      <Dialog open={leaveOpen} onOpenChange={setLeaveOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Request leave</DialogTitle>
            <DialogDescription>Working days are auto-counted (weekends and company holidays excluded).</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Leave type</Label>
              <Select value={leaveForm.leave_type}
                onValueChange={(v) => setLeaveForm((s) => ({ ...s, leave_type: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="vacation">Vacation / PTO</SelectItem>
                  <SelectItem value="sick">Sick</SelectItem>
                  <SelectItem value="parental">Parental</SelectItem>
                  <SelectItem value="bereavement">Bereavement</SelectItem>
                  <SelectItem value="unpaid">Unpaid</SelectItem>
                  <SelectItem value="other">Other</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Start</Label>
                <Input type="date" value={leaveForm.start_date}
                  onChange={(ev) => setLeaveForm((s) => ({ ...s, start_date: ev.target.value }))} />
              </div>
              <div>
                <Label>End</Label>
                <Input type="date" value={leaveForm.end_date}
                  onChange={(ev) => setLeaveForm((s) => ({ ...s, end_date: ev.target.value }))} />
              </div>
            </div>
            <div>
              <Label>Reason (optional)</Label>
              <Textarea rows={2} value={leaveForm.reason}
                onChange={(ev) => setLeaveForm((s) => ({ ...s, reason: ev.target.value }))} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setLeaveOpen(false)} disabled={leaveSaving}>Cancel</Button>
            <Button onClick={handleSubmitLeave} disabled={leaveSaving}>
              {leaveSaving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}Submit
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}


function Field({ icon: Icon, label, value }) {
  return (
    <div className="flex items-baseline gap-2 min-w-0">
      <Icon className="h-3.5 w-3.5 text-white/40 shrink-0" />
      <span className="text-white/45 text-xs uppercase tracking-wider w-24 shrink-0">{label}</span>
      <span className="text-white/85 truncate">{value || '—'}</span>
    </div>
  );
}
