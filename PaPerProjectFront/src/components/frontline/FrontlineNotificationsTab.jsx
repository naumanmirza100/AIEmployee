import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { labelOf } from '@/utils/labels';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Loader2, Trash2, Plus, Bell, Pencil } from 'lucide-react';
import { HINTS } from './frontlineTutorialSteps';
import InfoHint from './InfoHint';
import frontlineAgentService from '@/services/frontlineAgentService';

const TEMPLATE_DEFAULT = { name: '', subject: '', body: '', notification_type: 'ticket_update', channel: 'email', use_llm_personalization: false };

export function FrontlineNotificationsTab() {
  const { toast } = useToast();
  const [templates, setTemplates] = useState([]);
  const [scheduled, setScheduled] = useState([]);
  const [notificationTicketsList, setNotificationTicketsList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sendForm, setSendForm] = useState({ template_id: '', recipient_email: '', ticket_id: '' });
  const [sending, setSending] = useState(false);
  const [templateDialog, setTemplateDialog] = useState({ open: false, editingId: null, ...TEMPLATE_DEFAULT });
  const [savingTemplate, setSavingTemplate] = useState(false);
  const load = async () => {
    setLoading(true);
    try {
      const [tRes, sRes, tickRes] = await Promise.all([
        frontlineAgentService.listNotificationTemplates(),
        frontlineAgentService.listScheduledNotifications(),
        frontlineAgentService.listTickets({ limit: 100 }),
      ]);
      setTemplates((tRes.status === 'success' && tRes.data) ? tRes.data : []);
      setScheduled((sRes.status === 'success' && sRes.data) ? sRes.data : []);
      setNotificationTicketsList((tickRes.status === 'success' && tickRes.data) ? tickRes.data : []);
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
        <CardDescription>Which of these emails you get — and what reaches your bell from every agent — is now chosen in one place.</CardDescription>
      </CardHeader>
      <CardContent>
        <div data-tour-notif="prefs" className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            Ticket created and updated emails, other automation emails, tickets assigned to you and the weekly summary are all there.
          </p>
          <Button asChild size="sm" variant="outline">
            <Link to="/company/settings/notifications">Open notification settings</Link>
          </Button>
        </div>
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
                      {t.use_llm_personalization && <Badge variant="secondary" className="text-xs">AI</Badge>}
                      <Badge variant="outline">{labelOf(t.channel)}</Badge>
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
                    <Badge variant={n.status === 'sent' ? 'default' : n.status === 'failed' ? 'destructive' : 'secondary'}>{labelOf(n.status)}</Badge>
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
