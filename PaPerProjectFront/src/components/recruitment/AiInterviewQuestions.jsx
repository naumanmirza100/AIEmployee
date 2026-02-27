import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/components/ui/use-toast';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Loader2, Send, MessageSquare, Plus, MessageCircle, Trash2, Search, BarChart2, Save, LayoutDashboard, PanelLeftClose, PanelLeftOpen, Maximize2 } from 'lucide-react';
import { recruitmentQA, listQAChats, createQAChat, updateQAChat, deleteQAChat, generateGraph, savePrompt } from '@/services/recruitmentAgentService';
import { renderChart } from './ChartRenderer';

/** Markdown to HTML for Q&A answers - proper heading, subheading, lists, tables */
function markdownToHtml(markdown) {
  if (!markdown || typeof markdown !== 'string') return '';
  const escape = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const bold = (s) => s.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-foreground">$1</strong>');
  const lines = markdown.split('\n');
  const out = [];
  let inList = false;
  let listType = null; // 'ul' | 'ol'
  let i = 0;
  const closeList = () => {
    if (inList) {
      out.push(listType === 'ol' ? '</ol>' : '</ul>');
      inList = false;
      listType = null;
    }
  };
  while (i < lines.length) {
    const line = lines[i];
    const t = line.trim();
    if (t.startsWith('|') && t.endsWith('|')) {
      closeList();
      const tableRows = [];
      let j = i;
      while (j < lines.length && lines[j].trim().startsWith('|')) {
        const cells = lines[j].trim().split('|').map(c => c.trim()).filter(Boolean);
        if (cells.length > 0 && cells.every(c => /^[-:\s]+$/.test(c))) { j++; continue; }
        tableRows.push(cells);
        j++;
      }
      i = j;
      if (tableRows.length > 0) {
        out.push('<div class="my-5 rounded-lg border border-border overflow-hidden"><table class="w-full text-base">');
        out.push('<thead><tr class="bg-muted">');
        tableRows[0].forEach(cell => out.push(`<th class="px-4 py-3 text-left font-semibold">${bold(escape(cell))}</th>`));
        out.push('</tr></thead><tbody>');
        tableRows.slice(1).forEach((row, idx) => {
          out.push(`<tr class="${idx % 2 === 0 ? 'bg-muted/30' : ''}">`);
          row.forEach(cell => out.push(`<td class="px-4 py-3 border-t border-border text-base">${bold(escape(cell))}</td>`));
          out.push('</tr>');
        });
        out.push('</tbody></table></div>');
      }
      continue;
    }
    if (/^---+$/.test(t)) {
      closeList();
      out.push('<hr class="my-5 border-border"/>');
      i++; continue;
    }
    // # heading (h1)
    if (/^# [^#]/.test(t)) {
      closeList();
      out.push(`<h1 class="text-2xl font-bold mt-4 mb-4 text-violet-700 dark:text-violet-300">${bold(escape(t.slice(2)))}</h1>`);
      i++; continue;
    }
    // ## heading (h2)
    if (/^## /.test(t)) {
      closeList();
      out.push(`<h2 class="text-xl font-bold mt-6 mb-3 text-violet-600 dark:text-violet-400 border-b border-violet-200 dark:border-violet-800 pb-2">${bold(escape(t.slice(3)))}</h2>`);
      i++; continue;
    }
    // ### subheading (h3)
    if (/^### /.test(t)) {
      closeList();
      out.push(`<h3 class="text-lg font-semibold mt-4 mb-2 text-foreground">${bold(escape(t.slice(4)))}</h3>`);
      i++; continue;
    }
    // #### sub-subheading (h4)
    if (/^#### /.test(t)) {
      closeList();
      out.push(`<h4 class="text-base font-semibold mt-3 mb-1.5 text-muted-foreground">${bold(escape(t.slice(5)))}</h4>`);
      i++; continue;
    }
    if (t.endsWith(':') && t.length > 10 && !t.startsWith('-') && !t.startsWith('*') && !/^\d+\./.test(t)) {
      closeList();
      out.push(`<h2 class="text-xl font-bold mt-6 mb-3 text-violet-600 dark:text-violet-400 border-b border-violet-200 dark:border-violet-800 pb-2">${bold(escape(t))}</h2>`);
      i++; continue;
    }
    // Numbered list (1. 2. 3.)
    if (/^[\s]*\d+\.\s+/.test(t)) {
      if (!inList || listType !== 'ol') {
        closeList();
        out.push('<ol class="list-decimal pl-6 my-4 space-y-2">');
        inList = true;
        listType = 'ol';
      }
      const content = t.replace(/^[\s]*\d+\.\s+/, '');
      out.push(`<li class="text-base leading-relaxed">${bold(escape(content))}</li>`);
      i++; continue;
    }
    // Bullet list (•, -, *)
    if (/^[\s]*(?:•|-|\*)\s+/.test(t)) {
      if (!inList || listType !== 'ul') {
        closeList();
        out.push('<ul class="list-disc pl-6 my-4 space-y-2">');
        inList = true;
        listType = 'ul';
      }
      const content = t.replace(/^[\s]*(?:•|-|\*)\s+/, '');
      out.push(`<li class="text-base leading-relaxed">${bold(escape(content))}</li>`);
      i++; continue;
    }
    if (t === '' && inList) {
      closeList();
      i++; continue;
    }
    if (t && !t.startsWith('<')) {
      closeList();
      out.push(`<p class="my-4 text-base leading-relaxed">${bold(escape(t)).replace(/\n/g, '<br/>')}</p>`);
    }
    i++;
  }
  closeList();
  return out.join('\n');
}

/** Suggested questions when Graph mode is selected (4 buttons) */
const SUGGESTED_GRAPH_QUESTIONS = [
  'Show candidate decisions as a pie chart',
  'Display monthly CV processing trends as a line chart',
  'Compare interview outcomes by job position as a bar chart',
  'Show top 5 jobs by number of applicants',
];

/** Suggested questions when Search mode is selected (3 buttons) */
const SUGGESTED_SEARCH_QUESTIONS = [
  'How many jobs do I have? Which are active?',
  'Which candidates are best suited for the open role?',
  'What are basic React interview questions?',
];

/** Normalize chat from API shape to component shape */
function normalizeChat(chat) {
  if (!chat) return chat;
  return {
    ...chat,
    id: String(chat.id),
    title: chat.title || 'Chat',
    messages: chat.messages || [],
    updatedAt: chat.updatedAt || chat.timestamp,
    timestamp: chat.updatedAt || chat.timestamp,
  };
}

const AiInterviewQuestions = () => {
  const { toast } = useToast();
  const [chats, setChats] = useState([]);
  const [selectedChatId, setSelectedChatId] = useState(null);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingChats, setLoadingChats] = useState(true);
  const [deleteConfirmChatId, setDeleteConfirmChatId] = useState(null);
  const [inputMode, setInputMode] = useState('search'); // 'search' | 'graph'
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saveTitle, setSaveTitle] = useState('');
  const [saveTags, setSaveTags] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveContext, setSaveContext] = useState(null); // { prompt, chartTitle, chartType }
  const [showChatHistory, setShowChatHistory] = useState(true);
  const [expandedGraph, setExpandedGraph] = useState(null); // { chart, chartTitle } when modal open
  const messagesEndRef = useRef(null);

  const loadChatsFromApi = async () => {
    try {
      setLoadingChats(true);
      const res = await listQAChats();
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
    loadChatsFromApi();
  }, []);

  const selectedChat = chats.find((c) => c.id === selectedChatId);
  const currentMessages = selectedChat?.messages ?? [];

  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!question.trim()) {
      toast({ title: 'Error', description: 'Please enter a question.', variant: 'destructive' });
      return;
    }
    const q = question.trim();
    try {
      setLoading(true);
      if (inputMode === 'graph') {
        const result = await generateGraph(q);
        if (result.status === 'success' && result.data) {
          const { chart, insights } = result.data;
          const userMsg = { role: 'user', content: q };
          const assistantMsg = {
            role: 'assistant',
            content: chart?.title ? `**${chart.title}**` : 'Chart generated',
            responseData: { isGraph: true, chart, insights, chartTitle: chart?.title, chartType: chart?.type },
          };
          const title = q.slice(0, 40);
          if (selectedChatId) {
            const existing = chats.find((c) => c.id === selectedChatId);
            if (existing) {
              const newMessages = [...(existing.messages || []), userMsg, assistantMsg];
              const updRes = await updateQAChat(selectedChatId, { messages: [userMsg, assistantMsg], title: existing.title || title });
              if (updRes.status === 'success' && updRes.data) {
                const updatedChat = normalizeChat(updRes.data);
                setChats((prev) => [updatedChat, ...prev.filter((c) => c.id !== selectedChatId)]);
              } else throw new Error(updRes.message || 'Failed to save chat');
            } else {
              const createRes = await createQAChat({ title, messages: [userMsg, assistantMsg] });
              if (createRes.status === 'success' && createRes.data) {
                const newChat = normalizeChat(createRes.data);
                setChats((prev) => [newChat, ...prev]);
                setSelectedChatId(newChat.id);
              } else throw new Error(createRes.message || 'Failed to create chat');
            }
          } else {
            const createRes = await createQAChat({ title, messages: [userMsg, assistantMsg] });
            if (createRes.status === 'success' && createRes.data) {
              const newChat = normalizeChat(createRes.data);
              setChats((prev) => [newChat, ...prev]);
              setSelectedChatId(newChat.id);
            } else throw new Error(createRes.message || 'Failed to create chat');
          }
          setQuestion('');
          setTimeout(scrollToBottom, 100);
        } else {
          throw new Error(result.message || 'Failed to generate graph');
        }
        return;
      }

      const result = await recruitmentQA(q);
      if (result.status === 'success' && result.data) {
        const response = result.data;
        const answer = response.answer || 'No answer provided.';
        const insights = response.insights || [];
        let responseText = answer;
        if (insights.length > 0) {
          responseText += '\n\n**Key Insights & Metrics**\n';
          insights.forEach((i) => {
            responseText += `• **${i.title || 'N/A'}**: ${i.value || 'N/A'}\n`;
          });
        }
        const userMsg = { role: 'user', content: q };
        const assistantMsg = { role: 'assistant', content: responseText, responseData: response };
        const title = q.slice(0, 40);

        if (selectedChatId) {
          const existing = chats.find((c) => c.id === selectedChatId);
          if (existing) {
            const newMessages = [...(existing.messages || []), userMsg, assistantMsg];
            const updRes = await updateQAChat(selectedChatId, {
              messages: [userMsg, assistantMsg],
              title: existing.title || title,
            });
            if (updRes.status === 'success' && updRes.data) {
              const updatedChat = normalizeChat(updRes.data);
              setChats((prev) => [updatedChat, ...prev.filter((c) => c.id !== selectedChatId)]);
            } else {
              throw new Error(updRes.message || 'Failed to save chat');
            }
          } else {
            const createRes = await createQAChat({
              title,
              messages: [userMsg, assistantMsg],
            });
            if (createRes.status === 'success' && createRes.data) {
              const newChat = normalizeChat(createRes.data);
              setChats((prev) => [newChat, ...prev]);
              setSelectedChatId(newChat.id);
            } else {
              throw new Error(createRes.message || 'Failed to create chat');
            }
          }
        } else {
          const createRes = await createQAChat({
            title,
            messages: [userMsg, assistantMsg],
          });
          if (createRes.status === 'success' && createRes.data) {
            const newChat = normalizeChat(createRes.data);
            setChats((prev) => [newChat, ...prev]);
            setSelectedChatId(newChat.id);
          } else {
            throw new Error(createRes.message || 'Failed to create chat');
          }
        }
        setQuestion('');
        setTimeout(scrollToBottom, 100);
      } else {
        throw new Error(result.message || 'Failed to get response');
      }
    } catch (error) {
      toast({ title: 'Error', description: error.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const newChat = () => {
    setSelectedChatId(null);
    setQuestion('');
  };

  const deleteChat = async (e, chatId) => {
    e?.stopPropagation?.();
    try {
      const res = await deleteQAChat(chatId);
      if (res.status === 'success') {
        setChats((prev) => prev.filter((c) => c.id !== chatId));
        if (selectedChatId === chatId) setSelectedChatId(null);
        setDeleteConfirmChatId(null);
        toast({ title: 'Chat deleted' });
      } else {
        throw new Error(res.message || 'Failed to delete chat');
      }
    } catch (err) {
      toast({ title: 'Error', description: err.message || 'Could not delete chat', variant: 'destructive' });
    }
  };

  const confirmDeleteChat = (e, chatId) => {
    e.stopPropagation();
    setDeleteConfirmChatId(chatId);
  };

  const openSaveModal = (promptText, chartTitle, chartType) => {
    setSaveContext({ prompt: promptText, chartTitle: chartTitle || promptText?.slice(0, 40), chartType: chartType || 'bar' });
    setSaveTitle(chartTitle || promptText?.slice(0, 40) || '');
    setSaveTags('');
    setSaveModalOpen(true);
  };

  const handleSavePromptSubmit = async () => {
    if (!saveContext?.prompt || !saveTitle.trim()) {
      toast({ title: 'Error', description: 'Title is required.', variant: 'destructive' });
      return;
    }
    try {
      setSaving(true);
      const res = await savePrompt({
        title: saveTitle.trim(),
        prompt: saveContext.prompt,
        tags: saveTags ? saveTags.split(',').map((t) => t.trim()).filter(Boolean) : [],
        chart_type: saveContext.chartType || 'bar',
      });
      if (res.status === 'success') {
        setSaveModalOpen(false);
        setSaveContext(null);
        toast({ title: 'Prompt saved', description: 'You can find it in AI Graphs > Saved prompts.' });
      } else throw new Error(res.message || 'Failed to save');
    } catch (err) {
      toast({ title: 'Error', description: err.message || 'Failed to save prompt', variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const handleAddToDashboard = async (promptText, chartTitle, chartType) => {
    try {
      const title = (chartTitle || promptText?.slice(0, 40) || 'Graph').trim();
      const res = await savePrompt({
        title,
        prompt: promptText,
        tags: ['dashboard'],
        chart_type: chartType || 'bar',
      });
      if (res.status === 'success') {
        toast({ title: 'Added to dashboard', description: 'Card will appear on recruitment dashboard.' });
      } else throw new Error(res.message || 'Failed');
    } catch (err) {
      toast({ title: 'Error', description: err.message || 'Could not add to dashboard', variant: 'destructive' });
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
      {/* Sidebar - Previous chats (toggleable) */}
      {showChatHistory && (
        <div className="w-64 shrink-0 rounded-lg border bg-card">
          <div className="p-3 border-b flex items-center justify-between">
            <span className="text-sm font-semibold">Previous conversations</span>
            <div className="flex items-center gap-1">
              <Button variant="ghost" size="icon" onClick={newChat} title="New chat">
                <Plus className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setShowChatHistory(false)}
                title="Hide chat history"
              >
                <PanelLeftClose className="h-4 w-4" />
              </Button>
            </div>
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
                    className={`flex items-center gap-1 rounded-lg border text-sm transition-colors ${
                      selectedChatId === c.id ? 'border-primary/20 bg-primary/10' : 'border-border hover:bg-muted'
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => setSelectedChatId(c.id)}
                      className="flex-1 min-w-0 text-left p-3 rounded-lg"
                    >
                      <div className="font-medium truncate">{truncate(c.title || (c.messages?.[0]?.content) || c.question || 'Chat', 40)}</div>
                      <div className="text-xs text-muted-foreground mt-0.5">{formatDate(c.updatedAt || c.timestamp)}</div>
                    </button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 shrink-0 opacity-60 hover:opacity-100 hover:bg-destructive/10 hover:text-destructive"
                      onClick={(e) => confirmDeleteChat(e, c.id)}
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
      )}

      {/* Delete chat confirmation modal */}
      <Dialog open={!!deleteConfirmChatId} onOpenChange={(open) => !open && setDeleteConfirmChatId(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete chat?</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete this chat? This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirmChatId(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteConfirmChatId && deleteChat(null, deleteConfirmChatId)}
            >
              Yes, delete chat
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Main chat area - full width when sidebar hidden */}
      <Card className="flex-1 min-w-0 flex flex-col max-h-[calc(100vh-40px)]">
        <CardHeader className="shrink-0 flex flex-row items-start justify-between gap-2">
          <div>
            <CardTitle className="flex items-center gap-2">
              <MessageSquare className="h-5 w-5" />
              Knowledge Q&A
            </CardTitle>
            <CardDescription>
              Ask about your jobs & candidates, or get tech stack interview questions (React, Node, MERN, etc.) and recruitment tips.
            </CardDescription>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setShowChatHistory((v) => !v)}
            title={showChatHistory ? 'Hide chat history' : 'Show chat history'}
          >
            {showChatHistory ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
          </Button>
        </CardHeader>
        <CardContent className="p-0 flex flex-col flex-1 min-h-0">
          {/* Messages area - scrollable when content is long */}
          <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-4 pb-4 space-y-4">
            {!selectedChatId && chats.length === 0 && (
              <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                <MessageCircle className="h-12 w-12 mb-4 opacity-50" />
                <p className="font-medium">Ask your first question</p>
                <p className="text-sm">Select from suggested questions or type your own.</p>
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
                  className={`rounded-2xl ${
                    msg.role === 'user'
                      ? 'bg-primary text-primary-foreground max-w-[85%] px-4 py-3'
                      : msg.responseData?.isGraph
                        ? 'bg-muted border max-w-[70%] px-2 py-2'
                        : 'bg-muted border max-w-[85%] px-4 py-3'
                  }`}
                >
                  {msg.role === 'user' ? (
                    <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
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
                        {Array.isArray(msg.responseData.insights) && msg.responseData.insights.length > 0 && (
                          <div className="pt-2 border-t border-border/50">
                            <p className="text-xs font-semibold mb-2">Insights</p>
                            <table className="w-full text-xs">
                              <tbody>
                                {msg.responseData.insights.map((insight, j) => (
                                  <tr key={j} className="border-b border-border/30">
                                    <td className="py-1 pr-2 font-medium">{insight.title || 'N/A'}</td>
                                    <td className="py-1 text-muted-foreground">{insight.value || 'N/A'}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                        <div className="flex flex-wrap gap-2 pt-2">
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => openSaveModal(
                              currentMessages[i - 1]?.content,
                              msg.responseData.chartTitle,
                              msg.responseData.chartType
                            )}
                          >
                            <Save className="h-4 w-4 mr-2" />
                            Save Prompt
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            onClick={() => handleAddToDashboard(
                              currentMessages[i - 1]?.content,
                              msg.responseData.chartTitle,
                              msg.responseData.chartType
                            )}
                            className="rounded-xl bg-[#16162a] hover:bg-[#1e1e38] text-white border-0 shadow-[0_2px_8px_rgba(0,0,0,0.35)] hover:shadow-[0_3px_10px_rgba(0,0,0,0.4)] px-4 py-2 h-9"
                          >
                            <LayoutDashboard className="h-4 w-4 mr-2 shrink-0" />
                            Add to dashboard
                          </Button>
                        </div>
                      </div>
                    </>
                  ) : (
                    <>
                      <div
                        className="prose prose-base max-w-none [&_h2]:text-violet-600 [&_h2]:dark:text-violet-400 [&_strong]:font-semibold [&_p]:text-base [&_li]:text-base"
                        dangerouslySetInnerHTML={{ __html: markdownToHtml(msg.responseData?.answer ?? msg.content) }}
                      />
                      {Array.isArray(msg.responseData?.insights) && msg.responseData.insights.length > 0 && (
                        <div className="mt-3 pt-3 border-t border-border/50">
                          <p className="text-xs font-semibold mb-2">Key Insights</p>
                          <div>
                            <table className="w-full text-xs">
                              <tbody>
                                {msg.responseData.insights.map((insight, j) => (
                                  <tr key={j} className="border-b border-border/30">
                                    <td className="py-1 pr-2 font-medium">{insight.title || 'N/A'}</td>
                                    <td className="py-1 text-muted-foreground">{insight.value || 'N/A'}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
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
                  <span className="text-sm">Analyzing...</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input area — one row aligned, Try row aligned with bar */}
          <form onSubmit={handleSubmit} className="shrink-0 border-t border-border bg-muted/20">
            <div className="p-4 space-y-3">
              <div className="flex gap-3 items-center min-h-[48px]">
                <div className="flex h-11 rounded-lg border border-border bg-background overflow-hidden shrink-0">
                  <button
                    type="button"
                    onClick={() => setInputMode('search')}
                    className={`flex items-center justify-center gap-2 min-w-[88px] h-full px-3 text-sm transition-colors ${
                      inputMode === 'search' ? 'bg-muted font-medium text-foreground' : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <Search className="h-4 w-4 shrink-0" />
                    Search
                  </button>
                  <button
                    type="button"
                    onClick={() => setInputMode('graph')}
                    className={`flex items-center justify-center gap-2 min-w-[88px] h-full px-3 text-sm transition-colors border-l border-border ${
                      inputMode === 'graph' ? 'bg-muted font-medium text-foreground' : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <BarChart2 className="h-4 w-4 shrink-0" />
                    Graph
                  </button>
                </div>
                <Textarea
                  placeholder={inputMode === 'search' ? 'Ask about jobs, candidates, or interview questions…' : 'Describe the chart you want…'}
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(e); } }}
                  rows={1}
                  disabled={loading}
                  className="flex-1 min-h-[44px] h-11 max-h-32 resize-none rounded-lg border border-border bg-background text-sm py-2.5 text-left"
                />
                <Button type="submit" disabled={loading} size="icon" className="h-11 w-11 shrink-0 rounded-lg">
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </Button>
              </div>
              <div className="space-y-2">
                <span className="text-xs text-muted-foreground font-medium">Try these examples</span>
                <div className="flex flex-wrap gap-1.5">
                  {(inputMode === 'graph' ? SUGGESTED_GRAPH_QUESTIONS : SUGGESTED_SEARCH_QUESTIONS).map((q) => (
                    <button
                      key={q}
                      type="button"
                      onClick={() => setQuestion(q)}
                      className="text-xs text-foreground bg-muted/80 hover:bg-muted border border-border hover:border-border rounded-md px-2 py-1 text-left transition-colors"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </form>

      {/* Expand graph modal - full width */}
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

      {/* Save Prompt modal (for graph messages) */}
      <Dialog open={saveModalOpen} onOpenChange={(open) => { if (!open) { setSaveModalOpen(false); setSaveContext(null); } }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Save Prompt</DialogTitle>
            <DialogDescription>Save this graph prompt for quick access in AI Graphs.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="save-title">Title</Label>
              <Input
                id="save-title"
                value={saveTitle}
                onChange={(e) => setSaveTitle(e.target.value)}
                placeholder="e.g. Monthly CV Trends"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="save-tags">Tags (comma-separated)</Label>
              <Input
                id="save-tags"
                value={saveTags}
                onChange={(e) => setSaveTags(e.target.value)}
                placeholder="e.g. analytics, monthly"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setSaveModalOpen(false); setSaveContext(null); }}>Cancel</Button>
            <Button onClick={handleSavePromptSubmit} disabled={saving}>
              {saving ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Saving...</> : <><Save className="h-4 w-4 mr-2" /> Save Prompt</>}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
        </CardContent>
      </Card>
    </div>
  );
};

export default AiInterviewQuestions;
