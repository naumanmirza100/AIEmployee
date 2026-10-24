// "Prioritize with AI" for the Executive Meeting Assistant's Tasks.
//
// The AI suggests a priority (and a due date where a task has none) for each of the user's own open tasks, with its
// reason. Nothing is saved until the user ticks the suggestions they want and presses Apply: the server is asked
// with `apply: false` first, then only the ticked ones are sent to /tasks/ai/prioritize/apply.

import React, { useEffect, useState } from 'react';
import { Loader2, Sparkles, ArrowRight } from 'lucide-react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import execMeetingService from '@/services/execMeetingService';
import { priorityBadge } from './shared';

export const PrioritizeWithAIModal = ({ open, onClose, tasks = [], onApplied }) => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [ticked, setTicked] = useState({});

  const byId = Object.fromEntries(tasks.map((t) => [String(t.id), t]));

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setSuggestions([]);
    setTicked({});
    setLoading(true);
    execMeetingService.prioritizeTasks({ apply: false })
      .then((res) => {
        if (cancelled) return;
        const list = (res?.prioritized || []).filter((s) => s && s.id != null);
        setSuggestions(list);
        // Tick the ones that would change something.
        setTicked(Object.fromEntries(list.map((s) => {
          const task = byId[String(s.id)];
          const changes = !task || task.priority !== s.priority || (!task.due_date && s.suggested_due_date);
          return [String(s.id), !!changes];
        })));
      })
      .catch((err) => {
        if (cancelled) return;
        toast({ title: 'AI prioritising failed', description: err?.message || '', variant: 'destructive' });
        onClose();
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const chosen = suggestions.filter((s) => ticked[String(s.id)]);

  const apply = async () => {
    if (!chosen.length) return;
    setApplying(true);
    try {
      const res = await execMeetingService.applyPriorities(chosen.map((s) => ({
        id: s.id, priority: s.priority, ai_reasoning: s.ai_reasoning || '', suggested_due_date: s.suggested_due_date,
      })));
      toast({ title: `${res?.updated_count ?? chosen.length} task${chosen.length === 1 ? '' : 's'} updated` });
      onApplied?.();
      onClose();
    } catch (err) {
      toast({ title: 'Could not apply', description: err?.message || '', variant: 'destructive' });
    } finally {
      setApplying(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o && !applying) onClose(); }}>
      <DialogContent className="max-w-2xl" data-testid="EXEC-prioritize-ai-modal">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-violet-400" /> Prioritize with AI</DialogTitle>
          <DialogDescription>
            Suggested priorities for your own open tasks, with the reason. Tick the ones to apply; nothing changes until you do.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center gap-2 py-10 text-white/60">
            <Loader2 className="h-4 w-4 animate-spin" /> Reading your tasks…
          </div>
        ) : suggestions.length === 0 ? (
          <p className="py-8 text-center text-sm text-white/50">No open tasks of yours to prioritise.</p>
        ) : (
          <div className="max-h-[55vh] space-y-2 overflow-y-auto pr-1">
            {suggestions.map((s) => {
              const task = byId[String(s.id)];
              const key = String(s.id);
              return (
                <label key={key} className="flex cursor-pointer gap-3 rounded-lg border border-white/10 bg-white/[0.03] p-3 hover:bg-white/[0.06]">
                  <input
                    type="checkbox"
                    className="mt-1 h-4 w-4 accent-violet-500"
                    checked={!!ticked[key]}
                    onChange={(e) => setTicked((t) => ({ ...t, [key]: e.target.checked }))}
                    data-testid={`EXEC-prioritize-ai-tick-${key}`}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-white">{task?.title || s.title || `Task ${s.id}`}</span>
                      {task && priorityBadge(task.priority)}
                      <ArrowRight className="h-3.5 w-3.5 text-white/40" />
                      {priorityBadge(s.priority)}
                      {s.suggested_due_date && !task?.due_date && (
                        <span className="text-xs text-white/50">due {s.suggested_due_date}</span>
                      )}
                    </div>
                    {s.ai_reasoning && <p className="mt-1 text-xs text-white/60">{s.ai_reasoning}</p>}
                  </div>
                </label>
              );
            })}
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={applying}>Cancel</Button>
          <Button onClick={apply} disabled={loading || applying || !chosen.length} data-testid="EXEC-prioritize-ai-apply">
            {applying ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Apply {chosen.length || ''} selected
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default PrioritizeWithAIModal;
