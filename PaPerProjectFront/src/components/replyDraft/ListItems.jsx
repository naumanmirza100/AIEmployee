import React from 'react';
import { Quote, Zap } from 'lucide-react';
import { Avatar } from './SharedUI';
import { INTEREST_STYLES, STATUS_STYLES } from './replyDraftConstants';
import { formatRelative } from './replyDraftHelpers';

export const InboxItem = ({ reply, active, onClick }) => {
  const style = INTEREST_STYLES[reply.interest_level] || INTEREST_STYLES.not_analyzed;
  // Outgoing rows live in the Sent tab. Show the recipient instead of
  // ourselves — `from_email` for sent mail is the account's own address
  // and would render every row identically otherwise.
  const isOutgoing = reply.direction === 'out';
  const personName = isOutgoing
    ? (reply.to_email || 'Unknown recipient')
    : (reply.from_name || reply.from_email || 'Unknown');
  const personEmail = isOutgoing ? reply.to_email : reply.from_email;
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-3 border-b border-white/5 flex gap-3 transition-all ${active ? 'bg-gradient-to-r from-cyan-500/10 to-transparent border-l-2 border-l-cyan-400' : 'hover:bg-white/5 border-l-2 border-l-transparent'
        }`}
    >
      <Avatar name={personName} email={personEmail} size="md" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2 mb-0.5">
          <span className={`text-sm font-semibold truncate ${active ? 'text-white' : 'text-gray-100'}`}>
            {isOutgoing ? `To: ${personName}` : personName}
          </span>
          <span className="text-[10px] text-gray-500 shrink-0">{formatRelative(reply.replied_at)}</span>
        </div>
        <div className="text-xs text-gray-300 truncate font-medium mb-1">
          {reply.subject || '(no subject)'}
        </div>
        {reply.preview ? (
          <div className="text-xs text-gray-500 line-clamp-2 leading-snug mb-1.5">
            {reply.preview}
          </div>
        ) : null}
        <div className="flex items-center gap-1.5 flex-wrap">
          {!isOutgoing && (
            <span className={`inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full border ${style.className}`}>
              {style.label}
            </span>
          )}
          {/* Thread depth badge — only shows when the row is part of a
              multi-message conversation. Helps the user spot ongoing
              threads in the list without expanding them. */}
          {reply.thread_count > 1 && (
            <span
              title={`${reply.thread_count} messages in this thread`}
              className="inline-flex items-center gap-1 text-[10px] font-medium text-fuchsia-200 px-2 py-0.5 rounded-full bg-fuchsia-500/10 border border-fuchsia-500/20"
            >
              <Quote className="h-2.5 w-2.5" />
              {reply.thread_count}
            </span>
          )}
          {!isOutgoing && reply.campaign && (
            <span className="inline-flex items-center gap-1 text-[10px] text-gray-400 px-2 py-0.5 rounded-full bg-white/5 border border-white/10 truncate max-w-[120px]">
              <Zap className="h-2.5 w-2.5" />
              {reply.campaign}
            </span>
          )}
        </div>
      </div>
    </button>
  );
};

export const DraftItem = ({ draft, active, onClick }) => {
  const style = STATUS_STYLES[draft.status] || STATUS_STYLES.pending;
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-3 border-b border-white/5 flex gap-3 transition-all ${active ? 'bg-gradient-to-r from-fuchsia-500/10 to-transparent border-l-2 border-l-fuchsia-400' : 'hover:bg-white/5 border-l-2 border-l-transparent'
        }`}
    >
      <Avatar name={draft.to_name} email={draft.to_email} size="md" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2 mb-0.5">
          <span className="text-sm font-semibold truncate text-gray-100">
            To: {draft.to_name || draft.to_email || 'Unknown'}
          </span>
          <span className="text-[10px] text-gray-500 shrink-0">{formatRelative(draft.created_at)}</span>
        </div>
        <div className="text-xs text-gray-300 truncate font-medium mb-1">
          {draft.subject || '(no subject)'}
        </div>
        <div className="text-xs text-gray-500 line-clamp-2 leading-snug mb-1.5">
          {(draft.body || '').slice(0, 120) || 'Empty draft'}
        </div>
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className={`inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full border ${style.className}`}>
            {style.label}
          </span>
          <span className="inline-flex items-center text-[10px] text-gray-400 px-2 py-0.5 rounded-full bg-white/5 border border-white/10 capitalize">
            {draft.tone}
          </span>
        </div>
      </div>
    </button>
  );
};
