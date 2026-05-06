/**
 * HRKnowledgeQAAgent — full chat UI for HR Knowledge Q&A.
 *
 * Mirrors the layout + visual language of the Project Pilot Q&A
 * (`pm-agent/KnowledgeQAAgent.jsx`):
 *   * Collapsible left sidebar with chat history, search, new-chat, delete.
 *   * Right panel with markdown-rendered assistant responses, user bubbles,
 *     citation footnotes, and a multi-turn input box.
 *
 * Differences vs. PM:
 *   * No project scoping (HR isn't project-bound).
 *   * No graph mode (HR is text-first).
 *   * Calls `hrAgentService` and persists chats via the HR endpoints.
 */
import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/components/ui/use-toast';
import {
  Loader2, Send, MessageSquare, Plus, MessageCircle, Trash2,
  ChevronsLeft, ChevronsRight, Bot, Search,
} from 'lucide-react';
import hrAgentService from '@/services/hrAgentService';

// ---------- markdown → HTML (lifted from PM agent's helper) ----------
function markdownToHtml(markdown) {
  if (!markdown || typeof markdown !== 'string') return '';
  const escape = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const bold = (s) => s.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-violet-300">$1</strong>');

  const getIndentLevel = (line) => {
    const match = line.match(/^(\s*)(?:•|-|\*|\d+\.)\s+/);
    if (!match) return -1;
    return Math.floor(match[1].length / 2);
  };

  const lines = markdown.split('\n');
  const out = [];
  let listDepth = -1;

  const closeListsTo = (target) => {
    while (listDepth > target) { out.push('</ul>'); listDepth--; }
  };

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const t = line.trim();
    if (/^---+$/.test(t)) {
      closeListsTo(-1);
      out.push('<hr class="my-4 border-white/10"/>');
      i++; continue;
    }
    if (/^## /.test(t)) {
      closeListsTo(-1);
      out.push(`<h2 class="text-base font-bold mt-4 mb-2 text-violet-300 border-b border-violet-500/20 pb-1.5">${bold(escape(t.slice(3)))}</h2>`);
      i++; continue;
    }
    if (/^### /.test(t)) {
      closeListsTo(-1);
      out.push(`<h3 class="text-sm font-bold mt-3 mb-1.5 text-violet-200">${bold(escape(t.slice(4)))}</h3>`);
      i++; continue;
    }

    const indent = getIndentLevel(line);
    if (indent >= 0) {
      const content = t.replace(/^[\s]*(?:•|-|\*|\d+\.)\s+/, '');
      while (listDepth < indent) {
        out.push('<ul class="list-disc pl-5 space-y-1 my-2 text-sm">');
        listDepth++;
      }
      while (listDepth > indent) { out.push('</ul>'); listDepth--; }
      out.push(`<li>${bold(escape(content))}</li>`);
      i++; continue;
    }

    closeListsTo(-1);
    if (t) {
      out.push(`<p class="my-1.5 text-sm leading-relaxed">${bold(escape(t))}</p>`);
    }
    i++;
  }
  closeListsTo(-1);
  return out.join('\n');
}


const HRKnowledgeQAAgent = () => {
  const { toast } = useToast();
  const messagesEndRef = useRef(null);

  // Chat state
  const [chats, setChats] = useState([]);
  const [selectedChatId, setSelectedChatId] = useState(null);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingChats, setLoadingChats] = useState(false);

  // Sidebar state
  const [showChatHistory, setShowChatHistory] = useState(true);
  const [showSidebarSearch, setShowSidebarSearch] = useState(false);
  const [sidebarSearch, setSidebarSearch] = useState('');

  const currentChat = chats.find((c) => c.id === selectedChatId);
  const currentMessages = currentChat?.messages || [];

  // ---------- Initial load ----------
  useEffect(() => {
    loadChats();
  }, []);

  useEffect(() => {
    // Auto-scroll to the bottom on new messages
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [currentMessages.length, loading]);

  const loadChats = async () => {
    setLoadingChats(true);
    try {
      const res = await hrAgentService.listHRKnowledgeChats();
      setChats(res?.data || []);
    } catch (e) {
      toast({ title: 'Failed to load chats', description: e.message, variant: 'destructive' });
    } finally {
      setLoadingChats(false);
    }
  };

  // ---------- New chat ----------
  const startNewChat = () => {
    setSelectedChatId(null);
    setQuestion('');
  };

  const handleSelectChat = (id) => {
    setSelectedChatId(id);
    setQuestion('');
  };

  const handleDeleteChat = async (chatId, ev) => {
    if (ev) { ev.stopPropagation(); ev.preventDefault(); }
    if (!confirm('Delete this conversation?')) return;
    try {
      await hrAgentService.deleteHRKnowledgeChat(chatId);
      setChats((cs) => cs.filter((c) => c.id !== String(chatId)));
      if (selectedChatId === String(chatId)) {
        setSelectedChatId(null);
      }
    } catch (e) {
      toast({ title: 'Delete failed', description: e.message, variant: 'destructive' });
    }
  };

  // ---------- Submit ----------
  const handleSubmit = async (e) => {
    if (e) e.preventDefault();
    const q = question.trim();
    if (!q || loading) return;

    setLoading(true);
    setQuestion('');

    // Snapshot existing messages and append the user turn locally for instant feedback
    const baseMessages = currentMessages.slice();
    const newUserMsg = { role: 'user', content: q };
    const optimisticMessages = [...baseMessages, newUserMsg];

    // Show optimistic message in current chat (or temp chat) right away
    if (currentChat) {
      setChats((cs) => cs.map((c) =>
        c.id === currentChat.id ? { ...c, messages: optimisticMessages } : c,
      ));
    } else {
      // No chat selected yet — create a temp draft on screen so the user sees their bubble
      setChats((cs) => [{
        id: 'draft', title: q.slice(0, 40), messages: optimisticMessages,
        updatedAt: new Date().toISOString(), timestamp: new Date().toISOString(), isDraft: true,
      }, ...cs.filter((c) => c.id !== 'draft')]);
      setSelectedChatId('draft');
    }

    let assistantMsg = null;
    try {
      // Build chat_history payload from the prior turns (last 6) — keep it tight
      const history = baseMessages.slice(-6).map((m) => ({ role: m.role, content: m.content }));
      const res = await hrAgentService.askHRKnowledge(q, history);
      const data = res?.data || {};
      assistantMsg = {
        role: 'assistant',
        content: data.answer || '(no answer)',
        responseData: {
          has_verified_info: data.has_verified_info,
          confidence: data.confidence,
          best_score: data.best_score,
          threshold: data.threshold,
          citations: data.citations || [],
        },
      };
    } catch (err) {
      assistantMsg = { role: 'assistant', content: `Error: ${err.message || 'Failed to get answer'}` };
    }

    const finalMessages = [...optimisticMessages, assistantMsg];

    // Persist — create chat if this was a draft, otherwise update
    try {
      if (!currentChat || currentChat.isDraft) {
        const created = await hrAgentService.createHRKnowledgeChat({
          title: q.slice(0, 40),
          messages: finalMessages,
        });
        const c = created?.data;
        if (c) {
          setChats((cs) => [c, ...cs.filter((x) => x.id !== 'draft' && x.id !== c.id)]);
          setSelectedChatId(c.id);
        }
      } else {
        const updated = await hrAgentService.updateHRKnowledgeChat(currentChat.id, {
          messages: finalMessages,
        });
        const c = updated?.data;
        if (c) {
          setChats((cs) => cs.map((x) => (x.id === c.id ? c : x)));
        }
      }
    } catch (err) {
      console.error('persist chat failed', err);
      toast({ title: 'Saved locally only', description: err.message || 'Failed to persist chat', variant: 'destructive' });
      // Even if persistence failed, leave the local view consistent
      setChats((cs) => cs.map((x) => (x.id === selectedChatId
        ? { ...x, messages: finalMessages } : x)));
    } finally {
      setLoading(false);
    }
  };

  const filteredChats = chats.filter((c) => {
    const q = sidebarSearch.trim().toLowerCase();
    if (!q) return true;
    return (c.title || '').toLowerCase().includes(q);
  });

  // ---------- Render ----------
  return (
    <div
      className="w-full rounded-2xl border border-white/[0.06] p-0 overflow-hidden"
      style={{
        background: 'linear-gradient(90deg, #020308 0%, #020308 55%, rgba(10,37,64,0.68) 85%, rgba(14,39,71,0.52) 100%)',
      }}
    >
      <div className="flex w-full max-w-full relative max-h-[calc(100vh-200px)]">

        {/* SIDEBAR */}
        <div
          className={`shrink-0 rounded-xl border border-white/15 shadow-[0_2px_24px_0_rgba(80,36,180,0.18)] backdrop-blur-lg overflow-hidden transition-all duration-300 ease-in-out ${
            showChatHistory ? 'w-64 opacity-100 mr-4' : 'w-0 opacity-0 border-0 mr-0'
          }`}
          style={{
            minWidth: showChatHistory ? '16rem' : '0',
            background: 'linear-gradient(90deg, rgba(139,92,246,0.13) 0%, rgba(36,18,54,0.18) 18%, #0a0a0f 55%, #0a0a0f 100%)',
            backdropFilter: 'blur(12px)',
          }}
        >
          <div className="w-64 h-full flex flex-col">
            {/* Sidebar header */}
            <div
              className="px-3 pt-3 pb-2 border-b border-white/15 flex flex-col gap-2 shrink-0"
              style={{ background: 'linear-gradient(180deg, rgba(60,30,90,0.22) 0%, rgba(36,18,54,0.85) 100%)' }}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-base font-semibold text-white/90 tracking-wide">HR Assistant</span>
                <button
                  onClick={() => setShowChatHistory(false)}
                  title="Close sidebar"
                  className="h-8 w-8 flex items-center justify-center rounded-full border border-white/20 hover:border-violet-400/60 bg-black/30 hover:bg-violet-700/20 transition-all duration-150"
                >
                  <ChevronsLeft className="h-4 w-4 text-white/80" />
                </button>
              </div>

              {/* Search */}
              {showSidebarSearch ? (
                <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg w-full"
                  style={{ border: '1.5px solid rgba(139,92,246,0.22)',
                           background: 'linear-gradient(90deg, rgba(80,36,180,0.10) 0%, rgba(36,18,54,0.18) 100%)' }}>
                  <input
                    autoFocus
                    value={sidebarSearch}
                    onChange={(e) => setSidebarSearch(e.target.value)}
                    placeholder="Search conversations..."
                    className="flex-1 bg-transparent outline-none border-0 text-white/90 text-sm px-2 py-1.5 placeholder-white/40"
                  />
                  <button
                    title="Close search"
                    onClick={() => { setSidebarSearch(''); setShowSidebarSearch(false); }}
                    className="h-7 w-7 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60 bg-black/20 hover:bg-violet-700/20"
                  >
                    <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                      <line x1="6" y1="6" x2="18" y2="18" /><line x1="6" y1="18" x2="18" y2="6" />
                    </svg>
                  </button>
                </div>
              ) : (
                <div className="flex items-center justify-between text-xs uppercase tracking-wider text-white/50">
                  <span>Conversations</span>
                  <div className="flex items-center gap-1">
                    <button
                      title="Search"
                      onClick={() => setShowSidebarSearch(true)}
                      className="h-7 w-7 flex items-center justify-center rounded-full hover:bg-white/5"
                    >
                      <Search className="h-3.5 w-3.5 text-white/60" />
                    </button>
                    <button
                      title="New chat"
                      onClick={startNewChat}
                      className="h-7 w-7 flex items-center justify-center rounded-full hover:bg-white/5"
                    >
                      <Plus className="h-4 w-4 text-violet-400" />
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Chat list */}
            <div className="flex-1 overflow-y-auto px-2 py-2">
              {loadingChats ? (
                <div className="flex justify-center py-6">
                  <Loader2 className="h-4 w-4 animate-spin text-white/50" />
                </div>
              ) : filteredChats.length === 0 ? (
                <div className="text-center text-xs text-white/40 py-6">
                  {sidebarSearch ? 'No matches.' : 'No conversations yet.'}
                </div>
              ) : (
                <div className="space-y-1">
                  {filteredChats.map((c) => {
                    const isActive = c.id === selectedChatId;
                    return (
                      <div
                        key={c.id}
                        onClick={() => handleSelectChat(c.id)}
                        className={`group rounded-lg p-2 cursor-pointer transition-all duration-100 border ${
                          isActive
                            ? 'bg-violet-600/20 border-violet-400/40'
                            : 'bg-white/[0.02] border-white/[0.05] hover:border-violet-400/20 hover:bg-white/[0.04]'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="min-w-0 flex-1">
                            <div className="text-sm text-white/90 truncate">{c.title || 'Untitled'}</div>
                            <div className="text-[10px] text-white/40 mt-0.5">
                              {c.updatedAt ? new Date(c.updatedAt).toLocaleString() : '—'}
                            </div>
                          </div>
                          {!c.isDraft && (
                            <button
                              title="Delete"
                              onClick={(ev) => handleDeleteChat(c.id, ev)}
                              className="opacity-0 group-hover:opacity-100 transition-opacity h-6 w-6 flex items-center justify-center rounded-full hover:bg-rose-500/20"
                            >
                              <Trash2 className="h-3.5 w-3.5 text-rose-400" />
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* MAIN CHAT PANEL */}
        <Card className="flex-1 min-w-0 border-white/[0.06] bg-transparent flex flex-col">
          <CardHeader className="flex flex-row items-center justify-between gap-2 border-b border-white/[0.06] py-3">
            <div className="flex items-center gap-2 min-w-0">
              {!showChatHistory && (
                <button
                  onClick={() => setShowChatHistory(true)}
                  title="Open conversations"
                  className="h-8 w-8 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60 hover:bg-violet-700/20"
                >
                  <ChevronsRight className="h-4 w-4 text-white/80" />
                </button>
              )}
              <div className="min-w-0">
                <CardTitle className="text-base flex items-center gap-2">
                  <MessageSquare className="h-4 w-4 text-violet-400" />
                  HR Knowledge Q&A
                </CardTitle>
                <CardDescription className="text-xs">
                  Ask anything about company policy, leave, benefits, or process. Personalised to you.
                </CardDescription>
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={startNewChat}>
              <Plus className="h-3.5 w-3.5 mr-1" /> New chat
            </Button>
          </CardHeader>

          <CardContent className="flex-1 flex flex-col min-h-0 p-0">
            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 min-h-[280px]">
              {currentMessages.length === 0 && !loading ? (
                <div className="h-full min-h-[260px] flex flex-col items-center justify-center text-center text-white/60 px-6">
                  <div className="h-12 w-12 rounded-2xl bg-violet-500/10 border border-violet-400/20 flex items-center justify-center mb-3">
                    <Bot className="h-6 w-6 text-violet-400" />
                  </div>
                  <div className="text-sm font-medium text-white/90 mb-1">Ask the HR Assistant</div>
                  <div className="text-xs max-w-md">
                    Examples: <em>“How many vacation days do I have?”</em> · <em>“What's the parental leave policy?”</em> · <em>“Can I claim this commute as expense?”</em>
                  </div>
                </div>
              ) : (
                currentMessages.map((msg, idx) => (
                  <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div
                      className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm ${
                        msg.role === 'user'
                          ? 'bg-violet-600/20 border border-violet-400/30 text-white/95'
                          : 'bg-white/[0.04] border border-white/[0.08] text-white/90'
                      }`}
                    >
                      {msg.role === 'user' ? (
                        <div className="whitespace-pre-wrap">{msg.content}</div>
                      ) : (
                        <>
                          <div
                            className="prose prose-invert max-w-none"
                            dangerouslySetInnerHTML={{ __html: markdownToHtml(msg.content) }}
                          />
                          {msg.responseData?.citations?.length > 0 && (
                            <div className="mt-3 pt-2 border-t border-white/10 text-xs text-white/60 space-y-1">
                              <div className="font-medium">Sources</div>
                              <ol className="list-decimal list-inside space-y-0.5">
                                {msg.responseData.citations.map((c, ci) => (
                                  <li key={ci}>
                                    <span className="font-medium text-white/80">{c.title}</span>
                                    {c.score != null && <span className="text-white/40"> · score {c.score}</span>}
                                  </li>
                                ))}
                              </ol>
                            </div>
                          )}
                          {msg.responseData?.has_verified_info === false && (
                            <div className="mt-2 text-[11px] text-amber-300/80">
                              No verified info — escalating to HR.
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                ))
              )}

              {loading && (
                <div className="flex justify-start">
                  <div className="rounded-2xl px-4 py-2.5 bg-white/[0.04] border border-white/[0.08] text-white/70 text-sm flex items-center gap-2">
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-violet-400" />
                    Thinking...
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <form
              onSubmit={handleSubmit}
              className="border-t border-white/[0.06] px-3 py-3 flex flex-col sm:flex-row items-end gap-2"
            >
              <Textarea
                rows={2}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSubmit(e);
                  }
                }}
                placeholder='Ask about HR policy, leave, benefits...  (Shift+Enter for newline)'
                className="flex-1 resize-none bg-white/[0.03] border-white/[0.08] focus-visible:ring-violet-500/50"
              />
              <Button type="submit" disabled={loading || !question.trim()}>
                {loading
                  ? <Loader2 className="h-4 w-4 animate-spin" />
                  : <Send className="h-4 w-4" />}
                <span className="ml-1 hidden sm:inline">Send</span>
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default HRKnowledgeQAAgent;
