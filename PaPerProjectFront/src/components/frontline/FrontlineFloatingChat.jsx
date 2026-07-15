import React, { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import {
  MessageCircle,
  X,
  Send,
  Loader2,
  Sparkles,
  GraduationCap,
  History,
  Trash2,
  Paperclip,
  Ticket,
  FileText,
  Plus,
  Slash,
} from 'lucide-react';
import InfoHint, { useHints } from './InfoHint';
import FrontlineTutorial, { hasSeenTutorial, resetTutorial } from './FrontlineTutorial';
import { FLOATING_CHAT_TOUR, HINTS } from './frontlineTutorialSteps';
import {
  listChatHistory,
  saveChatConversation,
  deleteChatConversation,
  listRecentlyViewed,
} from './frontlineLocalStore';
import frontlineAgentService from '@/services/frontlineAgentService';
import { useToast } from '@/components/ui/use-toast';
import { useDraggableResizable, ContextIndicator, ResizeCorner } from './chatShellUtils';

const SAMPLE_PROMPTS = [
  "How do I reset a customer's password?",
  "What's our refund policy for enterprise plans?",
  'Which SOP covers escalation to engineering?',
];

// Slash commands surfaced in the auto-complete menu when the user types "/".
const SLASH_COMMANDS = [
  {
    key: '/help',
    label: '/help',
    description: 'Show every slash command available in Quick Chat.',
    hint: '',
    icon: Slash,
  },
  {
    key: '/new',
    label: '/new',
    description: 'Start a fresh conversation. Current chat is auto-saved to history first.',
    hint: '',
    icon: Plus,
  },
  {
    key: '/clear',
    label: '/clear',
    description: 'Clear the current chat without saving it to history.',
    hint: '',
    icon: Trash2,
  },
  {
    key: '/ticket',
    label: '/ticket',
    description: 'Create a support ticket. Format: /ticket <title> — <description>',
    hint: ' <title> — <description>',
    icon: Ticket,
  },
  {
    key: '/upload',
    label: '/upload',
    description: 'Open the file picker to upload a document into the knowledge base.',
    hint: '',
    icon: FileText,
  },
];

function newConversationId() {
  return `fc_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

const FrontlineFloatingChat = () => {
  const { enabled: hintsEnabled } = useHints();
  const { toast } = useToast();

  const [open, setOpen] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  // Current conversation state
  const [conversationId, setConversationId] = useState(() => newConversationId());
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);

  // Slash-menu state
  const [slashOpen, setSlashOpen] = useState(false);
  const [slashFilter, setSlashFilter] = useState('');
  const [slashActive, setSlashActive] = useState(0);

  // Tour state
  const [tourOpen, setTourOpen] = useState(false);

  // Reactive stores (re-read from localStorage when we need to show them)
  const [history, setHistory] = useState(() => listChatHistory());
  // Draggable + resizable geometry, persisted per storage key.
  const { containerStyle: geomStyle, dragHandleProps, resizeHandleProps } = useDraggableResizable('frontline_fc');
  const [recents, setRecents] = useState(() => listRecentlyViewed());

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const fileInputRef = useRef(null);

  const refreshHistory = () => setHistory(listChatHistory());
  const refreshRecents = () => setRecents(listRecentlyViewed());

  // Refresh stores whenever the chat opens (someone else may have viewed a
  // ticket / doc in another tab of the dashboard while chat was closed).
  useEffect(() => {
    if (open) {
      refreshHistory();
      refreshRecents();
    }
  }, [open]);

  // Persist current conversation whenever it changes and has content
  useEffect(() => {
    if (!messages.length) return;
    const firstUser = messages.find((m) => m.role === 'user');
    const title = (firstUser?.content || 'Untitled').slice(0, 60);
    saveChatConversation({
      id: conversationId,
      title,
      messages,
      updated_at: Date.now(),
    });
    refreshHistory();
  }, [messages, conversationId]);

  // Global Ctrl/Cmd+K shortcut to open the chat from anywhere in the dashboard.
  useEffect(() => {
    const onKey = (e) => {
      const isK = (e.key === 'k' || e.key === 'K');
      const isCmd = e.metaKey || e.ctrlKey;
      if (isK && isCmd) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Auto-launch the tour the first time the chat is opened, otherwise focus
  // the input for immediate typing.
  useEffect(() => {
    if (!open) return;
    if (!hasSeenTutorial(FLOATING_CHAT_TOUR.key)) {
      const t = setTimeout(() => setTourOpen(true), 500);
      return () => clearTimeout(t);
    }
    const f = setTimeout(() => inputRef.current?.focus(), 250);
    return () => clearTimeout(f);
  }, [open]);

  // Auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, sending, uploading]);

  const pushMessage = (msg) => setMessages((m) => [...m, msg]);

  const startNewConversation = () => {
    // Just rotate the id — the outgoing conversation is already persisted.
    setConversationId(newConversationId());
    setMessages([]);
    setInput('');
    setShowHistory(false);
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  const clearCurrentConversation = () => {
    deleteChatConversation(conversationId);
    setMessages([]);
    setInput('');
    refreshHistory();
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  const openHistoryEntry = (entry) => {
    setConversationId(entry.id);
    setMessages(entry.messages || []);
    setShowHistory(false);
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  const removeHistoryEntry = (id) => {
    deleteChatConversation(id);
    refreshHistory();
  };

  // ----- Slash-command handling -------------------------------------------

  const filteredCommands = SLASH_COMMANDS.filter((c) =>
    c.key.slice(1).startsWith(slashFilter.toLowerCase())
  );

  const applyCommand = (cmd) => {
    setInput(cmd.key + (cmd.hint || ' '));
    setSlashOpen(false);
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  const handleInputChange = (e) => {
    const val = e.target.value;
    setInput(val);
    if (val.startsWith('/') && !val.includes(' ')) {
      setSlashFilter(val.slice(1));
      setSlashOpen(true);
      setSlashActive(0);
    } else {
      setSlashOpen(false);
    }
  };

  const runSlashCommand = async (raw) => {
    const [rawCmd, ...rest] = raw.trim().split(/\s+/);
    const cmd = rawCmd.toLowerCase();
    const argText = rest.join(' ').trim();

    if (cmd === '/help') {
      pushMessage({
        role: 'assistant',
        content: `Available slash commands:\n${SLASH_COMMANDS.map((c) => `${c.label}${c.hint ? ' ' + c.hint.trim() : ''} — ${c.description}`).join('\n')}`,
        system: true,
      });
      return true;
    }
    if (cmd === '/new') {
      startNewConversation();
      return true;
    }
    if (cmd === '/clear') {
      clearCurrentConversation();
      return true;
    }
    if (cmd === '/upload') {
      fileInputRef.current?.click();
      return true;
    }
    if (cmd === '/ticket') {
      if (!argText) {
        pushMessage({
          role: 'assistant',
          content: 'Usage: /ticket <title> — <description>. Example: /ticket Password reset failing — Customer sees a 500 on submit.',
          system: true,
          error: true,
        });
        return true;
      }
      // Split "<title> — <description>" on em-dash or hyphen surrounded by spaces
      const m = argText.match(/^(.*?)(?:\s+[—-]\s+(.+))?$/);
      const title = (m?.[1] || argText).slice(0, 200);
      const description = (m?.[2] || argText).slice(0, 4000);
      pushMessage({ role: 'user', content: `/ticket ${argText}` });
      try {
        const res = await frontlineAgentService.createTicket(title, description);
        if (res && res.status === 'success' && res.data) {
          const t = res.data;
          const ticketId = t.id || t.ticket_id;
          pushMessage({
            role: 'assistant',
            content: `Ticket #${ticketId} created${t.auto_resolved ? ' and auto-resolved by AI.' : '.'}${t.response ? '\n\n' + t.response : ''}`,
            system: true,
          });
          toast({ title: 'Ticket created', description: `#${ticketId}: ${title}` });
        } else {
          throw new Error((res && res.message) || 'Failed to create ticket');
        }
      } catch (e) {
        pushMessage({
          role: 'assistant',
          content: `Failed to create ticket: ${e.message || 'Unknown error'}`,
          error: true,
        });
      }
      return true;
    }
    return false; // not a recognised slash command — fall through to LLM
  };

  // ----- Send flow --------------------------------------------------------

  const send = async () => {
    const q = input.trim();
    if (!q || sending || uploading) return;

    // If the input starts with "/", try to handle it as a slash command.
    if (q.startsWith('/')) {
      setInput('');
      setSlashOpen(false);
      const handled = await runSlashCommand(q);
      if (handled) return;
      // Not a recognised command — fall through and treat as a question.
    }

    pushMessage({ role: 'user', content: q });
    setInput('');
    setSlashOpen(false);
    setSending(true);
    try {
      const res = await frontlineAgentService.knowledgeQA(q, {});
      if (res && res.status === 'success' && res.data) {
        const data = res.data;
        pushMessage({
          role: 'assistant',
          content: data.answer || 'No answer available.',
          source: data.source || null,
          has_verified_info: !!data.has_verified_info,
          citations: data.citations || [],
        });
      } else {
        throw new Error((res && res.message) || 'Failed to get an answer');
      }
    } catch (e) {
      pushMessage({ role: 'assistant', content: `Error: ${e.message || 'Something went wrong.'}`, error: true });
    } finally {
      setSending(false);
    }
  };

  // ----- Upload flow ------------------------------------------------------

  const handleFilePicked = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    pushMessage({
      role: 'user',
      content: `📎 Uploading: ${file.name} (${Math.round(file.size / 1024)} KB)`,
    });
    setUploading(true);
    try {
      const res = await frontlineAgentService.uploadDocument(file, file.name, '', 'knowledge_base');
      if (res && (res.status === 'success' || res.status === 'accepted') && res.data) {
        const doc = res.data;
        pushMessage({
          role: 'assistant',
          content: `Uploaded "${doc.title || file.name}". The AI can now reference it once indexing completes.`,
          system: true,
        });
        toast({ title: 'Document uploaded', description: doc.title || file.name });
      } else {
        throw new Error((res && res.message) || 'Upload failed');
      }
    } catch (err) {
      pushMessage({
        role: 'assistant',
        content: `Upload failed: ${err.message || 'Unknown error'}`,
        error: true,
      });
    } finally {
      setUploading(false);
    }
  };

  // ----- Keyboard within the input ----------------------------------------

  const handleInputKeyDown = useCallback((e) => {
    if (slashOpen && filteredCommands.length > 0) {
      if (e.key === 'ArrowDown') { e.preventDefault(); setSlashActive((i) => (i + 1) % filteredCommands.length); return; }
      if (e.key === 'ArrowUp')   { e.preventDefault(); setSlashActive((i) => (i - 1 + filteredCommands.length) % filteredCommands.length); return; }
      if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
        e.preventDefault();
        applyCommand(filteredCommands[slashActive]);
        return;
      }
      if (e.key === 'Escape') { e.preventDefault(); setSlashOpen(false); return; }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }, [slashOpen, filteredCommands, slashActive]);

  const replayTour = () => {
    resetTutorial(FLOATING_CHAT_TOUR.key);
    setTourOpen(true);
  };

  // ----- Render helpers ---------------------------------------------------

  const relativeTime = (ts) => {
    if (!ts) return '';
    const diff = (Date.now() - ts) / 1000;
    if (diff < 60) return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  };

  return (
    <>
      {/* Floating launcher — visible only when the chat is closed */}
      {!open && createPortal(
        <div className="fixed bottom-6 right-6 z-[9990] flex items-end gap-2">
          {hintsEnabled && (
            <div className="pb-2"><InfoHint {...HINTS.fcLauncher} /></div>
          )}
          <button
            type="button"
            onClick={() => setOpen(true)}
            data-tour-fc="launcher"
            title="Open Quick Chat (Ctrl+K)"
            aria-label="Open Quick Chat"
            className="relative h-14 w-14 rounded-full flex items-center justify-center text-white shadow-2xl hover:scale-110 active:scale-95 transition-transform"
            style={{
              background: 'linear-gradient(135deg, #f59e0b 0%, #f97316 100%)',
              boxShadow: '0 12px 32px 0 rgba(245, 158, 11, 0.55), 0 0 0 1px rgba(255,255,255,0.08) inset',
            }}
          >
            <span aria-hidden="true" className="absolute inset-0 rounded-full"
              style={{ background: 'rgba(245, 158, 11, 0.55)', animation: 'fcPing 2.2s cubic-bezier(0,0,0.2,1) infinite' }} />
            <span aria-hidden="true" className="absolute inset-1.5 rounded-full"
              style={{ background: 'linear-gradient(135deg, #fbbf24 0%, #fb923c 100%)', animation: 'fcBlink 1.6s ease-in-out infinite' }} />
            <MessageCircle className="h-6 w-6 relative z-10 drop-shadow" />
            {/* Ctrl+K badge */}
            <span className="absolute -top-1 -right-1 z-20 rounded-md bg-black/70 text-white text-[9px] font-bold px-1.5 py-0.5 border border-white/15">
              Ctrl+K
            </span>
          </button>

          <style>{`
            @keyframes fcPing {
              0%   { transform: scale(1);   opacity: 0.75; }
              75%  { transform: scale(1.9); opacity: 0; }
              100% { transform: scale(1.9); opacity: 0; }
            }
            @keyframes fcBlink {
              0%, 100% { opacity: 1; }
              50%      { opacity: 0.75; }
            }
          `}</style>
        </div>,
        document.body
      )}

      {/* Chat modal */}
      {open && createPortal(
        <div
          className="fixed z-[9990] rounded-2xl border border-[#3a295a] bg-[#0e0e14] shadow-2xl flex flex-col overflow-hidden"
          style={geomStyle}
        >
          {/* Resize corner (top-left) */}
          <ResizeCorner handleProps={resizeHandleProps} />
          {/* Header — also acts as the drag handle */}
          <div
            data-tour-fc="header"
            {...dragHandleProps}
            className="flex items-center justify-between px-3 py-2.5 border-b border-white/10 select-none"
            style={{ ...dragHandleProps.style, background: 'linear-gradient(90deg, #f59e0b 0%, #f97316 100%)' }}
          >
            <div className="flex items-center gap-2 min-w-0">
              <Sparkles className="h-4 w-4 text-white shrink-0" />
              <div className="min-w-0">
                <div className="text-sm font-semibold text-white leading-tight">Quick Chat</div>
                <div className="text-[10px] text-white/70 leading-tight truncate">
                  AI grounded in your knowledge base · type / for commands
                </div>
              </div>
              {hintsEnabled && <InfoHint {...HINTS.fcHeader} />}
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <button type="button" onClick={() => setShowHistory((v) => !v)}
                title={showHistory ? 'Back to chat' : `History (${history.length})`}
                aria-label="Chat history"
                className={`p-1 rounded transition text-white relative ${showHistory ? 'bg-white/25' : 'hover:bg-white/25'}`}>
                <History className="h-4 w-4" />
                {history.length > 0 && !showHistory && (
                  <span className="absolute -top-0.5 -right-0.5 text-[8px] font-bold bg-white text-orange-600 rounded-full h-3.5 w-3.5 flex items-center justify-center">
                    {Math.min(history.length, 9)}
                  </span>
                )}
              </button>
              <button type="button" onClick={startNewConversation} title="Start new chat" aria-label="Start new chat"
                className="p-1 rounded hover:bg-white/25 text-white transition">
                <Plus className="h-4 w-4" />
              </button>
              <button type="button" onClick={replayTour} title="Take a tour of Quick Chat" aria-label="Take a tour"
                className="p-1 rounded hover:bg-white/25 text-white transition">
                <GraduationCap className="h-4 w-4" />
              </button>
              <button type="button" onClick={() => setOpen(false)} title="Close (Ctrl+K)" aria-label="Close Quick Chat"
                className="p-1 rounded hover:bg-white/25 text-white transition">
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Body: either the chat area or the history sidebar */}
          {showHistory ? (
            <div className="flex-1 overflow-y-auto p-3 space-y-1.5" style={{ background: '#0a0a0f' }}>
              <div className="flex items-center justify-between mb-2">
                <p className="text-[10px] uppercase tracking-wider text-white/40 font-semibold">Recent conversations</p>
                <span className="text-[10px] text-white/40">{history.length} saved</span>
              </div>
              {history.length === 0 ? (
                <p className="text-sm text-white/50 text-center py-8">No saved conversations yet.</p>
              ) : (
                history.map((h) => (
                  <div key={h.id}
                    className={`group flex items-center gap-2 px-2 py-2 rounded-lg cursor-pointer transition
                      ${h.id === conversationId ? 'bg-amber-400/10 border border-amber-400/30' : 'hover:bg-white/[0.04] border border-transparent'}`}
                    onClick={() => openHistoryEntry(h)}
                  >
                    <MessageCircle className="h-3.5 w-3.5 shrink-0 text-white/40" />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-white/85 truncate">{h.title}</div>
                      <div className="text-[10px] text-white/40">
                        {relativeTime(h.updated_at)} · {(h.messages || []).length} messages
                      </div>
                    </div>
                    <button type="button" onClick={(e) => { e.stopPropagation(); removeHistoryEntry(h.id); }}
                      title="Delete this conversation" aria-label="Delete this conversation"
                      className="opacity-0 group-hover:opacity-100 p-1 rounded text-white/40 hover:text-rose-400 hover:bg-white/[0.06] transition">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))
              )}
            </div>
          ) : (
            <div data-tour-fc="messages" className="flex-1 overflow-y-auto p-3 space-y-2.5" style={{ background: '#0a0a0f' }}>
              {messages.length === 0 ? (
                <div className="text-white/60">
                  <div className="text-center py-4">
                    <div className="h-10 w-10 mx-auto mb-2 rounded-full bg-amber-400/10 border border-amber-400/30 flex items-center justify-center">
                      <MessageCircle className="h-5 w-5 text-amber-300" />
                    </div>
                    <p className="text-sm px-2">Ask a question or type <span className="text-amber-300 font-mono">/</span> for commands.</p>
                    {hintsEnabled && (
                      <div className="mt-2 flex justify-center">
                        <InfoHint {...HINTS.fcMessages} />
                      </div>
                    )}
                  </div>

                  {/* Recently viewed strip */}
                  {recents.length > 0 && (
                    <div className="mt-3 mb-4">
                      <p className="text-[10px] uppercase tracking-wider text-white/40 font-semibold mb-1.5">Recently viewed</p>
                      <div className="space-y-1">
                        {recents.map((r) => {
                          const Icon = r.kind === 'ticket' ? Ticket : FileText;
                          return (
                            <button key={`${r.kind}-${r.id}`} type="button"
                              onClick={() => {
                                setInput(r.kind === 'ticket'
                                  ? `Tell me about ticket #${r.id}: ${r.title}`
                                  : `Summarize the document "${r.title}"`);
                                inputRef.current?.focus();
                              }}
                              className="w-full flex items-center gap-2 text-left px-2 py-1.5 rounded hover:bg-white/[0.05] transition group">
                              <Icon className="h-3.5 w-3.5 text-white/50 shrink-0" />
                              <span className="text-xs text-white/70 truncate group-hover:text-white/90">
                                {r.kind === 'ticket' ? `#${r.id} · ` : ''}{r.title}
                              </span>
                              <span className="text-[10px] text-white/30 ml-auto shrink-0">{relativeTime(r.at)}</span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  <div className="mt-3">
                    <p className="text-[10px] uppercase tracking-wider text-white/40 font-semibold mb-1">Try one</p>
                    <div className="space-y-1">
                      {(() => {
                        const dyn = [];
                        (recents || []).slice(0, 2).forEach((r) => {
                          if (r.kind === 'ticket') dyn.push(`Tell me about ticket #${r.id}: ${r.title}`);
                          else if (r.kind === 'document') dyn.push(`Summarize the document "${r.title}"`);
                        });
                        const rot = SAMPLE_PROMPTS[Math.floor((Date.now() / 60000) % SAMPLE_PROMPTS.length)];
                        const staticPool = SAMPLE_PROMPTS.filter((s) => s !== rot).slice(0, 2);
                        const shown = [...dyn, rot, ...staticPool].slice(0, 3);
                        return shown.map((sample) => (
                          <button key={sample} type="button"
                            onClick={() => { setInput(sample); inputRef.current?.focus(); }}
                            className="block w-full text-left text-xs text-amber-300/80 hover:text-amber-200 hover:bg-white/[0.04] rounded px-2 py-1 transition">
                            → {sample}
                          </button>
                        ));
                      })()}
                    </div>
                  </div>
                </div>
              ) : (
                messages.map((m, i) => (
                  <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div
                      className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                        m.role === 'user'
                          ? 'bg-amber-500/25 text-white border border-amber-400/30'
                          : m.error
                            ? 'bg-rose-500/15 text-rose-100 border border-rose-500/30'
                            : m.system
                              ? 'bg-violet-500/10 text-violet-100 border border-violet-400/30'
                              : 'bg-white/[0.06] text-white/90 border border-white/10'
                      }`}
                    >
                      <div className="whitespace-pre-wrap break-words">{m.content}</div>
                      {m.role === 'assistant' && !m.error && !m.system && (m.citations?.length > 0 || m.source) && (
                        <div className="mt-2 pt-2 border-t border-white/10 space-y-0.5">
                          <p className="text-[10px] font-medium text-white/50 uppercase tracking-wider">Sources</p>
                          {m.citations && m.citations.length > 0
                            ? m.citations.slice(0, 3).map((c, idx) => (
                                <div key={idx} className="text-[11px] text-white/60 truncate">
                                  • {c.title || c.source || 'Source'}
                                </div>
                              ))
                            : <div className="text-[11px] text-white/60 truncate">• {m.source}</div>}
                        </div>
                      )}
                    </div>
                  </div>
                ))
              )}
              {(sending || uploading) && (
                <div className="flex justify-start">
                  <div className="bg-white/[0.06] border border-white/10 rounded-lg px-3 py-2 flex items-center gap-2">
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-white/60" />
                    <span className="text-xs text-white/60">{uploading ? 'Uploading…' : 'Searching knowledge base…'}</span>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}

          {/* Input row — always rendered, hidden behind history view visually */}
          {!showHistory && (
            <div className="border-t border-white/10 relative" style={{ background: '#0e0e14' }}>
              {/* Multi-turn context indicator */}
              {messages.length >= 2 && (
                <div className="px-3 pt-2">
                  <ContextIndicator count={Math.min(messages.length, 6)} />
                </div>
              )}
              {/* Slash-command menu */}
              {slashOpen && filteredCommands.length > 0 && (
                <div className="absolute bottom-full left-2 right-2 mb-2 rounded-lg border border-[#3a295a] bg-[#161630] shadow-2xl overflow-hidden">
                  <div className="px-3 py-1.5 border-b border-white/10 text-[10px] uppercase tracking-wider text-white/40 font-semibold">
                    Commands · ↑↓ Tab/Enter to insert
                  </div>
                  <div className="max-h-48 overflow-y-auto">
                    {filteredCommands.map((c, i) => {
                      const Icon = c.icon;
                      return (
                        <button key={c.key} type="button" onMouseDown={(e) => { e.preventDefault(); applyCommand(c); }}
                          onMouseEnter={() => setSlashActive(i)}
                          className={`w-full flex items-start gap-2 px-3 py-2 text-left transition
                            ${i === slashActive ? 'bg-amber-400/10' : 'hover:bg-white/[0.03]'}`}>
                          <Icon className="h-4 w-4 shrink-0 text-amber-300 mt-0.5" />
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
              )}

              <div className="p-2.5 flex gap-2 items-end">
                {hintsEnabled && <div className="pb-1.5"><InfoHint {...HINTS.fcInput} /></div>}
                {/* Hidden file input for /upload */}
                <input ref={fileInputRef} type="file" className="hidden" onChange={handleFilePicked}
                  accept=".pdf,.doc,.docx,.txt,.md,.html" />
                <button type="button" onClick={() => fileInputRef.current?.click()}
                  disabled={sending || uploading}
                  title="Upload a document to the knowledge base"
                  aria-label="Upload document"
                  className="h-[38px] w-[38px] shrink-0 rounded-lg flex items-center justify-center text-white/60 hover:text-amber-300 hover:bg-white/[0.05] border border-white/10 transition disabled:opacity-40">
                  <Paperclip className="h-4 w-4" />
                </button>
                <textarea
                  ref={inputRef}
                  data-tour-fc="input"
                  value={input}
                  onChange={handleInputChange}
                  onKeyDown={handleInputKeyDown}
                  placeholder="Ask anything or type / for commands…"
                  rows={1}
                  disabled={sending || uploading}
                  className="flex-1 resize-none rounded-lg border border-white/10 bg-[#0a0a0f] text-white text-sm px-3 py-2 placeholder:text-white/30 focus:outline-none focus:ring-1 focus:ring-amber-400/60 min-h-[38px] max-h-[110px]"
                />
                <button
                  type="button" data-tour-fc="send" onClick={send}
                  disabled={sending || uploading || !input.trim()} aria-label="Send"
                  className="h-[38px] w-[38px] shrink-0 rounded-lg flex items-center justify-center text-white disabled:opacity-40 disabled:cursor-not-allowed transition-transform active:scale-95"
                  style={{ background: 'linear-gradient(135deg, #f59e0b 0%, #f97316 100%)' }}
                >
                  {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </button>
                {hintsEnabled && <div className="pb-1.5"><InfoHint {...HINTS.fcSend} /></div>}
              </div>
            </div>
          )}
        </div>,
        document.body
      )}

      {/* Guided tour for the floating chat */}
      <FrontlineTutorial
        open={tourOpen}
        onClose={() => setTourOpen(false)}
        steps={FLOATING_CHAT_TOUR.steps}
        storageKey={FLOATING_CHAT_TOUR.key}
      />
    </>
  );
};

export default FrontlineFloatingChat;
