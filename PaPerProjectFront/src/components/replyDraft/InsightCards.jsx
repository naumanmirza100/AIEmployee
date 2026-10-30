import React, { useEffect, useState } from 'react';
import { Loader2, ListChecks, Sparkles } from 'lucide-react';
import { CATEGORY_LABELS, PRIORITY_STYLES } from './replyDraftConstants';
import { getReplyDraftDashboard, summarizeConversation } from '@/services/replyDraftService';

// What the AI made of an email as it arrived (category, priority, one sentence), and the summary of its whole
// conversation on request. The AI read a mail only when someone asked for a draft (30 Oct 2026).
export const TriageCard = ({ email }) => {
  const [summary, setSummary] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  // A stored summary is shown at once while it still covers every message of the conversation.
  useEffect(() => {
    setError('');
    const stored = email?.thread_summary;
    const fresh = stored && (email.thread_summary_count || 0) >= (email.thread_count || 1);
    setSummary(fresh ? stored : null);
  }, [email?.id, email?.thread_summary, email?.thread_summary_count, email?.thread_count]);

  if (!email || email.direction === 'out') return null;
  const priority = email.priority ? PRIORITY_STYLES[email.priority] : null;

  const summarize = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await summarizeConversation(email.id);
      setSummary(res?.data || null);
    } catch (e) {
      setError(e?.message || 'The summary could not be made just now. Try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="rd-triage-card" className="mb-4 p-3 rounded-lg bg-cyan-500/5 border border-cyan-500/20">
      <div className="flex items-start gap-2.5">
        <Sparkles className="h-4 w-4 text-cyan-300 shrink-0 mt-0.5" />
        <div className="min-w-0 flex-1">
          {email.triaged ? (
            <>
              <div className="flex items-center gap-1.5 flex-wrap mb-1">
                {priority && (
                  <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${priority.className}`}>
                    {priority.label}
                  </span>
                )}
                {email.category && (
                  <span className="text-[10px] font-medium text-cyan-200 px-2 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-500/20">
                    {CATEGORY_LABELS[email.category] || email.category}
                  </span>
                )}
                {email.needs_reply && (
                  <span className="text-[10px] font-medium text-fuchsia-200 px-2 py-0.5 rounded-full bg-fuchsia-500/10 border border-fuchsia-500/20">
                    Waiting for an answer
                  </span>
                )}
              </div>
              <div data-testid="rd-ai-summary" className="text-sm text-gray-200 leading-relaxed">{email.ai_summary}</div>
            </>
          ) : (
            <div className="text-xs text-gray-400">The AI reads each new email within a few minutes of its arrival.</div>
          )}
          {email.reply_to && (
            <div className="text-[11px] text-gray-400 mt-1.5">
              Answers go to <span className="text-gray-200">{email.reply_to}</span>, the address the sender asked for
              (Reply-To), not {email.from_email}.
            </div>
          )}
        </div>
        {!summary && (
          <button
            type="button"
            data-testid="rd-summarize-conversation"
            onClick={summarize}
            disabled={busy}
            className="shrink-0 inline-flex items-center gap-1.5 text-xs font-medium text-cyan-200 px-2.5 py-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/30 hover:bg-cyan-500/20 disabled:opacity-60"
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ListChecks className="h-3.5 w-3.5" />}
            {(email.thread_count || 1) > 1 ? `Summarise the conversation (${email.thread_count})` : 'Summarise'}
          </button>
        )}
      </div>
      {error && <div className="mt-2 text-xs text-red-300">{error}</div>}
      {summary && <ConversationSummary summary={summary} />}
    </div>
  );
};

export const ConversationSummary = ({ summary }) => (
  <div data-testid="rd-conversation-summary" className="mt-3 pt-3 border-t border-cyan-500/20 text-xs text-gray-300 space-y-2">
    <div className="font-semibold text-cyan-200">
      {summary.messages > 1 ? `The conversation, ${summary.messages} messages` : 'The email in short'}
    </div>
    <ul className="list-disc pl-4 space-y-1">
      {(summary.points || []).map((p, i) => <li key={i}>{p}</li>)}
    </ul>
    {summary.next_step && (
      <div><span className="font-semibold text-gray-200">Next: </span>{summary.next_step}</div>
    )}
    {(summary.open_questions || []).length > 0 && (
      <div>
        <span className="font-semibold text-gray-200">Not answered yet: </span>
        {summary.open_questions.join(' · ')}
      </div>
    )}
  </div>
);

// The dashboard's "Needs you" card: urgent mail and mail waiting for an answer this week, from the AI's triage.
export const NeedsYouCard = ({ onOpen }) => {
  const [data, setData] = useState(null);
  useEffect(() => {
    let alive = true;
    getReplyDraftDashboard()
      .then((res) => { if (alive) setData(res?.data?.needs_you || null); })
      .catch(() => {});
    return () => { alive = false; };
  }, []);
  if (!data) return null;
  const figures = [
    { label: 'Urgent', value: data.urgent, tint: 'text-red-300' },
    { label: 'Waiting for an answer', value: data.waiting_for_answer, tint: 'text-fuchsia-300' },
    { label: 'Not read by the AI yet', value: data.not_read_yet, tint: 'text-gray-300' },
  ];
  return (
    <div data-testid="rd-needs-you" className="mb-6 rounded-xl bg-white/5 border border-white/10 p-4">
      <div className="flex items-center gap-2 mb-3">
        <Sparkles className="h-4 w-4 text-cyan-300" />
        <div className="text-sm font-semibold text-white">Needs you this week</div>
        <div className="text-[11px] text-gray-500">The AI reads each new email as it arrives.</div>
      </div>
      <div className="grid grid-cols-3 gap-3 mb-3">
        {figures.map((f) => (
          <div key={f.label} className="rounded-lg bg-black/20 border border-white/5 px-3 py-2">
            <div className={`text-xl font-bold ${f.tint}`}>{f.value}</div>
            <div className="text-[11px] text-gray-400">{f.label}</div>
          </div>
        ))}
      </div>
      {(data.top || []).length > 0 && (
        <div className="space-y-1">
          {data.top.map((m) => {
            const p = PRIORITY_STYLES[m.priority];
            return (
              <button key={m.id} type="button" onClick={() => onOpen(m.id)}
                className="w-full text-left flex items-start gap-2 px-2 py-1.5 rounded-lg hover:bg-white/5">
                <span className={`mt-1.5 h-2 w-2 rounded-full shrink-0 ${p ? p.dot : 'bg-gray-500'}`} />
                <span className="min-w-0 text-xs text-gray-300">
                  <span className="font-semibold text-gray-100">{m.from_name || m.from_email}</span>
                  {' · '}{m.ai_summary || m.subject}
                </span>
              </button>
            );
          })}
        </div>
      )}
      {Object.keys(data.by_category || {}).length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-3">
          {Object.entries(data.by_category).sort((a, b) => b[1] - a[1]).map(([c, n]) => (
            <span key={c} className="text-[10px] text-cyan-200 px-2 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-500/20">
              {CATEGORY_LABELS[c] || c}: {n}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};
