import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import pmAgentService from '@/services/pmAgentService';
import { Loader2, Send, MessageSquare, Plus, MessageCircle, Trash2 } from 'lucide-react';

const KnowledgeQAAgent = ({ projects = [] }) => {
  const { toast } = useToast();
  const safeProjects = Array.isArray(projects) ? projects : [];

  const [chats, setChats] = useState([]);
  const [selectedChatId, setSelectedChatId] = useState(null);
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingChats, setLoadingChats] = useState(true);
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
      const response = await pmAgentService.knowledgeQA(q, projectId, currentMessages);
      if (response.status === 'success' && response.data) {
        const data = response.data;
        const answerText = data.answer || 'No answer provided.';
        const userMsg = {
          role: 'user',
          content: q,
          responseData: projectTitle ? { project_id: projectId, project_title: projectTitle } : undefined,
        };
        const assistantMsg = {
          role: 'assistant',
          content: answerText,
          responseData: {
            answer: answerText,
            project_id: projectId,
            project_title: projectTitle,
          },
        };
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
      } else {
        throw new Error(response.message || 'Failed to get answer');
      }
    } catch (error) {
      toast({ title: 'Error', description: error.message || 'Failed to get answer', variant: 'destructive' });
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
    <div className="flex gap-4 w-full max-w-full">
      {/* Sidebar - Previous chats */}
      <div className="w-64 shrink-0 rounded-lg border bg-card">
        <div className="p-3 border-b flex items-center justify-between">
          <span className="text-sm font-semibold">Previous conversations</span>
          <Button variant="ghost" size="icon" onClick={newChat} title="New chat">
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        <div>
          {loadingChats ? (
            <div className="p-4 flex justify-center">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : chats.length === 0 ? (
            <div className="p-4 text-center text-sm text-muted-foreground">No conversations yet. Ask a question to start.</div>
          ) : (
            <div className="p-2 space-y-1">
              {chats.map((c) => (
                <div
                  key={c.id}
                  className={`flex items-center gap-1 rounded-lg text-sm transition-colors ${
                    selectedChatId === c.id ? 'bg-primary/10 border border-primary/20' : 'hover:bg-muted'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => setSelectedChatId(c.id)}
                    className="flex-1 min-w-0 text-left p-3 rounded-lg"
                  >
                    <div className="font-medium truncate">{truncate(c.title || (c.messages?.[0]?.content) || 'Chat', 40)}</div>
                    <div className="text-xs text-muted-foreground mt-0.5">{formatDate(c.updatedAt || c.timestamp)}</div>
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
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Main chat area */}
      <Card className="flex-1 min-w-0">
        <CardHeader className="shrink-0">
          <CardTitle className="flex items-center gap-2">
            <MessageSquare className="h-5 w-5 text-primary" />
            Knowledge Q&A Agent
          </CardTitle>
          <CardDescription>
            Ask questions about your projects, tasks, deadlines. Select a project (optional) to scope the answer. Previous conversations are in the sidebar.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="px-4 pb-4 space-y-4">
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

          <form onSubmit={handleSubmit} className="shrink-0 border-t p-4 space-y-3 bg-muted/30">
            <div>
              <label className="text-sm font-medium mb-1 block">Select Project (optional)</label>
              <Select value={selectedProjectId || 'all'} onValueChange={(v) => setSelectedProjectId(v === 'all' ? '' : v)}>
                <SelectTrigger className="mb-2">
                  <SelectValue placeholder="General Questions" />
                </SelectTrigger>
                <SelectContent>
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
            </div>
            <div className="flex gap-2">
              <Textarea
                placeholder="e.g., What tasks are overdue? What's the status of my project?"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSubmit(e);
                  }
                }}
                rows={2}
                disabled={loading}
                className="min-h-[60px] resize-none flex-1"
              />
              <Button type="submit" disabled={loading} size="icon" className="h-[60px] w-12 shrink-0">
                {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
};

export default KnowledgeQAAgent;
