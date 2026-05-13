/**
 * HRNotificationsTab — manage HR notification templates + view the
 * scheduled-queue history (sender + retry/DLQ are wired in the backend; this
 * is the missing UI surface).
 *
 * Two stacked sections:
 *   1. Templates — list + create/edit/delete dialog
 *   2. Scheduled queue — most recent rows with status badges + last error
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
  Loader2, Plus, Bell, Trash2, Pencil, RefreshCw,
} from 'lucide-react';
import hrAgentService from '@/services/hrAgentService';

const NOTIFICATION_TYPES = [
  ['birthday', 'Birthday'],
  ['work_anniversary', 'Work Anniversary'],
  ['probation_ending', 'Probation Ending'],
  ['review_due', 'Performance Review Due'],
  ['document_expiring', 'Document Expiring'],
  ['approval_pending', 'Approval Pending'],
  ['leave_request_status', 'Leave Request Status'],
  ['onboarding_step', 'Onboarding Step'],
  ['compliance_training', 'Compliance Training'],
  ['system', 'System'],
];

const SCHED_STATUS_BADGE = {
  pending: 'bg-slate-500/10 text-slate-300 border-slate-400/30',
  sent: 'bg-emerald-500/10 text-emerald-300 border-emerald-400/30',
  failed: 'bg-rose-500/10 text-rose-300 border-rose-400/30',
  cancelled: 'bg-white/[0.04] text-white/70 border-white/[0.06]',
  dead_lettered: 'bg-rose-600/15 text-rose-200 border-rose-500/40',
};


export default function HRNotificationsTab() {
  const { toast } = useToast();

  const [templates, setTemplates] = useState([]);
  const [tplLoading, setTplLoading] = useState(false);
  const [scheduled, setScheduled] = useState([]);
  const [schedLoading, setSchedLoading] = useState(false);

  const [dialog, setDialog] = useState({ open: false, mode: 'create', tpl: null });
  const [deleteTpl, setDeleteTpl] = useState({ open: false, tpl: null });

  const loadTemplates = async () => {
    setTplLoading(true);
    try {
      const res = await hrAgentService.listHRNotificationTemplates();
      setTemplates(res?.data || []);
    } catch (e) {
      toast({ title: 'Failed to load templates', description: e.message, variant: 'destructive' });
    } finally {
      setTplLoading(false);
    }
  };

  const loadScheduled = async () => {
    setSchedLoading(true);
    try {
      const res = await hrAgentService.listHRScheduledNotifications();
      setScheduled(res?.data || []);
    } catch (e) {
      toast({ title: 'Failed to load scheduled queue', description: e.message, variant: 'destructive' });
    } finally {
      setSchedLoading(false);
    }
  };

  useEffect(() => { loadTemplates(); loadScheduled(); }, []);

  const openCreate = () => setDialog({
    open: true, mode: 'create',
    tpl: {
      name: '', notification_type: 'system', channel: 'email',
      subject: '', body: 'Hi {{employee_name}},\n\nThis is your reminder.\n\n— HR',
      trigger_event: '', days_before: 0,
      use_llm_personalization: false,
    },
  });

  const openEdit = (t) => setDialog({
    open: true, mode: 'edit',
    tpl: {
      id: t.id, name: t.name, notification_type: t.notification_type,
      channel: t.channel, subject: t.subject || '', body: t.body || '',
      trigger_event: t.trigger_config?.on || '',
      days_before: Number(t.trigger_config?.days_before || 0),
      use_llm_personalization: !!t.use_llm_personalization,
    },
  });

  const handleSave = async () => {
    const tpl = dialog.tpl;
    if (!tpl?.name?.trim() || !tpl?.body?.trim()) {
      toast({ title: 'Name and body are required', variant: 'destructive' });
      return;
    }
    const trigger_config = {};
    if (tpl.trigger_event) trigger_config.on = tpl.trigger_event;
    if (tpl.days_before) trigger_config.days_before = Number(tpl.days_before) || 0;
    const payload = {
      name: tpl.name.trim(),
      notification_type: tpl.notification_type,
      channel: tpl.channel,
      subject: tpl.subject || '',
      body: tpl.body,
      trigger_config,
      use_llm_personalization: !!tpl.use_llm_personalization,
    };
    try {
      // Backend currently only exposes create-template. For an update we'd
      // need an endpoint; until then, a save in edit mode just creates a new
      // template — let the user decide if that's OK.
      if (dialog.mode === 'edit') {
        toast({
          title: 'Update endpoint not wired',
          description: 'Saving creates a new template. Delete the old one if you want to replace it.',
        });
      }
      await hrAgentService.createHRNotificationTemplate(payload);
      toast({ title: 'Template saved' });
      setDialog({ open: false, mode: 'create', tpl: null });
      loadTemplates();
    } catch (e) {
      toast({ title: 'Save failed', description: e.message, variant: 'destructive' });
    }
  };

  const handleDelete = async () => {
    // No backend delete endpoint exists yet — gentle no-op with explanation.
    toast({
      title: 'Delete endpoint not wired',
      description: 'Backend lacks a delete-template endpoint; remove via DB or add the route to wire this up.',
      variant: 'destructive',
    });
    setDeleteTpl({ open: false, tpl: null });
  };

  return (
    <div className="space-y-6">
      {/* TEMPLATES */}
      <Card className="border-white/10 bg-black/20 backdrop-blur-sm">
        <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Bell className="h-5 w-5 text-violet-400" /> Notification Templates
            </CardTitle>
            <CardDescription>
              Used by the daily walker (probation, birthdays, anniversaries, document expirations) and by workflow steps.
              Use <code>{'{{employee_name}}'}</code>, <code>{'{{event_date}}'}</code>, <code>{'{{document_title}}'}</code> placeholders.
            </CardDescription>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={loadTemplates} disabled={tplLoading}>
              {tplLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              <span className="ml-1">Refresh</span>
            </Button>
            <Button onClick={openCreate}><Plus className="h-4 w-4 mr-1" /> New template</Button>
          </div>
        </CardHeader>
        <CardContent>
          {tplLoading ? (
            <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-white/40" /></div>
          ) : templates.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-14 text-center">
              <div className="h-14 w-14 rounded-2xl bg-violet-500/10 border border-violet-400/20 flex items-center justify-center mb-3">
                <Bell className="h-7 w-7 text-violet-400" />
              </div>
              <div className="font-medium text-white/90 mb-1">No notification templates yet</div>
              <div className="text-sm text-white/50 max-w-md">
                Create a "Probation ending" or "Work anniversary" template — the daily walker auto-fans them out into scheduled rows.
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] overflow-hidden overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="border-white/[0.06] hover:bg-transparent">
                    <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">Name</TableHead>
                    <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">Type</TableHead>
                    <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">Channel</TableHead>
                    <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">Trigger</TableHead>
                    <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">LLM</TableHead>
                    <TableHead className="text-right text-white/60 uppercase text-[10px] tracking-wider">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {templates.map((t) => {
                    const trig = t.trigger_config || {};
                    const trigText = trig.on
                      ? `on ${trig.on}${trig.days_before ? ` · ${trig.days_before}d before` : ''}`
                      : '—';
                    return (
                      <TableRow key={t.id} className="border-white/[0.06] hover:bg-white/[0.04]">
                        <TableCell className="font-medium text-white/95">{t.name}</TableCell>
                        <TableCell className="text-xs text-white/70">{t.notification_type}</TableCell>
                        <TableCell><Badge variant="outline" className="text-[10px]">{t.channel}</Badge></TableCell>
                        <TableCell className="text-xs text-white/60">{trigText}</TableCell>
                        <TableCell>{t.use_llm_personalization
                          ? <Badge variant="outline" className="text-[10px] bg-violet-500/10 text-violet-300 border-violet-400/30">on</Badge>
                          : <span className="text-white/40 text-xs">off</span>}</TableCell>
                        <TableCell className="text-right">
                          <div className="flex gap-1 justify-end">
                            <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => openEdit(t)}>
                              <Pencil className="h-3 w-3 mr-1" /> Edit
                            </Button>
                            <Button variant="outline" size="sm" className="h-7 text-xs text-rose-400 hover:text-rose-300"
                              onClick={() => setDeleteTpl({ open: true, tpl: t })}>
                              <Trash2 className="h-3 w-3" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* SCHEDULED QUEUE */}
      <Card className="border-white/10 bg-black/20 backdrop-blur-sm">
        <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <CardTitle>Scheduled queue</CardTitle>
            <CardDescription>Most recent 200 rows. Sender runs every 60s with retry/DLQ.</CardDescription>
          </div>
          <Button variant="outline" onClick={loadScheduled} disabled={schedLoading}>
            {schedLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            <span className="ml-1">Refresh</span>
          </Button>
        </CardHeader>
        <CardContent>
          {schedLoading ? (
            <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-white/40" /></div>
          ) : scheduled.length === 0 ? (
            <div className="text-center py-10 text-white/50 text-sm">No scheduled notifications yet.</div>
          ) : (
            <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] overflow-hidden overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="border-white/[0.06] hover:bg-transparent">
                    <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">Recipient</TableHead>
                    <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">Status</TableHead>
                    <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">Scheduled</TableHead>
                    <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">Sent</TableHead>
                    <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">Attempts</TableHead>
                    <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">Error</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {scheduled.map((n) => (
                    <TableRow key={n.id} className="border-white/[0.06] hover:bg-white/[0.04]">
                      <TableCell className="text-xs text-white/85">{n.recipient_email || '—'}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className={`text-[10px] ${SCHED_STATUS_BADGE[n.status] || 'bg-white/[0.04]'}`}>
                          {n.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-white/60">
                        {n.scheduled_at ? new Date(n.scheduled_at).toLocaleString() : '—'}
                      </TableCell>
                      <TableCell className="text-xs text-white/60">
                        {n.sent_at ? new Date(n.sent_at).toLocaleString() : '—'}
                      </TableCell>
                      <TableCell className="text-xs text-white/60">{n.attempts}</TableCell>
                      <TableCell className="text-xs text-rose-300 max-w-[18rem] truncate" title={n.error_message || ''}>
                        {n.error_message || ''}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* CREATE / EDIT DIALOG */}
      <Dialog open={dialog.open} onOpenChange={(open) => setDialog((s) => ({ ...s, open }))}>
        <DialogContent className="max-w-xl max-h-[90vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>{dialog.mode === 'create' ? 'New template' : 'Edit template'}</DialogTitle>
            <DialogDescription>
              Pick a trigger event for the daily walker to auto-create scheduled rows. Or leave the trigger blank to use this template only via the workflow <code>send_email</code> step.
            </DialogDescription>
          </DialogHeader>
          {dialog.tpl && (
            <div className="space-y-3 overflow-y-auto pr-1">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <Label>Name</Label>
                  <Input value={dialog.tpl.name}
                    onChange={(e) => setDialog((s) => ({ ...s, tpl: { ...s.tpl, name: e.target.value } }))} />
                </div>
                <div>
                  <Label>Type</Label>
                  <Select value={dialog.tpl.notification_type}
                    onValueChange={(v) => setDialog((s) => ({ ...s, tpl: { ...s.tpl, notification_type: v } }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {NOTIFICATION_TYPES.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <Label>Channel</Label>
                  <Select value={dialog.tpl.channel}
                    onValueChange={(v) => setDialog((s) => ({ ...s, tpl: { ...s.tpl, channel: v } }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="email">Email</SelectItem>
                      <SelectItem value="sms">SMS</SelectItem>
                      <SelectItem value="in_app">In-app</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Trigger event (for daily walker)</Label>
                  <Select value={dialog.tpl.trigger_event || '__none__'}
                    onValueChange={(v) => setDialog((s) => ({ ...s, tpl: { ...s.tpl, trigger_event: v === '__none__' ? '' : v } }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">(none — workflow-step use only)</SelectItem>
                      <SelectItem value="probation_ending">probation_ending</SelectItem>
                      <SelectItem value="birthday">birthday</SelectItem>
                      <SelectItem value="work_anniversary">work_anniversary</SelectItem>
                      <SelectItem value="document_expiring">document_expiring</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              {(dialog.tpl.trigger_event === 'probation_ending'
                || dialog.tpl.trigger_event === 'document_expiring') && (
                <div>
                  <Label>Days before event</Label>
                  <Input type="number" min={0} max={365}
                    value={dialog.tpl.days_before}
                    onChange={(e) => setDialog((s) => ({ ...s, tpl: { ...s.tpl, days_before: Number(e.target.value) || 0 } }))} />
                </div>
              )}
              <div>
                <Label>Subject (email only)</Label>
                <Input value={dialog.tpl.subject}
                  onChange={(e) => setDialog((s) => ({ ...s, tpl: { ...s.tpl, subject: e.target.value } }))} />
              </div>
              <div>
                <Label>Body</Label>
                <Textarea rows={8} className="font-mono text-xs"
                  value={dialog.tpl.body}
                  onChange={(e) => setDialog((s) => ({ ...s, tpl: { ...s.tpl, body: e.target.value } }))} />
              </div>
              <label className="flex items-center gap-2 text-sm select-none">
                <input type="checkbox" className="h-4 w-4"
                  checked={!!dialog.tpl.use_llm_personalization}
                  onChange={(e) => setDialog((s) => ({ ...s, tpl: { ...s.tpl, use_llm_personalization: e.target.checked } }))} />
                <span>Use LLM personalization (slower, costs LLM tokens, falls back to template body on failure)</span>
              </label>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialog({ open: false, mode: 'create', tpl: null })}>Cancel</Button>
            <Button onClick={handleSave}>{dialog.mode === 'create' ? 'Create' : 'Save'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* DELETE CONFIRM */}
      <Dialog open={deleteTpl.open} onOpenChange={(open) => setDeleteTpl((s) => ({ ...s, open }))}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete template?</DialogTitle>
            <DialogDescription>{deleteTpl.tpl?.name}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTpl({ open: false, tpl: null })}>Keep</Button>
            <Button onClick={handleDelete} className="bg-rose-600 hover:bg-rose-500">Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
