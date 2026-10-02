import React, { useMemo, useState } from 'react';
import { AlertTriangle, CalendarClock, Check, Clock, Search, Users, X } from 'lucide-react';
import { Button } from '@/components/ui/button';

/**
 * Review form for a meeting request, before anything is booked.
 *
 * Every request typed into a scheduler comes here first — one that said
 * everything just has nothing marked missing.
 *
 * When a scheduling request doesn't say who, when or how long, the agent no
 * longer guesses (a silent 30 minutes), dead-ends ("couldn't find that user")
 * or shows a bare date picker. It returns a `draft` of everything it did
 * understand plus the list of what's `missing`, and this renders the lot:
 * the missing fields to fill in, the rest pre-filled to review, and a
 * summary to confirm against. Nothing is booked until the user confirms.
 *
 * The confirmed draft goes back as `pending_intent` with a `proposed_time`,
 * which the backend books directly — no second model call, so what gets
 * scheduled is exactly what is on screen.
 *
 * Props
 *   draft     { invitee_ids, invitee_names, proposed_time, duration_minutes, title, ... }
 *   missing   subset of ['attendees', 'time', 'duration']
 *   options   { users: [{id, name, email}], durations: [..], slots: [{iso, label}] }
 *   note      optional line, e.g. "I couldn't find **Zed** in your company."
 *   onConfirm (draft, proposedTimeIso) => void
 *   busy      disables the form while booking
 *   done      set once booked; the card stops being interactive
 */

const pad = (n) => String(n).padStart(2, '0');

/** ISO instant -> the value a datetime-local input wants, in local time. */
function toLocalInput(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const prettyWhen = (local) => {
  if (!local) return '';
  return new Date(local).toLocaleString(undefined, {
    weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit',
  });
};

const Needed = ({ show }) => (show ? (
  <span className="ml-1.5 text-[11px] font-normal text-amber-600 dark:text-amber-400">— not in your request</span>
) : null);

const MeetingDraftForm = ({ draft = {}, missing = [], options = {}, note, onConfirm, busy = false, done = false }) => {
  const users = options.users || [];
  const slots = options.slots || [];
  const durationChoices = useMemo(() => {
    const base = options.durations?.length ? options.durations : [15, 30, 45, 60, 90, 120];
    const current = Number(draft.duration_minutes) || 30;
    return base.includes(current) ? base : [...base, current].sort((a, b) => a - b);
  }, [options.durations, draft.duration_minutes]);

  const [title, setTitle] = useState(draft.title || '');
  const [attendeeIds, setAttendeeIds] = useState(() => (draft.invitee_ids || []).map(String));
  const [when, setWhen] = useState(() => toLocalInput(draft.proposed_time));
  const [duration, setDuration] = useState(() => Number(draft.duration_minutes) || 30);
  const [filter, setFilter] = useState('');

  const byId = useMemo(() => Object.fromEntries(users.map((u) => [String(u.id), u])), [users]);
  const nameOf = (id) => byId[id]?.name
    || draft.invitee_names?.[(draft.invitee_ids || []).map(String).indexOf(id)]
    || 'Unknown';

  const shown = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const list = q
      ? users.filter((u) => `${u.name} ${u.email}`.toLowerCase().includes(q))
      : users;
    return list.slice(0, 50);
  }, [users, filter]);

  const toggle = (id) => setAttendeeIds((prev) => (
    prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
  ));

  const inPast = when && new Date(when).getTime() < Date.now();
  const ready = attendeeIds.length > 0 && when && !inPast;
  const locked = busy || done;

  const confirm = () => {
    if (!ready) return;
    onConfirm({
      ...draft,
      title: title.trim() || null,
      invitee_ids: attendeeIds.map(Number),
      invitee_names: attendeeIds.map(nameOf),
      duration_minutes: Number(duration),
    }, new Date(when).toISOString());
  };

  return (
    <div className="mt-3 rounded-xl border border-border bg-card p-4 space-y-4 text-left">
      <div className="flex items-start gap-2">
        <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0 text-amber-500" />
        <div className="text-sm">
          <p className="font-semibold text-foreground">Review this meeting</p>
          <p className="text-muted-foreground">
            {missing.length
              ? 'Fill in what’s missing, check the rest, then confirm.'
              : 'Check the details, then confirm — nobody is invited until you do.'}
          </p>
        </div>
      </div>

      {note && (
        <p
          className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-foreground"
          // `note` is our own sentence with **bold** names; render the bold only.
          dangerouslySetInnerHTML={{ __html: String(note).replace(/[<>&]/g, '').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>') }}
        />
      )}

      <label className="block space-y-1">
        <span className="block text-xs text-muted-foreground">Title</span>
        <input
          type="text"
          value={title}
          placeholder={attendeeIds.length ? `Meeting with ${nameOf(attendeeIds[0])}` : 'Meeting'}
          disabled={locked}
          onChange={(e) => setTitle(e.target.value)}
          className="w-full h-9 rounded-md border border-input bg-background px-2 text-sm text-foreground disabled:opacity-50"
        />
      </label>

      {/* Who */}
      <div className="space-y-2">
        <span className="flex items-center text-xs text-muted-foreground">
          <Users className="mr-1 h-3.5 w-3.5" /> Attendees
          <Needed show={missing.includes('attendees') && attendeeIds.length === 0} />
        </span>
        {attendeeIds.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {attendeeIds.map((id) => (
              <span key={id} className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-1 text-xs text-foreground">
                {nameOf(id)}
                {!locked && (
                  <button type="button" onClick={() => toggle(id)} aria-label={`Remove ${nameOf(id)}`}>
                    <X className="h-3 w-3 text-muted-foreground hover:text-foreground" />
                  </button>
                )}
              </span>
            ))}
          </div>
        )}
        {!locked && (
          users.length === 0 ? (
            <p className="text-xs text-muted-foreground">There are no team members to invite yet.</p>
          ) : (
            <div className="rounded-lg border border-border bg-background">
              <div className="flex items-center gap-2 border-b border-border px-2">
                <Search className="h-3.5 w-3.5 text-muted-foreground" />
                <input
                  type="text"
                  value={filter}
                  placeholder="Search people"
                  onChange={(e) => setFilter(e.target.value)}
                  className="h-8 w-full bg-transparent text-sm text-foreground outline-none"
                />
              </div>
              <div className="max-h-40 overflow-y-auto p-1">
                {shown.map((u) => {
                  const id = String(u.id);
                  return (
                    <label key={id} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm hover:bg-accent">
                      <input type="checkbox" checked={attendeeIds.includes(id)} onChange={() => toggle(id)} />
                      <span className="text-foreground">{u.name}</span>
                      {u.email && <span className="truncate text-xs text-muted-foreground">{u.email}</span>}
                    </label>
                  );
                })}
                {shown.length === 0 && <p className="px-2 py-1 text-xs text-muted-foreground">No matches.</p>}
              </div>
            </div>
          )
        )}
      </div>

      {/* When + how long */}
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block space-y-1">
          <span className="flex items-center text-xs text-muted-foreground">
            <CalendarClock className="mr-1 h-3.5 w-3.5" /> When
            <Needed show={missing.includes('time') && !when} />
          </span>
          <input
            type="datetime-local"
            value={when}
            disabled={locked}
            onChange={(e) => setWhen(e.target.value)}
            className={`w-full h-9 rounded-md border bg-background px-2 text-sm text-foreground disabled:opacity-50 ${inPast ? 'border-destructive' : 'border-input'}`}
          />
          {inPast && <span className="block text-xs text-destructive">That time has already passed.</span>}
        </label>
        <label className="block space-y-1">
          <span className="flex items-center text-xs text-muted-foreground">
            <Clock className="mr-1 h-3.5 w-3.5" /> How long
            <Needed show={missing.includes('duration')} />
          </span>
          <select
            value={duration}
            disabled={locked}
            onChange={(e) => setDuration(Number(e.target.value))}
            className="w-full h-9 rounded-md border border-input bg-background px-2 text-sm text-foreground disabled:opacity-50"
          >
            {durationChoices.map((m) => (
              <option key={m} value={m}>{m < 60 ? `${m} minutes` : `${m / 60} hour${m === 60 ? '' : 's'}`}</option>
            ))}
          </select>
        </label>
      </div>

      {slots.length > 0 && !locked && (
        <div className="space-y-1.5">
          <span className="block text-xs text-muted-foreground">Everyone is free at:</span>
          <div className="flex flex-wrap gap-1.5">
            {slots.map((s) => {
              const local = toLocalInput(s.iso);
              return (
                <button
                  key={s.iso}
                  type="button"
                  onClick={() => setWhen(local)}
                  className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
                    when === local
                      ? 'border-primary bg-primary text-primary-foreground'
                      : 'border-border bg-background text-foreground hover:bg-accent'
                  }`}
                >
                  {s.label}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* What confirming actually books */}
      <div className="rounded-lg bg-muted/60 px-3 py-2 text-sm text-foreground">
        {attendeeIds.length && when ? (
          <>
            <span className="font-medium">{title.trim() || `Meeting with ${nameOf(attendeeIds[0])}`}</span>
            {' — with '}{attendeeIds.map(nameOf).join(', ')}
            {', '}{prettyWhen(when)}{' · '}{duration} min
          </>
        ) : (
          <span className="text-muted-foreground">
            {attendeeIds.length ? 'Pick a time to continue.' : 'Choose who should attend to continue.'}
          </span>
        )}
      </div>

      {done ? (
        <p className="flex items-center gap-1.5 text-sm text-emerald-600 dark:text-emerald-400">
          <Check className="h-4 w-4" /> Booked.
        </p>
      ) : (
        <Button size="sm" disabled={!ready || busy} onClick={confirm}>
          {busy ? 'Booking…' : 'Confirm and book'}
        </Button>
      )}
    </div>
  );
};

export default MeetingDraftForm;
