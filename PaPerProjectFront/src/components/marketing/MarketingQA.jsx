import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import { Badge } from '@/components/ui/badge';
import { 
  Loader2, 
  Send, 
  MessageSquare, 
  Plus, 
  MessageCircle, 
  Trash2,
  Bot,
  User,
  Sparkles,
  ChevronLeft,
  ChevronRight,
  Clock,
  X,
  Lightbulb,
  TrendingUp,
  Target,
  BarChart3,
  HelpCircle,
  BookOpen,
  Award,
  Zap,
  CheckCircle2,
  AlertCircle
} from 'lucide-react';
import marketingAgentService from '@/services/marketingAgentService';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/lib/utils';

const STORAGE_KEY = 'marketing_qa_chats';

/** Normalize question for comparison: trim, lower, collapse spaces, remove trailing punctuation */
function normalizeQuestion(text) {
  if (!text || typeof text !== 'string') return '';
  return text
    .replace(/\u200B|\u200C|\u200D|\uFEFF/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
    .replace(/[?!.,;:]+\s*$/, '');
}

/** True if question is greeting/small talk – do not call API */
function isGreetingOrSmallTalk(question) {
  const t = normalizeQuestion(question);
  if (!t) return true;
  if (t.length > 40) return false;
  const smallTalk = new Set([
    'hi', 'hii', 'hello', 'hey', 'helo', 'yo', 'sup', 'thanks', 'thank you', 'thx',
    'ok', 'okay', 'oky', 'okey', 'okie', 'k', 'kk', 'bye', 'goodbye', 'cya',
    'good', 'great', 'nice', 'cool', 'alright', 'fine', 'got it', 'understood',
    'perfect', 'sure', 'yeah', 'yep', 'yup', 'nope', 'no', 'yes',
    'ok good', 'okay good', 'oky good', 'ok god', 'oky god', 'okay god',
    'okya', 'okya good', 'okya god', 'okie good', 'gud', 'gud good',
  ]);
  if (smallTalk.has(t)) return true;
  if (t.length <= 14 && /^ok[a-z]*\s*(good|god|gud)?$/.test(t)) return true;
  return false;
}

/** True if question is meta (what can I ask) – do not call API. Platform/agent questions ("what is this platform", "how does this work") go to API. */
function isMetaQuestion(question) {
  const t = normalizeQuestion(question);
  if (!t || t.length > 80) return false;
  const metaPhrases = [
    'what can i ask', 'what i can ask', 'how can you help', 'what do you do',
    'what can you answer', 'what should i ask',
    'example questions', 'give me examples', 'what to ask',
  ];
  return metaPhrases.some((p) => t.includes(p));
}

/** Markdown to HTML for Q&A answers - readable paragraphs, headings, bullets, tables */
function markdownToHtml(markdown) {
  if (!markdown || typeof markdown !== 'string') return '';
  
  const escape = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const bold = (s) => s.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-primary">$1</strong>');
  
  const lines = markdown.split('\n');
  const out = [];
  let inList = false;
  let i = 0;
  
  while (i < lines.length) {
    const line = lines[i];
    const t = line.trim();
    
    // Markdown table: | col | col |
    if (t.startsWith('|') && t.endsWith('|')) {
      if (inList) { out.push('</ul>'); inList = false; }
      
      const tableRows = [];
      let j = i;
      while (j < lines.length && lines[j].trim().startsWith('|')) {
        const cells = lines[j].trim().split('|').map(c => c.trim()).filter(Boolean);
        if (cells.length > 0 && cells.every(c => /^[-:\s]+$/.test(c))) { 
          j++; 
          continue; 
        }
        tableRows.push(cells);
        j++;
      }
      i = j;
      
      if (tableRows.length > 0) {
        out.push('<div class="my-5 overflow-x-auto rounded-lg border border-border shadow-sm"><table class="w-full text-base">');
        out.push('<thead><tr class="bg-muted/80">');
        tableRows[0].forEach(cell => out.push(`<th class="px-4 py-3 text-left font-semibold text-foreground">${bold(escape(cell))}</th>`));
        out.push('</tr></thead><tbody>');
        tableRows.slice(1).forEach((row, idx) => {
          out.push(`<tr class="${idx % 2 === 0 ? 'bg-muted/30' : ''} hover:bg-muted/50 transition-colors">`);
          row.forEach(cell => out.push(`<td class="px-4 py-3 border-t border-border text-base">${bold(escape(cell))}</td>`));
          out.push('</tr>');
        });
        out.push('</tbody></table></div>');
      }
      continue;
    }
    
    if (/^---+$/.test(t)) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push('<hr class="my-5 border-border/50"/>');
      i++; continue;
    }
    
    if (/^## /.test(t)) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<h2 class="text-xl font-bold mt-6 mb-3 text-primary border-b border-primary/20 pb-2">${bold(escape(t.slice(3)))}</h2>`);
      i++; continue;
    }
    
    if (/^### /.test(t)) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<h3 class="text-lg font-bold mt-4 mb-2 text-foreground">${bold(escape(t.slice(4)))}</h3>`);
      i++; continue;
    }
    
    // Lines ending with : (like "Opportunities We're Missing:") treated as h2
    if (t.endsWith(':') && t.length > 10 && !t.startsWith('-') && !t.startsWith('*')) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<h2 class="text-xl font-bold mt-6 mb-3 text-primary border-b border-primary/20 pb-2">${bold(escape(t))}</h2>`);
      i++; continue;
    }
    
    if (/^[\s]*(?:•|-|\*|\d+\.)\s+/.test(t)) {
      if (!inList) { 
        out.push('<ul class="list-disc pl-6 my-4 space-y-2">'); 
        inList = true; 
      }
      const content = t.replace(/^[\s]*(?:•|-|\*|\d+\.)\s+/, '');
      out.push(`<li class="text-base leading-relaxed">${bold(escape(content))}</li>`);
      i++; continue;
    }
    
    if (t === '' && inList) {
      out.push('</ul>');
      inList = false;
      i++; continue;
    }
    
    if (t && !t.startsWith('<')) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<p class="my-4 text-base leading-relaxed">${bold(escape(t)).replace(/\n/g, '<br/>')}</p>`);
    }
    i++;
  }
  
  if (inList) out.push('</ul>');
  return out.join('\n');
}

/** Suggested questions matching backend / agents_test.html Knowledge Q&A + Analytics */
const SUGGESTED_QUESTIONS = [
  { 
    group: '🚀 Platform & Getting Started', 
    icon: BookOpen,
    color: 'text-blue-500',
    options: [
      'What is this platform?',
      'How does this platform work?',
      'How do I run a campaign?',
      'What is this agent?',
    ]
  },
  { 
    group: '📊 Performance & Analytics', 
    icon: BarChart3,
    color: 'text-emerald-500',
    options: [
      'What campaigns are performing best?',
      'What is our overall ROI?',
      'Which marketing channels are most effective?',
      'What is our conversion rate?',
      'How are our campaigns performing this month?',
      'What is our customer acquisition cost (CAC)?',
    ]
  },
  { 
    group: '🔍 Analysis & Insights', 
    icon: TrendingUp,
    color: 'text-purple-500',
    options: [
      'Why are sales dropping?',
      'What should we focus on to improve performance?',
      'What are the key trends in our marketing data?',
      'Which campaigns need optimization?',
      'What are our top performing campaigns and why?',
    ]
  },
  { 
    group: '🎯 Goals & Targets', 
    icon: Target,
    color: 'text-amber-500',
    options: [
      'How many leads have we generated this month?',
      'What is our lead conversion rate?',
      'Are we on track to meet our campaign goals?',
    ]
  },
  { 
    group: '💡 Strategy & Recommendations', 
    icon: Lightbulb,
    color: 'text-rose-500',
    options: [
      'What marketing strategies should we implement?',
      'What opportunities are we missing?',
      'How can we improve our campaign performance?',
      'What are the best practices for our industry?',
    ]
  },
];

/** Normalize chat to { id, messages: [{ role, content, responseData? }], timestamp } */
function normalizeChat(c) {
  if (c.messages && Array.isArray(c.messages)) return c;
  if (c.question != null) {
    return {
      id: c.id,
      messages: [
        { role: 'user', content: c.question },
        { role: 'assistant', content: c.response || '', responseData: c.responseData },
      ],
      timestamp: c.timestamp || new Date().toISOString(),
    };
  }
  return { id: c.id || Date.now().toString(), messages: [], timestamp: c.timestamp || new Date().toISOString() };
}

function loadChats() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const list = raw ? JSON.parse(raw) : [];
    return list.map(normalizeChat);
  } catch {
    return [];
  }
}

function saveChats(chats) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(chats.slice(-50))); // Keep last 50
  } catch {}
}

// Animation variants
const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1
    }
  }
};

const itemVariants = {
  hidden: { y: 20, opacity: 0 },
  visible: {
    y: 0,
    opacity: 1,
    transition: {
      type: "spring",
      stiffness: 100,
      damping: 12
    }
  }
};

const messageVariants = {
  hidden: { scale: 0.8, opacity: 0, y: 20 },
  visible: {
    scale: 1,
    opacity: 1,
    y: 0,
    transition: {
      type: "spring",
      stiffness: 100,
      damping: 15
    }
  },
  exit: {
    scale: 0.8,
    opacity: 0,
    transition: { duration: 0.2 }
  }
};

const sidebarItemVariants = {
  hidden: { x: -20, opacity: 0 },
  visible: {
    x: 0,
    opacity: 1,
    transition: {
      type: "spring",
      stiffness: 100,
      damping: 12
    }
  },
  hover: {
    scale: 1.02,
    x: 5,
    transition: { duration: 0.2 }
  }
};

const MarketingQA = () => {
  const { toast } = useToast();
  const [chats, setChats] = useState([]);
  const [selectedChatId, setSelectedChatId] = useState(null);
  const [question, setQuestion] = useState('');
  const [suggestedValue, setSuggestedValue] = useState('__none__');
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [showSuggestions, setShowSuggestions] = useState(true);
  
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    setChats(loadChats());
  }, []);

  const selectedChat = chats.find((c) => c.id === selectedChatId);
  const currentMessages = selectedChat?.messages ?? [];

  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  useEffect(() => {
    scrollToBottom();
  }, [currentMessages]);

  const fillFromSuggestion = (value) => {
    const v = value || '__none__';
    setSuggestedValue(v);
    if (v !== '__none__') {
      setQuestion(v);
      textareaRef.current?.focus();
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!question.trim()) {
      toast({ 
        title: 'Error', 
        description: 'Please enter a question.', 
        variant: 'destructive' 
      });
      return;
    }
    
    const q = question.trim();

    // Check for special cases
    if (isGreetingOrSmallTalk(q)) {
      const response = {
        answer: "👋 Hi there! I'm your Marketing Q&A Assistant. I can help you with:\n\n• **Campaign performance** metrics and insights\n• **ROI analysis** and optimization suggestions\n• **Lead generation** and conversion rates\n• **Channel effectiveness** comparisons\n• **Strategic recommendations** for improvement\n\nWhat would you like to know about your marketing data?",
        insights: [],
      };
      const responseText = response.answer;
      const userMsg = { role: 'user', content: q };
      const assistantMsg = { role: 'assistant', content: responseText, responseData: response };
      handleResponse(q, userMsg, assistantMsg, response);
      return;
    }

    if (isMetaQuestion(q)) {
      const response = {
        answer: "You can ask me about:\n\n**📈 Performance Metrics**\n• Campaign ROI, conversion rates, CAC\n• Channel effectiveness, lead generation\n\n**🔍 Analysis**\n• Why sales are dropping/rising\n• Which campaigns need optimization\n• Trends in your marketing data\n\n**💡 Recommendations**\n• Marketing strategies to implement\n• Opportunities you might be missing\n• Best practices for your industry\n\nPick a suggested question above or type your own!",
        insights: [],
      };
      const responseText = response.answer;
      const userMsg = { role: 'user', content: q };
      const assistantMsg = { role: 'assistant', content: responseText, responseData: response };
      handleResponse(q, userMsg, assistantMsg, response);
      return;
    }

    // Actual API call
    try {
      setLoading(true);
      
      // Send last 6 Q&A pairs for context
      const pairs = [];
      const messages = currentMessages || [];
      for (let i = 0; i < messages.length - 1; i++) {
        if (messages[i].role === 'user' && messages[i + 1].role === 'assistant') {
          const answer = messages[i + 1].responseData?.answer ?? messages[i + 1].content ?? '';
          pairs.push({ question: messages[i].content, answer });
        }
      }
      const conversationHistory = pairs.slice(-6);
      
      const result = await marketingAgentService.marketingQA(q, conversationHistory);
      
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
        handleResponse(q, userMsg, assistantMsg, response);
      } else {
        throw new Error(result.message || 'Failed to get response');
      }
    } catch (error) {
      const errMsg = error?.response?.data?.error ?? error?.response?.data?.message ?? error?.message ?? '';
      const isRateLimit = /429|rate limit/i.test(errMsg);
      const description = isRateLimit
        ? 'Server is busy. Please try again in a few seconds.'
        : 'Something went wrong. Please try again.';
      
      toast({ 
        title: 'Error', 
        description, 
        variant: 'destructive' 
      });
    } finally {
      setLoading(false);
    }
  };

  const handleResponse = (q, userMsg, assistantMsg, response) => {
    const now = new Date().toISOString();

    if (selectedChatId) {
      const chat = chats.find((c) => c.id === selectedChatId);
      if (chat) {
        const updatedChat = {
          ...chat,
          messages: [...(chat.messages || []), userMsg, assistantMsg],
          timestamp: now,
        };
        const updated = chats.map((c) => (c.id === selectedChatId ? updatedChat : c));
        setChats(updated);
        saveChats(updated);
      } else {
        createNewChat(q, response, userMsg, assistantMsg, now);
      }
    } else {
      createNewChat(q, response, userMsg, assistantMsg, now);
    }

    setQuestion('');
    setSuggestedValue('__none__');
    textareaRef.current?.focus();
  };

  const createNewChat = (q, response, userMsg, assistantMsg, now) => {
    const newChat = {
      id: Date.now().toString(),
      messages: [userMsg, assistantMsg],
      timestamp: now,
    };
    const updated = [newChat, ...chats];
    setChats(updated);
    saveChats(updated);
    setSelectedChatId(newChat.id);
  };

  const newChat = () => {
    setSelectedChatId(null);
    setQuestion('');
    setSuggestedValue('__none__');
    textareaRef.current?.focus();
  };

  const deleteChat = (e, chatId) => {
    e.stopPropagation();
    const updated = chats.filter((c) => c.id !== chatId);
    setChats(updated);
    saveChats(updated);
    if (selectedChatId === chatId) setSelectedChatId(null);
    toast({ 
      title: 'Deleted', 
      description: 'Conversation removed.' 
    });
  };

  const truncate = (s, n = 50) => (s.length <= n ? s : s.slice(0, n) + '…');
  
  const formatDate = (iso) => {
    try {
      const d = new Date(iso);
      const now = new Date();
      const diff = now - d;
      
      if (diff < 86400000) { // Less than 24 hours
        return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
      } else if (diff < 604800000) { // Less than 7 days
        return d.toLocaleDateString(undefined, { weekday: 'short' });
      } else {
        return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
      }
    } catch {
      return '';
    }
  };

  return (
    <motion.div 
      className="h-full min-h-0 flex gap-4"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
    >
      {/* Sidebar - Previous chats */}
      <motion.div 
        variants={itemVariants}
        className={cn(
          "shrink-0 flex flex-col rounded-xl border bg-card overflow-hidden transition-all duration-300",
          sidebarOpen ? "w-80" : "w-16"
        )}
      >
        <div className="p-4 border-b flex items-center justify-between bg-gradient-to-r from-primary/5 via-transparent to-transparent">
          <AnimatePresence mode="wait">
            {sidebarOpen ? (
              <motion.span
                key="title"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="text-sm font-semibold flex items-center gap-2"
              >
                <MessageCircle className="h-4 w-4 text-primary" />
                Conversations
              </motion.span>
            ) : (
              <motion.div
                key="icon"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="w-full flex justify-center"
              >
                <MessageCircle className="h-4 w-4 text-primary" />
              </motion.div>
            )}
          </AnimatePresence>
          <div className="flex items-center gap-1">
            <Button 
              variant="ghost" 
              size="icon" 
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="h-7 w-7 hover:bg-primary/10"
            >
              {sidebarOpen ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            </Button>
            <Button 
              variant="ghost" 
              size="icon" 
              onClick={newChat} 
              title="New conversation"
              className="h-7 w-7 hover:bg-primary/10"
            >
              <Plus className="h-4 w-4" />
            </Button>
          </div>
        </div>
        
        <div className="flex-1 overflow-y-auto scrollbar-thin">
          {chats.length === 0 ? (
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="p-6 text-center"
            >
              {sidebarOpen ? (
                <>
                  <motion.div
                    animate={{
                      scale: [1, 1.1, 1],
                      rotate: [0, 5, -5, 0]
                    }}
                    transition={{
                      duration: 3,
                      repeat: Infinity,
                      repeatType: "reverse"
                    }}
                  >
                    <MessageCircle className="h-12 w-12 mx-auto mb-3 text-muted-foreground/30" />
                  </motion.div>
                  <p className="text-sm text-muted-foreground">No conversations yet</p>
                  <p className="text-xs text-muted-foreground/70 mt-1">Ask a question to start</p>
                </>
              ) : (
                <MessageCircle className="h-5 w-5 mx-auto text-muted-foreground/50" />
              )}
            </motion.div>
          ) : (
            <div className="p-2 space-y-1">
              <AnimatePresence>
                {[...chats]
                  .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
                  .map((c, index) => {
                    const firstQuestion = c.messages?.find(m => m.role === 'user')?.content || 'New chat';
                    const messageCount = c.messages?.filter(m => m.role === 'user').length || 0;
                    
                    return (
                      <motion.div
                        key={c.id}
                        variants={sidebarItemVariants}
                        initial="hidden"
                        animate="visible"
                        exit={{ x: -20, opacity: 0 }}
                        whileHover="hover"
                        transition={{ delay: index * 0.05 }}
                        className={cn(
                          "group relative flex items-start gap-2 w-full p-3 rounded-lg text-sm transition-all cursor-pointer",
                          selectedChatId === c.id 
                            ? 'bg-primary/10 border border-primary/20 shadow-sm' 
                            : 'hover:bg-muted/80'
                        )}
                        onClick={() => setSelectedChatId(c.id)}
                      >
                        <div className={cn(
                          "shrink-0 rounded-lg p-1.5",
                          selectedChatId === c.id ? 'bg-primary/20' : 'bg-muted'
                        )}>
                          <MessageSquare className={cn(
                            "h-3.5 w-3.5",
                            selectedChatId === c.id ? 'text-primary' : 'text-muted-foreground'
                          )} />
                        </div>
                        
                        {sidebarOpen ? (
                          <>
                            <div className="flex-1 min-w-0">
                              <div className="font-medium truncate flex items-center gap-1">
                                {truncate(firstQuestion, 25)}
                                {messageCount > 1 && (
                                  <Badge variant="outline" className="h-4 px-1 text-[10px]">
                                    {messageCount}
                                  </Badge>
                                )}
                              </div>
                              <div className="flex items-center gap-1 mt-1 text-[10px] text-muted-foreground">
                                <Clock className="h-3 w-3" />
                                {formatDate(c.timestamp)}
                              </div>
                            </div>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6 shrink-0 opacity-0 group-hover:opacity-100 hover:bg-destructive/10 hover:text-destructive"
                              onClick={(e) => deleteChat(e, c.id)}
                            >
                              <X className="h-3 w-3" />
                            </Button>
                          </>
                        ) : (
                          <div className="absolute -top-1 -right-1">
                            <Badge variant="outline" className="h-3 px-1 text-[8px]">
                              {messageCount}
                            </Badge>
                          </div>
                        )}
                      </motion.div>
                    );
                  })}
              </AnimatePresence>
            </div>
          )}
        </div>
      </motion.div>

      {/* Main chat area */}
      <motion.div 
        variants={itemVariants}
        className="flex-1 min-w-0 min-h-0"
      >
        <Card className="h-full flex flex-col overflow-hidden border-0 shadow-lg">
          {/* Header */}
          <CardHeader className="shrink-0 bg-gradient-to-r from-primary/5 via-transparent to-transparent border-b pb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <motion.div 
                  whileHover={{ rotate: 360 }}
                  transition={{ duration: 0.5 }}
                  className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10"
                >
                  <Bot className="h-5 w-5 text-primary" />
                </motion.div>
                <div>
                  <CardTitle className="flex items-center gap-2">
                    Marketing Q&A Assistant
                    <Badge variant="outline" className="bg-primary/5 gap-1">
                      <Zap className="h-3 w-3 text-primary" />
                      AI-Powered
                    </Badge>
                  </CardTitle>
                  <CardDescription>
                    Ask anything about your campaigns, performance, and marketing data
                  </CardDescription>
                </div>
              </div>
              {selectedChat && (
                <Badge variant="secondary" className="gap-1">
                  <MessageSquare className="h-3 w-3" />
                  {currentMessages.filter(m => m.role === 'user').length} questions
                </Badge>
              )}
            </div>
          </CardHeader>

          {/* Messages area */}
          <CardContent className="flex-1 overflow-y-auto p-6 scrollbar-thin bg-gradient-to-b from-background via-background to-muted/20">
            <AnimatePresence mode="popLayout">
              {!selectedChatId ? (
                <motion.div
                  key="welcome"
                  variants={messageVariants}
                  initial="hidden"
                  animate="visible"
                  exit="hidden"
                  className="flex flex-col items-center justify-center h-full text-center"
                >
                  <motion.div
                    animate={{
                      scale: [1, 1.1, 1],
                      rotate: [0, 5, -5, 0]
                    }}
                    transition={{
                      duration: 2,
                      repeat: Infinity,
                      repeatType: "reverse"
                    }}
                  >
                    <Bot className="h-20 w-20 text-primary/20 mb-1" />
                  </motion.div>
                  <h3 className="text-xl font-semibold mb-2">Welcome to Marketing Q&A</h3>
                  <p className="text-muted-foreground max-w-md mb-2">
                    Ask me about campaign performance, ROI, conversion rates, and get data-driven insights
                  </p>
                  
                  <div className="grid grid-cols-2 gap-3 max-w-lg">
                    <div className="flex items-center gap-2 p-3 r">
                      <BarChart3 className="h-4 w-4 text-emerald-500" />
                      <span className="text-sm">Campaign ROI</span>
                    </div>
                    <div className="flex items-center gap-2 p-3 r">
                      <Target className="h-4 w-4 text-purple-500" />
                      <span className="text-sm">Conversion Rates</span>
                    </div>
                    <div className="flex items-center gap-2 p-3 r">
                      <TrendingUp className="h-4 w-4 text-amber-500" />
                      <span className="text-sm">Channel Analysis</span>
                    </div>
                    <div className="flex items-center gap-2 p-3 r">
                      <Lightbulb className="h-4 w-4 text-rose-500" />
                      <span className="text-sm">Recommendations</span>
                    </div>
                  </div>
                </motion.div>
              ) : (
                <div className="space-y-4">
                  <AnimatePresence>
                    {currentMessages.map((msg, i) => (
                      <motion.div
                        key={i}
                        variants={messageVariants}
                        initial="hidden"
                        animate="visible"
                        exit="exit"
                        className={cn(
                          "flex",
                          msg.role === 'user' ? 'justify-end' : 'justify-start'
                        )}
                      >
                        <div className={cn(
                          "max-w-[85%] rounded-2xl overflow-hidden",
                          msg.role === 'user' 
                            ? 'bg-primary text-primary-foreground' 
                            : 'bg-muted/50 border shadow-sm'
                        )}>
                          {msg.role === 'user' ? (
                            <div className="px-4 py-3">
                              <div className="flex items-center gap-2 mb-1">
                                <User className="h-3 w-3 opacity-70" />
                                <span className="text-xs opacity-70">You</span>
                              </div>
                              <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                            </div>
                          ) : (
                            <div className="px-5 py-4">
                              <div className="flex items-center gap-2 mb-3">
                                <div className="rounded-full bg-primary/10 p-1">
                                  <Bot className="h-3 w-3 text-primary" />
                                </div>
                                <span className="text-xs font-medium">Marketing Assistant</span>
                                {msg.responseData?.research_id && (
                                  <Badge variant="outline" className="text-[10px] h-4">
                                    ID: {msg.responseData.research_id.slice(0, 6)}
                                  </Badge>
                                )}
                              </div>
                              
                              <div
                                className="prose prose-base max-w-none dark:prose-invert [&_h2]:text-primary [&_strong]:font-semibold"
                                dangerouslySetInnerHTML={{ 
                                  __html: markdownToHtml(msg.responseData?.answer || msg.content) 
                                }}
                              />
                              
                              {msg.responseData?.insights?.length > 0 && (
                                <motion.div 
                                  initial={{ opacity: 0, y: 10 }}
                                  animate={{ opacity: 1, y: 0 }}
                                  className="mt-4 pt-4 border-t border-border/50"
                                >
                                  <h4 className="text-sm font-semibold flex items-center gap-2 mb-3">
                                    <Sparkles className="h-4 w-4 text-amber-500" />
                                    Key Insights
                                  </h4>
                                  <div className="grid grid-cols-2 gap-2">
                                    {msg.responseData.insights.map((insight, j) => (
                                      <div 
                                        key={j}
                                        className="rounded-lg bg-muted/50 p-3 border"
                                      >
                                        <p className="text-xs font-medium text-muted-foreground mb-1">
                                          {insight.title || 'Metric'}
                                        </p>
                                        <p className="text-sm font-semibold">
                                          {insight.value || 'N/A'}
                                        </p>
                                      </div>
                                    ))}
                                  </div>
                                </motion.div>
                              )}
                            </div>
                          )}
                        </div>
                      </motion.div>
                    ))}
                  </AnimatePresence>
                  
                  {loading && (
                    <motion.div
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="flex justify-start"
                    >
                      <div className="bg-muted border rounded-2xl px-4 py-3 flex items-center gap-3">
                        <motion.div
                          animate={{ rotate: 360 }}
                          transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                        >
                          <Loader2 className="h-4 w-4 text-primary" />
                        </motion.div>
                        <span className="text-sm">Analyzing your data...</span>
                      </div>
                    </motion.div>
                  )}
                  
                  <div ref={messagesEndRef} />
                </div>
              )}
            </AnimatePresence>
          </CardContent>

          {/* Input form */}
          <div className="shrink-0 border-t bg-muted/30 p-4">
            <form onSubmit={handleSubmit} className="space-y-3">
              <div className="flex gap-2">
                <div className="flex-1 relative">
                  <Textarea
                    ref={textareaRef}
                    placeholder="Ask a marketing question..."
                    value={question}
                    onChange={(e) => { 
                      setQuestion(e.target.value); 
                      setSuggestedValue('__none__'); 
                    }}
                    onKeyDown={(e) => { 
                      if (e.key === 'Enter' && !e.shiftKey) { 
                        e.preventDefault(); 
                        handleSubmit(e); 
                      } 
                    }}
                    rows={2}
                    disabled={loading}
                    className="min-h-[60px] resize-none pr-10 bg-background"
                  />
                  {question && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="absolute right-2 top-2 h-6 w-6"
                      onClick={() => setQuestion('')}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  )}
                </div>
                
                <motion.div
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  <Button 
                    type="submit" 
                    disabled={loading || !question.trim()} 
                    size="icon" 
                    className="mt-1 h-[50px] w-12 shrink-0 bg-primary hover:bg-primary/90"
                  >
                    {loading ? (
                      <Loader2 className="h-5 w-5 animate-spin" />
                    ) : (
                      <Send className="h-5 w-5" />
                    )}
                  </Button>
                </motion.div>
              </div>

              {/* Suggested questions */}
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowSuggestions(!showSuggestions)}
                  className="gap-1 h-7 text-xs"
                >
                  <HelpCircle className="h-3 w-3" />
                  {showSuggestions ? 'Hide' : 'Show'} suggestions
                </Button>
                
                <AnimatePresence>
                  {showSuggestions && (
                    <motion.div
                      initial={{ opacity: 0, width: 0 }}
                      animate={{ opacity: 1, width: '80%' }}
                      exit={{ opacity: 0, width: 0 }}
                      className="overflow-hidden "
                    >
                      <Select value={suggestedValue} onValueChange={fillFromSuggestion}>
                        <SelectTrigger className="h-7 text-xs gap-1 min-w-[180px]">
                          <SelectValue placeholder="Try a suggested question" />
                        </SelectTrigger>
                        <SelectContent>
                          {SUGGESTED_QUESTIONS.map((group) => (
                            <React.Fragment key={group.group}>
                              <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground flex items-center gap-1">
                                <group.icon className={cn("h-3 w-3", group.color)} />
                                {group.group}
                              </div>
                              {group.options.map((opt) => (
                                <SelectItem key={opt} value={opt} className="text-xs pl-6">
                                  {truncate(opt, 45)}
                                </SelectItem>
                              ))}
                            </React.Fragment>
                          ))}
                        </SelectContent>
                      </Select>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* Quick action chips */}
              {/* {!selectedChatId && showSuggestions && (
                <motion.div 
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="flex flex-wrap gap-2 mt-2"
                >
                  {SUGGESTED_QUESTIONS.slice(0, 2).flatMap(group => 
                    group.options.slice(0, 2).map((prompt, i) => (
                      <Button
                        key={i}
                        variant="outline"
                        size="sm"
                        className="text-xs h-7 bg-background/50 hover:bg-primary/5"
                        onClick={() => setQuestion(prompt)}
                      >
                        {truncate(prompt, 20)}
                      </Button>
                    ))
                  )}
                </motion.div>
              )} */}
            </form>
          </div>
        </Card>
      </motion.div>
    </motion.div>
  );
};

export default MarketingQA;