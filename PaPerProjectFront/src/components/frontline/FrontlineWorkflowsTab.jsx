import React, { useState, useEffect } from 'react';
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
import {
  Loader2, Trash2, CheckCircle2, XCircle, Plus, ChevronUp,
  ChevronDown, GitBranch, Pencil, PlayCircle,
} from 'lucide-react';
import { HINTS } from './frontlineTutorialSteps';
import InfoHint from './InfoHint';
import frontlineAgentService from '@/services/frontlineAgentService';

const WORKFLOW_STEPS_DEFAULT = '[{"type": "send_email", "template_id": 1, "recipient_email": "{{recipient_email}}"}]';

export function FrontlineWorkflowsTab() {
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
      if (s.status) parts.push(`status → ${labelOf(s.status)}`);
      if (s.resolution) parts.push('resolution');
      if (s.ticket_id) parts.push(`ticket #${s.ticket_id}`);
      return `Update ticket: ${parts.length ? parts.join(', ') : '(no fields)'}`;
    }
    if (s.type === 'webhook') return `Webhook: ${(s.method || 'POST')} ${(s.url || '').slice(0, 40)}${(s.url || '').length > 40 ? '…' : ''}`;
    if (s.type === 'slack') return `Slack: ${(s.text || '').slice(0, 35)}${(s.text || '').length > 35 ? '…' : ''}`;
    if (s.type === 'assign') {
      const cu = stepBuilderCompanyUsers.find((u) => u.id === s.assign_to_company_user_id);
      return `Assign ticket → ${cu ? (cu.full_name || cu.email || `#${cu.id}`) : `user #${s.assign_to_company_user_id}`}`;
    }
    return `Step: ${labelOf(s.type) || 'unknown'}`;
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
                      <Badge variant={ex.status === 'completed' ? 'default' : ex.status === 'failed' ? 'destructive' : 'secondary'}>{labelOf(ex.status)}</Badge>
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
                        {PRIORITY_OPTIONS.map((p) => <SelectItem key={p} value={p}>{labelOf(p)}</SelectItem>)}
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
