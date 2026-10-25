import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Check, FolderKanban, X } from 'lucide-react';

/**
 * Buttons under a Project Pilot reply, so a question gets answered with a click instead of a typed sentence.
 *
 *   choices   [{id, name}] — "Which project?": each sends the request again with that project
 *   onChoose  (choice) => void
 *   question  true when the reply asks the user something: Confirm / Reject (with an optional reason)
 *   onAnswer  (yes, reason) => void
 *   disabled  while a request is in flight
 */
export default function PilotQuickReplies({ choices = [], onChoose, question = false, onAnswer, disabled = false }) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState('');

  if (choices.length) {
    return (
      <div className="flex flex-wrap gap-2 pt-1" data-testid="pilot-choices">
        {choices.map((c) => (
          <Button key={c.id} size="sm" variant="outline" disabled={disabled} onClick={() => onChoose(c)}
                  className="h-8 text-xs max-w-full">
            <FolderKanban className="h-3.5 w-3.5 mr-1.5 shrink-0" /> <span className="truncate">{c.name}</span>
          </Button>
        ))}
      </div>
    );
  }
  if (!question) return null;
  return rejecting ? (
    <div className="space-y-2 pt-1" data-testid="pilot-question-reject">
      <textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Why not, or what should be different? (optional)"
        rows={2}
        className="w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm text-foreground"
      />
      <div className="flex gap-2">
        <Button size="sm" variant="destructive" disabled={disabled} onClick={() => onAnswer(false, reason.trim())}>
          Reject
        </Button>
        <Button size="sm" variant="ghost" disabled={disabled} onClick={() => setRejecting(false)}>Back</Button>
      </div>
    </div>
  ) : (
    <div className="flex gap-2 pt-1" data-testid="pilot-question">
      <Button size="sm" disabled={disabled} onClick={() => onAnswer(true)}>
        <Check className="h-3.5 w-3.5 mr-1" /> Confirm
      </Button>
      <Button size="sm" variant="outline" disabled={disabled} onClick={() => setRejecting(true)}>
        <X className="h-3.5 w-3.5 mr-1" /> Reject…
      </Button>
    </div>
  );
}
