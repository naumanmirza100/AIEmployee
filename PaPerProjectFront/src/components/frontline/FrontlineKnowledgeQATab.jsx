import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import ChatMarkdown from '@/components/shared/ChatMarkdown';
import {
  Loader2, Search, Trash2, CheckCircle2, XCircle, Send, Plus,
  MessageCircle, ChevronLeft, ChevronRight, BarChart3,
  ThumbsUp, ThumbsDown, Bot, Maximize2,
} from 'lucide-react';
import InfoHint from './InfoHint';
import { HINTS } from './frontlineTutorialSteps';
import { ElapsedTimer } from './chatShellUtils';
import frontlineAgentService from '@/services/frontlineAgentService';
import { renderChart } from '../recruitment/ChartRenderer';

/**
 * FrontlineKnowledgeQATab — extracted from the inline `qa` TabsContent in
 * FrontlineDashboard.jsx (Chunk B2 of FRONTLINE_AGENT_UX_REDESIGN.md).
 *
 * The whole 720-line chat pane: left sidebar (chat list + search + new-chat
 * + delete), main chat area (message list with streaming, citations,
 * timing footer, feedback thumbs), and the input form (scope picker +
 * mode selector + textarea + send). Rendered in TWO places by the parent:
 *   • KnowledgeView's "Q&A" sub-tab (the new home)
 *   • Legacy hidden `?tab=qa` (URL deep-links still work)
 * so the props signature is deliberately large to keep the two mounts
 * behaviourally identical.
 *
 * All state stays in the parent so the QA transcript survives sidebar
 * toggles, tab switches, and streaming callbacks.
 */

const DOCUMENT_TYPE_OPTIONS = [
  { value: 'knowledge_base', label: 'Knowledge Base' },
  { value: 'policy', label: 'Policy' },
  { value: 'procedure', label: 'Procedure' },
  { value: 'report', label: 'Report' },
  { value: 'ticket_attachment', label: 'Ticket Attachment' },
  { value: 'other', label: 'Other' },
];

const INPUT_MODE_OPTIONS = [
  { value: 'search', label: 'Search', placeholder: 'Ask a question...', icon: Search },
  { value: 'graph',  label: 'Graph',  placeholder: 'Describe the support graph you want to generate…', icon: BarChart3 },
];

const truncate = (s, n = 50) => (s && s.length > n ? s.slice(0, n) + '…' : (s || ''));
const formatDate = (iso) => {
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch { return ''; }
};

export default function FrontlineKnowledgeQATab(props) {
  const {
    // state (getters)
    chats, selectedChatId, question, answering, answeringStartedAt, loadingChats,
    inputMode, expandedGraph, showSidebarSearch, sidebarSearch, showChatHistory,
    qaScopeMode, qaScopeDocumentTypes, qaScopeDocumentIds,
    qaDocumentsList, qaDocumentsLoading, feedbackSent, feedbackSubmitting,
    documents,
    // state (setters)
    setSelectedChatId, setQuestion, setInputMode, setExpandedGraph,
    setShowSidebarSearch, setSidebarSearch, setShowChatHistory,
    setQaScopeMode, setQaScopeDocumentTypes, setQaScopeDocumentIds,
    setFeedbackSent, setFeedbackSubmitting,
    // handlers
    onNewChat, onDeleteChat, onAskQuestion,
    // ref
    messagesEndRef,
  } = props;
  const { toast } = useToast();

  const selectedMode = INPUT_MODE_OPTIONS.find((m) => m.value === inputMode) || INPUT_MODE_OPTIONS[0];
  const SelectedModeIcon = selectedMode.icon;
  const selectedChat = chats.find((c) => c.id === selectedChatId);
  const currentMessages = selectedChat?.messages ?? [];

  // Send feedback for assistant message #i. Extracted from the two inline
  // handlers on ThumbsUp/ThumbsDown so we don't repeat the fetch+catch.
  const submitFeedback = async (helpful, i, msg) => {
    const questionText = currentMessages[i - 1]?.content || '';
    if (!questionText) return;
    setFeedbackSubmitting(true);
    try {
      await frontlineAgentService.submitKnowledgeFeedback({
        question: questionText,
        helpful,
        document_id: msg.responseData?.document_id ?? undefined,
      });
      setFeedbackSent((prev) => ({ ...prev, [`${selectedChatId}-${i}`]: true }));
    } catch {
      toast({ title: 'Error', description: 'Could not send feedback', variant: 'destructive' });
    } finally {
      setFeedbackSubmitting(false);
    }
  };

  return (
    <div
      className="w-full rounded-2xl border border-white/[0.06] p-0 overflow-hidden"
      style={{
        background: 'linear-gradient(90deg, #020308 0%, #020308 55%, rgba(10,37,64,0.68) 85%, rgba(14,39,71,0.52) 100%)',
      }}
    >
      <div className="flex w-full max-w-full relative">

        {/* ── LEFT SIDEBAR — chat history / search / new-chat ─────────── */}
        <div
          data-tour-qa="sidebar"
          className={`shrink-0 rounded-xl border border-white/15 shadow-[0_2px_24px_0_rgba(80,36,180,0.18)] backdrop-blur-lg overflow-hidden transition-all duration-300 ease-in-out ${
            showChatHistory ? 'w-64 opacity-100 mr-4' : 'w-0 opacity-0 border-0 mr-0'
          }`}
          style={{
            minWidth: showChatHistory ? '16rem' : '0',
            background: 'linear-gradient(90deg, rgba(139,92,246,0.13) 0%, rgba(36,18,54,0.18) 18%, #0a0a0f 55%, #0a0a0f 100%)',
            borderRight: '1.5px solid rgba(255,255,255,0.10)',
            boxShadow: '0 2px 24px 0 rgba(80, 36, 180, 0.18), 0 0 0 1.5px rgba(120, 80, 255, 0.10) inset',
            borderTopLeftRadius: 16,
            borderBottomLeftRadius: 16,
            backdropFilter: 'blur(12px)',
            WebkitBackdropFilter: 'blur(12px)',
            overflow: 'hidden',
          }}
        >
          <div className="w-64">
            <div
              className="px-3 pt-3 pb-2 border-b border-white/15 flex flex-col gap-2"
              style={{
                background: 'linear-gradient(180deg, rgba(60, 30, 90, 0.22) 0%, rgba(36, 18, 54, 0.85) 100%)',
                borderTopLeftRadius: 16,
              }}
            >
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-1.5">
                  <span className="text-base font-semibold text-white/90 tracking-wide">Frontline</span>
                  <InfoHint {...HINTS.qaSidebar} />
                </div>
                <button
                  onClick={() => setShowChatHistory(false)}
                  title="Close sidebar"
                  className="h-8 w-8 flex items-center justify-center rounded-full border border-white/20 hover:border-violet-400/60 bg-black/30 hover:bg-violet-700/20 transition-all duration-150"
                  style={{ boxShadow: '0 0 0 2px rgba(139,92,246,0.10) inset' }}
                >
                  <ChevronLeft className="h-4 w-4 text-white/80" />
                </button>
              </div>

              {showSidebarSearch ? (
                <div
                  className="flex items-center gap-2 px-2 py-1.5 rounded-lg w-full"
                  style={{
                    border: '1.5px solid rgba(139,92,246,0.22)',
                    background: 'linear-gradient(90deg, rgba(80,36,180,0.10) 0%, rgba(36,18,54,0.18) 100%)',
                    boxShadow: '0 1px 8px 0 rgba(139,92,246,0.08) inset',
                    backdropFilter: 'blur(4px)',
                    WebkitBackdropFilter: 'blur(4px)',
                  }}
                >
                  <input
                    autoFocus
                    value={sidebarSearch}
                    onChange={(e) => setSidebarSearch(e.target.value)}
                    placeholder="Search conversations..."
                    className="flex-1 bg-transparent outline-none border-0 text-white/90 text-sm px-2 py-1.5 placeholder-white/40"
                    style={{ minWidth: 0 }}
                  />
                  <button
                    title="Close search"
                    onClick={() => { setSidebarSearch(''); setShowSidebarSearch(false); }}
                    className="h-7 w-7 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60 bg-black/20 hover:bg-violet-700/20 transition-all duration-150"
                  >
                    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-white/70">
                      <line x1="4" y1="4" x2="12" y2="12" />
                      <line x1="12" y1="4" x2="4" y2="12" />
                    </svg>
                  </button>
                </div>
              ) : (
                <div
                  className="flex items-center gap-2 px-2 py-1.5 rounded-lg w-full"
                  style={{
                    border: '1.5px solid rgba(139,92,246,0.22)',
                    background: 'linear-gradient(90deg, rgba(80,36,180,0.10) 0%, rgba(36,18,54,0.18) 100%)',
                    boxShadow: '0 1px 8px 0 rgba(139,92,246,0.08) inset',
                    backdropFilter: 'blur(4px)',
                    WebkitBackdropFilter: 'blur(4px)',
                  }}
                >
                  <span className="text-sm font-medium text-white/80 flex-1">Conversation</span>
                  <button
                    title="Search"
                    onClick={() => setShowSidebarSearch(true)}
                    className="h-7 w-7 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60 bg-black/20 hover:bg-violet-700/20 transition-all duration-150"
                  >
                    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-white/70">
                      <circle cx="7" cy="7" r="5" />
                      <line x1="15" y1="15" x2="11" y2="11" />
                    </svg>
                  </button>
                  <button
                    data-tour-qa="new-chat"
                    onClick={onNewChat}
                    title="New chat"
                    className="h-7 w-7 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60 bg-black/20 hover:bg-violet-700/20 transition-all duration-150"
                  >
                    <Plus className="h-4 w-4 text-white/80" />
                  </button>
                  <InfoHint {...HINTS.qaNewChat} />
                </div>
              )}
            </div>

            <div>
              {loadingChats ? (
                <div className="p-4 flex justify-center">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              ) : chats.length === 0 ? (
                <div className="p-4 text-center text-sm text-muted-foreground">No conversations yet. Ask a question to start.</div>
              ) : (
                <div
                  className="p-2 space-y-1"
                  style={{
                    background: 'linear-gradient(180deg, rgba(36, 18, 54, 0.10) 0%, rgba(24, 18, 43, 0.18) 100%)',
                    borderRadius: 12,
                  }}
                >
                  {(() => {
                    const searchTerm = sidebarSearch.trim().toLowerCase();
                    const filteredChats = searchTerm
                      ? chats.filter((c) => {
                          const title = (c.title || c.messages?.[0]?.content || '').toLowerCase();
                          const messagesMatch = (c.messages || []).some((m) => (m.content || '').toLowerCase().includes(searchTerm));
                          return title.includes(searchTerm) || messagesMatch;
                        })
                      : chats;
                    if (searchTerm && filteredChats.length === 0) {
                      return <div className="p-4 text-center text-sm text-muted-foreground">No matching conversations found.</div>;
                    }
                    return filteredChats.map((c) => (
                      <div
                        key={c.id}
                        className={`flex items-center gap-1 rounded-lg border text-sm transition-all duration-200 ${
                          selectedChatId === c.id
                            ? 'border-violet-500/60 bg-gradient-to-r from-violet-900/40 to-violet-700/20 shadow-[0_0_12px_rgba(139,92,246,0.18)]'
                            : 'border-white/10 bg-white/2 hover:bg-white/5 hover:border-violet-400/20'
                        }`}
                        style={{
                          boxShadow: selectedChatId === c.id
                            ? '0 0 12px 0 rgba(139,92,246,0.18), 0 1.5px 0 0 rgba(120,80,255,0.10) inset'
                            : '0 1px 2px 0 rgba(36,18,54,0.08) inset',
                          borderWidth: 1.5,
                        }}
                      >
                        <button
                          type="button"
                          onClick={() => setSelectedChatId(c.id)}
                          className="flex-1 min-w-0 text-left p-3 rounded-lg"
                        >
                          <div className={`font-medium truncate ${selectedChatId === c.id ? 'text-violet-300' : ''}`}>
                            {truncate(c.title || c.messages?.[0]?.content || 'Chat', 40)}
                          </div>
                          <div className={`text-xs mt-0.5 ${selectedChatId === c.id ? 'text-violet-400/70' : 'text-muted-foreground'}`}>
                            {formatDate(c.updatedAt || c.timestamp)}
                          </div>
                        </button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 shrink-0 opacity-60 hover:opacity-100 hover:bg-destructive/10 hover:text-destructive"
                          onClick={(e) => onDeleteChat(e, c.id)}
                          title="Delete chat"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    ));
                  })()}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── MAIN CHAT PANE ──────────────────────────────────────────── */}
        <Card
          className="flex-1 min-w-0 flex flex-col max-h-[calc(100vh-40px)] border-0 shadow-none"
          style={{ background: 'transparent' }}
        >
          <CardHeader
            className="shrink-0 flex flex-row items-start justify-between gap-3 border-b border-white/[0.07] px-0 py-4"
            style={{ background: 'transparent' }}
          >
            <div className="flex items-center gap-3 min-w-0 w-full">
              <div
                style={{
                  width: '7px', height: '48px', borderRadius: '8px',
                  background: 'linear-gradient(to bottom, #a259ff 0%, #6a1b9a 60%, #18122B 100%)',
                  marginLeft: '24px', marginRight: '18px',
                  boxShadow: '0 0 8px 2px #a259ff44',
                }}
              />
              <div className="h-10 w-10 rounded-lg flex items-center justify-center shrink-0" style={{ background: 'rgba(124, 58, 237, 0.15)' }}>
                <Bot className="h-5 w-5" style={{ color: '#a78bfa' }} />
              </div>
              <div className="min-w-0">
                <CardTitle className="flex items-center gap-2 truncate text-white text-lg">
                  Knowledge Q&A
                  <span className="text-[10px] rounded-full px-2.5 py-0.5 font-medium" style={{ background: 'rgba(124, 58, 237, 0.15)', color: '#a78bfa' }}>
                    AI-Powered
                  </span>
                </CardTitle>
                <CardDescription className="text-white/50 text-sm mt-0.5">
                  Ask questions and get answers from your knowledge base and uploaded documents.
                </CardDescription>
              </div>
              <InfoHint {...HINTS.qaMessages} />
            </div>

            <Button
              variant={showChatHistory ? 'ghost' : 'outline'}
              size="sm"
              onClick={() => setShowChatHistory((v) => !v)}
              title={showChatHistory ? 'Hide chat history' : 'Show chat history'}
              className={`gap-1.5 transition-all duration-200 ${
                !showChatHistory
                  ? 'bg-primary/5 hover:bg-primary/10 border-primary/20 text-primary'
                  : 'hover:bg-muted'
              }`}
              style={{ marginRight: '24px' }}
            >
              {showChatHistory ? (
                <><ChevronLeft className="h-4 w-4" /><span className="text-xs hidden sm:inline">Hide</span></>
              ) : (
                <><ChevronRight className="h-4 w-4" /><span className="text-xs hidden sm:inline">History</span></>
              )}
            </Button>
          </CardHeader>

          <CardContent className="p-0 flex flex-col flex-1 min-h-0">
            {/* Message list */}
            <div data-tour-qa="messages" className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-4 py-4 space-y-4">
              {!selectedChatId && chats.length === 0 && (
                <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                  <MessageCircle className="h-12 w-12 mb-4 opacity-50" />
                  <p className="font-medium">Ask your first question</p>
                  <p className="text-sm">Type a question to get an answer from your knowledge base.</p>
                  {documents && documents.length === 0 && (
                    <p className="text-xs mt-2 text-amber-600 dark:text-amber-400">💡 Tip: Upload documents in the Documents tab first</p>
                  )}
                </div>
              )}
              {!selectedChatId && chats.length > 0 && (
                <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                  <MessageCircle className="h-12 w-12 mb-4 opacity-50" />
                  <p className="font-medium">Select a conversation or ask a new question</p>
                  <p className="text-sm">Click a previous chat in the sidebar to view it.</p>
                </div>
              )}
              {currentMessages.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[85%] rounded-2xl px-4 py-3 ${msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted border'}`}>
                    {msg.role === 'user' ? (
                      <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                    ) : msg.responseData?.isGraph ? (
                      <div className="space-y-3">
                        {msg.responseData.chart && (
                          <div className="relative w-full rounded-xl border border-border bg-card p-2 shadow-sm">
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="absolute top-1.5 right-1.5 h-7 w-7 rounded-md opacity-70 hover:opacity-100 text-muted-foreground hover:text-foreground"
                              onClick={() => setExpandedGraph({ chart: msg.responseData.chart, chartTitle: msg.responseData.chartTitle })}
                              title="Expand graph"
                            >
                              <Maximize2 className="h-3.5 w-3.5" />
                            </Button>
                            <div className="pr-8 w-full min-w-0">{renderChart(msg.responseData.chart)}</div>
                          </div>
                        )}
                        {msg.responseData?.insights && (
                          <div className="pt-2 border-t border-border/50">
                            <p className="text-xs font-semibold mb-2">Insights</p>
                            <p className="text-xs text-muted-foreground whitespace-pre-wrap">{msg.responseData.insights}</p>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="flex items-start gap-2">
                        {msg.responseData?.has_verified_info ? (
                          <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400 mt-0.5 flex-shrink-0" />
                        ) : (
                          <XCircle className="h-4 w-4 text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" />
                        )}
                        <div className="flex-1 min-w-0">
                          {msg.streaming ? (
                            // While streaming, render as plain text with a blinking
                            // cursor — markdown parsing on every token would
                            // produce flicker on incomplete headers/lists/bold.
                            <div className="text-sm text-foreground whitespace-pre-wrap break-words">
                              {msg.content}
                              {!msg.content && <span className="text-muted-foreground italic">Thinking…</span>}
                              <span className="inline-block w-1.5 h-3.5 ml-0.5 bg-primary/70 animate-pulse align-middle" />
                            </div>
                          ) : (
                            <ChatMarkdown className="text-sm text-foreground">
                              {msg.responseData?.answer ?? msg.content ?? ''}
                            </ChatMarkdown>
                          )}
                          {msg.responseData?.confidence === 'low' && (
                            <div className="mt-2 text-xs rounded-md px-2 py-1 bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/30">
                              Low-confidence match{typeof msg.responseData?.best_score === 'number' ? ` (score ${msg.responseData.best_score})` : ''}. Consider escalating to a human agent.
                            </div>
                          )}
                          <ResponseTimingFooter msg={msg} />
                          {msg.responseData?.rewritten_query && (
                            <div className="mt-2 text-xs text-muted-foreground italic">
                              Interpreted as: "{msg.responseData.rewritten_query}"
                            </div>
                          )}
                          {msg.responseData?.citations?.length ? (
                            <div className="mt-3 pt-2 border-t border-border/50 space-y-2">
                              <p className="text-xs font-medium text-muted-foreground">Sources</p>
                              <ol className="space-y-1.5 text-xs text-muted-foreground list-decimal list-inside">
                                {msg.responseData.citations.map((c, idx) => (
                                  <li key={`${c.document_id || 'src'}-${c.chunk_id || idx}`} className="break-words">
                                    <span className="font-medium text-foreground">{c.title || c.source || 'Source'}</span>
                                    {typeof c.score === 'number' && <span className="ml-1 text-[10px] opacity-70">({c.score})</span>}
                                    {c.snippet && (
                                      <span className="block mt-0.5 opacity-80 whitespace-pre-wrap">{c.snippet}{c.snippet.length >= 200 ? '…' : ''}</span>
                                    )}
                                  </li>
                                ))}
                              </ol>
                            </div>
                          ) : (msg.responseData?.source ? (
                            <p className="text-xs text-muted-foreground mt-2">Source: {msg.responseData.source}</p>
                          ) : null)}
                          <div className="flex items-center gap-1 mt-2 pt-2 border-t border-border/50">
                            <span className="text-xs text-muted-foreground mr-1">Was this helpful?</span>
                            {feedbackSent[`${selectedChatId}-${i}`] ? (
                              <span className="text-xs text-muted-foreground">Thank you for feedback.</span>
                            ) : (
                              <>
                                <Button
                                  type="button" variant="ghost" size="icon" className="h-8 w-8"
                                  disabled={feedbackSubmitting}
                                  onClick={() => submitFeedback(true, i, msg)}
                                  title="Yes, helpful"
                                >
                                  <ThumbsUp className="h-4 w-4" />
                                </Button>
                                <Button
                                  type="button" variant="ghost" size="icon" className="h-8 w-8"
                                  disabled={feedbackSubmitting}
                                  onClick={() => submitFeedback(false, i, msg)}
                                  title="No, not helpful"
                                >
                                  <ThumbsDown className="h-4 w-4" />
                                </Button>
                              </>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {/* Suppress spinner when a streaming assistant message is already
                  visible — it has its own inline cursor. */}
              {answering && !currentMessages.some((m) => m.streaming) && (
                <div className="flex justify-start">
                  <div className="bg-muted border rounded-2xl px-4 py-3 flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span className="text-sm">Searching knowledge base…</span>
                    <span className="text-xs text-muted-foreground tabular-nums font-mono">
                      <ElapsedTimer since={answeringStartedAt} />
                    </span>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input form */}
            <form
              data-tour-qa="input"
              onSubmit={onAskQuestion}
              className="shrink-0"
              style={{ background: '#0a0a0f', borderTop: '1px solid rgba(255,255,255,0.08)' }}
            >
              <div className="mx-4 my-4 space-y-3 rounded-2xl px-4 py-4" style={{ border: '1px solid rgba(255,255,255,0.08)' }}>
                <div className="space-y-2" data-tour-qa="scope">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm text-muted-foreground">Answer from:</span>
                    <InfoHint {...HINTS.qaScope} />
                    <Select
                      value={qaScopeMode}
                      onValueChange={(v) => {
                        setQaScopeMode(v);
                        if (v !== 'type') setQaScopeDocumentTypes([]);
                        if (v !== 'documents') setQaScopeDocumentIds([]);
                      }}
                    >
                      <SelectTrigger className="w-[180px] h-8"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All documents</SelectItem>
                        <SelectItem value="type">By document type</SelectItem>
                        <SelectItem value="documents">Specific documents</SelectItem>
                      </SelectContent>
                    </Select>

                    {qaScopeMode === 'type' && (
                      <div className="flex flex-wrap items-center gap-2">
                        {DOCUMENT_TYPE_OPTIONS.map((opt) => (
                          <label key={opt.value} className="flex items-center gap-1.5 text-sm cursor-pointer">
                            <Checkbox
                              checked={qaScopeDocumentTypes.includes(opt.value)}
                              onCheckedChange={(checked) => {
                                setQaScopeDocumentTypes((prev) =>
                                  checked ? [...prev, opt.value] : prev.filter((t) => t !== opt.value)
                                );
                              }}
                            />
                            <span>{opt.label}</span>
                          </label>
                        ))}
                      </div>
                    )}

                    {qaScopeMode === 'documents' && (
                      <Select
                        value="_add"
                        onValueChange={(v) => {
                          if (v === '_add' || v === '_none') return;
                          const id = Number(v);
                          if (!qaScopeDocumentIds.includes(id)) setQaScopeDocumentIds((prev) => [...prev, id]);
                        }}
                      >
                        <SelectTrigger className="w-[220px] h-8">
                          <SelectValue placeholder={
                            qaDocumentsLoading ? 'Loading...' :
                            qaScopeDocumentIds.length ? 'Add another document...' :
                            'Add document...'
                          } />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="_add">Add document...</SelectItem>
                          {!qaDocumentsLoading &&
                            qaDocumentsList
                              .filter((d) => !qaScopeDocumentIds.includes(d.id))
                              .map((d) => {
                                // Surface indexing state — a doc that's still
                                // processing can't be queried. Marking it
                                // disabled prevents picking a doc that will hang.
                                const status = d.processing_status || (d.is_indexed ? 'ready' : 'pending');
                                const notReady = status !== 'ready';
                                // FRONTLINE-BUG-07: outdated docs stayed
                                // selectable in the dropdown, leading to
                                // dead-end Q&A loops on stale content.
                                const outdated = !!d.is_outdated;
                                const badge = outdated ? '⚠️ outdated' : {
                                  processing: '⏳ processing', pending: '⏳ queued', failed: '⚠️ failed',
                                }[status];
                                const disabled = notReady || outdated;
                                return (
                                  <SelectItem key={d.id} value={String(d.id)} disabled={disabled}>
                                    <span className={disabled ? 'opacity-60' : ''}>
                                      {d.title || `Document ${d.id}`}
                                      {badge ? ` — ${badge}` : ''}
                                    </span>
                                  </SelectItem>
                                );
                              })}
                        </SelectContent>
                      </Select>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm text-muted-foreground">Mode:</span>
                    <Select value={inputMode} onValueChange={setInputMode}>
                      <SelectTrigger className="w-[180px] h-8">
                        <div className="flex items-center gap-2">
                          <SelectedModeIcon className="h-4 w-4" />
                          <SelectValue placeholder="Search" />
                        </div>
                      </SelectTrigger>
                      <SelectContent>
                        {INPUT_MODE_OPTIONS.map((mode) => {
                          const ModeIcon = mode.icon;
                          return (
                            <SelectItem key={mode.value} value={mode.value}>
                              <div className="flex items-center gap-2">
                                <ModeIcon className="h-4 w-4" />
                                <span>{mode.label}</span>
                              </div>
                            </SelectItem>
                          );
                        })}
                      </SelectContent>
                    </Select>
                  </div>

                  {qaScopeMode === 'documents' && qaScopeDocumentIds.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {qaScopeDocumentIds.map((id) => {
                        const doc = qaDocumentsList.find((d) => d.id === id);
                        return (
                          <Badge key={id} variant="secondary" className="gap-2">
                            <span className="truncate max-w-[220px]">{doc?.title || `Document ${id}`}</span>
                            <button
                              type="button"
                              className="opacity-70 hover:opacity-100"
                              onClick={() => setQaScopeDocumentIds((prev) => prev.filter((x) => x !== id))}
                              title="Remove"
                            >
                              ×
                            </button>
                          </Badge>
                        );
                      })}
                    </div>
                  )}
                </div>

                <div className="flex gap-2 items-start">
                  <div className="pt-2"><InfoHint {...HINTS.qaInput} /></div>
                  <Textarea
                    placeholder={selectedMode.placeholder}
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        onAskQuestion(e);
                      }
                    }}
                    rows={2}
                    disabled={answering}
                    className="min-h-[60px] resize-none flex-1"
                    style={{ background: '#0e0e14', border: '1px solid rgba(255, 255, 255, 0.1)', color: '#e2e2f0' }}
                  />
                  <Button type="submit" disabled={answering} size="icon" className="h-[60px] w-12 shrink-0">
                    {answering ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
                  </Button>
                </div>
              </div>
            </form>

            {/* Expanded graph dialog */}
            <Dialog open={!!expandedGraph} onOpenChange={(open) => !open && setExpandedGraph(null)}>
              <DialogContent className="max-w-[95vw] w-full max-h-[90vh] overflow-auto">
                <DialogHeader className="shrink-0">
                  <DialogTitle>{expandedGraph?.chartTitle || 'Graph'}</DialogTitle>
                </DialogHeader>
                <div className="min-h-[400px] py-4">
                  {expandedGraph?.chart && renderChart(expandedGraph.chart)}
                </div>
              </DialogContent>
            </Dialog>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// Response timing footer — the IIFE originally lived inline in the assistant
// message bubble. Extracted so the message loop stays readable.
function ResponseTimingFooter({ msg }) {
  const t = msg.responseData?.responseTimeMs ?? msg.responseTimeMs;
  if (typeof t !== 'number') return null;
  const tm = msg.responseData?.timing_ms;
  const parts = [];
  if (tm && !tm.cache) {
    if (typeof tm.retrieval === 'number') parts.push(`retrieval ${(tm.retrieval / 1000).toFixed(1)}s`);
    if (typeof tm.llm === 'number') parts.push(`llm ${(tm.llm / 1000).toFixed(1)}s`);
    if (typeof tm.contextualise === 'number') parts.push(`ctx ${(tm.contextualise / 1000).toFixed(1)}s`);
  }
  // Retrieval sub-phase breakdown — only when retrieval > 1s so we can
  // pinpoint WHICH phase (faiss / json-scan / keyword / rerank).
  const rb = tm?.retrieval_breakdown;
  const rp = tm?.retrieval_path;
  const rbParts = [];
  if (rb && (tm?.retrieval || 0) > 1000) {
    const keys = ['query_embed', 'faiss_search', 'faiss_candidates', 'faiss_chunk_fetch', 'faiss_output_build', 'semantic', 'json_scan', 'keyword', 'rerank'];
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
    <div className="mt-2 text-[10px] text-muted-foreground/70 space-y-0.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <span>⏱ Answered in {(t / 1000).toFixed(2)}s</span>
        {parts.length > 0 && <span className="text-muted-foreground/50">({parts.join(' · ')})</span>}
        {msg.responseData?.cache_hit && (
          <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 text-[9px] font-medium">cached</span>
        )}
      </div>
      {(rbParts.length > 0 || rp) && (
        <div className="text-[9px] text-muted-foreground/50 font-mono">
          {rp && <span>path: {rp} </span>}
          {rbParts.join(' · ')}
        </div>
      )}
    </div>
  );
}
