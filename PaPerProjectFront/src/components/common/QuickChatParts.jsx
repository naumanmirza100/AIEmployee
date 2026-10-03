import React from 'react';
import { MessageCircle, Trash2 } from 'lucide-react';

/*
 * Pieces of the floating Quick Chat that PM, HR and Frontline each had a copy
 * of, the same but for their colour. (Its window is in
 * frontline/chatShellUtils, its history in hooks/useQuickChatHistory.)
 */

// Whole class names, so Tailwind keeps them.
const ACCENTS = {
  cyan: { selected: 'bg-cyan-500/10 border border-cyan-400/30', active: 'bg-cyan-500/10', icon: 'text-cyan-300' },
  violet: { selected: 'bg-violet-500/10 border border-violet-400/30', active: 'bg-violet-500/10', icon: 'text-violet-300' },
  amber: { selected: 'bg-amber-400/10 border border-amber-400/30', active: 'bg-amber-400/10', icon: 'text-amber-300' },
};

/** '5m ago' for a timestamp in milliseconds. */
export function relativeTime(ts) {
  if (!ts) return '';
  const diff = (Date.now() - ts) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

/** The saved conversations: open one, or delete it. */
export function QuickChatHistoryList({ history, currentId, onOpen, onRemove, heading = 'Recent conversations', accent = 'violet' }) {
  const colours = ACCENTS[accent] || ACCENTS.violet;
  return (
    <div className="flex-1 overflow-y-auto p-3 space-y-1.5" style={{ background: 'var(--panel-3)' }}>
      <div className="flex items-center justify-between mb-2">
        <p className="text-[10px] uppercase tracking-wider text-white/40 font-semibold">{heading}</p>
        <span className="text-[10px] text-white/40">{history.length} saved</span>
      </div>
      {history.length === 0 ? (
        <p className="text-sm text-white/50 text-center py-8">No saved conversations yet.</p>
      ) : history.map((h) => (
        <div key={h.id}
          className={`group flex items-center gap-2 px-2 py-2 rounded-lg cursor-pointer transition
            ${h.id === currentId ? colours.selected : 'hover:bg-white/[0.04] border border-transparent'}`}
          onClick={() => onOpen(h)}
        >
          <MessageCircle className="h-3.5 w-3.5 shrink-0 text-white/40" />
          <div className="flex-1 min-w-0">
            <div className="text-sm text-white/85 truncate">{h.title}</div>
            <div className="text-[10px] text-white/40">
              {relativeTime(h.updated_at)} · {(h.messages || []).length} messages
            </div>
          </div>
          <button type="button" onClick={(e) => { e.stopPropagation(); onRemove(h.id); }}
            title="Delete this conversation" aria-label="Delete this conversation"
            className="opacity-0 group-hover:opacity-100 p-1 rounded text-white/40 hover:text-rose-400 hover:bg-white/[0.06] transition">
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}

/** The "/" command list above the input. */
export function SlashCommandMenu({ commands, active, onPick, onHover, accent = 'violet',
  panelClassName = 'border-[var(--line-2)] bg-[var(--panel-4)]' }) {
  const colours = ACCENTS[accent] || ACCENTS.violet;
  return (
    <div className={`absolute bottom-full left-2 right-2 mb-2 rounded-lg border shadow-2xl overflow-hidden ${panelClassName}`}>
      <div className="px-3 py-1.5 border-b border-white/10 text-[10px] uppercase tracking-wider text-white/40 font-semibold">
        Commands · ↑↓ Tab/Enter to insert
      </div>
      <div className="max-h-48 overflow-y-auto">
        {commands.map((c, i) => {
          const Icon = c.icon;
          return (
            <button key={c.key} type="button" onMouseDown={(e) => { e.preventDefault(); onPick(c); }}
              onMouseEnter={() => onHover(i)}
              className={`w-full flex items-start gap-2 px-3 py-2 text-left transition
                ${i === active ? colours.active : 'hover:bg-white/[0.03]'}`}>
              <Icon className={`h-4 w-4 shrink-0 mt-0.5 ${colours.icon}`} />
              <div className="min-w-0">
                <div className="text-xs font-semibold text-white">
                  {c.label}
                  <span className="text-white/40 font-normal ml-1">{c.hint}</span>
                </div>
                <div className="text-[11px] text-white/60 mt-0.5">{c.description}</div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
