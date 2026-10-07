import React, { useEffect, useState } from 'react';
import { ArrowRightLeft, Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import hrAgentService from '@/services/hrAgentService';
import { getUserHandover, handOverUserWork } from '@/services/companyUserManagementService';

/**
 * Hand over a leaver's open work in every agent.
 *
 * Lists what they still own — open project tasks and projects they lead,
 * meetings they organise, support tickets, the people who report to them and
 * leave waiting for their decision, interviews they run or sit in on — with a
 * "Give to" choice per group. Nothing moves until HR confirms; a group left on
 * "Keep for now" stays put. Anything at a time the new person is busy is
 * skipped, and the result says why.
 */
const fmtWhen = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, {
    weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit',
  });
};

/**
 * `employeeId` opens it from an HR record. `userId` opens it for an employee
 * login from Company, Users, at an address that does not need the HR agent.
 */
export default function HandoverDialog({ employeeId, userId, open, onOpenChange, onDone }) {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [data, setData] = useState(null);
  const [choice, setChoice] = useState({});
  const [error, setError] = useState('');
  const [results, setResults] = useState(null);
  const [labels, setLabels] = useState({});

  const load = () => {
    setLoading(true);
    setError('');
    (userId ? getUserHandover(userId) : hrAgentService.getEmployeeHandover(employeeId))
      .then((res) => {
        setData(res?.data || null);
        setLabels(Object.fromEntries((res?.data?.groups || []).map((g) => [g.key, g.label])));
      })
      .catch((e) => setError(e?.message || 'Could not load their work.'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (!open || !(employeeId || userId)) return;
    setChoice({});
    setResults(null);
    setData(null);
    load();
  }, [open, employeeId, userId]);   // eslint-disable-line react-hooks/exhaustive-deps

  const chosen = Object.fromEntries(Object.entries(choice).filter(([, v]) => v));

  const confirm = async () => {
    setSaving(true);
    setError('');
    try {
      const res = await (userId ? handOverUserWork(userId, chosen)
        : hrAgentService.handOverEmployeeWork(employeeId, chosen));
      setResults(res?.data?.results || {});
      setData(res?.data?.remaining || null);
      setChoice({});
      const moved = Object.values(res?.data?.results || {}).reduce((n, r) => n + (r.moved || 0), 0);
      toast({ title: 'Work handed over', description: `${moved} item${moved === 1 ? '' : 's'} moved.` });
      onDone?.();
    } catch (e) {
      setError(e?.message || 'Could not hand over the work.');
    } finally {
      setSaving(false);
    }
  };

  const groups = data?.groups || [];
  const nothingLeft = data && groups.length === 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[95vw] max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ArrowRightLeft className="h-4 w-4" /> Hand over work{data?.employee ? ` — ${data.employee.full_name}` : ''}
          </DialogTitle>
          <DialogDescription>
            Everything they still own across the agents. Choose who takes each group; nothing moves until you confirm.
          </DialogDescription>
        </DialogHeader>

        {loading && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Looking through their work…
          </p>
        )}

        {results && Object.keys(results).length > 0 && (
          <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm space-y-1">
            {Object.entries(results).map(([key, r]) => (
              <p key={key}>
                {labels[key] ? `${labels[key]}: ` : ''}<span className="font-medium">{r.moved}</span> moved to {r.to}
                {r.skipped?.length ? ` — ${r.skipped.length} skipped: ${r.skipped.join('; ')}` : ''}
              </p>
            ))}
          </div>
        )}

        {nothingLeft && (
          <p className="text-sm text-muted-foreground">Nothing left to hand over in the agents.</p>
        )}

        <div className="space-y-3">
          {groups.map((g) => (
            <div key={g.key} className="rounded-lg border border-border bg-card p-3 space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-medium text-foreground">{g.label} <span className="text-muted-foreground">({g.count})</span></p>
                <select
                  aria-label={`Give ${g.label.toLowerCase()} to`}
                  value={choice[g.key] || ''}
                  onChange={(e) => setChoice((c) => ({ ...c, [g.key]: e.target.value ? Number(e.target.value) : '' }))}
                  className="h-9 min-w-[200px] rounded-md border border-input bg-background px-2 text-sm text-foreground"
                >
                  <option value="">Keep for now</option>
                  {g.targets.map((t) => <option key={t.id} value={t.id}>Give to {t.name}</option>)}
                </select>
              </div>
              {g.hint && <p className="text-xs text-muted-foreground">{g.hint}</p>}
              <ul className="max-h-32 overflow-y-auto text-xs text-muted-foreground space-y-0.5">
                {g.items.map((item) => (
                  <li key={item.id} className="truncate">
                    <span className="text-foreground">{item.title}</span>
                    {item.when ? ` · ${fmtWhen(item.when)}` : ''}
                    {item.detail ? ` · ${item.detail}` : ''}
                    {item.due ? ` · due ${item.due}` : ''}
                  </li>
                ))}
                {g.count > g.items.length && <li>…and {g.count - g.items.length} more</li>}
              </ul>
            </div>
          ))}
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)} disabled={saving}>
            {nothingLeft ? 'Close' : 'Not now'}
          </Button>
          {!nothingLeft && (
            <Button size="sm" onClick={confirm} disabled={saving || loading || Object.keys(chosen).length === 0}>
              {saving ? 'Handing over…' : 'Hand over'}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
