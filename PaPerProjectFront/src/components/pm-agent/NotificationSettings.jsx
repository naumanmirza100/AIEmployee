import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import { Checkbox } from '@/components/ui/checkbox';
import pmAgentService from '@/services/pmAgentService';
import { Loader2, Trash2, Send, Plus, Pencil, X, Check } from 'lucide-react';
import ConfirmDialog from '@/components/common/ConfirmDialog';

const CHANNEL_TYPES = [
  { value: 'slack', label: 'Slack (webhook)' },
  { value: 'teams', label: 'Microsoft Teams (webhook)' },
  { value: 'email', label: 'Extra Email Recipient' },
];

const SEVERITY_OPTIONS = ['info', 'warning', 'critical'];

const NOTIFICATION_TYPES = [
  'overdue_task', 'blocked_task', 'unassigned_high_priority', 'deadline_approaching',
  'workload_imbalance', 'project_at_risk', 'member_inactive', 'milestone_due',
  'sprint_overloaded', 'custom',
];

export default function NotificationSettings() {
  const { toast } = useToast();

  // ---------------- Channels ----------------
  const [channels, setChannels] = useState([]);
  const [channelsLoading, setChannelsLoading] = useState(false);
  const [newChannel, setNewChannel] = useState({
    name: '', channel_type: 'slack', target: '', severities: 'info,warning,critical', types: '', is_active: true,
  });
  const [savingChannel, setSavingChannel] = useState(false);

  // ---------------- Templates ---------------
  const [templates, setTemplates] = useState([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [newTemplate, setNewTemplate] = useState({
    notification_type: 'overdue_task', name: '', title_template: '', message_template: '', default_severity: 'info', is_active: true,
  });
  const [savingTemplate, setSavingTemplate] = useState(false);

  // Generic confirmation state — replaces window.confirm() throughout this file.
  // Caller sets the meta + onConfirm; dialog closes on cancel/confirm.
  const [confirm, setConfirm] = useState({
    open: false, title: '', description: '', confirmLabel: 'Delete', onConfirm: null, loading: false,
  });
  const closeConfirm = () => setConfirm((c) => ({ ...c, open: false }));

  // Inline-edit state — when non-null, the corresponding row swaps to a form.
  // We keep separate `editing*` (= id being edited) and `edit*Form` (= live
  // form values) so the original row data stays intact in `channels` /
  // `templates` until save succeeds.
  const [editingChannelId, setEditingChannelId] = useState(null);
  const [editChannelForm, setEditChannelForm] = useState(null);
  const [savingEditChannel, setSavingEditChannel] = useState(false);
  const [editingTemplateId, setEditingTemplateId] = useState(null);
  const [editTemplateForm, setEditTemplateForm] = useState(null);
  const [savingEditTemplate, setSavingEditTemplate] = useState(false);

  useEffect(() => {
    refreshChannels();
    refreshTemplates();
  }, []);

  const refreshChannels = async () => {
    setChannelsLoading(true);
    try {
      const res = await pmAgentService.listNotificationChannels();
      setChannels(res?.data || []);
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to load channels', variant: 'destructive' });
    } finally {
      setChannelsLoading(false);
    }
  };

  const refreshTemplates = async () => {
    setTemplatesLoading(true);
    try {
      const res = await pmAgentService.listNotificationTemplates();
      setTemplates(res?.data || []);
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to load templates', variant: 'destructive' });
    } finally {
      setTemplatesLoading(false);
    }
  };

  const createChannel = async () => {
    if (!newChannel.name.trim() || !newChannel.target.trim()) {
      toast({ title: 'Missing fields', description: 'Name and target are required', variant: 'destructive' });
      return;
    }
    setSavingChannel(true);
    try {
      await pmAgentService.createNotificationChannel(newChannel);
      toast({ title: 'Channel created' });
      setNewChannel({ name: '', channel_type: 'slack', target: '', severities: 'info,warning,critical', types: '', is_active: true });
      refreshChannels();
    } catch (e) {
      toast({ title: 'Error', description: e?.response?.data?.message || e.message, variant: 'destructive' });
    } finally {
      setSavingChannel(false);
    }
  };

  const toggleChannelActive = async (ch) => {
    try {
      await pmAgentService.updateNotificationChannel(ch.id, { is_active: !ch.is_active });
      refreshChannels();
    } catch (e) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    }
  };

  const removeChannel = (id) => {
    setConfirm({
      open: true,
      title: 'Delete this channel?',
      description: 'Notifications will stop going out through this channel. This cannot be undone.',
      confirmLabel: 'Delete channel',
      loading: false,
      onConfirm: async () => {
        setConfirm((c) => ({ ...c, loading: true }));
        try {
          await pmAgentService.deleteNotificationChannel(id);
          refreshChannels();
          closeConfirm();
        } catch (e) {
          toast({ title: 'Error', description: e.message, variant: 'destructive' });
          setConfirm((c) => ({ ...c, loading: false }));
        }
      },
    });
  };

  // ─── Channel edit-in-place ─────────────────────────────────────────
  const startEditChannel = (ch) => {
    setEditingChannelId(ch.id);
    setEditChannelForm({
      name: ch.name || '',
      channel_type: ch.channel_type || 'slack',
      target: ch.target || '',
      severities: ch.severities || 'info,warning,critical',
      types: ch.types || '',
    });
  };

  const cancelEditChannel = () => {
    setEditingChannelId(null);
    setEditChannelForm(null);
  };

  const saveEditedChannel = async () => {
    if (!editingChannelId || !editChannelForm) return;
    if (!editChannelForm.name.trim() || !editChannelForm.target.trim()) {
      toast({ title: 'Missing fields', description: 'Name and target are required', variant: 'destructive' });
      return;
    }
    setSavingEditChannel(true);
    try {
      await pmAgentService.updateNotificationChannel(editingChannelId, editChannelForm);
      toast({ title: 'Channel updated' });
      cancelEditChannel();
      refreshChannels();
    } catch (e) {
      toast({ title: 'Error', description: e?.response?.data?.message || e.message, variant: 'destructive' });
    } finally {
      setSavingEditChannel(false);
    }
  };

  const testChannel = async (id) => {
    try {
      const res = await pmAgentService.testNotificationChannel(id);
      if (res.status === 'success') {
        toast({ title: 'Test sent', description: 'Check your channel for the test message.' });
      } else {
        toast({ title: 'Test failed', description: res.message || 'Unknown error', variant: 'destructive' });
      }
      refreshChannels();
    } catch (e) {
      toast({ title: 'Test failed', description: e?.response?.data?.message || e.message, variant: 'destructive' });
    }
  };

  const createTemplate = async () => {
    if (!newTemplate.name.trim() || !newTemplate.title_template.trim() || !newTemplate.message_template.trim()) {
      toast({ title: 'Missing fields', description: 'Name, title, and message are required', variant: 'destructive' });
      return;
    }
    setSavingTemplate(true);
    try {
      await pmAgentService.createNotificationTemplate(newTemplate);
      toast({ title: 'Template created' });
      setNewTemplate({ notification_type: 'overdue_task', name: '', title_template: '', message_template: '', default_severity: 'info', is_active: true });
      refreshTemplates();
    } catch (e) {
      toast({ title: 'Error', description: e?.response?.data?.message || e.message, variant: 'destructive' });
    } finally {
      setSavingTemplate(false);
    }
  };

  const toggleTemplateActive = async (t) => {
    try {
      await pmAgentService.updateNotificationTemplate(t.id, { is_active: !t.is_active });
      refreshTemplates();
    } catch (e) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    }
  };

  const removeTemplate = (id) => {
    setConfirm({
      open: true,
      title: 'Delete this template?',
      description: 'Notifications of this type will fall back to the default template.',
      confirmLabel: 'Delete template',
      loading: false,
      onConfirm: async () => {
        setConfirm((c) => ({ ...c, loading: true }));
        try {
          await pmAgentService.deleteNotificationTemplate(id);
          refreshTemplates();
          closeConfirm();
        } catch (e) {
          toast({ title: 'Error', description: e.message, variant: 'destructive' });
          setConfirm((c) => ({ ...c, loading: false }));
        }
      },
    });
  };

  // ─── Template edit-in-place ────────────────────────────────────────
  const startEditTemplate = (t) => {
    setEditingTemplateId(t.id);
    setEditTemplateForm({
      notification_type: t.notification_type || 'overdue_task',
      name: t.name || '',
      title_template: t.title_template || '',
      message_template: t.message_template || '',
      default_severity: t.default_severity || 'info',
    });
  };

  const cancelEditTemplate = () => {
    setEditingTemplateId(null);
    setEditTemplateForm(null);
  };

  const saveEditedTemplate = async () => {
    if (!editingTemplateId || !editTemplateForm) return;
    if (!editTemplateForm.name.trim() || !editTemplateForm.title_template.trim() || !editTemplateForm.message_template.trim()) {
      toast({ title: 'Missing fields', description: 'Name, title, and message are required', variant: 'destructive' });
      return;
    }
    setSavingEditTemplate(true);
    try {
      await pmAgentService.updateNotificationTemplate(editingTemplateId, editTemplateForm);
      toast({ title: 'Template updated' });
      cancelEditTemplate();
      refreshTemplates();
    } catch (e) {
      toast({ title: 'Error', description: e?.response?.data?.message || e.message, variant: 'destructive' });
    } finally {
      setSavingEditTemplate(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Channels */}
      <Card className="bg-black/30 border-white/[0.06]">
        <CardHeader>
          <CardTitle className="text-lg text-violet-300">Notification Channels</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs text-white/55">
            Fan out PM notifications to Slack, Microsoft Teams, or extra emails. Add a webhook URL from the corresponding app.
          </p>

          {/* New channel form */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 p-3 rounded-lg border border-white/[0.06] bg-black/30">
            <div>
              <Label>Name</Label>
              <Input value={newChannel.name} onChange={(e) => setNewChannel({ ...newChannel, name: e.target.value })} placeholder="#pm-alerts" />
            </div>
            <div>
              <Label>Type</Label>
              <Select value={newChannel.channel_type} onValueChange={(v) => setNewChannel({ ...newChannel, channel_type: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {CHANNEL_TYPES.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="md:col-span-2">
              <Label>{newChannel.channel_type === 'email' ? 'Email address' : 'Webhook URL'}</Label>
              <Input value={newChannel.target} onChange={(e) => setNewChannel({ ...newChannel, target: e.target.value })} placeholder={newChannel.channel_type === 'email' ? 'alerts@example.com' : 'https://hooks.slack.com/services/...'} />
            </div>
            <div>
              <Label>Severities (comma-separated)</Label>
              <Input value={newChannel.severities} onChange={(e) => setNewChannel({ ...newChannel, severities: e.target.value })} placeholder="info,warning,critical" />
            </div>
            <div>
              <Label>Notification types filter (optional)</Label>
              <Input value={newChannel.types} onChange={(e) => setNewChannel({ ...newChannel, types: e.target.value })} placeholder="empty = all" />
            </div>
            <div className="md:col-span-2 flex justify-end">
              <Button onClick={createChannel} disabled={savingChannel}>
                {savingChannel ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Plus className="w-4 h-4 mr-2" />}
                Add Channel
              </Button>
            </div>
          </div>

          {channelsLoading ? (
            <Loader2 className="w-5 h-5 animate-spin mx-auto" />
          ) : channels.length === 0 ? (
            <p className="text-sm text-white/40">No channels configured yet.</p>
          ) : (
            <div className="space-y-2">
              {channels.map((ch) => {
                if (editingChannelId === ch.id && editChannelForm) {
                  // Inline edit form — mirrors the "new channel" form layout
                  // so users get the same UX for both flows.
                  return (
                    <div key={ch.id} className="grid grid-cols-1 md:grid-cols-2 gap-3 p-3 rounded-lg border border-amber-500/30 bg-amber-500/[0.04]">
                      <div>
                        <Label>Name</Label>
                        <Input value={editChannelForm.name} onChange={(e) => setEditChannelForm({ ...editChannelForm, name: e.target.value })} />
                      </div>
                      <div>
                        <Label>Type</Label>
                        <Select value={editChannelForm.channel_type} onValueChange={(v) => setEditChannelForm({ ...editChannelForm, channel_type: v })}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {CHANNEL_TYPES.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="md:col-span-2">
                        <Label>{editChannelForm.channel_type === 'email' ? 'Email address' : 'Webhook URL'}</Label>
                        <Input value={editChannelForm.target} onChange={(e) => setEditChannelForm({ ...editChannelForm, target: e.target.value })} />
                      </div>
                      <div>
                        <Label>Severities (comma-separated)</Label>
                        <Input value={editChannelForm.severities} onChange={(e) => setEditChannelForm({ ...editChannelForm, severities: e.target.value })} placeholder="info,warning,critical" />
                      </div>
                      <div>
                        <Label>Notification types filter (optional)</Label>
                        <Input value={editChannelForm.types} onChange={(e) => setEditChannelForm({ ...editChannelForm, types: e.target.value })} placeholder="empty = all" />
                      </div>
                      <div className="md:col-span-2 flex justify-end gap-2">
                        <Button size="sm" variant="ghost" onClick={cancelEditChannel} disabled={savingEditChannel}>
                          <X className="w-3 h-3 mr-1" /> Cancel
                        </Button>
                        <Button size="sm" onClick={saveEditedChannel} disabled={savingEditChannel}>
                          {savingEditChannel ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Check className="w-3 h-3 mr-1" />}
                          Save changes
                        </Button>
                      </div>
                    </div>
                  );
                }
                return (
                  <div key={ch.id} className="flex flex-wrap items-center gap-3 p-3 rounded border border-white/[0.06] bg-black/30/40">
                    <Checkbox checked={ch.is_active} onCheckedChange={() => toggleChannelActive(ch)} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-white truncate">{ch.name}</p>
                      <p className="text-xs text-white/55 truncate">
                        {ch.channel_type} · {ch.target}
                      </p>
                      <p className="text-xs text-white/40">severities: {ch.severities || 'all'}{ch.types ? ` · types: ${ch.types}` : ''}</p>
                      {ch.last_error && (
                        <p className="text-xs text-red-400 mt-1">Last error: {ch.last_error}</p>
                      )}
                    </div>
                    <Button size="sm" variant="outline" onClick={() => testChannel(ch.id)}>
                      <Send className="w-3 h-3 mr-1" /> Test
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => startEditChannel(ch)} title="Edit channel">
                      <Pencil className="w-3 h-3 text-white/70" />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => removeChannel(ch.id)} title="Delete channel">
                      <Trash2 className="w-3 h-3 text-red-400" />
                    </Button>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Templates */}
      <Card className="bg-black/30 border-white/[0.06]">
        <CardHeader>
          <CardTitle className="text-lg text-violet-300">Notification Templates</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs text-white/55">
            Override the wording for a given notification type. Use <code>{'{placeholders}'}</code> like <code>{'{meeting_title}'}</code>, <code>{'{pending_names}'}</code>, <code>{'{reminder_text}'}</code>, <code>{'{time_display}'}</code>.
          </p>

          {/* New template form */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 p-3 rounded-lg border border-white/[0.06] bg-black/30">
            <div>
              <Label>Notification type</Label>
              <Select value={newTemplate.notification_type} onValueChange={(v) => setNewTemplate({ ...newTemplate, notification_type: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {NOTIFICATION_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Template name</Label>
              <Input value={newTemplate.name} onChange={(e) => setNewTemplate({ ...newTemplate, name: e.target.value })} placeholder="Polite reminder" />
            </div>
            <div className="md:col-span-2">
              <Label>Title template</Label>
              <Input value={newTemplate.title_template} onChange={(e) => setNewTemplate({ ...newTemplate, title_template: e.target.value })} placeholder="Reminder: {meeting_title} starts soon" />
            </div>
            <div className="md:col-span-2">
              <Label>Message template</Label>
              <Textarea value={newTemplate.message_template} onChange={(e) => setNewTemplate({ ...newTemplate, message_template: e.target.value })} placeholder="Hi! Your meeting {meeting_title} starts {reminder_text}." rows={3} />
            </div>
            <div>
              <Label>Default severity</Label>
              <Select value={newTemplate.default_severity} onValueChange={(v) => setNewTemplate({ ...newTemplate, default_severity: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {SEVERITY_OPTIONS.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="md:col-span-2 flex justify-end">
              <Button onClick={createTemplate} disabled={savingTemplate}>
                {savingTemplate ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Plus className="w-4 h-4 mr-2" />}
                Add Template
              </Button>
            </div>
          </div>

          {templatesLoading ? (
            <Loader2 className="w-5 h-5 animate-spin mx-auto" />
          ) : templates.length === 0 ? (
            <p className="text-sm text-white/40">No custom templates yet — defaults will be used.</p>
          ) : (
            <div className="space-y-2">
              {templates.map((t) => {
                if (editingTemplateId === t.id && editTemplateForm) {
                  // Inline edit form — mirrors the "new template" form layout.
                  return (
                    <div key={t.id} className="grid grid-cols-1 md:grid-cols-2 gap-3 p-3 rounded-lg border border-amber-500/30 bg-amber-500/[0.04]">
                      <div>
                        <Label>Notification type</Label>
                        <Select value={editTemplateForm.notification_type} onValueChange={(v) => setEditTemplateForm({ ...editTemplateForm, notification_type: v })}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {NOTIFICATION_TYPES.map((tp) => <SelectItem key={tp} value={tp}>{tp}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label>Template name</Label>
                        <Input value={editTemplateForm.name} onChange={(e) => setEditTemplateForm({ ...editTemplateForm, name: e.target.value })} />
                      </div>
                      <div className="md:col-span-2">
                        <Label>Title template</Label>
                        <Input value={editTemplateForm.title_template} onChange={(e) => setEditTemplateForm({ ...editTemplateForm, title_template: e.target.value })} />
                      </div>
                      <div className="md:col-span-2">
                        <Label>Message template</Label>
                        <Textarea value={editTemplateForm.message_template} onChange={(e) => setEditTemplateForm({ ...editTemplateForm, message_template: e.target.value })} rows={3} />
                      </div>
                      <div>
                        <Label>Default severity</Label>
                        <Select value={editTemplateForm.default_severity} onValueChange={(v) => setEditTemplateForm({ ...editTemplateForm, default_severity: v })}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {SEVERITY_OPTIONS.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="md:col-span-2 flex justify-end gap-2">
                        <Button size="sm" variant="ghost" onClick={cancelEditTemplate} disabled={savingEditTemplate}>
                          <X className="w-3 h-3 mr-1" /> Cancel
                        </Button>
                        <Button size="sm" onClick={saveEditedTemplate} disabled={savingEditTemplate}>
                          {savingEditTemplate ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Check className="w-3 h-3 mr-1" />}
                          Save changes
                        </Button>
                      </div>
                    </div>
                  );
                }
                return (
                  <div key={t.id} className="flex items-start gap-3 p-3 rounded border border-white/[0.06] bg-black/30/40">
                    <Checkbox checked={t.is_active} onCheckedChange={() => toggleTemplateActive(t)} className="mt-1" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-white truncate">
                        {t.name} <span className="text-xs text-white/40">· {t.notification_type} · {t.default_severity}</span>
                      </p>
                      <p className="text-xs text-white/55 truncate mt-1">{t.title_template}</p>
                      <p className="text-xs text-white/40 line-clamp-2">{t.message_template}</p>
                    </div>
                    <Button size="sm" variant="ghost" onClick={() => startEditTemplate(t)} title="Edit template">
                      <Pencil className="w-3 h-3 text-white/70" />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => removeTemplate(t.id)} title="Delete template">
                      <Trash2 className="w-3 h-3 text-red-400" />
                    </Button>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={confirm.open}
        onOpenChange={(o) => !o && closeConfirm()}
        title={confirm.title}
        description={confirm.description}
        confirmLabel={confirm.confirmLabel}
        variant="danger"
        loading={confirm.loading}
        onConfirm={confirm.onConfirm}
      />
    </div>
  );
}
