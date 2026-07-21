import React, { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import {
  MessageCircle, X, Send, Loader2, Sparkles, GraduationCap,
  History, Trash2, Paperclip, FileText, Plus, Slash, Users, Upload,
} from 'lucide-react';
import InfoHint, { useHints } from '../frontline/InfoHint';
import FrontlineTutorial, { hasSeenTutorial, resetTutorial } from '../frontline/FrontlineTutorial';
import { HR_FLOATING_CHAT_TOUR, HR_HINTS } from './hrTutorialSteps';
import {
  listHRChatHistory,
  saveHRChatConversation,
  deleteHRChatConversation,
  listHRRecentlyViewed,
} from './hrLocalStore';
import hrAgentService from '@/services/hrAgentService';
import { useToast } from '@/components/ui/use-toast';
import { useDraggableResizable, ContextIndicator, ResizeCorner, MobileSheetHandle, ElapsedTimer } from '../frontline/chatShellUtils';

const SAMPLE_PROMPTS = [
  "What's our parental leave policy?",
  'How many PTO days do I have left?',
  'Walk me through the offboarding checklist.',
];

const SLASH_COMMANDS = [
  { key: '/help',   label: '/help',   hint: '',                      description: 'Show every slash command available in HR Quick Chat.', icon: Slash },
  { key: '/new',    label: '/new',    hint: '',                      description: 'Start a fresh conversation. Current chat is auto-saved.', icon: Plus },
  { key: '/clear',  label: '/clear',  hint: '',                      description: 'Clear the current chat without saving to history.', icon: Trash2 },
  { key: '/upload', label: '/upload', hint: '',                      description: 'Upload a document into the HR knowledge library.', icon: FileText },
  { key: '/find',   label: '/find',   hint: ' <name or email>',      description: 'Search employees. Example: /find sam@company.com', icon: Users },
];

function newConversationId() {
  return `hrfc_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

const HRFloatingChat = () => {
  const { enabled: hintsEnabled } = useHints();
  const { toast } = useToast();

  const [open, setOpen] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  const [conversationId, setConversationId] = useState(() => newConversationId());
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);
  // Byte-level upload % + chunk-embed indexing % for the file the user just
  // dropped. Renders a compact progress card below the message list.
  const [uploadProgress, setUploadProgress] = useState(0);
  const [indexProgress, setIndexProgress] = useState({
    status: 'idle', percent: 0, done: 0, total: 0, error: '', fileName: '',
  });
  // Start time of the current Q&A request — powers the live elapsed clock
  // inside the "Searching HR knowledge base…" indicator. Null when idle.
  const [sendingStartedAt, setSendingStartedAt] = useState(null);

  const [slashOpen, setSlashOpen] = useState(false);
  const [slashFilter, setSlashFilter] = useState('');
  const [slashActive, setSlashActive] = useState(0);
  // Live results for /find <arg>
  const [argResults, setArgResults] = useState(null); // null | array
  const argDebounceRef = useRef(null);

  const [tourOpen, setTourOpen] = useState(false);

  const [history, setHistory] = useState(() => listHRChatHistory());
  // Draggable + resizable geometry, persisted per storage key.
  const { containerStyle: geomStyle, dragHandleProps, resizeHandleProps } = useDraggableResizable('hr_fc');
  const [recents, setRecents] = useState(() => listHRRecentlyViewed());

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const fileInputRef = useRef(null);

  const refreshHistory = () => setHistory(listHRChatHistory());
  const refreshRecents = () => setRecents(listHRRecentlyViewed());

  useEffect(() => { if (open) { refreshHistory(); refreshRecents(); } }, [open]);

  // Persist current conversation whenever it changes
  useEffect(() => {
    if (!messages.length) return;
    const firstUser = messages.find((m) => m.role === 'user');
    const title = (firstUser?.content || 'Untitled').slice(0, 60);
    saveHRChatConversation({ id: conversationId, title, messages, updated_at: Date.now() });
    refreshHistory();
  }, [messages, conversationId]);

  // Global Ctrl/Cmd+K shortcut
  useEffect(() => {
    const onKey = (e) => {
      const isK = (e.key === 'k' || e.key === 'K');
      const isCmd = e.metaKey || e.ctrlKey;
      if (isK && isCmd) { e.preventDefault(); setOpen((v) => !v); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Auto-launch tour on first open; otherwise focus input
  useEffect(() => {
    if (!open) return;
    if (!hasSeenTutorial(HR_FLOATING_CHAT_TOUR.key)) {
      const t = setTimeout(() => setTourOpen(true), 500);
      return () => clearTimeout(t);
    }
    const f = setTimeout(() => inputRef.current?.focus(), 250);
    return () => clearTimeout(f);
  }, [open]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, sending, uploading]);

  const pushMessage = (msg) => setMessages((m) => [...m, msg]);

  const startNewConversation = () => {
    setConversationId(newConversationId());
    setMessages([]);
    setInput('');
    setShowHistory(false);
    setTimeout(() => inputRef.current?.focus(), 50);
  };
  const clearCurrentConversation = () => {
    deleteHRChatConversation(conversationId);
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
  const removeHistoryEntry = (id) => { deleteHRChatConversation(id); refreshHistory(); };

  // ---- Slash commands --------------------------------------------------

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
      setArgResults(null);
    } else {
      setSlashOpen(false);
      // Debounced arg autocomplete for /find <arg>
      const findMatch = val.match(/^\/find\s+(.+)$/i);
      clearTimeout(argDebounceRef.current);
      if (findMatch && findMatch[1].trim().length >= 2) {
        const q = findMatch[1].trim();
        argDebounceRef.current = setTimeout(async () => {
          try {
            const res = await hrAgentService.listHREmployees({ search: q, page_size: 5 });
            const rows = (res?.data?.results || res?.data || []).slice(0, 5);
            setArgResults(rows);
          } catch (_) { setArgResults([]); }
        }, 220);
      } else {
        setArgResults(null);
      }
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
    if (cmd === '/new')    { startNewConversation();      return true; }
    if (cmd === '/clear')  { clearCurrentConversation();  return true; }
    if (cmd === '/upload') { fileInputRef.current?.click(); return true; }
    if (cmd === '/find') {
      if (!argText) {
        pushMessage({ role: 'assistant', content: 'Usage: /find <name or email>. Example: /find sam@company.com', system: true, error: true });
        return true;
      }
      pushMessage({ role: 'user', content: `/find ${argText}` });
      setSending(true);
      try {
        const res = await hrAgentService.listHREmployees({ search: argText, page_size: 5 });
        const rows = (res?.data?.results || res?.data || []).slice(0, 5);
        if (rows.length === 0) {
          pushMessage({ role: 'assistant', content: `No employees found for "${argText}".`, system: true });
        } else {
          const summary = rows.map((r) =>
            `• ${r.first_name || ''} ${r.last_name || ''} — ${r.email || 'no email'}${r.job_title ? ' · ' + r.job_title : ''}${r.department_name ? ' · ' + r.department_name : ''}`.trim()
          ).join('\n');
          pushMessage({ role: 'assistant', content: `Found ${rows.length}:\n${summary}`, system: true });
        }
      } catch (e) {
        pushMessage({ role: 'assistant', content: `Search failed: ${e.message || 'Unknown error'}`, error: true });
      } finally {
        setSending(false);
      }
      return true;
    }
    return false;
  };

  // ---- Send flow -------------------------------------------------------

  const send = async () => {
    const q = input.trim();
    if (!q || sending || uploading) return;

    if (q.startsWith('/')) {
      setInput('');
      setSlashOpen(false);
      setArgResults(null);
      const handled = await runSlashCommand(q);
      if (handled) return;
    }

    pushMessage({ role: 'user', content: q });
    setInput('');
    setSlashOpen(false);
    setArgResults(null);
    setSending(true);

    const startedAt = (typeof performance !== 'undefined' && performance.now)
      ? performance.now() : Date.now();
    setSendingStartedAt(startedAt);
    try {
      // Pass short history (max last 6 messages) for multi-turn context
      const history = messages.slice(-6).map((m) => ({ role: m.role, content: m.content }));
      const res = await hrAgentService.askHRKnowledge(q, history);
      if (res && res.status === 'success' && res.data) {
        const data = res.data;
        const endedAt = (typeof performance !== 'undefined' && performance.now)
          ? performance.now() : Date.now();
        pushMessage({
          role: 'assistant',
          content: data.answer || data.response || 'No answer available.',
          source: data.source || null,
          citations: data.citations || data.sources || [],
          responseTimeMs: Math.round(endedAt - startedAt),
          cache_hit: !!data.cache_hit,
          // Server-side per-phase timing breakdown for the badge to render.
          timing_ms: data.timing_ms || null,
        });
      } else {
        throw new Error((res && res.message) || 'Failed to get an answer');
      }
    } catch (e) {
      pushMessage({ role: 'assistant', content: `Error: ${e.message || 'Something went wrong.'}`, error: true });
    } finally {
      setSending(false);
      setSendingStartedAt(null);
    }
  };

  // ---- Upload flow -----------------------------------------------------

  const handleFilePicked = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    pushMessage({ role: 'user', content: `📎 Uploading: ${file.name} (${Math.round(file.size / 1024)} KB)` });
    setUploading(true);
    setUploadProgress(0);
    setIndexProgress({ status: 'idle', percent: 0, done: 0, total: 0, error: '', fileName: file.name });
    try {
      const res = await hrAgentService.uploadHRDocument(file, file.name, '', {
        onProgress: ({ percent }) => setUploadProgress(percent),
      });
      setUploadProgress(100);
      if (!(res && (res.status === 'success' || res.status === 'accepted') && res.data)) {
        throw new Error((res && res.message) || 'Upload failed');
      }
      const doc = res.data;
      const documentId = doc.id;

      // Short-circuit if the server already reports the doc as ready.
      if (doc.processing_status === 'ready') {
        setIndexProgress({ status: 'ready', percent: 100, done: 0, total: 0, error: '', fileName: file.name });
        pushMessage({
          role: 'assistant',
          content: `Uploaded and indexed "${doc.title || file.name}". You can ask questions about it now.`,
          system: true,
        });
        toast({ title: 'HR document uploaded', description: doc.title || file.name });
        finishFloatingUpload();
        return;
      }

      setIndexProgress({ status: 'processing', percent: 0, done: 0, total: 0, error: '', fileName: file.name });
      if (documentId) {
        await pollFloatingIndexingProgress(documentId, file.name, doc.title);
      } else {
        pushMessage({
          role: 'assistant',
          content: `Uploaded "${doc.title || file.name}". The AI can reference it once indexing completes.`,
          system: true,
        });
        finishFloatingUpload();
      }
    } catch (err) {
      pushMessage({ role: 'assistant', content: `Upload failed: ${err.message || 'Unknown error'}`, error: true });
      setUploading(false);
      setUploadProgress(0);
      setIndexProgress({ status: 'idle', percent: 0, done: 0, total: 0, error: '', fileName: '' });
    }
  };

  // Reset the upload+index UI state after a successful lifecycle. Slight delay
  // so the user sees the completed bars before they disappear.
  const finishFloatingUpload = () => {
    setTimeout(() => {
      setUploading(false);
      setUploadProgress(0);
      setIndexProgress({ status: 'idle', percent: 0, done: 0, total: 0, error: '', fileName: '' });
    }, 800);
  };

  // Poll the lightweight status endpoint every 1.5s until the server flags the
  // doc as ready/failed or we hit a 5-min timeout. On timeout, we let the user
  // know the job is still running in the background.
  const pollFloatingIndexingProgress = async (documentId, fileName, docTitle) => {
    const startedAt = Date.now();
    const MAX_MS = 5 * 60 * 1000;
    const INTERVAL_MS = 1500;

    while (Date.now() - startedAt < MAX_MS) {
      try {
        const res = await hrAgentService.getHRDocumentStatus(documentId);
        const s = res?.data || {};
        setIndexProgress({
          status: s.processing_status || 'processing',
          percent: Number(s.percent || 0),
          done: Number(s.chunks_processed || 0),
          total: Number(s.chunks_total || 0),
          error: s.processing_error || '',
          fileName,
        });
        if (s.processing_status === 'ready') {
          pushMessage({
            role: 'assistant',
            content: `Indexed "${docTitle || fileName}" (${s.chunks_total || 0} chunk(s)). Ask me anything about it.`,
            system: true,
          });
          toast({ title: 'Indexing complete', description: docTitle || fileName });
          finishFloatingUpload();
          return;
        }
        if (s.processing_status === 'failed') {
          pushMessage({
            role: 'assistant',
            content: `Indexing failed: ${s.processing_error || 'The document could not be indexed.'}`,
            error: true,
          });
          setUploading(false);
          return;
        }
      } catch (err) {
        console.warn('Floating chat indexing poll error:', err);
      }
      await new Promise((r) => setTimeout(r, INTERVAL_MS));
    }
    pushMessage({
      role: 'assistant',
      content: `Still indexing "${docTitle || fileName}" — this can take a while for large documents. It will finish in the background.`,
      system: true,
    });
    setUploading(false);
  };

  // ---- Input keyboard --------------------------------------------------

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
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  }, [slashOpen, filteredCommands, slashActive]);

  const replayTour = () => { resetTutorial(HR_FLOATING_CHAT_TOUR.key); setTourOpen(true); };

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
      {/* Launcher */}
      {!open && createPortal(
        <div className="fixed bottom-6 right-6 z-[9990] flex items-end gap-2">
          {hintsEnabled && <div className="pb-2"><InfoHint {...HR_HINTS.hrFcLauncher} /></div>}
          <button
            type="button"
            onClick={() => setOpen(true)}
            data-tour-hrfc="launcher"
            title="Open HR Quick Chat (Ctrl+K)"
            aria-label="Open HR Quick Chat"
            className="relative h-14 w-14 rounded-full flex items-center justify-center text-white shadow-2xl hover:scale-110 active:scale-95 transition-transform"
            style={{
              background: 'linear-gradient(135deg, #8b5cf6 0%, #a78bfa 100%)',
              boxShadow: '0 12px 32px 0 rgba(139, 92, 246, 0.55), 0 0 0 1px rgba(255,255,255,0.08) inset',
            }}
          >
            <span aria-hidden="true" className="absolute inset-0 rounded-full"
              style={{ background: 'rgba(139, 92, 246, 0.55)', animation: 'hrfcPing 2.2s cubic-bezier(0,0,0.2,1) infinite' }} />
            <span aria-hidden="true" className="absolute inset-1.5 rounded-full"
              style={{ background: 'linear-gradient(135deg, #a78bfa 0%, #c4b5fd 100%)', animation: 'hrfcBlink 1.6s ease-in-out infinite' }} />
            <MessageCircle className="h-6 w-6 relative z-10 drop-shadow" />
            <span className="absolute -top-1 -right-1 z-20 rounded-md bg-black/70 text-white text-[9px] font-bold px-1.5 py-0.5 border border-white/15">
              Ctrl+K
            </span>
          </button>

          <style>{`
            @keyframes hrfcPing {
              0%   { transform: scale(1);   opacity: 0.75; }
              75%  { transform: scale(1.9); opacity: 0; }
              100% { transform: scale(1.9); opacity: 0; }
            }
            @keyframes hrfcBlink {
              0%, 100% { opacity: 1; }
              50%      { opacity: 0.75; }
            }
          `}</style>
        </div>,
        document.body
      )}

      {/* Modal */}
      {open && createPortal(
        <div
          className="fixed z-[9990] rounded-2xl border border-[#3a295a] bg-[#0e0e14] shadow-2xl flex flex-col overflow-hidden"
          style={geomStyle}
        >
          <ResizeCorner handleProps={resizeHandleProps} />
          <MobileSheetHandle />
          {/* Header — also acts as the drag handle on desktop */}
          <div
            data-tour-hrfc="header"
            {...dragHandleProps}
            className="flex items-center justify-between px-3 py-2.5 border-b border-white/10 select-none"
            style={{ ...dragHandleProps.style, background: 'linear-gradient(90deg, #8b5cf6 0%, #a78bfa 100%)' }}
          >
            <div className="flex items-center gap-2 min-w-0">
              <Sparkles className="h-4 w-4 text-white shrink-0" />
              <div className="min-w-0">
                <div className="text-sm font-semibold text-white leading-tight">HR Quick Chat</div>
                <div className="text-[10px] text-white/80 leading-tight truncate">
                  AI grounded in your HR docs · type / for commands
                </div>
              </div>
              {hintsEnabled && <InfoHint {...HR_HINTS.hrFcHeader} />}
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <button type="button" onClick={() => setShowHistory((v) => !v)}
                title={showHistory ? 'Back to chat' : `History (${history.length})`}
                className={`p-1 rounded transition text-white relative ${showHistory ? 'bg-white/25' : 'hover:bg-white/25'}`}>
                <History className="h-4 w-4" />
                {history.length > 0 && !showHistory && (
                  <span className="absolute -top-0.5 -right-0.5 text-[8px] font-bold bg-white text-violet-600 rounded-full h-3.5 w-3.5 flex items-center justify-center">
                    {Math.min(history.length, 9)}
                  </span>
                )}
              </button>
              <button type="button" onClick={startNewConversation} title="Start new chat"
                className="p-1 rounded hover:bg-white/25 text-white transition">
                <Plus className="h-4 w-4" />
              </button>
              <button type="button" onClick={replayTour} title="Take a tour of HR Quick Chat"
                className="p-1 rounded hover:bg-white/25 text-white transition">
                <GraduationCap className="h-4 w-4" />
              </button>
              <button type="button" onClick={() => setOpen(false)} title="Close (Ctrl+K)"
                className="p-1 rounded hover:bg-white/25 text-white transition">
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Body */}
          {showHistory ? (
            <div className="flex-1 overflow-y-auto p-3 space-y-1.5" style={{ background: '#0a0a0f' }}>
              <div className="flex items-center justify-between mb-2">
                <p className="text-[10px] uppercase tracking-wider text-white/40 font-semibold">Recent conversations</p>
                <span className="text-[10px] text-white/40">{history.length} saved</span>
              </div>
              {history.length === 0 ? (
                <p className="text-sm text-white/50 text-center py-8">No saved conversations yet.</p>
              ) : history.map((h) => (
                <div key={h.id}
                  className={`group flex items-center gap-2 px-2 py-2 rounded-lg cursor-pointer transition
                    ${h.id === conversationId ? 'bg-violet-500/10 border border-violet-400/30' : 'hover:bg-white/[0.04] border border-transparent'}`}
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
                    className="opacity-0 group-hover:opacity-100 p-1 rounded text-white/40 hover:text-rose-400 hover:bg-white/[0.06] transition">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div data-tour-hrfc="messages" className="flex-1 overflow-y-auto p-3 space-y-2.5" style={{ background: '#0a0a0f' }}>
              {messages.length === 0 ? (
                <div className="text-white/60">
                  <div className="text-center py-4">
                    <div className="h-10 w-10 mx-auto mb-2 rounded-full bg-violet-500/10 border border-violet-400/30 flex items-center justify-center">
                      <MessageCircle className="h-5 w-5 text-violet-300" />
                    </div>
                    <p className="text-sm px-2">Ask an HR question or type <span className="text-violet-300 font-mono">/</span> for commands.</p>
                    {hintsEnabled && <div className="mt-2 flex justify-center"><InfoHint {...HR_HINTS.hrFcMessages} /></div>}
                  </div>

                  {recents.length > 0 && (
                    <div className="mt-3 mb-4">
                      <p className="text-[10px] uppercase tracking-wider text-white/40 font-semibold mb-1.5">Recently viewed</p>
                      <div className="space-y-1">
                        {recents.map((r) => {
                          const Icon = r.kind === 'employee' ? Users : FileText;
                          return (
                            <button key={`${r.kind}-${r.id}`} type="button"
                              onClick={() => {
                                setInput(r.kind === 'employee'
                                  ? `Tell me about ${r.title}`
                                  : `Summarize the HR document "${r.title}"`);
                                inputRef.current?.focus();
                              }}
                              className="w-full flex items-center gap-2 text-left px-2 py-1.5 rounded hover:bg-white/[0.05] transition group">
                              <Icon className="h-3.5 w-3.5 text-white/50 shrink-0" />
                              <span className="text-xs text-white/70 truncate group-hover:text-white/90">{r.title}</span>
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
                      {/* Dynamic samples from recent activity when we have any,
                          otherwise fall back to the static set. */}
                      {(() => {
                        const dyn = [];
                        (recents || []).slice(0, 2).forEach((r) => {
                          if (r.kind === 'employee') dyn.push(`Tell me about ${r.title}`);
                          else if (r.kind === 'document') dyn.push(`Summarize the HR document "${r.title}"`);
                        });
                        // Rotate the static pool so repeat visits show variety.
                        const rot = SAMPLE_PROMPTS[Math.floor((Date.now() / 60000) % SAMPLE_PROMPTS.length)];
                        const staticPool = SAMPLE_PROMPTS.filter((s) => s !== rot).slice(0, 2);
                        const shown = [...dyn, rot, ...staticPool].slice(0, 3);
                        return shown.map((sample) => (
                          <button key={sample} type="button"
                            onClick={() => { setInput(sample); inputRef.current?.focus(); }}
                            className="block w-full text-left text-xs text-violet-300/80 hover:text-violet-200 hover:bg-white/[0.04] rounded px-2 py-1 transition">
                            → {sample}
                          </button>
                        ));
                      })()}
                    </div>
                  </div>
                </div>
              ) : messages.map((m, i) => (
                <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                      m.role === 'user'
                        ? 'bg-violet-500/25 text-white border border-violet-400/30'
                        : m.error
                          ? 'bg-rose-500/15 text-rose-100 border border-rose-500/30'
                          : m.system
                            ? 'bg-indigo-500/10 text-indigo-100 border border-indigo-400/30'
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
                    {typeof m.responseTimeMs === 'number' && m.role === 'assistant' && !m.error && (() => {
                      const tm = m.timing_ms;
                      const parts = [];
                      if (tm && !tm.cache) {
                        if (typeof tm.retrieval === 'number') parts.push(`retrieval ${(tm.retrieval / 1000).toFixed(1)}s`);
                        if (typeof tm.llm === 'number') parts.push(`llm ${(tm.llm / 1000).toFixed(1)}s`);
                      }
                      const rb = tm?.retrieval_breakdown;
                      const rbParts = [];
                      if (rb && (tm?.retrieval || 0) > 1000) {
                        const keys = ['query_embed', 'json_scan', 'keyword', 'chunk_fetch', 'output_build'];
                        for (const k of keys) {
                          if (typeof rb[k] === 'number' && rb[k] > 50) {
                            rbParts.push(`${k}=${(rb[k] / 1000).toFixed(1)}s`);
                          }
                        }
                        if (typeof rb.json_scan_chunks === 'number' && rb.json_scan_chunks > 0) {
                          rbParts.push(`scanned=${rb.json_scan_chunks}`);
                        }
                      }
                      return (
                        <div className="mt-1.5 text-[10px] text-white/40 space-y-0.5">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span>⏱ {(m.responseTimeMs / 1000).toFixed(2)}s</span>
                            {parts.length > 0 && (
                              <span className="text-white/30">({parts.join(' · ')})</span>
                            )}
                            {m.cache_hit && (
                              <span className="px-1 py-[1px] rounded bg-emerald-500/15 text-emerald-300 border border-emerald-400/25 text-[9px] font-medium">
                                cached
                              </span>
                            )}
                          </div>
                          {rbParts.length > 0 && (
                            <div className="text-[9px] text-white/30 font-mono">
                              {rbParts.join(' · ')}
                            </div>
                          )}
                        </div>
                      );
                    })()}
                  </div>
                </div>
              ))}
              {sending && !uploading && (
                <div className="flex justify-start">
                  <div className="bg-white/[0.06] border border-white/10 rounded-lg px-3 py-2 flex items-center gap-2">
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-white/60" />
                    <span className="text-xs text-white/60">Searching HR knowledge base…</span>
                    <span className="text-[11px] text-white/40 tabular-nums font-mono">
                      <ElapsedTimer since={sendingStartedAt} />
                    </span>
                  </div>
                </div>
              )}
              {uploading && (
                <div className="flex justify-start">
                  <div className="w-full max-w-[92%] bg-white/[0.04] border border-white/10 rounded-lg px-3 py-2.5 space-y-2.5">
                    {indexProgress.fileName && (
                      <div className="text-[11px] text-white/50 truncate">📎 {indexProgress.fileName}</div>
                    )}
                    <div>
                      <div className="flex items-center justify-between text-[11px] text-white/70 mb-1">
                        <span className="flex items-center gap-1.5">
                          <Upload className="h-3 w-3 text-violet-300" />
                          {uploadProgress < 100 ? 'Uploading file…' : 'Upload complete'}
                        </span>
                        <span className="font-mono text-white/50">{uploadProgress}%</span>
                      </div>
                      <div className="h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-violet-500 to-indigo-500 transition-all duration-200 ease-out"
                          style={{ width: `${uploadProgress}%` }}
                        />
                      </div>
                    </div>
                    {(uploadProgress >= 100 || indexProgress.status !== 'idle') && (
                      <div>
                        <div className="flex items-center justify-between text-[11px] text-white/70 mb-1">
                          <span className="flex items-center gap-1.5">
                            <Loader2 className={`h-3 w-3 text-amber-300 ${indexProgress.status === 'processing' ? 'animate-spin' : ''}`} />
                            {indexProgress.status === 'ready'
                              ? 'Indexing complete'
                              : indexProgress.status === 'failed'
                                ? 'Indexing failed'
                                : indexProgress.total > 0
                                  ? `Indexing ${indexProgress.done}/${indexProgress.total} chunks`
                                  : 'Preparing document…'}
                          </span>
                          <span className="font-mono text-white/50">{indexProgress.percent}%</span>
                        </div>
                        <div className="h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
                          <div
                            className={`h-full transition-all duration-200 ease-out ${
                              indexProgress.status === 'failed'
                                ? 'bg-red-500/70'
                                : indexProgress.status === 'ready'
                                  ? 'bg-emerald-500/80'
                                  : 'bg-gradient-to-r from-amber-500 to-orange-500'
                            }`}
                            style={{ width: `${indexProgress.percent}%` }}
                          />
                        </div>
                        {indexProgress.status === 'failed' && indexProgress.error && (
                          <div className="mt-1 text-[10px] text-red-300/90">{indexProgress.error}</div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}

          {/* Input row */}
          {!showHistory && (
            <div className="border-t border-white/10 relative" style={{ background: '#0e0e14' }}>
              {messages.length >= 2 && (
                <div className="px-3 pt-2">
                  <ContextIndicator count={Math.min(messages.length, 6)} />
                </div>
              )}
              {/* /find <arg> — live employee matches */}
              {argResults && !slashOpen && (
                <div className="absolute bottom-full left-2 right-2 mb-2 rounded-lg border border-[#3a295a] bg-[#161630] shadow-2xl overflow-hidden">
                  <div className="px-3 py-1.5 border-b border-white/10 text-[10px] uppercase tracking-wider text-white/40 font-semibold">
                    Matches
                  </div>
                  <div className="max-h-48 overflow-y-auto">
                    {argResults.length === 0 ? (
                      <div className="px-3 py-3 text-xs text-white/50">No employees found — Enter to send anyway.</div>
                    ) : argResults.map((r) => (
                      <button key={r.id} type="button"
                        onMouseDown={(e) => {
                          e.preventDefault();
                          setInput(`/find ${r.work_email || r.username || r.full_name}`);
                          setArgResults(null);
                          setTimeout(() => inputRef.current?.focus(), 0);
                        }}
                        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-violet-500/10 transition">
                        <div className="h-6 w-6 rounded-full bg-violet-500/20 flex items-center justify-center shrink-0 text-[10px] font-semibold text-violet-300">
                          {(r.full_name || r.username || '?').slice(0, 1).toUpperCase()}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="text-xs font-semibold text-white truncate">{r.full_name || r.username || `#${r.id}`}</div>
                          <div className="text-[10px] text-white/50 truncate">{r.work_email || r.email || ''}{r.job_title ? ' · ' + r.job_title : ''}</div>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}
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
                            ${i === slashActive ? 'bg-violet-500/10' : 'hover:bg-white/[0.03]'}`}>
                          <Icon className="h-4 w-4 shrink-0 text-violet-300 mt-0.5" />
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
                {hintsEnabled && <div className="pb-1.5"><InfoHint {...HR_HINTS.hrFcInput} /></div>}
                <input ref={fileInputRef} type="file" className="hidden" onChange={handleFilePicked}
                  accept=".pdf,.doc,.docx,.txt,.md,.html" />
                <button type="button" onClick={() => fileInputRef.current?.click()}
                  disabled={sending || uploading}
                  title="Upload a document to the HR knowledge base"
                  className="h-[38px] w-[38px] shrink-0 rounded-lg flex items-center justify-center text-white/60 hover:text-violet-300 hover:bg-white/[0.05] border border-white/10 transition disabled:opacity-40">
                  <Paperclip className="h-4 w-4" />
                </button>
                <textarea
                  ref={inputRef}
                  data-tour-hrfc="input"
                  value={input}
                  onChange={handleInputChange}
                  onKeyDown={handleInputKeyDown}
                  placeholder="Ask an HR question or type / for commands…"
                  rows={1}
                  disabled={sending || uploading}
                  className="flex-1 resize-none rounded-lg border border-white/10 bg-[#0a0a0f] text-white text-sm px-3 py-2 placeholder:text-white/30 focus:outline-none focus:ring-1 focus:ring-violet-400/60 min-h-[38px] max-h-[110px]"
                />
                <button
                  type="button" data-tour-hrfc="send" onClick={send}
                  disabled={sending || uploading || !input.trim()}
                  className="h-[38px] w-[38px] shrink-0 rounded-lg flex items-center justify-center text-white disabled:opacity-40 disabled:cursor-not-allowed transition-transform active:scale-95"
                  style={{ background: 'linear-gradient(135deg, #8b5cf6 0%, #a78bfa 100%)' }}
                >
                  {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </button>
                {hintsEnabled && <div className="pb-1.5"><InfoHint {...HR_HINTS.hrFcSend} /></div>}
              </div>
            </div>
          )}
        </div>,
        document.body
      )}

      {/* Guided tour */}
      <FrontlineTutorial
        open={tourOpen}
        onClose={() => setTourOpen(false)}
        steps={HR_FLOATING_CHAT_TOUR.steps}
        storageKey={HR_FLOATING_CHAT_TOUR.key}
      />
    </>
  );
};

export default HRFloatingChat;
