import React, { useEffect, useMemo, useState } from 'react';
import { Loader2, Search } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import { getInterviewerOptions, updateInterview } from '@/services/recruitmentAgentService';

/**
 * Choose colleagues who sit in on an interview, besides the recruiter.
 *
 * They're employee logins, so a booked interview becomes busy time on their
 * calendars (the one PM, HR and Frontline share) and appears on their own
 * meetings page. Adding someone to an interview that already has a time is
 * refused if they're busy then; the server's message names the clash.
 */
export default function InterviewersDialog({ interview, open, onOpenChange, onSaved }) {
  const { toast } = useToast();
  const [options, setOptions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [selected, setSelected] = useState([]);
  const [filter, setFilter] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open || !interview) return;
    setSelected((interview.interviewers || []).map((u) => u.id));
    setFilter('');
    setError('');
    setLoading(true);
    getInterviewerOptions()
      .then((res) => setOptions(res?.data || []))
      .catch(() => setError('Could not load your colleagues.'))
      .finally(() => setLoading(false));
  }, [open, interview]);

  const shown = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return q ? options.filter((u) => `${u.name} ${u.email}`.toLowerCase().includes(q)) : options;
  }, [options, filter]);

  const toggle = (id) => setSelected((prev) => (
    prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
  ));

  const save = async () => {
    setSaving(true);
    setError('');
    try {
      const res = await updateInterview(interview.id, { interviewer_ids: selected });
      toast({ title: 'Interviewers updated' });
      onSaved?.(res?.data?.interviewers || []);
      onOpenChange(false);
    } catch (e) {
      // A 409 explains who is busy at the interview's time.
      setError(e?.message || 'Could not update the interviewers.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[95vw] max-w-md">
        <DialogHeader>
          <DialogTitle>Interviewers</DialogTitle>
          <DialogDescription>
            {interview ? `${interview.candidate_name} — colleagues interviewing with you.` : ''}
            {' '}The interview goes on their calendars.
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-lg border border-border bg-background">
          <div className="flex items-center gap-2 border-b border-border px-2">
            <Search className="h-3.5 w-3.5 text-muted-foreground" />
            <input
              type="text"
              value={filter}
              placeholder="Search colleagues"
              onChange={(e) => setFilter(e.target.value)}
              className="h-9 w-full bg-transparent text-sm text-foreground outline-none"
            />
          </div>
          <div className="max-h-64 overflow-y-auto p-1">
            {loading && (
              <p className="flex items-center gap-2 px-2 py-2 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading…
              </p>
            )}
            {!loading && options.length === 0 && !error && (
              <p className="px-2 py-2 text-xs text-muted-foreground">
                No colleagues with an employee account yet.
              </p>
            )}
            {!loading && shown.map((u) => (
              <label key={u.id} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-accent">
                <input type="checkbox" checked={selected.includes(u.id)} onChange={() => toggle(u.id)} />
                <span className="text-foreground">{u.name}</span>
                {u.email && <span className="truncate text-xs text-muted-foreground">{u.email}</span>}
              </label>
            ))}
          </div>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)} disabled={saving}>Cancel</Button>
          <Button size="sm" onClick={save} disabled={saving || loading}>
            {saving ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
