import React, { useCallback, useEffect, useState } from 'react';
import { BookTemplate, FlaskConical, Loader2, Pencil, Plus, Trash2, Workflow } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/components/ui/use-toast';
import { companyApi } from '@/services/companyAuthService';

const BASE = '/recruitment/workflows';
const EMPTY = { name: '', description: '', trigger_event: 'application_received', steps_text: '[\n  \n]', is_active: true };

/**
 * Recruitment workflows (SOPs): steps that run by themselves on hiring events (docx item 7, "Workflow / SOP
 * Runner"). The same shape as HR's workflows screen: templates, a steps editor, a test run, and what ran.
 * Backend: api/views/recruitment_workflows.py, runner recruitment_agent/workflows.py.
 */
export default function RecruitmentWorkflows() {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [runs, setRuns] = useState([]);
  const [editing, setEditing] = useState(null);      // {id?, ...EMPTY}
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [testOpen, setTestOpen] = useState(false);
  const [busy, setBusy] = useState('');

  const load = useCallback(async () => {
    try {
      const [list, history] = await Promise.all([companyApi.get(BASE), companyApi.get(`${BASE}/runs`)]);
      setData(list?.data || null);
      setRuns(history?.data || []);
    } catch (e) {
      toast({ title: 'Could not load workflows', description: e?.message, variant: 'destructive' });
    }
  }, [toast]);
  useEffect(() => { load(); }, [load]);

  if (!data) return <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-violet-400" /></div>;

  const fromTemplate = async (key) => {
    setBusy(`t:${key}`);
    try {
      await companyApi.post(`${BASE}/from-template`, { template_key: key });
      toast({ title: 'Workflow added', description: 'It is on. Edit it to change the wording.' });
      load();
    } catch (e) {
      toast({ title: 'Not added', description: e?.message, variant: 'destructive' });
    } finally { setBusy(''); }
  };

  const save = async () => {
    let steps;
    try { steps = JSON.parse(editing.steps_text || '[]'); } catch {
      toast({ title: 'The steps are not valid JSON', description: 'Check commas and quotes.', variant: 'destructive' });
      return;
    }
    setSaving(true);
    const body = { name: editing.name, description: editing.description, trigger_event: editing.trigger_event,
      steps, is_active: editing.is_active };
    try {
      if (editing.id) await companyApi.patch(`${BASE}/${editing.id}`, body);
      else await companyApi.post(BASE, body);
      toast({ title: 'Saved' });
      setEditing(null);
      load();
    } catch (e) {
      toast({ title: 'Not saved', description: e?.message, variant: 'destructive' });
    } finally { setSaving(false); }
  };

  const toggle = async (wf) => {
    try { await companyApi.patch(`${BASE}/${wf.id}`, { is_active: !wf.is_active }); load(); } catch (e) {
      toast({ title: 'Not changed', description: e?.message, variant: 'destructive' });
    }
  };

  const remove = async (wf) => {
    if (!window.confirm(`Delete "${wf.name}"? Its run history stays.`)) return;
    try { await companyApi.delete(`${BASE}/${wf.id}`); load(); } catch (e) {
      toast({ title: 'Not deleted', description: e?.message, variant: 'destructive' });
    }
  };

  const test = async (wf) => {
    setBusy(`x:${wf.id}`);
    try {
      const res = await companyApi.post(`${BASE}/${wf.id}/test`, {});
      setTestResult({ name: wf.name, ...res?.data });
      setTestOpen(true);
      load();
    } catch (e) {
      toast({ title: 'Test not run', description: e?.message, variant: 'destructive' });
    } finally { setBusy(''); }
  };

  const eventLabel = (key) => (data.events.find((e) => e.key === key) || {}).label || key;

  return (
    <div className="space-y-4" data-testid="REC-workflows">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="flex items-center gap-2 text-white font-semibold"><Workflow className="h-4 w-4 text-violet-400" /> Workflows</h3>
          <p className="text-xs text-white/50">Steps that run by themselves when something happens in hiring: email the candidate, alert colleagues, make a task.</p>
        </div>
        {data.can_edit && (
          <Button size="sm" onClick={() => setEditing({ ...EMPTY })}><Plus className="h-4 w-4 mr-1" /> New workflow</Button>
        )}
      </div>
      {!data.can_edit && (
        <p className="text-xs text-amber-300/90">Only the company's owner or an admin can set up workflows. You can see them and try them.</p>
      )}

      {/* Templates */}
      {data.can_edit && (
        <div className="grid gap-2 sm:grid-cols-2">
          {data.templates.map((t) => (
            <div key={t.key} className="rounded-lg border border-white/10 bg-white/[0.02] p-3">
              <p className="text-sm text-white font-medium">{t.name}</p>
              <p className="text-xs text-white/50 mt-0.5">{t.description}</p>
              <div className="mt-2 flex items-center justify-between">
                <span className="text-[11px] text-white/40">When: {eventLabel(t.trigger_event)}</span>
                <Button size="sm" variant="outline" className="h-7 text-xs" disabled={busy === `t:${t.key}`}
                        onClick={() => fromTemplate(t.key)} data-testid={`REC-workflows-template-${t.key}`}>
                  <BookTemplate className="h-3.5 w-3.5 mr-1" /> Use
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* The company's workflows */}
      <div className="rounded-xl border border-white/10 divide-y divide-white/10">
        {data.workflows.length === 0 && <p className="p-4 text-sm text-white/50">No workflows yet. Start from a template above.</p>}
        {data.workflows.map((wf) => (
          <div key={wf.id} className="flex flex-wrap items-center gap-3 p-3" data-testid={`REC-workflow-${wf.id}`}>
            <div className="min-w-0 flex-1">
              <p className="text-sm text-white font-medium">{wf.name} {!wf.is_active && <Badge variant="outline" className="ml-1 text-[10px]">off</Badge>}</p>
              <p className="text-xs text-white/50">When: {wf.trigger_label}{wf.job_title ? ` · ${wf.job_title} only` : ''} · {wf.steps.length} step(s) · ran {wf.runs} time(s)</p>
            </div>
            <Button size="sm" variant="ghost" className="h-7 text-xs" disabled={busy === `x:${wf.id}`} onClick={() => test(wf)}>
              <FlaskConical className="h-3.5 w-3.5 mr-1" /> Test
            </Button>
            {data.can_edit && (
              <>
                <Switch checked={wf.is_active} onCheckedChange={() => toggle(wf)} aria-label="On or off" />
                <Button size="sm" variant="ghost" className="h-7" onClick={() => setEditing({ ...wf, steps_text: JSON.stringify(wf.steps, null, 2) })}>
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
                <Button size="sm" variant="ghost" className="h-7 text-red-300" onClick={() => remove(wf)}><Trash2 className="h-3.5 w-3.5" /></Button>
              </>
            )}
          </div>
        ))}
      </div>

      {/* What ran */}
      <div>
        <h4 className="text-sm text-white font-medium mb-2">What ran</h4>
        {runs.length === 0 ? <p className="text-xs text-white/50">Nothing yet.</p> : (
          <div className="rounded-xl border border-white/10 divide-y divide-white/10 text-xs">
            {runs.slice(0, 15).map((r) => (
              <div key={r.id} className="p-2.5">
                <span className="text-white/80">{r.workflow}</span>
                <span className="text-white/40"> · {r.candidate} · {new Date(r.started_at).toLocaleString()} · </span>
                <span className={r.status === 'failed' ? 'text-red-300' : 'text-emerald-300'}>{r.status === 'simulated' ? 'test run' : r.status}</span>
                {r.error && <span className="text-red-300/80"> · {r.error}</span>}
                {r.steps.length > 0 && <div className="mt-1 text-white/45">{r.steps.map((s) => `${s.type}${s.note ? `: ${s.note}` : ''}`).join('  →  ')}</div>}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Editor */}
      <Dialog open={!!editing} onOpenChange={(o) => { if (!o) setEditing(null); }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>{editing?.id ? 'Edit workflow' : 'New workflow'}</DialogTitle></DialogHeader>
          {editing && (
            <div className="space-y-3">
              <div><Label>Name</Label><Input value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} /></div>
              <div><Label>Description</Label><Textarea rows={2} value={editing.description || ''} onChange={(e) => setEditing({ ...editing, description: e.target.value })} /></div>
              <div>
                <Label>When it runs</Label>
                <select className="mt-1 w-full rounded-md border border-white/15 bg-black/30 p-2 text-sm text-white"
                        value={editing.trigger_event} onChange={(e) => setEditing({ ...editing, trigger_event: e.target.value })}>
                  {data.events.map((e) => <option key={e.key} value={e.key}>{e.label}</option>)}
                </select>
              </div>
              <div>
                <Label>Steps (JSON)</Label>
                <Textarea rows={10} className="font-mono text-xs" value={editing.steps_text}
                          onChange={(e) => setEditing({ ...editing, steps_text: e.target.value })} />
                <p className="mt-1 text-[11px] text-white/45 leading-relaxed">
                  Step types: <code>send_email</code> (to <code>candidate</code>, <code>recruiter</code> or an address, with <code>subject</code> and <code>body</code>),
                  <code> notify</code> (a bell alert to <code>recruiter</code>, <code>admins</code> or <code>hr_admins</code>, with <code>title</code> and <code>message</code>),
                  <code> create_task</code> (a Project Manager task: <code>project_id</code>, <code>title</code>, <code>due_in_days</code>),
                  <code> branch</code> (<code>condition</code>, <code>if_true</code>, <code>if_false</code>).
                  Texts can use {data.placeholders.map((p) => `{{${p}}}`).join(', ')}.
                </p>
              </div>
              <div className="flex items-center gap-2"><Switch checked={editing.is_active} onCheckedChange={(v) => setEditing({ ...editing, is_active: v })} /><span className="text-sm text-white/70">On</span></div>
            </div>
          )}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} disabled={saving}>{saving ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Save'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Test result */}
      <Dialog open={testOpen} onOpenChange={setTestOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Test run: {testResult?.name}</DialogTitle></DialogHeader>
          {testResult && (
            <div className="space-y-2 text-sm" data-testid="REC-workflows-test-result">
              <p className="text-white/60">On {testResult.candidate}. Nothing was sent or made.</p>
              {(testResult.results?.results || []).map((s, i) => (
                <div key={i} className="rounded border border-white/10 p-2 text-xs text-white/70">
                  <span className="font-medium text-white">{s.type}</span>
                  {s.branch_taken && <> · took the {s.branch_taken === 'if_true' ? 'yes' : 'no'} branch</>}
                  {s.to && <> · to {s.to}</>}
                  {(s.subject || s.title) && <> · “{s.subject || s.title}”</>}
                  {s.note && <> · {s.note}</>}
                  {s.error && <span className="text-red-300"> · {s.error}</span>}
                </div>
              ))}
              {testResult.error && <p className="text-red-300 text-xs">{testResult.error}</p>}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
