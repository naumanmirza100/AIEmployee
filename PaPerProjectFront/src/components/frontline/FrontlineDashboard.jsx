import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import { 
  Loader2, 
  FileText, 
  Upload, 
  MessageSquare,
  Ticket,
  Search,
  Trash2,
  Headphones,
  CheckCircle2,
  XCircle,
  Send,
  Plus,
  MessageCircle
} from 'lucide-react';
import frontlineAgentService from '@/services/frontlineAgentService';

const FrontlineDashboard = () => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [activeTab, setActiveTab] = useState('overview');
  const [isDarkMode, setIsDarkMode] = useState(false);
  
  // Document upload
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadTitle, setUploadTitle] = useState('');
  const [uploadDescription, setUploadDescription] = useState('');
  
  // Knowledge Q&A (chat-based)
  const [chats, setChats] = useState([]);
  const [selectedChatId, setSelectedChatId] = useState(null);
  const [question, setQuestion] = useState('');
  const [answering, setAnswering] = useState(false);
  const [loadingChats, setLoadingChats] = useState(false);
  const messagesEndRef = useRef(null);
  
  // Ticket creation
  const [showTicketDialog, setShowTicketDialog] = useState(false);
  const [ticketTitle, setTicketTitle] = useState('');
  const [ticketDescription, setTicketDescription] = useState('');
  const [creatingTicket, setCreatingTicket] = useState(false);


  useEffect(() => {
    fetchDashboard();
    
    // Check for dark mode
    const checkDarkMode = () => {
      setIsDarkMode(
        document.documentElement.classList.contains('dark') ||
        window.matchMedia('(prefers-color-scheme: dark)').matches
      );
    };
    
    checkDarkMode();
    
    // Watch for dark mode changes
    const observer = new MutationObserver(checkDarkMode);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class']
    });
    
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    mediaQuery.addEventListener('change', checkDarkMode);
    
    return () => {
      observer.disconnect();
      mediaQuery.removeEventListener('change', checkDarkMode);
    };
  }, []);

  const fetchDashboard = async () => {
    try {
      setLoading(true);
      const response = await frontlineAgentService.getFrontlineDashboard();
      if (response.status === 'success') {
        setStats(response.data.stats);
        setDocuments(response.data.recent_documents || []);
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to load dashboard',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async () => {
    if (!uploadFile) {
      toast({
        title: 'Error',
        description: 'Please select a file to upload',
        variant: 'destructive',
      });
      return;
    }

    try {
      setUploading(true);
      const response = await frontlineAgentService.uploadDocument(
        uploadFile,
        uploadTitle || uploadFile.name,
        uploadDescription,
        'knowledge_base'
      );

      if (response.status === 'success') {
        toast({
          title: 'Success!',
          description: 'Document uploaded and processed successfully',
        });
        setShowUploadDialog(false);
        setUploadFile(null);
        setUploadTitle('');
        setUploadDescription('');
        fetchDashboard();
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to upload document',
        variant: 'destructive',
      });
    } finally {
      setUploading(false);
    }
  };

  const handleDeleteDocument = async (documentId) => {
    if (!confirm('Are you sure you want to delete this document?')) {
      return;
    }

    try {
      const response = await frontlineAgentService.deleteDocument(documentId);
      if (response.status === 'success') {
        toast({
          title: 'Success!',
          description: 'Document deleted successfully',
        });
        fetchDashboard();
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to delete document',
        variant: 'destructive',
      });
    }
  };

  /** Normalize chat from API shape to component shape */
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
      const res = await frontlineAgentService.listQAChats();
      if (res.status === 'success' && res.data) {
        setChats((res.data || []).map(normalizeChat));
      } else {
        setChats([]);
      }
    } catch (err) {
      console.error('Load QA chats error:', err);
      setChats([]);
    } finally {
      setLoadingChats(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'qa') {
      loadChatsFromApi();
    }
  }, [activeTab]);

  const selectedChat = chats.find((c) => c.id === selectedChatId);
  const currentMessages = selectedChat?.messages ?? [];
  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  const newChat = () => {
    setSelectedChatId(null);
    setQuestion('');
  };

  const deleteChat = async (e, chatId) => {
    e.stopPropagation();
    try {
      const res = await frontlineAgentService.deleteQAChat(chatId);
      if (res.status === 'success') {
        setChats((prev) => prev.filter((c) => c.id !== chatId));
        if (selectedChatId === chatId) setSelectedChatId(null);
        toast({ title: 'Chat deleted' });
      } else {
        throw new Error(res.message || 'Failed to delete chat');
      }
    } catch (err) {
      toast({ title: 'Error', description: err.message || 'Could not delete chat', variant: 'destructive' });
    }
  };

  const handleAskQuestion = async (e) => {
    e?.preventDefault?.();
    if (!question.trim()) {
      toast({ title: 'Error', description: 'Please enter a question', variant: 'destructive' });
      return;
    }
    const q = question.trim();
    try {
      setAnswering(true);
      const response = await frontlineAgentService.knowledgeQA(q);
      if (response.status === 'success' && response.data) {
        const data = response.data;
        const answerText = data.answer || 'No answer available.';
        const userMsg = { role: 'user', content: q };
        const assistantMsg = {
          role: 'assistant',
          content: answerText,
          responseData: {
            answer: answerText,
            has_verified_info: data.has_verified_info || false,
            source: data.source || 'Knowledge Base',
            type: data.type || 'general',
          },
        };
        const title = q.slice(0, 40);
        if (selectedChatId) {
          const existing = chats.find((c) => c.id === selectedChatId);
          if (existing) {
            const updRes = await frontlineAgentService.updateQAChat(selectedChatId, {
              messages: [userMsg, assistantMsg],
              title: existing.title || title,
            });
            if (updRes.status === 'success' && updRes.data) {
              const updatedChat = normalizeChat(updRes.data);
              setChats((prev) => [updatedChat, ...prev.filter((c) => c.id !== selectedChatId)]);
            } else throw new Error(updRes.message || 'Failed to save chat');
          } else {
            const createRes = await frontlineAgentService.createQAChat({ title, messages: [userMsg, assistantMsg] });
            if (createRes.status === 'success' && createRes.data) {
              const newChatData = normalizeChat(createRes.data);
              setChats((prev) => [newChatData, ...prev]);
              setSelectedChatId(newChatData.id);
            } else throw new Error(createRes.message || 'Failed to create chat');
          }
        } else {
          const createRes = await frontlineAgentService.createQAChat({ title, messages: [userMsg, assistantMsg] });
          if (createRes.status === 'success' && createRes.data) {
            const newChatData = normalizeChat(createRes.data);
            setChats((prev) => [newChatData, ...prev]);
            setSelectedChatId(newChatData.id);
          } else throw new Error(createRes.message || 'Failed to create chat');
        }
        setQuestion('');
        setTimeout(scrollToBottom, 100);
      } else {
        throw new Error(response.message || 'Failed to get response');
      }
    } catch (error) {
      toast({ title: 'Error', description: error.message || 'Failed to get answer', variant: 'destructive' });
    } finally {
      setAnswering(false);
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

  const handleCreateTicket = async () => {
    if (!ticketDescription.trim()) {
      toast({
        title: 'Error',
        description: 'Please enter a description',
        variant: 'destructive',
      });
      return;
    }

    try {
      setCreatingTicket(true);
      const response = await frontlineAgentService.createTicket(
        ticketTitle || 'Support Request',
        ticketDescription
      );

      if (response.status === 'success' && response.data) {
        toast({
          title: response.data.auto_resolved ? 'Ticket Auto-Resolved!' : 'Ticket Created!',
          description: response.data.response || 'Your ticket has been processed',
        });
        setShowTicketDialog(false);
        setTicketTitle('');
        setTicketDescription('');
        fetchDashboard();
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to create ticket',
        variant: 'destructive',
      });
    } finally {
      setCreatingTicket(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Stats Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Documents</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.total_documents || 0}</div>
            <p className="text-xs text-muted-foreground">
              {stats?.indexed_documents || 0} indexed
            </p>
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Tickets</CardTitle>
            <Ticket className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.total_tickets || 0}</div>
            <p className="text-xs text-muted-foreground">
              {stats?.open_tickets || 0} open, {stats?.resolved_tickets || 0} resolved
            </p>
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Auto-Resolved</CardTitle>
            <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.auto_resolved_tickets || 0}</div>
            <p className="text-xs text-muted-foreground">
              Automatically resolved tickets
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Main Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="documents">Documents</TabsTrigger>
          <TabsTrigger value="qa">Knowledge Q&A</TabsTrigger>
          <TabsTrigger value="tickets">Tickets</TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Welcome to Frontline Agent</CardTitle>
              <CardDescription>
                AI-powered customer support system for handling tickets and answering questions
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Button onClick={() => setShowUploadDialog(true)} className="w-full">
                  <Upload className="mr-2 h-4 w-4" />
                  Upload Document
                </Button>
                <Button onClick={() => setActiveTab('qa')} variant="outline" className="w-full">
                  <MessageSquare className="mr-2 h-4 w-4" />
                  Ask a Question
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Recent Documents */}
          {documents.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Recent Documents</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {documents.slice(0, 5).map((doc) => (
                    <div key={doc.id} className="flex items-center justify-between p-2 border rounded">
                      <div className="flex items-center space-x-2">
                        <FileText className="h-4 w-4" />
                        <span className="text-sm">{doc.title}</span>
                        {doc.is_indexed && (
                          <span className="text-xs text-green-600">Indexed</span>
                        )}
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDeleteDocument(doc.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Documents Tab */}
        <TabsContent value="documents" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Documents</CardTitle>
                <CardDescription>Upload and manage knowledge base documents</CardDescription>
              </div>
              <Button onClick={() => setShowUploadDialog(true)}>
                <Upload className="mr-2 h-4 w-4" />
                Upload Document
              </Button>
            </CardHeader>
            <CardContent>
              {documents.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  No documents uploaded yet. Upload your first document to get started.
                </div>
              ) : (
                <div className="space-y-2">
                  {documents.map((doc) => (
                    <div key={doc.id} className="flex items-center justify-between p-3 border rounded">
                      <div className="flex items-center space-x-3">
                        <FileText className="h-5 w-5" />
                        <div>
                          <div className="font-medium">{doc.title}</div>
                          <div className="text-sm text-muted-foreground">
                            {doc.file_format.toUpperCase()} • {doc.document_type}
                            {doc.is_indexed && ' • Indexed'}
                          </div>
                        </div>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDeleteDocument(doc.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Knowledge Q&A Tab - Chat UI with sidebar (like Recruitment AI questions) */}
        <TabsContent value="qa" className="space-y-4">
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
                  <MessageSquare className="h-5 w-5" />
                  Knowledge Q&A
                </CardTitle>
                <CardDescription>
                  Ask questions and get answers from your knowledge base and uploaded documents. Previous conversations are shown in the sidebar.
                </CardDescription>
              </CardHeader>
              <CardContent className="p-0">
                <div className="px-4 pb-4 space-y-4">
                  {!selectedChatId && chats.length === 0 && (
                    <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                      <MessageCircle className="h-12 w-12 mb-4 opacity-50" />
                      <p className="font-medium">Ask your first question</p>
                      <p className="text-sm">Type a question to get an answer from your knowledge base.</p>
                      {documents.length === 0 && (
                        <p className="text-xs mt-2 text-yellow-600 dark:text-yellow-400">💡 Tip: Upload documents in the Documents tab first</p>
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
                    <div
                      key={i}
                      className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                    >
                      <div
                        className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                          msg.role === 'user'
                            ? 'bg-primary text-primary-foreground'
                            : 'bg-muted border'
                        }`}
                      >
                        {msg.role === 'user' ? (
                          <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                        ) : (
                          <>
                            <div className="flex items-start gap-2">
                              {(msg.responseData?.has_verified_info) ? (
                                <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400 mt-0.5 flex-shrink-0" />
                              ) : (
                                <XCircle className="h-4 w-4 text-yellow-600 dark:text-yellow-400 mt-0.5 flex-shrink-0" />
                              )}
                              <div className="flex-1 min-w-0">
                                <div className="text-sm text-foreground whitespace-pre-wrap break-words">
                                  {msg.responseData?.answer ?? msg.content}
                                </div>
                                {msg.responseData?.source && (
                                  <p className="text-xs text-muted-foreground mt-2">Source: {msg.responseData.source}</p>
                                )}
                              </div>
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                  {answering && (
                    <div className="flex justify-start">
                      <div className="bg-muted border rounded-2xl px-4 py-3 flex items-center gap-2">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        <span className="text-sm">Searching knowledge base...</span>
                      </div>
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                </div>

                <form onSubmit={handleAskQuestion} className="shrink-0 border-t p-4 space-y-3 bg-muted/30">
                  <div className="flex gap-2">
                    <Textarea
                      placeholder="Ask a question from your knowledge base..."
                      value={question}
                      onChange={(e) => setQuestion(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleAskQuestion(e); } }}
                      rows={2}
                      disabled={answering}
                      className="min-h-[60px] resize-none"
                    />
                    <Button type="submit" disabled={answering} size="icon" className="h-[60px] w-12 shrink-0">
                      {answering ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Tickets Tab */}
        <TabsContent value="tickets" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Support Tickets</CardTitle>
                <CardDescription>Create and manage support tickets</CardDescription>
              </div>
              <Button onClick={() => setShowTicketDialog(true)}>
                <Ticket className="mr-2 h-4 w-4" />
                Create Ticket
              </Button>
            </CardHeader>
            <CardContent>
              <div className="text-center py-8 text-muted-foreground">
                Ticket management interface coming soon
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Upload Document Dialog */}
      <Dialog open={showUploadDialog} onOpenChange={setShowUploadDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Upload Document</DialogTitle>
            <DialogDescription>
              Upload a document to add it to your knowledge base. Supported formats: PDF, DOCX, TXT, MD, HTML
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="file">File</Label>
              <Input
                id="file"
                type="file"
                accept=".pdf,.docx,.doc,.txt,.md,.html"
                onChange={(e) => setUploadFile(e.target.files[0])}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="title">Title (optional)</Label>
              <Input
                id="title"
                placeholder="Document title"
                value={uploadTitle}
                onChange={(e) => setUploadTitle(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">Description (optional)</Label>
              <Textarea
                id="description"
                placeholder="Document description"
                value={uploadDescription}
                onChange={(e) => setUploadDescription(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowUploadDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleFileUpload} disabled={uploading || !uploadFile}>
              {uploading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Uploading...
                </>
              ) : (
                <>
                  <Upload className="mr-2 h-4 w-4" />
                  Upload
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create Ticket Dialog */}
      <Dialog open={showTicketDialog} onOpenChange={setShowTicketDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Support Ticket</DialogTitle>
            <DialogDescription>
              Describe your issue and we'll help you resolve it
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="ticket-title">Title (optional)</Label>
              <Input
                id="ticket-title"
                placeholder="Brief title for your issue"
                value={ticketTitle}
                onChange={(e) => setTicketTitle(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ticket-description">Description</Label>
              <Textarea
                id="ticket-description"
                placeholder="Describe your issue in detail..."
                value={ticketDescription}
                onChange={(e) => setTicketDescription(e.target.value)}
                rows={5}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowTicketDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateTicket} disabled={creatingTicket || !ticketDescription.trim()}>
              {creatingTicket ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <Send className="mr-2 h-4 w-4" />
                  Create Ticket
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default FrontlineDashboard;

