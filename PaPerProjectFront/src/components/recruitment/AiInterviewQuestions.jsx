import React, { useState, useEffect, useRef } from 'react';
// ...existing code...
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Loader2, Send, MessageSquare, Plus, MessageCircle, Trash2, Search, BarChart2, Save, LayoutDashboard, Maximize2, Check, History, ChevronsLeft, ChevronsRight, Bot, Sparkles, Activity, Users, TrendingUp } from 'lucide-react';
import { recruitmentQA, listQAChats, createQAChat, updateQAChat, deleteQAChat, generateGraph, savePrompt, getSavedPrompts, isPromptOnDashboard } from '@/services/recruitmentAgentService';
import { renderChart } from './ChartRenderer';

// ...existing code...

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

const INPUT_MODE_OPTIONS = [
  {
    value: 'search',
    label: 'Search',
    placeholder: 'Ask about jobs, candidates, interview plans, or hiring recommendations…',
    icon: Search,
  },
  {
    value: 'graph',
    label: 'Graph',
    placeholder: 'Describe the recruitment graph you want to generate…',
    icon: BarChart2,
  },
];

const HERO_TOPICS = [
  { label: 'General', icon: Sparkles, prompt: 'Give me a quick recruitment pipeline summary for this month.' },
  { label: 'Hiring Trends', icon: TrendingUp, prompt: 'Show hiring trends by role and month in a graph.' },
  { label: 'Candidates', icon: Users, prompt: 'Which candidates are strongest for our open positions?' },
  { label: 'Performance', icon: Activity, prompt: 'What are key recruitment performance insights right now?' },
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
    // Sidebar search toggle state (must be inside component)
    const [showSidebarSearch, setShowSidebarSearch] = useState(false);
    const [sidebarSearch, setSidebarSearch] = useState("");
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
  const [addedToDashboard, setAddedToDashboard] = useState(new Set()); // track prompts already added to dashboard
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

  // Load existing dashboard prompts from API to pre-populate "Already Added" state
  const loadDashboardState = async () => {
    try {
      const res = await getSavedPrompts();
      const list = res?.data || [];
      const dashboardPrompts = list.filter(isPromptOnDashboard);
      if (dashboardPrompts.length > 0) {
        const keys = new Set(dashboardPrompts.map(p => `${p.prompt}__${p.chart_type || 'bar'}`));
        setAddedToDashboard(keys);
      }
    } catch (err) {
      console.error('Load dashboard state error:', err);
    }
  };

  useEffect(() => {
    loadChatsFromApi();
    loadDashboardState();
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
    // Prevent duplicate additions (client-side check)
    const key = `${promptText}__${chartType || 'bar'}`;
    if (addedToDashboard.has(key)) {
      toast({ title: 'Already Added', description: 'This graph is already on your dashboard.' });
      return;
    }
    try {
      const title = (chartTitle || promptText?.slice(0, 40) || 'Graph').trim();
      const res = await savePrompt({
        title,
        prompt: promptText,
        tags: ['dashboard'],
        chart_type: chartType || 'bar',
      });
      // Backend returns 'already_exists' if duplicate dashboard prompt
      if (res.status === 'success' || res.status === 'already_exists') {
        setAddedToDashboard(prev => new Set(prev).add(key));
        if (res.status === 'already_exists') {
          toast({ title: 'Already Added', description: 'This graph is already on your dashboard.' });
        } else {
          toast({ title: 'Added to dashboard', description: 'Card will appear on recruitment dashboard.' });
        }
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

  const selectedMode = INPUT_MODE_OPTIONS.find((mode) => mode.value === inputMode) || INPUT_MODE_OPTIONS[0];
  const SelectedModeIcon = selectedMode.icon;

  return (
    <div
      className="w-full rounded-2xl border border-white/[0.06] p-0 overflow-hidden"
      style={{ background: 'linear-gradient(90deg, #020308 0%, #020308 55%, rgba(10,37,64,0.68) 85%, rgba(14,39,71,0.52) 100%)' }}
    >
      {/* Scoped dark-bar placeholder color */}
      <style>{`.recruit-dark-input::placeholder { color: rgba(255,255,255,0.3) !important; }`}</style>
      <div className="flex w-full max-w-full relative">
      {/* Sidebar - Previous chats with smooth transition */}
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
        <div className="w-64">
          <div className="px-3 pt-3 pb-2 border-b border-white/15 flex flex-col gap-2" style={{ background: 'linear-gradient(180deg, rgba(60, 30, 90, 0.22) 0%, rgba(36, 18, 54, 0.85) 100%)', borderTopLeftRadius: 16 }}>
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
                  onChange={e => setSidebarSearch(e.target.value)}
                  placeholder="Search conversations..."
                  className="flex-1 bg-transparent outline-none border-0 text-white/90 text-sm px-2 py-1.5 placeholder-white/40"
                  style={{ minWidth: 0 }}
                />
                <button
                  title="Close search"
                  onClick={() => setShowSidebarSearch(false)}
                  className="h-7 w-7 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60 bg-black/20 hover:bg-violet-700/20 transition-all duration-150"
                >
                  <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-white/70"><line x1="4" y1="4" x2="12" y2="12"/><line x1="12" y1="4" x2="4" y2="12"/></svg>
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
                  <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-white/70"><circle cx="7" cy="7" r="5"/><line x1="15" y1="15" x2="11" y2="11"/></svg>
                </button>
                <button onClick={newChat} title="New chat" className="h-7 w-7 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60 bg-black/20 hover:bg-violet-700/20 transition-all duration-150">
                  <Plus className="h-4 w-4 text-white/80" />
                </button>
              </div>
            )}
          </div>
          <div >
            {loadingChats ? (
              <div className="p-4 flex justify-center">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : chats.length === 0 ? (
              <div className="p-4 text-center text-sm text-muted-foreground">No conversations yet. Ask a question to start.</div>
            ) : (
              <div className="p-2 space-y-1" style={{ background: 'linear-gradient(180deg, rgba(36, 18, 54, 0.10) 0%, rgba(24, 18, 43, 0.18) 100%)', borderRadius: 12 }}>
                {chats.map((c) => (
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
                      <div className={`font-medium truncate ${selectedChatId === c.id ? 'text-violet-300' : ''}`}>{truncate(c.title || (c.messages?.[0]?.content) || c.question || 'Chat', 40)}</div>
                      <div className={`text-xs mt-0.5 ${selectedChatId === c.id ? 'text-violet-400/70' : 'text-muted-foreground'}`}>{formatDate(c.updatedAt || c.timestamp)}</div>
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
      </div>

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
      <Card
      className="flex-1 min-w-0 flex flex-col max-h-[calc(100vh-40px)] border-0 shadow-none"
      style={{ background: 'transparent' }}>
        <CardHeader className="shrink-0 flex flex-row items-start justify-between gap-3 border-b border-white/[0.07] px-0 py-4" style={{ background: 'transparent' }}>
          <div className="flex items-center gap-3 min-w-0 w-full">
            {/* Vertical purple gradient bar */}
            <div style={{
              width: '7px',
              height: '48px',
              borderRadius: '8px',
              background: 'linear-gradient(to bottom, #a259ff 0%, #6a1b9a 60%, #18122B 100%)',
              marginLeft: '24px',
              marginRight: '18px',
              boxShadow: '0 0 8px 2px #a259ff44',
            }} />
            <div className="h-10 w-10 rounded-lg flex items-center justify-center shrink-0" style={{ background: 'rgba(124, 58, 237, 0.15)' }}>
              <Bot className="h-5 w-5" style={{ color: '#a78bfa' }} />
            </div>
            <div className="min-w-0">
              <CardTitle className="flex items-center gap-2 truncate text-white text-lg">
                Recruitment Research Assistance
                <span className="text-[10px] rounded-full px-2.5 py-0.5 font-medium" style={{ background: 'rgba(124, 58, 237, 0.15)', color: '#a78bfa' }}>AI-Powered</span>
              </CardTitle>
              <CardDescription className="text-white/50 text-sm mt-0.5">
                Ask anything about candidates, jobs, interview plans, and recruitment performance.
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
            {showChatHistory
              ? <><ChevronsLeft className="h-4 w-4" /><span className="text-xs hidden sm:inline">Hide</span></>
              : <><ChevronsRight className="h-4 w-4" /><span className="text-xs hidden sm:inline">History</span></>
            }
          </Button>
        </CardHeader>
        <CardContent className="p-0 flex flex-col flex-1 min-h-0 ">
          {/* Messages area - scrollable when content is long */}
          <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-4 py-4 space-y-4">
            {currentMessages.length === 0 && !loading && (
              <div className="flex flex-col items-center justify-center min-h-[420px] text-center px-4">
                <div className="h-20 w-20 rounded-2xl flex items-center justify-center mb-6" style={{ background: 'rgba(124, 58, 237, 0.12)' }}>
                  <Bot className="h-10 w-10" style={{ color: '#a78bfa' }} />
                </div>
                <h2 className="text-3xl font-semibold tracking-tight text-white">Ready to Research?</h2>
                <p className="mt-3 max-w-lg" style={{ color: 'rgba(255,255,255,0.45)' }}>
                  Ask about hiring trends, candidate insights, role fit, and recruitment optimization.
                </p>
                <div className="grid grid-cols-2 gap-3 mt-8 w-full max-w-md">
                  {HERO_TOPICS.map((topic) => {
                    const TopicIcon = topic.icon;
                    return (
                      <button
                        key={topic.label}
                        type="button"
                        onClick={() => setQuestion(topic.prompt)}
                        className="flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium text-left transition-all duration-200 text-white/90 hover:text-white"
                        style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)' }}
                        onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.09)'; e.currentTarget.style.borderColor = 'rgba(139,92,246,0.3)'; }}
                        onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.05)'; e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)'; }}
                      >
                        <TopicIcon className="h-5 w-5 shrink-0" style={{ color: '#a78bfa' }} />
                        {topic.label}
                      </button>
                    );
                  })}
                </div>
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
                          {(() => {
                            const _key = `${currentMessages[i - 1]?.content}__${msg.responseData.chartType || 'bar'}`;
                            const _isAdded = addedToDashboard.has(_key);
                            return (
                              <Button
                                type="button"
                                size="sm"
                                disabled={_isAdded}
                                onClick={() => handleAddToDashboard(
                                  currentMessages[i - 1]?.content,
                                  msg.responseData.chartTitle,
                                  msg.responseData.chartType
                                )}
                                className={_isAdded
                                  ? "rounded-xl bg-green-700 text-white border-0 shadow-[0_2px_8px_rgba(0,0,0,0.35)] px-4 py-2 h-9 cursor-not-allowed opacity-80"
                                  : "rounded-xl bg-[#16162a] hover:bg-[#1e1e38] text-white border-0 shadow-[0_2px_8px_rgba(0,0,0,0.35)] hover:shadow-[0_3px_10px_rgba(0,0,0,0.4)] px-4 py-2 h-9"
                                }
                              >
                                {_isAdded
                                  ? <><Check className="h-4 w-4 mr-2 shrink-0" /> Already Added</>
                                  : <><LayoutDashboard className="h-4 w-4 mr-2 shrink-0" /> Add to dashboard</>
                                }
                              </Button>
                            );
                          })()}
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

          {/* Input area — dark pill bar matching figma design */}
          <div style={{ position: 'relative', width: '100%' }}>
            <div
              style={{
                position: 'absolute',
                left: 0,
                right: 0,
                bottom: 0,
                top: 0,
                zIndex: 1,
                pointerEvents: 'none',
                background: 'linear-gradient(90deg, transparent 60%, rgba(10,37,64,0.38) 90%, rgba(14,39,71,0.22) 100%)',
              }}
            />
            <form onSubmit={handleSubmit} className="shrink-0" style={{ position: 'relative', zIndex: 2 }}>
              <div
                className="mx-4 mb-4 flex items-center gap-2.5 rounded-[28px] px-2.5 py-2.5"
                style={{
                  background: '#0a0a0f',
                  border: '1.5px solid rgba(255,255,255,0.08)',
                  boxShadow: '0 4px 24px rgba(0,0,0,0.5)',
                }}
              >
              {/* Dropdown selector – pill with violet glow border */}
              <Select value={inputMode} onValueChange={setInputMode}>
                <SelectTrigger
                  className="h-11 w-[145px] shrink-0 rounded-full text-sm font-medium focus:ring-0 focus:ring-offset-0 transition-all duration-200 px-4 gap-2 [&>svg]:opacity-70"
                  style={{
                    background: '#111118',
                    border: '1.5px solid rgba(139, 92, 246, 0.55)',
                    boxShadow: '0 0 16px rgba(139, 92, 246, 0.2), 0 0 4px rgba(139, 92, 246, 0.15)',
                    color: '#e2e2f0',
                  }}
                >
                  <div className="flex items-center gap-2">
                    <SelectedModeIcon className="h-4 w-4" style={{ color: '#a78bfa' }} />
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
                      <SelectItem
                        key={mode.value}
                        value={mode.value}
                        className="focus:bg-violet-600/20 focus:text-white"
                      >
                        <div className="flex items-center gap-2">
                          <ModeIcon className="h-4 w-4" />
                          <span>{mode.label}</span>
                        </div>
                      </SelectItem>
                    );
                  })}
                </SelectContent>
              </Select>

              {/* Input field – dark capsule with purple border on left fading out */}
              <div
                className="flex-1 min-w-0 rounded-full flex items-center overflow-hidden"
                style={{
                  background: '#0e0e14',
                  boxShadow: 'inset 2px 0 8px -2px rgba(139,92,246,0.35)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  borderLeftColor: 'rgba(139, 92, 246, 0.45)',
                }}
              >
                <Textarea
                  placeholder={selectedMode.placeholder}
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(e); } }}
                  rows={1}
                  disabled={loading}
                  className="recruit-dark-input flex-1 w-full min-h-[44px] h-11 max-h-32 resize-none border-0 bg-transparent text-sm py-3 px-4 focus-visible:ring-0 focus-visible:ring-offset-0"
                  style={{ color: 'rgba(255,255,255,0.85)', }}
                />
              </div>

              {/* Send button – purple circle */}
              <Button
                type="submit"
                disabled={loading}
                size="icon"
                className="h-11 w-11 shrink-0 rounded-full border-0 transition-all duration-200"
                style={{
                  background: 'linear-gradient(135deg, #7c3aed 0%, #6d28d9 50%, #5b21b6 100%)',
                  boxShadow: '0 0 16px rgba(124, 58, 237, 0.35), 0 2px 8px rgba(0,0,0,0.3)',
                  color: '#ffffff',
                }}
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </Button>
              </div>
            </form>
          </div>

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
    </div>
  );
};

export default AiInterviewQuestions;
