import React, { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import {
  MessageCircle, X, Send, Loader2, Sparkles, GraduationCap,
  History, Trash2, Paperclip, Plus, Slash, Target, MessageSquare,
} from 'lucide-react';
import InfoHint, { useHints } from '../frontline/InfoHint';
import FrontlineTutorial, { hasSeenTutorial, resetTutorial } from '../frontline/FrontlineTutorial';
import { PM_FLOATING_CHAT_TOUR, PM_HINTS } from './pmTutorialSteps';
import {
  listPMChatHistory,
  savePMChatConversation,
  deletePMChatConversation,
  listPMRecentlyViewed,
} from './pmLocalStore';
import pmAgentService from '@/services/pmAgentService';
import { useToast } from '@/components/ui/use-toast';
import { useDraggableResizable, ContextIndicator, ResizeCorner, MobileSheetHandle } from '../frontline/chatShellUtils';

const PM_LAST_MODE_KEY = 'pm_fc_last_mode_v1';

// Two "modes" — the same UI drives both, backed by different service methods
// and different localStorage histories.
const MODES = {
  pilot: {
    label: 'Project Pilot',
    icon: Target,
    call:  (q, history) => pmAgentService.projectPilot(q, null, history),
    placeholder:  "Create a task, update a project, generate subtasks…",
    empty:        "Ask the Pilot to take an action — create a project, add a task, generate subtasks, update statuses, upload requirements. It does the doing.",
    samples: [
      'Create a task "Design landing page" in the Marketing project',
      'Generate subtasks for the API integration task',
      'Mark all tasks in Q1 launch as In Progress',
    ],
  },
  qa: {
    label: 'Knowledge Q&A',
    icon: MessageSquare,
    call: (q, history) => pmAgentService.knowledgeQA(q, null, history),
    placeholder:  "Ask a question about your projects, tasks, or team…",
    empty:        "Ask the Q&A agent a question about your project data. It answers with citations from the actual projects, tasks, and team activity.",
    samples: [
      'Which projects are behind schedule?',
      'How many tasks are blocked right now?',
      'Break down open tasks by assignee',
    ],
  },
};

const SLASH_COMMANDS = [
  { key: '/help',   label: '/help',   hint: '',              description: 'Show every slash command available in PM Quick Chat.', icon: Slash },
  { key: '/pilot',  label: '/pilot',  hint: '',              description: 'Switch to Project Pilot mode — actions and task creation.', icon: Target },
  { key: '/qa',     label: '/qa',     hint: '',              description: 'Switch to Knowledge Q&A mode — data questions and citations.', icon: MessageSquare },
  { key: '/new',    label: '/new',    hint: '',              description: 'Start a fresh conversation in the current mode.', icon: Plus },
  { key: '/clear',  label: '/clear',  hint: '',              description: 'Clear the current chat without saving to history.', icon: Trash2 },
  { key: '/upload', label: '/upload', hint: '',              description: 'Upload a requirements / spec file to the Pilot.', icon: Paperclip },
];

function newConversationId() {
  return `pmfc_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

const PMFloatingChat = () => {
  const { enabled: hintsEnabled } = useHints();
  const { toast } = useToast();

  const [open, setOpen] = useState(false);
  // Preserve the last-used mode across sessions
  const [mode, setMode] = useState(() => {
    try {
      const raw = localStorage.getItem(PM_LAST_MODE_KEY);
      return raw === 'qa' || raw === 'pilot' ? raw : 'pilot';
    } catch (_) { return 'pilot'; }
  });
  useEffect(() => {
    try { localStorage.setItem(PM_LAST_MODE_KEY, mode); } catch (_) { /* ignore */ }
  }, [mode]);
  const [showHistory, setShowHistory] = useState(false);

  // Separate conversation state per mode. Keeps the two chats independent.
  const [pilotConv, setPilotConv] = useState({ id: newConversationId(), messages: [] });
  const [qaConv,    setQaConv]    = useState({ id: newConversationId(), messages: [] });

  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);

  // Slash-menu state
  const [slashOpen, setSlashOpen] = useState(false);
  const [slashFilter, setSlashFilter] = useState('');
  const [slashActive, setSlashActive] = useState(0);

  // Tour state
  const [tourOpen, setTourOpen] = useState(false);

  // Stores — refresh whenever mode changes or chat is opened
  const [history, setHistory] = useState(() => listPMChatHistory('pilot'));
  const { containerStyle: geomStyle, dragHandleProps, resizeHandleProps } = useDraggableResizable('pm_fc', { defaultWidth: 440, defaultHeight: 600 });
  const [recents, setRecents] = useState(() => listPMRecentlyViewed());

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const fileInputRef = useRef(null);

  const refreshHistory = () => setHistory(listPMChatHistory(mode));
  const refreshRecents = () => setRecents(listPMRecentlyViewed());

  // ---- Effects ---------------------------------------------------------

  useEffect(() => { if (open) { refreshHistory(); refreshRecents(); } }, [open, mode]);

  const currentConv = mode === 'pilot' ? pilotConv : qaConv;
  const setCurrentConv = mode === 'pilot' ? setPilotConv : setQaConv;

  // Persist current conversation whenever it changes
  useEffect(() => {
    if (!currentConv.messages.length) return;
    const firstUser = currentConv.messages.find((m) => m.role === 'user');
    const title = (firstUser?.content || 'Untitled').slice(0, 60);
    savePMChatConversation(mode, {
      id: currentConv.id,
      title,
      messages: currentConv.messages,
      updated_at: Date.now(),
    });
    refreshHistory();
  }, [currentConv.messages, currentConv.id, mode]);

  // Global Ctrl/Cmd+K shortcut
  useEffect(() => {
    const onKey = (e) => {
      const isK = (e.key === 'k' || e.key === 'K');
      if (isK && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Auto-launch tour on first open; otherwise focus input
  useEffect(() => {
    if (!open) return;
    if (!hasSeenTutorial(PM_FLOATING_CHAT_TOUR.key)) {
      const t = setTimeout(() => setTourOpen(true), 500);
      return () => clearTimeout(t);
    }
    const f = setTimeout(() => inputRef.current?.focus(), 250);
    return () => clearTimeout(f);
  }, [open]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [currentConv.messages, sending, uploading]);

  // ---- Helpers ---------------------------------------------------------

  const pushMessage = (msg) => {
    setCurrentConv((c) => ({ ...c, messages: [...c.messages, msg] }));
  };

  const startNewConversation = () => {
    setCurrentConv({ id: newConversationId(), messages: [] });
    setInput('');
    setShowHistory(false);
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  const clearCurrentConversation = () => {
    deletePMChatConversation(mode, currentConv.id);
    setCurrentConv({ id: newConversationId(), messages: [] });
    setInput('');
    refreshHistory();
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  const openHistoryEntry = (entry) => {
    setCurrentConv({ id: entry.id, messages: entry.messages || [] });
    setShowHistory(false);
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  const removeHistoryEntry = (id) => { deletePMChatConversation(mode, id); refreshHistory(); };

  const switchMode = (nextMode) => {
    if (nextMode === mode) return;
    setMode(nextMode);
    setInput('');
    setShowHistory(false);
    setTimeout(() => inputRef.current?.focus(), 50);
  };

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
    } else {
      setSlashOpen(false);
    }
  };

  const runSlashCommand = async (raw) => {
    const [rawCmd] = raw.trim().split(/\s+/);
    const cmd = rawCmd.toLowerCase();

    if (cmd === '/help') {
      pushMessage({
        role: 'assistant',
        content: `Available slash commands:\n${SLASH_COMMANDS.map((c) => `${c.label}${c.hint ? ' ' + c.hint.trim() : ''} — ${c.description}`).join('\n')}`,
        system: true,
      });
      return true;
    }
    if (cmd === '/pilot')  { switchMode('pilot'); return true; }
    if (cmd === '/qa')     { switchMode('qa');    return true; }
    if (cmd === '/new')    { startNewConversation();     return true; }
    if (cmd === '/clear')  { clearCurrentConversation(); return true; }
    if (cmd === '/upload') { fileInputRef.current?.click(); return true; }
    return false;
  };

  // ---- Send flow -------------------------------------------------------

  const send = async () => {
    const q = input.trim();
    if (!q || sending || uploading) return;

    if (q.startsWith('/')) {
      setInput('');
      setSlashOpen(false);
      const handled = await runSlashCommand(q);
      if (handled) return;
    }

    pushMessage({ role: 'user', content: q });
    setInput('');
    setSlashOpen(false);
    setSending(true);

    try {
      // Multi-turn context — last 6 messages
      const history = currentConv.messages.slice(-6).map((m) => ({ role: m.role, content: m.content }));
      const res = await MODES[mode].call(q, history);
      if (res && (res.status === 'success' || res.data)) {
        const data = res.data || res;
        pushMessage({
          role: 'assistant',
          content: data.answer || data.response || data.message || 'Done.',
          source: data.source || null,
          citations: data.citations || data.sources || [],
          mode,
        });
      } else {
        throw new Error((res && res.message) || 'Request failed');
      }
    } catch (e) {
      pushMessage({ role: 'assistant', content: `Error: ${e.message || 'Something went wrong.'}`, error: true });
    } finally {
      setSending(false);
    }
  };

  // ---- Upload flow -----------------------------------------------------

  const handleFilePicked = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    pushMessage({ role: 'user', content: `📎 Uploading: ${file.name} (${Math.round(file.size / 1024)} KB)` });
    setUploading(true);
    try {
      // Force Pilot mode for uploads — that's the agent that reads files.
      if (mode !== 'pilot') switchMode('pilot');
      const res = await pmAgentService.projectPilotFromFile(file, null, [], input.trim());
      if (res && (res.status === 'success' || res.data)) {
        const data = res.data || res;
        pushMessage({
          role: 'assistant',
          content: data.answer || data.response || `Ingested "${file.name}".`,
          system: true,
        });
        toast({ title: 'File processed', description: file.name });
      } else {
        throw new Error((res && res.message) || 'Upload failed');
      }
    } catch (err) {
      pushMessage({ role: 'assistant', content: `Upload failed: ${err.message || 'Unknown error'}`, error: true });
    } finally {
      setUploading(false);
    }
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

  const replayTour = () => { resetTutorial(PM_FLOATING_CHAT_TOUR.key); setTourOpen(true); };

  const relativeTime = (ts) => {
    if (!ts) return '';
    const diff = (Date.now() - ts) / 1000;
    if (diff < 60) return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  };

  const currentMode = MODES[mode];
  const ModeIcon = currentMode.icon;

  return (
    <>
      {/* Launcher */}
      {!open && createPortal(
        <div className="fixed bottom-6 right-6 z-[9990] flex items-end gap-2">
          {hintsEnabled && <div className="pb-2"><InfoHint {...PM_HINTS.pmFcLauncher} /></div>}
          <button
            type="button"
            onClick={() => setOpen(true)}
            data-tour-pmfc="launcher"
            title="Open PM Quick Chat (Ctrl+K)"
            aria-label="Open PM Quick Chat"
            className="relative h-14 w-14 rounded-full flex items-center justify-center text-white shadow-2xl hover:scale-110 active:scale-95 transition-transform"
            style={{
              background: 'linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%)',
              boxShadow: '0 12px 32px 0 rgba(59, 130, 246, 0.55), 0 0 0 1px rgba(255,255,255,0.08) inset',
            }}
          >
            <span aria-hidden="true" className="absolute inset-0 rounded-full"
              style={{ background: 'rgba(59, 130, 246, 0.55)', animation: 'pmfcPing 2.2s cubic-bezier(0,0,0.2,1) infinite' }} />
            <span aria-hidden="true" className="absolute inset-1.5 rounded-full"
              style={{ background: 'linear-gradient(135deg, #22d3ee 0%, #60a5fa 100%)', animation: 'pmfcBlink 1.6s ease-in-out infinite' }} />
            <MessageCircle className="h-6 w-6 relative z-10 drop-shadow" />
            <span className="absolute -top-1 -right-1 z-20 rounded-md bg-black/70 text-white text-[9px] font-bold px-1.5 py-0.5 border border-white/15">
              Ctrl+K
            </span>
          </button>

          <style>{`
            @keyframes pmfcPing {
              0%   { transform: scale(1);   opacity: 0.75; }
              75%  { transform: scale(1.9); opacity: 0; }
              100% { transform: scale(1.9); opacity: 0; }
            }
            @keyframes pmfcBlink {
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
          className="fixed z-[9990] rounded-2xl border border-[#1e3a5f] bg-[#0e0e14] shadow-2xl flex flex-col overflow-hidden"
          style={geomStyle}
        >
          <ResizeCorner handleProps={resizeHandleProps} />
          <MobileSheetHandle />
          {/* Header — also acts as the drag handle on desktop */}
          <div
            data-tour-pmfc="header"
            {...dragHandleProps}
            className="flex items-center justify-between px-3 py-2.5 border-b border-white/10 select-none"
            style={{ ...dragHandleProps.style, background: 'linear-gradient(90deg, #06b6d4 0%, #3b82f6 100%)' }}
          >
            <div className="flex items-center gap-2 min-w-0">
              <Sparkles className="h-4 w-4 text-white shrink-0" />
              <div className="min-w-0">
                <div className="text-sm font-semibold text-white leading-tight">PM Quick Chat</div>
                <div className="text-[10px] text-white/80 leading-tight truncate">
                  {currentMode.label} · type / for commands
                </div>
              </div>
              {hintsEnabled && <InfoHint {...PM_HINTS.pmFcHeader} />}
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <button type="button" onClick={() => setShowHistory((v) => !v)}
                title={showHistory ? 'Back to chat' : `History (${history.length})`}
                className={`p-1 rounded transition text-white relative ${showHistory ? 'bg-white/25' : 'hover:bg-white/25'}`}>
                <History className="h-4 w-4" />
                {history.length > 0 && !showHistory && (
                  <span className="absolute -top-0.5 -right-0.5 text-[8px] font-bold bg-white text-cyan-600 rounded-full h-3.5 w-3.5 flex items-center justify-center">
                    {Math.min(history.length, 9)}
                  </span>
                )}
              </button>
              <button type="button" onClick={startNewConversation} title="Start new chat"
                className="p-1 rounded hover:bg-white/25 text-white transition">
                <Plus className="h-4 w-4" />
              </button>
              <button type="button" onClick={replayTour} title="Take a tour of PM Quick Chat"
                className="p-1 rounded hover:bg-white/25 text-white transition">
                <GraduationCap className="h-4 w-4" />
              </button>
              <button type="button" onClick={() => setOpen(false)} title="Close (Ctrl+K)"
                className="p-1 rounded hover:bg-white/25 text-white transition">
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Mode switcher */}
          <div className="flex items-center gap-2 px-3 py-2 border-b border-white/10 bg-[#0a0a0f]">
            <div data-tour-pmfc="mode-switch" className="flex gap-1 rounded-lg border border-white/10 p-0.5 flex-1">
              {Object.entries(MODES).map(([key, m]) => {
                const Icon = m.icon;
                const active = key === mode;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => switchMode(key)}
                    className={`flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 text-xs font-semibold rounded-md transition ${
                      active
                        ? 'text-white'
                        : 'text-white/50 hover:text-white/80 hover:bg-white/[0.04]'
                    }`}
                    style={active ? { background: 'linear-gradient(90deg, #06b6d4 0%, #3b82f6 100%)' } : {}}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {m.label}
                  </button>
                );
              })}
            </div>
            {hintsEnabled && <InfoHint {...PM_HINTS.pmFcModeSwitch} />}
          </div>

          {/* Body */}
          {showHistory ? (
            <div className="flex-1 overflow-y-auto p-3 space-y-1.5" style={{ background: '#0a0a0f' }}>
              <div className="flex items-center justify-between mb-2">
                <p className="text-[10px] uppercase tracking-wider text-white/40 font-semibold">
                  {currentMode.label} · Recent conversations
                </p>
                <span className="text-[10px] text-white/40">{history.length} saved</span>
              </div>
              {history.length === 0 ? (
                <p className="text-sm text-white/50 text-center py-8">No saved conversations yet.</p>
              ) : history.map((h) => (
                <div key={h.id}
                  className={`group flex items-center gap-2 px-2 py-2 rounded-lg cursor-pointer transition
                    ${h.id === currentConv.id ? 'bg-cyan-500/10 border border-cyan-400/30' : 'hover:bg-white/[0.04] border border-transparent'}`}
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
            <div data-tour-pmfc="messages" className="flex-1 overflow-y-auto p-3 space-y-2.5" style={{ background: '#0a0a0f' }}>
              {currentConv.messages.length === 0 ? (
                <div className="text-white/60">
                  <div className="text-center py-4">
                    <div className="h-10 w-10 mx-auto mb-2 rounded-full bg-cyan-500/10 border border-cyan-400/30 flex items-center justify-center">
                      <ModeIcon className="h-5 w-5 text-cyan-300" />
                    </div>
                    <p className="text-sm px-2">{currentMode.empty}</p>
                    {hintsEnabled && <div className="mt-2 flex justify-center"><InfoHint {...PM_HINTS.pmFcMessages} /></div>}
                  </div>

                  {recents.length > 0 && (
                    <div className="mt-3 mb-4">
                      <p className="text-[10px] uppercase tracking-wider text-white/40 font-semibold mb-1.5">Recently viewed</p>
                      <div className="space-y-1">
                        {recents.map((r) => (
                          <button key={`${r.kind}-${r.id}`} type="button"
                            onClick={() => {
                              setInput(mode === 'pilot'
                                ? `Show me ${r.kind} "${r.title}"`
                                : `Tell me about ${r.kind} "${r.title}"`);
                              inputRef.current?.focus();
                            }}
                            className="w-full flex items-center gap-2 text-left px-2 py-1.5 rounded hover:bg-white/[0.05] transition group">
                            <Target className="h-3.5 w-3.5 text-white/50 shrink-0" />
                            <span className="text-xs text-white/70 truncate group-hover:text-white/90">
                              {r.kind}: {r.title}
                            </span>
                            <span className="text-[10px] text-white/30 ml-auto shrink-0">{relativeTime(r.at)}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="mt-3">
                    <p className="text-[10px] uppercase tracking-wider text-white/40 font-semibold mb-1">Try one</p>
                    <div className="space-y-1">
                      {(() => {
                        const dyn = [];
                        (recents || []).slice(0, 2).forEach((r) => {
                          if (mode === 'pilot') {
                            if (r.kind === 'project') dyn.push(`Add a task to project "${r.title}"`);
                            else if (r.kind === 'task') dyn.push(`Update the status of task "${r.title}" to In Progress`);
                          } else {
                            if (r.kind === 'project') dyn.push(`How is project "${r.title}" doing?`);
                            else if (r.kind === 'task') dyn.push(`What's blocking task "${r.title}"?`);
                            else if (r.kind === 'meeting') dyn.push(`Summarize meeting "${r.title}"`);
                          }
                        });
                        const rot = currentMode.samples[Math.floor((Date.now() / 60000) % currentMode.samples.length)];
                        const staticPool = currentMode.samples.filter((s) => s !== rot).slice(0, 2);
                        const shown = [...dyn, rot, ...staticPool].slice(0, 3);
                        return shown.map((sample) => (
                          <button key={sample} type="button"
                            onClick={() => { setInput(sample); inputRef.current?.focus(); }}
                            className="block w-full text-left text-xs text-cyan-300/80 hover:text-cyan-200 hover:bg-white/[0.04] rounded px-2 py-1 transition">
                            → {sample}
                          </button>
                        ));
                      })()}
                    </div>
                  </div>
                </div>
              ) : currentConv.messages.map((m, i) => (
                <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                      m.role === 'user'
                        ? 'bg-cyan-500/25 text-white border border-cyan-400/30'
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
                  </div>
                </div>
              ))}
              {(sending || uploading) && (
                <div className="flex justify-start">
                  <div className="bg-white/[0.06] border border-white/10 rounded-lg px-3 py-2 flex items-center gap-2">
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-white/60" />
                    <span className="text-xs text-white/60">
                      {uploading ? 'Processing file…' : mode === 'pilot' ? 'Pilot working…' : 'Searching project data…'}
                    </span>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}

          {/* Input row */}
          {!showHistory && (
            <div className="border-t border-white/10 relative" style={{ background: '#0e0e14' }}>
              {currentConv.messages.length >= 2 && (
                <div className="px-3 pt-2">
                  <ContextIndicator count={Math.min(currentConv.messages.length, 6)} />
                </div>
              )}
              {slashOpen && filteredCommands.length > 0 && (
                <div className="absolute bottom-full left-2 right-2 mb-2 rounded-lg border border-[#1e3a5f] bg-[#0a1929] shadow-2xl overflow-hidden">
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
                            ${i === slashActive ? 'bg-cyan-500/10' : 'hover:bg-white/[0.03]'}`}>
                          <Icon className="h-4 w-4 shrink-0 text-cyan-300 mt-0.5" />
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
                {hintsEnabled && <div className="pb-1.5"><InfoHint {...PM_HINTS.pmFcInput} /></div>}
                <input ref={fileInputRef} type="file" className="hidden" onChange={handleFilePicked}
                  accept=".pdf,.doc,.docx,.txt,.md,.html" />
                <button type="button" onClick={() => fileInputRef.current?.click()}
                  disabled={sending || uploading}
                  title="Upload requirements — sent to Project Pilot"
                  className="h-[38px] w-[38px] shrink-0 rounded-lg flex items-center justify-center text-white/60 hover:text-cyan-300 hover:bg-white/[0.05] border border-white/10 transition disabled:opacity-40">
                  <Paperclip className="h-4 w-4" />
                </button>
                <textarea
                  ref={inputRef}
                  data-tour-pmfc="input"
                  value={input}
                  onChange={handleInputChange}
                  onKeyDown={handleInputKeyDown}
                  placeholder={currentMode.placeholder}
                  rows={1}
                  disabled={sending || uploading}
                  className="flex-1 resize-none rounded-lg border border-white/10 bg-[#0a0a0f] text-white text-sm px-3 py-2 placeholder:text-white/30 focus:outline-none focus:ring-1 focus:ring-cyan-400/60 min-h-[38px] max-h-[110px]"
                />
                <button
                  type="button" data-tour-pmfc="send" onClick={send}
                  disabled={sending || uploading || !input.trim()}
                  className="h-[38px] w-[38px] shrink-0 rounded-lg flex items-center justify-center text-white disabled:opacity-40 disabled:cursor-not-allowed transition-transform active:scale-95"
                  style={{ background: 'linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%)' }}
                >
                  {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </button>
                {hintsEnabled && <div className="pb-1.5"><InfoHint {...PM_HINTS.pmFcSend} /></div>}
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
        steps={PM_FLOATING_CHAT_TOUR.steps}
        storageKey={PM_FLOATING_CHAT_TOUR.key}
      />
    </>
  );
};

export default PMFloatingChat;
