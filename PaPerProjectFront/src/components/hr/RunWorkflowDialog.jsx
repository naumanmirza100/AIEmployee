import React, { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Loader2, Play } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import hrAgentService from '@/services/hrAgentService';
import { labelOf } from '@/utils/labels';

/** One preview step as a sentence: what it would do, and to whom. */
function describe(step) {
  const kind = labelOf(step.type) || 'Step';
  if (step.error) return `${kind}: won't work — ${step.error}`;
  if (step.type === 'send_email') return `Email ${step.recipient}`;
  if (step.type === 'update_employee') {
    return `Change ${Object.entries(step.fields || {}).map(([k, v]) => `${labelOf(k).toLowerCase()} to "${v}"`).join(', ')}`;
  }
  if (step.awaiting_approval) return `Wait for approval: "${step.approval_request?.message}"`;
  if (step.seconds != null) return `Wait ${Math.round(step.seconds / 60)} min`;
  if (step.note) return `${kind} (does nothing)`;
  return kind;
}

/**
 * Run an HR workflow by hand: choose who it is for, see what each step would
 * do, then run it. The Run button used to start it at once, for nobody.
 */
export default function RunWorkflowDialog({ workflow, onOpenChange, onDone }) {
  const [employees, setEmployees] = useState([]);
  const [employeeId, setEmployeeId] = useState('');
  const [preview, setPreview] = useState(null);
  const [previewing, setPreviewing] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const open = !!workflow;

  useEffect(() => {
    if (!open) return;
    setEmployeeId('');
    setPreview(null);
    setError('');
    hrAgentService.listHREmployees({ limit: 500 })
      .then((res) => setEmployees((res?.data || []).filter((e) => !['offboarded'].includes(e.employment_status))))
      .catch(() => setEmployees([]));
  }, [open, workflow?.id]);

  useEffect(() => {
    if (!open) return;
    let stale = false;
    setPreviewing(true);
    setError('');
    hrAgentService.executeHRWorkflow(workflow.id, employeeId ? { employee_id: Number(employeeId) } : {}, { simulate: true })
      .then((res) => { if (!stale) setPreview(res?.data || null); })
      .catch((e) => { if (!stale) setError(e.message || 'Could not preview this workflow.'); })
      .finally(() => { if (!stale) setPreviewing(false); });
    return () => { stale = true; };
  }, [open, workflow?.id, employeeId]);

  const run = async () => {
    setRunning(true);
    setError('');
    try {
      const res = await hrAgentService.executeHRWorkflow(workflow.id, employeeId ? { employee_id: Number(employeeId) } : {});
      onDone?.(res?.data || {});
      onOpenChange(false);
    } catch (e) {
      setError(e.message || 'The workflow could not run.');
    } finally {
      setRunning(false);
    }
  };

  const steps = preview?.result_data?.results || [];
  const problems = steps.filter((s) => s.error).length;

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!running) onOpenChange(o); }}>
      <DialogContent className="max-w-lg" data-testid="HR-run-workflow-dialog">
        <DialogHeader>
          <DialogTitle>Run "{workflow?.name}"</DialogTitle>
          <DialogDescription>Nothing is sent or changed until you press Run it.</DialogDescription>
        </DialogHeader>

        <div className="space-y-1.5">
          <Label htmlFor="HR-run-workflow-employee">Who is it for?</Label>
          <select id="HR-run-workflow-employee" value={employeeId} onChange={(e) => setEmployeeId(e.target.value)}
            className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground">
            <option value="">Nobody in particular</option>
            {employees.map((e) => <option key={e.id} value={e.id}>{e.full_name}{e.work_email ? ` — ${e.work_email}` : ''}</option>)}
          </select>
        </div>

        <div className="space-y-1.5">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">What it will do</p>
          {previewing ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Checking…</div>
          ) : steps.length === 0 ? (
            <p className="text-sm text-muted-foreground">This workflow has no steps.</p>
          ) : (
            <ol className="space-y-1 text-sm">
              {steps.map((s, i) => (
                <li key={i} className={`flex items-start gap-2 ${s.error ? 'text-amber-300' : ''}`}>
                  {s.error ? <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> : <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />}
                  <span>{describe(s)}</span>
                </li>
              ))}
            </ol>
          )}
          {problems > 0 && !previewing && (
            <p className="text-xs text-amber-300">
              {problems} step{problems === 1 ? '' : 's'} would fail{employeeId ? '' : ' — choosing who it is for may fix this'}.
            </p>
          )}
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={running}>Cancel</Button>
          <Button onClick={run} disabled={running || previewing}>
            {running ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Play className="mr-1 h-4 w-4" />}
            Run it
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
