import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/components/ui/use-toast';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog';
import {
  Loader2, Send, MessageSquare, Plus, Trash2, Bot, Search,
  ChevronsLeft, ChevronsRight, FileText, Pencil, Check, X,
  HelpCircle, Upload, Sparkles, MessageSquareText, Quote, Lightbulb,
  Copy,
} from 'lucide-react';
import operationsService from '@/services/operationsAgentService';
import { ElapsedTimer } from '@/components/frontline/chatShellUtils';
import ConfirmDialog from '@/components/common/ConfirmDialog';

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
  const [sendStartedAt, setSendStartedAt] = useState(null);
  const [pendingDeleteChat, setPendingDeleteChat] = useState(null);
  const [deletingChat, setDeletingChat] = useState(false);
  const [loadingChats, setLoadingChats] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [showSidebar, setShowSidebar] = useState(true);
  const [sidebarSearch, setSidebarSearch] = useState('');
  const [showSearch, setShowSearch] = useState(false);
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState('');
  const [showOnboarding, setShowOnboarding] = useState(false);

  const scrollRef = useRef(null);
  // Ref to the most recent assistant answer, so we can scroll the user to the
  // START of a fresh answer (where it begins) instead of the container bottom
  // (its end) — the user wants to read from the top.
  const lastAnswerRef = useRef(null);

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      if (scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    });
  }, []);

  // Scroll so the top of the latest assistant answer sits near the top of the
  // viewport. Used when a new answer arrives so the user starts reading from the
  // beginning of the response, not scrolled past to its end.
  const scrollToAnswerTop = useCallback(() => {
    requestAnimationFrame(() => {
      if (lastAnswerRef.current) {
        lastAnswerRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
    setSendStartedAt(performance.now());
    setTimeout(scrollToBottom, 10);

    try {
      const res = await operationsService.askQaQuestion(q, selectedChatId || null);
      if (res?.status === 'success' && res.message) {
        // Keep timing on the message so the badge renders (nested in responseData
        // so it also survives a chat re-fetch).
        const assistantMsg = {
          ...res.message,
          responseData: {
            ...(res.message.responseData || {}),
            timing_ms: res.timing_ms || res.message.responseData?.timing_ms || {},
            cache_hit: res.cache_hit ?? res.message.responseData?.cache_hit ?? false,
          },
        };
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
      const isHardBlock = err?.status === 402 || err?.status === 403 || err?.data?.hard_block;
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: 'assistant',
          content: isHardBlock
            ? `**Generation blocked.**\n\n${err?.message || 'API key or token quota issue. Check your API Keys settings.'}`
            : `**Something went wrong.**\n\n${err?.message || 'Please try again in a moment.'}`,
          sources: [],
          created_at: new Date().toISOString(),
        },
      ]);
      toast({
        title: isHardBlock ? 'Generation blocked' : 'Error',
        description: isHardBlock
          ? (err?.message || 'API key or token quota issue. Check your API Keys settings.')
          : (err?.message || 'Something went wrong. Please try again.'),
        variant: 'destructive',
      });
    } finally {
      setSending(false);
      setSendStartedAt(null);
      // Land the user at the START of the new answer, not the container bottom.
      setTimeout(scrollToAnswerTop, 60);
    }
  };

  // Delete chat — opens the styled confirm modal (was window.confirm)
  const handleDeleteChat = (e, chat) => {
    e.stopPropagation();
    setPendingDeleteChat(chat);
  };

  const confirmDeleteChat = async () => {
    const chat = pendingDeleteChat;
    if (!chat) return;
    try {
      setDeletingChat(true);
      const res = await operationsService.deleteQaChat(chat.id);
      if (res?.status === 'success') {
        setChats((prev) => prev.filter((c) => c.id !== chat.id));
        if (selectedChatId === chat.id) {
          setSelectedChatId(null);
          setMessages([]);
        }
        setPendingDeleteChat(null);
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
    } finally {
      setDeletingChat(false);
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

  // ── Edit & resend the most recent question (ChatGPT-style, last turn only) ──
  const [editingId, setEditingId] = useState(null);
  const [editValue, setEditValue] = useState('');

  const startEdit = (msg) => {
    setEditingId(msg.id);
    setEditValue(msg.content || '');
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditValue('');
  };

  const submitEdit = async () => {
    const edited = (editValue || '').trim();
    if (!edited || sending) return;
    if (!selectedChatId) { cancelEdit(); return; }

    cancelEdit();
    setSending(true);
    setSendStartedAt(performance.now());

    // Optimistically drop the old last turn (trailing user msg + everything
    // after it) so the UI reflects the replace immediately.
    setMessages((prev) => {
      let cut = prev.length;
      for (let i = prev.length - 1; i >= 0; i -= 1) {
        if (prev[i].role === 'user') { cut = i; break; }
      }
      const trimmed = prev.slice(0, cut);
      return [
        ...trimmed,
        { id: `tmp-${Date.now()}`, role: 'user', content: edited, created_at: new Date().toISOString() },
      ];
    });
    setTimeout(scrollToBottom, 10);

    try {
      const res = await operationsService.replaceLastQaTurn(selectedChatId, edited);
      if (res?.status === 'success' && res.message) {
        const assistantMsg = {
          ...res.message,
          responseData: {
            ...(res.message.responseData || {}),
            timing_ms: res.timing_ms || res.message.responseData?.timing_ms || {},
            cache_hit: res.cache_hit ?? res.message.responseData?.cache_hit ?? false,
          },
        };
        setMessages((prev) => [...prev, assistantMsg]);
        loadChats();
      } else {
        throw new Error(res?.message || 'Failed to get a response');
      }
    } catch (err) {
      console.error('Edit & resend failed:', err);
      // Re-sync from the server so the UI matches the persisted state after a
      // failed replace (the old turn was never deleted server-side).
      try {
        const chatRes = await operationsService.getQaChat(selectedChatId);
        if (chatRes?.status === 'success') setMessages(chatRes.chat?.messages || []);
      } catch { /* leave optimistic state as-is */ }
      toast({
        title: 'Error',
        description: err?.message || 'Could not resend the edited question.',
        variant: 'destructive',
      });
    } finally {
      setSending(false);
      setSendStartedAt(null);
      setTimeout(scrollToAnswerTop, 60);
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
                  id="OPS-qa-hide-sidebar-btn"
                  data-testid="OPS-qa-hide-sidebar-btn"
                  onClick={() => setShowSidebar(false)}
                  title="Hide sidebar"
                  className="h-7 w-7 flex items-center justify-center rounded-md border border-white/10 hover:border-white/30 bg-black/20 hover:bg-white/5 transition-colors"
                >
                  <ChevronsLeft className="h-3.5 w-3.5 text-white/70" />
                </button>
              </div>

              <div className="flex items-center gap-2">
                <Button
                  id="OPS-qa-new-chat-btn"
                  data-testid="OPS-qa-new-chat-btn"
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
                  id="OPS-qa-search-toggle-btn"
                  data-testid="OPS-qa-search-toggle-btn"
                  onClick={() => { setShowSearch((v) => !v); if (showSearch) setSidebarSearch(''); }}
                  title="Search chats"
                  className="h-8 w-8 flex items-center justify-center rounded-md border border-white/10 hover:border-white/30 bg-black/20 hover:bg-white/5 transition-colors"
                >
                  <Search className="h-3.5 w-3.5 text-white/70" />
                </button>
              </div>

              {showSearch && (
                <input
                  id="OPS-qa-sidebar-search-input"
                  data-testid="OPS-qa-sidebar-search-input"
                  value={sidebarSearch}
                  onChange={(e) => setSidebarSearch(e.target.value)}
                  placeholder="Search conversations..."
                  className="w-full bg-black/30 border border-white/10 rounded-md px-2.5 py-1.5 text-xs text-white/90 placeholder-white/40 focus:outline-none focus:border-amber-500/40"
                  autoFocus
                />
              )}
            </div>

            <div
              id="OPS-qa-chat-list"
              data-testid="OPS-qa-chat-list"
              className="flex-1 overflow-y-auto px-2 py-2 space-y-1"
            >
              {loadingChats ? (
                <div
                  id="OPS-qa-chat-list-loading"
                  data-testid="OPS-qa-chat-list-loading"
                  className="flex items-center justify-center h-24 text-white/50 text-sm"
                >
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  Loading...
                </div>
              ) : filteredChats.length === 0 ? (
                <div
                  id="OPS-qa-chat-list-empty"
                  data-testid="OPS-qa-chat-list-empty"
                  className="text-center text-white/40 text-xs px-2 py-6"
                >
                  {sidebarSearch ? 'No conversations match your search.' : 'No conversations yet. Ask your first question!'}
                </div>
              ) : (
                filteredChats.map((chat) => {
                  const isActive = chat.id === selectedChatId;
                  const isRenaming = renamingId === chat.id;
                  return (
                    <div
                      key={chat.id}
                      id={`OPS-qa-chat-item-${chat.id}`}
                      data-testid={`OPS-qa-chat-item-${chat.id}`}
                      onClick={() => !isRenaming && handleSelectChat(chat.id)}
                      className={`group relative rounded-lg px-2.5 py-2 cursor-pointer transition-colors ${
                        isActive ? 'bg-amber-500/10 border border-amber-500/25' : 'hover:bg-white/[0.04] border border-transparent'
                      }`}
                    >
                      {isRenaming ? (
                        <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                          <input
                            id={`OPS-qa-rename-input-${chat.id}`}
                            data-testid={`OPS-qa-rename-input-${chat.id}`}
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
                            id={`OPS-qa-rename-save-btn-${chat.id}`}
                            data-testid={`OPS-qa-rename-save-btn-${chat.id}`}
                            onClick={(e) => commitRename(e, chat)}
                            className="h-6 w-6 flex items-center justify-center rounded hover:bg-green-500/20"
                            title="Save"
                          >
                            <Check className="h-3 w-3 text-green-400" />
                          </button>
                          <button
                            id={`OPS-qa-rename-cancel-btn-${chat.id}`}
                            data-testid={`OPS-qa-rename-cancel-btn-${chat.id}`}
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
                                id={`OPS-qa-chat-rename-btn-${chat.id}`}
                                data-testid={`OPS-qa-chat-rename-btn-${chat.id}`}
                                onClick={(e) => startRename(e, chat)}
                                title="Rename"
                                className="h-6 w-6 flex items-center justify-center rounded hover:bg-white/10"
                              >
                                <Pencil className="h-3 w-3 text-white/60 hover:text-amber-300" />
                              </button>
                              <button
                                id={`OPS-qa-chat-delete-btn-${chat.id}`}
                                data-testid={`OPS-qa-chat-delete-btn-${chat.id}`}
                                onClick={(e) => handleDeleteChat(e, chat)}
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
                id="OPS-qa-show-sidebar-btn"
                data-testid="OPS-qa-show-sidebar-btn"
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
            {/* Onboarding / how-it-works */}
            <button
              id="OPS-qa-how-it-works-btn"
              data-testid="OPS-qa-how-it-works-btn"
              onClick={() => setShowOnboarding(true)}
              title="How this page works"
              className="shrink-0 inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors"
              style={{ backgroundColor: ACCENT_SOFT, border: `1px solid ${ACCENT_BORDER}`, color: ACCENT }}
            >
              <HelpCircle className="h-4 w-4" />
              <span className="hidden sm:inline">How it works</span>
            </button>
          </div>

          {/* Messages */}
          <div
            ref={scrollRef}
            id="OPS-qa-messages-scroll"
            data-testid="OPS-qa-messages-scroll"
            className="flex-1 overflow-y-auto px-6 py-6"
          >
            {loadingMessages ? (
              <div
                id="OPS-qa-messages-loading"
                data-testid="OPS-qa-messages-loading"
                className="flex items-center justify-center h-full text-white/50 text-sm"
              >
                <Loader2 className="h-5 w-5 animate-spin mr-2" />
                Loading conversation...
              </div>
            ) : messages.length === 0 ? (
              <EmptyState onPick={(q) => setQuestion(q)} />
            ) : (
              <div
                id="OPS-qa-message-list"
                data-testid="OPS-qa-message-list"
                className="max-w-4xl mx-auto space-y-5"
              >
                {(() => {
                  // Index of the last user message (only that one is editable)
                  // and the last assistant message (target for scroll-to-top).
                  let lastUserIdx = -1;
                  let lastAssistantIdx = -1;
                  messages.forEach((m, idx) => {
                    if (m.role === 'user') lastUserIdx = idx;
                    else if (m.role === 'assistant') lastAssistantIdx = idx;
                  });
                  return messages.map((m, idx) => (
                    <Message
                      key={m.id}
                      index={idx}
                      message={m}
                      isLastUser={idx === lastUserIdx}
                      answerRef={idx === lastAssistantIdx ? lastAnswerRef : null}
                      isEditing={editingId === m.id}
                      editValue={editValue}
                      onEditChange={setEditValue}
                      onStartEdit={() => startEdit(m)}
                      onCancelEdit={cancelEdit}
                      onSubmitEdit={submitEdit}
                      editDisabled={sending}
                    />
                  ));
                })()}
                {sending && (
                  <div
                    id="OPS-qa-thinking-indicator"
                    data-testid="OPS-qa-thinking-indicator"
                    className="flex items-start gap-3"
                  >
                    <div
                      className="flex items-center justify-center w-9 h-9 rounded-xl shrink-0"
                      style={{ backgroundColor: ACCENT_SOFT, border: `1px solid ${ACCENT_BORDER}` }}
                    >
                      <Bot className="h-4 w-4" style={{ color: ACCENT }} />
                    </div>
                    <div className="rounded-2xl px-4 py-3 bg-white/[0.04] border border-white/10">
                      <div className="flex items-center gap-2 text-white/65 text-sm">
                        <Loader2 className="h-4 w-4 animate-spin" style={{ color: ACCENT }} />
                        Searching your documents…
                        {sendStartedAt != null && (
                          <ElapsedTimer since={sendStartedAt} className="text-xs font-mono text-white/40" />
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Composer */}
          <div className="border-t border-white/10 px-6 py-4 bg-black/25">
            <form id="OPS-qa-composer-form" data-testid="OPS-qa-composer-form" onSubmit={handleSend} className="max-w-4xl mx-auto">
              <div
                className="rounded-2xl border bg-black/50 overflow-hidden transition-all focus-within:border-amber-500/40 focus-within:shadow-[0_0_0_3px_rgba(245,158,11,0.08)]"
                style={{ borderColor: 'rgba(255,255,255,0.1)' }}
              >
                <Textarea
                  id="OPS-qa-question-input"
                  data-testid="OPS-qa-question-input"
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
                    id="OPS-qa-send-btn"
                    data-testid="OPS-qa-send-btn"
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

      {/* ── Onboarding / How-it-works modal ── */}
      <Dialog open={showOnboarding} onOpenChange={setShowOnboarding}>
        <DialogContent id="OPS-qa-onboarding-dialog" data-testid="OPS-qa-onboarding-dialog" className="max-w-lg max-h-[85vh] overflow-y-auto border-white/10 text-white" style={{ background: '#100a20' }}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-white">
              <span className="flex items-center justify-center w-8 h-8 rounded-lg" style={{ backgroundColor: ACCENT_SOFT, border: `1px solid ${ACCENT_BORDER}` }}>
                <Sparkles className="h-4 w-4" style={{ color: ACCENT }} />
              </span>
              Knowledge Q&amp;A — how it works
            </DialogTitle>
            <DialogDescription className="text-white/60">
              Chat with an AI that answers using the documents your team has uploaded.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 mt-1">
            {[
              {
                icon: Upload,
                title: '1. Upload your documents first',
                desc: 'Go to the Documents tab and upload files (PDF, Word, etc.). The assistant can only answer from what you have uploaded.',
              },
              {
                icon: MessageSquareText,
                title: '2. Ask a question',
                desc: 'Type a question in the box below — e.g. “What is our refund policy?” The AI reads your documents and replies.',
              },
              {
                icon: Quote,
                title: '3. Answers cite their sources',
                desc: 'Each answer shows which documents it came from, so you can verify and open the original.',
              },
              {
                icon: MessageSquare,
                title: '4. Organize your chats',
                desc: 'Use the sidebar to start a New Chat, search past conversations, rename them, or delete ones you no longer need.',
              },
            ].map((step, i) => (
              <div key={i} className="flex items-start gap-3 rounded-xl p-3" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
                <span className="shrink-0 flex items-center justify-center w-9 h-9 rounded-lg mt-0.5" style={{ backgroundColor: ACCENT_SOFT }}>
                  <step.icon className="h-4 w-4" style={{ color: ACCENT }} />
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-white">{step.title}</p>
                  <p className="text-xs text-white/60 mt-0.5 leading-relaxed">{step.desc}</p>
                </div>
              </div>
            ))}

            <div className="flex items-start gap-2 rounded-xl p-3" style={{ background: 'rgba(245,158,11,0.10)', border: `1px solid ${ACCENT_BORDER}` }}>
              <Lightbulb className="h-4 w-4 shrink-0 mt-0.5" style={{ color: ACCENT }} />
              <p className="text-xs text-white/75 leading-relaxed">
                <span className="font-semibold text-white">Tip:</span> Ask specific questions and mention the topic — the more precise your question, the better the cited answer.
              </p>
            </div>

            <Button
              id="OPS-qa-onboarding-close-btn"
              data-testid="OPS-qa-onboarding-close-btn"
              onClick={() => setShowOnboarding(false)}
              className="w-full border-0"
              style={{ background: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)', color: '#fff' }}
            >
              Got it
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <div id="OPS-qa-delete-confirm-dialog" data-testid="OPS-qa-delete-confirm-dialog">
      <ConfirmDialog
        open={!!pendingDeleteChat}
        onOpenChange={(open) => { if (!open) setPendingDeleteChat(null); }}
        title="Delete this chat?"
        description={
          <>
            <span className="text-white/80 font-medium">
              {pendingDeleteChat?.title || 'This chat'}
            </span>
            {' '}and all of its messages will be permanently deleted. Your
            documents are not affected. This cannot be undone.
          </>
        }
        confirmLabel="Delete chat"
        variant="danger"
        loading={deletingChat}
        onConfirm={confirmDeleteChat}
      />
      </div>
    </div>
  );
};

// ──────────────────────────────────────────────
// Sub-components
// ──────────────────────────────────────────────

const EmptyState = ({ onPick }) => (
  <div id="OPS-qa-empty-state" data-testid="OPS-qa-empty-state" className="max-w-2xl mx-auto flex flex-col items-center justify-center py-10 text-center">
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
      {SUGGESTIONS.map((s, i) => (
        <button
          key={s}
          id={`OPS-qa-suggestion-btn-${i}`}
          data-testid={`OPS-qa-suggestion-btn-${i}`}
          onClick={() => onPick(s)}
          className="text-left px-3 py-2.5 rounded-lg border border-white/10 bg-white/[0.02] hover:bg-white/[0.06] hover:border-amber-500/30 text-sm text-white/80 transition-colors"
        >
          {s}
        </button>
      ))}
    </div>
  </div>
);

// Small hover-reveal copy button; flips to a check for 2s on success.
const CopyButton = ({ text, title = 'Copy', testId }) => {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text || '');
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard blocked — silently ignore */
    }
  };
  return (
    <button
      id={testId}
      data-testid={testId}
      type="button"
      onClick={copy}
      title={copied ? 'Copied' : title}
      className="h-6 w-6 flex items-center justify-center rounded hover:bg-white/10 transition-colors"
    >
      {copied
        ? <Check className="h-3.5 w-3.5 text-green-400" />
        : <Copy className="h-3.5 w-3.5 text-white/50 hover:text-amber-300" />}
    </button>
  );
};

const Message = ({
  message,
  index = 0,
  isLastUser = false,
  answerRef = null,
  isEditing = false,
  editValue = '',
  onEditChange = () => {},
  onStartEdit = () => {},
  onCancelEdit = () => {},
  onSubmitEdit = () => {},
  editDisabled = false,
}) => {
  if (message.role === 'user') {
    // Inline edit mode (only reachable for the last user message).
    if (isEditing) {
      return (
        <div
          id={`OPS-qa-message-edit-${index}`}
          data-testid={`OPS-qa-message-edit-${index}`}
          className="flex justify-end"
        >
          <div
            className="w-full max-w-[78%] rounded-2xl px-3 py-3"
            style={{ backgroundColor: 'rgba(245,158,11,0.10)', border: `1px solid ${ACCENT_BORDER}` }}
          >
            <Textarea
              id={`OPS-qa-message-edit-input-${index}`}
              data-testid={`OPS-qa-message-edit-input-${index}`}
              value={editValue}
              onChange={(e) => onEditChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSubmitEdit(); }
                if (e.key === 'Escape') onCancelEdit();
              }}
              rows={2}
              autoFocus
              className="w-full resize-none bg-black/30 border border-amber-500/30 rounded-lg text-white/95 text-[14px] leading-relaxed focus:outline-none focus-visible:ring-0 px-3 py-2 min-h-[44px] max-h-[160px]"
            />
            <div className="flex items-center justify-end gap-2 mt-2">
              <button
                id={`OPS-qa-message-edit-cancel-btn-${index}`}
                data-testid={`OPS-qa-message-edit-cancel-btn-${index}`}
                type="button"
                onClick={onCancelEdit}
                className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs text-white/70 hover:bg-white/10 transition-colors"
              >
                <X className="h-3.5 w-3.5" /> Cancel
              </button>
              <button
                id={`OPS-qa-message-edit-save-btn-${index}`}
                data-testid={`OPS-qa-message-edit-save-btn-${index}`}
                type="button"
                onClick={onSubmitEdit}
                disabled={editDisabled || !editValue.trim()}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-40 transition-transform active:scale-95"
                style={{ backgroundColor: ACCENT, color: '#1a0e00' }}
              >
                <Send className="h-3.5 w-3.5" /> Save &amp; resend
              </button>
            </div>
          </div>
        </div>
      );
    }
    return (
      <div
        id={`OPS-qa-message-user-${index}`}
        data-testid={`OPS-qa-message-user-${index}`}
        className="group flex justify-end items-start gap-1.5"
      >
        {/* Hover actions sit to the LEFT of the right-aligned bubble */}
        <div className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-0.5 mt-1 shrink-0">
          <CopyButton text={message.content} title="Copy question" testId={`OPS-qa-message-copy-btn-${index}`} />
          {isLastUser && (
            <button
              id={`OPS-qa-message-edit-btn-${index}`}
              data-testid={`OPS-qa-message-edit-btn-${index}`}
              type="button"
              onClick={onStartEdit}
              title="Edit & resend"
              className="h-6 w-6 flex items-center justify-center rounded hover:bg-white/10 transition-colors"
            >
              <Pencil className="h-3.5 w-3.5 text-white/50 hover:text-amber-300" />
            </button>
          )}
        </div>
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
  // Timing lives inside responseData so it survives a chat re-fetch.
  const timing = message.responseData?.timing_ms || message.timing_ms || null;
  const cacheHit = message.responseData?.cache_hit ?? message.cache_hit ?? false;
  const totalMs = timing?.total;
  return (
    <div
      ref={answerRef}
      id={`OPS-qa-message-assistant-${index}`}
      data-testid={`OPS-qa-message-assistant-${index}`}
      className="group flex items-start gap-3 scroll-mt-6"
    >
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
          <div
            id={`OPS-qa-message-sources-${index}`}
            data-testid={`OPS-qa-message-sources-${index}`}
            className="mt-3 pt-3 border-t border-white/10"
          >
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
                  id={`OPS-qa-message-source-${index}-${i}`}
                  data-testid={`OPS-qa-message-source-${index}-${i}`}
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
        {totalMs != null && (
          <div className="mt-2 flex items-center gap-2 text-[10px] text-white/35 font-mono">
            <span>⏱ Answered in {(totalMs / 1000).toFixed(2)}s</span>
            {!cacheHit && timing?.retrieval != null && timing?.llm != null && totalMs > 1000 && (
              <span className="text-white/25">
                (retrieval {(timing.retrieval / 1000).toFixed(1)}s · llm {(timing.llm / 1000).toFixed(1)}s)
              </span>
            )}
            {cacheHit && (
              <span className="px-1.5 py-[1px] rounded bg-emerald-500/15 text-emerald-300 border border-emerald-400/25">
                cached
              </span>
            )}
          </div>
        )}
        {/* Hover-reveal copy for the answer text */}
        <div className="mt-2 -mb-1 flex items-center opacity-0 group-hover:opacity-100 transition-opacity">
          <CopyButton text={message.content} title="Copy answer" testId={`OPS-qa-message-copy-btn-${index}`} />
        </div>
      </div>
    </div>
  );
};

export default KnowledgeQA;
