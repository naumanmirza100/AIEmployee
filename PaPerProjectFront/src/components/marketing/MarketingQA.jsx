import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
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
  ChevronUp,
  ChevronDown,
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
  AlertCircle,
  Search,
  BarChart2,
  Maximize2,
  Save,
  LayoutDashboard,
  PieChart,
  Activity
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

const SUGGESTED_GRAPH_QUESTIONS = [
  'Show campaigns by status as a pie chart',
  'Display open rate by campaign as a bar chart',
  'Compare emails sent by campaign',
  'Show leads per campaign',
  'Display replies by campaign as a bar chart',
  'Top 5 campaigns by emails sent',
  'Campaigns by status',
  'Open rate by campaign',
];

const SUGGESTED_SEARCH_QUESTIONS = [
  'What campaigns are performing best?',
  'What is our overall ROI?',
  'Which marketing channels are most effective?',
  'How are our campaigns performing this month?',
  'What should we focus on to improve performance?',
];

// Chart components
const SimpleBarChart = ({ data, colors, height = 250, title }) => {
  if (!data || Object.keys(data).length === 0) return <div className="text-sm text-muted-foreground">No data available</div>;
  const maxValue = Math.max(...Object.values(data), 1);
  const defaultColors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];
  const chartColors = colors || defaultColors;
  return (
    <div className="space-y-3" style={{ minHeight: `${height}px` }}>
      {title && <h4 className="font-medium text-sm text-muted-foreground mb-4">{title}</h4>}
      {Object.entries(data).map(([key, value], index) => (
        <div key={key}>
          <div className="flex justify-between text-xs mb-1">
            <span className="text-sm">{key}</span>
            <span className="font-semibold">{value}</span>
          </div>
          <div className="w-full bg-muted rounded-full h-2">
            <div
              className="h-2 rounded-full transition-all"
              style={{
                width: `${(value / maxValue) * 100}%`,
                backgroundColor: chartColors[index % chartColors.length],
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
};

const SimplePieChart = ({ data, colors, title }) => {
  if (!data || Object.keys(data).length === 0) return <div className="text-sm text-muted-foreground">No data available</div>;
  const total = Object.values(data).reduce((sum, val) => sum + val, 0);
  if (total === 0) return <div className="text-sm text-muted-foreground">No data available</div>;
  const defaultColors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];
  const chartColors = colors || defaultColors;
  let currentAngle = 0;
  const segments = Object.entries(data).map(([key, value], index) => {
    const angle = (value / total) * 360;
    const slice = { key, value, percentage: Math.round((value / total) * 100), color: chartColors[index % chartColors.length], angle, startAngle: currentAngle };
    currentAngle += angle;
    return slice;
  });
  return (
    <div className="flex flex-col items-center gap-4">
      {title && <h4 className="font-medium text-sm text-muted-foreground">{title}</h4>}
      <div className="relative w-48 h-48 sm:w-56 sm:h-56">
        <svg width="100%" height="100%" viewBox="0 0 200 200" className="transform -rotate-90">
          {segments.map((segment, index) => {
            const x1 = 100 + 100 * Math.cos((segment.startAngle * Math.PI) / 180);
            const y1 = 100 + 100 * Math.sin((segment.startAngle * Math.PI) / 180);
            const x2 = 100 + 100 * Math.cos(((segment.startAngle + segment.angle) * Math.PI) / 180);
            const y2 = 100 + 100 * Math.sin(((segment.startAngle + segment.angle) * Math.PI) / 180);
            const largeArc = segment.angle > 180 ? 1 : 0;
            return (
              <path
                key={index}
                d={`M100,100 L${x1},${y1} A100,100 0 ${largeArc},1 ${x2},${y2} Z`}
                fill={segment.color}
                stroke="#000"
                strokeWidth="1"
              />
            );
          })}
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center">
            <div className="text-2xl font-bold">{total}</div>
            <div className="text-xs text-muted-foreground">Total</div>
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 w-full max-w-xs">
        {segments.map((segment, index) => (
          <div key={index} className="flex items-center gap-2 text-xs sm:text-sm">
            <div className="w-3 h-3 rounded shrink-0" style={{ backgroundColor: segment.color }} />
            <span className="truncate flex-1">{segment.key}</span>
            <span className="font-medium shrink-0">{segment.percentage}%</span>
          </div>
        ))}
      </div>
    </div>
  );
};

const SimpleLineChart = ({ data, color = '#3b82f6', height = 200, title }) => {
  if (!data || data.length === 0) return <div className="text-sm text-muted-foreground">No data available</div>;
  const values = data.map(d => d.value ?? d.count ?? 0);
  const maxValue = Math.max(...values, 1);
  const labels = data.map(d => d.label ?? d.date ?? d.month ?? '');
  const points = values.map((value, index) => {
    const x = (index / (values.length - 1 || 1)) * 100;
    const y = 100 - (value / maxValue) * 100;
    return `${x},${y}`;
  }).join(' ');
  const areaPoints = `0,100 ${points} 100,100`;
  return (
    <div className="space-y-2">
      {title && <h4 className="font-medium text-sm text-muted-foreground">{title}</h4>}
      <div className="relative w-full" style={{ height: `${height}px` }}>
        <svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none">
          <polygon points={areaPoints} fill={`${color}20`} />
          <polyline points={points} fill="none" stroke={color} strokeWidth="0.5" strokeLinecap="round" strokeLinejoin="round" />
          {values.map((value, index) => (
            <circle key={index} cx={(index / (values.length - 1 || 1)) * 100} cy={100 - (value / maxValue) * 100} r="1" fill={color} />
          ))}
        </svg>
        <div className="absolute bottom-0 left-0 right-0 flex justify-between text-[10px] text-muted-foreground px-1">
          {labels.length <= 7 ? labels.map((label, i) => <span key={i} className="truncate">{label}</span>) : (
            <><span>{labels[0]}</span><span>{labels[Math.floor(labels.length / 2)]}</span><span>{labels[labels.length - 1]}</span></>
          )}
        </div>
      </div>
    </div>
  );
};

const renderChart = (chartData) => {
  if (!chartData) return null;
  const { type, data, title, color, colors } = chartData;
  switch (type) {
    case 'bar': return <SimpleBarChart data={data} colors={colors} title={title} />;
    case 'pie': return <SimplePieChart data={data} colors={colors} title={title} />;
    case 'line': return <SimpleLineChart data={data} color={color} title={title} />;
    case 'area': return <SimpleLineChart data={data} color={color} title={title} />;
    default: return <SimpleBarChart data={data} colors={colors} title={title} />;
  }
};

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
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [inputMode, setInputMode] = useState('search');
  const [expandedGraph, setExpandedGraph] = useState(null);
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saveTitle, setSaveTitle] = useState('');
  const [saveTags, setSaveTags] = useState('');
  const [saving, setSaving] = useState(false);
  const [currentPromptData, setCurrentPromptData] = useState(null);
  const [comparisonResults, setComparisonResults] = useState([]);
  
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

  // Load prompt from dashboard when clicking saved graph
  useEffect(() => {
    if (window.marketingQALoadPrompt) {
      const { prompt, chartType } = window.marketingQALoadPrompt;
      if (prompt) {
        setQuestion(prompt);
        setInputMode('graph');
        textareaRef.current?.focus();
        // Clear the flag
        window.marketingQALoadPrompt = null;
      }
    }
  }, []);

  const fillFromSuggestion = (value) => {
    const v = value || '__none__';
    setSuggestedValue(v);
    if (v !== '__none__') {
      setQuestion(v);
      textareaRef.current?.focus();
    }
  };

  // Compare manual query with AI response
  const compareResponses = async (query, inputMode) => {
    try {
      console.log('🔍 Starting comparison for query:', query);
      
      // Manual API call
      let manualResponse;
      if (inputMode === 'graph') {
        manualResponse = await marketingAgentService.generateGraph(query);
      } else {
        manualResponse = await marketingAgentService.marketingQA(query, []);
      }
      
      console.log('📊 Manual API Response:', manualResponse);

      // Store comparison result
      const comparisonData = {
        query,
        mode: inputMode,
        timestamp: new Date().toISOString(),
        manualResponse,
        status: manualResponse?.status,
        success: manualResponse?.status === 'success'
      };

      if (inputMode === 'graph') {
        comparisonData.manualChart = manualResponse?.data?.chart;
        comparisonData.manualTitle = manualResponse?.data?.title;
        comparisonData.manualInsights = manualResponse?.data?.insights;
      } else {
        comparisonData.manualAnswer = manualResponse?.data?.answer;
        comparisonData.manualInsights = manualResponse?.data?.insights;
      }

      // Add to comparison results
      setComparisonResults(prev => [comparisonData, ...prev].slice(0, 20)); // Keep last 20
      
      console.log('✅ Comparison Result:', comparisonData);
      console.log('📈 All Comparisons:', [comparisonData, ...comparisonResults]);
      
      return comparisonData;
    } catch (error) {
      const errorData = {
        query,
        mode: inputMode,
        timestamp: new Date().toISOString(),
        error: error?.message,
        status: 'error',
        success: false
      };
      
      console.error('❌ Comparison Error:', errorData);
      setComparisonResults(prev => [errorData, ...prev].slice(0, 20));
      
      return errorData;
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

    // Check for special cases (only for search mode)
    if (inputMode === 'search') {
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
      
      let result;
      
      if (inputMode === 'graph') {
        // Call graph generation API
        result = await marketingAgentService.generateGraph(q);
      } else {
        // Call QA API
        result = await marketingAgentService.marketingQA(q, conversationHistory);
      }
      
      if (result.status === 'success' && result.data) {
        const response = result.data;
        
        if (inputMode === 'graph') {
          // Handle graph response
          const userMsg = { role: 'user', content: q };
          const assistantMsg = { 
            role: 'assistant', 
            content: q, 
            responseData: {
              isGraph: true,
              chart: response.chart,
              chartTitle: response.title || 'Chart',
              chartType: response.type,
              insights: response.insights || []
            }
          };
          handleResponse(q, userMsg, assistantMsg, response);
        } else {
          // Handle QA response
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
        }
      } else {
        throw new Error(result.message || 'Failed to get response');
      }
      
      // Run comparison in background (no await - non-blocking)
      compareResponses(q, inputMode).catch(err => console.error('Comparison failed:', err));
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

  const openSaveModal = (prompt, chartTitle, chartType) => {
    setCurrentPromptData({ prompt, chartTitle, chartType });
    setSaveTitle(chartTitle || '');
    setSaveTags('');
    setSaveModalOpen(true);
  };

  const handleSavePrompt = async () => {
    if (!saveTitle.trim()) {
      toast({
        title: 'Error',
        description: 'Please enter a title',
        variant: 'destructive'
      });
      return;
    }

    try {
      setSaving(true);
      const promptData = {
        title: saveTitle,
        prompt: currentPromptData.prompt,
        tags: saveTags.split(',').map(t => t.trim()).filter(t => t),
        chart_type: currentPromptData.chartType
      };
      
      await marketingAgentService.saveGraphPrompt(promptData);
      
      toast({
        title: 'Success',
        description: 'Prompt saved successfully'
      });
      setSaveModalOpen(false);
      setSaveTitle('');
      setSaveTags('');
      setCurrentPromptData(null);
    } catch (error) {
      console.error('Save prompt error:', error);
      toast({
        title: 'Error',
        description: error?.response?.data?.message || 'Failed to save prompt',
        variant: 'destructive'
      });
    } finally {
      setSaving(false);
    }
  };

  const handleAddToDashboard = async (prompt, chartTitle, chartType) => {
    try {
      // First save the prompt
      const promptData = {
        title: chartTitle || 'Untitled Chart',
        prompt: prompt,
        tags: ['dashboard'],
        chart_type: chartType
      };
      
      await marketingAgentService.saveGraphPrompt(promptData);
      
      toast({
        title: 'Success',
        description: 'Chart added to dashboard'
      });
    } catch (error) {
      console.error('Add to dashboard error:', error);
      toast({
        title: 'Error',
        description: error?.response?.data?.message || 'Failed to add to dashboard',
        variant: 'destructive'
      });
    }
  };

  // Expose comparison results to window for debugging
  useEffect(() => {
    window.marketingQAComparison = {
      getComparisons: () => comparisonResults,
      getLatestComparison: () => comparisonResults[0],
      compareNow: (query, mode = 'search') => compareResponses(query, mode),
      getAllComparisonStatus: () => ({
        total: comparisonResults.length,
        successful: comparisonResults.filter(c => c.success).length,
        failed: comparisonResults.filter(c => !c.success).length,
        byMode: {
          search: comparisonResults.filter(c => c.mode === 'search').length,
          graph: comparisonResults.filter(c => c.mode === 'graph').length
        }
      })
    };
    
    console.log('🎯 Marketing QA Comparison Tool Available');
    console.log('Usage: window.marketingQAComparison.getComparisons()');
    
    return () => {
      delete window.marketingQAComparison;
    };
  }, [comparisonResults]);

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
                              
                              {msg.responseData?.isGraph ? (
                                <>
                                  <div className="space-y-3">
                                    {msg.responseData.chart && (
                                      <div className="relative w-full rounded-xl border border-border bg-card p-3 shadow-sm">
                                        <Button
                                          type="button"
                                          variant="ghost"
                                          size="icon"
                                          className="absolute top-2 right-2 h-7 w-7 rounded-md opacity-70 hover:opacity-100 text-muted-foreground hover:text-foreground"
                                          onClick={() => setExpandedGraph({ chart: msg.responseData.chart, chartTitle: msg.responseData.chartTitle })}
                                          title="Expand graph"
                                        >
                                          <Maximize2 className="h-3.5 w-3.5" />
                                        </Button>
                                        <div className="pr-8">
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
                                          currentMessages[currentMessages.indexOf(msg) - 1]?.content,
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
                                          currentMessages[currentMessages.indexOf(msg) - 1]?.content,
                                          msg.responseData.chartTitle,
                                          msg.responseData.chartType
                                        )}
                                        className="rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground"
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
                                </>
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
              <div className="flex gap-3 items-center min-h-[48px]">
                <Select value={inputMode} onValueChange={setInputMode}>
                  <SelectTrigger className="w-[140px] h-11 rounded-lg text-sm gap-2 border-border bg-background">
                    {inputMode === 'search' ? (
                      <>
                        <Search className="h-4 w-4" />
                        <span>Search</span>
                      </>
                    ) : (
                      <>
                        <BarChart2 className="h-4 w-4" />
                        <span>Graph</span>
                      </>
                    )}
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="search">
                      <div className="flex items-center gap-2">
                        <Search className="h-4 w-4" />
                        <span>Search QA</span>
                      </div>
                    </SelectItem>
                    <SelectItem value="graph">
                      <div className="flex items-center gap-2">
                        <BarChart2 className="h-4 w-4" />
                        <span>Generate Graph</span>
                      </div>
                    </SelectItem>
                  </SelectContent>
                </Select>
                <Textarea
                  ref={textareaRef}
                  placeholder={inputMode === 'search' ? 'Ask about campaign performance, ROI, channels...' : 'Describe the chart you want...'}
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
                  rows={1}
                  disabled={loading}
                  className="flex-1 min-h-[44px] h-11 max-h-32 resize-none rounded-lg border border-border bg-background text-sm py-2.5 text-left"
                />
                <motion.div
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  <Button 
                    type="submit" 
                    disabled={loading || !question.trim()} 
                    size="icon" 
                    className="h-11 w-11 shrink-0 rounded-lg bg-primary hover:bg-primary/90"
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
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground font-medium">Try these examples</span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowSuggestions(!showSuggestions)}
                    className="h-6 w-6 p-0 text-muted-foreground hover:text-foreground"
                    title={showSuggestions ? 'Hide suggestions' : 'Show suggestions'}
                  >
                    {showSuggestions ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </Button>
                </div>
                
                <AnimatePresence>
                  {showSuggestions && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
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

        {/* Expand graph dialog */}
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

        {/* Save prompt dialog */}
        <Dialog open={saveModalOpen} onOpenChange={(open) => {
          if (!open) {
            setSaveModalOpen(false);
            setSaveTitle('');
            setSaveTags('');
            setCurrentPromptData(null);
          }
        }}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Save Prompt</DialogTitle>
              <DialogDescription>Save this graph prompt for quick access later.</DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="save-title">Title</Label>
                <Input
                  id="save-title"
                  value={saveTitle}
                  onChange={(e) => setSaveTitle(e.target.value)}
                  placeholder="e.g. Monthly Campaign Performance"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="save-tags">Tags (comma-separated)</Label>
                <Input
                  id="save-tags"
                  value={saveTags}
                  onChange={(e) => setSaveTags(e.target.value)}
                  placeholder="e.g. analytics, campaigns"
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setSaveModalOpen(false)}>Cancel</Button>
              <Button onClick={handleSavePrompt} disabled={saving}>
                {saving ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Saving...</> : <><Save className="h-4 w-4 mr-2" /> Save Prompt</>}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
        </Card>
      </motion.div>
    </motion.div>
  );
};

export default MarketingQA;