import React, { useMemo, useState } from 'react';
import { ChevronsLeft, ChevronsRight, Loader2, MessageCircle, Plus, Search, Trash2, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { sidePanelStartsOpen } from '@/utils/sidePanel';

/**
 * A chat page laid out like the PM agent's Knowledge Q&A and Project Pilot (14 Nov 2026): the chats on the left
 * (search, a new chat, each with its title, a detail line and a delete), the conversation on the right under a header,
 * and the composer fixed at the bottom. Used by the AI Data Analyst and the Company Assistant.
 *
 * Phones: the list starts closed and opens over the conversation instead of squeezing it.
 *
 * Props:
 *   icon, title, badge, description    the header
 *   chats       [{ id, title, detail, updatedAt }], newest first
 *   selectedId  the open chat, or null for a new one
 *   onSelect(chat), onNew(), onDelete(chat)
 *   loadingChats, emptyChatsText, testId
 *   children    the messages
 *   composer    the composer, below the messages
 */
const when = (iso) => {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
};

export default function ChatShell({
  icon: Icon = MessageCircle, title, badge, description,
  chats = [], selectedId = null, onSelect, onNew, onDelete, loadingChats = false,
  emptyChatsText = 'No chats yet. Ask a question to start one.', testId = 'chat',
  children, composer,
}) {
  const [open, setOpen] = useState(sidePanelStartsOpen);
  const [search, setSearch] = useState('');
  const [searching, setSearching] = useState(false);

  const shown = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return chats;
    return chats.filter((c) => `${c.title || ''} ${c.detail || ''}`.toLowerCase().includes(term));
  }, [chats, search]);

  const closeOnPhone = () => { if (!sidePanelStartsOpen()) setOpen(false); };

  return (
    <div
      data-testid={`${testId}-shell`}
      className="relative flex h-[calc(100dvh-150px)] min-h-[480px] w-full overflow-hidden rounded-2xl border border-border"
      style={{ background: 'var(--app-hero-bg)' }}
    >
      {/* The chats */}
      <aside
        data-testid={`${testId}-list`}
        aria-hidden={!open}
        className={`z-20 flex shrink-0 flex-col overflow-hidden border-border transition-all duration-300 ease-in-out
          max-md:absolute max-md:inset-y-0 max-md:left-0 max-md:shadow-2xl
          ${open ? 'w-64 border-r opacity-100' : 'w-0 border-r-0 opacity-0'}`}
        style={{ background: 'var(--panel-3)' }}
      >
        <div className="w-64 shrink-0 space-y-2 border-b border-border px-3 pb-2 pt-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold tracking-wide text-foreground">Chats</span>
            <button type="button" onClick={() => setOpen(false)} title="Close the list"
              className="flex h-8 w-8 items-center justify-center rounded-full border border-border hover:border-violet-400/60 hover:bg-violet-500/10">
              <ChevronsLeft className="h-4 w-4 text-muted-foreground" />
            </button>
          </div>
          <div className="flex items-center gap-2 rounded-lg border border-violet-500/25 bg-violet-500/5 px-2 py-1.5">
            {searching ? (
              <>
                <input autoFocus value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search chats..."
                  className="min-w-0 flex-1 bg-transparent px-1 text-sm text-foreground outline-none placeholder:text-muted-foreground" />
                <button type="button" title="Close search" onClick={() => { setSearch(''); setSearching(false); }}
                  className="flex h-7 w-7 items-center justify-center rounded-full border border-border hover:border-violet-400/60">
                  <X className="h-3.5 w-3.5 text-muted-foreground" />
                </button>
              </>
            ) : (
              <>
                <span className="flex-1 text-sm font-medium text-muted-foreground">Conversations</span>
                <button type="button" title="Search" onClick={() => setSearching(true)}
                  className="flex h-7 w-7 items-center justify-center rounded-full border border-border hover:border-violet-400/60">
                  <Search className="h-3.5 w-3.5 text-muted-foreground" />
                </button>
                <button type="button" title="New chat" data-testid={`${testId}-new`} onClick={() => { onNew?.(); closeOnPhone(); }}
                  className="flex h-7 w-7 items-center justify-center rounded-full border border-border hover:border-violet-400/60">
                  <Plus className="h-4 w-4 text-foreground" />
                </button>
              </>
            )}
          </div>
        </div>
        <div className="w-64 min-h-0 flex-1 overflow-y-auto p-2">
          {loadingChats ? (
            <div className="flex justify-center p-4"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
          ) : shown.length === 0 ? (
            <p className="p-4 text-center text-sm text-muted-foreground">{search.trim() ? 'No chat matches.' : emptyChatsText}</p>
          ) : (
            <div className="space-y-1">
              {shown.map((c) => {
                const active = c.id === selectedId;
                return (
                  <div key={c.id} data-testid={`${testId}-item`}
                    className={`flex items-center gap-1 rounded-lg border text-sm transition-colors ${active
                      ? 'border-violet-500/60 bg-violet-500/10 shadow-[0_0_12px_rgba(139,92,246,0.15)]'
                      : 'border-border/60 hover:border-violet-400/30 hover:bg-accent/50'}`}>
                    <button type="button" onClick={() => { onSelect?.(c); closeOnPhone(); }} className="min-w-0 flex-1 p-2.5 text-left">
                      <div className={`truncate font-medium ${active ? 'text-violet-300' : 'text-foreground'}`} title={c.title}>{c.title || 'Chat'}</div>
                      <div className="mt-0.5 truncate text-xs text-muted-foreground">
                        {[c.detail, when(c.updatedAt)].filter(Boolean).join(' · ')}
                      </div>
                    </button>
                    {onDelete && (
                      <Button type="button" variant="ghost" size="icon" title="Delete chat" onClick={() => onDelete(c)}
                        className="h-8 w-8 shrink-0 opacity-60 hover:bg-destructive/10 hover:text-destructive hover:opacity-100">
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </aside>
      {open && (
        <button type="button" aria-label="Close the list" onClick={() => setOpen(false)}
          className="absolute inset-0 z-10 bg-black/40 md:hidden" />
      )}

      {/* The conversation */}
      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-3 py-3 sm:px-5">
          <div className="flex min-w-0 items-center gap-3">
            <div className="hidden h-10 w-1.5 shrink-0 rounded-full sm:block"
              style={{ background: 'linear-gradient(to bottom, hsl(var(--brand-accent)) 0%, #6a1b9a 60%, #18122B 100%)' }} />
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-violet-500/15">
              <Icon className="h-5 w-5 text-violet-300" />
            </div>
            <div className="min-w-0">
              <h2 className="flex items-center gap-2 truncate text-base font-semibold text-foreground sm:text-lg">
                <span className="truncate">{title}</span>
                {badge && <span className="shrink-0 rounded-full bg-violet-500/15 px-2.5 py-0.5 text-[10px] font-medium text-violet-300">{badge}</span>}
              </h2>
              {description && <p className="truncate text-xs text-muted-foreground sm:text-sm">{description}</p>}
            </div>
          </div>
          <Button type="button" size="sm" variant={open ? 'ghost' : 'outline'} onClick={() => setOpen((v) => !v)}
            title={open ? 'Hide the chats' : 'Show the chats'} data-testid={`${testId}-toggle`} className="shrink-0 gap-1.5">
            {open ? <ChevronsLeft className="h-4 w-4" /> : <ChevronsRight className="h-4 w-4" />}
            <span className="hidden text-xs sm:inline">{open ? 'Hide' : 'Chats'}</span>
          </Button>
        </header>
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto overflow-x-hidden px-3 py-4 sm:px-5">{children}</div>
        {composer && <div className="shrink-0 border-t border-border" style={{ background: 'var(--panel-3)' }}>{composer}</div>}
      </section>
    </div>
  );
}
