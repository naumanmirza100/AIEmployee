import React from 'react';
import { Loader2, Sparkles } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { labelOf } from '@/utils/labels';

/*
 * What Frontline's AI suggests, for a person to accept. The AI used to act on
 * its own: close a ticket staff had just filed with a knowledge-base answer,
 * and change a ticket's category and priority on Re-triage.
 */

/** A new ticket stays open; the knowledge base's answer is offered here. */
export function TicketSuggestionDialog({ suggestion, busy, onResolve, onKeepOpen }) {
  return (
    <Dialog open={!!suggestion} onOpenChange={(open) => { if (!open && !busy) onKeepOpen(); }}>
      <DialogContent className="max-w-lg" data-testid="FL-ticket-suggestion-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-amber-400" /> The knowledge base has an answer
          </DialogTitle>
          <DialogDescription>
            Ticket #{suggestion?.ticketId} is created and open. Resolve it with this answer, or keep it open for a person
            to handle.
          </DialogDescription>
        </DialogHeader>
        <div className="max-h-64 overflow-y-auto whitespace-pre-wrap rounded-md border border-white/10 bg-white/[0.03] p-3 text-sm">
          {suggestion?.text}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onKeepOpen} disabled={busy}>Keep it open</Button>
          <Button onClick={onResolve} disabled={busy}>
            {busy && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            Resolve with this answer
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Re-triage's suggestion, applied only when confirmed. */
export function RetriageReviewDialog({ proposal, busy, onApply, onCancel }) {
  const d = proposal?.data || {};
  const rows = [
    ['Category', d.old_category, d.new_category],
    ['Priority', d.old_priority, d.new_priority],
  ];
  const changed = rows.some(([, before, after]) => before !== after);
  return (
    <Dialog open={!!proposal} onOpenChange={(open) => { if (!open && !busy) onCancel(); }}>
      <DialogContent className="max-w-md" data-testid="FL-retriage-review-dialog">
        <DialogHeader>
          <DialogTitle>Re-triage #{proposal?.ticket?.id}</DialogTitle>
          <DialogDescription>
            {changed ? 'The AI suggests these changes. Nothing changes until you apply them.'
              : 'The AI suggests keeping the category and priority as they are.'}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5 text-sm">
          {rows.map(([name, before, after]) => (
            <div key={name} className="flex items-center justify-between gap-3 rounded-md border border-white/10 px-3 py-2">
              <span className="text-muted-foreground">{name}</span>
              <span>
                {before === after ? labelOf(before) : (
                  <>
                    <span className="text-muted-foreground line-through">{labelOf(before)}</span>
                    {' → '}
                    <span className="font-medium">{labelOf(after)}</span>
                  </>
                )}
              </span>
            </div>
          ))}
          {d.intent && <p className="text-xs text-muted-foreground">Read as: {labelOf(d.intent)}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel} disabled={busy}>{changed ? 'Cancel' : 'Close'}</Button>
          {changed && (
            <Button onClick={onApply} disabled={busy}>
              {busy && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
              Apply changes
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
