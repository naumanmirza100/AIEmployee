import React, { useMemo, useState } from 'react';
import { AlertTriangle, Check, UserPlus } from 'lucide-react';
import { Button } from '@/components/ui/button';

/**
 * The form the Project Pilot shows when its proposal is missing details.
 *
 * The agent only knows what the user's sentence mentioned, so "plan the
 * rebuild" used to become a project with no deadline and a pile of unassigned
 * tasks — created immediately, with nothing said about it. The backend now
 * holds the proposal back and reports the gaps; this renders them.
 *
 * Every gap is optional to fill. Leaving one blank is a legitimate choice, so
 * the confirm button always works — the point is that the user is told, not
 * that they are forced. The summary underneath lists exactly what will be
 * created so the decision is made against the real thing.
 *
 * Props
 *   data       the `needs_input` payload: { items, summary, no_users, actions }
 *   onConfirm  (answers) => void, where answers is {actionIndex: {field: value}}
 *   busy       disables the controls while the confirm request is in flight
 *   done       set once applied, so the card stops being interactive
 */
const PilotGapForm = ({ data, onConfirm, busy = false, done = false }) => {
  const items = data?.items || [];
  const summary = data?.summary || [];
  const [answers, setAnswers] = useState({});

  const setAnswer = (index, field, value) => {
    setAnswers((prev) => ({ ...prev, [index]: { ...(prev[index] || {}), [field]: value } }));
  };

  // How many gaps the user has actually filled, for the confirm button's label.
  const totals = useMemo(() => {
    const all = items.reduce((n, item) => n + item.gaps.length, 0);
    const filled = Object.values(answers)
      .reduce((n, fields) => n + Object.values(fields).filter((v) => v !== '' && v != null).length, 0);
    return { all, filled, blank: Math.max(0, all - filled) };
  }, [items, answers]);

  if (!items.length) return null;

  return (
    <div className="mt-3 rounded-xl border border-border bg-card p-4 space-y-4">
      <div className="flex items-start gap-2">
        <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0 text-amber-500" />
        <div className="text-sm">
          <p className="font-semibold text-foreground">Before I create this, a few details are missing</p>
          <p className="text-muted-foreground">
            Fill in what you know. Anything left blank is simply created empty.
          </p>
        </div>
      </div>

      {data?.no_users && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm">
          <UserPlus className="h-4 w-4 mt-0.5 shrink-0 text-amber-600 dark:text-amber-400" />
          <p className="text-foreground">
            There are no team members to assign work to yet. You can still create these
            and assign them later.
          </p>
        </div>
      )}

      <div className="space-y-3">
        {items.map((item) => (
          <div key={item.index} className="rounded-lg border border-border bg-background p-3">
            <p className="text-sm font-medium text-foreground mb-2">
              {item.action === 'create_project' ? 'Project' : 'Task'}: {item.title}
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {item.gaps.map((gap) => {
                const value = answers[item.index]?.[gap.field] ?? '';
                const id = `gap-${item.index}-${gap.field}`;
                return (
                  <div key={gap.field} className="space-y-1">
                    <label htmlFor={id} className="block text-xs text-muted-foreground">
                      {gap.label}
                    </label>

                    {gap.input === 'user' ? (
                      <select
                        id={id}
                        value={value}
                        disabled={busy || done || gap.no_options}
                        onChange={(e) => setAnswer(item.index, gap.field, e.target.value)}
                        className="w-full h-9 rounded-md border border-input bg-background px-2 text-sm text-foreground disabled:opacity-50"
                      >
                        <option value="">
                          {gap.no_options ? 'No team members yet' : 'Leave unassigned'}
                        </option>
                        {(gap.options || []).map((u) => (
                          <option key={u.id} value={u.id}>
                            {u.name}{u.role ? ` — ${u.role}` : ''}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        id={id}
                        type="date"
                        value={value}
                        disabled={busy || done}
                        onChange={(e) => setAnswer(item.index, gap.field, e.target.value)}
                        className="w-full h-9 rounded-md border border-input bg-background px-2 text-sm text-foreground disabled:opacity-50"
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* What confirming actually does, spelled out rather than implied. */}
      <div className="rounded-lg bg-muted/60 px-3 py-2">
        <p className="text-xs font-medium text-muted-foreground mb-1">This will create:</p>
        <ul className="text-sm text-foreground space-y-0.5">
          {summary.map((s) => (
            <li key={s.index}>
              · {s.action === 'create_project' ? 'Project' : 'Task'} — {s.title}
            </li>
          ))}
        </ul>
      </div>

      {done ? (
        <p className="flex items-center gap-1.5 text-sm text-emerald-600 dark:text-emerald-400">
          <Check className="h-4 w-4" /> Created.
        </p>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" disabled={busy} onClick={() => onConfirm(answers)}>
            {busy ? 'Creating…' : 'Confirm and create'}
          </Button>
          <span className="text-xs text-muted-foreground">
            {totals.blank > 0
              ? `${totals.blank} of ${totals.all} details will be left empty`
              : 'All details filled in'}
          </span>
        </div>
      )}
    </div>
  );
};

export default PilotGapForm;
