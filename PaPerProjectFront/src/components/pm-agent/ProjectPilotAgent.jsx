import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import pmAgentService from '@/services/pmAgentService';
import { Loader2, Send, Sparkles, Plus, MessageCircle, Trash2, Upload, FileText, X, CheckCircle2, XCircle } from 'lucide-react';

const ProjectPilotAgent = ({ projects = [], onProjectUpdate }) => {
  const { toast } = useToast();
  const safeProjects = Array.isArray(projects) ? projects : [];

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
    <div className="flex gap-4 w-full max-w-full">
      {/* Sidebar */}
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
            <div className="p-4 text-center text-sm text-muted-foreground">No conversations yet. Send a request or upload a file to start.</div>
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
            <Sparkles className="h-5 w-5 text-primary" />
            Project Pilot Agent
          </CardTitle>
          <CardDescription>
            Create projects and tasks with natural language or upload a document (txt, pdf, docx). Select a project (optional) to scope actions. Previous conversations are in the sidebar.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="px-4 pb-4 space-y-4">
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

          {/* Form: file upload + project + text request */}
          <div className="shrink-0 border-t p-4 space-y-3 bg-muted/30">
            {/* File upload */}
            <div className="p-3 border rounded-lg bg-background/50 space-y-2">
              <label className="text-sm font-medium flex items-center gap-2">
                <Upload className="h-4 w-4" />
                Upload document (txt, pdf, docx)
              </label>
              {!selectedFile ? (
                <>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".txt,.pdf,.docx"
                    onChange={handleFileSelect}
                    className="hidden"
                    id="pilot-file-upload"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    className="w-full"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <Upload className="h-4 w-4 mr-2" />
                    Choose file
                  </Button>
                </>
              ) : (
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <FileText className="h-4 w-4 shrink-0 text-primary" />
                    <span className="text-sm truncate">{selectedFile.name}</span>
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <Button
                      type="button"
                      size="sm"
                      disabled={fileLoading}
                      onClick={handleFileUpload}
                    >
                      {fileLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                      <span className="ml-1">{fileLoading ? 'Processing...' : 'Process file'}</span>
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => { setSelectedFile(null); if (fileInputRef.current) fileInputRef.current.value = ''; }}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              )}
            </div>

            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <span className="w-full border-t" />
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="bg-muted/30 px-2 text-muted-foreground">Or type a request</span>
              </div>
            </div>

            <div>
              <label className="text-sm font-medium mb-1 block">Select project (optional)</label>
              <Select value={selectedProjectId || 'all'} onValueChange={(v) => setSelectedProjectId(v === 'all' ? '' : v)}>
                <SelectTrigger className="mb-2">
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
            </div>

            <form onSubmit={handleSubmit} className="flex gap-2">
              <Textarea
                placeholder="e.g., Create a new project 'Website Redesign' with high priority..."
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSubmit(e);
                  }
                }}
                rows={2}
                disabled={loading || fileLoading}
                className="min-h-[60px] resize-none flex-1"
              />
              <Button type="submit" disabled={loading || fileLoading} size="icon" className="h-[60px] w-12 shrink-0">
                {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
              </Button>
            </form>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default ProjectPilotAgent;
