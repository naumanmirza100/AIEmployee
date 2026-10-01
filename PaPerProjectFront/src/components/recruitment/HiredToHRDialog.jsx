import React, { useEffect, useMemo, useState } from 'react';
import { Loader2, UserPlus } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/components/ui/use-toast';
import { getHRHandoff, handOffToHR } from '@/services/recruitmentAgentService';

/**
 * Add a hired candidate to HR as a new starter.
 *
 * Everything is pre-filled from the interview and the job; the recruiter
 * reviews it, sets the first day, and confirms. The HR record is created as a
 * candidate ("offer signed, not started"), which starts HR's onboarding
 * workflow, and HR admins are told. If HR already has someone with their
 * email (added by hand, or a rehire), it offers to link that record instead.
 */
export default function HiredToHRDialog({ interview, open, onOpenChange, onDone }) {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [info, setInfo] = useState(null);
  const [form, setForm] = useState({});
  const [errors, setErrors] = useState({});
  const [managerFilter, setManagerFilter] = useState('');

  useEffect(() => {
    if (!open || !interview) return;
    setInfo(null);
    setErrors({});
    setManagerFilter('');
    setLoading(true);
    getHRHandoff(interview.id)
      .then((res) => {
        const data = res?.data || {};
        setInfo(data);
        setForm({ ...(data.prefill || {}) });
      })
      .catch((e) => setErrors({ _: e?.message || 'Could not load the form.' }))
      .finally(() => setLoading(false));
  }, [open, interview]);

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const managers = useMemo(() => {
    const q = managerFilter.trim().toLowerCase();
    const all = info?.managers || [];
    return q ? all.filter((m) => `${m.full_name} ${m.job_title}`.toLowerCase().includes(q)) : all;
  }, [info, managerFilter]);

  const finish = (description) => {
    toast({ title: 'Added to HR', description });
    onDone?.();
    onOpenChange(false);
  };

  const submit = async () => {
    setSaving(true);
    setErrors({});
    try {
      const res = await handOffToHR(interview.id, form);
      const runs = res?.data?.onboarding_workflows || [];
      finish(runs.length
        ? `${form.full_name} starts ${form.start_date}. Onboarding started: ${runs.join(', ')}.`
        : `${form.full_name} starts ${form.start_date}. There's no onboarding workflow in HR yet.`);
    } catch (e) {
      setErrors(e?.data?.errors || { _: e?.message || 'Could not add them to HR.' });
    } finally {
      setSaving(false);
    }
  };

  const linkExisting = async () => {
    setSaving(true);
    setErrors({});
    try {
      await handOffToHR(interview.id, { link_existing: true });
      finish(`Linked to ${info.existing.full_name}'s HR record.`);
    } catch (e) {
      setErrors({ _: e?.message || 'Could not link the record.' });
    } finally {
      setSaving(false);
    }
  };

  const field = (name, label, props = {}) => (
    <div className="space-y-1">
      <Label htmlFor={`hr-handoff-${name}`} className="text-xs">{label}</Label>
      <Input id={`hr-handoff-${name}`} value={form[name] || ''} onChange={set(name)} {...props} />
      {errors[name] && <p className="text-xs text-destructive">{errors[name]}</p>}
    </div>
  );

  const existing = info?.existing;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[95vw] max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><UserPlus className="h-4 w-4" /> Add to HR</DialogTitle>
          <DialogDescription>
            {interview?.candidate_name} becomes a new starter in HR. Check the details and set their first day.
          </DialogDescription>
        </DialogHeader>

        {loading && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading…
          </p>
        )}

        {!loading && info && !info.hr_available && (
          <p className="text-sm text-muted-foreground">
            Your company doesn&apos;t have the HR agent, so there&apos;s nowhere to add them.
          </p>
        )}

        {!loading && info?.hr_available && existing && (
          <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm space-y-2">
            <p>
              HR already has <strong>{existing.full_name}</strong> ({existing.work_email},{' '}
              {existing.employment_status}). Link this hire to that record instead of adding someone new?
            </p>
            <Button size="sm" variant="outline" onClick={linkExisting} disabled={saving}>Link to this record</Button>
          </div>
        )}

        {!loading && info?.hr_available && (
          <div className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              {field('full_name', 'Name')}
              {field('work_email', 'Work email', { type: 'email' })}
            </div>
            <p className="-mt-1 text-[11px] text-muted-foreground">
              This is the email they applied with. Change it if they already have a company address.
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              {field('job_title', 'Job title')}
              <div className="space-y-1">
                <Label htmlFor="hr-handoff-department" className="text-xs">Department</Label>
                <Input id="hr-handoff-department" list="hr-handoff-departments"
                  value={form.department || ''} onChange={set('department')} />
                <datalist id="hr-handoff-departments">
                  {(info.departments || []).map((d) => <option key={d} value={d} />)}
                </datalist>
              </div>
              {field('start_date', 'First day', { type: 'date' })}
              <div className="space-y-1">
                <Label htmlFor="hr-handoff-type" className="text-xs">Employment type</Label>
                <select id="hr-handoff-type" value={form.employment_type || 'full_time'} onChange={set('employment_type')}
                  className="w-full h-10 rounded-md border border-input bg-background px-2 text-sm text-foreground">
                  {(info.employment_types || []).map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              </div>
            </div>
            <div className="space-y-1">
              <Label htmlFor="hr-handoff-manager" className="text-xs">Manager (optional)</Label>
              <Input placeholder="Search people" value={managerFilter} onChange={(e) => setManagerFilter(e.target.value)} />
              <select id="hr-handoff-manager" value={form.manager_id || ''}
                onChange={(e) => setForm((f) => ({ ...f, manager_id: e.target.value ? Number(e.target.value) : null }))}
                className="w-full h-10 rounded-md border border-input bg-background px-2 text-sm text-foreground">
                <option value="">No manager yet</option>
                {managers.map((m) => (
                  <option key={m.id} value={m.id}>{m.full_name}{m.job_title ? ` — ${m.job_title}` : ''}</option>
                ))}
              </select>
              {errors.manager_id && <p className="text-xs text-destructive">{errors.manager_id}</p>}
            </div>

            <p className="rounded-md bg-muted/60 px-3 py-2 text-xs text-muted-foreground">
              {(info.onboarding_workflows || []).length
                ? `Onboarding that will start: ${info.onboarding_workflows.join(', ')}.`
                : 'No onboarding workflow is set up in HR yet. They will still be added, and HR will be told.'}
            </p>
          </div>
        )}

        {errors._ && <p className="text-sm text-destructive">{errors._}</p>}

        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)} disabled={saving}>Not now</Button>
          {info?.hr_available && (
            <Button size="sm" onClick={submit} disabled={saving || loading}>
              {saving ? 'Adding…' : 'Add to HR'}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
