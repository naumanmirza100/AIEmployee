// "Create with AI" modal for the Executive Meeting Assistant.
//
// The user writes (or edits a pre-filled default) prompt describing the
// meeting or task they want. On "Generate", the backend parses it into
// structured fields — title, time, duration/priority, due date — and resolves
// any people named in the prompt to real company members. Those fields are
// handed back to the parent (via onParsed), which opens the normal Schedule-
// Meeting / Add-Task dialog PRE-FILLED so the user can review, tweak the
// participants (add more via the dialog's own "View all members"), and save.
//
// One component serves both flows via `mode` ('meeting' | 'task').

import React, { useState, useEffect } from 'react';
import { Sparkles, Loader2, Wand2, Users, ChevronRight } from 'lucide-react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/components/ui/use-toast';
import execMeetingService from '@/services/execMeetingService';
import { AllMembersPanel } from './AllMembersPanel';

// Editable starter prompts — shown pre-filled so the user has a template to
// tweak instead of a blank box. Kept intentionally concrete so the AI has
// something to parse even if the user only edits a few words.
const DEFAULT_MEETING_PROMPT =
  'Schedule a 45-minute meeting titled "Q3 Strategy Review" tomorrow at 3:00 PM with the product team. Cover roadmap priorities and budget.';
const DEFAULT_TASK_PROMPT =
  'Create a high-priority task "Review the Q3 report" due this Friday, assigned to the finance lead.';

// `initialPrompt` lets the parent reopen this modal with the user's previous
// prompt (from the dialog's "Edit AI prompt" button) instead of the default,
// so they can tweak and regenerate.
export const CreateWithAIModal = ({ open, onClose, mode = 'meeting', onParsed, initialPrompt = '' }) => {
  const { toast } = useToast();
  const isTask = mode === 'task';
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);

  // Members the user hand-picks (via @-mention in the prompt or the View-all
  // panel). Merged with anyone the AI resolves from the prompt on Generate.
  const [members, setMembers] = useState([]);
  const [showAllMembers, setShowAllMembers] = useState(false);
  const mKey = (u) => `${u?.user_type || 'company_user'}-${u?.id}`;
  const textareaRef = React.useRef(null);

  // @-mention autocomplete inside the prompt textarea. We load the whole
  // company roster once when the modal opens and filter it client-side, so
  // suggestions appear on the very first letter (the server-side search has a
  // 2-char minimum, which is why one letter used to show nothing). `mention`
  // holds the active "@query" + where it starts.
  const [allMembers, setAllMembers] = useState([]);
  const [mention, setMention] = useState(null); // { query, start } | null

  const removeMember = (u) => setMembers((prev) => prev.filter((m) => mKey(m) !== mKey(u)));
  const toggleMember = (u) =>
    setMembers((prev) => (prev.some((m) => mKey(m) === mKey(u)) ? prev.filter((m) => mKey(m) !== mKey(u)) : [...prev, u]));

  // Detect an active "@query" immediately before the caret. Returns
  // { query, start } or null. The query stops at whitespace, so "@las" in
  // "…member @las" is detected but "@las done" (after a space) is not.
  const detectMention = (value, caret) => {
    const upto = value.slice(0, caret);
    const at = upto.lastIndexOf('@');
    if (at === -1) return null;
    const between = upto.slice(at + 1);
    if (/\s/.test(between)) return null; // space after @ ends the mention
    return { query: between, start: at };
  };

  const onPromptChange = (e) => {
    const value = e.target.value;
    setPrompt(value);
    const caret = e.target.selectionStart ?? value.length;
    setMention(detectMention(value, caret));
  };

  // Matches for the active @-mention, filtered client-side from the loaded
  // roster. Shows results from the FIRST letter; when the query is empty
  // (just "@") we show everyone so the user can browse. Already-added members
  // are excluded.
  const mentionResults = React.useMemo(() => {
    if (!mention) return [];
    const q = mention.query.trim().toLowerCase();
    const have = new Set(members.map(mKey));
    return allMembers
      .filter((u) => !have.has(mKey(u)))
      .filter((u) => !q
        || (u.full_name || '').toLowerCase().includes(q)
        || (u.email || '').toLowerCase().includes(q));
  }, [mention, allMembers, members]);

  // Replace the active "@query" with the picked member's name and add them.
  const pickMention = (u) => {
    setMembers((prev) => (prev.some((m) => mKey(m) === mKey(u)) ? prev : [...prev, u]));
    if (mention) {
      const before = prompt.slice(0, mention.start);
      const after = prompt.slice(mention.start + 1 + mention.query.length);
      // Insert the name (no @) followed by a space so typing continues cleanly.
      const inserted = `${u.full_name} `;
      setPrompt(`${before}${inserted}${after}`);
    }
    setMention(null);
    // Return focus to the textarea after the click.
    requestAnimationFrame(() => textareaRef.current?.focus());
  };

  // On open: restore the previous prompt if we were given one (re-edit flow),
  // otherwise seed the mode's editable default (fresh flow). Also clear the
  // hand-picked members + mention state each time it opens.
  useEffect(() => {
    if (open) {
      setPrompt(initialPrompt || (isTask ? DEFAULT_TASK_PROMPT : DEFAULT_MEETING_PROMPT));
      setMembers([]);
      setMention(null); setShowAllMembers(false);
    }
  }, [open, isTask, initialPrompt]);

  // Load the full company roster once each time the modal opens — powers the
  // client-side @-mention filter (instant, first-letter matches).
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    execMeetingService.listAllUsers()
      .then((res) => { if (!cancelled) setAllMembers(Array.isArray(res?.users) ? res.users : []); })
      .catch(() => { if (!cancelled) setAllMembers([]); });
    return () => { cancelled = true; };
  }, [open]);

  const handleGenerate = async () => {
    const text = prompt.trim();
    if (!text) {
      toast({ title: 'Write a prompt first', description: 'Describe the ' + (isTask ? 'task' : 'meeting') + ' you want.', variant: 'destructive' });
      return;
    }
    setLoading(true);
    try {
      const res = isTask
        ? await execMeetingService.aiParseTask(text)
        : await execMeetingService.aiParseMeeting(text);
      const data = res?.data || {};

      // Merge the members the user hand-picked here with the ones the AI
      // resolved from names in the prompt (dedupe by key). Hand-picked come
      // first so the user's explicit choices are visible at the top.
      const aiPeople = isTask ? (data.assignees || []) : (data.participants || []);
      const seen = new Set(members.map(mKey));
      const merged = [...members];
      for (const p of aiPeople) {
        if (!seen.has(mKey(p))) { seen.add(mKey(p)); merged.push(p); }
      }
      const finalData = isTask
        ? { ...data, assignees: merged }
        : { ...data, participants: merged };

      toast({
        title: 'Draft ready',
        description: 'Review the details and members, then save.',
      });
      // Hand the parsed fields to the parent, which opens the normal dialog
      // pre-filled. We also return the prompt so the parent can offer an
      // "Edit AI prompt" button that reopens this modal to regenerate.
      onParsed?.(finalData, text);
    } catch (err) {
      toast({
        title: 'Could not generate',
        description: err?.message || 'The AI could not parse that prompt. Try rephrasing.',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      {/* Widen + lay out side-by-side when the View-all panel is open. */}
      <DialogContent className={`bg-[#0d0b1f] border-white/10 text-white transition-[max-width] ${showAllMembers ? 'max-w-4xl' : 'max-w-xl'}`}>
        <div className="flex gap-4 items-stretch">
          <div className="min-w-0 flex-1">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Wand2 className="h-5 w-5 text-violet-300" />
                Create {isTask ? 'task' : 'meeting'} with AI
              </DialogTitle>
              <DialogDescription className="text-white/50">
                Describe it in plain language — include the {isTask ? 'title, due date, priority, and who to assign' : 'title, time, duration, and who to invite'}.
                Type <span className="text-violet-300">@name</span> to add people, or use “View all members”.
              </DialogDescription>
            </DialogHeader>

            <div className="py-2 space-y-2">
              {/* View all members — above the prompt, opens the side panel */}
              <div className="flex items-center justify-end">
                <button
                  type="button"
                  onClick={() => setShowAllMembers((v) => !v)}
                  className="flex items-center gap-1 text-[11px] text-violet-300 hover:text-violet-200"
                >
                  <Users className="h-3 w-3" />
                  View all members
                  <ChevronRight className={`h-3 w-3 transition-transform ${showAllMembers ? 'rotate-90' : ''}`} />
                </button>
              </div>

              {/* Prompt textarea with @-mention autocomplete */}
              <div className="relative">
                <Textarea
                  ref={textareaRef}
                  value={prompt}
                  onChange={onPromptChange}
                  rows={5}
                  placeholder={isTask
                    ? 'e.g. High-priority task "Review Q3 report" due Friday, assign @noor'
                    : 'e.g. 30-min "Launch sync" next Monday 11am with @noor and @ali'}
                  className="bg-white/5 border-white/10 text-white text-sm leading-relaxed"
                  disabled={loading}
                />
                {/* @-mention dropdown — filtered client-side, shows from the
                    first letter (and everyone on a bare "@"). */}
                {mention && mentionResults.length > 0 && (
                  // ~4 rows tall (each row ≈ 50px); more than 4 matches scroll.
                  <div className="absolute left-2 right-2 top-full -mt-1 z-50 rounded-xl border border-white/10 bg-[#1a1333] shadow-xl max-h-[200px] overflow-y-auto custom-scrollbar">
                    {mentionResults.map((u) => (
                      <button key={mKey(u)} type="button" onClick={() => pickMention(u)}
                        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-violet-500/20 transition-colors text-left">
                        <div className="h-7 w-7 rounded-full bg-violet-500/30 flex items-center justify-center text-violet-200 text-xs font-bold flex-shrink-0">
                          {u.full_name?.[0]?.toUpperCase() || '?'}
                        </div>
                        <div className="min-w-0">
                          <p className="text-white text-xs font-medium truncate">{u.full_name}</p>
                          <p className="text-white/40 text-[10px] truncate">{u.email}{u.role ? ` · ${u.role}` : ''}</p>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <p className="text-[11px] text-white/35">
                Tip: type <span className="text-violet-300">@</span> to add a person (e.g. “@noor”). They'll be invited when you generate.
              </p>

              {/* Selected member chips */}
              {members.length > 0 && (
                <div className="flex flex-wrap gap-1.5 pt-0.5">
                  {members.map((m) => (
                    <span key={mKey(m)} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-violet-500/20 border border-violet-500/30 text-violet-200 text-xs">
                      {m.full_name}
                      <button type="button" onClick={() => removeMember(m)} className="text-violet-300/60 hover:text-white leading-none">✕</button>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Side panel — all company members, vertical list, attached right */}
          <AllMembersPanel
            open={showAllMembers}
            onClose={() => setShowAllMembers(false)}
            selected={members}
            onToggle={toggleMember}
          />
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={onClose} disabled={loading} className="border-white/10 text-white/70">
            Cancel
          </Button>
          <Button
            onClick={handleGenerate}
            disabled={loading || !prompt.trim()}
            className="bg-gradient-to-r from-violet-500 to-fuchsia-600 hover:from-violet-400 hover:to-fuchsia-500 text-white font-semibold"
          >
            {loading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Sparkles className="h-4 w-4 mr-2" />}
            {loading ? 'Generating…' : 'Generate draft'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default CreateWithAIModal;
