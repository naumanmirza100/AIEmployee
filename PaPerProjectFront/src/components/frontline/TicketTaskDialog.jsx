import React, { useEffect, useState } from 'react';
import { ClipboardList, Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/components/ui/use-toast';
import frontlineAgentService from '@/services/frontlineAgentService';

/**
 * Turn a support ticket into a Project Manager task.
 *
 * Pre-filled from the ticket (title, description with the customer and ticket
 * number, priority, a due date from the priority); the agent picks a project
 * and, optionally, who does it. Created through Project Manager's own rules,
 * and linked both ways: when the task is done the ticket gets a note and its
 * owner a bell alert.
 */
export default function TicketTaskDialog({ ticket, open, onOpenChange, onDone }) {
  const { toast } = useToast();
  const [info, setInfo] = useState(null);
  const [form, setForm] = useState({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open || !ticket) return;
    setInfo(null);
    setError('');
    setLoading(true);
    frontlineAgentService.getTicketTask(ticket.id)
      .then((res) => {
        const data = res?.data || {};
        setInfo(data);
        setForm({ ...(data.prefill || {}) });
      })
      .catch((e) => setError(e?.message || 'Could not load the form.'))
      .finally(() => setLoading(false));
  }, [open, ticket]);

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const create = async () => {
    setSaving(true);
    setError('');
    try {
      const res = await frontlineAgentService.createTicketTask(ticket.id, {
        ...form,
        project_id: form.project_id ? Number(form.project_id) : null,
        assignee_id: form.assignee_id ? Number(form.assignee_id) : null,
      });
      toast({ title: 'Project task created', description: `"${res?.data?.title}" in ${res?.data?.project}.` });
      onDone?.();
      onOpenChange(false);
    } catch (e) {
      setError(e?.message || 'Could not create the task.');
    } finally {
      setSaving(false);
    }
  };

  const selectClass = 'w-full h-10 rounded-md border border-input bg-background px-2 text-sm text-foreground';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[95vw] max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><ClipboardList className="h-4 w-4" /> Create project task</DialogTitle>
          <DialogDescription>
            From ticket #{ticket?.id}. When the task is done, this ticket gets a note so you can tell the customer.
          </DialogDescription>
        </DialogHeader>

        {loading && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</p>
        )}

        {!loading && info && !info.pm_available && (
          <p className="text-sm text-muted-foreground">Your company doesn&apos;t have the Project Manager agent.</p>
        )}

        {!loading && info?.pm_available && (
          <div className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="ticket-task-project" className="text-xs">Project</Label>
              <select id="ticket-task-project" value={form.project_id || ''} onChange={set('project_id')} className={selectClass}>
                <option value="">Choose a project…</option>
                {(info.projects || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              {(info.projects || []).length === 0 && (
                <p className="text-xs text-muted-foreground">No open projects yet — create one in the Project Manager agent first.</p>
              )}
            </div>
            <div className="space-y-1">
              <Label htmlFor="ticket-task-title" className="text-xs">Task</Label>
              <Input id="ticket-task-title" value={form.title || ''} onChange={set('title')} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="ticket-task-description" className="text-xs">Description</Label>
              <Textarea id="ticket-task-description" rows={5} value={form.description || ''} onChange={set('description')} />
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="space-y-1">
                <Label htmlFor="ticket-task-priority" className="text-xs">Priority</Label>
                <select id="ticket-task-priority" value={form.priority || 'medium'} onChange={set('priority')} className={selectClass}>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="ticket-task-due" className="text-xs">Due</Label>
                <Input id="ticket-task-due" type="date" value={form.due_date || ''} onChange={set('due_date')} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="ticket-task-assignee" className="text-xs">Assign to</Label>
                <select id="ticket-task-assignee" value={form.assignee_id || ''} onChange={set('assignee_id')} className={selectClass}>
                  <option value="">Nobody yet</option>
                  {(info.assignees || []).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                </select>
              </div>
            </div>
          </div>
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)} disabled={saving}>Cancel</Button>
          {info?.pm_available && (
            <Button size="sm" onClick={create} disabled={saving || loading || !form.project_id || !(form.title || '').trim()}>
              {saving ? 'Creating…' : 'Create task'}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
