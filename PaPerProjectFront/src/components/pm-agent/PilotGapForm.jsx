import React, { useMemo, useState } from 'react';
import { AlertTriangle, ArrowRight, CalendarClock, Check, Trash2, UserPlus, X } from 'lucide-react';
import { Button } from '@/components/ui/button';

/**
 * Review card for a Project Pilot proposal.
 *
 * Every proposal that would change anything comes here first; nothing is
 * written until the user confirms. New work is an editable form: the
 * assignee and deadline of every task, and the project deadline — gaps marked,
 * the rest pre-filled. Updates and deletes are listed against what is stored
 * now ("Status: To Do → Done", "Also deletes its 4 tasks"). Each task and each
 * change has a tick box; unticked ones are skipped.
 *
 * Deadlines arrive pre-filled. Where the agent gave none, the backend
 * suggests one (project_manager_agent/drafts.py `timeline`): tasks laid end to
 * end by their estimated effort, fitted inside the project's window. Each task
 * carries a `weight` — how far through the project it falls — so moving the
 * project deadline re-spreads every task date the user has not set by hand.
 *
 * Nothing is required. Clearing a field is a legitimate choice and is sent as
 * "clear it"; the point is that the user decides, rather than finding out
 * afterwards.
 *
 * Props
 *   data       the `needs_input` payload: { rows, changes, timeline, users, no_users, summary }
 *   onConfirm  (answers, skip) => void, answers = { actionIndex: { field: value } },
 *              skip = [actionIndex] the user unticked
 *   onCancel   optional; the user dismissed the proposal
 *   busy       disables the form while the confirm request is in flight
 *   done       set once applied; the card stops being interactive
 *   cancelled  set once dismissed
 *   compact    one column, for narrow chats
 */

const DAY = 86400000;
const toUtc = (iso) => {
  const [y, m, d] = iso.split('-').map(Number);
  return Date.UTC(y, m - 1, d);
};
const toIso = (ms) => new Date(ms).toISOString().slice(0, 10);

/** Place a task `weight` of the way from start to end, avoiding weekends. */
function spread(weight, startIso, endIso) {
  const start = toUtc(startIso);
  const end = toUtc(endIso);
  if (end < start) return startIso;
  const span = Math.round((end - start) / DAY);
  let at = start + Math.round(weight * span) * DAY;
  // Pull a Saturday or Sunday back to the Friday, but never before the start.
  while ([0, 6].includes(new Date(at).getUTCDay()) && at > start) at -= DAY;
  return toIso(Math.min(Math.max(at, start), end));
}

const niceDate = (iso) => {
  if (!iso) return '';
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
};

/** Drafts saved before rows existed only carry `items` (the gaps). */
function legacyRows(data) {
  return (data?.items || []).map((item) => ({
    index: item.index,
    action: item.action,
    title: item.title,
    assignee_id: null,
    due_date: null,
    deadline: null,
    missing: item.gaps.map((g) => g.field),
  }));
}

const SuggestedTag = () => (
  <span className="ml-1.5 rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
    suggested
  </span>
);

const PilotGapForm = ({
  data, onConfirm, onCancel, busy = false, done = false, cancelled = false, compact = false,
}) => {
  const rows = data?.rows?.length ? data.rows : legacyRows(data);
  const changes = data?.changes || [];
  // Unticked tasks and changes; a change that can't be made starts unticked.
  const [skipped, setSkipped] = useState(() => new Set(changes.filter((c) => c.problem).map((c) => c.index)));
  const toggleSkip = (index) => setSkipped((prev) => {
    const next = new Set(prev);
    if (next.has(index)) next.delete(index); else next.add(index);
    return next;
  });
  const timeline = data?.timeline || null;
  const users = data?.users
    || (data?.items || []).flatMap((i) => i.gaps).find((g) => g.input === 'user')?.options
    || [];
  const noUsers = users.length === 0;

  const projectRow = rows.find((r) => r.action === 'create_project');
  const taskRows = rows.filter((r) => r.action === 'create_task');

  const [projectDeadline, setProjectDeadline] = useState(
    projectRow?.deadline || timeline?.deadline || '',
  );
  const [values, setValues] = useState(() => Object.fromEntries(
    taskRows.map((r) => [r.index, {
      assignee_id: r.assignee_id != null ? String(r.assignee_id) : '',
      due_date: r.due_date || '',
    }]),
  ));
  // Task dates the user set by hand. Moving the project deadline leaves these
  // alone and re-spreads the rest.
  const [pinned, setPinned] = useState(() => new Set());

  const setTask = (index, field, value) => {
    setValues((prev) => ({ ...prev, [index]: { ...prev[index], [field]: value } }));
    if (field === 'due_date') setPinned((prev) => new Set(prev).add(index));
  };

  const moveProjectDeadline = (iso) => {
    setProjectDeadline(iso);
    if (!iso || !timeline?.start) return;
    setValues((prev) => {
      const next = { ...prev };
      taskRows.forEach((r) => {
        if (r.weight == null || pinned.has(r.index)) return;
        next[r.index] = { ...next[r.index], due_date: spread(r.weight, timeline.start, iso) };
      });
      return next;
    });
  };

  // The task service refuses a task due after its project's deadline (or,
  // for an existing project, before its start). Say so here, before confirming.
  const problems = useMemo(() => {
    const out = {};
    taskRows.forEach((r) => {
      const due = values[r.index]?.due_date;
      if (!due) return;
      if (projectDeadline && due > projectDeadline) out[r.index] = 'After the project deadline';
      else if (timeline && !timeline.deadline_editable && timeline.start && due < timeline.start) {
        out[r.index] = 'Before the project starts';
      }
    });
    return out;
  }, [values, projectDeadline, timeline, taskRows]);

  // Assignees on approved leave before the task is due (from HR). A warning,
  // not a block — recomputed as the assignee or date changes.
  const leaveWarnings = useMemo(() => {
    const today = new Date().toLocaleDateString('en-CA');           // YYYY-MM-DD, local
    const from = timeline?.start && timeline.start > today ? timeline.start : today;
    const out = {};
    taskRows.forEach((r) => {
      const { assignee_id: id, due_date: due } = values[r.index] || {};
      if (!id || !due) return;
      const person = users.find((u) => String(u.id) === String(id));
      const clash = (person?.on_leave || []).find((l) => l.start <= due && l.end >= from);
      if (clash) out[r.index] = `${person.name}: ${clash.label}`;
    });
    return out;
  }, [values, timeline, taskRows, users]);

  const emptyCount = useMemo(() => {
    let n = taskRows.filter((r) => !skipped.has(r.index)).reduce((acc, r) => acc
      + (values[r.index]?.assignee_id ? 0 : 1)
      + (values[r.index]?.due_date ? 0 : 1), 0);
    if (projectRow && !projectDeadline) n += 1;
    return n;
  }, [values, projectDeadline, taskRows, projectRow, skipped]);

  const submit = () => {
    const answers = {};
    if (projectRow) answers[projectRow.index] = { deadline: projectDeadline };
    taskRows.forEach((r) => {
      answers[r.index] = {
        assignee_id: values[r.index]?.assignee_id || '',
        due_date: values[r.index]?.due_date || '',
      };
    });
    onConfirm(answers, [...skipped]);
  };

  if (!rows.length && !changes.length) return null;
  const locked = busy || done || cancelled;
  const problemCount = Object.keys(problems).filter((i) => !skipped.has(Number(i))).length;
  const keptChanges = changes.filter((c) => !skipped.has(c.index));
  const deletes = keptChanges.filter((c) => c.kind === 'delete').length;
  const keptTasks = taskRows.filter((r) => !skipped.has(r.index)).length;
  const nothingLeft = !projectRow && keptTasks === 0 && keptChanges.length === 0;

  return (
    <div className="mt-3 rounded-xl border border-border bg-card p-4 space-y-4">
      <div className="flex items-start gap-2">
        <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0 text-amber-500" />
        <div className="text-sm">
          <p className="font-semibold text-foreground">
            {changes.length && !rows.length ? 'Review these changes' : 'Review before I make this'}
          </p>
          <p className="text-muted-foreground">
            {rows.some((r) => r.missing?.length)
              ? 'Some details weren\u2019t in your request, so I\u2019ve suggested them. Change anything you like.'
              : 'Nothing changes until you confirm. Untick anything you don\u2019t want.'}
          </p>
        </div>
      </div>

      {noUsers && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm">
          <UserPlus className="h-4 w-4 mt-0.5 shrink-0 text-amber-600 dark:text-amber-400" />
          <p className="text-foreground">
            There are no team members to assign work to yet. You can still create these and
            assign them later.
          </p>
        </div>
      )}

      {/* Project deadline: editable for a new project, shown for an existing one. */}
      {projectRow ? (
        <div className="rounded-lg border border-border bg-background p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-semibold text-foreground">Project: {projectRow.title}</p>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <CalendarClock className="h-3.5 w-3.5" />
              Deadline
              {projectRow.suggested && projectDeadline === projectRow.deadline && <SuggestedTag />}
              <input
                type="date"
                value={projectDeadline}
                min={timeline?.start || undefined}
                disabled={locked}
                onChange={(e) => moveProjectDeadline(e.target.value)}
                className="h-8 rounded-md border border-input bg-background px-2 text-sm text-foreground disabled:opacity-50"
              />
            </label>
          </div>
          {taskRows.some((r) => r.weight != null) && (
            <p className="mt-1.5 text-xs text-muted-foreground">
              Moving this re-spreads the task dates you haven&apos;t changed yourself.
            </p>
          )}
        </div>
      ) : taskRows.length > 0 && timeline?.deadline ? (
        <p className="text-xs text-muted-foreground">
          Adding to an existing project — due {niceDate(timeline.deadline)}.
        </p>
      ) : null}

      <div className="space-y-2">
        {taskRows.map((row) => {
          const v = values[row.index] || {};
          const suggestedDate = row.suggested && v.due_date === row.due_date && !pinned.has(row.index);
          return (
            <div
              key={row.index}
              className={`rounded-lg border border-border bg-background p-3 ${skipped.has(row.index) ? 'opacity-50' : ''}`}
            >
              <label className="mb-2 flex items-center gap-2 text-sm font-medium text-foreground">
                <input
                  type="checkbox"
                  checked={!skipped.has(row.index)}
                  disabled={locked}
                  onChange={() => toggleSkip(row.index)}
                  aria-label={`Include ${row.title}`}
                />
                {row.title}
              </label>
              <div className={`grid gap-2 ${compact ? '' : 'sm:grid-cols-2'}`}>
                <label className="space-y-1">
                  <span className="block text-xs text-muted-foreground">
                    Assigned to
                    {row.missing?.includes('assignee_id') && !v.assignee_id && (
                      <span className="ml-1.5 text-amber-600 dark:text-amber-400">— not in your request</span>
                    )}
                  </span>
                  <select
                    value={v.assignee_id || ''}
                    disabled={locked || noUsers}
                    onChange={(e) => setTask(row.index, 'assignee_id', e.target.value)}
                    className="w-full h-9 rounded-md border border-input bg-background px-2 text-sm text-foreground disabled:opacity-50"
                  >
                    <option value="">{noUsers ? 'No team members yet' : 'Unassigned'}</option>
                    {users.map((u) => (
                      <option key={u.id} value={String(u.id)}>
                        {u.name}{u.role ? ` — ${u.role}` : ''}
                        {u.on_leave?.length ? ` · ${u.on_leave[0].label}` : ''}
                      </option>
                    ))}
                  </select>
                  {leaveWarnings[row.index] && (
                    <span className="block text-xs text-amber-600 dark:text-amber-400">
                      {leaveWarnings[row.index]} — before this is due.
                    </span>
                  )}
                </label>
                <label className="space-y-1">
                  <span className="block text-xs text-muted-foreground">
                    Due
                    {suggestedDate && <SuggestedTag />}
                  </span>
                  <input
                    type="date"
                    value={v.due_date || ''}
                    disabled={locked}
                    onChange={(e) => setTask(row.index, 'due_date', e.target.value)}
                    className={`w-full h-9 rounded-md border bg-background px-2 text-sm text-foreground disabled:opacity-50 ${
                      problems[row.index] ? 'border-destructive' : 'border-input'
                    }`}
                  />
                  {problems[row.index] && (
                    <span className="block text-xs text-destructive">{problems[row.index]}</span>
                  )}
                </label>
              </div>
            </div>
          );
        })}
      </div>

      {changes.length > 0 && (
        <div className="space-y-2">
          {changes.map((c) => {
            const off = skipped.has(c.index);
            const isDelete = c.kind === 'delete';
            return (
              <div
                key={c.index}
                className={`rounded-lg border p-3 ${isDelete ? 'border-destructive/40 bg-destructive/5' : 'border-border bg-background'} ${off ? 'opacity-50' : ''}`}
              >
                <label className="flex items-start gap-2 text-sm text-foreground">
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={!off}
                    disabled={locked || !!c.problem}
                    onChange={() => toggleSkip(c.index)}
                    aria-label={`${isDelete ? 'Delete' : 'Change'} ${c.title}`}
                  />
                  <span className="min-w-0">
                    <span className={`font-medium ${isDelete ? 'text-destructive' : ''}`}>
                      {isDelete && <Trash2 className="mr-1 inline h-3.5 w-3.5 -mt-0.5" />}
                      {isDelete ? 'Delete' : 'Change'} {c.target}: {c.title}
                    </span>
                    {c.project && <span className="text-muted-foreground"> · {c.project}</span>}
                    {c.effect && <span className="block text-xs text-destructive">{c.effect}</span>}
                    {c.problem && <span className="block text-xs text-amber-600 dark:text-amber-400">{c.problem}</span>}
                  </span>
                </label>
                {c.lines?.length > 0 && (
                  <ul className="mt-1.5 space-y-0.5 pl-6 text-xs">
                    {c.lines.map((l) => (
                      <li key={l.field} className="flex flex-wrap items-center gap-1 text-muted-foreground">
                        <span className="text-foreground">{l.label}:</span>
                        <span className="line-through">{l.before}</span>
                        <ArrowRight className="h-3 w-3" />
                        <span className="font-medium text-foreground">{l.after}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      )}

      {rows.length > 0 && (
      <div className="rounded-lg bg-muted/60 px-3 py-2">
        <p className="text-xs font-medium text-muted-foreground mb-1">This will create:</p>
        <ul className="text-sm text-foreground space-y-0.5">
          {(data?.summary || rows)
            .filter((s) => ['create_project', 'create_task'].includes(s.action) && !skipped.has(s.index))
            .map((s) => (
              <li key={s.index}>· {s.action === 'create_project' ? 'Project' : 'Task'} — {s.title}</li>
            ))}
        </ul>
      </div>
      )}

      {done ? (
        <p className="flex items-center gap-1.5 text-sm text-emerald-600 dark:text-emerald-400">
          <Check className="h-4 w-4" /> Done.
        </p>
      ) : cancelled ? (
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <X className="h-4 w-4" /> Cancelled — nothing was changed.
        </p>
      ) : (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <Button
            size="sm"
            variant={deletes ? 'destructive' : 'default'}
            disabled={busy || nothingLeft}
            onClick={submit}
          >
            {busy ? 'Working…' : deletes ? `Confirm, including ${deletes} delete${deletes === 1 ? '' : 's'}` : 'Confirm'}
          </Button>
          {onCancel && (
            <Button size="sm" variant="ghost" disabled={busy} onClick={onCancel}>Cancel</Button>
          )}
          {rows.length > 0 && (
            <span className="text-xs text-muted-foreground">
              {emptyCount > 0 ? `${emptyCount} detail${emptyCount === 1 ? '' : 's'} left empty` : 'Everything filled in'}
            </span>
          )}
          {problemCount > 0 && (
            <span className="text-xs text-destructive">
              {problemCount} task{problemCount === 1 ? '' : 's'} will be refused — dated outside the project
            </span>
          )}
        </div>
      )}
    </div>
  );
};

export default PilotGapForm;
