import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import pmAgentService from '@/services/pmAgentService';
import { Loader2, Send, MessageSquare, Plus, MessageCircle, Trash2, ChevronsLeft, ChevronsRight, Bot, Search, BarChart2, Maximize2 } from 'lucide-react';
import { renderChart } from '../recruitment/ChartRenderer';

const KnowledgeQAAgent = ({ projects = [] }) => {
  const { toast } = useToast();
  const safeProjects = Array.isArray(projects) ? projects : [];

  const INPUT_MODE_OPTIONS = [
    {
      value: 'search',
      label: 'Search',
      placeholder: 'Ask about projects, tasks, deadlines, people…',
      icon: Search,
    },
    {
      value: 'graph',
      label: 'Graph',
      placeholder: 'Describe the project graph you want to generate…',
      icon: BarChart2,
    },
  ];

  const [showSidebarSearch, setShowSidebarSearch] = useState(false);
  const [sidebarSearch, setSidebarSearch] = useState('');
  const [showChatHistory, setShowChatHistory] = useState(true);

  const [chats, setChats] = useState([]);
  const [selectedChatId, setSelectedChatId] = useState(null);
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingChats, setLoadingChats] = useState(true);
  const [inputMode, setInputMode] = useState('search');
  const [expandedGraph, setExpandedGraph] = useState(null); // { chart, chartTitle }
  const messagesEndRef = useRef(null);

  const selectedMode = INPUT_MODE_OPTIONS.find((m) => m.value === inputMode) || INPUT_MODE_OPTIONS[0];
  const SelectedModeIcon = selectedMode.icon;

  const normalizeChat = (chat) => {
    if (!chat) return chat;
    return {
      ...chat,
      id: String(chat.id),
      title: chat.title || 'Chat',
      messages: chat.messages || [],
      updatedAt: chat.updatedAt || chat.timestamp,
      timestamp: chat.updatedAt || chat.timestamp,
    };
  };

  const loadChatsFromApi = async () => {
    try {
      setLoadingChats(true);
      const res = await pmAgentService.listKnowledgeQAChats();
      if (res.status === 'success' && res.data) {
        setChats((res.data || []).map(normalizeChat));
      } else {
        setChats([]);
      }
    } catch (err) {
      console.error('Load Knowledge QA chats error:', err);
      setChats([]);
    } finally {
      setLoadingChats(false);
    }
  };

  useEffect(() => {
    loadChatsFromApi();
  }, []);

  const selectedChat = chats.find((c) => c.id === selectedChatId);
  const currentMessages = selectedChat?.messages ?? [];
  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  const getProjectTitle = (projectId) => {
    if (!projectId) return null;
    const p = safeProjects.find((x) => String(x.id) === String(projectId));
    return p ? (p.title || p.name) : null;
  };

  const handleSubmit = async (e) => {
    e?.preventDefault?.();
    if (!question.trim()) {
      toast({ title: 'Error', description: 'Please enter a question', variant: 'destructive' });
      return;
    }
    const q = question.trim();
    const projectId = selectedProjectId && selectedProjectId !== 'all' ? selectedProjectId : null;
    const projectTitle = getProjectTitle(projectId);

    try {
      setLoading(true);
      let assistantMsg;
      const userMsg = {
        role: 'user',
        content: q,
        responseData: projectTitle ? { project_id: projectId, project_title: projectTitle } : undefined,
      };

      if (inputMode === 'graph') {
        const graphRes = await pmAgentService.generateGraph(q, projectId ? Number(projectId) : null);
        if (graphRes.status === 'success' && graphRes.data) {
          const { chart, insights } = graphRes.data;
          assistantMsg = {
            role: 'assistant',
            content: chart?.title ? `**${chart.title}**` : 'Chart generated',
            responseData: {
              isGraph: true,
              chart,
              insights,
              chartTitle: chart?.title,
              chartType: chart?.type,
              project_id: projectId,
              project_title: projectTitle,
            },
          };
        } else {
          throw new Error(graphRes.message || 'Failed to generate graph');
        }
      } else {
        const response = await pmAgentService.knowledgeQA(q, projectId, currentMessages);
        if (response.status === 'success' && response.data) {
          const data = response.data;
          const answerText = data.answer || 'No answer provided.';
          assistantMsg = {
            role: 'assistant',
            content: answerText,
            responseData: {
              answer: answerText,
              project_id: projectId,
              project_title: projectTitle,
            },
          };
        } else {
          throw new Error(response.message || 'Failed to get response');
        }
      }

      const title = q.slice(0, 40);

      if (selectedChatId) {
        const existing = chats.find((c) => c.id === selectedChatId);
        if (existing) {
          const updRes = await pmAgentService.updateKnowledgeQAChat(selectedChatId, {
            messages: [userMsg, assistantMsg],
            title: existing.title || title,
          });
          if (updRes.status === 'success' && updRes.data) {
            const updatedChat = normalizeChat(updRes.data);
            setChats((prev) => [updatedChat, ...prev.filter((c) => c.id !== selectedChatId)]);
          } else throw new Error(updRes.message || 'Failed to save chat');
        } else {
          const createRes = await pmAgentService.createKnowledgeQAChat({ title, messages: [userMsg, assistantMsg] });
          if (createRes.status === 'success' && createRes.data) {
            const newChatData = normalizeChat(createRes.data);
            setChats((prev) => [newChatData, ...prev]);
            setSelectedChatId(newChatData.id);
          } else throw new Error(createRes.message || 'Failed to create chat');
        }
      } else {
        const createRes = await pmAgentService.createKnowledgeQAChat({ title, messages: [userMsg, assistantMsg] });
        if (createRes.status === 'success' && createRes.data) {
          const newChatData = normalizeChat(createRes.data);
          setChats((prev) => [newChatData, ...prev]);
          setSelectedChatId(newChatData.id);
        } else throw new Error(createRes.message || 'Failed to create chat');
      }
      setQuestion('');
      setTimeout(scrollToBottom, 100);
    } catch (error) {
      console.error('Knowledge Q&A error:', error);
      toast({
        title: 'Error',
        description: error?.message || 'Something went wrong. Please try again.',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const newChat = () => {
    setSelectedChatId(null);
    setQuestion('');
  };

  const deleteChat = async (e, chatId) => {
    e.stopPropagation();
    try {
      const res = await pmAgentService.deleteKnowledgeQAChat(chatId);
      if (res.status === 'success') {
        setChats((prev) => prev.filter((c) => c.id !== chatId));
        if (selectedChatId === chatId) setSelectedChatId(null);
        toast({ title: 'Chat deleted' });
      } else throw new Error(res.message || 'Failed to delete chat');
    } catch (err) {
      toast({ title: 'Error', description: err.message || 'Could not delete chat', variant: 'destructive' });
    }
  };

  const truncate = (s, n = 50) => (s.length <= n ? s : s.slice(0, n) + '…');
  const formatDate = (iso) => {
    try {
      const d = new Date(iso);
      return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  return (
    <div
      className="w-full rounded-2xl border border-white/[0.06] p-0 overflow-hidden"
      style={{
        background:
          'linear-gradient(90deg, #020308 0%, #020308 55%, rgba(10,37,64,0.68) 85%, rgba(14,39,71,0.52) 100%)',
      }}
    >
      <div className="flex w-full max-w-full relative max-h-[calc(100vh-40px)]">
        <div
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
          <div className="w-64 h-full flex flex-col">
            <div
              className="px-3 pt-3 pb-2 border-b border-white/15 flex flex-col gap-2 shrink-0"
              style={{
                background: 'linear-gradient(180deg, rgba(60, 30, 90, 0.22) 0%, rgba(36, 18, 54, 0.85) 100%)',
                borderTopLeftRadius: 16,
              }}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-base font-semibold text-white/90 tracking-wide">Payper Project</span>
                <button
                  onClick={() => setShowChatHistory(false)}
                  title="Close sidebar"
                  className="h-8 w-8 flex items-center justify-center rounded-full border border-white/20 hover:border-violet-400/60 bg-black/30 hover:bg-violet-700/20 transition-all duration-150"
                  style={{ boxShadow: '0 0 0 2px rgba(139,92,246,0.10) inset' }}
                >
                  <ChevronsLeft className="h-4 w-4 text-white/80" />
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
                    onClick={() => {
                      setSidebarSearch('');
                      setShowSidebarSearch(false);
                    }}
                    className="h-7 w-7 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60 bg-black/20 hover:bg-violet-700/20 transition-all duration-150"
                  >
                    <svg
                      width="16"
                      height="16"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="text-white/70"
                    >
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
                    <svg
                      width="16"
                      height="16"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="text-white/70"
                    >
                      <circle cx="7" cy="7" r="5" />
                      <line x1="15" y1="15" x2="11" y2="11" />
                    </svg>
                  </button>
                  <button
                    onClick={newChat}
                    title="New chat"
                    className="h-7 w-7 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60 bg-black/20 hover:bg-violet-700/20 transition-all duration-150"
                  >
                    <Plus className="h-4 w-4 text-white/80" />
                  </button>
                </div>
              )}
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto custom-sidebar-scroll">
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
                          boxShadow:
                            selectedChatId === c.id
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
                          onClick={(e) => deleteChat(e, c.id)}
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

        <Card className="flex-1 min-w-0 flex flex-col max-h-[calc(100vh-40px)] border-0 shadow-none" style={{ background: 'transparent' }}>
          <CardHeader
            className="shrink-0 flex flex-row items-start justify-between gap-3 border-b border-white/[0.07] px-0 py-4"
            style={{ background: 'transparent' }}
          >
            <div className="flex items-center gap-3 min-w-0 w-full">
              <div
                style={{
                  width: '7px',
                  height: '48px',
                  borderRadius: '8px',
                  background: 'linear-gradient(to bottom, #a259ff 0%, #6a1b9a 60%, #18122B 100%)',
                  marginLeft: '24px',
                  marginRight: '18px',
                  boxShadow: '0 0 8px 2px #a259ff44',
                }}
              />
              <div className="h-10 w-10 rounded-lg flex items-center justify-center shrink-0" style={{ background: 'rgba(124, 58, 237, 0.15)' }}>
                <Bot className="h-5 w-5" style={{ color: '#a78bfa' }} />
              </div>
              <div className="min-w-0">
                <CardTitle className="flex items-center gap-2 truncate text-white text-lg">
                  Knowledge Q&A Agent
                  <span
                    className="text-[10px] rounded-full px-2.5 py-0.5 font-medium"
                    style={{ background: 'rgba(124, 58, 237, 0.15)', color: '#a78bfa' }}
                  >
                    AI-Powered
                  </span>
                </CardTitle>
                <CardDescription className="text-white/50 text-sm mt-0.5">
                  Ask questions about projects, tasks, deadlines. Select a project (optional) to scope the answer.
                </CardDescription>
              </div>
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
                <>
                  <ChevronsLeft className="h-4 w-4" />
                  <span className="text-xs hidden sm:inline">Hide</span>
                </>
              ) : (
                <>
                  <ChevronsRight className="h-4 w-4" />
                  <span className="text-xs hidden sm:inline">History</span>
                </>
              )}
            </Button>
          </CardHeader>
          <CardContent className="p-0 flex flex-col flex-1 min-h-0">
            <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-4 py-4 space-y-4">
            {!selectedChatId && chats.length === 0 && (
              <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                <MessageCircle className="h-12 w-12 mb-4 opacity-50" />
                <p className="font-medium">Ask your first question</p>
                <p className="text-sm">Select a project (optional) and type your question below.</p>
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
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                    msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted border'
                  }`}
                >
                  {msg.role === 'user' ? (
                    <>
                      <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                      {msg.responseData?.project_title && (
                        <p className="text-xs opacity-80 mt-1">Project: {msg.responseData.project_title}</p>
                      )}
                    </>
                  ) : msg.responseData?.isGraph ? (
                    <>
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
                            <div className="pr-8 w-full min-w-0">
                              {renderChart(msg.responseData.chart)}
                            </div>
                          </div>
                        )}
                        {msg.responseData?.insights && (
                          <div className="pt-2 border-t border-border/50">
                            <p className="text-xs font-semibold mb-2">Insights</p>
                            <p className="text-xs text-muted-foreground whitespace-pre-wrap">{msg.responseData.insights}</p>
                          </div>
                        )}
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="text-sm text-foreground whitespace-pre-wrap break-words">
                        {msg.responseData?.answer ?? msg.content}
                      </div>
                      {msg.responseData?.project_title && (
                        <p className="text-xs text-muted-foreground mt-2">Scoped to: {msg.responseData.project_title}</p>
                      )}
                    </>
                  )}
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex justify-start">
                <div className="bg-muted border rounded-2xl px-4 py-3 flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span className="text-sm">Processing...</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
            </div>

            <form
              onSubmit={handleSubmit}
              className="shrink-0"
              style={{
                background: '#0a0a0f',
                borderTop: '1px solid rgba(255,255,255,0.08)',
              }}
            >
              <div className="mx-4 my-3 rounded-xl px-3 py-3" style={{ border: '1px solid rgba(255,255,255,0.08)' }}>
                {/* Top row: project select + mode side by side */}
                <div className="flex items-center gap-2 mb-2">
                  <Select value={selectedProjectId || 'all'} onValueChange={(v) => setSelectedProjectId(v === 'all' ? '' : v)}>
                    <SelectTrigger
                      className="h-8 text-xs flex-1 min-w-0"
                      style={{
                        background: '#111118',
                        border: '1.5px solid rgba(139, 92, 246, 0.35)',
                        color: '#e2e2f0',
                      }}
                    >
                      <SelectValue placeholder="All projects" />
                    </SelectTrigger>
                    <SelectContent
                      style={{
                        background: '#161630',
                        border: '1px solid rgba(139, 92, 246, 0.25)',
                        color: '#e2e2f0',
                      }}
                    >
                      <SelectItem value="all">General Questions</SelectItem>
                      {safeProjects.length > 0 ? (
                        safeProjects.map((project) => (
                          <SelectItem key={project.id} value={String(project.id)}>
                            {project.title || project.name}
                          </SelectItem>
                        ))
                      ) : (
                        <SelectItem value="none" disabled>No projects available</SelectItem>
                      )}
                    </SelectContent>
                  </Select>

                  <Select value={inputMode} onValueChange={setInputMode}>
                    <SelectTrigger
                      className="h-8 text-xs w-[130px] shrink-0"
                      style={{
                        background: '#111118',
                        border: '1.5px solid rgba(139, 92, 246, 0.35)',
                        color: '#e2e2f0',
                      }}
                    >
                      <div className="flex items-center gap-1.5">
                        <SelectedModeIcon className="h-3.5 w-3.5" style={{ color: '#a78bfa' }} />
                        <SelectValue placeholder="Search" />
                      </div>
                    </SelectTrigger>
                    <SelectContent
                      style={{
                        background: '#161630',
                        border: '1px solid rgba(139, 92, 246, 0.25)',
                        color: '#e2e2f0',
                      }}
                    >
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

                {/* Textarea + send */}
                <div className="flex gap-2">
                  <Textarea
                    placeholder={selectedMode.placeholder}
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        handleSubmit(e);
                      }
                    }}
                    rows={1}
                    disabled={loading}
                    className="min-h-[40px] resize-none flex-1 text-sm"
                    style={{
                      background: '#0e0e14',
                      border: '1px solid rgba(255, 255, 255, 0.1)',
                      color: '#e2e2f0',
                    }}
                  />
                  <Button type="submit" disabled={loading} size="icon" className="h-[40px] w-10 shrink-0">
                    {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  </Button>
                </div>
              </div>
            </form>

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
};

export default KnowledgeQAAgent;
