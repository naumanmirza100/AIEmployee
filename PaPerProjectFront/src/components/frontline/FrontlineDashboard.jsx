import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import ErrorBoundary from '@/components/common/ErrorBoundary';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
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
import { Checkbox } from '@/components/ui/checkbox';
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
  ChevronUp,
  ChevronDown,
  Bell,
  GitBranch,
  BarChart3,
  Mail,
  FileSearch,
  ListChecks,
  Pencil,
  MoreHorizontal,
  StickyNote,
  PauseCircle,
  PlayCircle,
  Moon,
  Sun,
  RefreshCw,
  Menu,
  Check,
  LayoutDashboard,
  Monitor,
  Copy,
  Sparkles,
  ThumbsUp,
  ThumbsDown,
  Bot,
  Maximize2,
  User,
} from 'lucide-react';
import FrontlineAIGraphs from './FrontlineAIGraphs';
import frontlineAgentService from '@/services/frontlineAgentService';
import { renderChart } from '../recruitment/ChartRenderer';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

const TEMPLATE_DEFAULT = { name: '', subject: '', body: '', notification_type: 'ticket_update', channel: 'email', use_llm_personalization: false };
// Document types for Q&A scope (must match backend Document.DOCUMENT_TYPE_CHOICES)
const DOCUMENT_TYPE_OPTIONS = [
  { value: 'knowledge_base', label: 'Knowledge Base' },
  { value: 'policy', label: 'Policy' },
  { value: 'procedure', label: 'Procedure' },
  { value: 'report', label: 'Report' },
  { value: 'ticket_attachment', label: 'Ticket Attachment' },
  { value: 'other', label: 'Other' },
];
const WORKFLOW_STEPS_DEFAULT = '[{"type": "send_email", "template_id": 1, "recipient_email": "{{recipient_email}}"}]';
const WORKFLOW_STEPS_COMPLEX_EXAMPLE = `[
  { "type": "send_email", "template_id": 1, "recipient_email": "{{recipient_email}}", "context": { "note": "Acknowledgement" } },
  { "type": "update_ticket", "status": "open" },
  { "type": "send_email", "template_id": 1, "recipient_email": "{{recipient_email}}", "context": { "note": "Confirmation" } },
  { "type": "update_ticket", "status": "in_progress" },
  { "type": "send_email", "template_id": 2, "recipient_email": "{{recipient_email}}" },
  { "type": "update_ticket", "resolution": "Workflow: customer notified. Ticket is being processed." },
  { "type": "send_email", "template_id": 2, "recipient_email": "{{recipient_email}}" },
  { "type": "update_ticket", "resolution": "Update: in progress. Customer notified. Reference ticket ID from context." },
  { "type": "send_email", "template_id": 2, "recipient_email": "{{recipient_email}}" },
  { "type": "update_ticket", "status": "resolved", "resolution": "Resolved via workflow. Customer received all notifications." },
  { "type": "send_email", "template_id": 3, "recipient_email": "{{recipient_email}}" },
  { "type": "update_ticket", "status": "closed" }
]`;

const PREFERENCES_DEFAULT = {
  email_enabled: true,
  in_app_enabled: true,
  ticket_created_email: true,
  ticket_updated_email: true,
  ticket_assigned_email: true,
  workflow_email_enabled: true,
};

function FrontlineNotificationsTab() {
  const { toast } = useToast();
  const [templates, setTemplates] = useState([]);
  const [scheduled, setScheduled] = useState([]);
  const [notificationTicketsList, setNotificationTicketsList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [preferences, setPreferences] = useState(PREFERENCES_DEFAULT);
  const [preferencesLoading, setPreferencesLoading] = useState(true);
  const [preferencesSaving, setPreferencesSaving] = useState(false);
  const [sendForm, setSendForm] = useState({ template_id: '', recipient_email: '', ticket_id: '' });
  const [sending, setSending] = useState(false);
  const [templateDialog, setTemplateDialog] = useState({ open: false, editingId: null, ...TEMPLATE_DEFAULT });
  const [savingTemplate, setSavingTemplate] = useState(false);
  const load = async () => {
    setLoading(true);
    try {
      const [tRes, sRes, tickRes, prefsRes] = await Promise.all([
        frontlineAgentService.listNotificationTemplates(),
        frontlineAgentService.listScheduledNotifications(),
        frontlineAgentService.listTickets({ limit: 100 }),
        frontlineAgentService.getNotificationPreferences?.().catch(() => ({ status: 'success', data: PREFERENCES_DEFAULT })),
      ]);
      setTemplates((tRes.status === 'success' && tRes.data) ? tRes.data : []);
      setScheduled((sRes.status === 'success' && sRes.data) ? sRes.data : []);
      setNotificationTicketsList((tickRes.status === 'success' && tickRes.data) ? tickRes.data : []);
      if (prefsRes?.status === 'success' && prefsRes.data) setPreferences(prefsRes.data);
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to load', variant: 'destructive' });
    } finally {
      setLoading(false);
      setPreferencesLoading(false);
    }
  };
  useEffect(() => { load(); }, []);
  const updatePreference = async (key, value) => {
    const next = { ...preferences, [key]: value };
    setPreferences(next);
    setPreferencesSaving(true);
    try {
      const res = await frontlineAgentService.updateNotificationPreferences({ [key]: value });
      if (res.status === 'success' && res.data) setPreferences(res.data);
      else toast({ title: 'Error', description: res.message || 'Failed to save preference', variant: 'destructive' });
    } catch (e) {
      setPreferences(preferences);
      toast({ title: 'Error', description: e.message || 'Failed to save', variant: 'destructive' });
    } finally {
      setPreferencesSaving(false);
    }
  };
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
      } else if (res.status === 'skipped') {
        toast({ title: 'Not sent', description: res.message || 'Recipient has disabled notification emails.', variant: 'secondary' });
      } else throw new Error(res.message);
    } catch (err) {
      toast({ title: 'Error', description: err.message || 'Send failed', variant: 'destructive' });
    } finally {
      setSending(false);
    }
  };
  const openCreateTemplate = () => setTemplateDialog({ open: true, editingId: null, ...TEMPLATE_DEFAULT });
  const openEditTemplate = (t) => setTemplateDialog({ open: true, editingId: t.id, name: t.name || '', subject: t.subject || '', body: t.body || '', notification_type: t.notification_type || 'ticket_update', channel: t.channel || 'email', use_llm_personalization: !!t.use_llm_personalization });
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
          use_llm_personalization: !!templateDialog.use_llm_personalization,
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
          use_llm_personalization: !!templateDialog.use_llm_personalization,
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
    <Card className="mb-4">
      <CardHeader>
        <CardTitle className="text-base">Notification preferences</CardTitle>
        <CardDescription>Control how and when you receive notifications. Turning these off reduces spam and respects your choice.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {preferencesLoading ? (
          <div className="flex items-center gap-2 text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading preferences...</div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-3">
              <p className="text-sm font-medium text-muted-foreground">Master toggles</p>
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="pref-email"
                  checked={!!preferences.email_enabled}
                  onCheckedChange={(checked) => updatePreference('email_enabled', !!checked)}
                  disabled={preferencesSaving}
                />
                <Label htmlFor="pref-email" className="text-sm font-normal cursor-pointer">Receive notification emails</Label>
              </div>
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="pref-inapp"
                  checked={!!preferences.in_app_enabled}
                  onCheckedChange={(checked) => updatePreference('in_app_enabled', !!checked)}
                  disabled={preferencesSaving}
                />
                <Label htmlFor="pref-inapp" className="text-sm font-normal cursor-pointer">Show in-app notifications</Label>
              </div>
            </div>
            <div className="space-y-3">
              <p className="text-sm font-medium text-muted-foreground">Email by event (when emails are on)</p>
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="pref-ticket-created"
                  checked={!!preferences.ticket_created_email}
                  onCheckedChange={(checked) => updatePreference('ticket_created_email', !!checked)}
                  disabled={preferencesSaving}
                />
                <Label htmlFor="pref-ticket-created" className="text-sm font-normal cursor-pointer">Ticket created</Label>
              </div>
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="pref-ticket-updated"
                  checked={!!preferences.ticket_updated_email}
                  onCheckedChange={(checked) => updatePreference('ticket_updated_email', !!checked)}
                  disabled={preferencesSaving}
                />
                <Label htmlFor="pref-ticket-updated" className="text-sm font-normal cursor-pointer">Ticket updated</Label>
              </div>
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="pref-ticket-assigned"
                  checked={!!preferences.ticket_assigned_email}
                  onCheckedChange={(checked) => updatePreference('ticket_assigned_email', !!checked)}
                  disabled={preferencesSaving}
                />
                <Label htmlFor="pref-ticket-assigned" className="text-sm font-normal cursor-pointer">Ticket assigned to me</Label>
              </div>
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="pref-workflow-email"
                  checked={!!preferences.workflow_email_enabled}
                  onCheckedChange={(checked) => updatePreference('workflow_email_enabled', !!checked)}
                  disabled={preferencesSaving}
                />
                <Label htmlFor="pref-workflow-email" className="text-sm font-normal cursor-pointer">Workflow & template trigger emails</Label>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
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
            <Label>Ticket (optional)</Label>
            <Select value={sendForm.ticket_id || '_none'} onValueChange={(v) => setSendForm((f) => ({ ...f, ticket_id: v === '_none' ? '' : v }))}>
              <SelectTrigger className="w-[260px] max-w-full"><SelectValue placeholder="Select ticket" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="_none">No ticket</SelectItem>
                {notificationTicketsList.map((t) => (
                  <SelectItem key={t.id} value={String(t.id)}>#{t.id}: {(t.title || '').slice(0, 35)}{(t.title || '').length > 35 ? '…' : ''}</SelectItem>
                ))}
              </SelectContent>
            </Select>
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
                      {t.use_llm_personalization && <Badge variant="secondary" className="text-xs">LLM</Badge>}
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
          <div className="flex items-center space-x-2">
            <Checkbox
              id="use_llm_personalization"
              checked={!!templateDialog.use_llm_personalization}
              onCheckedChange={(checked) => setTemplateDialog((d) => ({ ...d, use_llm_personalization: !!checked }))}
            />
            <Label htmlFor="use_llm_personalization" className="text-sm font-normal cursor-pointer">
              Use LLM personalization — generate a short, empathetic email body from ticket/customer context (fallback to template body if unavailable)
            </Label>
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
  const [workflowDialog, setWorkflowDialog] = useState({
    open: false, editingId: null, name: '', description: '', stepsJson: WORKFLOW_STEPS_DEFAULT, is_active: true,
    triggerOn: 'none', triggerCategory: '', triggerPriority: '', triggerStatus: '',
  });
  const [savingWorkflow, setSavingWorkflow] = useState(false);
  const [executeTicketsList, setExecuteTicketsList] = useState([]);
  const [stepBuilderOpen, setStepBuilderOpen] = useState(false);
  const [stepBuilderSteps, setStepBuilderSteps] = useState([]);
  const [stepBuilderTemplates, setStepBuilderTemplates] = useState([]);
  const [stepBuilderTickets, setStepBuilderTickets] = useState([]);
  const [stepBuilderCompanyUsers, setStepBuilderCompanyUsers] = useState([]);
  const [stepBuilderTemplatesLoading, setStepBuilderTemplatesLoading] = useState(false);
  const [stepForm, setStepForm] = useState(null);
  const [stepEditIndex, setStepEditIndex] = useState(null);
  const TRIGGER_ON_OPTIONS = [{ value: 'none', label: 'None (manual only)' }, { value: 'ticket_created', label: 'Ticket created' }, { value: 'ticket_updated', label: 'Ticket updated' }];
  const CATEGORY_OPTIONS = ['technical', 'billing', 'account', 'feature_request', 'bug', 'knowledge_gap', 'other'];
  const PRIORITY_OPTIONS = ['low', 'medium', 'high', 'urgent'];
  const STATUS_OPTIONS = ['new', 'open', 'in_progress', 'resolved', 'closed', 'auto_resolved'];
  const STEP_STATUS_OPTIONS = [{ value: '_optional', label: '(optional)' }, ...STATUS_OPTIONS.map((s) => ({ value: s, label: s.replace('_', ' ') }))];

  const openStepBuilder = async () => {
    let steps = [];
    try {
      const parsed = JSON.parse(workflowDialog.stepsJson || '[]');
      if (Array.isArray(parsed)) steps = parsed;
    } catch (_) {}
    setStepBuilderSteps(steps);
    setStepForm(null);
    setStepEditIndex(null);
    setStepBuilderOpen(true);
    setStepBuilderTemplatesLoading(true);
    try {
      const [tRes, tickRes, cuRes] = await Promise.all([
        frontlineAgentService.listNotificationTemplates(),
        frontlineAgentService.listTickets({ limit: 100 }),
        frontlineAgentService.listWorkflowCompanyUsers?.() ?? Promise.resolve({ status: 'success', data: [] }),
      ]);
      setStepBuilderTemplates((tRes.status === 'success' && tRes.data) ? tRes.data : []);
      setStepBuilderTickets((tickRes.status === 'success' && tickRes.data) ? tickRes.data : []);
      setStepBuilderCompanyUsers((cuRes.status === 'success' && cuRes.data) ? cuRes.data : []);
    } catch (_) {
      setStepBuilderTemplates([]);
      setStepBuilderTickets([]);
      setStepBuilderCompanyUsers([]);
    } finally {
      setStepBuilderTemplatesLoading(false);
    }
  };

  const closeStepBuilder = (apply) => {
    if (apply && stepBuilderSteps.length > 0) {
      setWorkflowDialog((d) => ({ ...d, stepsJson: JSON.stringify(stepBuilderSteps, null, 2) }));
    }
    setStepBuilderOpen(false);
    setStepForm(null);
    setStepEditIndex(null);
  };

  const addStepToBuilder = (step) => {
    const normalized = { type: step.type };
    if (step.type === 'send_email') {
      const tid = parseInt(step.template_id, 10);
      if (!tid) return;
      normalized.template_id = tid;
      normalized.recipient_email = (step.recipient_email || '').trim() || '{{recipient_email}}';
    }
    if (step.type === 'update_ticket') {
      if (step.status && step.status !== '_optional') normalized.status = step.status;
      if (step.resolution && step.resolution.trim()) normalized.resolution = step.resolution.trim();
      const tid = (step.ticket_id || '').trim();
      if (tid) normalized.ticket_id = parseInt(tid, 10) || undefined;
      if (normalized.ticket_id === undefined && !normalized.status && !normalized.resolution) return;
    }
    if (step.type === 'webhook') {
      const url = (step.url || '').trim();
      if (!url) return;
      normalized.url = url;
      normalized.method = (step.method || 'POST').toUpperCase();
      if ((step.body || '').trim()) normalized.body = step.body.trim();
    }
    if (step.type === 'slack') {
      const webhook_url = (step.webhook_url || '').trim();
      if (!webhook_url) return;
      normalized.webhook_url = webhook_url;
      normalized.text = (step.text || 'Workflow step executed.').trim();
    }
    if (step.type === 'assign') {
      const cuId = step.assign_to_company_user_id != null ? parseInt(step.assign_to_company_user_id, 10) : undefined;
      if (cuId == null || isNaN(cuId)) return;
      normalized.assign_to_company_user_id = cuId;
      const tid = (step.ticket_id || '').trim();
      if (tid) normalized.ticket_id = parseInt(tid, 10) || undefined;
    }
    if (stepEditIndex !== null) {
      setStepBuilderSteps((prev) => prev.map((s, i) => (i === stepEditIndex ? normalized : s)));
      setStepEditIndex(null);
    } else {
      setStepBuilderSteps((prev) => [...prev, normalized]);
    }
    setStepForm(null);
  };

  const removeStepAt = (index) => {
    setStepBuilderSteps((prev) => prev.filter((_, i) => i !== index));
    if (stepEditIndex === index) { setStepForm(null); setStepEditIndex(null); }
    else if (stepEditIndex !== null && stepEditIndex > index) setStepEditIndex(stepEditIndex - 1);
  };

  const moveStep = (index, dir) => {
    if (dir === -1 && index <= 0) return;
    if (dir === 1 && index >= stepBuilderSteps.length - 1) return;
    const next = [...stepBuilderSteps];
    const j = index + dir;
    [next[index], next[j]] = [next[j], next[index]];
    setStepBuilderSteps(next);
    if (stepEditIndex === index) setStepEditIndex(j);
    else if (stepEditIndex === j) setStepEditIndex(index);
  };

  const stepSummary = (s) => {
    if (s.type === 'send_email') return `Send email: template ${s.template_id || '?'} → ${(s.recipient_email || '').slice(0, 30)}${(s.recipient_email || '').length > 30 ? '…' : ''}`;
    if (s.type === 'update_ticket') {
      const parts = [];
      if (s.status) parts.push(`status=${s.status}`);
      if (s.resolution) parts.push('resolution');
      if (s.ticket_id) parts.push(`ticket_id=${s.ticket_id}`);
      return `Update ticket: ${parts.length ? parts.join(', ') : '(no fields)'}`;
    }
    if (s.type === 'webhook') return `Webhook: ${(s.method || 'POST')} ${(s.url || '').slice(0, 40)}${(s.url || '').length > 40 ? '…' : ''}`;
    if (s.type === 'slack') return `Slack: ${(s.text || '').slice(0, 35)}${(s.text || '').length > 35 ? '…' : ''}`;
    if (s.type === 'assign') {
      const cu = stepBuilderCompanyUsers.find((u) => u.id === s.assign_to_company_user_id);
      return `Assign ticket → ${cu ? (cu.full_name || cu.email || `#${cu.id}`) : `user #${s.assign_to_company_user_id}`}`;
    }
    return `Step: ${s.type || 'unknown'}`;
  };

  const load = async () => {
    setLoading(true);
    try {
      const [wRes, eRes, tRes] = await Promise.all([
        frontlineAgentService.listWorkflows(),
        frontlineAgentService.listWorkflowExecutions(),
        frontlineAgentService.listTickets({ limit: 100 }),
      ]);
      setWorkflows((wRes.status === 'success' && wRes.data) ? wRes.data : []);
      setExecutions((eRes.status === 'success' && eRes.data) ? eRes.data : []);
      setExecuteTicketsList((tRes.status === 'success' && tRes.data) ? tRes.data : []);
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
  const openCreateWorkflow = () => setWorkflowDialog({
    open: true, editingId: null, name: '', description: '', stepsJson: WORKFLOW_STEPS_DEFAULT, is_active: true,
    triggerOn: 'none', triggerCategory: '', triggerPriority: '', triggerStatus: '',
  });
  const openEditWorkflow = (w) => {
    const tc = w.trigger_conditions || {};
    setWorkflowDialog({
      open: true, editingId: w.id, name: w.name || '', description: w.description || '',
      stepsJson: Array.isArray(w.steps) ? JSON.stringify(w.steps, null, 2) : (typeof w.steps === 'string' ? w.steps : WORKFLOW_STEPS_DEFAULT),
      is_active: w.is_active !== false,
      triggerOn: tc.on || 'none', triggerCategory: tc.category || '', triggerPriority: tc.priority || '', triggerStatus: tc.status || '',
    });
  };
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
      const trigger_conditions = workflowDialog.triggerOn === 'none' ? {} : {
        on: workflowDialog.triggerOn,
        ...(workflowDialog.triggerCategory && { category: workflowDialog.triggerCategory }),
        ...(workflowDialog.triggerPriority && { priority: workflowDialog.triggerPriority }),
        ...(workflowDialog.triggerOn === 'ticket_updated' && workflowDialog.triggerStatus && { status: workflowDialog.triggerStatus }),
      };
      if (workflowDialog.editingId) {
        const res = await frontlineAgentService.updateWorkflow(workflowDialog.editingId, {
          name: workflowDialog.name.trim(),
          description: workflowDialog.description,
          steps,
          is_active: workflowDialog.is_active,
          trigger_conditions,
        });
        if (res.status === 'success') {
          toast({ title: 'Saved', description: 'Workflow updated.' });
          setWorkflowDialog({ open: false, editingId: null, name: '', description: '', stepsJson: WORKFLOW_STEPS_DEFAULT, is_active: true, triggerOn: 'none', triggerCategory: '', triggerPriority: '', triggerStatus: '' });
          load();
        } else throw new Error(res.message);
      } else {
        const res = await frontlineAgentService.createWorkflow({
          name: workflowDialog.name.trim(),
          description: workflowDialog.description,
          steps,
          is_active: workflowDialog.is_active,
          trigger_conditions,
        });
        if (res.status === 'success') {
          toast({ title: 'Created', description: 'Workflow created.' });
          setWorkflowDialog({ open: false, editingId: null, name: '', description: '', stepsJson: WORKFLOW_STEPS_DEFAULT, is_active: true, triggerOn: 'none', triggerCategory: '', triggerPriority: '', triggerStatus: '' });
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
            <Label>Ticket (optional)</Label>
            <Select value={executeForm.ticket_id || '_none'} onValueChange={(v) => setExecuteForm((f) => ({ ...f, ticket_id: v === '_none' ? '' : v }))}>
              <SelectTrigger className="w-[280px] max-w-full"><SelectValue placeholder="Select ticket" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="_none">No ticket (manual context only)</SelectItem>
                {executeTicketsList.map((t) => (
                  <SelectItem key={t.id} value={String(t.id)}>#{t.id}: {(t.title || '').slice(0, 40)}{(t.title || '').length > 40 ? '…' : ''}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Recipient email (optional)</Label>
            <Input placeholder="email@example.com" value={executeForm.recipient_email} onChange={(e) => setExecuteForm((f) => ({ ...f, recipient_email: e.target.value }))} className="w-[180px]" />
          </div>
          <Button type="submit" disabled={executing}>Execute</Button>
        </form>
        {loading ? <div className="flex justify-center py-4"><Loader2 className="h-6 w-6 animate-spin" /></div> : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full min-w-0">
            <div className="min-w-0">
              <h4 className="font-medium mb-2">Workflows ({workflows.length})</h4>
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {workflows.length === 0 ? <p className="text-sm text-muted-foreground">No workflows yet. Click &quot;Create workflow&quot; to add one.</p> : workflows.map((w) => (
                  <div key={w.id} className="flex justify-between items-center p-2 border rounded text-sm">
                    <span className="truncate min-w-0">{w.name}</span>
                    <div className="flex items-center gap-1 flex-wrap justify-end shrink-0">
                      {(w.trigger_conditions?.on) && <Badge variant="outline" className="text-xs">{w.trigger_conditions.on.replace('_', ' ')}</Badge>}
                      <Badge variant={w.is_active ? 'default' : 'secondary'}>{w.is_active ? 'Active' : 'Inactive'}</Badge>
                      <Button type="button" variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEditWorkflow(w)} title="Edit"><Pencil className="h-4 w-4" /></Button>
                      <Button type="button" variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive" onClick={() => handleDeleteWorkflow(w)} title="Delete"><Trash2 className="h-4 w-4" /></Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="min-w-0">
              <h4 className="font-medium mb-2">Recent executions</h4>
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {executions.length === 0 ? <p className="text-sm text-muted-foreground">No executions yet.</p> : executions.slice(0, 15).map((ex) => (
                  <div key={ex.id} className="flex justify-between items-center p-2 border rounded text-sm gap-2">
                    <span className="truncate min-w-0">{ex.workflow_name} · {new Date(ex.started_at).toLocaleString()}</span>
                    <Badge variant={ex.status === 'completed' ? 'default' : ex.status === 'failed' ? 'destructive' : 'secondary'} className="shrink-0">{ex.status}</Badge>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
    <Dialog open={workflowDialog.open} onOpenChange={(open) => !open && setWorkflowDialog((d) => ({ ...d, open: false }))}>
      <DialogContent className="max-w-xl max-h-[90vh] flex flex-col overflow-hidden">
        <DialogHeader className="shrink-0">
          <DialogTitle>{workflowDialog.editingId ? 'Edit workflow' : 'Create workflow'}</DialogTitle>
          <DialogDescription>Steps run in order. When triggered by a ticket, context includes ticket_id, ticket_title, recipient_email, etc.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSaveWorkflow} className="flex flex-col min-h-0 flex-1 overflow-hidden">
          <div className="overflow-y-auto flex-1 min-h-0 space-y-4 pr-1">
          <div className="space-y-2">
            <Label>Name</Label>
            <Input value={workflowDialog.name} onChange={(e) => setWorkflowDialog((d) => ({ ...d, name: e.target.value }))} placeholder="e.g. Ticket follow-up flow" required />
          </div>
          <div className="space-y-2">
            <Label>Description (optional)</Label>
            <Input value={workflowDialog.description} onChange={(e) => setWorkflowDialog((d) => ({ ...d, description: e.target.value }))} placeholder="Short description" />
          </div>
          <div className="space-y-3 p-3 border rounded-lg bg-muted/40">
            <Label className="text-sm font-medium">Trigger (run automatically)</Label>
            <div className="space-y-2">
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Run when</Label>
                <Select value={workflowDialog.triggerOn} onValueChange={(v) => setWorkflowDialog((d) => ({ ...d, triggerOn: v, triggerStatus: v === 'ticket_updated' ? d.triggerStatus : '' }))}>
                  <SelectTrigger className="w-full max-w-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {TRIGGER_ON_OPTIONS.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              {workflowDialog.triggerOn !== 'none' && (
                <div className="flex flex-wrap gap-3">
                  <div className="space-y-1">
                    <Label className="text-xs text-muted-foreground">Category (optional)</Label>
                    <Select value={workflowDialog.triggerCategory || '_any'} onValueChange={(v) => setWorkflowDialog((d) => ({ ...d, triggerCategory: v === '_any' ? '' : v }))}>
                      <SelectTrigger className="w-[160px]"><SelectValue placeholder="Any" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="_any">Any</SelectItem>
                        {CATEGORY_OPTIONS.map((c) => <SelectItem key={c} value={c}>{c.replace('_', ' ')}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs text-muted-foreground">Priority (optional)</Label>
                    <Select value={workflowDialog.triggerPriority || '_any'} onValueChange={(v) => setWorkflowDialog((d) => ({ ...d, triggerPriority: v === '_any' ? '' : v }))}>
                      <SelectTrigger className="w-[120px]"><SelectValue placeholder="Any" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="_any">Any</SelectItem>
                        {PRIORITY_OPTIONS.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  {workflowDialog.triggerOn === 'ticket_updated' && (
                    <div className="space-y-1">
                      <Label className="text-xs text-muted-foreground">New status (optional)</Label>
                      <Select value={workflowDialog.triggerStatus || '_any'} onValueChange={(v) => setWorkflowDialog((d) => ({ ...d, triggerStatus: v === '_any' ? '' : v }))}>
                        <SelectTrigger className="w-[140px]"><SelectValue placeholder="Any" /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="_any">Any</SelectItem>
                          {STATUS_OPTIONS.map((s) => <SelectItem key={s} value={s}>{s.replace('_', ' ')}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
          <div className="space-y-2">
            <Label>Steps</Label>
            <div className="flex items-center gap-2 flex-wrap">
              <Button type="button" variant="outline" onClick={openStepBuilder}>
                {(() => {
                  let n = 0;
                  try {
                    const p = JSON.parse(workflowDialog.stepsJson || '[]');
                    n = Array.isArray(p) ? p.length : 0;
                  } catch (_) {}
                  return n ? `${n} step(s) configured — Configure steps` : 'Configure steps (email, ticket, webhook, Slack, assign)';
                })()}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Add steps: send email, update ticket, webhook (HTTP), Slack (message), or assign ticket to a user. Use {`{{recipient_email}}`}, {`{{ticket_id}}`}, {`{{ticket_title}}`} when triggered by a ticket.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <input type="checkbox" id="wf-active" checked={workflowDialog.is_active} onChange={(e) => setWorkflowDialog((d) => ({ ...d, is_active: e.target.checked }))} className="rounded border" />
            <Label htmlFor="wf-active">Active (can be executed)</Label>
          </div>
          </div>
          <DialogFooter className="shrink-0 border-t pt-4 mt-4 flex-shrink-0">
            <Button type="button" variant="outline" onClick={() => setWorkflowDialog((d) => ({ ...d, open: false }))}>Cancel</Button>
            <Button type="submit" disabled={savingWorkflow}>{savingWorkflow ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Save</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>

    {/* Step builder dialog */}
    <Dialog open={stepBuilderOpen} onOpenChange={(open) => !open && closeStepBuilder(false)}>
      <DialogContent className="max-w-lg max-h-[90vh] flex flex-col overflow-hidden">
        <DialogHeader>
          <DialogTitle>Configure workflow steps</DialogTitle>
          <DialogDescription>Add steps in order. They run one after another when the workflow runs.</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col min-h-0 flex-1 overflow-hidden space-y-4">
          <div className="overflow-y-auto min-h-0 space-y-2">
            {stepBuilderSteps.length === 0 && !stepForm && (
              <p className="text-sm text-muted-foreground">No steps yet. Add send email, update ticket, webhook, Slack, or assign below.</p>
            )}
            {stepBuilderSteps.map((s, i) => (
              <div key={i} className="flex items-center gap-2 p-2 border rounded bg-muted/30">
                <span className="text-xs text-muted-foreground w-6">{i + 1}.</span>
                <span className="flex-1 min-w-0 truncate text-sm">{stepSummary(s)}</span>
                <div className="flex items-center shrink-0">
                  <Button type="button" variant="ghost" size="icon" className="h-8 w-8" onClick={() => moveStep(i, -1)} title="Move up"><ChevronUp className="h-4 w-4" /></Button>
                  <Button type="button" variant="ghost" size="icon" className="h-8 w-8" onClick={() => moveStep(i, 1)} title="Move down"><ChevronDown className="h-4 w-4" /></Button>
                  <Button type="button" variant="ghost" size="icon" className="h-8 w-8" onClick={() => {
                    if (s.type === 'send_email') setStepForm({ type: 'send_email', template_id: String(s.template_id ?? ''), recipient_email: s.recipient_email ?? '' });
                    else if (s.type === 'update_ticket') setStepForm({ type: 'update_ticket', status: s.status ?? '', resolution: s.resolution ?? '', ticket_id: s.ticket_id ? String(s.ticket_id) : '' });
                    else if (s.type === 'webhook') setStepForm({ type: 'webhook', url: s.url ?? '', method: s.method ?? 'POST', body: s.body ?? '' });
                    else if (s.type === 'slack') setStepForm({ type: 'slack', webhook_url: s.webhook_url ?? '', text: s.text ?? 'Workflow step executed.' });
                    else if (s.type === 'assign') setStepForm({ type: 'assign', assign_to_company_user_id: s.assign_to_company_user_id != null ? String(s.assign_to_company_user_id) : '', ticket_id: s.ticket_id ? String(s.ticket_id) : '' });
                    else setStepForm(null);
                    setStepEditIndex(i);
                  }} title="Edit"><Pencil className="h-4 w-4" /></Button>
                  <Button type="button" variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={() => removeStepAt(i)} title="Remove"><Trash2 className="h-4 w-4" /></Button>
                </div>
              </div>
            ))}
          </div>

          {!stepForm ? (
            <div className="flex flex-wrap gap-2 shrink-0">
              <Button type="button" variant="outline" size="sm" onClick={() => setStepForm({ type: 'send_email', template_id: (stepBuilderTemplates[0] && stepBuilderTemplates[0].id) ? String(stepBuilderTemplates[0].id) : '', recipient_email: '{{recipient_email}}' })}>Add send email</Button>
              <Button type="button" variant="outline" size="sm" onClick={() => setStepForm({ type: 'update_ticket', status: '', resolution: '', ticket_id: '' })}>Add update ticket</Button>
              <Button type="button" variant="outline" size="sm" onClick={() => setStepForm({ type: 'webhook', url: '', method: 'POST', body: '{}' })}>Add webhook</Button>
              <Button type="button" variant="outline" size="sm" onClick={() => setStepForm({ type: 'slack', webhook_url: '', text: 'Workflow step executed.' })}>Add Slack</Button>
              <Button type="button" variant="outline" size="sm" onClick={() => setStepForm({ type: 'assign', assign_to_company_user_id: (stepBuilderCompanyUsers[0] && stepBuilderCompanyUsers[0].id) ? String(stepBuilderCompanyUsers[0].id) : '', ticket_id: '' })}>Add assign ticket</Button>
            </div>
          ) : (
            <div className="rounded-lg border p-4 space-y-3 bg-muted/20 shrink-0">
              <div className="flex justify-between items-center">
                <span className="font-medium text-sm">
                  {stepForm.type === 'send_email' && 'Send email'}
                  {stepForm.type === 'update_ticket' && 'Update ticket'}
                  {stepForm.type === 'webhook' && 'Webhook'}
                  {stepForm.type === 'slack' && 'Slack'}
                  {stepForm.type === 'assign' && 'Assign ticket'}
                </span>
                <Button type="button" variant="ghost" size="sm" onClick={() => { setStepForm(null); setStepEditIndex(null); }}>Cancel</Button>
              </div>
              {stepForm.type === 'send_email' && (
                <>
                  <div className="space-y-1">
                    <Label className="text-xs">Template</Label>
                    <Select value={stepForm.template_id || ''} onValueChange={(v) => setStepForm((f) => ({ ...f, template_id: v }))} disabled={stepBuilderTemplatesLoading}>
                      <SelectTrigger><SelectValue placeholder="Select template" /></SelectTrigger>
                      <SelectContent>
                        {stepBuilderTemplates.map((t) => <SelectItem key={t.id} value={String(t.id)}>{t.name} (ID: {t.id})</SelectItem>)}
                        {stepBuilderTemplates.length === 0 && !stepBuilderTemplatesLoading && <SelectItem value="_no_templates" disabled>No templates — create one in Notifications tab</SelectItem>}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Recipient email</Label>
                    <Input value={stepForm.recipient_email || ''} onChange={(e) => setStepForm((f) => ({ ...f, recipient_email: e.target.value }))} placeholder="{{recipient_email}} or email@example.com" />
                  </div>
                </>
              )}
              {stepForm.type === 'update_ticket' && (
                <>
                  <div className="space-y-1">
                    <Label className="text-xs">Status (optional)</Label>
                    <Select value={stepForm.status || '_optional'} onValueChange={(v) => setStepForm((f) => ({ ...f, status: v }))}>
                      <SelectTrigger><SelectValue placeholder="Optional" /></SelectTrigger>
                      <SelectContent>
                        {STEP_STATUS_OPTIONS.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Resolution (optional)</Label>
                    <Textarea value={stepForm.resolution || ''} onChange={(e) => setStepForm((f) => ({ ...f, resolution: e.target.value }))} rows={2} placeholder="Text to set on the ticket" className="resize-y" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Ticket (optional — use from context when triggered)</Label>
                    <Select value={stepForm.ticket_id || '_context'} onValueChange={(v) => setStepForm((f) => ({ ...f, ticket_id: v === '_context' ? '' : v }))}>
                      <SelectTrigger><SelectValue placeholder="Use from context" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="_context">Use from context</SelectItem>
                        {stepBuilderTickets.map((t) => (
                          <SelectItem key={t.id} value={String(t.id)}>#{t.id}: {(t.title || '').slice(0, 35)}{(t.title || '').length > 35 ? '…' : ''}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </>
              )}
              {stepForm.type === 'webhook' && (
                <>
                  <div className="space-y-1">
                    <Label className="text-xs">URL (required)</Label>
                    <Input value={stepForm.url || ''} onChange={(e) => setStepForm((f) => ({ ...f, url: e.target.value }))} placeholder="https://example.com/webhook" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Method</Label>
                    <Select value={stepForm.method || 'POST'} onValueChange={(v) => setStepForm((f) => ({ ...f, method: v }))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="GET">GET</SelectItem>
                        <SelectItem value="POST">POST</SelectItem>
                        <SelectItem value="PUT">PUT</SelectItem>
                        <SelectItem value="PATCH">PATCH</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Body (JSON, use {`{{ticket_id}}`}, {`{{recipient_email}}`} for context)</Label>
                    <Textarea value={stepForm.body || ''} onChange={(e) => setStepForm((f) => ({ ...f, body: e.target.value }))} rows={3} placeholder='{"event": "ticket_created", "ticket_id": "{{ticket_id}}"}' className="font-mono text-xs resize-y" />
                  </div>
                </>
              )}
              {stepForm.type === 'slack' && (
                <>
                  <div className="space-y-1">
                    <Label className="text-xs">Slack webhook URL (required)</Label>
                    <Input value={stepForm.webhook_url || ''} onChange={(e) => setStepForm((f) => ({ ...f, webhook_url: e.target.value }))} placeholder="https://hooks.slack.com/services/..." type="password" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Message (use {`{{ticket_id}}`}, {`{{ticket_title}}`} for context)</Label>
                    <Textarea value={stepForm.text || ''} onChange={(e) => setStepForm((f) => ({ ...f, text: e.target.value }))} rows={2} placeholder="New ticket #{{ticket_id}}: {{ticket_title}}" className="resize-y" />
                  </div>
                </>
              )}
              {stepForm.type === 'assign' && (
                <>
                  <div className="space-y-1">
                    <Label className="text-xs">Assign to (company user)</Label>
                    <Select value={stepForm.assign_to_company_user_id || ''} onValueChange={(v) => setStepForm((f) => ({ ...f, assign_to_company_user_id: v }))}>
                      <SelectTrigger><SelectValue placeholder="Select user" /></SelectTrigger>
                      <SelectContent>
                        {stepBuilderCompanyUsers.map((u) => (
                          <SelectItem key={u.id} value={String(u.id)}>{u.full_name || u.email || `#${u.id}`}</SelectItem>
                        ))}
                        {stepBuilderCompanyUsers.length === 0 && <SelectItem value="_none" disabled>No company users</SelectItem>}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Ticket (optional — use from context when triggered)</Label>
                    <Select value={stepForm.ticket_id || '_context'} onValueChange={(v) => setStepForm((f) => ({ ...f, ticket_id: v === '_context' ? '' : v }))}>
                      <SelectTrigger><SelectValue placeholder="Use from context" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="_context">Use from context</SelectItem>
                        {stepBuilderTickets.map((t) => (
                          <SelectItem key={t.id} value={String(t.id)}>#{t.id}: {(t.title || '').slice(0, 35)}{(t.title || '').length > 35 ? '…' : ''}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </>
              )}
              <Button type="button" size="sm" onClick={() => addStepToBuilder(stepForm)}>
                {stepEditIndex !== null ? 'Save' : 'Add step'}
              </Button>
            </div>
          )}
        </div>
        <DialogFooter className="shrink-0 border-t pt-4 mt-4">
          <Button type="button" variant="outline" onClick={() => closeStepBuilder(false)}>Cancel</Button>
          <Button type="button" onClick={() => closeStepBuilder(true)}>Apply</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </>
  );
}

const CHART_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];

const FRONTLINE_TAB_ITEMS = [
  { value: 'overview', label: 'Overview', icon: LayoutDashboard },
  { value: 'documents', label: 'Documents', icon: FileText },
  { value: 'qa', label: 'Knowledge Q&A', icon: MessageSquare },
  { value: 'widget', label: 'Chat widget', icon: Monitor },
  { value: 'tickets', label: 'Tickets', icon: Ticket },
  { value: 'handoffs', label: 'Hand-offs', icon: Headphones },
  { value: 'notifications', label: 'Notifications', icon: Bell },
  { value: 'workflows', label: 'Workflows', icon: GitBranch },
  { value: 'analytics', label: 'Analytics', icon: BarChart3 },
  { value: 'ai-graphs', label: 'AI Graphs', icon: Sparkles },
];

// ============================================================================
// Hand-off queue tab (Phase 3 Batch 4 — UI)
// Lists pending + accepted hand-offs, opens a drawer with the ticket thread,
// an LLM-drafted reply button, and "Send reply" / "Accept hand-off" actions.
// ============================================================================
function HandoffQueueTab() {
  const { toast } = useToast();
  const [statusFilter, setStatusFilter] = useState('pending');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [mine, setMine] = useState(false);
  // Drawer state for the currently-open hand-off.
  const [drawer, setDrawer] = useState({
    open: false, ticket: null, messages: [], loading: false,
    reply: '', sending: false, suggesting: false, accepting: false,
  });

  const load = async () => {
    setLoading(true);
    try {
      const res = await frontlineAgentService.listHandoffQueue({
        status: statusFilter,
        mine: mine,
      });
      setRows((res.status === 'success' && Array.isArray(res.data)) ? res.data : []);
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to load hand-offs', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, [statusFilter, mine]);

  const openTicket = async (ticket) => {
    setDrawer({
      open: true, ticket, messages: [], loading: true,
      reply: '', sending: false, suggesting: false, accepting: false,
    });
    try {
      const res = await frontlineAgentService.listTicketMessages(ticket.id);
      setDrawer((prev) => ({
        ...prev,
        messages: (res?.data) || [],
        loading: false,
      }));
    } catch (e) {
      console.error('Load thread failed', e);
      setDrawer((prev) => ({ ...prev, loading: false }));
      toast({ title: 'Failed to load thread', variant: 'destructive' });
    }
  };

  const handleSuggest = async () => {
    if (!drawer.ticket) return;
    setDrawer((prev) => ({ ...prev, suggesting: true }));
    try {
      const res = await frontlineAgentService.suggestTicketReply(drawer.ticket.id);
      const draft = (res?.data?.draft || '').trim();
      if (!draft) {
        toast({ title: 'No draft returned', variant: 'destructive' });
      } else {
        setDrawer((prev) => ({ ...prev, reply: draft }));
      }
    } catch (e) {
      toast({ title: 'Draft failed', description: e.message || 'LLM error', variant: 'destructive' });
    } finally {
      setDrawer((prev) => ({ ...prev, suggesting: false }));
    }
  };

  const handleAccept = async () => {
    if (!drawer.ticket) return;
    setDrawer((prev) => ({ ...prev, accepting: true }));
    try {
      const res = await frontlineAgentService.acceptHandoff(drawer.ticket.id);
      if (res?.status === 'success' && res.data) {
        setDrawer((prev) => ({ ...prev, ticket: res.data }));
        setRows((list) => list.map((r) => (r.id === res.data.id ? res.data : r)));
        toast({ title: 'Hand-off accepted' });
      }
    } catch (e) {
      toast({ title: 'Accept failed', description: e.message || 'Error', variant: 'destructive' });
    } finally {
      setDrawer((prev) => ({ ...prev, accepting: false }));
    }
  };

  const handleSend = async () => {
    if (!drawer.ticket) return;
    const body = drawer.reply.trim();
    if (!body) {
      toast({ title: 'Reply is empty', variant: 'destructive' });
      return;
    }
    setDrawer((prev) => ({ ...prev, sending: true }));
    try {
      const res = await frontlineAgentService.replyToTicket(drawer.ticket.id, { body_text: body });
      if (res?.status === 'success' && res.data) {
        setDrawer((prev) => ({
          ...prev,
          messages: [...prev.messages, res.data],
          reply: '',
        }));
        toast({ title: 'Reply sent' });
      }
    } catch (e) {
      toast({ title: 'Send failed', description: e.message || 'Error', variant: 'destructive' });
    } finally {
      setDrawer((prev) => ({ ...prev, sending: false }));
    }
  };

  const reasonLabel = (r) => ({
    low_confidence: 'Low AI confidence',
    customer_requested: 'Customer asked for a human',
    manual_escalation: 'Manual escalation',
    sla_risk: 'SLA at risk',
  }[r] || r || '—');

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2">
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="accepted">Accepted</SelectItem>
            <SelectItem value="all">All</SelectItem>
          </SelectContent>
        </Select>
        <label className="flex items-center gap-2 text-sm select-none">
          <Checkbox
            checked={mine}
            onCheckedChange={(v) => setMine(Boolean(v))}
          />
          Only mine
        </label>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          <span className="ml-2">Refresh</span>
        </Button>
        <span className="text-sm text-muted-foreground ml-auto">{rows.length} ticket{rows.length === 1 ? '' : 's'}</span>
      </div>

      {/* Queue table */}
      <div className="overflow-x-auto -mx-2 sm:mx-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Customer</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Requested</TableHead>
              <TableHead>Priority</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-8">
                  <Loader2 className="h-5 w-5 animate-spin inline-block text-muted-foreground" />
                </TableCell>
              </TableRow>
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-sm text-muted-foreground py-10">
                  No {statusFilter === 'all' ? '' : statusFilter} hand-offs.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((t) => (
                <TableRow key={t.id}>
                  <TableCell className="max-w-[28ch] truncate" title={t.title}>{t.title}</TableCell>
                  <TableCell>
                    {t.contact ? (
                      <span className="text-sm">
                        <span className="font-medium">{t.contact.name || t.contact.email}</span>
                        {t.contact.name && (
                          <span className="text-xs text-muted-foreground"> · {t.contact.email}</span>
                        )}
                      </span>
                    ) : <span className="text-muted-foreground">—</span>}
                  </TableCell>
                  <TableCell><Badge variant="secondary" className="text-xs">{reasonLabel(t.handoff_reason)}</Badge></TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {t.handoff_requested_at ? new Date(t.handoff_requested_at).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' }) : '—'}
                  </TableCell>
                  <TableCell><Badge variant="outline" className="text-xs">{t.priority}</Badge></TableCell>
                  <TableCell className="text-right">
                    <Button size="sm" variant="outline" onClick={() => openTicket(t)}>
                      Open
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Hand-off detail drawer (dialog) */}
      <Dialog open={drawer.open} onOpenChange={(open) => setDrawer((prev) => ({ ...prev, open }))}>
        <DialogContent className="max-w-3xl max-h-[90vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Headphones className="h-5 w-5 text-violet-400" />
              <span className="truncate">{drawer.ticket?.title || 'Hand-off'}</span>
            </DialogTitle>
            <DialogDescription>
              {drawer.ticket ? (
                <span className="flex flex-wrap items-center gap-2 text-xs">
                  <Badge variant="secondary">{reasonLabel(drawer.ticket.handoff_reason)}</Badge>
                  <Badge variant="outline">{drawer.ticket.handoff_status}</Badge>
                  {drawer.ticket.contact && (
                    <span className="text-muted-foreground">
                      · {drawer.ticket.contact.name || drawer.ticket.contact.email}
                    </span>
                  )}
                </span>
              ) : null}
            </DialogDescription>
          </DialogHeader>

          {/* Handoff context from AI (question, AI answer, score) */}
          {drawer.ticket?.handoff_context && Object.keys(drawer.ticket.handoff_context).length > 0 && (
            <div className="rounded-md border border-border/50 bg-muted/30 p-3 text-xs space-y-1">
              {drawer.ticket.handoff_context.question && (
                <div><span className="text-muted-foreground">Question:</span> {drawer.ticket.handoff_context.question}</div>
              )}
              {drawer.ticket.handoff_context.ai_answer && (
                <div className="line-clamp-3"><span className="text-muted-foreground">AI answer:</span> {drawer.ticket.handoff_context.ai_answer}</div>
              )}
              {drawer.ticket.handoff_context.best_score != null && (
                <div>
                  <span className="text-muted-foreground">Score:</span> {drawer.ticket.handoff_context.best_score}
                  {drawer.ticket.handoff_context.threshold != null && (
                    <span className="text-muted-foreground"> (threshold {drawer.ticket.handoff_context.threshold})</span>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Thread */}
          <div className="flex-1 overflow-y-auto space-y-3 py-2 min-h-0">
            {drawer.loading ? (
              <div className="flex justify-center py-6">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : drawer.messages.length === 0 ? (
              <div className="text-center text-sm text-muted-foreground py-8">
                No messages on this ticket yet.
                {drawer.ticket?.handoff_context?.question && (
                  <div className="text-xs mt-2">Customer's original question appears in the context panel above.</div>
                )}
              </div>
            ) : drawer.messages.map((m) => (
              <div
                key={m.id}
                className={`rounded-md border p-3 text-sm ${m.direction === 'inbound'
                  ? 'border-border/50 bg-muted/40'
                  : 'border-violet-500/30 bg-violet-500/5'
                }`}
              >
                <div className="flex items-center justify-between gap-2 text-xs mb-1">
                  <span className="font-medium">
                    {m.direction === 'inbound' ? (m.from_name || m.from_address || 'Customer') : 'Agent'}
                  </span>
                  <span className="text-muted-foreground">
                    {m.created_at ? new Date(m.created_at).toLocaleString() : ''}
                  </span>
                </div>
                <div className="whitespace-pre-wrap break-words">{m.body_text || m.subject}</div>
              </div>
            ))}
          </div>

          {/* Reply box + actions */}
          <div className="space-y-2 pt-2 border-t border-border/50">
            <Textarea
              value={drawer.reply}
              onChange={(e) => setDrawer((prev) => ({ ...prev, reply: e.target.value }))}
              placeholder="Type your reply, or click 'Suggest reply' for an AI draft..."
              rows={5}
            />
            <div className="flex items-center gap-2 flex-wrap">
              <Button
                variant="outline"
                size="sm"
                onClick={handleSuggest}
                disabled={drawer.suggesting || drawer.sending}
              >
                {drawer.suggesting
                  ? <Loader2 className="h-4 w-4 animate-spin mr-1" />
                  : <Sparkles className="h-4 w-4 mr-1" />}
                Suggest reply
              </Button>
              {drawer.ticket?.handoff_status === 'pending' && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleAccept}
                  disabled={drawer.accepting}
                >
                  {drawer.accepting
                    ? <Loader2 className="h-4 w-4 animate-spin mr-1" />
                    : <CheckCircle2 className="h-4 w-4 mr-1" />}
                  Accept hand-off
                </Button>
              )}
              <div className="ml-auto">
                <Button onClick={handleSend} disabled={drawer.sending || !drawer.reply.trim()}>
                  {drawer.sending
                    ? <Loader2 className="h-4 w-4 animate-spin mr-1" />
                    : <Send className="h-4 w-4 mr-1" />}
                  Send reply
                </Button>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}


function FrontlineAnalyticsTab() {
  const { toast } = useToast();
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [nlQuestion, setNlQuestion] = useState('');
  const [nlLoading, setNlLoading] = useState(false);
  const [nlResult, setNlResult] = useState(null);
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
  const handleAskAnalytics = async (e) => {
    e?.preventDefault?.();
    const q = nlQuestion.trim();
    if (!q) {
      toast({ title: 'Error', description: 'Enter a question', variant: 'destructive' });
      return;
    }
    setNlLoading(true);
    setNlResult(null);
    try {
      const res = await frontlineAgentService.askFrontlineAnalytics(q, dateFrom || undefined, dateTo || undefined);
      if (res.status === 'success' && res.data) {
        setNlResult(res.data);
      } else {
        throw new Error(res.message || 'Failed to get answer');
      }
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Ask failed', variant: 'destructive' });
    } finally {
      setNlLoading(false);
    }
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><BarChart3 className="h-5 w-5" /> Analytics</CardTitle>
        <CardDescription>Tickets trends and export. Ask in plain language or set date range and load.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* NL analytics - ask in plain language */}
        <div className="rounded-lg border bg-muted/30 p-4 space-y-2">
          <Label className="text-sm font-medium">Ask in plain language</Label>
          <p className="text-xs text-muted-foreground">e.g. &quot;How many tickets were resolved?&quot; or &quot;Breakdown by status&quot;</p>
          <form onSubmit={handleAskAnalytics} className="flex flex-wrap gap-2">
            <Input
              placeholder="Ask a question about your tickets..."
              value={nlQuestion}
              onChange={(e) => setNlQuestion(e.target.value)}
              disabled={nlLoading}
              className="max-w-md"
            />
            <Button type="submit" disabled={nlLoading}>
              {nlLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {nlLoading ? 'Asking...' : 'Ask'}
            </Button>
          </form>
          {nlResult && (
            <div className="mt-3 space-y-3">
              <div className="p-3 rounded-lg bg-background border text-sm whitespace-pre-wrap">{nlResult.answer}</div>
              {nlResult.chart_type && nlResult.analytics_data && (
                <div className="mt-2">
                  {nlResult.chart_type === 'by_date' && (nlResult.analytics_data.tickets_by_date || []).length > 0 && (
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm">Tickets over time</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <ResponsiveContainer width="100%" height={220}>
                          <BarChart data={nlResult.analytics_data.tickets_by_date} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                            <Tooltip contentStyle={{ borderRadius: 8 }} />
                            <Bar dataKey="count" name="Tickets" fill={CHART_COLORS[0]} radius={[4, 4, 0, 0]} />
                          </BarChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>
                  )}
                  {nlResult.chart_type === 'by_status' && (nlResult.analytics_data.tickets_by_status || []).length > 0 && (
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm">By status</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <ResponsiveContainer width="100%" height={220}>
                          <BarChart data={nlResult.analytics_data.tickets_by_status} layout="vertical" margin={{ top: 8, right: 8, left: 60, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                            <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                            <YAxis type="category" dataKey="status" width={56} tick={{ fontSize: 11 }} />
                            <Tooltip contentStyle={{ borderRadius: 8 }} />
                            <Bar dataKey="count" name="Tickets" fill={CHART_COLORS[1]} radius={[0, 4, 4, 0]} />
                          </BarChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>
                  )}
                  {nlResult.chart_type === 'by_category' && (nlResult.analytics_data.tickets_by_category || []).length > 0 && (
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm">By category</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <ResponsiveContainer width="100%" height={220}>
                          <BarChart data={nlResult.analytics_data.tickets_by_category} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                            <XAxis dataKey="category" tick={{ fontSize: 11 }} />
                            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                            <Tooltip contentStyle={{ borderRadius: 8 }} />
                            <Bar dataKey="count" name="Tickets" fill={CHART_COLORS[2]} radius={[4, 4, 0, 0]} />
                          </BarChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

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

            {/* Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Tickets over time */}
              {(data.tickets_by_date || []).length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">Tickets over time</CardTitle>
                    <CardDescription>Daily ticket count</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={260}>
                      <BarChart data={data.tickets_by_date} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                        <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                        <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                        <Tooltip contentStyle={{ borderRadius: 8 }} />
                        <Bar dataKey="count" name="Tickets" fill={CHART_COLORS[0]} radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              )}
              {/* By status */}
              {(data.tickets_by_status || []).length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">By status</CardTitle>
                    <CardDescription>Ticket distribution by status</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={260}>
                      <BarChart data={data.tickets_by_status} layout="vertical" margin={{ top: 8, right: 8, left: 60, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                        <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                        <YAxis type="category" dataKey="status" width={56} tick={{ fontSize: 11 }} />
                        <Tooltip contentStyle={{ borderRadius: 8 }} />
                        <Bar dataKey="count" name="Tickets" fill={CHART_COLORS[1]} radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              )}
            </div>

            {/* By category - full width bar or pie */}
            {(data.tickets_by_category || []).length > 0 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">By category</CardTitle>
                  <CardDescription>Ticket distribution by category</CardDescription>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={data.tickets_by_category} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                      <XAxis dataKey="category" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                      <Tooltip contentStyle={{ borderRadius: 8 }} />
                      <Bar dataKey="count" name="Tickets" fill={CHART_COLORS[2]} radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            )}

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

  const INPUT_MODE_OPTIONS = [
    {
      value: 'search',
      label: 'Search',
      placeholder: 'Ask a question...',
      icon: Search,
    },
    {
      value: 'graph',
      label: 'Graph',
      placeholder: 'Describe the support graph you want to generate…',
      icon: BarChart3,
    },
  ];

  const [inputMode, setInputMode] = useState('search');
  const [expandedGraph, setExpandedGraph] = useState(null); // { chart, chartTitle }
  const selectedMode = INPUT_MODE_OPTIONS.find((m) => m.value === inputMode) || INPUT_MODE_OPTIONS[0];
  const SelectedModeIcon = selectedMode.icon;

  const [showSidebarSearch, setShowSidebarSearch] = useState(false);
  const [sidebarSearch, setSidebarSearch] = useState('');
  const [showChatHistory, setShowChatHistory] = useState(true);
  const messagesEndRef = useRef(null);
  // Q&A scope: restrict answers to document type(s) or specific documents
  const [qaScopeMode, setQaScopeMode] = useState('all'); // 'all' | 'type' | 'documents'
  const [qaScopeDocumentTypes, setQaScopeDocumentTypes] = useState([]); // e.g. ['policy', 'knowledge_base']
  const [qaScopeDocumentIds, setQaScopeDocumentIds] = useState([]);
  const [qaDocumentsList, setQaDocumentsList] = useState([]); // full list for "Specific documents" selector
  const [qaDocumentsLoading, setQaDocumentsLoading] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState({}); // { 'chatId-messageIndex': true } to avoid double submit
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  // Chat widget tab
  const [widgetKey, setWidgetKey] = useState('');
  const [widgetConfigLoading, setWidgetConfigLoading] = useState(false);
  
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

  // Ticket lifecycle: notes dialog + per-row busy flag
  const [notesDialog, setNotesDialog] = useState({ open: false, ticketId: null, ticketTitle: '', notes: [], loading: false });
  const [noteDraft, setNoteDraft] = useState('');
  const [ticketBusyId, setTicketBusyId] = useState(null);
  // Customer 360 panel — shows contact info, prior ticket count, and recent tickets for the ticket's customer
  const [customerDialog, setCustomerDialog] = useState({
    open: false, ticketId: null, ticketTitle: '',
    loading: false, contact: null, stats: null,
  });
  const [ticketFilters, setTicketFilters] = useState({ status: '', priority: '', category: '', date_from: '', date_to: '' });
  const [ticketsPagination, setTicketsPagination] = useState({ page: 1, limit: 20, total: 0, total_pages: 1 });
  const [ticketsAging, setTicketsAging] = useState(null); // { breached: [], at_risk: [], count_breached, count_at_risk }

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

  // Load widget config when Chat widget tab is selected
  useEffect(() => {
    if (activeTab !== 'widget') return;
    let cancelled = false;
    setWidgetConfigLoading(true);
    frontlineAgentService.getFrontlineWidgetConfig()
      .then((res) => {
        if (!cancelled && res?.status === 'success' && res?.data?.widget_key) setWidgetKey(res.data.widget_key);
      })
      .catch(() => { if (!cancelled) setWidgetKey(''); })
      .finally(() => { if (!cancelled) setWidgetConfigLoading(false); });
    return () => { cancelled = true; };
  }, [activeTab]);

  // Load document list for Q&A scope when user selects "Specific documents"
  useEffect(() => {
    if (qaScopeMode !== 'documents') return;
    let cancelled = false;
    (async () => {
      setQaDocumentsLoading(true);
      try {
        const res = await frontlineAgentService.listDocuments({ limit: 200 });
        const list = res?.data?.documents ?? (Array.isArray(res?.data) ? res.data : []);
        if (!cancelled) setQaDocumentsList(list);
      } catch {
        if (!cancelled) setQaDocumentsList([]);
      } finally {
        if (!cancelled) setQaDocumentsLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [qaScopeMode]);

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

  const loadTicketsAging = async () => {
    try {
      const res = await frontlineAgentService.listTicketsAging();
      if (res.status === 'success' && res.data) setTicketsAging(res.data);
      else setTicketsAging(null);
    } catch {
      setTicketsAging(null);
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
      loadTicketsAging();
    }
  }, [activeTab, ticketFilters.status, ticketFilters.priority, ticketFilters.category, ticketFilters.date_from, ticketFilters.date_to, ticketsPagination.page]);

  // ---------- Ticket lifecycle handlers (notes / snooze / SLA / re-triage) ----------
  const openNotesDialog = async (ticket) => {
    setNotesDialog({ open: true, ticketId: ticket.id, ticketTitle: ticket.title, notes: [], loading: true });
    setNoteDraft('');
    try {
      const res = await frontlineAgentService.listTicketNotes(ticket.id);
      setNotesDialog((prev) => ({ ...prev, notes: res?.data || [], loading: false }));
    } catch (err) {
      console.error('Load notes failed', err);
      setNotesDialog((prev) => ({ ...prev, loading: false }));
      toast({ title: 'Failed to load notes', variant: 'destructive' });
    }
  };

  const submitNote = async () => {
    const body = noteDraft.trim();
    if (!body || !notesDialog.ticketId) return;
    try {
      const res = await frontlineAgentService.createTicketNote(notesDialog.ticketId, body, true);
      setNotesDialog((prev) => ({ ...prev, notes: [...prev.notes, res.data] }));
      setNoteDraft('');
      // Bump the row's notes_count in the table
      setTicketsList((list) => list.map((t) => (t.id === notesDialog.ticketId
        ? { ...t, notes_count: (t.notes_count || 0) + 1 }
        : t)));
    } catch (err) {
      console.error('Add note failed', err);
      toast({ title: 'Failed to add note', variant: 'destructive' });
    }
  };

  const deleteNote = async (noteId) => {
    try {
      await frontlineAgentService.deleteTicketNote(notesDialog.ticketId, noteId);
      setNotesDialog((prev) => ({ ...prev, notes: prev.notes.filter((n) => n.id !== noteId) }));
      setTicketsList((list) => list.map((t) => (t.id === notesDialog.ticketId
        ? { ...t, notes_count: Math.max(0, (t.notes_count || 0) - 1) }
        : t)));
    } catch (err) {
      console.error('Delete note failed', err);
      toast({ title: 'Failed to delete note', variant: 'destructive' });
    }
  };

  // Customer 360: fetch contact + stats for a ticket; backend 404s if ticket has no contact yet.
  const openCustomerDialog = async (ticket) => {
    setCustomerDialog({
      open: true, ticketId: ticket.id, ticketTitle: ticket.title,
      loading: true, contact: null, stats: null,
    });
    try {
      const res = await frontlineAgentService.getTicketContext(ticket.id);
      const data = res?.data || {};
      setCustomerDialog((prev) => ({
        ...prev,
        loading: false,
        contact: data.contact || null,
        stats: data.stats || null,
      }));
    } catch (err) {
      console.error('Load customer context failed', err);
      setCustomerDialog((prev) => ({ ...prev, loading: false }));
      toast({ title: 'Failed to load customer context', variant: 'destructive' });
    }
  };

  const handleSnooze = async (ticket, hours) => {
    setTicketBusyId(ticket.id);
    try {
      const res = await frontlineAgentService.snoozeTicket(ticket.id, { hours });
      setTicketsList((list) => list.map((t) => (t.id === ticket.id
        ? { ...t, snoozed_until: res.data.snoozed_until, is_snoozed: true }
        : t)));
      toast({ title: `Ticket snoozed for ${hours}h` });
    } catch (err) {
      toast({ title: 'Snooze failed', variant: 'destructive' });
    } finally {
      setTicketBusyId(null);
    }
  };

  const handleUnsnooze = async (ticket) => {
    setTicketBusyId(ticket.id);
    try {
      await frontlineAgentService.unsnoozeTicket(ticket.id);
      setTicketsList((list) => list.map((t) => (t.id === ticket.id
        ? { ...t, snoozed_until: null, is_snoozed: false }
        : t)));
      toast({ title: 'Ticket unsnoozed' });
    } catch (err) {
      toast({ title: 'Unsnooze failed', variant: 'destructive' });
    } finally {
      setTicketBusyId(null);
    }
  };

  const handleToggleSlaPause = async (ticket) => {
    setTicketBusyId(ticket.id);
    try {
      const fn = ticket.is_sla_paused ? frontlineAgentService.resumeTicketSla : frontlineAgentService.pauseTicketSla;
      const res = await fn(ticket.id);
      setTicketsList((list) => list.map((t) => (t.id === ticket.id ? {
        ...t,
        sla_paused_at: res.data.sla_paused_at || null,
        is_sla_paused: !!res.data.sla_paused_at,
        sla_due_at: res.data.sla_due_at ?? t.sla_due_at,
      } : t)));
      toast({ title: ticket.is_sla_paused ? 'SLA resumed' : 'SLA paused' });
    } catch (err) {
      toast({ title: 'SLA toggle failed', variant: 'destructive' });
    } finally {
      setTicketBusyId(null);
    }
  };

  const handleRetriage = async (ticket) => {
    setTicketBusyId(ticket.id);
    try {
      const res = await frontlineAgentService.retriageTicket(ticket.id);
      const { new_category, new_priority } = res.data || {};
      setTicketsList((list) => list.map((t) => (t.id === ticket.id ? {
        ...t,
        category: new_category ?? t.category,
        priority: new_priority ?? t.priority,
        last_triaged_at: res.data.last_triaged_at ?? t.last_triaged_at,
      } : t)));
      toast({ title: 'Re-triage complete', description: `Category: ${new_category}, Priority: ${new_priority}` });
    } catch (err) {
      toast({ title: 'Re-triage failed', variant: 'destructive' });
    } finally {
      setTicketBusyId(null);
    }
  };

  const selectedChat = chats.find((c) => c.id === selectedChatId);
  const currentMessages = selectedChat?.messages ?? [];
  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  const currentTab = FRONTLINE_TAB_ITEMS.find((item) => item.value === activeTab) || FRONTLINE_TAB_ITEMS[0];

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
    const scopeOptions = {};
    if (qaScopeMode === 'type' && qaScopeDocumentTypes.length > 0) scopeOptions.scope_document_type = qaScopeDocumentTypes;
    if (qaScopeMode === 'documents' && qaScopeDocumentIds.length > 0) scopeOptions.scope_document_ids = qaScopeDocumentIds;
    try {
      setAnswering(true);
      const userMsg = { role: 'user', content: q };
      let assistantMsg;

      if (inputMode === 'graph') {
        const graphRes = await frontlineAgentService.generateFrontlineGraph(q);
        if (graphRes.status === 'success' && graphRes.data) {
          const { chart, insights } = graphRes.data;
          assistantMsg = {
            role: 'assistant',
            content: chart?.title ? `**${chart.title}**` : 'Chart generated',
            responseData: {
              isGraph: true,
              chart,
              insights,
              chartTitle: chart?.title,
              chartType: chart?.type,
            },
          };
        } else {
          throw new Error(graphRes.message || 'Failed to generate graph');
        }
      } else {
        const response = await frontlineAgentService.knowledgeQA(q, scopeOptions);
        if (response.status === 'success' && response.data) {
          const data = response.data;
          const answerText = data.answer || 'No answer available.';
          assistantMsg = {
            role: 'assistant',
            content: answerText,
            responseData: {
              answer: answerText,
              has_verified_info: data.has_verified_info || false,
              source: data.source || 'Knowledge Base',
              type: data.type || 'general',
              document_id: data.document_id ?? null,
            },
          };
        } else {
          throw new Error(response.message || 'Failed to get response');
        }
      }

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
        if (activeTab === 'tickets') { loadTickets(); loadTicketsAging(); }
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
    <div
      className="w-full rounded-2xl border border-white/[0.06] p-0"
      style={{ background: 'linear-gradient(90deg, #020308 0%, #020308 55%, rgba(10,37,64,0.68) 85%, rgba(14,39,71,0.52) 100%)' }}
    >
    <div className="space-y-6 w-full max-w-full overflow-x-hidden p-4 md:p-6 lg:p-8">
      {/* Stats Overview */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6 sm:mb-8 w-full">
        {[
          {
            label: 'Total Documents',
            value: stats?.total_documents || 0,
            sub: `${stats?.indexed_documents || 0} indexed`,
            icon: FileText,
            color: '#a78bfa',
            bgColor: 'rgba(167,139,250,0.2)',
            borderColor: 'rgba(167,139,250,0.2)',
            gradientFrom: 'rgba(167,139,250,0.2)',
            gradientTo: 'rgba(147,51,234,0.1)',
          },
          {
            label: 'Total Tickets',
            value: stats?.total_tickets || 0,
            sub: `${stats?.open_tickets || 0} open`,
            icon: Ticket,
            color: '#34d399',
            bgColor: 'rgba(52,211,153,0.2)',
            borderColor: 'rgba(52,211,153,0.2)',
            gradientFrom: 'rgba(52,211,153,0.2)',
            gradientTo: 'rgba(22,163,74,0.1)',
          },
          {
            label: 'Resolved',
            value: stats?.resolved_tickets || 0,
            sub: 'Successfully resolved',
            icon: CheckCircle2,
            color: '#fbbf24',
            bgColor: 'rgba(251,191,36,0.2)',
            borderColor: 'rgba(251,191,36,0.2)',
            gradientFrom: 'rgba(251,191,36,0.15)',
            gradientTo: 'rgba(245,158,11,0.08)',
          },
          {
            label: 'Auto-Resolved',
            value: stats?.auto_resolved_tickets || 0,
            sub: 'Resolved automatically',
            icon: Sparkles,
            color: '#60a5fa',
            bgColor: 'rgba(96,165,250,0.2)',
            borderColor: 'rgba(96,165,250,0.2)',
            gradientFrom: 'rgba(96,165,250,0.2)',
            gradientTo: 'rgba(34,211,238,0.1)',
          },
        ].map((card) => (
          <div
            key={card.label}
            className="relative group w-full min-w-0 rounded-xl backdrop-blur-sm p-5 transition-all duration-300 hover:scale-[1.02] hover:shadow-lg"
            style={{
              border: `1px solid ${card.borderColor}`,
              background: `linear-gradient(135deg, ${card.gradientFrom} 0%, ${card.gradientTo} 100%)`,
            }}
          >
            <div className="flex items-start justify-between mb-3">
              <div className="rounded-lg p-2.5" style={{ backgroundColor: card.bgColor }}>
                <card.icon className="h-5 w-5" style={{ color: card.color }} />
              </div>
            </div>
            <div className="space-y-1">
              <p className="text-sm font-medium text-white/50 tracking-wide">{card.label}</p>
              <p className="text-3xl font-bold text-white tracking-tight">{card.value}</p>
              <p className="text-xs text-white/40">{card.sub}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Main Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full space-y-4">
        {/* Mobile & Tablet: Hamburger menu (below lg) */}
        <div className="lg:hidden w-full mb-4">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" className="w-full justify-between h-11 border-[#3a295a] bg-[#1a1333] text-white/80 hover:bg-[#231845] hover:text-white">
                <div className="flex items-center gap-2 min-w-0">
                  <currentTab.icon className="h-4 w-4 shrink-0 text-violet-400" />
                  <span className="font-medium truncate">{currentTab.label}</span>
                </div>
                <Menu className="h-5 w-5 text-white/40 shrink-0" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-[calc(100vw-2rem)] max-w-sm max-h-[60vh] overflow-y-auto border-[#3a295a] bg-[#161630]">
              {FRONTLINE_TAB_ITEMS.map((item) => {
                const isActive = item.value === activeTab;
                const ItemIcon = item.icon;
                return (
                  <DropdownMenuItem
                    key={item.value}
                    onClick={() => setActiveTab(item.value)}
                    className={`flex items-center justify-between py-3 cursor-pointer ${isActive ? 'bg-violet-600/20' : 'hover:bg-white/5'}`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <ItemIcon className={`h-4 w-4 shrink-0 ${isActive ? 'text-violet-400' : 'text-white/40'}`} />
                      <span className={isActive ? 'font-medium text-violet-300' : 'text-white/70'}>{item.label}</span>
                    </div>
                    {isActive && <Check className="h-4 w-4 text-violet-400 shrink-0" />}
                  </DropdownMenuItem>
                );
              })}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {/* Desktop: Regular tabs (lg and above) with horizontal scroll */}
        <div className="hidden lg:block overflow-x-auto pb-1">
          <TabsList
            className="inline-flex w-max min-w-full h-auto p-1 gap-1 rounded-lg bg-[#1a1333] border border-[#3a295a]"
            style={{ boxShadow: '0 2px 12px 0 #a259ff0a' }}
          >
            {FRONTLINE_TAB_ITEMS.map((item) => {
              const TabIcon = item.icon;
              return (
                <TabsTrigger
                  key={item.value}
                  value={item.value}
                  className="whitespace-nowrap shrink-0 px-4 py-2 text-sm font-medium rounded-md border transition-all duration-150"
                  style={activeTab === item.value
                    ? {
                        background: 'linear-gradient(90deg, #a259ff 0%, #7c3aed 100%)',
                        color: '#fff',
                        border: '1.5px solid #a259ff',
                        boxShadow: '0 0 8px 0 #a259ff55',
                      }
                    : {
                        background: 'rgba(60, 30, 90, 0.22)',
                        color: '#cfc6e6',
                        border: '1.5px solid #2d2342',
                        boxShadow: 'none',
                      }
                  }
                >
                  <TabIcon className="h-4 w-4 mr-2" />
                  {item.label}
                </TabsTrigger>
              );
            })}
          </TabsList>
        </div>

        {/* Overview Tab */}
        <TabsContent value="overview" className="mt-6">
          <ErrorBoundary>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-6 w-full min-w-0">
            {[
              {
                title: 'Documents',
                desc: 'Upload and manage knowledge base documents for AI-powered answers',
                icon: FileText,
                tab: 'documents',
                color: '#a78bfa',
                bgColor: 'rgba(167,139,250,0.15)',
                borderHover: 'rgba(167,139,250,0.4)',
              },
              {
                title: 'Knowledge Q&A',
                desc: 'Ask questions and get AI-powered answers from your knowledge base',
                icon: MessageSquare,
                tab: 'qa',
                color: '#34d399',
                bgColor: 'rgba(52,211,153,0.15)',
                borderHover: 'rgba(52,211,153,0.4)',
              },
              {
                title: 'Tickets',
                desc: 'Manage support tickets with AI auto-resolution and prioritization',
                icon: Ticket,
                tab: 'tickets',
                color: '#60a5fa',
                bgColor: 'rgba(96,165,250,0.15)',
                borderHover: 'rgba(96,165,250,0.4)',
              },
              {
                title: 'Chat Widget',
                desc: 'Configure and embed a customer-facing chat widget on your site',
                icon: Monitor,
                tab: 'widget',
                color: '#fbbf24',
                bgColor: 'rgba(251,191,36,0.15)',
                borderHover: 'rgba(251,191,36,0.4)',
              },
              {
                title: 'Workflows',
                desc: 'Set up automated workflows for ticket routing and notifications',
                icon: GitBranch,
                tab: 'workflows',
                color: '#2dd4bf',
                bgColor: 'rgba(45,212,191,0.15)',
                borderHover: 'rgba(45,212,191,0.4)',
              },
              {
                title: 'Analytics',
                desc: 'View ticket trends, performance metrics, and AI-generated graphs',
                icon: BarChart3,
                tab: 'analytics',
                color: '#f472b6',
                bgColor: 'rgba(244,114,182,0.15)',
                borderHover: 'rgba(244,114,182,0.4)',
              },
            ].map((card) => (
              <button
                key={card.title}
                onClick={() => setActiveTab(card.tab)}
                className="group relative flex flex-col items-start gap-3 rounded-xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-sm p-5 text-left transition-all duration-300 hover:bg-white/[0.06] cursor-pointer w-full min-w-0"
                onMouseEnter={(e) => e.currentTarget.style.borderColor = card.borderHover}
                onMouseLeave={(e) => e.currentTarget.style.borderColor = ''}
              >
                <div className="rounded-lg p-2.5" style={{ backgroundColor: card.bgColor }}>
                  <card.icon className="h-5 w-5" style={{ color: card.color }} />
                </div>
                <div>
                  <p className="font-semibold text-sm text-white group-hover:text-white transition-colors">{card.title}</p>
                  <p className="text-xs text-white/40 mt-1 leading-relaxed">{card.desc}</p>
                </div>
              </button>
            ))}
          </div>

          {/* Recent Documents */}
          {documents.length > 0 && (
            <div className="mt-6 rounded-xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-sm p-5">
              <h3 className="text-sm font-semibold text-white mb-3">Recent Documents</h3>
              <div className="space-y-2">
                {documents.slice(0, 5).map((doc) => (
                  <div key={doc.id} className="flex items-center justify-between p-2 rounded-lg border border-white/[0.06] bg-white/[0.02]">
                    <div className="flex items-center space-x-2 min-w-0">
                      <FileText className="h-4 w-4 text-white/40 shrink-0" />
                      <span className="text-sm text-white/70 truncate">{doc.title}</span>
                      {doc.is_indexed && (
                        <span className="text-xs text-emerald-400">Indexed</span>
                      )}
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-white/30 hover:text-white/60 shrink-0"
                      onClick={() => handleDeleteDocument(doc.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          )}
          </ErrorBoundary>
        </TabsContent>

        {/* Documents Tab */}
        <TabsContent value="documents" className="space-y-4 mt-4">
          <ErrorBoundary>
          <Card className="w-full min-w-0">
            <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div className="min-w-0">
                <CardTitle>Documents</CardTitle>
                <CardDescription>Upload and manage knowledge base documents</CardDescription>
              </div>
              <Button onClick={() => setShowUploadDialog(true)} className="w-full sm:w-auto shrink-0">
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
                    <div key={doc.id} className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 p-3 border rounded">
                      <div className="flex items-center space-x-3 min-w-0">
                        <FileText className="h-5 w-5 shrink-0" />
                        <div className="min-w-0">
                          <div className="font-medium truncate">{doc.title}</div>
                          <div className="text-sm text-muted-foreground">
                            {doc.file_format.toUpperCase()} • {doc.document_type}
                            {doc.is_indexed && ' • Indexed'}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-1 shrink-0 self-end sm:self-center">
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
          </ErrorBoundary>
        </TabsContent>

        {/* Knowledge Q&A Tab - Chat UI with sidebar */}
        <TabsContent value="qa" className="space-y-4 mt-4">
          <ErrorBoundary>
          <div
            className="w-full rounded-2xl border border-white/[0.06] p-0 overflow-hidden"
            style={{
              background:
                'linear-gradient(90deg, #020308 0%, #020308 55%, rgba(10,37,64,0.68) 85%, rgba(14,39,71,0.52) 100%)',
            }}
          >
            <div className="flex w-full max-w-full relative">
              <div
                className={`shrink-0 rounded-xl border border-white/15 shadow-[0_2px_24px_0_rgba(80,36,180,0.18)] backdrop-blur-lg overflow-hidden transition-all duration-300 ease-in-out ${
                  showChatHistory ? 'w-64 opacity-100 mr-4' : 'w-0 opacity-0 border-0 mr-0'
                }`}
                style={{
                  minWidth: showChatHistory ? '16rem' : '0',
                  background: 'linear-gradient(90deg, rgba(139,92,246,0.13) 0%, rgba(36,18,54,0.18) 18%, #0a0a0f 55%, #0a0a0f 100%)',
                  borderRight: '1.5px solid rgba(255,255,255,0.10)',
                  boxShadow: '0 2px 24px 0 rgba(80, 36, 180, 0.18), 0 0 0 1.5px rgba(120, 80, 255, 0.10) inset',
                  borderTopLeftRadius: 16,
                  borderBottomLeftRadius: 16,
                  backdropFilter: 'blur(12px)',
                  WebkitBackdropFilter: 'blur(12px)',
                  overflow: 'hidden',
                }}
              >
                <div className="w-64">
                  <div
                    className="px-3 pt-3 pb-2 border-b border-white/15 flex flex-col gap-2"
                    style={{
                      background: 'linear-gradient(180deg, rgba(60, 30, 90, 0.22) 0%, rgba(36, 18, 54, 0.85) 100%)',
                      borderTopLeftRadius: 16,
                    }}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-base font-semibold text-white/90 tracking-wide">Frontline</span>
                      <button
                        onClick={() => setShowChatHistory(false)}
                        title="Close sidebar"
                        className="h-8 w-8 flex items-center justify-center rounded-full border border-white/20 hover:border-violet-400/60 bg-black/30 hover:bg-violet-700/20 transition-all duration-150"
                        style={{ boxShadow: '0 0 0 2px rgba(139,92,246,0.10) inset' }}
                      >
                        <ChevronLeft className="h-4 w-4 text-white/80" />
                      </button>
                    </div>

                    {showSidebarSearch ? (
                      <div
                        className="flex items-center gap-2 px-2 py-1.5 rounded-lg w-full"
                        style={{
                          border: '1.5px solid rgba(139,92,246,0.22)',
                          background: 'linear-gradient(90deg, rgba(80,36,180,0.10) 0%, rgba(36,18,54,0.18) 100%)',
                          boxShadow: '0 1px 8px 0 rgba(139,92,246,0.08) inset',
                          backdropFilter: 'blur(4px)',
                          WebkitBackdropFilter: 'blur(4px)',
                        }}
                      >
                        <input
                          autoFocus
                          value={sidebarSearch}
                          onChange={(e) => setSidebarSearch(e.target.value)}
                          placeholder="Search conversations..."
                          className="flex-1 bg-transparent outline-none border-0 text-white/90 text-sm px-2 py-1.5 placeholder-white/40"
                          style={{ minWidth: 0 }}
                        />
                        <button
                          title="Close search"
                          onClick={() => {
                            setSidebarSearch('');
                            setShowSidebarSearch(false);
                          }}
                          className="h-7 w-7 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60 bg-black/20 hover:bg-violet-700/20 transition-all duration-150"
                        >
                          <svg
                            width="16"
                            height="16"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            className="text-white/70"
                          >
                            <line x1="4" y1="4" x2="12" y2="12" />
                            <line x1="12" y1="4" x2="4" y2="12" />
                          </svg>
                        </button>
                      </div>
                    ) : (
                      <div
                        className="flex items-center gap-2 px-2 py-1.5 rounded-lg w-full"
                        style={{
                          border: '1.5px solid rgba(139,92,246,0.22)',
                          background: 'linear-gradient(90deg, rgba(80,36,180,0.10) 0%, rgba(36,18,54,0.18) 100%)',
                          boxShadow: '0 1px 8px 0 rgba(139,92,246,0.08) inset',
                          backdropFilter: 'blur(4px)',
                          WebkitBackdropFilter: 'blur(4px)',
                        }}
                      >
                        <span className="text-sm font-medium text-white/80 flex-1">Conversation</span>
                        <button
                          title="Search"
                          onClick={() => setShowSidebarSearch(true)}
                          className="h-7 w-7 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60 bg-black/20 hover:bg-violet-700/20 transition-all duration-150"
                        >
                          <svg
                            width="16"
                            height="16"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            className="text-white/70"
                          >
                            <circle cx="7" cy="7" r="5" />
                            <line x1="15" y1="15" x2="11" y2="11" />
                          </svg>
                        </button>
                        <button
                          onClick={newChat}
                          title="New chat"
                          className="h-7 w-7 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60 bg-black/20 hover:bg-violet-700/20 transition-all duration-150"
                        >
                          <Plus className="h-4 w-4 text-white/80" />
                        </button>
                      </div>
                    )}
                  </div>

                  <div>
                    {loadingChats ? (
                      <div className="p-4 flex justify-center">
                        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                      </div>
                    ) : chats.length === 0 ? (
                      <div className="p-4 text-center text-sm text-muted-foreground">No conversations yet. Ask a question to start.</div>
                    ) : (
                      <div
                        className="p-2 space-y-1"
                        style={{
                          background: 'linear-gradient(180deg, rgba(36, 18, 54, 0.10) 0%, rgba(24, 18, 43, 0.18) 100%)',
                          borderRadius: 12,
                        }}
                      >
                        {(() => {
                          const searchTerm = sidebarSearch.trim().toLowerCase();
                          const filteredChats = searchTerm
                            ? chats.filter((c) => {
                                const title = (c.title || c.messages?.[0]?.content || '').toLowerCase();
                                const messagesMatch = (c.messages || []).some((m) => (m.content || '').toLowerCase().includes(searchTerm));
                                return title.includes(searchTerm) || messagesMatch;
                              })
                            : chats;

                          if (searchTerm && filteredChats.length === 0) {
                            return <div className="p-4 text-center text-sm text-muted-foreground">No matching conversations found.</div>;
                          }

                          return filteredChats.map((c) => (
                            <div
                              key={c.id}
                              className={`flex items-center gap-1 rounded-lg border text-sm transition-all duration-200 ${
                                selectedChatId === c.id
                                  ? 'border-violet-500/60 bg-gradient-to-r from-violet-900/40 to-violet-700/20 shadow-[0_0_12px_rgba(139,92,246,0.18)]'
                                  : 'border-white/10 bg-white/2 hover:bg-white/5 hover:border-violet-400/20'
                              }`}
                              style={{
                                boxShadow:
                                  selectedChatId === c.id
                                    ? '0 0 12px 0 rgba(139,92,246,0.18), 0 1.5px 0 0 rgba(120,80,255,0.10) inset'
                                    : '0 1px 2px 0 rgba(36,18,54,0.08) inset',
                                borderWidth: 1.5,
                              }}
                            >
                              <button
                                type="button"
                                onClick={() => setSelectedChatId(c.id)}
                                className="flex-1 min-w-0 text-left p-3 rounded-lg"
                              >
                                <div className={`font-medium truncate ${selectedChatId === c.id ? 'text-violet-300' : ''}`}>
                                  {truncate(c.title || c.messages?.[0]?.content || 'Chat', 40)}
                                </div>
                                <div className={`text-xs mt-0.5 ${selectedChatId === c.id ? 'text-violet-400/70' : 'text-muted-foreground'}`}>
                                  {formatDate(c.updatedAt || c.timestamp)}
                                </div>
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
                          ));
                        })()}
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <Card className="flex-1 min-w-0 flex flex-col max-h-[calc(100vh-40px)] border-0 shadow-none" style={{ background: 'transparent' }}>
                <CardHeader
                  className="shrink-0 flex flex-row items-start justify-between gap-3 border-b border-white/[0.07] px-0 py-4"
                  style={{ background: 'transparent' }}
                >
                  <div className="flex items-center gap-3 min-w-0 w-full">
                    <div
                      style={{
                        width: '7px',
                        height: '48px',
                        borderRadius: '8px',
                        background: 'linear-gradient(to bottom, #a259ff 0%, #6a1b9a 60%, #18122B 100%)',
                        marginLeft: '24px',
                        marginRight: '18px',
                        boxShadow: '0 0 8px 2px #a259ff44',
                      }}
                    />
                    <div className="h-10 w-10 rounded-lg flex items-center justify-center shrink-0" style={{ background: 'rgba(124, 58, 237, 0.15)' }}>
                      <Bot className="h-5 w-5" style={{ color: '#a78bfa' }} />
                    </div>
                    <div className="min-w-0">
                      <CardTitle className="flex items-center gap-2 truncate text-white text-lg">
                        Knowledge Q&A
                        <span
                          className="text-[10px] rounded-full px-2.5 py-0.5 font-medium"
                          style={{ background: 'rgba(124, 58, 237, 0.15)', color: '#a78bfa' }}
                        >
                          AI-Powered
                        </span>
                      </CardTitle>
                      <CardDescription className="text-white/50 text-sm mt-0.5">
                        Ask questions and get answers from your knowledge base and uploaded documents.
                      </CardDescription>
                    </div>
                  </div>

                  <Button
                    variant={showChatHistory ? 'ghost' : 'outline'}
                    size="sm"
                    onClick={() => setShowChatHistory((v) => !v)}
                    title={showChatHistory ? 'Hide chat history' : 'Show chat history'}
                    className={`gap-1.5 transition-all duration-200 ${
                      !showChatHistory
                        ? 'bg-primary/5 hover:bg-primary/10 border-primary/20 text-primary'
                        : 'hover:bg-muted'
                    }`}
                    style={{ marginRight: '24px' }}
                  >
                    {showChatHistory ? (
                      <>
                        <ChevronLeft className="h-4 w-4" />
                        <span className="text-xs hidden sm:inline">Hide</span>
                      </>
                    ) : (
                      <>
                        <ChevronRight className="h-4 w-4" />
                        <span className="text-xs hidden sm:inline">History</span>
                      </>
                    )}
                  </Button>
                </CardHeader>

                <CardContent className="p-0 flex flex-col flex-1 min-h-0">
                  <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-4 py-4 space-y-4">
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
                        ) : msg.responseData?.isGraph ? (
                          <>
                            <div className="space-y-3">
                              {msg.responseData.chart && (
                                <div className="relative w-full rounded-xl border border-border bg-card p-2 shadow-sm">
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="icon"
                                    className="absolute top-1.5 right-1.5 h-7 w-7 rounded-md opacity-70 hover:opacity-100 text-muted-foreground hover:text-foreground"
                                    onClick={() => setExpandedGraph({ chart: msg.responseData.chart, chartTitle: msg.responseData.chartTitle })}
                                    title="Expand graph"
                                  >
                                    <Maximize2 className="h-3.5 w-3.5" />
                                  </Button>
                                  <div className="pr-8 w-full min-w-0">
                                    {renderChart(msg.responseData.chart)}
                                  </div>
                                </div>
                              )}
                              {msg.responseData?.insights && (
                                <div className="pt-2 border-t border-border/50">
                                  <p className="text-xs font-semibold mb-2">Insights</p>
                                  <p className="text-xs text-muted-foreground whitespace-pre-wrap">{msg.responseData.insights}</p>
                                </div>
                              )}
                            </div>
                          </>
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
                                {msg.responseData?.confidence === 'low' && (
                                  <div className="mt-2 text-xs rounded-md px-2 py-1 bg-yellow-500/10 text-yellow-700 dark:text-yellow-400 border border-yellow-500/30">
                                    Low-confidence match{typeof msg.responseData?.best_score === 'number' ? ` (score ${msg.responseData.best_score})` : ''}. Consider escalating to a human agent.
                                  </div>
                                )}
                                {msg.responseData?.rewritten_query && (
                                  <div className="mt-2 text-xs text-muted-foreground italic">
                                    Interpreted as: "{msg.responseData.rewritten_query}"
                                  </div>
                                )}
                                {msg.responseData?.citations?.length ? (
                                  <div className="mt-3 pt-2 border-t border-border/50 space-y-2">
                                    <p className="text-xs font-medium text-muted-foreground">Sources</p>
                                    <ol className="space-y-1.5 text-xs text-muted-foreground list-decimal list-inside">
                                      {msg.responseData.citations.map((c, idx) => (
                                        <li key={`${c.document_id || 'src'}-${c.chunk_id || idx}`} className="break-words">
                                          <span className="font-medium text-foreground">{c.title || c.source || 'Source'}</span>
                                          {typeof c.score === 'number' && (
                                            <span className="ml-1 text-[10px] opacity-70">({c.score})</span>
                                          )}
                                          {c.snippet && (
                                            <span className="block mt-0.5 opacity-80 whitespace-pre-wrap">{c.snippet}{c.snippet.length >= 200 ? '…' : ''}</span>
                                          )}
                                        </li>
                                      ))}
                                    </ol>
                                  </div>
                                ) : (msg.responseData?.source ? (
                                  <p className="text-xs text-muted-foreground mt-2">Source: {msg.responseData.source}</p>
                                ) : null)}
                                <div className="flex items-center gap-1 mt-2 pt-2 border-t border-border/50">
                                  <span className="text-xs text-muted-foreground mr-1">Was this helpful?</span>
                                  {feedbackSent[`${selectedChatId}-${i}`] ? (
                                    <span className="text-xs text-muted-foreground">Thank you for feedback.</span>
                                  ) : (
                                    <>
                                      <Button
                                        type="button"
                                        variant="ghost"
                                        size="icon"
                                        className="h-8 w-8"
                                        disabled={feedbackSubmitting}
                                        onClick={async () => {
                                          const questionText = currentMessages[i - 1]?.content || '';
                                          if (!questionText) return;
                                          setFeedbackSubmitting(true);
                                          try {
                                            await frontlineAgentService.submitKnowledgeFeedback({
                                              question: questionText,
                                              helpful: true,
                                              document_id: msg.responseData?.document_id ?? undefined,
                                            });
                                            setFeedbackSent((prev) => ({ ...prev, [`${selectedChatId}-${i}`]: true }));
                                          } catch {
                                            toast({ title: 'Error', description: 'Could not send feedback', variant: 'destructive' });
                                          } finally {
                                            setFeedbackSubmitting(false);
                                          }
                                        }}
                                        title="Yes, helpful"
                                      >
                                        <ThumbsUp className="h-4 w-4" />
                                      </Button>
                                      <Button
                                        type="button"
                                        variant="ghost"
                                        size="icon"
                                        className="h-8 w-8"
                                        disabled={feedbackSubmitting}
                                        onClick={async () => {
                                          const questionText = currentMessages[i - 1]?.content || '';
                                          if (!questionText) return;
                                          setFeedbackSubmitting(true);
                                          try {
                                            await frontlineAgentService.submitKnowledgeFeedback({
                                              question: questionText,
                                              helpful: false,
                                              document_id: msg.responseData?.document_id ?? undefined,
                                            });
                                            setFeedbackSent((prev) => ({ ...prev, [`${selectedChatId}-${i}`]: true }));
                                          } catch {
                                            toast({ title: 'Error', description: 'Could not send feedback', variant: 'destructive' });
                                          } finally {
                                            setFeedbackSubmitting(false);
                                          }
                                        }}
                                        title="No, not helpful"
                                      >
                                        <ThumbsDown className="h-4 w-4" />
                                      </Button>
                                    </>
                                  )}
                                </div>
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

                  <form
                    onSubmit={handleAskQuestion}
                    className="shrink-0"
                    style={{
                      background: '#0a0a0f',
                      borderTop: '1px solid rgba(255,255,255,0.08)',
                    }}
                  >
                    <div className="mx-4 my-4 space-y-3 rounded-2xl px-4 py-4" style={{ border: '1px solid rgba(255,255,255,0.08)' }}>
                      <div className="space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm text-muted-foreground">Answer from:</span>
                          <Select
                            value={qaScopeMode}
                            onValueChange={(v) => {
                              setQaScopeMode(v);
                              if (v !== 'type') setQaScopeDocumentTypes([]);
                              if (v !== 'documents') setQaScopeDocumentIds([]);
                            }}
                          >
                            <SelectTrigger className="w-[180px] h-8">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="all">All documents</SelectItem>
                              <SelectItem value="type">By document type</SelectItem>
                              <SelectItem value="documents">Specific documents</SelectItem>
                            </SelectContent>
                          </Select>

                          {qaScopeMode === 'type' && (
                            <div className="flex flex-wrap items-center gap-2">
                              {DOCUMENT_TYPE_OPTIONS.map((opt) => (
                                <label key={opt.value} className="flex items-center gap-1.5 text-sm cursor-pointer">
                                  <Checkbox
                                    checked={qaScopeDocumentTypes.includes(opt.value)}
                                    onCheckedChange={(checked) => {
                                      setQaScopeDocumentTypes((prev) =>
                                        checked ? [...prev, opt.value] : prev.filter((t) => t !== opt.value)
                                      );
                                    }}
                                  />
                                  <span>{opt.label}</span>
                                </label>
                              ))}
                            </div>
                          )}

                          {qaScopeMode === 'documents' && (
                            <Select
                              value="_add"
                              onValueChange={(v) => {
                                if (v === '_add' || v === '_none') return;
                                const id = Number(v);
                                if (!qaScopeDocumentIds.includes(id)) setQaScopeDocumentIds((prev) => [...prev, id]);
                              }}
                            >
                              <SelectTrigger className="w-[220px] h-8">
                                <SelectValue
                                  placeholder={qaDocumentsLoading
                                    ? 'Loading...'
                                    : qaScopeDocumentIds.length
                                      ? 'Add another document...'
                                      : 'Add document...'
                                  }
                                />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="_add">Add document...</SelectItem>
                                {!qaDocumentsLoading &&
                                  qaDocumentsList
                                    .filter((d) => !qaScopeDocumentIds.includes(d.id))
                                    .map((d) => (
                                      <SelectItem key={d.id} value={String(d.id)}>
                                        {d.title || `Document ${d.id}`}
                                      </SelectItem>
                                    ))}
                              </SelectContent>
                            </Select>
                          )}
                        </div>

                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm text-muted-foreground">Mode:</span>
                          <Select value={inputMode} onValueChange={setInputMode}>
                            <SelectTrigger className="w-[180px] h-8">
                              <div className="flex items-center gap-2">
                                <SelectedModeIcon className="h-4 w-4" />
                                <SelectValue placeholder="Search" />
                              </div>
                            </SelectTrigger>
                            <SelectContent>
                              {INPUT_MODE_OPTIONS.map((mode) => {
                                const ModeIcon = mode.icon;
                                return (
                                  <SelectItem key={mode.value} value={mode.value}>
                                    <div className="flex items-center gap-2">
                                      <ModeIcon className="h-4 w-4" />
                                      <span>{mode.label}</span>
                                    </div>
                                  </SelectItem>
                                );
                              })}
                            </SelectContent>
                          </Select>
                        </div>

                        {qaScopeMode === 'documents' && qaScopeDocumentIds.length > 0 && (
                          <div className="flex flex-wrap gap-2">
                            {qaScopeDocumentIds.map((id) => {
                              const doc = qaDocumentsList.find((d) => d.id === id);
                              return (
                                <Badge key={id} variant="secondary" className="gap-2">
                                  <span className="truncate max-w-[220px]">{doc?.title || `Document ${id}`}</span>
                                  <button
                                    type="button"
                                    className="opacity-70 hover:opacity-100"
                                    onClick={() => setQaScopeDocumentIds((prev) => prev.filter((x) => x !== id))}
                                    title="Remove"
                                  >
                                    ×
                                  </button>
                                </Badge>
                              );
                            })}
                          </div>
                        )}
                      </div>

                      <div className="flex gap-2">
                        <Textarea
                          placeholder={selectedMode.placeholder}
                          value={question}
                          onChange={(e) => setQuestion(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                              e.preventDefault();
                              handleAskQuestion(e);
                            }
                          }}
                          rows={2}
                          disabled={answering}
                          className="min-h-[60px] resize-none flex-1"
                          style={{
                            background: '#0e0e14',
                            border: '1px solid rgba(255, 255, 255, 0.1)',
                            color: '#e2e2f0',
                          }}
                        />
                        <Button type="submit" disabled={answering} size="icon" className="h-[60px] w-12 shrink-0">
                          {answering ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
                        </Button>
                      </div>
                    </div>
                  </form>

                  <Dialog open={!!expandedGraph} onOpenChange={(open) => !open && setExpandedGraph(null)}>
                    <DialogContent className="max-w-[95vw] w-full max-h-[90vh] overflow-auto">
                      <DialogHeader className="shrink-0">
                        <DialogTitle>{expandedGraph?.chartTitle || 'Graph'}</DialogTitle>
                      </DialogHeader>
                      <div className="min-h-[400px] py-4">
                        {expandedGraph?.chart && renderChart(expandedGraph.chart)}
                      </div>
                    </DialogContent>
                  </Dialog>
                </CardContent>
              </Card>
            </div>
          </div>
          </ErrorBoundary>
        </TabsContent>

        {/* Chat widget tab */}
        <TabsContent value="widget" className="space-y-4 mt-4">
          <ErrorBoundary>
          <Card className="w-full min-w-0">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Monitor className="h-5 w-5" />
                Chat widget &amp; web form
              </CardTitle>
              <CardDescription>
                Embed a chat widget or contact form on your website so visitors get support where they are. No login required.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {widgetConfigLoading ? (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                  Loading...
                </div>
              ) : widgetKey ? (
                <>
                  <div className="space-y-1">
                    <Label className="text-muted-foreground">Your widget key</Label>
                    <div className="flex items-center gap-2">
                      <code className="flex-1 rounded bg-muted px-3 py-2 text-sm font-mono break-all">{widgetKey}</code>
                      <Button
                        variant="outline"
                        size="icon"
                        onClick={() => {
                          navigator.clipboard.writeText(widgetKey);
                          toast({ title: 'Copied', description: 'Widget key copied to clipboard' });
                        }}
                      >
                        <Copy className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-muted-foreground">Embed on your site (floating chat button)</Label>
                    <p className="text-xs text-muted-foreground mb-1">Add this script before &lt;/body&gt;. Replace the origin with your app URL if different.</p>
                    <pre className="rounded bg-muted p-3 text-xs overflow-x-auto relative">
                      <code>{`<script src="${typeof window !== 'undefined' ? window.location.origin : ''}/frontline-widget.js" data-key="${widgetKey}" data-base="${typeof window !== 'undefined' ? window.location.origin : ''}`}{'"></script>'}</code>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="absolute top-2 right-2 h-8 w-8"
                        onClick={() => {
                          const origin = typeof window !== 'undefined' ? window.location.origin : '';
                          const snippet = `<script src="${origin}/frontline-widget.js" data-key="${widgetKey}" data-base="${origin}"></script>`;
                          navigator.clipboard.writeText(snippet);
                          toast({ title: 'Copied', description: 'Embed code copied to clipboard' });
                        }}
                      >
                        <Copy className="h-4 w-4" />
                      </Button>
                    </pre>
                  </div>
                  <div className="flex flex-wrap gap-2 pt-2">
                    <Button variant="outline" size="sm" asChild>
                      <a href={`${typeof window !== 'undefined' ? window.location.origin : ''}/embed/chat?key=${widgetKey}`} target="_blank" rel="noopener noreferrer">
                        Open chat page
                      </a>
                    </Button>
                    <Button variant="outline" size="sm" asChild>
                      <a href={`${typeof window !== 'undefined' ? window.location.origin : ''}/embed/form?key=${widgetKey}`} target="_blank" rel="noopener noreferrer">
                        Open web form
                      </a>
                    </Button>
                  </div>
                </>
              ) : (
                <p className="text-sm text-muted-foreground">Could not load widget key. Try again later.</p>
              )}
            </CardContent>
          </Card>
          </ErrorBoundary>
        </TabsContent>

        {/* Tickets Tab */}
        <TabsContent value="tickets" className="space-y-4 mt-4">
          <ErrorBoundary>
          <Card className="w-full min-w-0">
            <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div className="min-w-0">
                <CardTitle>Support Tickets</CardTitle>
                <CardDescription>Create and filter your support tickets</CardDescription>
              </div>
              <Button onClick={() => setShowTicketDialog(true)} className="w-full sm:w-auto shrink-0">
                <Ticket className="mr-2 h-4 w-4" />
                Create Ticket
              </Button>
            </CardHeader>
            <CardContent className="space-y-4 overflow-x-hidden">
              {ticketsAging && (ticketsAging.count_breached > 0 || ticketsAging.count_at_risk > 0) && (
                <div className="rounded-lg border bg-destructive/10 border-destructive/30 p-3 flex flex-wrap items-center gap-3">
                  <span className="font-medium text-sm">SLA / aging alerts</span>
                  {ticketsAging.count_breached > 0 && (
                    <Badge variant="destructive">{ticketsAging.count_breached} breached</Badge>
                  )}
                  {ticketsAging.count_at_risk > 0 && (
                    <Badge variant="secondary" className="bg-amber-500/20 text-amber-700 dark:text-amber-400">{ticketsAging.count_at_risk} at risk</Badge>
                  )}
                  <span className="text-xs text-muted-foreground">Tickets past due or due within 2 hours. Resolve or reassign to avoid missed SLAs.</span>
                </div>
              )}
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
                  <div className="overflow-x-auto -mx-2 sm:mx-0">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Title</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Priority</TableHead>
                        <TableHead>Category</TableHead>
                        <TableHead className="whitespace-nowrap">SLA</TableHead>
                        <TableHead>Auto-resolved</TableHead>
                        <TableHead>Created</TableHead>
                        <TableHead className="text-right whitespace-nowrap">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {ticketsList.map((t) => (
                        <TableRow key={t.id}>
                          <TableCell>
                            <div>
                              <div className="font-medium flex items-center gap-2 flex-wrap">
                                <span>{t.title}</span>
                                {t.is_snoozed && (
                                  <Badge variant="outline" className="text-[10px] gap-1">
                                    <Moon className="h-3 w-3" /> Snoozed
                                  </Badge>
                                )}
                                {t.is_sla_paused && (
                                  <Badge variant="outline" className="text-[10px] gap-1 bg-amber-500/10">
                                    <PauseCircle className="h-3 w-3" /> SLA paused
                                  </Badge>
                                )}
                                {t.notes_count > 0 && (
                                  <Badge variant="outline" className="text-[10px] gap-1">
                                    <StickyNote className="h-3 w-3" /> {t.notes_count}
                                  </Badge>
                                )}
                              </div>
                              {t.description && <div className="text-xs text-muted-foreground line-clamp-1">{t.description}</div>}
                            </div>
                          </TableCell>
                          <TableCell><Badge variant="outline">{t.status}</Badge></TableCell>
                          <TableCell><Badge variant="secondary">{t.priority}</Badge></TableCell>
                          <TableCell className="capitalize">{t.category?.replace('_', ' ')}</TableCell>
                          <TableCell className="text-sm">
                            {t.sla_due_at ? (
                              <span className="flex items-center gap-1 flex-wrap">
                                {t.sla_breached && <Badge variant="destructive" className="text-xs">Breached</Badge>}
                                {t.sla_at_risk && !t.sla_breached && <Badge variant="secondary" className="text-xs bg-amber-500/20 text-amber-700 dark:text-amber-400">At risk</Badge>}
                                <span className="text-muted-foreground">{new Date(t.sla_due_at).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })}</span>
                              </span>
                            ) : '—'}
                          </TableCell>
                          <TableCell>{t.auto_resolved ? <CheckCircle2 className="h-4 w-4 text-green-600" /> : '—'}</TableCell>
                          <TableCell className="text-sm text-muted-foreground">{t.created_at ? new Date(t.created_at).toLocaleDateString() : '—'}</TableCell>
                          <TableCell className="text-right">
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button variant="ghost" size="icon" className="h-8 w-8" disabled={ticketBusyId === t.id}>
                                  {ticketBusyId === t.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <MoreHorizontal className="h-4 w-4" />}
                                </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end">
                                <DropdownMenuItem onClick={() => openCustomerDialog(t)}>
                                  <User className="h-4 w-4 mr-2" /> View customer
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={() => openNotesDialog(t)}>
                                  <StickyNote className="h-4 w-4 mr-2" /> Notes{t.notes_count ? ` (${t.notes_count})` : ''}
                                </DropdownMenuItem>
                                {t.is_snoozed ? (
                                  <DropdownMenuItem onClick={() => handleUnsnooze(t)}>
                                    <Sun className="h-4 w-4 mr-2" /> Unsnooze
                                  </DropdownMenuItem>
                                ) : (
                                  <>
                                    <DropdownMenuItem onClick={() => handleSnooze(t, 1)}>
                                      <Moon className="h-4 w-4 mr-2" /> Snooze 1 hour
                                    </DropdownMenuItem>
                                    <DropdownMenuItem onClick={() => handleSnooze(t, 24)}>
                                      <Moon className="h-4 w-4 mr-2" /> Snooze 1 day
                                    </DropdownMenuItem>
                                    <DropdownMenuItem onClick={() => handleSnooze(t, 72)}>
                                      <Moon className="h-4 w-4 mr-2" /> Snooze 3 days
                                    </DropdownMenuItem>
                                  </>
                                )}
                                <DropdownMenuItem onClick={() => handleToggleSlaPause(t)}>
                                  {t.is_sla_paused ? (
                                    <><PlayCircle className="h-4 w-4 mr-2" /> Resume SLA</>
                                  ) : (
                                    <><PauseCircle className="h-4 w-4 mr-2" /> Pause SLA</>
                                  )}
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={() => handleRetriage(t)}>
                                  <RefreshCw className="h-4 w-4 mr-2" /> Re-triage
                                </DropdownMenuItem>
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  </div>
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
          </ErrorBoundary>
        </TabsContent>

        {/* Hand-offs Tab */}
        <TabsContent value="handoffs" className="space-y-4 mt-4">
          <ErrorBoundary><HandoffQueueTab /></ErrorBoundary>
        </TabsContent>

        {/* Notifications Tab */}
        <TabsContent value="notifications" className="space-y-4 mt-4">
          <ErrorBoundary><FrontlineNotificationsTab /></ErrorBoundary>
        </TabsContent>

        {/* Workflows Tab */}
        <TabsContent value="workflows" className="space-y-4 mt-4">
          <ErrorBoundary><FrontlineWorkflowsTab /></ErrorBoundary>
        </TabsContent>

        {/* Analytics Tab */}
        <TabsContent value="analytics" className="space-y-4 mt-4">
          <ErrorBoundary><FrontlineAnalyticsTab /></ErrorBoundary>
        </TabsContent>

        {/* AI Graphs Tab */}
        <TabsContent value="ai-graphs" className="space-y-4 mt-4">
          <ErrorBoundary><FrontlineAIGraphs /></ErrorBoundary>
        </TabsContent>
      </Tabs>

      {/* Ticket notes dialog (internal / private agent discussion) */}
      <Dialog open={notesDialog.open} onOpenChange={(open) => setNotesDialog((prev) => ({ ...prev, open }))}>
        <DialogContent className="max-w-lg max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Internal notes</DialogTitle>
            <DialogDescription className="line-clamp-1">Ticket: {notesDialog.ticketTitle}</DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-y-auto space-y-3 py-2 min-h-0">
            {notesDialog.loading ? (
              <div className="flex justify-center py-6">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : notesDialog.notes.length === 0 ? (
              <div className="text-center text-sm text-muted-foreground py-6">No notes yet.</div>
            ) : notesDialog.notes.map((n) => (
              <div key={n.id} className="rounded-md border border-border/50 p-3 text-sm">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs text-muted-foreground">
                    {n.author_name || 'Agent'} · {new Date(n.created_at).toLocaleString()}
                  </span>
                  <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => deleteNote(n.id)} title="Delete note">
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
                <div className="mt-1 whitespace-pre-wrap break-words">{n.body}</div>
              </div>
            ))}
          </div>
          <div className="space-y-2 pt-2 border-t border-border/50">
            <Textarea
              value={noteDraft}
              onChange={(e) => setNoteDraft(e.target.value)}
              placeholder="Add an internal note (only visible to agents)..."
              rows={3}
            />
            <div className="flex justify-end">
              <Button onClick={submitNote} disabled={!noteDraft.trim()}>
                <Plus className="h-4 w-4 mr-1" /> Add note
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Customer 360 dialog — contact info + ticket history for the ticket's customer */}
      <Dialog open={customerDialog.open} onOpenChange={(open) => setCustomerDialog((prev) => ({ ...prev, open }))}>
        <DialogContent className="max-w-xl max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Customer</DialogTitle>
            <DialogDescription className="line-clamp-1">Ticket: {customerDialog.ticketTitle}</DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-y-auto space-y-4 py-2 min-h-0">
            {customerDialog.loading ? (
              <div className="flex justify-center py-6">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : !customerDialog.contact ? (
              <div className="text-center text-sm text-muted-foreground py-8">
                No customer record linked to this ticket yet.
                <div className="text-xs mt-1">Contacts are created automatically from inbound emails and widget submissions.</div>
              </div>
            ) : (
              <>
                {/* Contact header */}
                <div className="rounded-md border border-border/50 p-4">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
                      <User className="h-5 w-5 text-primary" />
                    </div>
                    <div className="min-w-0">
                      <div className="font-medium truncate">
                        {customerDialog.contact.name || customerDialog.contact.email}
                      </div>
                      <div className="text-xs text-muted-foreground truncate">
                        {customerDialog.contact.email}
                        {customerDialog.contact.phone ? ` · ${customerDialog.contact.phone}` : ''}
                      </div>
                    </div>
                  </div>
                  {(customerDialog.contact.tags || []).length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-3">
                      {customerDialog.contact.tags.map((tag) => (
                        <Badge key={tag} variant="secondary" className="text-xs">{tag}</Badge>
                      ))}
                    </div>
                  )}
                  <div className="grid grid-cols-3 gap-2 mt-3 text-xs">
                    <div>
                      <div className="text-muted-foreground">First seen</div>
                      <div>{customerDialog.contact.first_seen_at
                        ? new Date(customerDialog.contact.first_seen_at).toLocaleDateString()
                        : '—'}</div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">Last seen</div>
                      <div>{customerDialog.contact.last_seen_at
                        ? new Date(customerDialog.contact.last_seen_at).toLocaleDateString()
                        : '—'}</div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">External</div>
                      <div>{customerDialog.contact.external_source
                        ? `${customerDialog.contact.external_source} · ${customerDialog.contact.external_id}`
                        : '—'}</div>
                    </div>
                  </div>
                </div>

                {/* Stats */}
                {customerDialog.stats && (
                  <div className="grid grid-cols-2 gap-2">
                    <div className="rounded-md border border-border/50 p-3">
                      <div className="text-xs text-muted-foreground">Total tickets</div>
                      <div className="text-2xl font-semibold">{customerDialog.stats.total_tickets}</div>
                    </div>
                    <div className="rounded-md border border-border/50 p-3">
                      <div className="text-xs text-muted-foreground">Open now</div>
                      <div className="text-2xl font-semibold">{customerDialog.stats.open_tickets}</div>
                    </div>
                  </div>
                )}

                {/* Recent tickets */}
                {customerDialog.stats?.recent_tickets?.length > 0 && (
                  <div>
                    <div className="text-sm font-medium mb-2">Recent tickets</div>
                    <div className="space-y-1">
                      {customerDialog.stats.recent_tickets.map((t) => (
                        <div key={t.id} className="rounded border border-border/40 p-2 text-sm flex items-center justify-between gap-2">
                          <div className="min-w-0">
                            <div className="truncate">{t.title}</div>
                            <div className="text-xs text-muted-foreground">
                              #{t.id} · {t.created_at ? new Date(t.created_at).toLocaleDateString() : '—'}
                            </div>
                          </div>
                          <div className="flex items-center gap-1 flex-shrink-0">
                            <Badge variant="outline" className="text-xs">{t.priority}</Badge>
                            <Badge variant="secondary" className="text-xs">{t.status}</Badge>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </DialogContent>
      </Dialog>

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
    </div>
  );
};

export default FrontlineDashboard;

