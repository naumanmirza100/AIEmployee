import React from 'react';
import { ArrowDown, ArrowUp, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

/**
 * HR workflow steps as forms, not JSON (24 Nov 2026). Each step keeps any field the builder doesn't show, so a step
 * written by hand, or by a template, survives being edited here. "If … otherwise" steps nest a list of their own.
 */

export const STEP_TYPES = [
  { value: 'send_email', label: 'Send an email' },
  { value: 'notify', label: 'Alert in the bell' },
  { value: 'notify_template', label: 'Send a saved message' },
  { value: 'create_task', label: 'Create a Project Manager task' },
  { value: 'schedule_meeting', label: 'Book a meeting' },
  { value: 'update_employee', label: 'Change the employee record' },
  { value: 'assign_manager', label: 'Set the manager' },
  { value: 'update_leave_balance', label: 'Adjust a leave balance' },
  { value: 'wait', label: 'Wait' },
  { value: 'wait_for_approval', label: 'Wait for an HR admin to approve' },
  { value: 'branch', label: 'If … then … otherwise' },
];

const NEW_STEP = {
  send_email: { recipient_email: '{{employee_email}}', subject: '', body: '' },
  notify: { to: ['hr_admins'], title: '', message: '' },
  notify_template: { template_id: null, delay_minutes: 0 },
  create_task: { title: '', description: '', assignee: 'employee', priority: 'medium', due_in_days: 7 },
  schedule_meeting: { title: '', meeting_type: 'one_on_one', duration_minutes: 30, offset_days_from_start: 0, with_manager: true },
  update_employee: { fields: { employment_status: 'active' } },
  assign_manager: { manager_id: null },
  update_leave_balance: { leave_type: 'vacation', delta_accrued_days: 0 },
  wait: { seconds: 3600 },
  wait_for_approval: { message: 'Please approve to carry on.' },
  branch: { condition: { left: 'employee.department', op: '==', right: '' }, if_true: [], if_false: [] },
};

const MEETING_TYPES = [
  ['onboarding_orientation', 'Onboarding orientation'], ['one_on_one', '1:1 with manager'],
  ['performance_review', 'Performance review'], ['mid_year_check_in', 'Mid-year check-in'],
  ['exit_interview', 'Exit interview'], ['training_session', 'Training session'],
  ['benefits_consult', 'Benefits consultation'], ['other', 'Other'],
];
const LEAVE_TYPES = ['vacation', 'sick', 'parental', 'bereavement', 'unpaid', 'other'];
const EMPLOYEE_FIELDS = [
  ['employment_status', 'Status'], ['employment_type', 'Employment type'], ['job_title', 'Job title'],
  ['department', 'Department'], ['probation_end_date', 'Probation ends (YYYY-MM-DD)'], ['timezone_name', 'Time zone'],
];
const CONDITION_FIELDS = [
  ['employee.department', "The employee's department"], ['employee.job_title', "The employee's job title"],
  ['employment_type', 'Employment type'], ['employment_status', 'Employment status'], ['leave_type', 'Leave type'],
  ['days_requested', 'Leave days asked for'], ['department', 'Department (from the event)'],
];
const OPERATORS = [
  ['==', 'is'], ['!=', 'is not'], ['contains', 'contains'], ['>', 'is more than'], ['<', 'is less than'],
  ['is_empty', 'is empty'], ['is_not_empty', 'is not empty'],
];
const WAIT_UNITS = [['60', 'minutes'], ['3600', 'hours']];

const selectClass = 'h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground';

const Field = ({ label, children, hint }) => (
  <div className="space-y-1">
    <Label className="text-xs">{label}</Label>
    {children}
    {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
  </div>
);

const PLACEHOLDER_HINT = 'You can use {{employee_name}}, {{employee_email}}, {{employee.manager_name}}, {{employee.start_date}}, {{leave_type}}.';

/** One step's own fields. */
function StepFields({ step, set, options, depth }) {
  const num = (v) => (v === '' || v === null || v === undefined ? '' : Number(v));
  switch (step.type) {
    case 'send_email':
      return (
        <div className="grid gap-2">
          <Field label="To" hint="An address, or {{employee_email}} for the employee the workflow runs for.">
            <Input value={step.recipient_email || step.to || ''} onChange={(e) => set({ recipient_email: e.target.value, to: undefined })} />
          </Field>
          <Field label="Message">
            <select className={selectClass} value={step.template_id ? String(step.template_id) : ''}
              onChange={(e) => set({ template_id: e.target.value ? Number(e.target.value) : undefined, template_name: undefined })}>
              <option value="">Written here</option>
              {(options.templates || []).map((t) => <option key={t.id} value={t.id}>Template: {t.name}</option>)}
            </select>
          </Field>
          {!step.template_id && !step.template_name && (
            <>
              <Field label="Subject"><Input value={step.subject || ''} onChange={(e) => set({ subject: e.target.value })} /></Field>
              <Field label="Text" hint={PLACEHOLDER_HINT}>
                <Textarea rows={4} value={step.body || ''} onChange={(e) => set({ body: e.target.value })} />
              </Field>
            </>
          )}
          {step.template_name && !step.template_id && (
            <p className="text-xs text-muted-foreground">Uses the template named "{step.template_name}".</p>
          )}
        </div>
      );
    case 'notify': {
      const to = Array.isArray(step.to) ? step.to : [step.to || 'hr_admins'];
      const toggle = (who) => set({ to: to.includes(who) ? to.filter((w) => w !== who) : [...to, who] });
      return (
        <div className="grid gap-2">
          <Field label="Who is told">
            <div className="flex flex-wrap gap-3 text-sm">
              {[['hr_admins', 'HR admins'], ['manager', "The employee's manager"], ['employee', 'The employee']].map(([value, label]) => (
                <label key={value} className="flex items-center gap-1.5">
                  <input type="checkbox" checked={to.includes(value)} onChange={() => toggle(value)} /> {label}
                </label>
              ))}
            </div>
          </Field>
          <Field label="Title"><Input value={step.title || ''} onChange={(e) => set({ title: e.target.value })} /></Field>
          <Field label="Message" hint={PLACEHOLDER_HINT}>
            <Textarea rows={3} value={step.message || ''} onChange={(e) => set({ message: e.target.value })} />
          </Field>
        </div>
      );
    }
    case 'notify_template':
      return (
        <div className="grid gap-2 sm:grid-cols-2">
          <Field label="Saved message">
            <select className={selectClass} value={step.template_id ? String(step.template_id) : ''}
              onChange={(e) => set({ template_id: e.target.value ? Number(e.target.value) : null, template_name: undefined })}>
              <option value="">{step.template_name ? `"${step.template_name}"` : 'Choose…'}</option>
              {(options.templates || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </Field>
          <Field label="Send it after (minutes)">
            <Input type="number" min={0} value={num(step.delay_minutes)} onChange={(e) => set({ delay_minutes: Number(e.target.value) || 0 })} />
          </Field>
        </div>
      );
    case 'create_task':
      return (
        <div className="grid gap-2">
          <Field label="Project" hint={options.has_project_manager ? 'With none chosen, HR admins get the task as an alert.'
            : 'The company has no Project Manager agent: HR admins get the task as an alert.'}>
            <select className={selectClass} value={step.project_id ? String(step.project_id) : ''}
              onChange={(e) => set({ project_id: e.target.value ? Number(e.target.value) : undefined })}>
              <option value="">None</option>
              {(options.projects || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </Field>
          <Field label="Title" hint={PLACEHOLDER_HINT}><Input value={step.title || ''} onChange={(e) => set({ title: e.target.value })} /></Field>
          <Field label="Description"><Textarea rows={2} value={step.description || ''} onChange={(e) => set({ description: e.target.value })} /></Field>
          <div className="grid gap-2 sm:grid-cols-3">
            <Field label="Given to">
              <select className={selectClass} value={step.assignee || ''} onChange={(e) => set({ assignee: e.target.value || undefined })}>
                <option value="">Nobody yet</option>
                <option value="employee">The employee</option>
                <option value="manager">Their manager</option>
              </select>
            </Field>
            <Field label="Priority">
              <select className={selectClass} value={step.priority || 'medium'} onChange={(e) => set({ priority: e.target.value })}>
                {['low', 'medium', 'high'].map((p) => <option key={p} value={p}>{p[0].toUpperCase() + p.slice(1)}</option>)}
              </select>
            </Field>
            <Field label="Due in (days)">
              <Input type="number" min={0} value={num(step.due_in_days)} onChange={(e) => set({ due_in_days: e.target.value === '' ? undefined : Number(e.target.value) })} />
            </Field>
          </div>
        </div>
      );
    case 'schedule_meeting': {
      const fromStart = step.offset_days_from_now === undefined || step.offset_days_from_now === null;
      return (
        <div className="grid gap-2">
          <Field label="Title" hint={PLACEHOLDER_HINT}><Input value={step.title || ''} onChange={(e) => set({ title: e.target.value })} /></Field>
          <div className="grid gap-2 sm:grid-cols-3">
            <Field label="Kind">
              <select className={selectClass} value={step.meeting_type || 'one_on_one'} onChange={(e) => set({ meeting_type: e.target.value })}>
                {MEETING_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </Field>
            <Field label="Length (minutes)">
              <Input type="number" min={5} max={480} value={num(step.duration_minutes)} onChange={(e) => set({ duration_minutes: Number(e.target.value) || 30 })} />
            </Field>
            <Field label="When (days)" hint={fromStart ? 'After the employee starts' : 'After the workflow runs'}>
              <div className="flex gap-1">
                <Input type="number" min={0} className="w-20"
                  value={num(fromStart ? step.offset_days_from_start : step.offset_days_from_now)}
                  onChange={(e) => set(fromStart ? { offset_days_from_start: Number(e.target.value) || 0 }
                    : { offset_days_from_now: Number(e.target.value) || 0 })} />
                <select className={selectClass} value={fromStart ? 'start' : 'now'}
                  onChange={(e) => {
                    const days = (fromStart ? step.offset_days_from_start : step.offset_days_from_now) || 0;
                    set(e.target.value === 'start' ? { offset_days_from_start: days, offset_days_from_now: undefined }
                      : { offset_days_from_now: days, offset_days_from_start: undefined });
                  }}>
                  <option value="start">after the start date</option>
                  <option value="now">from the run</option>
                </select>
              </div>
            </Field>
          </div>
          <div className="flex flex-wrap gap-4 text-sm">
            <label className="flex items-center gap-1.5"><input type="checkbox" checked={!!step.with_manager} onChange={(e) => set({ with_manager: e.target.checked })} /> With their manager</label>
            <label className="flex items-center gap-1.5"><input type="checkbox" checked={!!step.with_hr} onChange={(e) => set({ with_hr: e.target.checked })} /> With HR</label>
          </div>
        </div>
      );
    }
    case 'update_employee': {
      const fields = step.fields && typeof step.fields === 'object' ? step.fields : {};
      const entries = Object.entries(fields);
      const setFields = (next) => set({ fields: next });
      const unused = EMPLOYEE_FIELDS.filter(([key]) => !(key in fields));
      return (
        <div className="grid gap-2">
          {entries.map(([key, value]) => (
            <div key={key} className="flex gap-2 items-end">
              <Field label={(EMPLOYEE_FIELDS.find(([k]) => k === key) || [key, key])[1]}>
                <Input value={value ?? ''} onChange={(e) => setFields({ ...fields, [key]: e.target.value })} />
              </Field>
              <Button type="button" variant="ghost" size="icon" aria-label="Remove field"
                onClick={() => { const next = { ...fields }; delete next[key]; setFields(next); }}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          ))}
          {unused.length > 0 && (
            <select className={selectClass} value="" onChange={(e) => e.target.value && setFields({ ...fields, [e.target.value]: '' })}>
              <option value="">Change another field…</option>
              {unused.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
          )}
        </div>
      );
    }
    case 'assign_manager':
      return (
        <Field label="Manager">
          <select className={selectClass} value={step.manager_id ? String(step.manager_id) : ''}
            onChange={(e) => set({ manager_id: e.target.value ? Number(e.target.value) : null })}>
            <option value="">Choose…</option>
            {(options.employees || []).map((e) => <option key={e.id} value={e.id}>{e.full_name}{e.job_title ? ` — ${e.job_title}` : ''}</option>)}
          </select>
        </Field>
      );
    case 'update_leave_balance':
      return (
        <div className="grid gap-2 sm:grid-cols-3">
          <Field label="Leave type">
            <select className={selectClass} value={step.leave_type || 'vacation'} onChange={(e) => set({ leave_type: e.target.value })}>
              {LEAVE_TYPES.map((t) => <option key={t} value={t}>{t[0].toUpperCase() + t.slice(1)}</option>)}
            </select>
          </Field>
          <Field label="Days added to the allowance">
            <Input type="number" step="0.5" value={num(step.delta_accrued_days)} onChange={(e) => set({ delta_accrued_days: Number(e.target.value) || 0 })} />
          </Field>
          <Field label="Days counted as used">
            <Input type="number" step="0.5" value={num(step.delta_used_days)} onChange={(e) => set({ delta_used_days: Number(e.target.value) || 0 })} />
          </Field>
        </div>
      );
    case 'wait': {
      const seconds = Number(step.seconds) || 0;
      const unit = seconds && seconds % 3600 === 0 ? '3600' : '60';
      return (
        <Field label="Wait for" hint="At most a day; for longer, start the next part from an event.">
          <div className="flex gap-2">
            <Input type="number" min={0} className="w-24" value={seconds / Number(unit)}
              onChange={(e) => set({ seconds: Math.min(86400, (Number(e.target.value) || 0) * Number(unit)) })} />
            <select className={selectClass} value={unit}
              onChange={(e) => set({ seconds: Math.min(86400, (seconds / Number(unit)) * Number(e.target.value)) })}>
              {WAIT_UNITS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
        </Field>
      );
    }
    case 'wait_for_approval':
      return (
        <Field label="What the approver is asked" hint="The run waits under Run history until an HR admin approves or rejects it.">
          <Textarea rows={2} value={step.message || ''} onChange={(e) => set({ message: e.target.value })} />
        </Field>
      );
    case 'branch': {
      const cond = step.condition && typeof step.condition === 'object' && !Array.isArray(step.condition)
        ? step.condition : { left: '', op: '==', right: '' };
      const setCond = (patch) => set({ condition: { ...cond, ...patch } });
      const noValue = ['is_empty', 'is_not_empty'].includes(cond.op);
      if (typeof step.condition === 'string' || cond.all || cond.any || cond.not) {
        return <p className="text-xs text-muted-foreground">This condition was written by hand; edit it as JSON.</p>;
      }
      return (
        <div className="grid gap-2">
          <div className="grid gap-2 sm:grid-cols-3">
            <Field label="If">
              <select className={selectClass} value={cond.left || ''} onChange={(e) => setCond({ left: e.target.value })}>
                {!CONDITION_FIELDS.some(([k]) => k === cond.left) && cond.left && <option value={cond.left}>{cond.left}</option>}
                {CONDITION_FIELDS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </Field>
            <Field label="&nbsp;">
              <select className={selectClass} value={cond.op || '=='} onChange={(e) => setCond({ op: e.target.value })}>
                {OPERATORS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </Field>
            {!noValue && (
              <Field label="&nbsp;"><Input value={cond.right ?? ''} onChange={(e) => setCond({ right: e.target.value })} /></Field>
            )}
          </div>
          <div className="rounded-md border border-emerald-500/30 p-2">
            <p className="mb-1 text-xs font-medium text-emerald-300">Then</p>
            <StepList steps={step.if_true || []} onChange={(next) => set({ if_true: next })} options={options} depth={depth + 1} />
          </div>
          <div className="rounded-md border border-white/10 p-2">
            <p className="mb-1 text-xs font-medium text-muted-foreground">Otherwise</p>
            <StepList steps={step.if_false || []} onChange={(next) => set({ if_false: next })} options={options} depth={depth + 1} />
          </div>
        </div>
      );
    }
    default:
      return <p className="text-xs text-muted-foreground">This step ({step.type || 'no type'}) has no form here; edit it as JSON.</p>;
  }
}

/** A list of steps: add, change, move and remove. */
export function StepList({ steps, onChange, options = {}, depth = 0 }) {
  const list = Array.isArray(steps) ? steps : [];
  const update = (index, patch) => onChange(list.map((s, i) => {
    if (i !== index) return s;
    const next = { ...s, ...patch };
    Object.keys(next).forEach((k) => next[k] === undefined && delete next[k]);
    return next;
  }));
  const move = (index, by) => {
    const next = [...list];
    const [item] = next.splice(index, 1);
    next.splice(index + by, 0, item);
    onChange(next);
  };
  const add = (type) => onChange([...list, { type, ...(NEW_STEP[type] || {}) }]);
  const types = depth >= 2 ? STEP_TYPES.filter((t) => t.value !== 'branch') : STEP_TYPES;

  return (
    <div className="space-y-2">
      {list.map((step, index) => (
        <div key={index} className="rounded-lg border border-border bg-background/40 p-3" data-testid="HR-step">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-xs text-muted-foreground w-5">{index + 1}.</span>
            <select className={`${selectClass} flex-1`} value={step.type || ''}
              onChange={(e) => onChange(list.map((s, i) => (i === index ? { type: e.target.value, ...(NEW_STEP[e.target.value] || {}) } : s)))}
              aria-label={`Step ${index + 1} type`}>
              {!STEP_TYPES.some((t) => t.value === step.type) && <option value={step.type}>{step.type || 'Choose…'}</option>}
              {types.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
            <Button type="button" variant="ghost" size="icon" disabled={index === 0} onClick={() => move(index, -1)} aria-label="Move up"><ArrowUp className="h-4 w-4" /></Button>
            <Button type="button" variant="ghost" size="icon" disabled={index === list.length - 1} onClick={() => move(index, 1)} aria-label="Move down"><ArrowDown className="h-4 w-4" /></Button>
            <Button type="button" variant="ghost" size="icon" onClick={() => onChange(list.filter((_, i) => i !== index))} aria-label="Remove step"><Trash2 className="h-4 w-4" /></Button>
          </div>
          <StepFields step={step} set={(patch) => update(index, patch)} options={options} depth={depth} />
          {!['branch', 'wait', 'wait_for_approval'].includes(step.type) && (
            <label className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
              <input type="checkbox" checked={!!step.continue_on_error} onChange={(e) => update(index, { continue_on_error: e.target.checked || undefined })} />
              If this step fails, carry on with the next
            </label>
          )}
        </div>
      ))}
      <select className={selectClass} value="" onChange={(e) => e.target.value && add(e.target.value)} aria-label="Add a step">
        <option value="">+ Add a step…</option>
        {types.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
      </select>
    </div>
  );
}

export default StepList;
