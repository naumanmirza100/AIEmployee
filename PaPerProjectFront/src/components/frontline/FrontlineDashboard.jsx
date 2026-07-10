import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import ErrorBoundary from '@/components/common/ErrorBoundary';
import FrontlineInsightsPanel from './FrontlineInsightsPanel';
import MacroPickerDialog from './MacroPickerDialog';
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
  BookOpen,
  CheckSquare,
  Square,
  X as XIcon,
  Paperclip,
} from 'lucide-react';
import FrontlineAIGraphs from './FrontlineAIGraphs';
import FrontlineTutorial, { hasSeenTutorial, resetTutorial } from './FrontlineTutorial';
import { TAB_TOURS, HINTS } from './frontlineTutorialSteps';
import InfoHint, { HintsProvider, useHints } from './InfoHint';
import FrontlineFloatingChat from './FrontlineFloatingChat';
import { trackRecentlyViewed } from './frontlineLocalStore';
import { GraduationCap, Eye, EyeOff } from 'lucide-react';
import frontlineAgentService from '@/services/frontlineAgentService';
import { apiErrorMessage } from '@/utils/apiErrorMessage';
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
        <div className="flex items-center gap-2">
          <CardTitle className="text-base">Notification preferences</CardTitle>
          <InfoHint {...HINTS.notifPrefs} />
        </div>
        <CardDescription>Control how and when you receive notifications. Turning these off reduces spam and respects your choice.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {preferencesLoading ? (
          <div className="flex items-center gap-2 text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading preferences...</div>
        ) : (
          <div data-tour-notif="prefs" className="grid gap-4 sm:grid-cols-2">
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
        <div className="flex items-center gap-2">
          <Button data-tour-notif="template-create" onClick={openCreateTemplate}><Plus className="h-4 w-4 mr-2" /> Create template</Button>
          <InfoHint {...HINTS.notifTemplateCreate} />
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex items-start gap-2">
          <div className="pt-3"><InfoHint {...HINTS.notifSendForm} /></div>
          <form data-tour-notif="send-form" onSubmit={handleSendNow} className="flex flex-wrap items-end gap-3 p-3 border rounded-lg flex-1">
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
        </div>
        {loading ? <div className="flex justify-center py-4"><Loader2 className="h-6 w-6 animate-spin" /></div> : (
          <div data-tour-notif="lists">
            <div className="flex items-center gap-1.5 mb-1">
              <span className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">Templates & sends</span>
              <InfoHint {...HINTS.notifLists} />
            </div>
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
          </div>
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
                  {/* Only channels the backend dispatcher (`_dispatch_notification`)
                      actually routes are offered. SMS / In-App are accepted by
                      the form but silently dropped at send-time — we hide them
                      until they ship. Slack/Teams use the same global PM
                      webhook config; if it isn't set, notifications fall back
                      to email. */}
                  <SelectItem value="email">Email</SelectItem>
                  <SelectItem value="slack">Slack (uses PM webhook)</SelectItem>
                  <SelectItem value="teams">Microsoft Teams (uses PM webhook)</SelectItem>
                  <SelectItem value="sms" disabled>SMS — coming soon</SelectItem>
                  <SelectItem value="in_app" disabled>In-App — coming soon</SelectItem>
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
  // Dry-run dialog — opened when the user clicks the Play button on a workflow
  // row. Side-effect-free preview of what the workflow would do; backend at
  // `dry_run_workflow` returns step-by-step result_data with simulated: true.
  const [dryRunDialog, setDryRunDialog] = useState({
    open: false, loading: false, workflowName: '', result: null, error: '',
  });
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
  // Approve or reject a paused execution (status='awaiting_approval').
  // Backend resumes the workflow on approve, terminates it on reject.
  const [approvingExecId, setApprovingExecId] = useState(null);
  const handleApproveExecution = async (ex, action) => {
    setApprovingExecId(ex.id);
    try {
      const res = await frontlineAgentService.approveWorkflowExecution(ex.id, action);
      if (res.status === 'success' || res.status === 'accepted') {
        toast({
          title: action === 'approve' ? 'Workflow resumed' : 'Workflow rejected',
          description: res.data?.status ? `New state: ${res.data.status}` : undefined,
        });
        load();
      } else {
        throw new Error(res.message || `${action} failed`);
      }
    } catch (err) {
      toast({ title: 'Error', description: err.message || `Failed to ${action}`, variant: 'destructive' });
    } finally {
      setApprovingExecId(null);
    }
  };

  // Side-effect-free preview. We invoke with an empty context so the user
  // can sanity-check the workflow shape; a richer "pick a sample ticket"
  // picker can be added later if needed.
  const runDryRun = async (w) => {
    setDryRunDialog({ open: true, loading: true, workflowName: w.name || `Workflow #${w.id}`, result: null, error: '' });
    try {
      const res = await frontlineAgentService.dryRunWorkflow(w.id, {});
      if (res.status === 'success') {
        setDryRunDialog((d) => ({ ...d, loading: false, result: res.data || res, error: '' }));
      } else {
        throw new Error(res.message || 'Dry run failed');
      }
    } catch (err) {
      setDryRunDialog((d) => ({ ...d, loading: false, result: null, error: err.message || 'Dry run failed' }));
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
        <div className="flex items-center gap-2">
          <Button data-tour-workflows="create" onClick={openCreateWorkflow}><Plus className="h-4 w-4 mr-2" /> Create workflow</Button>
          <InfoHint {...HINTS.workflowsCreate} />
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex items-start gap-2">
          <div className="pt-3"><InfoHint {...HINTS.workflowsExecute} /></div>
          <form data-tour-workflows="execute-form" onSubmit={handleExecute} className="flex flex-wrap items-end gap-3 p-3 border rounded-lg flex-1">
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
        </div>
        {loading ? <div className="flex justify-center py-4"><Loader2 className="h-6 w-6 animate-spin" /></div> : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full min-w-0">
            <div data-tour-workflows="list" className="min-w-0">
              <div className="flex items-center gap-1.5 mb-2">
                <h4 className="font-medium">Workflows ({workflows.length})</h4>
                <InfoHint {...HINTS.workflowsList} />
              </div>
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {workflows.length === 0 ? <p className="text-sm text-muted-foreground">No workflows yet. Click &quot;Create workflow&quot; to add one.</p> : workflows.map((w) => (
                  <div key={w.id} className="flex justify-between items-center p-2 border rounded text-sm">
                    <span className="truncate min-w-0">{w.name}</span>
                    <div className="flex items-center gap-1 flex-wrap justify-end shrink-0">
                      {(w.trigger_conditions?.on) && <Badge variant="outline" className="text-xs">{w.trigger_conditions.on.replace('_', ' ')}</Badge>}
                      <Badge variant={w.is_active ? 'default' : 'secondary'}>{w.is_active ? 'Active' : 'Inactive'}</Badge>
                      <Button type="button" variant="ghost" size="icon" className="h-8 w-8" onClick={() => runDryRun(w)} title="Dry run (preview, no side effects)"><PlayCircle className="h-4 w-4" /></Button>
                      <Button type="button" variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEditWorkflow(w)} title="Edit"><Pencil className="h-4 w-4" /></Button>
                      <Button type="button" variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive" onClick={() => handleDeleteWorkflow(w)} title="Delete"><Trash2 className="h-4 w-4" /></Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div data-tour-workflows="executions" className="min-w-0">
              <div className="flex items-center gap-1.5 mb-2">
                <h4 className="font-medium">Recent executions</h4>
                <InfoHint {...HINTS.workflowsExecutions} />
              </div>
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {executions.length === 0 ? <p className="text-sm text-muted-foreground">No executions yet.</p> : executions.slice(0, 15).map((ex) => (
                  <div key={ex.id} className="flex justify-between items-center p-2 border rounded text-sm gap-2">
                    <span className="truncate min-w-0">{ex.workflow_name} · {new Date(ex.started_at).toLocaleString()}</span>
                    <div className="flex items-center gap-1 shrink-0">
                      <Badge variant={ex.status === 'completed' ? 'default' : ex.status === 'failed' ? 'destructive' : 'secondary'}>{ex.status}</Badge>
                      {/* Approve / Reject only render when the execution is
                          actually paused waiting for a human. Avoids cluttering
                          rows that have nothing to action. */}
                      {ex.status === 'awaiting_approval' && (
                        <>
                          <Button type="button" size="icon" variant="ghost"
                                  className="h-7 w-7 text-emerald-400 hover:text-emerald-300"
                                  disabled={approvingExecId === ex.id}
                                  onClick={() => handleApproveExecution(ex, 'approve')}
                                  title="Approve & resume workflow">
                            {approvingExecId === ex.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle2 className="h-3 w-3" />}
                          </Button>
                          <Button type="button" size="icon" variant="ghost"
                                  className="h-7 w-7 text-destructive hover:text-destructive"
                                  disabled={approvingExecId === ex.id}
                                  onClick={() => handleApproveExecution(ex, 'reject')}
                                  title="Reject (terminate workflow)">
                            <XCircle className="h-3 w-3" />
                          </Button>
                        </>
                      )}
                    </div>
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

    {/* Workflow dry-run preview — shows what each step WOULD do without
        actually sending emails, hitting webhooks, or writing to the DB. */}
    <Dialog open={dryRunDialog.open} onOpenChange={(open) => !open && setDryRunDialog((d) => ({ ...d, open: false }))}>
      <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <PlayCircle className="h-5 w-5 text-amber-400" />
            Dry run: {dryRunDialog.workflowName}
          </DialogTitle>
          <DialogDescription>
            Preview of what this workflow would do with an empty context. Side-effect-free — no emails, webhooks, or DB writes.
          </DialogDescription>
        </DialogHeader>
        <div className="overflow-y-auto min-h-0 flex-1 space-y-3">
          {dryRunDialog.loading ? (
            <div className="flex items-center gap-2 text-sm text-white/55 py-4">
              <Loader2 className="h-4 w-4 animate-spin" /> Simulating…
            </div>
          ) : dryRunDialog.error ? (
            <div className="rounded border border-red-700 bg-red-900/20 p-3 text-sm text-red-300">
              {dryRunDialog.error}
            </div>
          ) : dryRunDialog.result ? (
            <>
              <div className="flex items-center gap-2 text-xs">
                <Badge variant={dryRunDialog.result.success ? 'default' : 'destructive'}>
                  {dryRunDialog.result.success ? 'Would succeed' : 'Would fail'}
                </Badge>
                {dryRunDialog.result.error && (
                  <span className="text-red-300">{dryRunDialog.result.error}</span>
                )}
              </div>
              {Array.isArray(dryRunDialog.result?.result_data?.steps) && dryRunDialog.result.result_data.steps.length > 0 ? (
                <ol className="space-y-2">
                  {dryRunDialog.result.result_data.steps.map((step, idx) => (
                    <li key={idx} className="rounded border border-white/[0.08] bg-black/30 p-3 text-sm">
                      <div className="flex items-start justify-between gap-2 mb-1">
                        <span className="font-medium text-white">{idx + 1}. {step.type || step.action || 'Step'}</span>
                        <Badge variant={step.success === false ? 'destructive' : 'default'} className="shrink-0 text-xs">
                          {step.simulated ? 'Simulated' : (step.success === false ? 'Would fail' : 'Would run')}
                        </Badge>
                      </div>
                      {(step.summary || step.detail || step.note) && (
                        <p className="text-xs text-white/65">{step.summary || step.detail || step.note}</p>
                      )}
                      {step.recipient && (
                        <p className="text-xs text-white/40 mt-1">→ {step.recipient}</p>
                      )}
                    </li>
                  ))}
                </ol>
              ) : (
                <pre className="text-xs bg-black/40 border border-white/[0.06] rounded p-3 overflow-x-auto text-white/75">
                  {JSON.stringify(dryRunDialog.result?.result_data ?? dryRunDialog.result, null, 2)}
                </pre>
              )}
            </>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setDryRunDialog((d) => ({ ...d, open: false }))}>Close</Button>
        </DialogFooter>
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
  // Macro picker — opens when the agent wants a canned reply.
  const [macroOpen, setMacroOpen] = useState(false);
  // Ticket-link state for the open drawer: existing links + the in-progress
  // form for creating a new one. Reloaded each time the drawer opens.
  const [ticketLinks, setTicketLinks] = useState([]);
  const [ticketLinksLoading, setTicketLinksLoading] = useState(false);
  const [newLink, setNewLink] = useState({ relation: 'related', toTicketId: '' });
  const [creatingLink, setCreatingLink] = useState(false);

  // Customer-submitted widget attachments (images, PDFs, etc.) for the open
  // ticket. Loaded lazily when the drawer opens — the list endpoint walks
  // the per-company upload directory and returns rows shaped like
  // `{ name, size, stored_filename }`. The stored_filename is what the
  // download URL needs.
  const [widgetAttachments, setWidgetAttachments] = useState([]);
  const [widgetAttachmentsLoading, setWidgetAttachmentsLoading] = useState(false);

  const loadWidgetAttachments = async (ticketId) => {
    if (!ticketId) return;
    setWidgetAttachmentsLoading(true);
    try {
      const res = await frontlineAgentService.listWidgetAttachments(ticketId);
      setWidgetAttachments((res?.data) || []);
    } catch (e) {
      console.warn('Load widget attachments failed', e);
      setWidgetAttachments([]);
    } finally {
      setWidgetAttachmentsLoading(false);
    }
  };

  const formatAttachmentSize = (n) => {
    if (typeof n !== 'number' || n < 0) return '';
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(1)} MB`;
  };

  const loadTicketLinks = async (ticketId) => {
    if (!ticketId) return;
    setTicketLinksLoading(true);
    try {
      const res = await frontlineAgentService.listTicketLinks(ticketId);
      setTicketLinks((res?.data) || []);
    } catch (e) {
      console.warn('Load ticket links failed', e);
      setTicketLinks([]);
    } finally {
      setTicketLinksLoading(false);
    }
  };

  const handleCreateTicketLink = async () => {
    const toId = parseInt(String(newLink.toTicketId).trim(), 10);
    if (!drawer.ticket || !toId) {
      toast({ title: 'Pick a target ticket', description: 'Enter the ID of the ticket you want to link to.', variant: 'destructive' });
      return;
    }
    setCreatingLink(true);
    try {
      await frontlineAgentService.createTicketLink(drawer.ticket.id, {
        to_ticket_id: toId, relation: newLink.relation,
      });
      toast({ title: 'Linked' });
      setNewLink({ relation: 'related', toTicketId: '' });
      await loadTicketLinks(drawer.ticket.id);
    } catch (e) {
      toast({ title: 'Link failed', description: e?.response?.data?.message || e.message, variant: 'destructive' });
    } finally {
      setCreatingLink(false);
    }
  };

  const handleDeleteTicketLink = async (linkId) => {
    try {
      await frontlineAgentService.deleteTicketLink(linkId);
      setTicketLinks((rows) => rows.filter((l) => l.id !== linkId));
    } catch (e) {
      toast({ title: 'Delete failed', description: e.message, variant: 'destructive' });
    }
  };

  // Reassign / Release support — handoffs to colleagues.
  // We lazy-load the company-user list the first time the reassign popover opens.
  const [reassignPopover, setReassignPopover] = useState({ open: false, candidates: [], loading: false });
  const [releasingHandoff, setReleasingHandoff] = useState(false);
  const [reassigningHandoff, setReassigningHandoff] = useState(false);

  const openReassignPopover = async () => {
    setReassignPopover({ open: true, candidates: [], loading: true });
    try {
      const res = await frontlineAgentService.listWorkflowCompanyUsers();
      const data = (res?.data) || [];
      setReassignPopover({ open: true, candidates: data, loading: false });
    } catch (e) {
      setReassignPopover({ open: false, candidates: [], loading: false });
      toast({ title: 'Failed to load agents', description: e.message, variant: 'destructive' });
    }
  };

  const handleReleaseHandoff = async () => {
    if (!drawer.ticket) return;
    setReleasingHandoff(true);
    try {
      await frontlineAgentService.releaseHandoff(drawer.ticket.id);
      toast({ title: 'Released', description: 'Hand-off returned to the pending pool.' });
      setDrawer((prev) => ({ ...prev, open: false }));
      load();
    } catch (e) {
      toast({ title: 'Release failed', description: e?.response?.data?.message || e.message, variant: 'destructive' });
    } finally {
      setReleasingHandoff(false);
    }
  };

  const handleReassignHandoff = async (cu) => {
    if (!drawer.ticket || !cu) return;
    setReassigningHandoff(true);
    try {
      await frontlineAgentService.reassignHandoff(drawer.ticket.id, cu.id);
      toast({ title: 'Reassigned', description: `Hand-off transferred to ${cu.full_name || cu.username || cu.email}.` });
      setReassignPopover({ open: false, candidates: [], loading: false });
      setDrawer((prev) => ({ ...prev, open: false }));
      load();
    } catch (e) {
      toast({ title: 'Reassign failed', description: e?.response?.data?.message || e.message, variant: 'destructive' });
    } finally {
      setReassigningHandoff(false);
    }
  };
  const handleMacroInsert = (body) => {
    setDrawer((prev) => {
      const cur = prev.reply || '';
      // Append to existing draft when there is one, otherwise replace.
      const sep = cur.trim() ? '\n\n' : '';
      return { ...prev, reply: cur + sep + body };
    });
  };

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
    // Remember this hand-off for the "Recently viewed" strip in Quick Chat.
    trackRecentlyViewed({
      kind: 'ticket',
      id: ticket.id,
      title: ticket.title || `Ticket #${ticket.id}`,
      meta: ticket.priority || '',
    });
    setDrawer({
      open: true, ticket, messages: [], loading: true,
      reply: '', sending: false, suggesting: false, accepting: false,
    });
    setTicketLinks([]);
    setNewLink({ relation: 'related', toTicketId: '' });
    setWidgetAttachments([]);
    loadTicketLinks(ticket.id);
    loadWidgetAttachments(ticket.id);
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
      <div data-tour-handoffs="filters" className="flex flex-wrap items-center gap-2">
        <InfoHint {...HINTS.handoffsFilters} />
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
      <div className="flex items-center gap-1.5">
        <span className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">Queue</span>
        <InfoHint {...HINTS.handoffsQueue} />
      </div>
      <div data-tour-handoffs="queue" className="overflow-x-auto -mx-2 sm:mx-0">
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

          {/* Customer-uploaded attachments from the public widget. Files are
              auth-gated server-side and stored under the company directory;
              the link below opens an inline-served stream (images / PDFs
              preview, binaries download). */}
          {(widgetAttachments.length > 0 || widgetAttachmentsLoading) && (
            <div className="space-y-2 pt-2 border-t border-border/50">
              <div className="flex items-center justify-between">
                <Label className="text-xs uppercase tracking-wider text-muted-foreground">Customer attachments</Label>
                {widgetAttachmentsLoading && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
              </div>
              {widgetAttachments.length > 0 && (
                <div className="space-y-1">
                  {widgetAttachments.map((a) => (
                    <a
                      key={a.stored_filename}
                      href={frontlineAgentService.widgetAttachmentDownloadUrl(drawer.ticket.id, a.stored_filename)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-2 text-xs rounded border border-border/40 bg-muted/30 px-2 py-1.5 hover:bg-muted/50 transition-colors"
                    >
                      <Paperclip className="h-3 w-3 text-muted-foreground shrink-0" />
                      <span className="truncate flex-1">{a.name}</span>
                      {typeof a.size === 'number' && (
                        <span className="text-muted-foreground shrink-0">{formatAttachmentSize(a.size)}</span>
                      )}
                    </a>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Linked tickets — pick a relation + target ticket ID to annotate
              cross-ticket relationships. Backend stores them in TicketLink and
              the relation drives downstream automation (e.g. closing a parent
              cascades to children). */}
          <div className="space-y-2 pt-2 border-t border-border/50">
            <div className="flex items-center justify-between">
              <Label className="text-xs uppercase tracking-wider text-muted-foreground">Linked tickets</Label>
              {ticketLinksLoading && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
            </div>
            {ticketLinks.length > 0 && (
              <div className="space-y-1">
                {ticketLinks.map((l) => (
                  <div key={l.id} className="flex items-center gap-2 text-xs rounded border border-border/40 bg-muted/30 px-2 py-1">
                    <Badge variant="secondary" className="text-[10px] shrink-0">
                      {(frontlineAgentService.TICKET_LINK_RELATIONS.find((r) => r.value === l.relation) || {}).label || l.relation}
                    </Badge>
                    <span className="truncate flex-1">
                      #{l.other_ticket?.id ?? l.to_ticket?.id ?? l.from_ticket?.id} —{' '}
                      {l.other_ticket?.title || l.to_ticket?.title || l.from_ticket?.title || 'Untitled'}
                    </span>
                    <Button size="icon" variant="ghost" className="h-6 w-6 text-destructive hover:text-destructive shrink-0"
                            onClick={() => handleDeleteTicketLink(l.id)} title="Remove link">
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
            <div className="flex items-center gap-2">
              <Select value={newLink.relation} onValueChange={(v) => setNewLink((n) => ({ ...n, relation: v }))}>
                <SelectTrigger className="w-[160px] h-8 text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {frontlineAgentService.TICKET_LINK_RELATIONS.map((r) => (
                    <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Input
                type="number"
                inputMode="numeric"
                placeholder="Ticket ID"
                className="h-8 w-32 text-xs"
                value={newLink.toTicketId}
                onChange={(e) => setNewLink((n) => ({ ...n, toTicketId: e.target.value }))}
              />
              <Button size="sm" variant="outline" onClick={handleCreateTicketLink} disabled={creatingLink || !newLink.toTicketId}>
                {creatingLink ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Plus className="h-3 w-3 mr-1" />}
                Link
              </Button>
            </div>
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
              <Button
                variant="outline"
                size="sm"
                onClick={() => setMacroOpen(true)}
                disabled={drawer.sending}
                title="Insert a saved reply"
              >
                <BookOpen className="h-4 w-4 mr-1" /> Macros
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
              {/* Release returns the handoff to the unowned pending pool.
                  Only meaningful on accepted handoffs (the endpoint 400s
                  otherwise). Reassign explicitly transfers to another
                  agent and works on either pending or accepted. */}
              {drawer.ticket?.handoff_status === 'accepted' && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleReleaseHandoff}
                  disabled={releasingHandoff}
                  title="Send back to the unowned queue"
                >
                  {releasingHandoff
                    ? <Loader2 className="h-4 w-4 animate-spin mr-1" />
                    : <RotateCcw className="h-4 w-4 mr-1" />}
                  Release
                </Button>
              )}
              {(drawer.ticket?.handoff_status === 'pending' || drawer.ticket?.handoff_status === 'accepted') && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={openReassignPopover}
                  disabled={reassigningHandoff}
                  title="Hand off to a specific other agent"
                >
                  <User className="h-4 w-4 mr-1" /> Reassign…
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

      <MacroPickerDialog open={macroOpen}
        onOpenChange={setMacroOpen}
        onInsert={handleMacroInsert} />

      {/* Reassign-handoff picker. Opens when "Reassign…" is clicked in the
          drawer; lists company users and assigns the ticket directly to the
          picked one. */}
      <Dialog open={reassignPopover.open} onOpenChange={(open) => !open && !reassigningHandoff && setReassignPopover({ open: false, candidates: [], loading: false })}>
        <DialogContent className="max-w-md max-h-[70vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <User className="h-4 w-4" /> Reassign hand-off
            </DialogTitle>
            <DialogDescription>
              Pick the agent to hand this ticket to. They'll see it in their own queue immediately.
            </DialogDescription>
          </DialogHeader>
          <div className="overflow-y-auto min-h-0 flex-1 space-y-1">
            {reassignPopover.loading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
                <Loader2 className="h-4 w-4 animate-spin" /> Loading agents…
              </div>
            ) : reassignPopover.candidates.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">No agents available in your company.</p>
            ) : (
              reassignPopover.candidates.map((cu) => (
                <Button
                  key={cu.id}
                  variant="ghost"
                  size="sm"
                  disabled={reassigningHandoff}
                  className="w-full justify-start"
                  onClick={() => handleReassignHandoff(cu)}
                >
                  <User className="h-3.5 w-3.5 mr-2 text-muted-foreground shrink-0" />
                  <div className="flex-1 min-w-0 text-left">
                    <div className="truncate">{cu.full_name || cu.username || cu.email}</div>
                    {cu.email && <div className="text-xs text-muted-foreground truncate">{cu.email}</div>}
                  </div>
                  {reassigningHandoff && <Loader2 className="h-3 w-3 animate-spin ml-2" />}
                </Button>
              ))
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReassignPopover({ open: false, candidates: [], loading: false })} disabled={reassigningHandoff}>
              Cancel
            </Button>
          </DialogFooter>
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
  // Team performance drill-down (per-agent). Loaded alongside analytics
  // so the same date range applies to both. State is separate from `data`
  // so a slow team-perf fetch doesn't block the summary cards from rendering.
  const [perfRows, setPerfRows] = useState(null);
  const [perfLoading, setPerfLoading] = useState(false);
  // Column the perf table is sorted by (defaults to tickets_assigned desc,
  // matching the backend order but rebindable client-side).
  const [perfSort, setPerfSort] = useState({ col: 'tickets_assigned', dir: 'desc' });
  // CSAT drill-down — same fetch strategy as team perf, requests the
  // opt-in `by_agent` + `by_month` add-ons.
  const [csatDetail, setCsatDetail] = useState(null);
  const [csatLoading, setCsatLoading] = useState(false);

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
  const loadPerf = async () => {
    setPerfLoading(true);
    try {
      const res = await frontlineAgentService.getFrontlineAgentPerformance(
        dateFrom || undefined, dateTo || undefined,
      );
      setPerfRows((res.status === 'success' && Array.isArray(res.data)) ? res.data : []);
    } catch (e) {
      setPerfRows([]);
      console.warn('Team performance load failed:', e.message);
    } finally {
      setPerfLoading(false);
    }
  };
  const loadCsat = async () => {
    setCsatLoading(true);
    try {
      // The date-range inputs above are ticket-created dates. CSAT's
      // window_days param counts back from now. As a pragmatic compromise:
      // if a date-range is set, size the window from the earlier of the
      // two — imperfect but consistent with how the SLA tile works.
      const daysFromRange = dateFrom
        ? Math.max(1, Math.ceil((Date.now() - new Date(dateFrom).getTime()) / 86400000))
        : 90;
      const res = await frontlineAgentService.getFrontlineSatisfactionSummary({
        windowDays: Math.min(daysFromRange, 365),
        byAgent: true, byMonth: true,
      });
      setCsatDetail((res.status === 'success' && res.data) ? res.data : null);
    } catch (e) {
      setCsatDetail(null);
      console.warn('CSAT detail load failed:', e.message);
    } finally {
      setCsatLoading(false);
    }
  };
  useEffect(() => { load(); loadPerf(); loadCsat(); }, [dateFrom, dateTo]);
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
        <div data-tour-analytics="nlq" className="rounded-lg border bg-muted/30 p-4 space-y-2">
          <div className="flex items-center gap-1.5">
            <Label className="text-sm font-medium">Ask in plain language</Label>
            <InfoHint {...HINTS.analyticsNlq} />
          </div>
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

        <div data-tour-analytics="range" className="flex flex-wrap items-end gap-3">
          <div className="pb-2"><InfoHint {...HINTS.analyticsRange} /></div>
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
            <div className="flex items-center gap-1.5">
              <span className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">KPIs</span>
              <InfoHint {...HINTS.analyticsKpis} />
            </div>
            <div data-tour-analytics="kpis" className="grid grid-cols-2 md:grid-cols-4 gap-4">
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
            <div className="flex items-center gap-1.5">
              <span className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">Charts & team</span>
              <InfoHint {...HINTS.analyticsCharts} />
            </div>
            <div data-tour-analytics="charts" className="grid grid-cols-1 lg:grid-cols-2 gap-4">
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

        {/* Team performance — per-agent breakdown. Sortable columns +
            outlier highlighting so a manager can spot who needs help
            (high SLA breach %) or who's carrying more than their share
            (high tickets_assigned relative to the team average). */}
        <div className="rounded-lg border bg-muted/20 p-4 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div>
              <h4 className="font-medium text-sm">Team performance</h4>
              <p className="text-xs text-muted-foreground">
                Per-agent stats over the selected date range. Click a column
                to sort. Median is more robust than mean for skewed data.
              </p>
            </div>
            <Button variant="ghost" size="sm" onClick={loadPerf} disabled={perfLoading}>
              {perfLoading
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <RefreshCw className="h-3.5 w-3.5" />}
            </Button>
          </div>

          {perfLoading && !perfRows ? (
            <div className="flex justify-center py-6">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : !perfRows || perfRows.length === 0 ? (
            <p className="text-xs text-muted-foreground py-3">
              No agents with assigned tickets in this window.
            </p>
          ) : (() => {
            // Compute team averages for outlier highlighting. Uses the
            // subset of agents who resolved anything — computing a mean
            // over agents who never resolved would just skew everything.
            const withResolved = perfRows.filter((r) => r.resolved > 0);
            const avgBreachPct = withResolved.length
              ? withResolved.reduce((s, r) => s + (r.sla_breach_pct || 0), 0) / withResolved.length
              : 0;
            const avgMedianRes = withResolved.length
              ? withResolved.reduce((s, r) => s + (r.median_resolution_seconds || 0), 0) / withResolved.length
              : 0;

            const sorted = [...perfRows].sort((a, b) => {
              const av = a[perfSort.col] ?? -Infinity;
              const bv = b[perfSort.col] ?? -Infinity;
              const cmp = av === bv ? 0 : (av < bv ? -1 : 1);
              return perfSort.dir === 'asc' ? cmp : -cmp;
            });
            const setSort = (col) => setPerfSort((s) =>
              s.col === col
                ? { col, dir: s.dir === 'asc' ? 'desc' : 'asc' }
                : { col, dir: 'desc' },
            );
            const hdr = (col, label) => (
              <th
                onClick={() => setSort(col)}
                className={`px-2 py-1.5 text-left font-medium cursor-pointer select-none ${
                  perfSort.col === col ? 'text-white' : 'text-white/60'
                } hover:text-white`}
              >
                {label}{perfSort.col === col ? (perfSort.dir === 'asc' ? ' ↑' : ' ↓') : ''}
              </th>
            );
            const fmtSecs = (s) => {
              if (s == null) return '—';
              if (s < 60) return `${Math.round(s)}s`;
              if (s < 3600) return `${Math.round(s / 60)}m`;
              if (s < 86400) return `${(s / 3600).toFixed(1)}h`;
              return `${(s / 86400).toFixed(1)}d`;
            };
            return (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="border-b border-white/[0.06]">
                    <tr>
                      {hdr('assigned_to_name', 'Agent')}
                      {hdr('tickets_assigned', 'Assigned')}
                      {hdr('resolved', 'Resolved')}
                      {hdr('resolution_rate', 'Rate')}
                      {hdr('median_resolution_seconds', 'Median resolve')}
                      {hdr('sla_breach_pct', 'SLA breach %')}
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map((r) => {
                      // Flag as outlier if this agent's breach % is at least
                      // 15 percentage points above the team's average AND they
                      // resolved enough to be statistically meaningful (>= 3).
                      // 15pp is a rule-of-thumb, not gospel — tune later.
                      const isBreachOutlier = r.resolved >= 3
                        && (r.sla_breach_pct - avgBreachPct) >= 0.15;
                      // Similarly for slow median resolution — flag if ≥1.5×
                      // the team median AND at least 3 resolved tickets.
                      const isSlowOutlier = r.resolved >= 3
                        && avgMedianRes > 0
                        && r.median_resolution_seconds
                        && r.median_resolution_seconds >= 1.5 * avgMedianRes;
                      const bg = isBreachOutlier
                        ? 'bg-rose-500/[0.05]'
                        : isSlowOutlier ? 'bg-amber-500/[0.05]' : '';
                      return (
                        <tr key={r.assigned_to_id} className={`border-b border-white/[0.04] ${bg}`}>
                          <td className="px-2 py-1.5 text-white/85">
                            {r.assigned_to_name || `User #${r.assigned_to_id}`}
                          </td>
                          <td className="px-2 py-1.5 text-white/70">{r.tickets_assigned}</td>
                          <td className="px-2 py-1.5 text-white/70">
                            {r.resolved}
                            {r.auto_resolved > 0 && (
                              <span className="text-white/40"> ({r.auto_resolved} auto)</span>
                            )}
                          </td>
                          <td className="px-2 py-1.5 text-white/70">
                            {r.tickets_assigned > 0 ? `${Math.round(r.resolution_rate * 100)}%` : '—'}
                          </td>
                          <td className={`px-2 py-1.5 ${isSlowOutlier ? 'text-amber-300' : 'text-white/70'}`}>
                            {fmtSecs(r.median_resolution_seconds)}
                          </td>
                          <td className={`px-2 py-1.5 ${isBreachOutlier ? 'text-rose-300 font-medium' : 'text-white/70'}`}>
                            {r.resolved > 0
                              ? `${Math.round(r.sla_breach_pct * 100)}%`
                              : '—'}
                            {r.sla_breached_count > 0 && (
                              <span className="text-white/40"> ({r.sla_breached_count})</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {(withResolved.length > 0) && (
                  <p className="text-[10px] text-muted-foreground pt-2">
                    Team average: median resolve <span className="text-white/70">{fmtSecs(avgMedianRes)}</span>
                    {' · '}
                    SLA breach <span className="text-white/70">{Math.round(avgBreachPct * 100)}%</span>.
                    <span className="text-rose-300"> Rose </span>rows = breach % ≥ 15pp over team avg.
                    <span className="text-amber-300"> Amber </span>rows = median resolve ≥ 1.5× team median.
                  </p>
                )}
              </div>
            );
          })()}
        </div>

        {/* CSAT drill-down — per-agent breakdown + monthly trend. The tile
            on the Overview shows only the roll-up; this section adds the
            "who's getting the good ratings" and "are we trending up or
            down" dimensions the reporting was missing. */}
        <div className="rounded-lg border bg-muted/20 p-4 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <div>
              <h4 className="font-medium text-sm">CSAT drill-down</h4>
              <p className="text-xs text-muted-foreground">
                Per-agent and monthly trend for customer satisfaction.
              </p>
            </div>
            <Button variant="ghost" size="sm" onClick={loadCsat} disabled={csatLoading}>
              {csatLoading
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <RefreshCw className="h-3.5 w-3.5" />}
            </Button>
          </div>

          {csatLoading && !csatDetail ? (
            <div className="flex justify-center py-6">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : !csatDetail || csatDetail.response_count === 0 ? (
            <p className="text-xs text-muted-foreground py-3">
              No CSAT responses in this window.
            </p>
          ) : (
            <div className="space-y-4">
              {/* Header stats */}
              <div className="flex items-baseline gap-4 flex-wrap">
                <div>
                  <div className="text-2xl font-semibold text-white">
                    {csatDetail.average != null ? csatDetail.average.toFixed(2) : '—'}
                    <span className="text-sm text-white/40 font-normal"> / 5</span>
                  </div>
                  <div className="text-[10px] text-white/40">
                    {csatDetail.response_count} responses over {csatDetail.window_days}d
                  </div>
                </div>
                {/* Distribution — inline horizontal bar (no chart lib). */}
                <div className="flex-1 min-w-[200px] space-y-0.5">
                  {[5, 4, 3, 2, 1].map((star) => {
                    const c = csatDetail.distribution?.[String(star)] || 0;
                    const pct = csatDetail.response_count
                      ? Math.round((c / csatDetail.response_count) * 100)
                      : 0;
                    return (
                      <div key={star} className="flex items-center gap-2 text-[11px]">
                        <span className="w-4 text-white/50 text-right">{star}</span>
                        <div className="flex-1 h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
                          <div
                            className={`h-full ${star >= 4 ? 'bg-emerald-500' : star === 3 ? 'bg-amber-500' : 'bg-rose-500'}`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <span className="w-8 text-white/50 text-right">{c}</span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Monthly trend */}
              {Array.isArray(csatDetail.trend) && csatDetail.trend.length > 0 && (
                <div>
                  <div className="text-[11px] uppercase tracking-wide text-white/40 mb-1">Monthly trend</div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead className="border-b border-white/[0.06]">
                        <tr className="text-white/60">
                          <th className="px-2 py-1.5 text-left font-medium">Month</th>
                          <th className="px-2 py-1.5 text-left font-medium">Responses</th>
                          <th className="px-2 py-1.5 text-left font-medium">Average</th>
                          <th className="px-2 py-1.5 text-left font-medium">vs prev</th>
                        </tr>
                      </thead>
                      <tbody>
                        {csatDetail.trend.map((m, i) => {
                          const prev = csatDetail.trend[i - 1];
                          const delta = prev && prev.average != null && m.average != null
                            ? m.average - prev.average
                            : null;
                          const deltaColor = delta == null
                            ? 'text-white/40'
                            : delta > 0.05 ? 'text-emerald-400'
                              : delta < -0.05 ? 'text-rose-400'
                                : 'text-white/50';
                          return (
                            <tr key={m.month} className="border-b border-white/[0.04]">
                              <td className="px-2 py-1.5 text-white/80">{m.month}</td>
                              <td className="px-2 py-1.5 text-white/70">{m.response_count}</td>
                              <td className="px-2 py-1.5 text-white/80">
                                {m.average != null ? m.average.toFixed(2) : '—'}
                              </td>
                              <td className={`px-2 py-1.5 ${deltaColor}`}>
                                {delta == null ? '—' : `${delta > 0 ? '+' : ''}${delta.toFixed(2)}`}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Per-agent breakdown */}
              {Array.isArray(csatDetail.by_agent) && csatDetail.by_agent.length > 0 && (
                <div>
                  <div className="text-[11px] uppercase tracking-wide text-white/40 mb-1">By agent</div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead className="border-b border-white/[0.06]">
                        <tr className="text-white/60">
                          <th className="px-2 py-1.5 text-left font-medium">Agent</th>
                          <th className="px-2 py-1.5 text-left font-medium">Responses</th>
                          <th className="px-2 py-1.5 text-left font-medium">Average</th>
                          <th className="px-2 py-1.5 text-left font-medium">5★</th>
                          <th className="px-2 py-1.5 text-left font-medium">1★</th>
                        </tr>
                      </thead>
                      <tbody>
                        {csatDetail.by_agent.map((a) => {
                          const low = a.average != null && a.average < 3.5 && a.response_count >= 3;
                          const good = a.average != null && a.average >= 4.5 && a.response_count >= 3;
                          return (
                            <tr key={a.assigned_to_id ?? 'unassigned'}
                                className={`border-b border-white/[0.04] ${low ? 'bg-rose-500/[0.05]' : good ? 'bg-emerald-500/[0.05]' : ''}`}>
                              <td className="px-2 py-1.5 text-white/85">{a.assigned_to_name || `User #${a.assigned_to_id}`}</td>
                              <td className="px-2 py-1.5 text-white/70">{a.response_count}</td>
                              <td className={`px-2 py-1.5 ${low ? 'text-rose-300' : good ? 'text-emerald-300' : 'text-white/85'}`}>
                                {a.average != null ? a.average.toFixed(2) : '—'}
                              </td>
                              <td className="px-2 py-1.5 text-white/70">{a.distribution?.['5'] || 0}</td>
                              <td className="px-2 py-1.5 text-white/70">{a.distribution?.['1'] || 0}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    <p className="text-[10px] text-muted-foreground pt-2">
                      Highlighted: <span className="text-emerald-300">green</span> = avg ≥ 4.5 with 3+ responses;
                      <span className="text-rose-300"> red</span> = avg &lt; 3.5 with 3+ responses.
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
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
  const [tutorialOpen, setTutorialOpen] = useState(false);
  // Which per-tab tour is currently open (null when none). Value = tab key.
  const [activeTabTour, setActiveTabTour] = useState(null);

  // Auto-launch onboarding tutorial the first time this user lands on the dashboard.
  useEffect(() => {
    if (!hasSeenTutorial()) {
      const t = setTimeout(() => setTutorialOpen(true), 600);
      return () => clearTimeout(t);
    }
  }, []);

  const handleReplayTutorial = () => {
    resetTutorial();
    setTutorialOpen(true);
  };

  // Auto-launch the per-tab tour the first time the user visits a given tab.
  useEffect(() => {
    if (tutorialOpen) return; // don't stack with the main tour
    const tour = TAB_TOURS[activeTab];
    if (!tour) return;
    if (hasSeenTutorial(tour.key)) return;
    const t = setTimeout(() => setActiveTabTour(activeTab), 500);
    return () => clearTimeout(t);
  }, [activeTab, tutorialOpen]);

  const handleReplayTabTour = (tabKey) => {
    const tour = TAB_TOURS[tabKey];
    if (!tour) return;
    resetTutorial(tour.key);
    setActiveTabTour(tabKey);
  };

  // Small button rendered inside each TabsContent header
  const TabTourButton = ({ tabKey }) => (
    <button
      type="button"
      onClick={() => handleReplayTabTour(tabKey)}
      title={`Take a guided tour of the ${TAB_TOURS[tabKey]?.label || 'this'} tab`}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-amber-400/40 bg-amber-400/10 text-amber-300 text-xs font-semibold hover:bg-amber-400/20 hover:text-amber-200 transition"
    >
      <GraduationCap className="h-3.5 w-3.5" />
      Tour this tab
    </button>
  );

  // Toggle for showing/hiding all "!" InfoHint icons across the dashboard.
  // Reads from the same context every InfoHint consumes, so flipping this
  // state hides / re-shows every hint icon instantly and persistently.
  const HintsToggleButton = () => {
    const { enabled, toggle } = useHints();
    return (
      <button
        type="button"
        onClick={toggle}
        aria-pressed={enabled}
        title={enabled ? 'Hide the ! help icons on every element' : 'Show the ! help icons on every element'}
        className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-semibold transition border ${
          enabled
            ? 'border-amber-400/40 bg-amber-400/10 text-amber-300 hover:bg-amber-400/20 hover:text-amber-200'
            : 'border-white/10 bg-white/[0.03] text-white/50 hover:bg-white/[0.06] hover:text-white/70'
        }`}
      >
        {enabled ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
        <span>Hints: {enabled ? 'On' : 'Off'}</span>
      </button>
    );
  };
  
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
  const [allowedOrigins, setAllowedOrigins] = useState('');
  const [allowedOriginsSaving, setAllowedOriginsSaving] = useState(false);
  // Extra theming knobs (EW1). When all are blank/null, the widget JS uses its
  // built-in defaults — these are purely additive customisations.
  const [widgetTheme, setWidgetTheme] = useState({
    primary_color: '', font_family: '', border_radius: '',
    header_bg: '', header_text_color: '',
    bubble_bg_user: '', bubble_bg_agent: '',
    css_overrides: '',
  });
  const [themeSaving, setThemeSaving] = useState(false);
  
  // Ticket creation
  const [showTicketDialog, setShowTicketDialog] = useState(false);
  const [ticketTitle, setTicketTitle] = useState('');
  const [ticketDescription, setTicketDescription] = useState('');
  const [creatingTicket, setCreatingTicket] = useState(false);

  // Document processing result (summarize / extract)
  const [docResultDialog, setDocResultDialog] = useState({ open: false, type: null, title: '', content: null, loading: false });
  // Per-doc inline summary cache + expand toggle for the redesigned card grid.
  // Shape: { [docId]: { summary, loading, expanded, error } }
  const [docSummaries, setDocSummaries] = useState({});

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
  // Bulk-update selection state. Set of ticket IDs. Cleared when filters change
  // so a selection from a previous page can't accidentally be applied to a
  // different list.
  const [selectedTicketIds, setSelectedTicketIds] = useState(new Set());
  const [bulkActionDialog, setBulkActionDialog] = useState({ open: false, field: null, value: '' });
  const [bulkApplying, setBulkApplying] = useState(false);
  const toggleTicketSelected = (id) => {
    setSelectedTicketIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  const toggleAllTicketsOnPage = () => {
    setSelectedTicketIds((prev) => {
      const allOnPage = ticketsList.every((t) => prev.has(t.id));
      if (allOnPage) {
        const next = new Set(prev);
        ticketsList.forEach((t) => next.delete(t.id));
        return next;
      }
      const next = new Set(prev);
      ticketsList.forEach((t) => next.add(t.id));
      return next;
    });
  };
  const clearTicketSelection = () => setSelectedTicketIds(new Set());
  const handleBulkApply = async () => {
    const ids = Array.from(selectedTicketIds);
    const { field, value } = bulkActionDialog;
    if (!ids.length || !field || !value) return;
    setBulkApplying(true);
    try {
      const payload = { ids };
      if (field === 'status') payload.status = value;
      else if (field === 'priority') payload.priority = value;
      else if (field === 'category') payload.category = value;
      const res = await frontlineAgentService.bulkUpdateTickets(payload);
      const data = res?.data || {};
      const updated = data.updated || [];
      const skipped = data.skipped || [];
      toast({
        title: `Bulk update: ${updated.length} updated`,
        description: skipped.length
          ? `${skipped.length} skipped — see console for details.`
          : (data.not_found?.length ? `${data.not_found.length} not found.` : 'All matching tickets updated.'),
      });
      if (skipped.length) console.warn('Bulk update skipped:', skipped);
      // Refresh list so badges reflect new state.
      loadTickets?.();
      clearTicketSelection();
      setBulkActionDialog({ open: false, field: null, value: '' });
    } catch (e) {
      toast({ title: 'Bulk update failed', description: e.message, variant: 'destructive' });
    } finally {
      setBulkApplying(false);
    }
  };

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
        if (cancelled || res?.status !== 'success') return;
        if (res?.data?.widget_key) setWidgetKey(res.data.widget_key);
        setAllowedOrigins(res?.data?.allowed_origins || '');
        const theme = res?.data?.config?.theme || {};
        setWidgetTheme({
          primary_color: theme.primary_color || '',
          font_family: theme.font_family || '',
          border_radius: theme.border_radius || '',
          header_bg: theme.header_bg || '',
          header_text_color: theme.header_text_color || '',
          bubble_bg_user: theme.bubble_bg_user || '',
          bubble_bg_agent: theme.bubble_bg_agent || '',
          css_overrides: theme.css_overrides || '',
        });
      })
      .catch(() => { if (!cancelled) { setWidgetKey(''); setAllowedOrigins(''); } })
      .finally(() => { if (!cancelled) setWidgetConfigLoading(false); });
    return () => { cancelled = true; };
  }, [activeTab]);

  const handleSaveAllowedOrigins = async () => {
    setAllowedOriginsSaving(true);
    try {
      const res = await frontlineAgentService.updateFrontlineWidgetConfig({
        allowedOrigins: allowedOrigins.trim(),
      });
      if (res?.status === 'success') {
        setAllowedOrigins(res?.data?.allowed_origins ?? allowedOrigins.trim());
        toast({ title: 'Allowed origins saved' });
      } else {
        throw new Error(res?.message || 'Save failed');
      }
    } catch (e) {
      toast({ title: 'Save failed', description: e.message, variant: 'destructive' });
    } finally {
      setAllowedOriginsSaving(false);
    }
  };

  const handleSaveTheme = async () => {
    setThemeSaving(true);
    try {
      // Only send non-empty values so blank inputs fall back to backend defaults.
      const themePatch = Object.fromEntries(
        Object.entries(widgetTheme).filter(([, v]) => v !== '' && v != null),
      );
      const res = await frontlineAgentService.updateFrontlineWidgetConfig({
        config: { theme: themePatch },
      });
      if (res?.status === 'success') {
        toast({ title: 'Theme saved', description: 'Embed widget will pick up new colours on next load.' });
      } else {
        throw new Error(res?.message || 'Save failed');
      }
    } catch (e) {
      toast({ title: 'Save failed', description: e.message, variant: 'destructive' });
    } finally {
      setThemeSaving(false);
    }
  };

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

      // Backend returns 'accepted' (202) when processing was enqueued asynchronously,
      // or 'success' when processed inline. Treat either as a successful upload.
      if (response.status === 'success' || response.status === 'accepted') {
        const mode = response?.data?.dispatch_mode;
        toast({
          title: 'Success!',
          description: mode === 'inline'
            ? 'Document uploaded and indexed.'
            : 'Document uploaded — processing in the background.',
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
    trackRecentlyViewed({ kind: 'document', id: doc.id, title: doc.title || `Document #${doc.id}` });
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
      setDocResultDialog((prev) => ({ ...prev, content: apiErrorMessage(error, 'Extraction failed'), loading: false }));
    }
  };

  const handleToggleDocOutdated = async (doc, makeOutdated) => {
    try {
      if (makeOutdated) {
        await frontlineAgentService.markFrontlineDocumentOutdated(doc.id);
        toast({ title: 'Document marked outdated', description: 'Excluded from knowledge retrieval until restored.' });
      } else {
        await frontlineAgentService.unmarkFrontlineDocumentOutdated(doc.id);
        toast({ title: 'Document restored', description: 'Back in knowledge retrieval.' });
      }
      setDocuments((arr) => arr.map((x) => x.id === doc.id ? { ...x, is_outdated: makeOutdated } : x));
    } catch (e) {
      toast({
        title: makeOutdated ? 'Mark-outdated failed' : 'Restore failed',
        description: e.message,
        variant: 'destructive',
      });
    }
  };

  /** Inline summary toggle for the Documents card grid.
   *  First click on a card fetches the summary (short — 3 sentences) and expands.
   *  Subsequent clicks just flip expanded without re-fetching. */
  const toggleDocSummary = async (doc) => {
    const cur = docSummaries[doc.id];
    if (cur?.summary) {
      setDocSummaries((m) => ({ ...m, [doc.id]: { ...cur, expanded: !cur.expanded } }));
      return;
    }
    setDocSummaries((m) => ({ ...m, [doc.id]: { summary: null, loading: true, expanded: true, error: null } }));
    try {
      const response = await frontlineAgentService.summarizeDocument(doc.id, { max_sentences: 3 });
      const summary = response?.data?.summary ?? response?.summary ?? '';
      setDocSummaries((m) => ({ ...m, [doc.id]: { summary, loading: false, expanded: true, error: null } }));
    } catch (error) {
      setDocSummaries((m) => ({
        ...m,
        [doc.id]: { summary: null, loading: false, expanded: true, error: error.message || 'Failed to summarize' },
      }));
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

  // Delete the contact currently shown in the Customer-360 dialog. Tickets
  // that reference this contact stay (the FK is set null on delete); the
  // contact's notes cascade away. Confirmation is delegated to a custom
  // dialog instead of window.confirm to match the rest of the dashboard UX.
  const [deleteContactConfirm, setDeleteContactConfirm] = useState({ open: false, busy: false });
  const handleDeleteContact = async () => {
    const contact = customerDialog.contact;
    if (!contact) return;
    setDeleteContactConfirm((d) => ({ ...d, busy: true }));
    try {
      await frontlineAgentService.deleteContact(contact.id);
      toast({ title: 'Contact deleted', description: contact.email });
      setDeleteContactConfirm({ open: false, busy: false });
      setCustomerDialog((prev) => ({ ...prev, open: false, contact: null }));
    } catch (e) {
      toast({ title: 'Delete failed', description: e.message || 'Unknown error', variant: 'destructive' });
      setDeleteContactConfirm((d) => ({ ...d, busy: false }));
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
      toast({ title: 'Error', description: apiErrorMessage(error, 'Failed to get answer'), variant: 'destructive' });
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
    <HintsProvider>
    <div
      className="w-full rounded-2xl border border-white/[0.06] p-0"
      style={{ background: 'linear-gradient(90deg, #020308 0%, #020308 55%, rgba(10,37,64,0.68) 85%, rgba(14,39,71,0.52) 100%)' }}
    >
    <div className="space-y-6 w-full max-w-full overflow-x-hidden p-4 md:p-6 lg:p-8">
      {/* Take the Tour + Hints toggle */}
      <div className="flex justify-end items-center gap-2">
        <HintsToggleButton />
        <button
          type="button"
          onClick={handleReplayTutorial}
          data-tour="replay"
          title="Replay the onboarding tutorial"
          className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg border border-amber-400/40 bg-amber-400/10 text-amber-300 text-sm font-semibold hover:bg-amber-400/20 hover:text-amber-200 transition"
        >
          <GraduationCap className="h-4 w-4" />
          Take the Tour
        </button>
      </div>

      {/* Stats Overview */}
      <div data-tour="stats" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6 sm:mb-8 w-full">
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
        <div data-tour="tabs" className="hidden lg:block overflow-x-auto pb-1">
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
                  data-tour-tab={item.value}
                  className="whitespace-nowrap shrink-0 px-4 py-2 text-sm font-medium rounded-md border transition-all duration-150"
                  style={activeTab === item.value
                    ? {
                        background: 'linear-gradient(90deg, #f59e0b 0%, #f97316 100%)',
                        color: '#fff',
                        border: '1.5px solid #f59e0b',
                        boxShadow: '0 0 8px 0 #f59e0b55',
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
          <div className="flex justify-end mb-3"><TabTourButton tabKey="overview" /></div>
          {/* Admin insights — SLA / KB / DLQ / audit log tiles. Lazy-fetched. */}
          <div data-tour-ov="insights" className="mb-5 relative">
            <div className="absolute -top-1 right-1 z-10"><InfoHint {...HINTS.ovInsights} /></div>
            <FrontlineInsightsPanel />
          </div>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs uppercase tracking-wider text-white/40 font-semibold">Quick jump</span>
            <InfoHint {...HINTS.ovQuicknav} />
          </div>
          <div data-tour-ov="quicknav" className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-6 w-full min-w-0">
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
          <div className="flex justify-end"><TabTourButton tabKey="documents" /></div>
          <Card className="w-full min-w-0">
            <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <CardTitle>Documents</CardTitle>
                  <InfoHint {...HINTS.docsGrid} />
                </div>
                <CardDescription>Upload and manage knowledge base documents</CardDescription>
              </div>
              <div className="flex items-center gap-2 w-full sm:w-auto shrink-0">
                <Button data-tour-docs="upload" onClick={() => setShowUploadDialog(true)} className="w-full sm:w-auto">
                  <Upload className="mr-2 h-4 w-4" />
                  Upload Document
                </Button>
                <InfoHint {...HINTS.docsUpload} />
              </div>
            </CardHeader>
            <CardContent>
              {documents.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <div className="h-14 w-14 rounded-2xl bg-violet-500/10 border border-violet-400/20 flex items-center justify-center mb-3">
                    <FileText className="h-7 w-7 text-violet-400" />
                  </div>
                  <div className="font-medium mb-1">No documents yet</div>
                  <div className="text-sm text-muted-foreground max-w-sm">
                    Upload a document to give the knowledge agent something to answer from.
                  </div>
                </div>
              ) : (
                <div data-tour-docs="grid" className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                  {documents.map((doc) => {
                    const fmt = (doc.file_format || 'other').toLowerCase();
                    const fmtColor = {
                      pdf: 'bg-rose-500/15 text-rose-400 border-rose-400/30',
                      docx: 'bg-violet-500/15 text-violet-400 border-violet-400/30',
                      doc: 'bg-violet-500/15 text-violet-400 border-violet-400/30',
                      txt: 'bg-white/[0.04] text-white/55 border-white/[0.08]',
                      md: 'bg-emerald-500/15 text-emerald-400 border-emerald-400/30',
                      html: 'bg-amber-500/15 text-amber-400 border-amber-400/30',
                    }[fmt] || 'bg-violet-500/15 text-violet-400 border-violet-400/30';
                    const sizeKB = doc.file_size ? Math.max(1, Math.round(doc.file_size / 1024)) : null;
                    const sizeDisplay = sizeKB && sizeKB >= 1024
                      ? `${(sizeKB / 1024).toFixed(1)} MB`
                      : (sizeKB ? `${sizeKB} KB` : null);
                    const summaryState = docSummaries[doc.id];
                    const procStatus = doc.processing_status || (doc.is_indexed ? 'ready' : 'pending');
                    const procLabel = {
                      ready: 'Indexed',
                      processing: 'Processing',
                      pending: 'Queued',
                      failed: 'Failed',
                    }[procStatus] || procStatus;
                    const procColor = {
                      ready: 'bg-emerald-500/15 text-emerald-400 border-emerald-400/30',
                      processing: 'bg-violet-500/15 text-violet-400 border-violet-400/30',
                      pending: 'bg-white/[0.04] text-white/55 border-white/[0.08]',
                      failed: 'bg-rose-500/15 text-rose-400 border-rose-400/30',
                    }[procStatus] || 'bg-white/[0.04] text-white/55 border-white/[0.08]';

                    return (
                      <div
                        key={doc.id}
                        className="group flex flex-col rounded-xl border border-white/[0.08] bg-gradient-to-br from-white/[0.04] to-white/[0.01] hover:border-violet-400/40 hover:shadow-[0_0_0_1px_rgba(139,92,246,0.15),0_8px_32px_-8px_rgba(139,92,246,0.25)] transition-all duration-200 overflow-hidden"
                      >
                        {/* Header row: format badge + title + status */}
                        <div className="p-4 pb-3">
                          <div className="flex items-start gap-3">
                            <div className={`shrink-0 h-10 w-10 rounded-lg border flex items-center justify-center ${fmtColor}`}>
                              <FileText className="h-5 w-5" />
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="font-medium truncate text-sm" title={doc.title}>{doc.title}</div>
                              <div className="mt-0.5 text-xs text-muted-foreground truncate">
                                {fmt.toUpperCase()}
                                {doc.document_type ? ` • ${doc.document_type.replace(/_/g, ' ')}` : ''}
                                {sizeDisplay ? ` • ${sizeDisplay}` : ''}
                              </div>
                            </div>
                          </div>
                          <div className="mt-3 flex items-center gap-1.5 flex-wrap">
                            <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${procColor}`}>
                              {procLabel}
                            </Badge>
                            {doc.is_outdated && (
                              <Badge variant="outline" className="text-[10px] px-1.5 py-0 bg-rose-500/10 text-rose-300 border-rose-400/30">
                                outdated
                              </Badge>
                            )}
                            {doc.created_at && (
                              <span className="text-[10px] text-muted-foreground">
                                {new Date(doc.created_at).toLocaleDateString()}
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Expandable summary area */}
                        <div className="px-4 pb-3 flex-1">
                          {summaryState?.expanded ? (
                            <div className="rounded-md bg-black/20 border border-white/[0.06] p-3 text-xs text-white/80 space-y-2">
                              {summaryState.loading ? (
                                <div className="flex items-center gap-2 text-muted-foreground">
                                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                  <span>Generating summary...</span>
                                </div>
                              ) : summaryState.error ? (
                                <div className="text-rose-400">{summaryState.error}</div>
                              ) : (
                                <div className="whitespace-pre-wrap break-words leading-relaxed">
                                  {summaryState.summary || 'No summary available.'}
                                </div>
                              )}
                              <button
                                onClick={() => toggleDocSummary(doc)}
                                disabled={summaryState.loading}
                                className="text-violet-400 hover:text-violet-300 text-[11px] font-medium flex items-center gap-0.5"
                              >
                                Show less <ChevronUp className="h-3 w-3" />
                              </button>
                            </div>
                          ) : (
                            <button
                              onClick={() => toggleDocSummary(doc)}
                              className="text-violet-400 hover:text-violet-300 text-xs font-medium flex items-center gap-0.5"
                            >
                              Show summary <ChevronDown className="h-3 w-3" />
                            </button>
                          )}
                        </div>

                        {/* Action bar */}
                        <div data-tour-docs="card-actions" className="border-t border-white/[0.06] px-2 py-1.5 flex items-center justify-between bg-black/10">
                          <div className="flex items-center">
                            <InfoHint {...HINTS.docsCardActions} className="ml-1 mr-2" />
                            <Button variant="ghost" size="sm" className="h-8 px-2 text-xs" onClick={() => handleSummarizeDocument(doc)} title="Full summary">
                              <FileSearch className="h-3.5 w-3.5 mr-1" /> Summarize
                            </Button>
                            <Button variant="ghost" size="sm" className="h-8 px-2 text-xs" onClick={() => handleExtractDocument(doc)} title="Extract structured data">
                              <ListChecks className="h-3.5 w-3.5 mr-1" /> Extract
                            </Button>
                            {doc.is_outdated ? (
                              <Button variant="ghost" size="sm" className="h-8 px-2 text-xs text-emerald-400 hover:text-emerald-300"
                                onClick={() => handleToggleDocOutdated(doc, false)}
                                title="Restore — bring this doc back into retrieval">
                                Restore
                              </Button>
                            ) : (
                              <Button variant="ghost" size="sm" className="h-8 px-2 text-xs text-amber-400 hover:text-amber-300"
                                onClick={() => handleToggleDocOutdated(doc, true)}
                                title="Mark outdated — excluded from knowledge retrieval until restored">
                                Outdated
                              </Button>
                            )}
                          </div>
                          <Button variant="ghost" size="sm" className="h-8 w-8 p-0 text-muted-foreground hover:text-rose-400" onClick={() => handleDeleteDocument(doc.id)} title="Delete">
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
          </ErrorBoundary>
        </TabsContent>

        {/* Knowledge Q&A Tab - Chat UI with sidebar */}
        <TabsContent value="qa" className="space-y-4 mt-4">
          <ErrorBoundary>
          <div className="flex justify-end mb-2"><TabTourButton tabKey="qa" /></div>
          <div
            className="w-full rounded-2xl border border-white/[0.06] p-0 overflow-hidden"
            style={{
              background:
                'linear-gradient(90deg, #020308 0%, #020308 55%, rgba(10,37,64,0.68) 85%, rgba(14,39,71,0.52) 100%)',
            }}
          >
            <div className="flex w-full max-w-full relative">
              <div
                data-tour-qa="sidebar"
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
                      <div className="flex items-center gap-1.5">
                        <span className="text-base font-semibold text-white/90 tracking-wide">Frontline</span>
                        <InfoHint {...HINTS.qaSidebar} />
                      </div>
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
                          data-tour-qa="new-chat"
                          onClick={newChat}
                          title="New chat"
                          className="h-7 w-7 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60 bg-black/20 hover:bg-violet-700/20 transition-all duration-150"
                        >
                          <Plus className="h-4 w-4 text-white/80" />
                        </button>
                        <InfoHint {...HINTS.qaNewChat} />
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
                    <InfoHint {...HINTS.qaMessages} />
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
                  <div data-tour-qa="messages" className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-4 py-4 space-y-4">
                  {!selectedChatId && chats.length === 0 && (
                    <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                      <MessageCircle className="h-12 w-12 mb-4 opacity-50" />
                      <p className="font-medium">Ask your first question</p>
                      <p className="text-sm">Type a question to get an answer from your knowledge base.</p>
                      {documents.length === 0 && (
                        <p className="text-xs mt-2 text-amber-600 dark:text-amber-400">💡 Tip: Upload documents in the Documents tab first</p>
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
                                <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400 mt-0.5 flex-shrink-0" />
                              ) : (
                                <XCircle className="h-4 w-4 text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" />
                              )}
                              <div className="flex-1 min-w-0">
                                <div className="text-sm text-foreground whitespace-pre-wrap break-words">
                                  {msg.responseData?.answer ?? msg.content}
                                </div>
                                {msg.responseData?.confidence === 'low' && (
                                  <div className="mt-2 text-xs rounded-md px-2 py-1 bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/30">
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
                    data-tour-qa="input"
                    onSubmit={handleAskQuestion}
                    className="shrink-0"
                    style={{
                      background: '#0a0a0f',
                      borderTop: '1px solid rgba(255,255,255,0.08)',
                    }}
                  >
                    <div className="mx-4 my-4 space-y-3 rounded-2xl px-4 py-4" style={{ border: '1px solid rgba(255,255,255,0.08)' }}>
                      <div className="space-y-2" data-tour-qa="scope">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm text-muted-foreground">Answer from:</span>
                          <InfoHint {...HINTS.qaScope} />
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

                      <div className="flex gap-2 items-start">
                        <div className="pt-2"><InfoHint {...HINTS.qaInput} /></div>
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
          <div className="flex justify-end"><TabTourButton tabKey="widget" /></div>
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
                  <div data-tour-widget="key" className="space-y-1">
                    <div className="flex items-center gap-1.5">
                      <Label className="text-muted-foreground">Your widget key</Label>
                      <InfoHint {...HINTS.widgetKey} />
                    </div>
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
                  <div data-tour-widget="origins" className="space-y-1">
                    <div className="flex items-center gap-1.5">
                      <Label className="text-muted-foreground">Allowed origins</Label>
                      <InfoHint {...HINTS.widgetOrigins} />
                    </div>
                    <p className="text-xs text-muted-foreground mb-1">
                      Comma-separated list of domains permitted to use this widget key (e.g.
                      <code className="mx-1 px-1 rounded bg-muted text-[10px]">https://example.com,https://app.example.com</code>).
                      Leave blank to accept any origin — best for testing, risky for prod.
                      Requests from other origins are rejected with 403.
                    </p>
                    <div className="flex items-center gap-2">
                      <Input
                        value={allowedOrigins}
                        onChange={(e) => setAllowedOrigins(e.target.value)}
                        placeholder="https://example.com, https://app.example.com"
                        className="flex-1"
                      />
                      <Button onClick={handleSaveAllowedOrigins} disabled={allowedOriginsSaving}>
                        {allowedOriginsSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : null}
                        Save
                      </Button>
                    </div>
                  </div>

                  {/* Theming — pure customisation. Empty values use widget defaults. */}
                  <div data-tour-widget="theme" className="space-y-2 rounded-lg border border-white/[0.06] bg-black/20 p-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <Label className="text-muted-foreground">Theme & appearance</Label>
                        <InfoHint {...HINTS.widgetTheme} />
                      </div>
                      <Button size="sm" onClick={handleSaveTheme} disabled={themeSaving}>
                        {themeSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : null}
                        Save theme
                      </Button>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      All fields optional — blank inputs fall back to the widget's defaults.
                      Customers see these on the embedded chat. CSS overrides are an escape hatch
                      for white-label partners; powerful but unvalidated.
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                      <div>
                        <Label className="text-xs">Primary colour</Label>
                        <Input placeholder="#7c3aed"
                          value={widgetTheme.primary_color}
                          onChange={(e) => setWidgetTheme((s) => ({ ...s, primary_color: e.target.value }))} />
                      </div>
                      <div>
                        <Label className="text-xs">Font family</Label>
                        <Input placeholder='"Inter", system-ui, sans-serif'
                          value={widgetTheme.font_family}
                          onChange={(e) => setWidgetTheme((s) => ({ ...s, font_family: e.target.value }))} />
                      </div>
                      <div>
                        <Label className="text-xs">Border radius</Label>
                        <Input placeholder="12px or 0.75rem"
                          value={widgetTheme.border_radius}
                          onChange={(e) => setWidgetTheme((s) => ({ ...s, border_radius: e.target.value }))} />
                      </div>
                      <div>
                        <Label className="text-xs">Header background</Label>
                        <Input placeholder="defaults to primary colour"
                          value={widgetTheme.header_bg}
                          onChange={(e) => setWidgetTheme((s) => ({ ...s, header_bg: e.target.value }))} />
                      </div>
                      <div>
                        <Label className="text-xs">Header text colour</Label>
                        <Input placeholder="#ffffff"
                          value={widgetTheme.header_text_color}
                          onChange={(e) => setWidgetTheme((s) => ({ ...s, header_text_color: e.target.value }))} />
                      </div>
                      <div>
                        <Label className="text-xs">User bubble bg</Label>
                        <Input placeholder="#eef2ff"
                          value={widgetTheme.bubble_bg_user}
                          onChange={(e) => setWidgetTheme((s) => ({ ...s, bubble_bg_user: e.target.value }))} />
                      </div>
                      <div>
                        <Label className="text-xs">Agent bubble bg</Label>
                        <Input placeholder="#f8fafc"
                          value={widgetTheme.bubble_bg_agent}
                          onChange={(e) => setWidgetTheme((s) => ({ ...s, bubble_bg_agent: e.target.value }))} />
                      </div>
                    </div>
                    <div>
                      <Label className="text-xs">Custom CSS overrides</Label>
                      <textarea
                        rows={3}
                        placeholder="/* injected into the widget's shadow DOM — use sparingly */"
                        value={widgetTheme.css_overrides}
                        onChange={(e) => setWidgetTheme((s) => ({ ...s, css_overrides: e.target.value }))}
                        className="w-full mt-1 rounded-md border border-white/10 bg-black/30 px-2 py-1.5 text-xs font-mono text-white/85 placeholder:text-white/30 focus:outline-none focus:ring-1 focus:ring-violet-400/50 resize-none"
                      />
                    </div>
                  </div>
                  <div data-tour-widget="embed" className="space-y-1">
                    <div className="flex items-center gap-1.5">
                      <Label className="text-muted-foreground">Embed on your site (floating chat button)</Label>
                      <InfoHint {...HINTS.widgetEmbed} />
                    </div>
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
          <div className="flex justify-end"><TabTourButton tabKey="tickets" /></div>
          <Card className="w-full min-w-0">
            <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <CardTitle>Support Tickets</CardTitle>
                  <InfoHint {...HINTS.ticketsTable} />
                </div>
                <CardDescription>Create and filter your support tickets</CardDescription>
              </div>
              <div className="flex items-center gap-2 w-full sm:w-auto shrink-0">
                <Button data-tour-tickets="create" onClick={() => setShowTicketDialog(true)} className="w-full sm:w-auto">
                  <Ticket className="mr-2 h-4 w-4" />
                  Create Ticket
                </Button>
                <InfoHint {...HINTS.ticketsCreate} />
              </div>
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
              <div data-tour-tickets="filters" className="flex flex-wrap items-center gap-2">
                <InfoHint {...HINTS.ticketsFilters} />
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
                  {/* Bulk action bar — appears when at least one row is selected. */}
                  {selectedTicketIds.size > 0 && (
                    <div data-tour-tickets="bulk-hint" className="flex items-center gap-2 flex-wrap rounded-lg border border-violet-400/30 bg-violet-500/10 px-3 py-2 mb-2">
                      <InfoHint {...HINTS.ticketsBulk} />
                      <span className="text-sm font-medium text-violet-200">
                        {selectedTicketIds.size} selected
                      </span>
                      <div className="flex items-center gap-1 ml-2 flex-wrap">
                        <Button size="sm" variant="outline" className="h-7 text-xs"
                          onClick={() => setBulkActionDialog({ open: true, field: 'status', value: '' })}>
                          Change status…
                        </Button>
                        <Button size="sm" variant="outline" className="h-7 text-xs"
                          onClick={() => setBulkActionDialog({ open: true, field: 'priority', value: '' })}>
                          Change priority…
                        </Button>
                        <Button size="sm" variant="outline" className="h-7 text-xs"
                          onClick={() => setBulkActionDialog({ open: true, field: 'category', value: '' })}>
                          Change category…
                        </Button>
                      </div>
                      <Button size="sm" variant="ghost" className="h-7 ml-auto text-xs"
                        onClick={clearTicketSelection}>
                        <XIcon className="h-3.5 w-3.5 mr-1" /> Clear
                      </Button>
                    </div>
                  )}
                  <div data-tour-tickets="table" className="overflow-x-auto -mx-2 sm:mx-0">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-8">
                          <button onClick={toggleAllTicketsOnPage}
                            title={ticketsList.every((t) => selectedTicketIds.has(t.id))
                              ? 'Deselect all on page' : 'Select all on page'}
                            className="text-white/50 hover:text-white/90">
                            {ticketsList.every((t) => selectedTicketIds.has(t.id))
                              ? <CheckSquare className="h-4 w-4" />
                              : <Square className="h-4 w-4" />}
                          </button>
                        </TableHead>
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
                          <TableCell className="w-8">
                            <button onClick={() => toggleTicketSelected(t.id)}
                              className="text-white/50 hover:text-white/90"
                              title={selectedTicketIds.has(t.id) ? 'Deselect' : 'Select'}>
                              {selectedTicketIds.has(t.id)
                                ? <CheckSquare className="h-4 w-4 text-violet-400" />
                                : <Square className="h-4 w-4" />}
                            </button>
                          </TableCell>
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
                          <TableCell>{t.auto_resolved ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : '—'}</TableCell>
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
          <div className="flex justify-end"><TabTourButton tabKey="handoffs" /></div>
          <ErrorBoundary><HandoffQueueTab /></ErrorBoundary>
        </TabsContent>

        {/* Notifications Tab */}
        <TabsContent value="notifications" className="space-y-4 mt-4">
          <div className="flex justify-end"><TabTourButton tabKey="notifications" /></div>
          <ErrorBoundary><FrontlineNotificationsTab /></ErrorBoundary>
        </TabsContent>

        {/* Workflows Tab */}
        <TabsContent value="workflows" className="space-y-4 mt-4">
          <div className="flex justify-end"><TabTourButton tabKey="workflows" /></div>
          <ErrorBoundary><FrontlineWorkflowsTab /></ErrorBoundary>
        </TabsContent>

        {/* Analytics Tab */}
        <TabsContent value="analytics" className="space-y-4 mt-4">
          <div className="flex justify-end"><TabTourButton tabKey="analytics" /></div>
          <ErrorBoundary><FrontlineAnalyticsTab /></ErrorBoundary>
        </TabsContent>

        {/* AI Graphs Tab */}
        <TabsContent value="ai-graphs" className="space-y-4 mt-4">
          <div className="flex justify-end"><TabTourButton tabKey="ai-graphs" /></div>
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
                    <div className="min-w-0 flex-1">
                      <div className="font-medium truncate">
                        {customerDialog.contact.name || customerDialog.contact.email}
                      </div>
                      <div className="text-xs text-muted-foreground truncate">
                        {customerDialog.contact.email}
                        {customerDialog.contact.phone ? ` · ${customerDialog.contact.phone}` : ''}
                      </div>
                    </div>
                    {/* Hard-delete the contact record. Tickets stay; their
                        contact reference is detached (FK null-on-delete). */}
                    <Button
                      variant="ghost" size="icon"
                      className="h-8 w-8 text-destructive hover:text-destructive shrink-0"
                      title="Delete contact"
                      onClick={() => setDeleteContactConfirm({ open: true, busy: false })}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
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

      {/* Delete-contact confirmation. Two-step on purpose because deleting a
          contact is destructive: it detaches them from any open tickets and
          drops their custom_fields/tags. */}
      <Dialog open={deleteContactConfirm.open} onOpenChange={(open) => !open && !deleteContactConfirm.busy && setDeleteContactConfirm({ open: false, busy: false })}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-destructive flex items-center gap-2">
              <Trash2 className="h-4 w-4" /> Delete contact?
            </DialogTitle>
            <DialogDescription>
              Permanently removes <strong>{customerDialog.contact?.email}</strong>. Past tickets remain
              but lose the link to this contact record. Notes attached to the
              contact will be deleted.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteContactConfirm({ open: false, busy: false })} disabled={deleteContactConfirm.busy}>Cancel</Button>
            <Button variant="destructive" onClick={handleDeleteContact} disabled={deleteContactConfirm.busy}>
              {deleteContactConfirm.busy ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Trash2 className="h-4 w-4 mr-1" />}
              Delete contact
            </Button>
          </DialogFooter>
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

      {/* Bulk ticket update dialog (#3). Reused across status / priority /
          category — the trigger button decides which field. */}
      <Dialog open={bulkActionDialog.open}
        onOpenChange={(o) => setBulkActionDialog((s) => ({ ...s, open: o }))}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {bulkActionDialog.field === 'status' && 'Change status'}
              {bulkActionDialog.field === 'priority' && 'Change priority'}
              {bulkActionDialog.field === 'category' && 'Change category'}
            </DialogTitle>
            <DialogDescription>
              Applies to {selectedTicketIds.size} selected ticket{selectedTicketIds.size === 1 ? '' : 's'}.
              {bulkActionDialog.field === 'status' && ' Illegal status transitions are skipped per ticket; you\'ll see the count in the result.'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Label className="text-xs">New value</Label>
            {bulkActionDialog.field === 'status' && (
              <Select value={bulkActionDialog.value}
                onValueChange={(v) => setBulkActionDialog((s) => ({ ...s, value: v }))}>
                <SelectTrigger><SelectValue placeholder="Pick a status" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="open">open</SelectItem>
                  <SelectItem value="in_progress">in_progress</SelectItem>
                  <SelectItem value="resolved">resolved</SelectItem>
                  <SelectItem value="closed">closed</SelectItem>
                </SelectContent>
              </Select>
            )}
            {bulkActionDialog.field === 'priority' && (
              <Select value={bulkActionDialog.value}
                onValueChange={(v) => setBulkActionDialog((s) => ({ ...s, value: v }))}>
                <SelectTrigger><SelectValue placeholder="Pick a priority" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="low">low</SelectItem>
                  <SelectItem value="medium">medium</SelectItem>
                  <SelectItem value="high">high</SelectItem>
                  <SelectItem value="urgent">urgent</SelectItem>
                </SelectContent>
              </Select>
            )}
            {bulkActionDialog.field === 'category' && (
              <Select value={bulkActionDialog.value}
                onValueChange={(v) => setBulkActionDialog((s) => ({ ...s, value: v }))}>
                <SelectTrigger><SelectValue placeholder="Pick a category" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="technical">technical</SelectItem>
                  <SelectItem value="billing">billing</SelectItem>
                  <SelectItem value="account">account</SelectItem>
                  <SelectItem value="feature_request">feature_request</SelectItem>
                  <SelectItem value="bug">bug</SelectItem>
                  <SelectItem value="knowledge_gap">knowledge_gap</SelectItem>
                  <SelectItem value="other">other</SelectItem>
                </SelectContent>
              </Select>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline"
              onClick={() => setBulkActionDialog({ open: false, field: null, value: '' })}
              disabled={bulkApplying}>Cancel</Button>
            <Button onClick={handleBulkApply}
              disabled={bulkApplying || !bulkActionDialog.value}>
              {bulkApplying ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
              Apply to {selectedTicketIds.size}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* First-time onboarding tutorial (main tour) */}
      <FrontlineTutorial
        open={tutorialOpen}
        onClose={() => setTutorialOpen(false)}
        setActiveTab={setActiveTab}
      />

      {/* Per-tab guided tour */}
      {activeTabTour && TAB_TOURS[activeTabTour] && (
        <FrontlineTutorial
          open={!!activeTabTour}
          onClose={() => setActiveTabTour(null)}
          steps={TAB_TOURS[activeTabTour].steps}
          storageKey={TAB_TOURS[activeTabTour].key}
        />
      )}
    </div>
    </div>
    {/* Floating quick-chat launcher — pinned bottom-right of the viewport,
        rendered via portal so it stays put across every tab. */}
    <FrontlineFloatingChat />
    </HintsProvider>
  );
};

export default FrontlineDashboard;

