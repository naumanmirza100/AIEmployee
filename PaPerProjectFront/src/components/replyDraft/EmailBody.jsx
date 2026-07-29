import React, { useState } from 'react';
import { Loader2, CornerUpLeft, Quote, ChevronDown } from 'lucide-react';
import { HtmlBody } from './HtmlBody';
import { parseReplyBody, cleanQuoted } from './replyDraftHelpers';

export const EmailBody = ({ body, bodyHtml, direction = 'in' }) => {
  // Header label semantics:
  //   - "Their reply" / "Your reply" — only when the body genuinely looks
  //     like a reply (plain-text quote-folding finds a quoted thread).
  //     Marketing emails, fresh incoming mail, and HTML mail without a
  //     visible quoted section are NOT replies, so we used to mislabel
  //     every opened email as "Their reply" — fixed below.
  //   - "Their message" / "Your message" — for everything else, picked by
  //     direction so an outbound (Sent-tab) row never says "Their".
  const isOutgoing = direction === 'out';
  const messageLabel = isOutgoing ? 'Your message' : 'Their message';
  const replyLabelForQuote = isOutgoing ? 'Your reply' : 'Their reply';
  const [showQuoted, setShowQuoted] = useState(false);
  // `body === undefined` means the list endpoint returned just a preview and
  // the detail fetch is still in flight. Show a gentle loading state instead
  // of "No content" to avoid misleading the user.
  if (body === undefined && bodyHtml === undefined) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-500 italic">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading message…
      </div>
    );
  }

  // HTML path — when the source had a text/html part, render it for
  // visual fidelity. Quote-folding only applies to plain text (parseReplyBody
  // is regex-based and would mangle markup), so HTML mail is shown whole.
  if (bodyHtml && bodyHtml.trim()) {
    return (
      <div>
        <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-cyan-300 mb-1">
          <CornerUpLeft className="h-3 w-3" />
          {messageLabel}
        </div>
        <HtmlBody html={bodyHtml} />
      </div>
    );
  }

  if (!body || !body.trim()) {
    return <div className="text-sm text-gray-500 italic">No content.</div>;
  }
  const { reply, quoted } = parseReplyBody(body);

  // Nothing was detected as a quote — render the whole body as the message.
  if (!quoted) {
    return (
      <div>
        <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-cyan-300 mb-1">
          <CornerUpLeft className="h-3 w-3" />
          {messageLabel}
        </div>
        <div className="text-sm text-gray-100 whitespace-pre-wrap leading-relaxed">
          {reply}
        </div>
      </div>
    );
  }

  const cleanedQuote = cleanQuoted(quoted);

  return (
    <div className="space-y-3">
      {reply && (
        <div>
          <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-cyan-300 mb-2">
            <CornerUpLeft className="h-3 w-3" />
            {replyLabelForQuote}
          </div>
          <div className="text-sm text-gray-100 whitespace-pre-wrap leading-relaxed bg-cyan-500/5 border border-cyan-500/15 rounded-lg p-3">
            {reply}
          </div>
        </div>
      )}
      <div>
        <button
          type="button"
          onClick={() => setShowQuoted((v) => !v)}
          className="w-full flex items-center justify-between gap-2 text-left px-3 py-2 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 transition"
        >
          <span className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-gray-400">
            <Quote className="h-3 w-3" />
            Original email (quoted)
          </span>
          <ChevronDown className={`h-4 w-4 text-gray-400 transition-transform ${showQuoted ? 'rotate-180' : ''}`} />
        </button>
        {showQuoted && (
          <div className="mt-2 pl-4 border-l-2 border-white/15 text-sm text-gray-400 whitespace-pre-wrap leading-relaxed">
            {cleanedQuote}
          </div>
        )}
      </div>
    </div>
  );
};
