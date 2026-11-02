import React, { useRef, useState } from 'react';
import { Loader2, Mail, MessageSquare, Send } from 'lucide-react';
import { askInbox } from '@/services/replyDraftService';
import { formatRelative } from './replyDraftHelpers';

// Questions about the inbox, in any language, answered from its emails with the emails named. There was no way to
// ask anything about the inbox (the AI Employee list's Knowledge Q&A, 30 Oct 2026).
const EXAMPLES = [
  'What came in today that needs an answer?',
  'Which customers complained this week?',
  'Kis ne invoice ke baare mein likha hai?',
];

const AskInbox = ({ hasMailbox, onOpenEmail }) => {
  const [turns, setTurns] = useState([]);
  const [question, setQuestion] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const endRef = useRef(null);

  const ask = async (text) => {
    const q = (text ?? question).trim();
    if (q.length < 3 || busy) return;
    setBusy(true);
    setError('');
    try {
      const history = turns.slice(-3).map((t) => ({ question: t.question, answer: t.answer }));
      const res = await askInbox(q, history);
      setTurns((prev) => [...prev, { question: q, ...(res?.data || {}) }]);
      setQuestion('');
      setTimeout(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
    } catch (e) {
      setError(e?.message || 'The answer could not be made just now. Try again.');
    } finally {
      setBusy(false);
    }
  };

  if (!hasMailbox) {
    return (
      <div className="rounded-xl bg-white/5 border border-white/10 p-6 text-sm text-gray-300">
        Connect the inbox on the Dashboard first; then ask anything about its mail.
      </div>
    );
  }

  return (
    <div className="rounded-xl bg-white/5 border border-white/10 flex flex-col min-h-[60vh]">
      <div className="flex-1 p-4 space-y-5 overflow-y-auto custom-scrollbar">
        {turns.length === 0 && (
          <div className="text-sm text-gray-400 space-y-3">
            <div>Ask anything about the mail in this inbox, in English or Roman Urdu. Each answer names the emails it
              came from.</div>
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((ex) => (
                <button key={ex} type="button" onClick={() => ask(ex)} disabled={busy}
                  className="text-xs text-cyan-200 px-3 py-1.5 rounded-full bg-cyan-500/10 border border-cyan-500/20 hover:bg-cyan-500/20">
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map((t, i) => (
          <div key={i} className="space-y-2">
            <div className="flex justify-end">
              <div className="max-w-[80%] text-sm text-white bg-fuchsia-500/20 border border-fuchsia-500/30 rounded-xl px-3 py-2">
                {t.question}
              </div>
            </div>
            <div data-testid="rd-ask-answer" className="max-w-[90%] text-sm text-gray-200 bg-black/20 border border-white/10 rounded-xl px-3 py-2 whitespace-pre-wrap">
              {t.answer}
            </div>
            {(t.sources || []).length > 0 && (
              <div className="flex flex-wrap gap-2 pl-1">
                {t.sources.map((s) => (
                  <button key={s.id} type="button" data-testid="rd-ask-source" onClick={() => onOpenEmail(s.id)}
                    className="inline-flex items-center gap-1.5 text-[11px] text-gray-300 px-2.5 py-1 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 max-w-[320px]">
                    <Mail className="h-3 w-3 shrink-0 text-cyan-300" />
                    <span className="text-cyan-200 shrink-0">#{s.id}</span>
                    <span className="truncate">
                      {s.direction === 'out' ? `To ${s.to_email}` : (s.from_name || s.from_email)} · {s.subject}
                    </span>
                    <span className="text-gray-500 shrink-0">{formatRelative(s.received_at)}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        <div ref={endRef} />
      </div>
      {error && <div className="px-4 pb-2 text-xs text-red-300">{error}</div>}
      <form
        className="border-t border-white/10 p-3 flex gap-2"
        onSubmit={(e) => { e.preventDefault(); ask(); }}
      >
        <div className="relative flex-1">
          <MessageSquare className="h-4 w-4 text-gray-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            data-testid="rd-ask-input"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            maxLength={500}
            placeholder="Ask about your email…"
            className="w-full bg-white/5 border border-white/10 rounded-lg pl-9 pr-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500/50"
          />
        </div>
        <button type="submit" data-testid="rd-ask-send" disabled={busy || question.trim().length < 3}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium text-pure-white bg-gradient-to-r from-fuchsia-500 to-purple-600 disabled:opacity-50">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          Ask
        </button>
      </form>
    </div>
  );
};

export default AskInbox;
