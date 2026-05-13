/**
 * HRLeaveTab — three sub-views in one tab:
 *   * Pending for me — requests where the caller is the assigned approver
 *   * My requests — requests submitted by the caller
 *   * All requests — full company queue (HR-admin shaped)
 *
 * Plus a "Submit" dialog and approve/reject dialogs.
 *
 * Backend: list_leave_requests + submit + decide. Approval permission is
 * enforced server-side (assigned approver OR HR-roled CompanyUser).
 */
import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { useToast } from '@/components/ui/use-toast';
import {
  Loader2, Plus, RefreshCw, Check, X, ClipboardList,
} from 'lucide-react';
import hrAgentService from '@/services/hrAgentService';

const STATUS_BADGE = {
  pending: 'bg-amber-500/10 text-amber-300 border-amber-400/30',
  approved: 'bg-emerald-500/10 text-emerald-300 border-emerald-400/30',
  rejected: 'bg-rose-500/10 text-rose-300 border-rose-400/30',
  cancelled: 'bg-slate-500/10 text-slate-300 border-slate-400/30',
};


export default function HRLeaveTab() {
  const { toast } = useToast();
  const [view, setView] = useState('pending_for_me'); // 'pending_for_me' | 'mine' | 'all'
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  const [employees, setEmployees] = useState([]);
  const [submitOpen, setSubmitOpen] = useState(false);
  const [form, setForm] = useState({
    employee_id: '', leave_type: 'vacation',
    start_date: '', end_date: '', reason: '',
  });
  const [submitting, setSubmitting] = useState(false);

  const [decideDialog, setDecideDialog] = useState({ open: false, lr: null, action: 'approve', note: '' });

  const load = async () => {
    setLoading(true);
    try {
      const params = {};
      if (view === 'pending_for_me') params.pending_for_me = 1;
      else if (view === 'mine') params.mine = 1;
      // 'all' — no filter
      const res = await hrAgentService.listLeaveRequests(params);
      setRows(res?.data || []);
    } catch (e) {
      toast({ title: 'Failed to load leave requests', description: e.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const loadEmployees = async () => {
    try {
      const res = await hrAgentService.listHREmployees({ limit: 200 });
      setEmployees(res?.data || []);
    } catch { /* keep silent — submit dialog will show empty list */ }
  };

  useEffect(() => { load(); }, [view]);
  useEffect(() => { loadEmployees(); }, []);

  const openSubmit = () => {
    setForm({ employee_id: '', leave_type: 'vacation', start_date: '', end_date: '', reason: '' });
    setSubmitOpen(true);
  };

  const handleSubmit = async () => {
    if (!form.employee_id || !form.start_date || !form.end_date) {
      toast({ title: 'Pick employee + start & end date', variant: 'destructive' });
      return;
    }
    if (form.end_date < form.start_date) {
      toast({ title: 'End date must be on or after start date', variant: 'destructive' });
      return;
    }
    setSubmitting(true);
    try {
      const res = await hrAgentService.submitLeaveRequest(form);
      const lr = res?.data || {};
      toast({
        title: 'Leave requested',
        description: lr.approver_name
          ? `Approver: ${lr.approver_name} · ${lr.days_requested} working day(s)`
          : `${lr.days_requested} working day(s) — no approver assigned`,
      });
      setSubmitOpen(false);
      load();
    } catch (e) {
      toast({ title: 'Submit failed', description: e.message, variant: 'destructive' });
    } finally {
      setSubmitting(false);
    }
  };

  const openDecide = (lr, action) => setDecideDialog({ open: true, lr, action, note: '' });

  const handleDecide = async () => {
    const { lr, action, note } = decideDialog;
    if (!lr) return;
    try {
      await hrAgentService.decideLeaveRequest(lr.id, action, note);
      toast({ title: action === 'approve' ? 'Approved' : 'Rejected' });
      setDecideDialog({ open: false, lr: null, action: 'approve', note: '' });
      load();
    } catch (e) {
      toast({ title: 'Decision failed', description: e.message, variant: 'destructive' });
    }
  };

  return (
    <div className="space-y-4">
      <Card className="border-white/10 bg-black/20 backdrop-blur-sm">
        <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <ClipboardList className="h-5 w-5 text-violet-400" /> Leave requests
            </CardTitle>
            <CardDescription>
              Working-day count skips weekends + your <strong>Holiday</strong> rows. Approval auto-routes to the employee's manager
              (or HR if no manager set).
            </CardDescription>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={load} disabled={loading}>
              {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              <span className="ml-1">Refresh</span>
            </Button>
            <Button onClick={openSubmit}><Plus className="h-4 w-4 mr-1" /> New request</Button>
          </div>
        </CardHeader>
        <CardContent>
          {/* View switcher */}
          <div className="flex gap-1 rounded-lg border border-white/[0.08] p-0.5 mb-4 w-fit">
            {[
              ['pending_for_me', 'Pending for me'],
              ['mine', 'My requests'],
              ['all', 'All'],
            ].map(([v, label]) => (
              <button key={v} onClick={() => setView(v)}
                className={`px-3 py-1.5 text-xs rounded-md ${
                  view === v ? 'bg-violet-600/30 text-violet-200' : 'text-white/60 hover:bg-white/[0.04]'
                }`}>
                {label}
              </button>
            ))}
          </div>

          {loading ? (
            <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-white/40" /></div>
          ) : rows.length === 0 ? (
            <div className="text-center py-10 text-white/50 text-sm">
              {view === 'pending_for_me' ? 'No requests waiting on you.' : 'No leave requests.'}
            </div>
          ) : (
            <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] overflow-hidden overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="border-white/[0.06] hover:bg-transparent">
                    <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">Employee</TableHead>
                    <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">Type</TableHead>
                    <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">Dates</TableHead>
                    <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">Days</TableHead>
                    <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">Approver</TableHead>
                    <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">Status</TableHead>
                    <TableHead className="text-right text-white/60 uppercase text-[10px] tracking-wider">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((lr) => (
                    <TableRow key={lr.id} className="border-white/[0.06] hover:bg-white/[0.04]">
                      <TableCell className="font-medium text-white/95 text-sm">
                        {lr.employee_name || '—'}
                        <div className="text-[10px] text-white/45">{lr.employee_email}</div>
                      </TableCell>
                      <TableCell><Badge variant="outline" className="text-[10px]">{lr.leave_type}</Badge></TableCell>
                      <TableCell className="text-xs text-white/70">
                        {lr.start_date} → {lr.end_date}
                      </TableCell>
                      <TableCell className="text-sm text-white/85">{lr.days_requested}</TableCell>
                      <TableCell className="text-xs text-white/70">{lr.approver_name || '—'}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className={`text-[10px] ${STATUS_BADGE[lr.status] || ''}`}>
                          {lr.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        {lr.status === 'pending' ? (
                          <div className="flex gap-1 justify-end">
                            <Button variant="outline" size="sm" className="h-7 text-xs text-emerald-300 hover:text-emerald-200"
                              onClick={() => openDecide(lr, 'approve')}>
                              <Check className="h-3 w-3 mr-1" /> Approve
                            </Button>
                            <Button variant="outline" size="sm" className="h-7 text-xs text-rose-400 hover:text-rose-300"
                              onClick={() => openDecide(lr, 'reject')}>
                              <X className="h-3 w-3 mr-1" /> Reject
                            </Button>
                          </div>
                        ) : (
                          <span className="text-xs text-white/40">—</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* SUBMIT DIALOG */}
      <Dialog open={submitOpen} onOpenChange={setSubmitOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>New leave request</DialogTitle>
            <DialogDescription>Days are auto-counted by working day (weekends + holidays excluded).</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Employee</Label>
              <Select value={form.employee_id ? String(form.employee_id) : ''}
                onValueChange={(v) => setForm((s) => ({ ...s, employee_id: Number(v) }))}>
                <SelectTrigger><SelectValue placeholder="Pick employee" /></SelectTrigger>
                <SelectContent>
                  {employees.map((e) => (
                    <SelectItem key={e.id} value={String(e.id)}>
                      {e.full_name || e.work_email}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Leave type</Label>
              <Select value={form.leave_type}
                onValueChange={(v) => setForm((s) => ({ ...s, leave_type: v }))}>
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
                <Label>Start date</Label>
                <Input type="date" value={form.start_date}
                  onChange={(e) => setForm((s) => ({ ...s, start_date: e.target.value }))} />
              </div>
              <div>
                <Label>End date</Label>
                <Input type="date" value={form.end_date}
                  onChange={(e) => setForm((s) => ({ ...s, end_date: e.target.value }))} />
              </div>
            </div>
            <div>
              <Label>Reason (optional)</Label>
              <Textarea rows={2} value={form.reason}
                onChange={(e) => setForm((s) => ({ ...s, reason: e.target.value }))} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSubmitOpen(false)} disabled={submitting}>Cancel</Button>
            <Button onClick={handleSubmit} disabled={submitting}>
              {submitting ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}Submit
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* APPROVE / REJECT DIALOG */}
      <Dialog open={decideDialog.open} onOpenChange={(open) => setDecideDialog((s) => ({ ...s, open }))}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{decideDialog.action === 'approve' ? 'Approve request' : 'Reject request'}</DialogTitle>
            <DialogDescription>
              {decideDialog.lr ? (
                <>
                  {decideDialog.lr.employee_name} · {decideDialog.lr.leave_type} ·{' '}
                  {decideDialog.lr.days_requested} day(s) ({decideDialog.lr.start_date} → {decideDialog.lr.end_date})
                </>
              ) : null}
            </DialogDescription>
          </DialogHeader>
          <Textarea rows={2} placeholder="Optional note for the employee..."
            value={decideDialog.note}
            onChange={(e) => setDecideDialog((s) => ({ ...s, note: e.target.value }))} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setDecideDialog({ open: false, lr: null, action: 'approve', note: '' })}>Cancel</Button>
            <Button onClick={handleDecide}
              className={decideDialog.action === 'approve' ? '' : 'bg-rose-600 hover:bg-rose-500'}>
              {decideDialog.action === 'approve' ? 'Approve' : 'Reject'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
