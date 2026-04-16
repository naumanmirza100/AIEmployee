import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import pmAgentService from '@/services/pmAgentService';
import { Loader2, Send, Sparkles, Plus, MessageCircle, Trash2, Upload, FileText, X, CheckCircle2, XCircle, ChevronsLeft, ChevronsRight, Bot } from 'lucide-react';

const ProjectPilotAgent = ({ projects = [], onProjectUpdate }) => {
  const { toast } = useToast();
  const safeProjects = Array.isArray(projects) ? projects : [];

  const [showSidebarSearch, setShowSidebarSearch] = useState(false);
  const [sidebarSearch, setSidebarSearch] = useState('');
  const [showChatHistory, setShowChatHistory] = useState(true);

  const [chats, setChats] = useState([]);
  const [selectedChatId, setSelectedChatId] = useState(null);
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [fileLoading, setFileLoading] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [loadingChats, setLoadingChats] = useState(true);
  const fileInputRef = useRef(null);
  const messagesEndRef = useRef(null);

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
      const res = await pmAgentService.listProjectPilotChats();
      if (res.status === 'success' && res.data) {
        setChats((res.data || []).map(normalizeChat));
      } else {
        setChats([]);
      }
    } catch (err) {
      console.error('Load Project Pilot chats error:', err);
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

  const addMessagePairToChat = async (userMsg, assistantMsg, titleSnippet) => {
    const title = titleSnippet.slice(0, 40);
    if (selectedChatId) {
      const existing = chats.find((c) => c.id === selectedChatId);
      if (existing) {
        const updRes = await pmAgentService.updateProjectPilotChat(selectedChatId, {
          messages: [userMsg, assistantMsg],
          title: existing.title || title,
        });
        if (updRes.status === 'success' && updRes.data) {
          const updatedChat = normalizeChat(updRes.data);
          setChats((prev) => [updatedChat, ...prev.filter((c) => c.id !== selectedChatId)]);
        } else throw new Error(updRes.message || 'Failed to save chat');
      } else {
        const createRes = await pmAgentService.createProjectPilotChat({ title, messages: [userMsg, assistantMsg] });
        if (createRes.status === 'success' && createRes.data) {
          const newChatData = normalizeChat(createRes.data);
          setChats((prev) => [newChatData, ...prev]);
          setSelectedChatId(newChatData.id);
        } else throw new Error(createRes.message || 'Failed to create chat');
      }
    } else {
      const createRes = await pmAgentService.createProjectPilotChat({ title, messages: [userMsg, assistantMsg] });
      if (createRes.status === 'success' && createRes.data) {
        const newChatData = normalizeChat(createRes.data);
        setChats((prev) => [newChatData, ...prev]);
        setSelectedChatId(newChatData.id);
      } else throw new Error(createRes.message || 'Failed to create chat');
    }
    setQuestion('');
    setSelectedFile(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
    setTimeout(scrollToBottom, 100);
  };

  const handleSubmit = async (e) => {
    e?.preventDefault?.();
    if (!question.trim()) {
      toast({ title: 'Error', description: 'Please enter a request', variant: 'destructive' });
      return;
    }
    const q = question.trim();
    const projectId = selectedProjectId && selectedProjectId !== 'all' ? selectedProjectId : null;
    const projectTitle = getProjectTitle(projectId);

    try {
      setLoading(true);
      const response = await pmAgentService.projectPilot(q, projectId, currentMessages);
      if (response.status === 'success') {
        const data = response.data || response;
        const answerText = data.answer || '';
        const actionResults = data.action_results || response.action_results || [];
        const cannotDo = data.cannot_do || response.cannot_do;
        const userMsg = {
          role: 'user',
          content: q,
          responseData: projectTitle ? { project_id: projectId, project_title: projectTitle } : undefined,
        };
        const assistantMsg = {
          role: 'assistant',
          content: answerText || (cannotDo || 'No response.'),
          responseData: {
            answer: answerText,
            action_results: actionResults,
            cannot_do: cannotDo,
            project_id: projectId,
            project_title: projectTitle,
          },
        };
        await addMessagePairToChat(userMsg, assistantMsg, q);
        if (actionResults.some((r) => r.success) && onProjectUpdate) onProjectUpdate();
      } else {
        throw new Error(response.message || 'Failed to process request');
      }
    } catch (error) {
      toast({ title: 'Error', description: error.message || 'Failed to process request', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const handleFileSelect = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const allowed = ['.txt', '.pdf', '.docx'];
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!allowed.includes(ext)) {
      toast({ title: 'Invalid file type', description: `Use ${allowed.join(', ')}`, variant: 'destructive' });
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      toast({ title: 'File too large', description: 'Max 10MB', variant: 'destructive' });
      return;
    }
    setSelectedFile(file);
  };

  const handleFileUpload = async () => {
    if (!selectedFile) {
      toast({ title: 'Error', description: 'Please select a file', variant: 'destructive' });
      return;
    }
    const projectId = selectedProjectId && selectedProjectId !== 'all' ? selectedProjectId : null;
    const projectTitle = getProjectTitle(projectId);

    try {
      setFileLoading(true);
      const response = await pmAgentService.projectPilotFromFile(selectedFile, projectId, currentMessages);
      if (response.status === 'success') {
        const data = response.data || response;
        const answerText = data.answer || '';
        const actionResults = data.action_results || [];
        const cannotDo = data.cannot_do;
        const userMsg = {
          role: 'user',
          content: `Uploaded file: ${selectedFile.name}`,
          responseData: {
            from_file: true,
            file_name: selectedFile.name,
            project_id: projectId,
            project_title: projectTitle,
          },
        };
        const assistantMsg = {
          role: 'assistant',
          content: answerText || (cannotDo || 'Processed.'),
          responseData: {
            answer: answerText,
            action_results: actionResults,
            cannot_do: cannotDo,
            project_id: projectId,
            project_title: projectTitle,
            from_file: true,
            file_name: selectedFile.name,
          },
        };
        await addMessagePairToChat(userMsg, assistantMsg, `File: ${selectedFile.name}`);
        if (actionResults.some((r) => r.success) && onProjectUpdate) onProjectUpdate();
      } else {
        throw new Error(response.message || 'Failed to process file');
      }
    } catch (error) {
      toast({ title: 'Error', description: error.message || 'Failed to process file', variant: 'destructive' });
    } finally {
      setFileLoading(false);
    }
  };

  const newChat = () => {
    setSelectedChatId(null);
    setQuestion('');
    setSelectedFile(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const deleteChat = async (e, chatId) => {
    e.stopPropagation();
    try {
      const res = await pmAgentService.deleteProjectPilotChat(chatId);
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
                <div className="p-4 text-center text-sm text-muted-foreground">No conversations yet. Send a request or upload a file to start.</div>
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
                  Project Pilot Agent
                  <span
                    className="text-[10px] rounded-full px-2.5 py-0.5 font-medium"
                    style={{ background: 'rgba(124, 58, 237, 0.15)', color: '#a78bfa' }}
                  >
                    AI-Powered
                  </span>
                </CardTitle>
                <CardDescription className="text-white/50 text-sm mt-0.5">
                  Create projects and tasks with natural language or upload a document (txt, pdf, docx). Select a project (optional) to scope actions.
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
                <p className="font-medium">Send your first request</p>
                <p className="text-sm">Type a request below or upload a file.</p>
              </div>
            )}
            {!selectedChatId && chats.length > 0 && (
              <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                <MessageCircle className="h-12 w-12 mb-4 opacity-50" />
                <p className="font-medium">Select a conversation or send a new request</p>
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
                      {(msg.responseData?.project_title || msg.responseData?.file_name) && (
                        <p className="text-xs opacity-80 mt-1">
                          {msg.responseData.file_name && `File: ${msg.responseData.file_name}`}
                          {msg.responseData.file_name && msg.responseData.project_title && ' · '}
                          {msg.responseData.project_title && `Project: ${msg.responseData.project_title}`}
                        </p>
                      )}
                    </>
                  ) : (
                    <div className="space-y-2">
                      {(msg.responseData?.answer) && (() => {
                        const a = msg.responseData.answer;
                        const looksLikeJson = typeof a === 'string' && (a.trim().startsWith('{') || a.trim().startsWith('['));
                        if (looksLikeJson) return null;
                        return <p className="text-sm whitespace-pre-wrap">{a}</p>;
                      })()}
                      {!(msg.responseData?.answer && typeof msg.responseData.answer === 'string' && !msg.responseData.answer.trim().startsWith('[') && !msg.responseData.answer.trim().startsWith('{')) && !(msg.responseData?.action_results?.length > 0) && msg.content && (
                        <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                      )}
                      {(msg.responseData?.action_results?.length > 0) && (
                        <div className="space-y-2 mt-2">
                          {msg.responseData.action_results.map((action, idx) => {
                            const isTaskAction = action.action === 'create_task' || action.action === 'update_task';
                            const formatDate = (iso) => {
                              if (!iso) return '—';
                              try {
                                const d = new Date(iso);
                                return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
                              } catch {
                                return iso;
                              }
                            };
                            const assigneeDisplay = action.assignee_name || action.assignee_username || 'Unassigned';
                            const priorityDisplay = action.priority ? String(action.priority).replace(/_/g, ' ') : '—';
                            return (
                              <div
                                key={idx}
                                className={`p-3 rounded border text-sm ${
                                  action.success ? 'bg-green-50 border-green-200 dark:bg-green-950/50 dark:border-green-800' : 'bg-red-50 border-red-200 dark:bg-red-950/50 dark:border-red-800'
                                }`}
                              >
                                <div className="flex items-start gap-2">
                                  {action.success ? (
                                    <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400 mt-0.5 shrink-0" />
                                  ) : (
                                    <XCircle className="h-4 w-4 text-red-600 dark:text-red-400 mt-0.5 shrink-0" />
                                  )}
                                  <div className="flex-1 min-w-0">
                                    <Badge variant={action.success ? 'default' : 'destructive'} className="mb-1.5">
                                      {action.action?.replace(/_/g, ' ') || 'Action'}
                                    </Badge>
                                    {(action.message || action.error) && (
                                      <p className="text-xs text-muted-foreground mb-2">{action.message || action.error}</p>
                                    )}
                                    {isTaskAction && (
                                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 text-xs text-muted-foreground">
                                        <span><strong className="text-foreground">Priority:</strong> {priorityDisplay}</span>
                                        <span><strong className="text-foreground">Assigned to:</strong> {assigneeDisplay}</span>
                                        <span><strong className="text-foreground">Deadline:</strong> {formatDate(action.due_date)}</span>
                                        <span><strong className="text-foreground">Start:</strong> {formatDate(action.created_at)}</span>
                                      </div>
                                    )}
                                    {action.project_name && !isTaskAction && (
                                      <p className="text-xs text-muted-foreground mt-1">Project: {action.project_name}</p>
                                    )}
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                      {msg.responseData?.cannot_do && (
                        <p className="text-sm text-yellow-700 dark:text-yellow-300 mt-2">{msg.responseData.cannot_do}</p>
                      )}
                      {(msg.responseData?.project_title || msg.responseData?.file_name) && (
                        <p className="text-xs text-muted-foreground mt-2">
                          {msg.responseData.file_name && `File: ${msg.responseData.file_name}`}
                          {msg.responseData.file_name && msg.responseData.project_title && ' · '}
                          {msg.responseData.project_title && `Project: ${msg.responseData.project_title}`}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {(loading || fileLoading) && (
              <div className="flex justify-start">
                <div className="bg-muted border rounded-2xl px-4 py-3 flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span className="text-sm">{fileLoading ? 'Processing file...' : 'Processing...'}</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
            </div>

            <div
              className="shrink-0"
              style={{
                background: '#0a0a0f',
                borderTop: '1px solid rgba(255,255,255,0.08)',
              }}
            >
            {/* Compact input area: project select + file upload + textarea */}
            <div className="mx-4 my-3 rounded-xl px-3 py-3" style={{ border: '1px solid rgba(255,255,255,0.08)' }}>
            {/* Top row: project select + file upload side by side */}
            <div className="flex items-center gap-2 mb-2">
              <Select value={selectedProjectId || 'all'} onValueChange={(v) => setSelectedProjectId(v === 'all' ? '' : v)}>
                <SelectTrigger className="h-8 text-xs flex-1 min-w-0">
                  <SelectValue placeholder="All projects" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All projects</SelectItem>
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

              <input
                ref={fileInputRef}
                type="file"
                accept=".txt,.pdf,.docx"
                onChange={handleFileSelect}
                className="hidden"
                id="pilot-file-upload"
              />
              {!selectedFile ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8 text-xs shrink-0"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload className="h-3.5 w-3.5 mr-1" />
                  Upload
                </Button>
              ) : (
                <div className="flex items-center gap-1 shrink-0">
                  <FileText className="h-3.5 w-3.5 text-primary shrink-0" />
                  <span className="text-xs truncate max-w-[80px]">{selectedFile.name}</span>
                  <Button
                    type="button"
                    size="sm"
                    className="h-7 text-xs px-2"
                    disabled={fileLoading}
                    onClick={handleFileUpload}
                  >
                    {fileLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Send className="h-3 w-3" />}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={() => { setSelectedFile(null); if (fileInputRef.current) fileInputRef.current.value = ''; }}
                  >
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              )}
            </div>

            {/* Textarea + send */}
            <form onSubmit={handleSubmit} className="flex gap-2">
              <Textarea
                placeholder="e.g., Create a new project 'Website Redesign' with high priority..."
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if ((e.key === 'Enter' && !e.shiftKey) || (e.key === 'Enter' && (e.ctrlKey || e.metaKey))) {
                    e.preventDefault();
                    handleSubmit(e);
                  }
                }}
                rows={1}
                disabled={loading || fileLoading}
                className="min-h-[40px] resize-none flex-1 text-sm"
              />
              <Button type="submit" disabled={loading || fileLoading} size="icon" className="h-[40px] w-10 shrink-0">
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </Button>
            </form>
            </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default ProjectPilotAgent;
