import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/components/ui/use-toast';
import {
  Loader2, Send, MessageSquare, Plus, Trash2, Bot, Search,
  ChevronsLeft, ChevronsRight, FileText, Pencil, Check, X,
} from 'lucide-react';
import operationsService from '@/services/operationsAgentService';

const ACCENT = '#f59e0b'; // amber / operations accent
const ACCENT_SOFT = 'rgba(245,158,11,0.12)';
const ACCENT_BORDER = 'rgba(245,158,11,0.28)';

// ──────────────────────────────────────────────
// Lightweight markdown renderer tuned for the operations assistant.
// Supports: headings (## / ###), bold, lists (nested), tables, hr, paragraphs, code spans.
// Kept pure (no dangerouslySetInnerHTML of untrusted HTML — content is escaped before formatting).
// ──────────────────────────────────────────────
function markdownToHtml(md) {
  if (!md || typeof md !== 'string') return '';
  const escape = (s) => String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  const inline = (s) => {
    let out = escape(s);
    // inline code
    out = out.replace(/`([^`]+)`/g, '<code class="px-1.5 py-0.5 rounded bg-white/10 text-amber-200 text-[0.85em] font-mono">$1</code>');
    // bold
    out = out.replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold text-amber-200">$1</strong>');
    // italics (not after bold-closing)
    out = out.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em class="italic text-white/85">$2</em>');
    return out;
  };

  const getIndent = (line) => {
    const m = line.match(/^(\s*)(?:[-*•]|\d+\.)\s+/);
    if (!m) return -1;
    return Math.floor(m[1].length / 2);
  };

  const lines = md.replace(/\r\n/g, '\n').split('\n');
  const out = [];
  let listDepth = -1;

  const closeLists = (target) => {
    while (listDepth > target) {
      out.push('</ul>');
      listDepth--;
    }
  };

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const t = line.trim();

    // Table
    if (t.startsWith('|') && t.endsWith('|')) {
      closeLists(-1);
      const rows = [];
      let j = i;
      while (j < lines.length && lines[j].trim().startsWith('|')) {
        const cells = lines[j].trim().split('|').map((c) => c.trim()).filter(Boolean);
        if (cells.length && cells.every((c) => /^[-:\s]+$/.test(c))) { j++; continue; }
        rows.push(cells);
        j++;
      }
      i = j;
      if (rows.length) {
        out.push('<div class="my-3 overflow-x-auto rounded-lg border border-white/10">');
        out.push('<table class="w-full text-sm"><thead><tr class="bg-amber-500/10">');
        rows[0].forEach((c) => out.push(`<th class="px-3 py-2 text-left font-semibold text-amber-300">${inline(c)}</th>`));
        out.push('</tr></thead><tbody>');
        rows.slice(1).forEach((r, idx) => {
          out.push(`<tr class="${idx % 2 === 0 ? 'bg-white/[0.02]' : ''} hover:bg-white/[0.04] transition-colors">`);
          r.forEach((c) => out.push(`<td class="px-3 py-2 border-t border-white/5 text-white/85">${inline(c)}</td>`));
          out.push('</tr>');
        });
        out.push('</tbody></table></div>');
      }
      continue;
    }

    if (/^---+$/.test(t)) {
      closeLists(-1);
      out.push('<hr class="my-4 border-white/10" />');
      i++; continue;
    }

    if (/^#### /.test(t)) {
      closeLists(-1);
      out.push(`<h4 class="text-sm font-semibold mt-2 mb-1 text-amber-100/90">${inline(t.slice(5))}</h4>`);
      i++; continue;
    }
    if (/^### /.test(t)) {
      closeLists(-1);
      out.push(`<h3 class="text-sm font-bold mt-3 mb-1.5 text-amber-200">${inline(t.slice(4))}</h3>`);
      i++; continue;
    }
    if (/^## /.test(t)) {
      closeLists(-1);
      out.push(`<h2 class="text-base font-bold mt-4 mb-2 text-amber-300 border-b border-amber-500/20 pb-1.5">${inline(t.slice(3))}</h2>`);
      i++; continue;
    }
    if (/^# /.test(t)) {
      closeLists(-1);
      out.push(`<h1 class="text-lg font-bold mt-4 mb-2 text-amber-300">${inline(t.slice(2))}</h1>`);
      i++; continue;
    }

    const indent = getIndent(line);
    if (indent >= 0) {
      const content = t.replace(/^[\s]*(?:[-*•]|\d+\.)\s+/, '');
      if (indent > listDepth) {
        while (listDepth < indent) {
          const isTop = listDepth === -1;
          out.push(`<ul class="${isTop ? 'pl-4 my-2 space-y-1.5' : 'pl-5 mt-1 mb-1 space-y-1 border-l border-white/[0.06]'}">`);
          listDepth++;
        }
      } else if (indent < listDepth) {
        closeLists(indent);
      }
      const bullet = indent === 0 ? '•' : '›';
      const color = indent === 0 ? 'text-amber-400' : 'text-white/30';
      const textColor = indent === 0 ? 'text-white/90' : 'text-white/70';
      out.push(
        `<li class="text-sm leading-relaxed ${textColor} flex gap-2 ${indent === 0 ? 'pt-1' : ''}">` +
        `<span class="${color} shrink-0 mt-0.5">${bullet}</span>` +
        `<span>${inline(content)}</span></li>`,
      );
      i++; continue;
    }

    if (t === '' && listDepth >= 0) {
      // close only if next non-empty is not list
      let k = i + 1;
      while (k < lines.length && lines[k].trim() === '') k++;
      if (k >= lines.length || getIndent(lines[k]) < 0) closeLists(-1);
      i++; continue;
    }

    if (t === '') { i++; continue; }

    // Paragraph
    closeLists(-1);
    out.push(`<p class="text-sm leading-relaxed text-white/85 my-2">${inline(t)}</p>`);
    i++;
  }
  closeLists(-1);
  return out.join('\n');
}

// ──────────────────────────────────────────────
// Empty-state suggestion prompts
// ──────────────────────────────────────────────
const SUGGESTIONS = [
  'What documents do I have uploaded?',
  'Summarize the key risks across my latest documents',
  'List all invoices and their amounts',
  'What are the upcoming deadlines mentioned in my documents?',
  'Compare the main findings across my reports',
];

const KnowledgeQA = () => {
  const { toast } = useToast();
  const [chats, setChats] = useState([]);
  const [selectedChatId, setSelectedChatId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState('');
  const [sending, setSending] = useState(false);
  const [loadingChats, setLoadingChats] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [showSidebar, setShowSidebar] = useState(true);
  const [sidebarSearch, setSidebarSearch] = useState('');
  const [showSearch, setShowSearch] = useState(false);
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState('');

  const scrollRef = useRef(null);

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      if (scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    });
  }, []);

  // ── Load chats on mount
  const loadChats = useCallback(async () => {
    try {
      setLoadingChats(true);
      const res = await operationsService.listQaChats();
      if (res?.status === 'success') {
        setChats(res.chats || []);
      }
    } catch (err) {
      console.error('Load Q&A chats failed:', err);
    } finally {
      setLoadingChats(false);
    }
  }, []);

  useEffect(() => {
    loadChats();
  }, [loadChats]);

  // ── Load messages when a chat is selected
  useEffect(() => {
    if (!selectedChatId) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        setLoadingMessages(true);
        const res = await operationsService.getQaChat(selectedChatId);
        if (!cancelled && res?.status === 'success') {
          setMessages(res.chat?.messages || []);
          setTimeout(scrollToBottom, 50);
        }
      } catch (err) {
        console.error('Load chat failed:', err);
        if (!cancelled) {
          toast({
            title: 'Could not load chat',
            description: err?.message || 'Please try again.',
            variant: 'destructive',
          });
        }
      } finally {
        if (!cancelled) setLoadingMessages(false);
      }
    })();
    return () => { cancelled = true; };
  }, [selectedChatId, scrollToBottom, toast]);

  const filteredChats = useMemo(() => {
    const q = sidebarSearch.trim().toLowerCase();
    if (!q) return chats;
    return chats.filter((c) =>
      (c.title || '').toLowerCase().includes(q) ||
      (c.last_message || '').toLowerCase().includes(q),
    );
  }, [chats, sidebarSearch]);

  const handleNewChat = () => {
    setSelectedChatId(null);
    setMessages([]);
    setQuestion('');
  };

  const handleSelectChat = (id) => {
    if (id === selectedChatId) return;
    setSelectedChatId(id);
  };

  const handleSend = async (e) => {
    e?.preventDefault?.();
    const q = question.trim();
    if (!q) return;
    if (sending) return;

    // Optimistic user message
    const tempId = `tmp-${Date.now()}`;
    const userMsg = { id: tempId, role: 'user', content: q, created_at: new Date().toISOString() };
    setMessages((prev) => [...prev, userMsg]);
    setQuestion('');
    setSending(true);
    setTimeout(scrollToBottom, 10);

    try {
      const res = await operationsService.askQaQuestion(q, selectedChatId || null);
      if (res?.status === 'success' && res.message) {
        const assistantMsg = res.message;
        setMessages((prev) => [...prev, assistantMsg]);

        // If this was a new chat, pick up the new id + title and refresh sidebar list
        if (!selectedChatId && res.chat_id) {
          setSelectedChatId(res.chat_id);
        }
        // Refresh chat list to reflect new title / ordering
        loadChats();

        if (res.success === false && res.error) {
          toast({
            title: 'Partial response',
            description: res.error,
            variant: 'default',
          });
        }
      } else {
        throw new Error(res?.message || 'Failed to get a response');
      }
    } catch (err) {
      console.error('Ask question failed:', err);
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: 'assistant',
          content: `**Something went wrong.**\n\n${err?.message || 'Please try again in a moment.'}`,
          sources: [],
          created_at: new Date().toISOString(),
        },
      ]);
      toast({
        title: 'Error',
        description: err?.message || 'Something went wrong. Please try again.',
        variant: 'destructive',
      });
    } finally {
      setSending(false);
      setTimeout(scrollToBottom, 50);
    }
  };

  const handleDeleteChat = async (e, chatId) => {
    e.stopPropagation();
    if (!window.confirm('Delete this chat? This cannot be undone.')) return;
    try {
      const res = await operationsService.deleteQaChat(chatId);
      if (res?.status === 'success') {
        setChats((prev) => prev.filter((c) => c.id !== chatId));
        if (selectedChatId === chatId) {
          setSelectedChatId(null);
          setMessages([]);
        }
        toast({ title: 'Chat deleted' });
      } else {
        throw new Error(res?.message || 'Delete failed');
      }
    } catch (err) {
      toast({
        title: 'Error',
        description: err?.message || 'Could not delete chat',
        variant: 'destructive',
      });
    }
  };

  const startRename = (e, chat) => {
    e.stopPropagation();
    setRenamingId(chat.id);
    setRenameValue(chat.title || '');
  };

  const cancelRename = (e) => {
    e?.stopPropagation?.();
    setRenamingId(null);
    setRenameValue('');
  };

  const commitRename = async (e, chat) => {
    e?.stopPropagation?.();
    const newTitle = (renameValue || '').trim();
    if (!newTitle || newTitle === chat.title) {
      cancelRename();
      return;
    }
    try {
      const res = await operationsService.renameQaChat(chat.id, newTitle);
      if (res?.status === 'success') {
        setChats((prev) => prev.map((c) => (c.id === chat.id ? { ...c, title: newTitle } : c)));
        cancelRename();
      } else {
        throw new Error(res?.message || 'Rename failed');
      }
    } catch (err) {
      toast({
        title: 'Error',
        description: err?.message || 'Could not rename chat',
        variant: 'destructive',
      });
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const formatDate = (iso) => {
    try {
      const d = new Date(iso);
      const now = new Date();
      const same = d.toDateString() === now.toDateString();
      return same
        ? d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
        : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    } catch {
      return '';
    }
  };

  return (
    <div
      className="w-full rounded-2xl border border-amber-500/10 overflow-hidden shadow-[0_8px_40px_-12px_rgba(245,158,11,0.15)]"
      style={{
        background:
          'linear-gradient(135deg, #1a1333 0%, #1a1333 45%, rgba(64,40,10,0.55) 100%)',
      }}
    >
      <div className="flex w-full max-w-full relative" style={{ height: 'calc(100vh - 120px)', minHeight: 680 }}>
        {/* ── Sidebar ── */}
        <div
          className={`shrink-0 transition-all duration-300 ease-in-out border-r border-white/10 ${
            showSidebar ? 'w-72 opacity-100' : 'w-0 opacity-0 border-0'
          }`}
          style={{ minWidth: showSidebar ? '18rem' : 0, overflow: 'hidden' }}
        >
          <div className="w-72 h-full flex flex-col bg-black/30">
            <div className="px-3 pt-3 pb-2 border-b border-white/10 flex flex-col gap-2 shrink-0">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div
                    className="flex items-center justify-center w-8 h-8 rounded-lg"
                    style={{ backgroundColor: ACCENT_SOFT }}
                  >
                    <MessageSquare className="h-4 w-4" style={{ color: ACCENT }} />
                  </div>
                  <span className="text-sm font-semibold text-white/90">Conversations</span>
                </div>
                <button
                  onClick={() => setShowSidebar(false)}
                  title="Hide sidebar"
                  className="h-7 w-7 flex items-center justify-center rounded-md border border-white/10 hover:border-white/30 bg-black/20 hover:bg-white/5 transition-colors"
                >
                  <ChevronsLeft className="h-3.5 w-3.5 text-white/70" />
                </button>
              </div>

              <div className="flex items-center gap-2">
                <Button
                  onClick={handleNewChat}
                  size="sm"
                  className="flex-1 text-xs h-8"
                  style={{
                    backgroundColor: ACCENT,
                    color: '#1a0e00',
                    border: 'none',
                  }}
                >
                  <Plus className="h-3.5 w-3.5 mr-1" />
                  New chat
                </Button>
                <button
                  onClick={() => { setShowSearch((v) => !v); if (showSearch) setSidebarSearch(''); }}
                  title="Search chats"
                  className="h-8 w-8 flex items-center justify-center rounded-md border border-white/10 hover:border-white/30 bg-black/20 hover:bg-white/5 transition-colors"
                >
                  <Search className="h-3.5 w-3.5 text-white/70" />
                </button>
              </div>

              {showSearch && (
                <input
                  value={sidebarSearch}
                  onChange={(e) => setSidebarSearch(e.target.value)}
                  placeholder="Search conversations..."
                  className="w-full bg-black/30 border border-white/10 rounded-md px-2.5 py-1.5 text-xs text-white/90 placeholder-white/40 focus:outline-none focus:border-amber-500/40"
                  autoFocus
                />
              )}
            </div>

            <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1">
              {loadingChats ? (
                <div className="flex items-center justify-center h-24 text-white/50 text-sm">
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  Loading...
                </div>
              ) : filteredChats.length === 0 ? (
                <div className="text-center text-white/40 text-xs px-2 py-6">
                  {sidebarSearch ? 'No conversations match your search.' : 'No conversations yet. Ask your first question!'}
                </div>
              ) : (
                filteredChats.map((chat) => {
                  const isActive = chat.id === selectedChatId;
                  const isRenaming = renamingId === chat.id;
                  return (
                    <div
                      key={chat.id}
                      onClick={() => !isRenaming && handleSelectChat(chat.id)}
                      className={`group relative rounded-lg px-2.5 py-2 cursor-pointer transition-colors ${
                        isActive ? 'bg-amber-500/10 border border-amber-500/25' : 'hover:bg-white/[0.04] border border-transparent'
                      }`}
                    >
                      {isRenaming ? (
                        <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                          <input
                            value={renameValue}
                            onChange={(e) => setRenameValue(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') commitRename(e, chat);
                              if (e.key === 'Escape') cancelRename(e);
                            }}
                            className="flex-1 bg-black/40 border border-amber-500/40 rounded px-1.5 py-1 text-xs text-white/90 focus:outline-none"
                            autoFocus
                          />
                          <button
                            onClick={(e) => commitRename(e, chat)}
                            className="h-6 w-6 flex items-center justify-center rounded hover:bg-green-500/20"
                            title="Save"
                          >
                            <Check className="h-3 w-3 text-green-400" />
                          </button>
                          <button
                            onClick={cancelRename}
                            className="h-6 w-6 flex items-center justify-center rounded hover:bg-red-500/20"
                            title="Cancel"
                          >
                            <X className="h-3 w-3 text-red-400" />
                          </button>
                        </div>
                      ) : (
                        <>
                          <div className="flex items-start justify-between gap-2">
                            <div className="flex-1 min-w-0">
                              <div className="text-sm text-white/90 font-medium truncate">
                                {chat.title || 'Untitled chat'}
                              </div>
                              {chat.last_message && (
                                <div className="text-[11px] text-white/40 truncate mt-0.5">
                                  {chat.last_message}
                                </div>
                              )}
                              <div className="text-[10px] text-white/30 mt-0.5">
                                {formatDate(chat.updated_at)}
                                {typeof chat.message_count === 'number' && chat.message_count > 0 && (
                                  <span className="ml-2">· {chat.message_count} msg</span>
                                )}
                              </div>
                            </div>
                            <div className="opacity-0 group-hover:opacity-100 transition-opacity flex gap-0.5 shrink-0">
                              <button
                                onClick={(e) => startRename(e, chat)}
                                title="Rename"
                                className="h-6 w-6 flex items-center justify-center rounded hover:bg-white/10"
                              >
                                <Pencil className="h-3 w-3 text-white/60 hover:text-amber-300" />
                              </button>
                              <button
                                onClick={(e) => handleDeleteChat(e, chat.id)}
                                title="Delete"
                                className="h-6 w-6 flex items-center justify-center rounded hover:bg-red-500/20"
                              >
                                <Trash2 className="h-3 w-3 text-white/60 hover:text-red-400" />
                              </button>
                            </div>
                          </div>
                        </>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>

        {/* ── Main chat area ── */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Header */}
          <div className="px-4 py-3 border-b border-white/10 flex items-center gap-3 bg-black/20">
            {!showSidebar && (
              <button
                onClick={() => setShowSidebar(true)}
                title="Show sidebar"
                className="h-8 w-8 flex items-center justify-center rounded-md border border-white/10 hover:border-white/30 bg-black/30 hover:bg-white/5 transition-colors"
              >
                <ChevronsRight className="h-4 w-4 text-white/70" />
              </button>
            )}
            <div className="flex items-center gap-3 flex-1 min-w-0">
              <div
                className="flex items-center justify-center w-10 h-10 rounded-xl shrink-0"
                style={{ backgroundColor: ACCENT_SOFT, border: `1px solid ${ACCENT_BORDER}` }}
              >
                <Bot className="h-5 w-5" style={{ color: ACCENT }} />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-semibold text-white/95 truncate">
                  Operations Knowledge Assistant
                </div>
                <div className="text-xs text-white/50 truncate">
                  Ask questions about your documents — answers cite their sources.
                </div>
              </div>
            </div>
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6">
            {loadingMessages ? (
              <div className="flex items-center justify-center h-full text-white/50 text-sm">
                <Loader2 className="h-5 w-5 animate-spin mr-2" />
                Loading conversation...
              </div>
            ) : messages.length === 0 ? (
              <EmptyState onPick={(q) => setQuestion(q)} />
            ) : (
              <div className="max-w-4xl mx-auto space-y-5">
                {messages.map((m) => (
                  <Message key={m.id} message={m} />
                ))}
                {sending && (
                  <div className="flex items-start gap-3">
                    <div
                      className="flex items-center justify-center w-9 h-9 rounded-xl shrink-0"
                      style={{ backgroundColor: ACCENT_SOFT, border: `1px solid ${ACCENT_BORDER}` }}
                    >
                      <Bot className="h-4 w-4" style={{ color: ACCENT }} />
                    </div>
                    <div className="rounded-2xl px-4 py-3 bg-white/[0.04] border border-white/10">
                      <div className="flex items-center gap-2 text-white/65 text-sm">
                        <Loader2 className="h-4 w-4 animate-spin" style={{ color: ACCENT }} />
                        Searching your documents...
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Composer */}
          <div className="border-t border-white/10 px-6 py-4 bg-black/25">
            <form onSubmit={handleSend} className="max-w-4xl mx-auto">
              <div
                className="rounded-2xl border bg-black/50 overflow-hidden transition-all focus-within:border-amber-500/40 focus-within:shadow-[0_0_0_3px_rgba(245,158,11,0.08)]"
                style={{ borderColor: 'rgba(255,255,255,0.1)' }}
              >
                <Textarea
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask anything about your operations documents..."
                  rows={1}
                  disabled={sending}
                  className="w-full resize-none bg-transparent border-0 text-white/95 placeholder-white/45 text-[14px] leading-relaxed focus:outline-none focus-visible:ring-0 focus-visible:ring-offset-0 px-4 py-2.5 min-h-[44px] max-h-[180px]"
                />
                <div className="flex items-center justify-between px-4 py-2.5 border-t border-white/[0.06] bg-black/20">
                  <div className="text-[11px] text-white/45">
                    Press <kbd className="px-1.5 py-0.5 bg-white/10 rounded text-[10px] font-mono">Enter</kbd> to send,
                    {' '}
                    <kbd className="px-1.5 py-0.5 bg-white/10 rounded text-[10px] font-mono">Shift+Enter</kbd> for newline
                  </div>
                  <Button
                    type="submit"
                    size="sm"
                    disabled={!question.trim() || sending}
                    className="h-9 px-4 text-xs font-semibold disabled:opacity-40 transition-transform active:scale-95"
                    style={{
                      backgroundColor: ACCENT,
                      color: '#1a0e00',
                      border: 'none',
                    }}
                  >
                    {sending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <>
                        <Send className="h-3.5 w-3.5 mr-1.5" />
                        Send
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
};

// ──────────────────────────────────────────────
// Sub-components
// ──────────────────────────────────────────────

const EmptyState = ({ onPick }) => (
  <div className="max-w-2xl mx-auto flex flex-col items-center justify-center py-10 text-center">
    <div
      className="flex items-center justify-center w-14 h-14 rounded-2xl mb-4"
      style={{ backgroundColor: ACCENT_SOFT, border: `1px solid ${ACCENT_BORDER}` }}
    >
      <Bot className="h-7 w-7" style={{ color: ACCENT }} />
    </div>
    <h3 className="text-lg font-semibold text-white/95 mb-1">
      How can I help with your documents?
    </h3>
    <p className="text-sm text-white/55 mb-6">
      Ask about contracts, invoices, reports, policies — I'll answer with source citations.
    </p>
    <div className="grid sm:grid-cols-2 gap-2 w-full">
      {SUGGESTIONS.map((s) => (
        <button
          key={s}
          onClick={() => onPick(s)}
          className="text-left px-3 py-2.5 rounded-lg border border-white/10 bg-white/[0.02] hover:bg-white/[0.06] hover:border-amber-500/30 text-sm text-white/80 transition-colors"
        >
          {s}
        </button>
      ))}
    </div>
  </div>
);

const Message = ({ message }) => {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div
          className="max-w-[78%] rounded-2xl px-4 py-3 text-[14px] leading-relaxed"
          style={{
            backgroundColor: 'rgba(245,158,11,0.14)',
            border: `1px solid ${ACCENT_BORDER}`,
            color: 'rgba(255,255,255,0.96)',
          }}
        >
          <div className="whitespace-pre-wrap">{message.content}</div>
        </div>
      </div>
    );
  }

  // assistant
  const sources = Array.isArray(message.sources) ? message.sources : [];
  return (
    <div className="flex items-start gap-3">
      <div
        className="flex items-center justify-center w-9 h-9 rounded-xl shrink-0 mt-0.5"
        style={{ backgroundColor: ACCENT_SOFT, border: `1px solid ${ACCENT_BORDER}` }}
      >
        <Bot className="h-4 w-4" style={{ color: ACCENT }} />
      </div>
      <div className="flex-1 min-w-0 rounded-2xl px-5 py-4 bg-white/[0.04] border border-white/10">
        <div
          className="prose prose-invert max-w-none"
          dangerouslySetInnerHTML={{ __html: markdownToHtml(message.content || '') }}
        />
        {sources.length > 0 && (
          <div className="mt-3 pt-3 border-t border-white/10">
            <div className="flex items-center gap-1.5 mb-2">
              <FileText className="h-3 w-3 text-amber-300" />
              <span className="text-[11px] uppercase tracking-wider text-amber-300 font-semibold">
                Sources ({sources.length})
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {sources.map((s, i) => (
                <span
                  key={`${s.document_id || i}-${s.page || 0}-${i}`}
                  className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-amber-500/8 border border-amber-500/20 text-[11px] text-amber-100/90"
                >
                  <FileText className="h-2.5 w-2.5" />
                  <span className="max-w-[240px] truncate">{s.title || 'Document'}</span>
                  {s.page && <span className="text-amber-300/70">p.{s.page}</span>}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default KnowledgeQA;
