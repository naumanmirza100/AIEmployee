import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { 
  Loader2, 
  FileText, 
  Upload, 
  MessageSquare,
  Ticket,
  Search,
  Trash2,
  Headphones,
  CheckCircle2,
  XCircle,
  Send,
  Plus,
  MessageCircle,
  ChevronLeft,
  ChevronRight,
  Bell,
  GitBranch,
  BarChart3,
  Mail,
  FileSearch,
  ListChecks,
  Pencil,
} from 'lucide-react';
import frontlineAgentService from '@/services/frontlineAgentService';

const TEMPLATE_DEFAULT = { name: '', subject: '', body: '', notification_type: 'ticket_update', channel: 'email' };
const WORKFLOW_STEPS_DEFAULT = '[{"type": "send_email", "template_id": 1, "recipient_email": "{{recipient_email}}"}]';

function FrontlineNotificationsTab() {
  const { toast } = useToast();
  const [templates, setTemplates] = useState([]);
  const [scheduled, setScheduled] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sendForm, setSendForm] = useState({ template_id: '', recipient_email: '', ticket_id: '' });
  const [sending, setSending] = useState(false);
  const [templateDialog, setTemplateDialog] = useState({ open: false, editingId: null, ...TEMPLATE_DEFAULT });
  const [savingTemplate, setSavingTemplate] = useState(false);
  const load = async () => {
    setLoading(true);
    try {
      const [tRes, sRes] = await Promise.all([frontlineAgentService.listNotificationTemplates(), frontlineAgentService.listScheduledNotifications()]);
      setTemplates((tRes.status === 'success' && tRes.data) ? tRes.data : []);
      setScheduled((sRes.status === 'success' && sRes.data) ? sRes.data : []);
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to load', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);
  const handleSendNow = async (e) => {
    e.preventDefault();
    if (!sendForm.template_id || !sendForm.recipient_email) {
      toast({ title: 'Error', description: 'Template and recipient email required', variant: 'destructive' });
      return;
    }
    setSending(true);
    try {
      const res = await frontlineAgentService.sendNotificationNow({
        template_id: parseInt(sendForm.template_id, 10),
        recipient_email: sendForm.recipient_email,
        ticket_id: sendForm.ticket_id ? parseInt(sendForm.ticket_id, 10) : undefined,
      });
      if (res.status === 'success') {
        toast({ title: 'Sent', description: 'Notification sent.' });
        setSendForm({ template_id: '', recipient_email: '', ticket_id: '' });
        load();
      } else throw new Error(res.message);
    } catch (err) {
      toast({ title: 'Error', description: err.message || 'Send failed', variant: 'destructive' });
    } finally {
      setSending(false);
    }
  };
  const openCreateTemplate = () => setTemplateDialog({ open: true, editingId: null, ...TEMPLATE_DEFAULT });
  const openEditTemplate = (t) => setTemplateDialog({ open: true, editingId: t.id, name: t.name || '', subject: t.subject || '', body: t.body || '', notification_type: t.notification_type || 'ticket_update', channel: t.channel || 'email' });
  const handleSaveTemplate = async (e) => {
    e.preventDefault();
    if (!templateDialog.name.trim()) {
      toast({ title: 'Error', description: 'Name is required', variant: 'destructive' });
      return;
    }
    setSavingTemplate(true);
    try {
      if (templateDialog.editingId) {
        const res = await frontlineAgentService.updateNotificationTemplate(templateDialog.editingId, {
          name: templateDialog.name.trim(),
          subject: templateDialog.subject,
          body: templateDialog.body,
          notification_type: templateDialog.notification_type,
          channel: templateDialog.channel,
        });
        if (res.status === 'success') {
          toast({ title: 'Saved', description: 'Template updated.' });
          setTemplateDialog({ open: false, editingId: null, ...TEMPLATE_DEFAULT });
          load();
        } else throw new Error(res.message);
      } else {
        const res = await frontlineAgentService.createNotificationTemplate({
          name: templateDialog.name.trim(),
          subject: templateDialog.subject,
          body: templateDialog.body,
          notification_type: templateDialog.notification_type,
          channel: templateDialog.channel,
        });
        if (res.status === 'success') {
          toast({ title: 'Created', description: 'Template created.' });
          setTemplateDialog({ open: false, editingId: null, ...TEMPLATE_DEFAULT });
          load();
        } else throw new Error(res.message);
      }
    } catch (err) {
      toast({ title: 'Error', description: err.message || 'Failed to save template', variant: 'destructive' });
    } finally {
      setSavingTemplate(false);
    }
  };
  const handleDeleteTemplate = async (t) => {
    if (!confirm(`Delete template "${t.name}"?`)) return;
    try {
      const res = await frontlineAgentService.deleteNotificationTemplate(t.id);
      if (res.status === 'success') {
        toast({ title: 'Deleted', description: 'Template removed.' });
        load();
      } else throw new Error(res.message);
    } catch (err) {
      toast({ title: 'Error', description: err.message || 'Delete failed', variant: 'destructive' });
    }
  };
  return (
  <>
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="flex items-center gap-2"><Bell className="h-5 w-5" /> Notifications</CardTitle>
          <CardDescription>Templates and send/schedule notifications (email).</CardDescription>
        </div>
        <Button onClick={openCreateTemplate}><Plus className="h-4 w-4 mr-2" /> Create template</Button>
      </CardHeader>
      <CardContent className="space-y-6">
        <form onSubmit={handleSendNow} className="flex flex-wrap items-end gap-3 p-3 border rounded-lg">
          <div className="space-y-1">
            <Label>Template</Label>
            <Select value={sendForm.template_id} onValueChange={(v) => setSendForm((f) => ({ ...f, template_id: v }))}>
              <SelectTrigger className="w-[200px]"><SelectValue placeholder="Select template" /></SelectTrigger>
              <SelectContent>
                {templates.map((t) => <SelectItem key={t.id} value={String(t.id)}>{t.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>To email</Label>
            <Input placeholder="email@example.com" value={sendForm.recipient_email} onChange={(e) => setSendForm((f) => ({ ...f, recipient_email: e.target.value }))} className="w-[200px]" />
          </div>
          <div className="space-y-1">
            <Label>Ticket ID (optional)</Label>
            <Input placeholder="123" value={sendForm.ticket_id} onChange={(e) => setSendForm((f) => ({ ...f, ticket_id: e.target.value }))} className="w-[80px]" />
          </div>
          <Button type="submit" disabled={sending}>Send now</Button>
        </form>
        {loading ? <div className="flex justify-center py-4"><Loader2 className="h-6 w-6 animate-spin" /></div> : (
          <>
            <div>
              <h4 className="font-medium mb-2">Templates ({templates.length})</h4>
              <div className="space-y-2 max-h-40 overflow-y-auto">
                {templates.length === 0 ? <p className="text-sm text-muted-foreground">No templates yet. Click &quot;Create template&quot; to add one.</p> : templates.map((t) => (
                  <div key={t.id} className="flex justify-between items-center p-2 border rounded text-sm">
                    <span>{t.name}</span>
                    <div className="flex items-center gap-1">
                      <Badge variant="outline">{t.channel}</Badge>
                      <Button type="button" variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEditTemplate(t)} title="Edit"><Pencil className="h-4 w-4" /></Button>
                      <Button type="button" variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive" onClick={() => handleDeleteTemplate(t)} title="Delete"><Trash2 className="h-4 w-4" /></Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h4 className="font-medium mb-2">Scheduled / history</h4>
              <div className="space-y-2 max-h-40 overflow-y-auto">
                {scheduled.length === 0 ? <p className="text-sm text-muted-foreground">No scheduled notifications.</p> : scheduled.slice(0, 20).map((n) => (
                  <div key={n.id} className="flex justify-between items-center p-2 border rounded text-sm">
                    <span>{n.recipient_email} · {new Date(n.scheduled_at).toLocaleString()}</span>
                    <Badge variant={n.status === 'sent' ? 'default' : n.status === 'failed' ? 'destructive' : 'secondary'}>{n.status}</Badge>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
    <Dialog open={templateDialog.open} onOpenChange={(open) => !open && setTemplateDialog((d) => ({ ...d, open: false }))}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{templateDialog.editingId ? 'Edit template' : 'Create template'}</DialogTitle>
          <DialogDescription>Name and body support placeholders: {`{{ticket_id}}`}, {`{{ticket_title}}`}, {`{{customer_name}}`}, {`{{resolution}}`}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSaveTemplate} className="space-y-4">
          <div className="space-y-2">
            <Label>Name</Label>
            <Input value={templateDialog.name} onChange={(e) => setTemplateDialog((d) => ({ ...d, name: e.target.value }))} placeholder="e.g. Ticket follow-up" required />
          </div>
          <div className="space-y-2">
            <Label>Subject (email)</Label>
            <Input value={templateDialog.subject} onChange={(e) => setTemplateDialog((d) => ({ ...d, subject: e.target.value }))} placeholder="e.g. Update on ticket {{ticket_id}}" />
          </div>
          <div className="space-y-2">
            <Label>Body</Label>
            <Textarea value={templateDialog.body} onChange={(e) => setTemplateDialog((d) => ({ ...d, body: e.target.value }))} placeholder="Hi, your ticket {{ticket_id}}: {{ticket_title}}..." rows={4} className="resize-y" />
          </div>
          <div className="flex gap-4">
            <div className="space-y-2 flex-1">
              <Label>Type</Label>
              <Select value={templateDialog.notification_type} onValueChange={(v) => setTemplateDialog((d) => ({ ...d, notification_type: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="ticket_update">Ticket Update</SelectItem>
                  <SelectItem value="follow_up">Follow-up</SelectItem>
                  <SelectItem value="reminder">Reminder</SelectItem>
                  <SelectItem value="alert">Alert</SelectItem>
                  <SelectItem value="system">System</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2 flex-1">
              <Label>Channel</Label>
              <Select value={templateDialog.channel} onValueChange={(v) => setTemplateDialog((d) => ({ ...d, channel: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="email">Email</SelectItem>
                  <SelectItem value="sms">SMS</SelectItem>
                  <SelectItem value="in_app">In-App</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setTemplateDialog((d) => ({ ...d, open: false }))}>Cancel</Button>
            <Button type="submit" disabled={savingTemplate}>{savingTemplate ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Save</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  </>
  );
}

function FrontlineWorkflowsTab() {
  const { toast } = useToast();
  const [workflows, setWorkflows] = useState([]);
  const [executions, setExecutions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [executeForm, setExecuteForm] = useState({ workflow_id: '', ticket_id: '', recipient_email: '' });
  const [executing, setExecuting] = useState(false);
  const [workflowDialog, setWorkflowDialog] = useState({ open: false, editingId: null, name: '', description: '', stepsJson: WORKFLOW_STEPS_DEFAULT, is_active: true });
  const [savingWorkflow, setSavingWorkflow] = useState(false);
  const load = async () => {
    setLoading(true);
    try {
      const [wRes, eRes] = await Promise.all([frontlineAgentService.listWorkflows(), frontlineAgentService.listWorkflowExecutions()]);
      setWorkflows((wRes.status === 'success' && wRes.data) ? wRes.data : []);
      setExecutions((eRes.status === 'success' && eRes.data) ? eRes.data : []);
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to load', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);
  const handleExecute = async (e) => {
    e.preventDefault();
    if (!executeForm.workflow_id) {
      toast({ title: 'Error', description: 'Select a workflow', variant: 'destructive' });
      return;
    }
    setExecuting(true);
    try {
      const res = await frontlineAgentService.executeWorkflow(parseInt(executeForm.workflow_id, 10), {
        ticket_id: executeForm.ticket_id ? parseInt(executeForm.ticket_id, 10) : undefined,
        recipient_email: executeForm.recipient_email || undefined,
      });
      if (res.status === 'success') {
        toast({ title: 'Done', description: `Execution ${res.data?.status || 'completed'}.` });
        load();
      } else throw new Error(res.message);
    } catch (err) {
      toast({ title: 'Error', description: err.message || 'Execute failed', variant: 'destructive' });
    } finally {
      setExecuting(false);
    }
  };
  const openCreateWorkflow = () => setWorkflowDialog({ open: true, editingId: null, name: '', description: '', stepsJson: WORKFLOW_STEPS_DEFAULT, is_active: true });
  const openEditWorkflow = (w) => setWorkflowDialog({
    open: true, editingId: w.id, name: w.name || '', description: w.description || '',
    stepsJson: Array.isArray(w.steps) ? JSON.stringify(w.steps, null, 2) : (typeof w.steps === 'string' ? w.steps : WORKFLOW_STEPS_DEFAULT),
    is_active: w.is_active !== false,
  });
  const handleSaveWorkflow = async (e) => {
    e.preventDefault();
    if (!workflowDialog.name.trim()) {
      toast({ title: 'Error', description: 'Name is required', variant: 'destructive' });
      return;
    }
    let steps = [];
    try {
      steps = JSON.parse(workflowDialog.stepsJson || '[]');
      if (!Array.isArray(steps)) steps = [];
    } catch {
      toast({ title: 'Error', description: 'Steps must be valid JSON array', variant: 'destructive' });
      return;
    }
    setSavingWorkflow(true);
    try {
      if (workflowDialog.editingId) {
        const res = await frontlineAgentService.updateWorkflow(workflowDialog.editingId, {
          name: workflowDialog.name.trim(),
          description: workflowDialog.description,
          steps,
          is_active: workflowDialog.is_active,
        });
        if (res.status === 'success') {
          toast({ title: 'Saved', description: 'Workflow updated.' });
          setWorkflowDialog({ open: false, editingId: null, name: '', description: '', stepsJson: WORKFLOW_STEPS_DEFAULT, is_active: true });
          load();
        } else throw new Error(res.message);
      } else {
        const res = await frontlineAgentService.createWorkflow({
          name: workflowDialog.name.trim(),
          description: workflowDialog.description,
          steps,
          is_active: workflowDialog.is_active,
        });
        if (res.status === 'success') {
          toast({ title: 'Created', description: 'Workflow created.' });
          setWorkflowDialog({ open: false, editingId: null, name: '', description: '', stepsJson: WORKFLOW_STEPS_DEFAULT, is_active: true });
          load();
        } else throw new Error(res.message);
      }
    } catch (err) {
      toast({ title: 'Error', description: err.message || 'Failed to save workflow', variant: 'destructive' });
    } finally {
      setSavingWorkflow(false);
    }
  };
  const handleDeleteWorkflow = async (w) => {
    if (!confirm(`Delete workflow "${w.name}"?`)) return;
    try {
      const res = await frontlineAgentService.deleteWorkflow(w.id);
      if (res.status === 'success') {
        toast({ title: 'Deleted', description: 'Workflow removed.' });
        load();
      } else throw new Error(res.message);
    } catch (err) {
      toast({ title: 'Error', description: err.message || 'Delete failed', variant: 'destructive' });
    }
  };
  return (
  <>
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="flex items-center gap-2"><GitBranch className="h-5 w-5" /> Workflows</CardTitle>
          <CardDescription>Run SOP/workflows with context (e.g. ticket_id, recipient_email).</CardDescription>
        </div>
        <Button onClick={openCreateWorkflow}><Plus className="h-4 w-4 mr-2" /> Create workflow</Button>
      </CardHeader>
      <CardContent className="space-y-6">
        <form onSubmit={handleExecute} className="flex flex-wrap items-end gap-3 p-3 border rounded-lg">
          <div className="space-y-1">
            <Label>Workflow</Label>
            <Select value={executeForm.workflow_id} onValueChange={(v) => setExecuteForm((f) => ({ ...f, workflow_id: v }))}>
              <SelectTrigger className="w-[220px]"><SelectValue placeholder="Select workflow" /></SelectTrigger>
              <SelectContent>
                {workflows.filter((w) => w.is_active).map((w) => <SelectItem key={w.id} value={String(w.id)}>{w.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Ticket ID (optional)</Label>
            <Input placeholder="123" value={executeForm.ticket_id} onChange={(e) => setExecuteForm((f) => ({ ...f, ticket_id: e.target.value }))} className="w-[90px]" />
          </div>
          <div className="space-y-1">
            <Label>Recipient email (optional)</Label>
            <Input placeholder="email@example.com" value={executeForm.recipient_email} onChange={(e) => setExecuteForm((f) => ({ ...f, recipient_email: e.target.value }))} className="w-[180px]" />
          </div>
          <Button type="submit" disabled={executing}>Execute</Button>
        </form>
        {loading ? <div className="flex justify-center py-4"><Loader2 className="h-6 w-6 animate-spin" /></div> : (
          <>
            <div>
              <h4 className="font-medium mb-2">Workflows ({workflows.length})</h4>
              <div className="space-y-2 max-h-32 overflow-y-auto">
                {workflows.length === 0 ? <p className="text-sm text-muted-foreground">No workflows yet. Click &quot;Create workflow&quot; to add one.</p> : workflows.map((w) => (
                  <div key={w.id} className="flex justify-between items-center p-2 border rounded text-sm">
                    <span>{w.name}</span>
                    <div className="flex items-center gap-1">
                      <Badge variant={w.is_active ? 'default' : 'secondary'}>{w.is_active ? 'Active' : 'Inactive'}</Badge>
                      <Button type="button" variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEditWorkflow(w)} title="Edit"><Pencil className="h-4 w-4" /></Button>
                      <Button type="button" variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive" onClick={() => handleDeleteWorkflow(w)} title="Delete"><Trash2 className="h-4 w-4" /></Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h4 className="font-medium mb-2">Recent executions</h4>
              <div className="space-y-2 max-h-32 overflow-y-auto">
                {executions.length === 0 ? <p className="text-sm text-muted-foreground">No executions yet.</p> : executions.slice(0, 15).map((ex) => (
                  <div key={ex.id} className="flex justify-between items-center p-2 border rounded text-sm">
                    <span>{ex.workflow_name} · {new Date(ex.started_at).toLocaleString()}</span>
                    <Badge variant={ex.status === 'completed' ? 'default' : ex.status === 'failed' ? 'destructive' : 'secondary'}>{ex.status}</Badge>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
    <Dialog open={workflowDialog.open} onOpenChange={(open) => !open && setWorkflowDialog((d) => ({ ...d, open: false }))}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{workflowDialog.editingId ? 'Edit workflow' : 'Create workflow'}</DialogTitle>
          <DialogDescription>Steps run in order. Types: send_email (template_id, recipient_email), update_ticket (ticket_id, status). Use {`{{ticket_id}}`}, {`{{recipient_email}}`} in context.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSaveWorkflow} className="space-y-4">
          <div className="space-y-2">
            <Label>Name</Label>
            <Input value={workflowDialog.name} onChange={(e) => setWorkflowDialog((d) => ({ ...d, name: e.target.value }))} placeholder="e.g. Ticket follow-up flow" required />
          </div>
          <div className="space-y-2">
            <Label>Description (optional)</Label>
            <Input value={workflowDialog.description} onChange={(e) => setWorkflowDialog((d) => ({ ...d, description: e.target.value }))} placeholder="Short description" />
          </div>
          <div className="space-y-2">
            <Label>Steps (JSON array)</Label>
            <Textarea value={workflowDialog.stepsJson} onChange={(e) => setWorkflowDialog((d) => ({ ...d, stepsJson: e.target.value }))} rows={8} className="font-mono text-sm resize-y" placeholder={WORKFLOW_STEPS_DEFAULT} />
            <p className="text-xs text-muted-foreground">Example: send_email with template_id and recipient_email; update_ticket with status.</p>
          </div>
          <div className="flex items-center gap-2">
            <input type="checkbox" id="wf-active" checked={workflowDialog.is_active} onChange={(e) => setWorkflowDialog((d) => ({ ...d, is_active: e.target.checked }))} className="rounded border" />
            <Label htmlFor="wf-active">Active (can be executed)</Label>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setWorkflowDialog((d) => ({ ...d, open: false }))}>Cancel</Button>
            <Button type="submit" disabled={savingWorkflow}>{savingWorkflow ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Save</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  </>
  );
}

function FrontlineAnalyticsTab() {
  const { toast } = useToast();
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const load = async () => {
    setLoading(true);
    try {
      const res = await frontlineAgentService.getFrontlineAnalytics(dateFrom || undefined, dateTo || undefined);
      setData((res.status === 'success' && res.data) ? res.data : null);
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to load analytics', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, [dateFrom, dateTo]);
  const handleExport = async () => {
    setExporting(true);
    try {
      await frontlineAgentService.downloadFrontlineAnalyticsExport(dateFrom || undefined, dateTo || undefined);
      toast({ title: 'Export started', description: 'CSV download should start.' });
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Export failed', variant: 'destructive' });
    } finally {
      setExporting(false);
    }
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><BarChart3 className="h-5 w-5" /> Analytics</CardTitle>
        <CardDescription>Tickets trends and export. Set date range and load.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label>From</Label>
            <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-[160px]" />
          </div>
          <div className="space-y-1">
            <Label>To</Label>
            <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-[160px]" />
          </div>
          <Button variant="outline" onClick={load} disabled={loading}>Load</Button>
          <Button variant="outline" onClick={handleExport} disabled={exporting}>Export CSV</Button>
        </div>
        {loading ? <div className="flex justify-center py-4"><Loader2 className="h-6 w-6 animate-spin" /></div> : data && (
          <div className="space-y-4">
            {data.narrative && (
              <div className="p-3 rounded-lg bg-muted/50 border text-sm text-foreground">
                <p className="font-medium text-muted-foreground mb-1">Summary</p>
                <p className="whitespace-pre-wrap">{data.narrative}</p>
              </div>
            )}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="p-3 border rounded">
                <p className="text-sm text-muted-foreground">Total tickets</p>
                <p className="text-2xl font-semibold">{data.total_tickets}</p>
              </div>
              <div className="p-3 border rounded">
                <p className="text-sm text-muted-foreground">Auto-resolved</p>
                <p className="text-2xl font-semibold">{data.auto_resolved_count ?? 0}</p>
              </div>
              <div className="p-3 border rounded">
                <p className="text-sm text-muted-foreground">Avg resolution (hours)</p>
                <p className="text-2xl font-semibold">{data.avg_resolution_hours ?? '—'}</p>
              </div>
            </div>
            <div>
              <h4 className="font-medium mb-2">By status</h4>
              <div className="flex flex-wrap gap-2">
                {(data.tickets_by_status || []).map((s) => (
                  <Badge key={s.status} variant="outline">{s.status}: {s.count}</Badge>
                ))}
              </div>
            </div>
            <div>
              <h4 className="font-medium mb-2">By category</h4>
              <div className="flex flex-wrap gap-2">
                {(data.tickets_by_category || []).map((c) => (
                  <Badge key={c.category} variant="secondary">{c.category}: {c.count}</Badge>
                ))}
              </div>
            </div>
            {(data.tickets_by_date || []).length > 0 && (
              <div>
                <h4 className="font-medium mb-2">By date</h4>
                <div className="max-h-48 overflow-y-auto space-y-1 text-sm">
                  {data.tickets_by_date.map((d) => (
                    <div key={d.date} className="flex justify-between"><span>{d.date}</span><span>{d.count}</span></div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

const FrontlineDashboard = () => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [activeTab, setActiveTab] = useState('overview');
  const [isDarkMode, setIsDarkMode] = useState(false);
  
  // Document upload
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadTitle, setUploadTitle] = useState('');
  const [uploadDescription, setUploadDescription] = useState('');
  
  // Knowledge Q&A (chat-based)
  const [chats, setChats] = useState([]);
  const [selectedChatId, setSelectedChatId] = useState(null);
  const [question, setQuestion] = useState('');
  const [answering, setAnswering] = useState(false);
  const [loadingChats, setLoadingChats] = useState(false);
  const messagesEndRef = useRef(null);
  
  // Ticket creation
  const [showTicketDialog, setShowTicketDialog] = useState(false);
  const [ticketTitle, setTicketTitle] = useState('');
  const [ticketDescription, setTicketDescription] = useState('');
  const [creatingTicket, setCreatingTicket] = useState(false);

  // Document processing result (summarize / extract)
  const [docResultDialog, setDocResultDialog] = useState({ open: false, type: null, title: '', content: null, loading: false });

  // Tickets list (filter + pagination)
  const [ticketsList, setTicketsList] = useState([]);
  const [ticketsLoading, setTicketsLoading] = useState(false);
  const [ticketFilters, setTicketFilters] = useState({ status: '', priority: '', category: '', date_from: '', date_to: '' });
  const [ticketsPagination, setTicketsPagination] = useState({ page: 1, limit: 20, total: 0, total_pages: 1 });

  useEffect(() => {
    fetchDashboard();
    
    // Check for dark mode
    const checkDarkMode = () => {
      setIsDarkMode(
        document.documentElement.classList.contains('dark') ||
        window.matchMedia('(prefers-color-scheme: dark)').matches
      );
    };
    
    checkDarkMode();
    
    // Watch for dark mode changes
    const observer = new MutationObserver(checkDarkMode);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class']
    });
    
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    mediaQuery.addEventListener('change', checkDarkMode);
    
    return () => {
      observer.disconnect();
      mediaQuery.removeEventListener('change', checkDarkMode);
    };
  }, []);

  const fetchDashboard = async () => {
    try {
      setLoading(true);
      const response = await frontlineAgentService.getFrontlineDashboard();
      if (response.status === 'success') {
        setStats(response.data.stats);
        setDocuments(response.data.recent_documents || []);
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to load dashboard',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async () => {
    if (!uploadFile) {
      toast({
        title: 'Error',
        description: 'Please select a file to upload',
        variant: 'destructive',
      });
      return;
    }

    try {
      setUploading(true);
      const response = await frontlineAgentService.uploadDocument(
        uploadFile,
        uploadTitle || uploadFile.name,
        uploadDescription,
        'knowledge_base'
      );

      if (response.status === 'success') {
        toast({
          title: 'Success!',
          description: 'Document uploaded and processed successfully',
        });
        setShowUploadDialog(false);
        setUploadFile(null);
        setUploadTitle('');
        setUploadDescription('');
        fetchDashboard();
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to upload document',
        variant: 'destructive',
      });
    } finally {
      setUploading(false);
    }
  };

  const handleDeleteDocument = async (documentId) => {
    if (!confirm('Are you sure you want to delete this document?')) {
      return;
    }

    try {
      const response = await frontlineAgentService.deleteDocument(documentId);
      if (response.status === 'success') {
        toast({
          title: 'Success!',
          description: 'Document deleted successfully',
        });
        fetchDashboard();
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to delete document',
        variant: 'destructive',
      });
    }
  };

  const handleSummarizeDocument = async (doc) => {
    setDocResultDialog({ open: true, type: 'summary', title: `Summary: ${doc.title}`, content: null, loading: true });
    try {
      const response = await frontlineAgentService.summarizeDocument(doc.id, {});
      const summary = response?.data?.summary ?? response?.summary;
      setDocResultDialog((prev) => ({ ...prev, content: summary || 'No summary generated.', loading: false }));
    } catch (error) {
      setDocResultDialog((prev) => ({ ...prev, content: `Error: ${error.message || 'Summarization failed'}`, loading: false }));
    }
  };

  const handleExtractDocument = async (doc) => {
    setDocResultDialog({ open: true, type: 'extract', title: `Extracted data: ${doc.title}`, content: null, loading: true });
    try {
      const response = await frontlineAgentService.extractDocument(doc.id, {});
      const extracted = response?.data?.extracted ?? response?.extracted;
      const content = typeof extracted === 'object' ? JSON.stringify(extracted, null, 2) : (extracted || 'No data extracted.');
      setDocResultDialog((prev) => ({ ...prev, content, loading: false }));
    } catch (error) {
      setDocResultDialog((prev) => ({ ...prev, content: `Error: ${error.message || 'Extraction failed'}`, loading: false }));
    }
  };

  /** Normalize chat from API shape to component shape */
  const normalizeChat = (chat) => {
    if (!chat) return chat;
    return {
      ...chat,
      id: String(chat.id),
      title: chat.title || 'Chat',
      messages: chat.messages || [],
      updatedAt: chat.updatedAt || chat.timestamp,
      timestamp: chat.updatedAt || chat.timestamp,
    };
  };

  const loadChatsFromApi = async () => {
    try {
      setLoadingChats(true);
      const res = await frontlineAgentService.listQAChats();
      if (res.status === 'success' && res.data) {
        setChats((res.data || []).map(normalizeChat));
      } else {
        setChats([]);
      }
    } catch (err) {
      console.error('Load QA chats error:', err);
      setChats([]);
    } finally {
      setLoadingChats(false);
    }
  };

  const loadTickets = async () => {
    try {
      setTicketsLoading(true);
      const params = { page: ticketsPagination.page, limit: ticketsPagination.limit };
      if (ticketFilters.status) params.status = ticketFilters.status;
      if (ticketFilters.priority) params.priority = ticketFilters.priority;
      if (ticketFilters.category) params.category = ticketFilters.category;
      if (ticketFilters.date_from) params.date_from = ticketFilters.date_from;
      if (ticketFilters.date_to) params.date_to = ticketFilters.date_to;
      const res = await frontlineAgentService.listTickets(params);
      if (res.status === 'success') {
        setTicketsList(res.data || []);
        if (res.pagination) setTicketsPagination(res.pagination);
      } else {
        setTicketsList([]);
      }
    } catch (err) {
      console.error('Load tickets error:', err);
      setTicketsList([]);
      toast({ title: 'Error', description: err.message || 'Failed to load tickets', variant: 'destructive' });
    } finally {
      setTicketsLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'qa') {
      loadChatsFromApi();
    }
  }, [activeTab]);

  useEffect(() => {
    if (activeTab === 'tickets') {
      loadTickets();
    }
  }, [activeTab, ticketFilters.status, ticketFilters.priority, ticketFilters.category, ticketFilters.date_from, ticketFilters.date_to, ticketsPagination.page]);

  const selectedChat = chats.find((c) => c.id === selectedChatId);
  const currentMessages = selectedChat?.messages ?? [];
  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  const newChat = () => {
    setSelectedChatId(null);
    setQuestion('');
  };

  const deleteChat = async (e, chatId) => {
    e.stopPropagation();
    try {
      const res = await frontlineAgentService.deleteQAChat(chatId);
      if (res.status === 'success') {
        setChats((prev) => prev.filter((c) => c.id !== chatId));
        if (selectedChatId === chatId) setSelectedChatId(null);
        toast({ title: 'Chat deleted' });
      } else {
        throw new Error(res.message || 'Failed to delete chat');
      }
    } catch (err) {
      toast({ title: 'Error', description: err.message || 'Could not delete chat', variant: 'destructive' });
    }
  };

  const handleAskQuestion = async (e) => {
    e?.preventDefault?.();
    if (!question.trim()) {
      toast({ title: 'Error', description: 'Please enter a question', variant: 'destructive' });
      return;
    }
    const q = question.trim();
    try {
      setAnswering(true);
      const response = await frontlineAgentService.knowledgeQA(q);
      if (response.status === 'success' && response.data) {
        const data = response.data;
        const answerText = data.answer || 'No answer available.';
        const userMsg = { role: 'user', content: q };
        const assistantMsg = {
          role: 'assistant',
          content: answerText,
          responseData: {
            answer: answerText,
            has_verified_info: data.has_verified_info || false,
            source: data.source || 'Knowledge Base',
            type: data.type || 'general',
          },
        };
        const title = q.slice(0, 40);
        if (selectedChatId) {
          const existing = chats.find((c) => c.id === selectedChatId);
          if (existing) {
            const updRes = await frontlineAgentService.updateQAChat(selectedChatId, {
              messages: [userMsg, assistantMsg],
              title: existing.title || title,
            });
            if (updRes.status === 'success' && updRes.data) {
              const updatedChat = normalizeChat(updRes.data);
              setChats((prev) => [updatedChat, ...prev.filter((c) => c.id !== selectedChatId)]);
            } else throw new Error(updRes.message || 'Failed to save chat');
          } else {
            const createRes = await frontlineAgentService.createQAChat({ title, messages: [userMsg, assistantMsg] });
            if (createRes.status === 'success' && createRes.data) {
              const newChatData = normalizeChat(createRes.data);
              setChats((prev) => [newChatData, ...prev]);
              setSelectedChatId(newChatData.id);
            } else throw new Error(createRes.message || 'Failed to create chat');
          }
        } else {
          const createRes = await frontlineAgentService.createQAChat({ title, messages: [userMsg, assistantMsg] });
          if (createRes.status === 'success' && createRes.data) {
            const newChatData = normalizeChat(createRes.data);
            setChats((prev) => [newChatData, ...prev]);
            setSelectedChatId(newChatData.id);
          } else throw new Error(createRes.message || 'Failed to create chat');
        }
        setQuestion('');
        setTimeout(scrollToBottom, 100);
      } else {
        throw new Error(response.message || 'Failed to get response');
      }
    } catch (error) {
      toast({ title: 'Error', description: error.message || 'Failed to get answer', variant: 'destructive' });
    } finally {
      setAnswering(false);
    }
  };

  const truncate = (s, n = 50) => (s.length <= n ? s : s.slice(0, n) + '…');
  const formatDate = (iso) => {
    try {
      const d = new Date(iso);
      return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  const handleCreateTicket = async () => {
    if (!ticketDescription.trim()) {
      toast({
        title: 'Error',
        description: 'Please enter a description',
        variant: 'destructive',
      });
      return;
    }

    try {
      setCreatingTicket(true);
      const response = await frontlineAgentService.createTicket(
        ticketTitle || 'Support Request',
        ticketDescription
      );

      if (response.status === 'success' && response.data) {
        toast({
          title: response.data.auto_resolved ? 'Ticket Auto-Resolved!' : 'Ticket Created!',
          description: response.data.response || 'Your ticket has been processed',
        });
        setShowTicketDialog(false);
        setTicketTitle('');
        setTicketDescription('');
        fetchDashboard();
        if (activeTab === 'tickets') loadTickets();
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to create ticket',
        variant: 'destructive',
      });
    } finally {
      setCreatingTicket(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Stats Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Documents</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.total_documents || 0}</div>
            <p className="text-xs text-muted-foreground">
              {stats?.indexed_documents || 0} indexed
            </p>
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Tickets</CardTitle>
            <Ticket className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.total_tickets || 0}</div>
            <p className="text-xs text-muted-foreground">
              {stats?.open_tickets || 0} open, {stats?.resolved_tickets || 0} resolved
            </p>
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Auto-Resolved</CardTitle>
            <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.auto_resolved_tickets || 0}</div>
            <p className="text-xs text-muted-foreground">
              Automatically resolved tickets
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Main Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="documents">Documents</TabsTrigger>
          <TabsTrigger value="qa">Knowledge Q&A</TabsTrigger>
          <TabsTrigger value="tickets">Tickets</TabsTrigger>
          <TabsTrigger value="notifications">Notifications</TabsTrigger>
          <TabsTrigger value="workflows">Workflows</TabsTrigger>
          <TabsTrigger value="analytics">Analytics</TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Welcome to Frontline Agent</CardTitle>
              <CardDescription>
                AI-powered customer support system for handling tickets and answering questions
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Button onClick={() => setShowUploadDialog(true)} className="w-full">
                  <Upload className="mr-2 h-4 w-4" />
                  Upload Document
                </Button>
                <Button onClick={() => setActiveTab('qa')} variant="outline" className="w-full">
                  <MessageSquare className="mr-2 h-4 w-4" />
                  Ask a Question
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Recent Documents */}
          {documents.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Recent Documents</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {documents.slice(0, 5).map((doc) => (
                    <div key={doc.id} className="flex items-center justify-between p-2 border rounded">
                      <div className="flex items-center space-x-2">
                        <FileText className="h-4 w-4" />
                        <span className="text-sm">{doc.title}</span>
                        {doc.is_indexed && (
                          <span className="text-xs text-green-600">Indexed</span>
                        )}
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDeleteDocument(doc.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Documents Tab */}
        <TabsContent value="documents" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Documents</CardTitle>
                <CardDescription>Upload and manage knowledge base documents</CardDescription>
              </div>
              <Button onClick={() => setShowUploadDialog(true)}>
                <Upload className="mr-2 h-4 w-4" />
                Upload Document
              </Button>
            </CardHeader>
            <CardContent>
              {documents.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  No documents uploaded yet. Upload your first document to get started.
                </div>
              ) : (
                <div className="space-y-2">
                  {documents.map((doc) => (
                    <div key={doc.id} className="flex items-center justify-between p-3 border rounded">
                      <div className="flex items-center space-x-3">
                        <FileText className="h-5 w-5" />
                        <div>
                          <div className="font-medium">{doc.title}</div>
                          <div className="text-sm text-muted-foreground">
                            {doc.file_format.toUpperCase()} • {doc.document_type}
                            {doc.is_indexed && ' • Indexed'}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-1">
                        <Button variant="ghost" size="sm" onClick={() => handleSummarizeDocument(doc)} title="Summarize">
                          <FileSearch className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => handleExtractDocument(doc)} title="Extract data">
                          <ListChecks className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => handleDeleteDocument(doc.id)} title="Delete">
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Knowledge Q&A Tab - Chat UI with sidebar (like Recruitment AI questions) */}
        <TabsContent value="qa" className="space-y-4">
          <div className="flex gap-4 w-full max-w-full">
            {/* Sidebar - Previous chats */}
            <div className="w-64 shrink-0 rounded-lg border bg-card">
              <div className="p-3 border-b flex items-center justify-between shrink-0">
                <span className="text-sm font-semibold">Previous conversations</span>
                <Button variant="ghost" size="icon" onClick={newChat} title="New chat">
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
              <div className="overflow-y-auto overflow-x-hidden max-h-[min(60vh,420px)]">
                {loadingChats ? (
                  <div className="p-4 flex justify-center">
                    <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                  </div>
                ) : chats.length === 0 ? (
                  <div className="p-4 text-center text-sm text-muted-foreground">No conversations yet. Ask a question to start.</div>
                ) : (
                  <div className="p-2 space-y-1">
                    {chats.map((c) => (
                      <div
                        key={c.id}
                        className={`flex items-center gap-1 rounded-lg text-sm transition-colors ${
                          selectedChatId === c.id ? 'bg-primary/10 border border-primary/20' : 'hover:bg-muted'
                        }`}
                      >
                        <button
                          type="button"
                          onClick={() => setSelectedChatId(c.id)}
                          className="flex-1 min-w-0 text-left p-3 rounded-lg"
                        >
                          <div className="font-medium truncate">{truncate(c.title || (c.messages?.[0]?.content) || 'Chat', 40)}</div>
                          <div className="text-xs text-muted-foreground mt-0.5">{formatDate(c.updatedAt || c.timestamp)}</div>
                        </button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 shrink-0 opacity-60 hover:opacity-100 hover:bg-destructive/10 hover:text-destructive"
                          onClick={(e) => deleteChat(e, c.id)}
                          title="Delete chat"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Main chat area */}
            <Card className="flex-1 min-w-0">
              <CardHeader className="shrink-0">
                <CardTitle className="flex items-center gap-2">
                  <MessageSquare className="h-5 w-5" />
                  Knowledge Q&A
                </CardTitle>
                <CardDescription>
                  Ask questions and get answers from your knowledge base and uploaded documents. Previous conversations are shown in the sidebar.
                </CardDescription>
              </CardHeader>
              <CardContent className="p-0 flex flex-col min-h-0">
                <div className="px-4 pb-4 space-y-4 overflow-y-auto overflow-x-hidden max-h-[min(55vh,480px)] min-h-0">
                  {!selectedChatId && chats.length === 0 && (
                    <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                      <MessageCircle className="h-12 w-12 mb-4 opacity-50" />
                      <p className="font-medium">Ask your first question</p>
                      <p className="text-sm">Type a question to get an answer from your knowledge base.</p>
                      {documents.length === 0 && (
                        <p className="text-xs mt-2 text-yellow-600 dark:text-yellow-400">💡 Tip: Upload documents in the Documents tab first</p>
                      )}
                    </div>
                  )}
                  {!selectedChatId && chats.length > 0 && (
                    <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                      <MessageCircle className="h-12 w-12 mb-4 opacity-50" />
                      <p className="font-medium">Select a conversation or ask a new question</p>
                      <p className="text-sm">Click a previous chat in the sidebar to view it.</p>
                    </div>
                  )}
                  {currentMessages.map((msg, i) => (
                    <div
                      key={i}
                      className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                    >
                      <div
                        className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                          msg.role === 'user'
                            ? 'bg-primary text-primary-foreground'
                            : 'bg-muted border'
                        }`}
                      >
                        {msg.role === 'user' ? (
                          <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                        ) : (
                          <>
                            <div className="flex items-start gap-2">
                              {(msg.responseData?.has_verified_info) ? (
                                <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400 mt-0.5 flex-shrink-0" />
                              ) : (
                                <XCircle className="h-4 w-4 text-yellow-600 dark:text-yellow-400 mt-0.5 flex-shrink-0" />
                              )}
                              <div className="flex-1 min-w-0">
                                <div className="text-sm text-foreground whitespace-pre-wrap break-words">
                                  {msg.responseData?.answer ?? msg.content}
                                </div>
                                {(msg.responseData?.source || msg.responseData?.citations?.length) ? (
                                  <div className="text-xs text-muted-foreground mt-2 space-y-1">
                                    {msg.responseData?.source && (
                                      <p>Source: {msg.responseData.source}</p>
                                    )}
                                    {msg.responseData?.citations?.length > 1 && (
                                      <p>References: {msg.responseData.citations.map((c, i) => c.document_title || c.source).filter(Boolean).join('; ')}</p>
                                    )}
                                  </div>
                                ) : null}
                              </div>
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                  {answering && (
                    <div className="flex justify-start">
                      <div className="bg-muted border rounded-2xl px-4 py-3 flex items-center gap-2">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        <span className="text-sm">Searching knowledge base...</span>
                      </div>
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                </div>

                <form onSubmit={handleAskQuestion} className="shrink-0 border-t p-4 space-y-3 bg-muted/30">
                  <div className="flex gap-2">
                    <Textarea
                      placeholder="Ask a question from your knowledge base..."
                      value={question}
                      onChange={(e) => setQuestion(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleAskQuestion(e); } }}
                      rows={2}
                      disabled={answering}
                      className="min-h-[60px] resize-none"
                    />
                    <Button type="submit" disabled={answering} size="icon" className="h-[60px] w-12 shrink-0">
                      {answering ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Tickets Tab */}
        <TabsContent value="tickets" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Support Tickets</CardTitle>
                <CardDescription>Create and filter your support tickets</CardDescription>
              </div>
              <Button onClick={() => setShowTicketDialog(true)}>
                <Ticket className="mr-2 h-4 w-4" />
                Create Ticket
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <Select value={ticketFilters.status || 'all'} onValueChange={(v) => { setTicketFilters((f) => ({ ...f, status: v === 'all' ? '' : v })); setTicketsPagination((p) => ({ ...p, page: 1 })); }}>
                  <SelectTrigger className="w-[140px]">
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All statuses</SelectItem>
                    <SelectItem value="new">New</SelectItem>
                    <SelectItem value="open">Open</SelectItem>
                    <SelectItem value="in_progress">In Progress</SelectItem>
                    <SelectItem value="resolved">Resolved</SelectItem>
                    <SelectItem value="closed">Closed</SelectItem>
                    <SelectItem value="auto_resolved">Auto Resolved</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={ticketFilters.priority || 'all'} onValueChange={(v) => { setTicketFilters((f) => ({ ...f, priority: v === 'all' ? '' : v })); setTicketsPagination((p) => ({ ...p, page: 1 })); }}>
                  <SelectTrigger className="w-[120px]">
                    <SelectValue placeholder="Priority" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All priorities</SelectItem>
                    <SelectItem value="low">Low</SelectItem>
                    <SelectItem value="medium">Medium</SelectItem>
                    <SelectItem value="high">High</SelectItem>
                    <SelectItem value="urgent">Urgent</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={ticketFilters.category || 'all'} onValueChange={(v) => { setTicketFilters((f) => ({ ...f, category: v === 'all' ? '' : v })); setTicketsPagination((p) => ({ ...p, page: 1 })); }}>
                  <SelectTrigger className="w-[160px]">
                    <SelectValue placeholder="Category" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All categories</SelectItem>
                    <SelectItem value="technical">Technical</SelectItem>
                    <SelectItem value="billing">Billing</SelectItem>
                    <SelectItem value="account">Account</SelectItem>
                    <SelectItem value="feature_request">Feature Request</SelectItem>
                    <SelectItem value="bug">Bug</SelectItem>
                    <SelectItem value="knowledge_gap">Knowledge gap</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
                <Input
                  type="date"
                  placeholder="From"
                  className="w-[140px]"
                  value={ticketFilters.date_from}
                  onChange={(e) => { setTicketFilters((f) => ({ ...f, date_from: e.target.value })); setTicketsPagination((p) => ({ ...p, page: 1 })); }}
                />
                <Input
                  type="date"
                  placeholder="To"
                  className="w-[140px]"
                  value={ticketFilters.date_to}
                  onChange={(e) => { setTicketFilters((f) => ({ ...f, date_to: e.target.value })); setTicketsPagination((p) => ({ ...p, page: 1 })); }}
                />
                <Button variant="outline" size="sm" onClick={() => setTicketFilters({ status: '', priority: '', category: '', date_from: '', date_to: '' })}>Clear filters</Button>
              </div>
              {ticketsLoading ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : ticketsList.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  No tickets found. Create a ticket to get started.
                </div>
              ) : (
                <>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Title</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Priority</TableHead>
                        <TableHead>Category</TableHead>
                        <TableHead>Auto-resolved</TableHead>
                        <TableHead>Created</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {ticketsList.map((t) => (
                        <TableRow key={t.id}>
                          <TableCell>
                            <div>
                              <div className="font-medium">{t.title}</div>
                              {t.description && <div className="text-xs text-muted-foreground line-clamp-1">{t.description}</div>}
                            </div>
                          </TableCell>
                          <TableCell><Badge variant="outline">{t.status}</Badge></TableCell>
                          <TableCell><Badge variant="secondary">{t.priority}</Badge></TableCell>
                          <TableCell className="capitalize">{t.category?.replace('_', ' ')}</TableCell>
                          <TableCell>{t.auto_resolved ? <CheckCircle2 className="h-4 w-4 text-green-600" /> : '—'}</TableCell>
                          <TableCell className="text-sm text-muted-foreground">{t.created_at ? new Date(t.created_at).toLocaleDateString() : '—'}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  {ticketsPagination.total_pages > 1 && (
                    <div className="flex items-center justify-between pt-2">
                      <p className="text-sm text-muted-foreground">
                        Page {ticketsPagination.page} of {ticketsPagination.total_pages} ({ticketsPagination.total} tickets)
                      </p>
                      <div className="flex gap-2">
                        <Button variant="outline" size="sm" disabled={ticketsPagination.page <= 1} onClick={() => setTicketsPagination((p) => ({ ...p, page: p.page - 1 }))}>
                          <ChevronLeft className="h-4 w-4" />
                        </Button>
                        <Button variant="outline" size="sm" disabled={ticketsPagination.page >= ticketsPagination.total_pages} onClick={() => setTicketsPagination((p) => ({ ...p, page: p.page + 1 }))}>
                          <ChevronRight className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Notifications Tab */}
        <TabsContent value="notifications" className="space-y-4">
          <FrontlineNotificationsTab />
        </TabsContent>

        {/* Workflows Tab */}
        <TabsContent value="workflows" className="space-y-4">
          <FrontlineWorkflowsTab />
        </TabsContent>

        {/* Analytics Tab */}
        <TabsContent value="analytics" className="space-y-4">
          <FrontlineAnalyticsTab />
        </TabsContent>
      </Tabs>

      {/* Document result (summary / extract) dialog */}
      <Dialog open={docResultDialog.open} onOpenChange={(open) => setDocResultDialog((prev) => ({ ...prev, open }))}>
        <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>{docResultDialog.title}</DialogTitle>
            <DialogDescription>
              {docResultDialog.type === 'summary' ? 'AI-generated summary of the document.' : 'Structured data extracted from the document.'}
            </DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-auto rounded border bg-muted/30 p-3">
            {docResultDialog.loading ? (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Processing...</span>
              </div>
            ) : (
              <pre className="text-sm whitespace-pre-wrap break-words font-sans">{docResultDialog.content}</pre>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDocResultDialog((prev) => ({ ...prev, open: false }))}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Upload Document Dialog */}
      <Dialog open={showUploadDialog} onOpenChange={setShowUploadDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Upload Document</DialogTitle>
            <DialogDescription>
              Upload a document to add it to your knowledge base. Supported formats: PDF, DOCX, TXT, MD, HTML
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="file">File</Label>
              <Input
                id="file"
                type="file"
                accept=".pdf,.docx,.doc,.txt,.md,.html"
                onChange={(e) => setUploadFile(e.target.files[0])}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="title">Title (optional)</Label>
              <Input
                id="title"
                placeholder="Document title"
                value={uploadTitle}
                onChange={(e) => setUploadTitle(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">Description (optional)</Label>
              <Textarea
                id="description"
                placeholder="Document description"
                value={uploadDescription}
                onChange={(e) => setUploadDescription(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowUploadDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleFileUpload} disabled={uploading || !uploadFile}>
              {uploading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Uploading...
                </>
              ) : (
                <>
                  <Upload className="mr-2 h-4 w-4" />
                  Upload
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create Ticket Dialog */}
      <Dialog open={showTicketDialog} onOpenChange={setShowTicketDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Support Ticket</DialogTitle>
            <DialogDescription>
              Describe your issue and we'll help you resolve it
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="ticket-title">Title (optional)</Label>
              <Input
                id="ticket-title"
                placeholder="Brief title for your issue"
                value={ticketTitle}
                onChange={(e) => setTicketTitle(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ticket-description">Description</Label>
              <Textarea
                id="ticket-description"
                placeholder="Describe your issue in detail..."
                value={ticketDescription}
                onChange={(e) => setTicketDescription(e.target.value)}
                rows={5}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowTicketDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateTicket} disabled={creatingTicket || !ticketDescription.trim()}>
              {creatingTicket ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <Send className="mr-2 h-4 w-4" />
                  Create Ticket
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default FrontlineDashboard;

