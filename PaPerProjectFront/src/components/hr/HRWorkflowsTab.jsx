import React, { useEffect, useState } from 'react';
import { labelOf } from '@/utils/labels';
import {
  Card, CardContent, CardHeader, CardTitle, CardDescription,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useToast } from '@/components/ui/use-toast';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Loader2, GitBranch, Plus, Trash2, Play, Power, Pencil, History, BookTemplate,
} from 'lucide-react';
import hrAgentService from '@/services/hrAgentService';
import InfoHint from '../frontline/InfoHint';
import { Spinner, EmptyState } from './HRUiKit';
import { HR_HINTS } from './hrTutorialSteps';
import { WORKFLOW_EVENTS, FILTER_LABELS, eventLabel, humanize } from './hrEventLabels';
import RunWorkflowDialog from './RunWorkflowDialog';

/**
 * HR workflows (SOPs): the list, the editor, Run, templates and run history
 * with approve/reject. Moved out of HRDashboard; shown both on the Workflows
 * tab and inline under Operations.
 */
export default function HRWorkflowsTab() {
  const { toast } = useToast();
  const [workflows, setWorkflows] = useState([]);
  const [wfLoading, setWfLoading] = useState(false);
  const [wfDialog, setWfDialog] = useState({ open: false, mode: 'create', wf: null });
  const [wfDelete, setWfDelete] = useState({ open: false, wf: null, loading: false });
  const [wfHistory, setWfHistory] = useState({ open: false, wf: null, loading: false, rows: [] });
  const [wfBusyId, setWfBusyId] = useState(null);
  const [wfTemplateDialog, setWfTemplateDialog] = useState({
    open: false, loading: false, templates: [], selectedKey: '', name: '',
  });

  const loadWorkflows = async () => {
    setWfLoading(true);
    try {
      const res = await hrAgentService.listHRWorkflows();
      setWorkflows(res?.data || []);
    } catch (e) {
      toast({ title: 'Failed to load workflows', description: e.message, variant: 'destructive' });
    } finally {
      setWfLoading(false);
    }
  };

  useEffect(() => { loadWorkflows(); }, []);

  const openCreateWorkflow = () => setWfDialog({
    open: true, mode: 'create',
    wf: {
      name: '', description: '',
      trigger_event: 'employee_hired', trigger_filters: {},
      steps_text: JSON.stringify([
        { type: 'send_email', template_name: 'welcome_email', recipient: '{{employee_email}}' },
        { type: 'wait', seconds: 0 },
      ], null, 2),
      is_active: true, requires_approval: false, timeout_seconds: 0,
    },
  });

  const openEditWorkflow = (w) => setWfDialog({
    open: true, mode: 'edit',
    wf: {
      id: w.id, name: w.name, description: w.description || '',
      trigger_event: w.trigger_conditions?.on || '',
      trigger_filters: { ...w.trigger_conditions, on: undefined },
      steps_text: JSON.stringify(w.steps || [], null, 2),
      is_active: !!w.is_active, requires_approval: !!w.requires_approval,
      timeout_seconds: w.timeout_seconds || 0,
    },
  });

  const handleSaveWorkflow = async () => {
    const wf = wfDialog.wf;
    if (!wf?.name?.trim()) {
      toast({ title: 'Name required', variant: 'destructive' });
      return;
    }
    let steps;
    try {
      steps = JSON.parse(wf.steps_text || '[]');
      if (!Array.isArray(steps)) throw new Error('steps must be a JSON array');
    } catch (e) {
      toast({ title: 'Steps JSON invalid', description: e.message, variant: 'destructive' });
      return;
    }
    const trigger_conditions = {};
    if (wf.trigger_event) trigger_conditions.on = wf.trigger_event;
    Object.entries(wf.trigger_filters || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') trigger_conditions[k] = v;
    });
    const payload = {
      name: wf.name.trim(),
      description: wf.description || '',
      trigger_conditions,
      steps,
      is_active: !!wf.is_active,
      requires_approval: !!wf.requires_approval,
      timeout_seconds: Number(wf.timeout_seconds) || 0,
    };
    try {
      if (wfDialog.mode === 'create') {
        const res = await hrAgentService.createHRWorkflow(payload);
        toast({ title: 'Workflow created', description: res?.data?.name || '' });
      } else {
        await hrAgentService.updateHRWorkflow(wf.id, payload);
        toast({ title: 'Workflow saved' });
      }
      setWfDialog({ open: false, mode: 'create', wf: null });
      loadWorkflows();
    } catch (e) {
      toast({ title: 'Save failed', description: e.message, variant: 'destructive' });
    }
  };

  const handleToggleActive = async (w) => {
    setWfBusyId(w.id);
    try {
      await hrAgentService.updateHRWorkflow(w.id, { is_active: !w.is_active });
      setWorkflows((arr) => arr.map((x) => (x.id === w.id ? { ...x, is_active: !w.is_active } : x)));
    } catch (e) {
      toast({ title: 'Toggle failed', description: e.message, variant: 'destructive' });
    } finally {
      setWfBusyId(null);
    }
  };

  // Run opens a preview: who it is for and what each step will do; it runs
  // only from there. It used to start at once, for nobody.
  const [runWorkflow, setRunWorkflow] = useState(null);
  const handleRunWorkflow = (w) => setRunWorkflow(w);
  const afterWorkflowRun = (data) => {
    const status = data?.status || 'completed';
    const sc = data?.result_data?.steps_completed;
    toast({
      title: `Workflow ${labelOf(status).toLowerCase()}`,
      description: sc != null ? `${sc} step(s) completed` : undefined,
    });
  };

  const handleDeleteWorkflow = async () => {
    const w = wfDelete.wf;
    if (!w) return;
    setWfDelete((s) => ({ ...s, loading: true }));
    try {
      await hrAgentService.deleteHRWorkflow(w.id);
      setWorkflows((arr) => arr.filter((x) => x.id !== w.id));
      toast({ title: 'Workflow deleted' });
      setWfDelete({ open: false, wf: null, loading: false });
    } catch (e) {
      toast({ title: 'Delete failed', description: e.message, variant: 'destructive' });
      setWfDelete((s) => ({ ...s, loading: false }));
    }
  };

  const handleViewHistory = async (w) => {
    setWfHistory({ open: true, wf: w, loading: true, rows: [] });
    try {
      const res = await hrAgentService.listHRWorkflowExecutions(w.id);
      setWfHistory({ open: true, wf: w, loading: false, rows: res?.data || [] });
    } catch (e) {
      toast({ title: 'Failed to load history', description: e.message, variant: 'destructive' });
      setWfHistory({ open: true, wf: w, loading: false, rows: [] });
    }
  };

  const openWfTemplateDialog = async () => {
    setWfTemplateDialog({ open: true, loading: true, templates: [], selectedKey: '', name: '' });
    try {
      const res = await hrAgentService.listWorkflowTemplates();
      setWfTemplateDialog((s) => ({ ...s, loading: false, templates: res?.data || [] }));
    } catch (e) {
      toast({ title: 'Failed to load templates', description: e.message, variant: 'destructive' });
      setWfTemplateDialog({ open: false, loading: false, templates: [], selectedKey: '', name: '' });
    }
  };

  const handleCloneTemplate = async () => {
    const { selectedKey, name } = wfTemplateDialog;
    if (!selectedKey) {
      toast({ title: 'Pick a template first', variant: 'destructive' });
      return;
    }
    setWfTemplateDialog((s) => ({ ...s, loading: true }));
    try {
      const res = await hrAgentService.createWorkflowFromTemplate({
        template_key: selectedKey,
        name: name || undefined,
      });
      toast({ title: 'Workflow created from template', description: res?.data?.name || '' });
      setWfTemplateDialog({ open: false, loading: false, templates: [], selectedKey: '', name: '' });
      loadWorkflows();
    } catch (e) {
      toast({ title: 'Clone failed', description: e.message, variant: 'destructive' });
      setWfTemplateDialog((s) => ({ ...s, loading: false }));
    }
  };

  const handleApproveExecution = async (row) => {
    const comment = window.prompt('Optional approval comment:') || '';
    try {
      const res = await hrAgentService.approveHRWorkflowExecution(row.id, comment);
      const updated = res?.data || {};
      setWfHistory((s) => ({
        ...s,
        rows: s.rows.map((r) => (r.id === row.id ? { ...r, ...updated } : r)),
      }));
      toast({ title: 'Approved', description: `Execution now ${updated.status || 'resumed'}` });
    } catch (e) {
      toast({ title: 'Approve failed', description: e.message, variant: 'destructive' });
    }
  };

  const handleRejectExecution = async (row) => {
    const reason = window.prompt('Rejection reason (optional):') || '';
    try {
      const res = await hrAgentService.rejectHRWorkflowExecution(row.id, reason);
      const updated = res?.data || {};
      setWfHistory((s) => ({
        ...s,
        rows: s.rows.map((r) => (r.id === row.id ? { ...r, ...updated } : r)),
      }));
      toast({ title: 'Rejected', description: 'Workflow stopped at the approval gate.' });
    } catch (e) {
      toast({ title: 'Reject failed', description: e.message, variant: 'destructive' });
    }
  };

  return (
    <>
      <Card className="border-white/10 bg-pure-black/20 backdrop-blur-sm">
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <GitBranch className="h-5 w-5 text-violet-400" /> HR Workflows / SOPs
              <InfoHint {...HR_HINTS.hrWfList} />
            </CardTitle>
            <CardDescription>Onboarding · offboarding · approvals · reminders. Triggers fire on lifecycle events.</CardDescription>
          </div>
          <div className="flex gap-2">
            <div className="flex items-center gap-1.5" data-tour-hr-wf="template">
              <Button variant="outline" onClick={openWfTemplateDialog}>
                <BookTemplate className="h-4 w-4 mr-1" /> From template
              </Button>
              <InfoHint {...HR_HINTS.hrWfTemplate} />
            </div>
            <div className="flex items-center gap-1.5" data-tour-hr-wf="create">
              <Button onClick={openCreateWorkflow}>
                <Plus className="h-4 w-4 mr-1" /> New workflow
              </Button>
              <InfoHint {...HR_HINTS.hrWfCreate} />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {wfLoading ? (
            <Spinner />
          ) : workflows.length === 0 ? (
            <EmptyState icon={GitBranch} title="No workflows yet"
              sub="Create your first workflow — onboarding, offboarding, leave approval, or any custom SOP." />
          ) : (
            <div data-tour-hr-wf="list" className="space-y-2">
              {workflows.map((w) => {
                const trig = w.trigger_conditions || {};
                const trigEvent = trig.on || null;
                const trigExtras = Object.entries(trig).filter(([k]) => k !== 'on');
                const stepCount = (w.steps || []).length;
                const busy = wfBusyId === w.id;
                return (
                  <div key={w.id}
                       className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4 transition-all hover:bg-white/[0.06] hover:border-violet-400/30">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <div className="font-medium text-white/95 truncate">{w.name}</div>
                          <Badge variant="outline" className={w.is_active
                            ? 'text-[10px] bg-emerald-500/10 text-emerald-300 border-emerald-400/30'
                            : 'text-[10px] bg-white/[0.03] text-white/65 border-white/[0.08]'}>
                            {w.is_active ? 'Active' : 'Inactive'}
                          </Badge>
                          {w.requires_approval && (
                            <Badge variant="outline" className="text-[10px] bg-amber-500/10 text-amber-300 border-amber-400/30">
                              Requires approval
                            </Badge>
                          )}
                        </div>
                        {w.description && (
                          <div className="text-xs text-white/60 mt-1">{w.description}</div>
                        )}
                        <div className="text-xs text-white/45 mt-2 flex flex-wrap items-center gap-2">
                          {trigEvent ? (
                            <Badge variant="outline" className="text-[10px] bg-violet-500/10 text-violet-300 border-violet-400/30">
                              {eventLabel(trigEvent)}
                            </Badge>
                          ) : (
                            <span className="italic">Runs on demand only</span>
                          )}
                          {trigExtras.map(([k, v]) => (
                            <Badge key={k} variant="outline" className="text-[10px]">
                              {FILTER_LABELS[k] || humanize(k)}: {String(v)}
                            </Badge>
                          ))}
                          <span className="text-white/40">· {stepCount} step{stepCount === 1 ? '' : 's'}</span>
                          {w.timeout_seconds > 0 && (
                            <span className="text-white/40">· gives up after {w.timeout_seconds}s</span>
                          )}
                        </div>
                      </div>
                      <div className="flex flex-col gap-1 shrink-0">
                        <Button variant="outline" size="sm" className="h-7 text-xs"
                          onClick={() => handleRunWorkflow(w)} disabled={busy}>
                          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3 mr-1" />}
                          <span className="ml-1">Run</span>
                        </Button>
                        <Button variant="outline" size="sm" className="h-7 text-xs"
                          onClick={() => openEditWorkflow(w)}>
                          <Pencil className="h-3 w-3 mr-1" /> Edit
                        </Button>
                        <Button variant="outline" size="sm" className="h-7 text-xs"
                          onClick={() => handleToggleActive(w)} disabled={busy}>
                          <Power className="h-3 w-3 mr-1" />
                          {w.is_active ? 'Disable' : 'Enable'}
                        </Button>
                        <Button variant="outline" size="sm" className="h-7 text-xs"
                          onClick={() => handleViewHistory(w)}>
                          <History className="h-3 w-3 mr-1" /> Runs
                        </Button>
                        <Button variant="outline" size="sm" className="h-7 text-xs text-rose-400 hover:text-rose-300"
                          onClick={() => setWfDelete({ open: true, wf: w, loading: false })}>
                          <Trash2 className="h-3 w-3 mr-1" /> Delete
                        </Button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Workflow create / edit dialog */}
      <Dialog open={wfDialog.open} onOpenChange={(open) => setWfDialog((s) => ({ ...s, open }))}>
        <DialogContent className="max-w-2xl max-h-[90vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>{wfDialog.mode === 'create' ? 'New workflow' : 'Edit workflow'}</DialogTitle>
            <DialogDescription>
              Set the trigger event + the step list. Steps run top-down; supported types include
              <code className="text-violet-300"> send_email</code>,
              <code className="text-violet-300"> update_employee</code>,
              <code className="text-violet-300"> update_leave_balance</code>,
              <code className="text-violet-300"> schedule_meeting</code>,
              <code className="text-violet-300"> provision_account</code>,
              <code className="text-violet-300"> assign_training</code>,
              <code className="text-violet-300"> notify_template</code>,
              <code className="text-violet-300"> branch</code>,
              <code className="text-violet-300"> wait</code>.
            </DialogDescription>
          </DialogHeader>
          {wfDialog.wf && (
            <div className="space-y-3 overflow-y-auto pr-1">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <Label>Name</Label>
                  <Input value={wfDialog.wf.name}
                    onChange={(e) => setWfDialog((s) => ({ ...s, wf: { ...s.wf, name: e.target.value } }))}
                    placeholder="e.g. Standard onboarding" />
                </div>
                <div>
                  <Label>Runs automatically</Label>
                  <Select
                    value={wfDialog.wf.trigger_event || ''}
                    onValueChange={(v) => setWfDialog((s) => ({ ...s, wf: { ...s.wf, trigger_event: v === '__none__' ? '' : v } }))}>
                    <SelectTrigger><SelectValue placeholder="Pick when it runs" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">Never — only when someone runs it</SelectItem>
                      {WORKFLOW_EVENTS.map((e) => <SelectItem key={e.value} value={e.value}>{e.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div>
                <Label>Description</Label>
                <Textarea rows={2} value={wfDialog.wf.description || ''}
                  onChange={(e) => setWfDialog((s) => ({ ...s, wf: { ...s.wf, description: e.target.value } }))}
                  placeholder="Optional — what this workflow does" />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <Label>Only for this leave type (optional)</Label>
                  <Input
                    value={wfDialog.wf.trigger_filters?.leave_type || ''}
                    onChange={(e) => setWfDialog((s) => ({ ...s, wf: {
                      ...s.wf,
                      trigger_filters: { ...(s.wf.trigger_filters || {}), leave_type: e.target.value || undefined },
                    } }))}
                    placeholder="vacation / sick / parental / ..." />
                </div>
                <div>
                  <Label>Only for this department (optional)</Label>
                  <Input
                    value={wfDialog.wf.trigger_filters?.department || ''}
                    onChange={(e) => setWfDialog((s) => ({ ...s, wf: {
                      ...s.wf,
                      trigger_filters: { ...(s.wf.trigger_filters || {}), department: e.target.value || undefined },
                    } }))}
                    placeholder="Engineering / Sales / ..." />
                </div>
              </div>
              <div>
                <Label>Steps (JSON array)</Label>
                <Textarea rows={10} className="font-mono text-xs"
                  value={wfDialog.wf.steps_text}
                  onChange={(e) => setWfDialog((s) => ({ ...s, wf: { ...s.wf, steps_text: e.target.value } }))} />
              </div>
              <div className="flex items-center gap-4 flex-wrap">
                <label className="flex items-center gap-2 text-sm select-none">
                  <input type="checkbox" checked={!!wfDialog.wf.is_active}
                    onChange={(e) => setWfDialog((s) => ({ ...s, wf: { ...s.wf, is_active: e.target.checked } }))}
                    className="h-4 w-4" />
                  <span>Active (runs automatically when it should)</span>
                </label>
                <label className="flex items-center gap-2 text-sm select-none">
                  <input type="checkbox" checked={!!wfDialog.wf.requires_approval}
                    onChange={(e) => setWfDialog((s) => ({ ...s, wf: { ...s.wf, requires_approval: e.target.checked } }))}
                    className="h-4 w-4" />
                  <span>Requires approval before running</span>
                </label>
                <div>
                  <Label className="mr-2">Give up after (seconds, 0 = never)</Label>
                  <Input type="number" min={0} className="w-28 inline-block"
                    value={wfDialog.wf.timeout_seconds}
                    onChange={(e) => setWfDialog((s) => ({ ...s, wf: { ...s.wf, timeout_seconds: Number(e.target.value) || 0 } }))} />
                </div>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setWfDialog({ open: false, mode: 'create', wf: null })}>Cancel</Button>
            <Button onClick={handleSaveWorkflow}>{wfDialog.mode === 'create' ? 'Create' : 'Save'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <RunWorkflowDialog workflow={runWorkflow} onDone={afterWorkflowRun}
        onOpenChange={(open) => { if (!open) setRunWorkflow(null); }} />

      {/* Workflow delete confirm */}
      <Dialog open={wfDelete.open} onOpenChange={(open) => setWfDelete((s) => ({ ...s, open }))}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete workflow?</DialogTitle>
            <DialogDescription>
              Removes <strong>{wfDelete.wf?.name}</strong> and stops all future auto-runs. Past
              execution rows are kept for audit.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setWfDelete({ open: false, wf: null, loading: false })} disabled={wfDelete.loading}>Keep</Button>
            <Button onClick={handleDeleteWorkflow} disabled={wfDelete.loading} className="bg-rose-600 hover:bg-rose-500">
              {wfDelete.loading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Trash2 className="h-4 w-4 mr-1" />}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Workflow template picker */}
      <Dialog open={wfTemplateDialog.open}
        onOpenChange={(open) => setWfTemplateDialog((s) => ({ ...s, open }))}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Clone a workflow template</DialogTitle>
            <DialogDescription>
              Built-in flows you can clone and customise. The clone becomes an editable workflow in your company.
            </DialogDescription>
          </DialogHeader>
          {wfTemplateDialog.loading && wfTemplateDialog.templates.length === 0 ? (
            <Spinner />
          ) : (
            <div className="space-y-2 max-h-[50vh] overflow-y-auto">
              {wfTemplateDialog.templates.map((t) => (
                <button key={t.key}
                  onClick={() => setWfTemplateDialog((s) => ({ ...s, selectedKey: t.key, name: t.name }))}
                  className={`w-full text-left rounded-lg border p-3 transition-colors ${
                    wfTemplateDialog.selectedKey === t.key
                      ? 'border-violet-400/60 bg-violet-500/10'
                      : 'border-white/[0.08] bg-white/[0.03] hover:bg-white/[0.06]'
                  }`}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold text-white text-sm">{t.name}</span>
                    <Badge variant="outline" className="text-[10px]">
                      {t.step_count} step{t.step_count === 1 ? '' : 's'}
                    </Badge>
                    {t.trigger_event && (
                      <Badge variant="outline" className="text-[10px] bg-violet-500/10 text-violet-300 border-violet-400/30">
                        {eventLabel(t.trigger_event)}
                      </Badge>
                    )}
                    {t.requires_approval && (
                      <Badge variant="outline" className="text-[10px] bg-amber-500/10 text-amber-300 border-amber-400/30">
                        Requires approval
                      </Badge>
                    )}
                  </div>
                  <div className="text-xs text-white/65">{t.description}</div>
                </button>
              ))}
            </div>
          )}
          {wfTemplateDialog.selectedKey && (
            <div className="mt-2">
              <Label className="text-xs">Custom name (optional)</Label>
              <Input value={wfTemplateDialog.name}
                onChange={(e) => setWfTemplateDialog((s) => ({ ...s, name: e.target.value }))}
                placeholder="Defaults to template name" />
            </div>
          )}
          <DialogFooter>
            <Button variant="outline"
              onClick={() => setWfTemplateDialog({ open: false, loading: false, templates: [], selectedKey: '', name: '' })}
              disabled={wfTemplateDialog.loading}>Cancel</Button>
            <Button onClick={handleCloneTemplate}
              disabled={wfTemplateDialog.loading || !wfTemplateDialog.selectedKey}>
              {wfTemplateDialog.loading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
              Clone
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Workflow run history */}
      <Dialog open={wfHistory.open} onOpenChange={(open) => setWfHistory((s) => ({ ...s, open }))}>
        <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Run history{wfHistory.wf ? ` — ${wfHistory.wf.name}` : ''}</DialogTitle>
            <DialogDescription>Most recent 100 executions, newest first.</DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-auto">
            {wfHistory.loading ? (
              <Spinner />
            ) : wfHistory.rows.length === 0 ? (
              <div className="text-center text-sm text-white/50 py-10">No executions yet.</div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-[10px] uppercase">Started</TableHead>
                    <TableHead className="text-[10px] uppercase">Status</TableHead>
                    <TableHead className="text-[10px] uppercase">Steps done</TableHead>
                    <TableHead className="text-[10px] uppercase">Completed</TableHead>
                    <TableHead className="text-[10px] uppercase">Error / Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {wfHistory.rows.map((row) => (
                    <TableRow key={row.id} className="border-white/[0.06]">
                      <TableCell className="text-xs">{row.started_at ? new Date(row.started_at).toLocaleString() : '—'}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className={`text-[10px] ${
                          {
                            completed: 'bg-emerald-500/10 text-emerald-300 border-emerald-400/30',
                            failed: 'bg-rose-500/10 text-rose-300 border-rose-400/30',
                            paused: 'bg-amber-500/10 text-amber-300 border-amber-400/30',
                            in_progress: 'bg-violet-500/10 text-violet-300 border-violet-400/30',
                            awaiting_approval: 'bg-violet-500/10 text-violet-300 border-violet-400/30',
                          }[row.status] || 'bg-white/[0.04] text-white/70'
                        }`}>{labelOf(row.status)}</Badge>
                      </TableCell>
                      <TableCell className="text-xs">{row.steps_completed ?? '—'}</TableCell>
                      <TableCell className="text-xs">{row.completed_at ? new Date(row.completed_at).toLocaleString() : '—'}</TableCell>
                      <TableCell className="text-xs max-w-[16rem]">
                        {row.status === 'awaiting_approval' ? (
                          <div className="space-y-1">
                            {row.approval_request?.message && (
                              <div className="text-white/70 text-[11px] truncate" title={row.approval_request.message}>
                                {row.approval_request.message}
                              </div>
                            )}
                            <div className="flex gap-1">
                              <Button size="sm" className="h-6 px-2 text-[10px] bg-emerald-600 hover:bg-emerald-500"
                                      onClick={() => handleApproveExecution(row)}>
                                Approve
                              </Button>
                              <Button size="sm" variant="outline" className="h-6 px-2 text-[10px] border-rose-400/40 text-rose-300 hover:bg-rose-500/10"
                                      onClick={() => handleRejectExecution(row)}>
                                Reject
                              </Button>
                            </div>
                          </div>
                        ) : (
                          <span className="text-rose-300 truncate inline-block max-w-full" title={row.error_message || ''}>
                            {row.error_message || ''}
                          </span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setWfHistory({ open: false, wf: null, loading: false, rows: [] })}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
