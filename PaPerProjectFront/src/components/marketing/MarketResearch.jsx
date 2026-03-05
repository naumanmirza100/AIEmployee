import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ChevronLeft } from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import { Badge } from '@/components/ui/badge';
import { 
  Loader2, 
  Sparkles, 
  Search, 
  Plus, 
  FileSearch, 
  Send, 
  Trash2,
  TrendingUp,
  Users,
  Globe,
  Target,
  AlertCircle,
  CheckCircle2,
  Lightbulb,
  BarChart3,
  MessageSquare,
  Bot,
  User,
  Clock,
  Calendar,
  ChevronDown,
  ChevronRight,
  X,
  Filter,
  BookOpen,
  Award
} from 'lucide-react';
import marketingAgentService from '@/services/marketingAgentService';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/lib/utils';

const STORAGE_KEY = 'marketing_research_chats';

/** Research types matching backend. General = verify/question fits any type; others = must match selected type. */
const RESEARCH_TYPES = [
  { value: 'general', label: 'General', icon: Search, color: 'text-slate-500', bgColor: 'bg-slate-500/10' },
  { value: 'market_trend', label: 'Market Trend', icon: TrendingUp, color: 'text-blue-500', bgColor: 'bg-blue-500/10' },
  { value: 'competitor', label: 'Competitor', icon: Users, color: 'text-purple-500', bgColor: 'bg-purple-500/10' },
  { value: 'customer_behavior', label: 'Customer Behavior', icon: Target, color: 'text-emerald-500', bgColor: 'bg-emerald-500/10' },
  { value: 'opportunity', label: 'Opportunity', icon: Lightbulb, color: 'text-amber-500', bgColor: 'bg-amber-500/10' },
  { value: 'threat', label: 'Risk & Threat', icon: AlertCircle, color: 'text-rose-500', bgColor: 'bg-rose-500/10' },
];

/** Simple markdown to HTML with enhanced styling */
function markdownToHtml(markdown) {
  if (!markdown || typeof markdown !== 'string') return '';
  
  const escape = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const bold = (s) => s.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-primary">$1</strong>');
  
  const lines = markdown.split('\n');
  const out = [];
  let inList = false;
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const t = line.trim();
    
    if (/^---+$/.test(t)) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push('<hr class="my-4 border-border/50"/>');
      continue;
    }
    
    if (/^## /.test(t)) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<h2 class="text-lg font-semibold mt-4 mb-2 text-primary border-b pb-1">${bold(escape(t.slice(3)))}</h2>`);
      continue;
    }
    
    if (/^### /.test(t)) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<h3 class="text-base font-semibold mt-3 mb-1">${bold(escape(t.slice(4)))}</h3>`);
      continue;
    }
    
    if (/^[\s]*(?:•|-|\*|\d+\.)\s+/.test(t)) {
      if (!inList) { 
        out.push('<ul class="list-disc pl-4 my-2 space-y-1.5">'); 
        inList = true; 
      }
      const content = t.replace(/^[\s]*(?:•|-|\*|\d+\.)\s+/, '');
      out.push(`<li class="text-sm leading-relaxed">${bold(escape(content))}</li>`);
      continue;
    }
    
    if (t === '' && inList) {
      out.push('</ul>');
      inList = false;
      continue;
    }
    
    if (t && !t.startsWith('<')) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<p class="my-2 leading-relaxed">${bold(escape(t)).replace(/\n/g, '<br/>')}</p>`);
    }
  }
  
  if (inList) out.push('</ul>');
  return out.join('\n');
}

/** Normalize topic for comparison: trim, lower, remove trailing punctuation, collapse spaces, remove zero-width chars */
function normalizeTopic(topic) {
  if (!topic || typeof topic !== 'string') return '';
  return topic
    .replace(/\u200B|\u200C|\u200D|\uFEFF/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
    .replace(/[?!.,;:]+\s*$/, '');
}

/** Fix common typos in normalized text so intent detection still works (used only for matching, not sent to API) */
function fixCommonTyposForDetection(text) {
  if (!text || typeof text !== 'string') return '';
  let t = text;
  const fixes = [
    [/\bwaht\b/g, 'what'], [/\bwhta\b/g, 'what'], [/\bwnat\b/g, 'what'], [/\bwat\b/g, 'what'],
    [/\bthigns\b/g, 'things'], [/\bthigs\b/g, 'things'], [/\btings\b/g, 'things'],
    [/\bknwo\b/g, 'know'], [/\bkonw\b/g, 'know'], [/\bkno\b/g, 'know'],
    [/\babuot\b/g, 'about'], [/\babotu\b/g, 'about'], [/\bboaut\b/g, 'about'],
    [/\btaht\b/g, 'that'], [/\btehm\b/g, 'them'],
    [/\bhelo\b/g, 'hello'], [/\bhelloo\b/g, 'hello'],
    [/\bques\b/g, 'question'], [/\bqustion\b/g, 'question'], [/\bquetsion\b/g, 'question'], [/\bqueston\b/g, 'question'],
    [/\baswer\b/g, 'answer'], [/\banwer\b/g, 'answer'], [/\banser\b/g, 'answer'], [/\basnwer\b/g, 'answer'],
  ];
  fixes.forEach(([pattern, replacement]) => { t = t.replace(pattern, replacement); });
  return t;
}

/** Normalized topic with typo fixes – use only for intent detection (greeting/meta/dismissive/etc.) */
function topicForDetection(topic) {
  return fixCommonTyposForDetection(normalizeTopic(topic));
}

/** True if topic is greeting/small talk – do not call research API */
function isGreetingOrSmallTalk(topic) {
  const t = topicForDetection(topic);
  if (!t) return true;
  if (t.length > 40) return false;
  const smallTalk = new Set([
    'hi', 'hii', 'hiii', 'hello', 'helloo', 'hey', 'heyy', 'heyyy', 'helo', 'heloo',
    'hi there', 'hello there', 'hey there', 'good morning', 'good afternoon', 'good evening', 'howdy',
    'yo', 'sup', "what's up", 'whats up', 'wassup', 'greetings', 'nm', 'nvm', 'nothing', 'idk', 'lol',
    'how are you', 'how are u', 'how r u', 'how r you', 'howre you', "how's it going", 'hows it going',
    'how are you doing', 'how u doing', "what's going on", 'how do you do', 'how is it going',
    'thanks', 'thank you', 'thx', 'ok', 'okay', 'oky', 'okey', 'okie', 'k', 'kk', 'bye', 'goodbye', 'good by', 'cya',
    'good', 'great', 'nice', 'cool', 'alright', 'fine', 'good to know', 'got it', 'understood',
    'perfect', 'sure', 'yeah', 'yep', 'yup', 'nope', 'no', 'yes', 'what', 'why', 'help', 'please',
    'ok good', 'okay good', 'oky good', 'ok god', 'oky god', 'okay god',
    'okya', 'okya good', 'okya god', 'okie good', 'gud', 'gud good',
    'olly', 'oli',
    'lets start', "let's start", 'let us start', 'start', 'ready', 'im ready', "i'm ready", 'we can start', 'can we start',
  ]);
  if (smallTalk.has(t)) return true;
  if (t.length <= 30 && (t.startsWith('how are') || t.startsWith("how's it") || t.startsWith('hows it') || t.startsWith('how do you do'))) return true;
  if (t.length <= 25 && (t.startsWith('lets start') || t.startsWith("let's start") || t.startsWith('can we start') || t.startsWith('we can start'))) return true;
  if (t.length <= 14 && /^ok[a-z]*\s*(good|god|gud)?$/.test(t)) return true;
  return false;
}

/** True if topic is a definition/general-knowledge question (full form of X, what is X) – not research */
function isDefinitionOrGeneralQuestion(topic) {
  const t = topicForDetection(topic);
  if (!t || t.length > 80) return false;
  const definitionPhrases = [
    'full form of', 'full form', 'what is the full form', 'fullform of',
    'what does ', 'what is ', 'meaning of', 'what do you mean by',
    'define ', 'definition of', 'abbreviation of', 'stand for',
  ];
  return definitionPhrases.some((p) => t.includes(p));
}

/** True if topic is a meta question (what can I ask, how can you help) – do not run full research */
function isMetaQuestion(topic) {
  const t = topicForDetection(topic);
  if (!t || t.length > 80) return false;
  const metaPhrases = [
    'what question', 'what questions', 'what can i ask', 'what i can ask', 'what can you answer',
    'what can u answer', 'what question u can answer', 'what questions can u answer',
    'how can you help', 'how can i use', 'what do you do', 'what do you know',
    'what can you tell', 'what can you do', 'how does this work', 'what should i ask',
    'give me examples', 'example questions', 'example topics', 'what to ask',
    'help me', 'what research', 'what can you research', 'what topics',
    'what can u ask', 'what can i ask you', 'what can i ask u',
    'what are the things', 'things you know', 'things u know', 'what do u know', 'what u know',
    'what do you know about', 'what do u know about',
  ];
  return metaPhrases.some((p) => t.includes(p));
}

/** True if topic is dismissive/off-topic (e.g. "ok u dont know about it") – do not run research */
function isDismissiveOrOffTopic(topic) {
  const t = topicForDetection(topic);
  if (!t || t.length > 60) return false;
  const offTopicPhrases = [
    'u dont know', 'you dont know', "don't know about", 'dont know about',
    'you don\'t know', 'u don\'t know', 'okay u dont know', 'ok u dont know',
    'k u dont know', 'okay you dont know', 'ok you dont know',
    'dont know bout', "don't know bout", 'u dont know bout', 'you dont know bout',
  ];
  return offTopicPhrases.some((p) => t.includes(p));
}

/** Short response for meta questions (no API call) */
const META_RESPONSE = {
  success: true,
  research_id: null,
  insights: 'I can help you research:\n\n**Market Trends** - Emerging patterns in your industry\n**Competitor Analysis** - Study competitors\' strategies\n**Customer Behavior** - Understand your audience\n**Opportunities** - Identify growth areas\n**Risks & Threats** - Analyze potential challenges\n\nJust enter a specific topic and choose a research type above!',
  opportunities: [],
  risks: [],
  recommendations: [],
};

/** True if topic is about the user’s own campaigns/company data – direct to Q&A agent, no research */
function isCampaignOrCompanyQuestion(topic) {
  const t = topicForDetection(topic);
  if (!t || t.length > 120) return false;
  const campaignCompanyPhrases = [
    'how many campaign', 'how many campaigns', 'campaigns do you have', 'campaign do you have',
    'do you have campaign', 'do you have any campaign', 'any info about campaign', 'any info on campaign',
    'list my campaign', 'list campaign', 'my campaign', 'my campaigns', 'our campaign', 'our campaigns',
    'company info', 'company data', 'my company', 'our company', 'how many campaign do u',
    'campaigns do u have', 'campaign info', 'campaign data', 'details about campaign',
  ];
  return campaignCompanyPhrases.some((p) => t.includes(p));
}

/** Short response directing user to Q&A for campaign/company questions */
const CAMPAIGN_QA_RESPONSE = {
  success: true,
  research_id: null,
  insights: 'For details about **your campaigns**, **company data**, or **marketing analytics**, please use the **Q&A** tab. I specialize in market and competitive research (trends, competitors, opportunities).\n\nTry asking me about:\n- Market trends in your industry\n- Competitor strategies\n- Customer behavior patterns\n- Growth opportunities\n- Market risks',
  opportunities: [],
  risks: [],
  recommendations: [],
};

/** Short response for definition/general questions – this agent does research only */
const NOT_RESEARCH_RESPONSE = {
  success: true,
  research_id: null,
  insights: 'I focus on **market and competitive research** only (trends, competitors, opportunities, risks).\n\nTry rephrasing as a research topic:\n- "Market trends for [industry]" \n- "Competitor analysis for [company]" \n- "Customer behavior in [sector]" \n- "Opportunities in [market]"',
  opportunities: [],
  risks: [],
  recommendations: [],
};

/** Short response for dismissive/off-topic input – prompt for a real research topic */
const OFF_TOPIC_RESPONSE = {
  success: true,
  research_id: null,
  insights: 'That doesn\'t look like a research topic. Ask me about:\n\n- **Specific markets** (e.g., "cloud adoption in UK")\n- **Competitors** (e.g., "competitor analysis for Amazon")\n- **Trends** (e.g., "AI marketing trends 2024")\n- **Customer behavior** (e.g., "buying patterns in e-commerce")',
  opportunities: [],
  risks: [],
  recommendations: [],
};

/** Normalize chat to { id, messages: [{ role, topic?, researchType?, context?, response? }], timestamp } */
function normalizeChat(c) {
  if (c.messages && Array.isArray(c.messages)) return c;
  if (c.topic != null) {
    return {
      id: c.id,
      messages: [
        { role: 'user', topic: c.topic, researchType: c.researchType, context: c.context },
        { role: 'assistant', response: c.response },
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
    localStorage.setItem(STORAGE_KEY, JSON.stringify(chats.slice(-50)));
  } catch { }
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

const MarketResearch = () => {
  const { toast } = useToast();
  const [chats, setChats] = useState([]);
  const [selectedChatId, setSelectedChatId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [researchType, setResearchType] = useState('general');
  const [topic, setTopic] = useState('');
  const [competitors, setCompetitors] = useState('');
  const [industry, setIndustry] = useState('');
  const [geographicRegion, setGeographicRegion] = useState('');
  const [showContext, setShowContext] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    setChats(loadChats());
  }, []);

  const selectedChat = chats.find((c) => c.id === selectedChatId);
  const currentMessages = selectedChat?.messages ?? [];

  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  useEffect(() => {
    scrollToBottom();
  }, [currentMessages]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!topic.trim()) {
      toast({ 
        title: 'Error', 
        description: 'Please enter a research topic', 
        variant: 'destructive' 
      });
      return;
    }
    
    const trimmedTopic = topic.trim();
    const context = {};
    if (competitors.trim()) context.competitors = competitors.split(',').map((c) => c.trim()).filter(Boolean);
    if (industry.trim()) context.industry = industry.trim();
    if (geographicRegion.trim()) context.geographic_region = geographicRegion.trim();
    
    const userMsg = { 
      role: 'user', 
      topic: trimmedTopic, 
      researchType, 
      context: { competitors, industry, geographicRegion } 
    };

    // Check for special cases
    if (isGreetingOrSmallTalk(trimmedTopic)) {
      const friendlyResponse = {
        success: true,
        research_id: null,
        insights: "👋 Hello! I'm your Market Research Assistant. I can help you analyze:\n\n• **Market Trends** - Emerging patterns in your industry\n• **Competitors** - Study competitors' strategies\n• **Customer Behavior** - Understand your audience\n• **Opportunities** - Identify growth areas\n• **Risks** - Analyze potential challenges\n\nWhat would you like to research today?",
        opportunities: [],
        risks: [],
        recommendations: [],
      };
      const assistantMsg = { role: 'assistant', response: friendlyResponse };
      handleResponse(userMsg, assistantMsg);
      return;
    }

    if (isMetaQuestion(trimmedTopic)) {
      const assistantMsg = { role: 'assistant', response: META_RESPONSE };
      handleResponse(userMsg, assistantMsg);
      return;
    }

    if (isCampaignOrCompanyQuestion(trimmedTopic)) {
      const assistantMsg = { role: 'assistant', response: CAMPAIGN_QA_RESPONSE };
      handleResponse(userMsg, assistantMsg);
      return;
    }

    if (isDefinitionOrGeneralQuestion(trimmedTopic)) {
      const assistantMsg = { role: 'assistant', response: NOT_RESEARCH_RESPONSE };
      handleResponse(userMsg, assistantMsg);
      return;
    }

    if (isDismissiveOrOffTopic(trimmedTopic)) {
      const assistantMsg = { role: 'assistant', response: OFF_TOPIC_RESPONSE };
      handleResponse(userMsg, assistantMsg);
      return;
    }

    // Perform actual research
    try {
      setLoading(true);
      const result = await marketingAgentService.marketResearch(researchType, trimmedTopic, context);

      if (result?.status === 'success' && result?.data) {
        const data = result.data;
        const assistantMsg = { role: 'assistant', response: data };
        handleResponse(userMsg, assistantMsg);
        toast({ 
          title: '✅ Research Complete', 
          description: 'Your market research has been generated successfully.',
        });
      } else {
        throw new Error(result?.message || result?.error || 'Failed to conduct research');
      }
    } catch (error) {
      toast({ 
        title: 'Error', 
        description: 'Something went wrong. Please try again.', 
        variant: 'destructive' 
      });
    } finally {
      setLoading(false);
    }
  };

  const handleResponse = (userMsg, assistantMsg) => {
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
        createNewChat(userMsg, assistantMsg, now);
      }
    } else {
      createNewChat(userMsg, assistantMsg, now);
    }
    
    // Clear form
    setTopic('');
    setCompetitors('');
    setIndustry('');
    setGeographicRegion('');
    setShowContext(false);
    inputRef.current?.focus();
  };

  const createNewChat = (userMsg, assistantMsg, now) => {
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
    setTopic('');
    setCompetitors('');
    setIndustry('');
    setGeographicRegion('');
    setResearchType('general');
    inputRef.current?.focus();
  };

  const deleteChat = (e, chatId) => {
    e.stopPropagation();
    const updated = chats.filter((c) => c.id !== chatId);
    setChats(updated);
    saveChats(updated);
    if (selectedChatId === chatId) setSelectedChatId(null);
    toast({ 
      title: 'Deleted', 
      description: 'Research conversation removed.',
    });
  };

  const truncate = (s, n = 45) => (s.length <= n ? s : s.slice(0, n) + '…');
  
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

  const getTypeIcon = (type) => {
    const found = RESEARCH_TYPES.find(t => t.value === type);
    return found ? found.icon : Search;
  };

  return (
    <motion.div 
      className="h-full min-h-0 flex gap-4"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
    >
      {/* Sidebar - Previous research */}
      <motion.div 
        variants={itemVariants}
        className={cn(
          "shrink-0 flex flex-col rounded-2xl border bg-gradient-to-b from-card to-muted/20 overflow-hidden transition-all duration-300 shadow-lg",
          sidebarOpen ? "w-80" : "w-16"
        )}
      >
        <div className="p-4 border-b flex items-center justify-between bg-gradient-to-r from-primary/10 via-primary/5 to-transparent">
          <AnimatePresence mode="wait">
            {sidebarOpen ? (
              <motion.span
                key="title"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="text-sm font-semibold flex items-center gap-2"
              >
                <BookOpen className="h-4 w-4 text-primary" />
                Research History
              </motion.span>
            ) : (
              <motion.div
                key="icon"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="w-full flex justify-center"
              >
                <BookOpen className="h-4 w-4 text-muted-foreground" />
              </motion.div>
            )}
          </AnimatePresence>
          <div className="flex items-center gap-1">
            <Button 
              variant="ghost" 
              size="icon" 
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="h-7 w-7 rounded-lg hover:bg-primary/20 hover:text-primary transition-all"
            >
              {sidebarOpen ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            </Button>
            <Button 
              variant="ghost" 
              size="icon" 
              onClick={newChat} 
              title="New research"
              className="h-7 w-7 rounded-lg hover:bg-primary/20 hover:text-primary transition-all"
            >
              <Plus className="h-4 w-4" />
            </Button>
          </div>
        </div>
        
        <div className="flex-1 overflow-y-auto scrollbar-thin scrollbar-thumb-primary/20 scrollbar-track-transparent">
          {chats.length === 0 ? (
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="p-6 text-center"
            >
              {sidebarOpen ? (
                <>
                  <FileSearch className="h-12 w-12 mx-auto mb-3 text-muted-foreground/30" />
                  <p className="text-sm text-muted-foreground">No research yet</p>
                  <p className="text-xs text-muted-foreground/70 mt-1">Start a new conversation</p>
                </>
              ) : (
                <FileSearch className="h-5 w-5 mx-auto text-muted-foreground/50" />
              )}
            </motion.div>
          ) : (
            <div className="p-2 space-y-1">
              <AnimatePresence>
                {[...chats]
                  .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
                  .map((c, index) => {
                    const lastUserMsg = c.messages?.find(m => m.role === 'user');
                    const topic = lastUserMsg?.topic || 'Research';
                    const type = lastUserMsg?.researchType || 'general';
                    const Icon = getTypeIcon(type);
                    
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
                          "group relative flex items-start gap-2 w-full p-3 rounded-xl text-sm transition-all cursor-pointer",
                          selectedChatId === c.id 
                            ? 'bg-gradient-to-r from-primary/20 to-primary/5 border border-primary/30 shadow-md' 
                            : 'hover:bg-gradient-to-r hover:from-muted/80 hover:to-muted/40'
                        )}
                        onClick={() => setSelectedChatId(c.id)}
                      >
                        <div className={cn(
                          "shrink-0 rounded-lg p-1.5 transition-all",
                          selectedChatId === c.id ? 'bg-primary/30' : 'bg-muted'
                        )}>
                          <Icon className={cn(
                            "h-3.5 w-3.5",
                            RESEARCH_TYPES.find(t => t.value === type)?.color
                          )} />
                        </div>
                        
                        {sidebarOpen ? (
                          <>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-1.5">
                                <span className="font-medium truncate">{truncate(topic, 25)}</span>
                                <Badge variant="outline" className="h-4 px-1 text-[10px] rounded-full bg-primary/10 border-primary/20">
                                  {type === 'general' ? 'GEN' : type.slice(0, 2).toUpperCase()}
                                </Badge>
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
                              className="h-6 w-6 shrink-0 opacity-0 group-hover:opacity-100 hover:bg-destructive/20 hover:text-destructive rounded-lg transition-all"
                              onClick={(e) => deleteChat(e, c.id)}
                            >
                              <X className="h-3 w-3" />
                            </Button>
                          </>
                        ) : (
                          <div className="absolute -top-1 -right-1">
                            <Badge variant="outline" className="h-3 px-1 text-[8px] rounded-full bg-primary/10 border-primary/20">
                              {c.messages?.length || 0}
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

      {/* Main area */}
      <motion.div 
        variants={itemVariants}
        className="flex-1 min-w-0 min-h-0"
      >
        <Card className="h-full flex flex-col overflow-hidden border-0 shadow-xl rounded-2xl bg-gradient-to-b from-background to-muted/10">
          {/* Header */}
          <CardHeader className="shrink-0 bg-gradient-to-r from-primary/10 via-primary/5 to-transparent border-b pb-3 rounded-t-2xl">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <motion.div 
                  whileHover={{ rotate: 360, scale: 1.1 }}
                  transition={{ duration: 0.5 }}
                  className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary/20 to-primary/5 shadow-md"
                >
                  <Bot className="h-5 w-5 text-primary" />
                </motion.div>
                <div>
                  <CardTitle className="flex items-center gap-2">
                    Market Research Assistant
                    <Badge variant="outline" className="bg-gradient-to-r from-primary/20 to-primary/5 gap-1 rounded-full border-primary/30">
                      <Award className="h-3 w-3 text-primary" />
                      AI-Powered
                    </Badge>
                  </CardTitle>
                  <CardDescription>
                    Analyze markets, competitors, and opportunities with AI
                  </CardDescription>
                </div>
              </div>
              {selectedChat && (
                <Badge variant="secondary" className="gap-1 rounded-full bg-gradient-to-r from-muted to-muted/50">
                  <MessageSquare className="h-3 w-3" />
                  {currentMessages.length} messages
                </Badge>
              )}
            </div>
          </CardHeader>

          {/* Messages area */}
          <CardContent className="flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-primary/20 scrollbar-track-transparent bg-gradient-to-b from-background via-background to-muted/10">
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
                    <div className="relative">
                      <div className="absolute inset-0 bg-primary/20 blur-3xl rounded-full" />
                      <Bot className="h-20 w-20 text-primary/40 relative z-10" />
                    </div>
                  </motion.div>
                  <h3 className="text-xl font-semibold mb-2 bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">Ready to Research?</h3>
                  <p className="text-muted-foreground max-w-md mb-6">
                    Ask about market trends, competitor analysis, customer behavior, or growth opportunities
                  </p>
                  <div className="grid grid-cols-2 gap-3 max-w-lg">
                    {RESEARCH_TYPES.slice(0, 4).map((type) => (
                      <motion.div
                        key={type.value}
                        whileHover={{ scale: 1.05, y: -2 }}
                        className="flex items-center gap-2 p-3 rounded-xl bg-gradient-to-r border shadow-sm"
                      >
                        <div className={cn("rounded-lg p-1.5", type.bgColor)}>
                          <type.icon className={cn("h-4 w-4", type.color)} />
                        </div>
                        <span className="text-sm font-medium">{type.label}</span>
                      </motion.div>
                    ))}
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
                        exit="hidden"
                        className={cn(
                          "flex",
                          msg.role === 'user' ? 'justify-end' : 'justify-start'
                        )}
                      >
                        <div className={cn(
                          "max-w-[85%] rounded-2xl overflow-hidden shadow-md",
                          msg.role === 'user' 
                            ? 'bg-gradient-to-r from-primary to-primary/90 text-primary-foreground' 
                            : 'bg-gradient-to-r from-muted/80 to-muted/40 border shadow-sm'
                        )}>
                          {msg.role === 'user' ? (
                            <div className="px-4 py-3">
                              <div className="flex items-center gap-2 mb-1">
                                <User className="h-3 w-3 opacity-70" />
                                <span className="text-xs opacity-70">You</span>
                                {msg.researchType && (
                                  <Badge variant="secondary" className="text-[10px] h-4 rounded-full bg-primary-foreground/15 border-0">
                                    {RESEARCH_TYPES.find(t => t.value === msg.researchType)?.label}
                                  </Badge>
                                )}
                              </div>
                              <p className="text-sm font-medium">{msg.topic}</p>
                              {msg.context && Object.values(msg.context).some(Boolean) && (
                                <div className="mt-2 text-xs opacity-70 flex flex-wrap gap-2">
                                  {msg.context.competitors && (
                                    <span>🎯 {msg.context.competitors}</span>
                                  )}
                                  {msg.context.industry && (
                                    <span>🏭 {msg.context.industry}</span>
                                  )}
                                  {msg.context.geographicRegion && (
                                    <span>🌍 {msg.context.geographicRegion}</span>
                                  )}
                                </div>
                              )}
                            </div>
                          ) : (
                            <div className="px-5 py-4">
                              <div className="flex items-center gap-2 mb-3">
                                <div className="rounded-full bg-primary/20 p-1">
                                  <Bot className="h-3 w-3 text-primary" />
                                </div>
                                <span className="text-xs font-medium">Research Assistant</span>
                                {msg.response?.research_id != null && (
                                  <Badge variant="outline" className="text-[10px] h-4 rounded-full bg-primary/10 border-primary/20">
                                    ID: {String(msg.response.research_id).slice(0, 6)}
                                  </Badge>
                                )}
                              </div>
                              
                              {msg.response?.insights && (
                                <div
                                  className="prose prose-base max-w-none dark:prose-invert [&_h2]:text-primary [&_strong]:font-semibold"
                                  dangerouslySetInnerHTML={{ 
                                    __html: markdownToHtml(msg.response.insights) 
                                  }}
                                />
                              )}
                              
                              <div className="mt-4 space-y-3">
                                {msg.response?.opportunities?.length > 0 && (
                                  <motion.div 
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    className="rounded-xl border border-emerald-500/20 bg-gradient-to-br from-emerald-500/10 to-emerald-500/5 p-3 shadow-sm"
                                  >
                                    <h5 className="flex items-center gap-2 font-semibold text-sm mb-2">
                                      <Lightbulb className="h-4 w-4 text-emerald-500" />
                                      Opportunities
                                    </h5>
                                    <ul className="list-disc pl-5 space-y-1">
                                      {msg.response.opportunities.map((o, j) => (
                                        <li key={j} className="text-sm">{o}</li>
                                      ))}
                                    </ul>
                                  </motion.div>
                                )}
                                
                                {msg.response?.risks?.length > 0 && (
                                  <motion.div 
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ delay: 0.1 }}
                                    className="rounded-xl border border-rose-500/20 bg-gradient-to-br from-rose-500/10 to-rose-500/5 p-3 shadow-sm"
                                  >
                                    <h5 className="flex items-center gap-2 font-semibold text-sm mb-2">
                                      <AlertCircle className="h-4 w-4 text-rose-500" />
                                      Risks & Challenges
                                    </h5>
                                    <ul className="list-disc pl-5 space-y-1">
                                      {msg.response.risks.map((r, j) => (
                                        <li key={j} className="text-sm">{r}</li>
                                      ))}
                                    </ul>
                                  </motion.div>
                                )}
                                
                                {msg.response?.recommendations?.length > 0 && (
                                  <motion.div 
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ delay: 0.2 }}
                                    className="rounded-xl border border-blue-500/20 bg-gradient-to-br from-blue-500/10 to-blue-500/5 p-3 shadow-sm"
                                  >
                                    <h5 className="flex items-center gap-2 font-semibold text-sm mb-2">
                                      <CheckCircle2 className="h-4 w-4 text-blue-500" />
                                      Recommendations
                                    </h5>
                                    <ul className="list-disc pl-5 space-y-1">
                                      {msg.response.recommendations.map((r, j) => (
                                        <li key={j} className="text-sm">{r}</li>
                                      ))}
                                    </ul>
                                  </motion.div>
                                )}
                              </div>
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
                      <div className="bg-gradient-to-r from-muted to-muted/50 border rounded-2xl px-4 py-3 flex items-center gap-3 shadow-md">
                        <motion.div
                          animate={{ rotate: 360 }}
                          transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                        >
                          <Loader2 className="h-4 w-4 text-primary" />
                        </motion.div>
                        <span className="text-sm">Running market research...</span>
                      </div>
                    </motion.div>
                  )}
                  <div ref={messagesEndRef} />
                </div>
              )}
            </AnimatePresence>
          </CardContent>

          {/* Input form */}
          <div className="shrink-0 p-4 rounded-b-2xl">
            <form onSubmit={handleSubmit} className="space-y-3">
              {/* Main input row */}
              <div className="relative">
                <div
                  className="absolute inset-0 rounded-[28px] pointer-events-none"
                  style={{
                    background: 'linear-gradient(90deg, transparent 60%, rgba(10,37,64,0.38) 90%, rgba(14,39,71,0.22) 100%)',
                  }}
                />
                <div
                  className="relative z-[1] rounded-[28px] px-2.5 py-2.5 space-y-3"
                  style={{
                    background: '#0a0a0f',
                    border: '1.5px solid rgba(255,255,255,0.08)',
                    boxShadow: '0 4px 24px rgba(0,0,0,0.5)',
                  }}
                >
                  <div className="flex gap-2.5 items-center">
                    <Select value={researchType} onValueChange={setResearchType}>
                      <SelectTrigger
                        className="h-11 w-[145px] shrink-0 rounded-full text-sm font-medium focus:ring-0 focus:ring-offset-0 transition-all duration-200 px-4 gap-2 [&>svg]:opacity-70"
                        style={{
                          background: '#111118',
                          border: '1.5px solid rgba(139, 92, 246, 0.55)',
                          boxShadow: '0 0 16px rgba(139, 92, 246, 0.2), 0 0 4px rgba(139, 92, 246, 0.15)',
                          color: '#e2e2f0',
                        }}
                      >
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent
                        className="rounded-xl"
                        style={{
                          background: '#161630',
                          border: '1px solid rgba(139, 92, 246, 0.25)',
                          color: '#e2e2f0',
                        }}
                      >
                        {RESEARCH_TYPES.map((t) => {
                          const Icon = t.icon;
                          return (
                            <SelectItem key={t.value} value={t.value} className="rounded-lg focus:bg-violet-600/20 focus:text-white">
                              <div className="flex items-center gap-2">
                                <Icon className={cn("h-4 w-4", t.color)} />
                                <span>{t.label}</span>
                              </div>
                            </SelectItem>
                          );
                        })}
                      </SelectContent>
                    </Select>

                    <div
                      className="flex-1 min-w-0 rounded-full flex items-center overflow-hidden"
                      style={{
                        background: '#0e0e14',
                        boxShadow: 'inset 2px 0 8px -2px rgba(139,92,246,0.35)',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        borderLeftColor: 'rgba(139, 92, 246, 0.45)',
                      }}
                    >
                      <div className="flex-1 relative">
                        <Input
                          ref={inputRef}
                          placeholder="Ask about market trends, competitors, opportunities..."
                          value={topic}
                          onChange={(e) => setTopic(e.target.value)}
                          className="h-11 pr-10 border-0 bg-transparent rounded-full text-sm text-white placeholder:text-white/30 focus-visible:ring-0 focus-visible:ring-offset-0"
                        />
                        {topic && (
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="absolute right-1 top-1/2 -translate-y-1/2 h-8 w-8 rounded-lg text-white/70 hover:text-white"
                            onClick={() => setTopic('')}
                          >
                            <X className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </div>

                    <Button 
                      type="submit" 
                      disabled={loading || !topic.trim()}
                      className="h-11 w-11 shrink-0 rounded-full border-0 transition-all duration-200"
                      style={{
                        background: 'linear-gradient(135deg, #7c3aed 0%, #6d28d9 50%, #5b21b6 100%)',
                        boxShadow: '0 0 16px rgba(124, 58, 237, 0.35), 0 2px 8px rgba(0,0,0,0.3)',
                        color: '#ffffff',
                      }}
                    >
                      {loading ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Send className="h-4 w-4" />
                      )}
                    </Button>

                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      className="h-11 w-11 rounded-full border-0 text-white/80 hover:text-white"
                      style={{
                        background: '#111118',
                        border: '1.5px solid rgba(139, 92, 246, 0.30)',
                        boxShadow: '0 0 12px rgba(139, 92, 246, 0.15)',
                      }}
                      onClick={() => setShowContext(!showContext)}
                    >
                      <Filter className={cn("h-4 w-4", showContext ? "text-violet-300" : "text-white/80")} />
                    </Button>
                  </div>
 {/* Context inputs */}
                  <AnimatePresence>
                    {showContext && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        className="overflow-hidden"
                      >
                        <div
                          className="grid grid-cols-1 sm:grid-cols-3 gap-2 pt-2 p-2"
                          // style={{
                          //   background: 'linear-gradient(90deg, rgba(80,36,180,0.10) 0%, rgba(36,18,54,0.22) 55%, rgba(12,12,18,0.95) 100%)',
                          //   borderColor: 'rgba(139, 92, 246, 0.22)',
                          // }}
                        >
                          <div className="space-y-1">
                            <Label className="text-xs text-white/80">Competitors</Label>
                            <Input
                              placeholder="e.g., Competitor A, B"
                              value={competitors}
                              onChange={(e) => setCompetitors(e.target.value)}
                              className="h-8 text-sm rounded-lg border-0 bg-[#111118] text-white placeholder:text-white/40 focus-visible:ring-0 focus-visible:ring-offset-0"
                              style={{ border: '1px solid rgba(139, 92, 246, 0.22)' }}
                            />
                          </div>
                          <div className="space-y-1">
                            <Label className="text-xs text-white/80">Industry</Label>
                            <Input
                              placeholder="e.g., Technology"
                              value={industry}
                              onChange={(e) => setIndustry(e.target.value)}
                              className="h-8 text-sm rounded-lg border-0 bg-[#111118] text-white placeholder:text-white/40 focus-visible:ring-0 focus-visible:ring-offset-0"
                              style={{ border: '1px solid rgba(139, 92, 246, 0.22)' }}
                            />
                          </div>
                          <div className="space-y-1">
                            <Label className="text-xs text-white/80">Region</Label>
                            <Input
                              placeholder="e.g., North America"
                              value={geographicRegion}
                              onChange={(e) => setGeographicRegion(e.target.value)}
                              className="h-8 text-sm rounded-lg border-0 bg-[#111118] text-white placeholder:text-white/40 focus-visible:ring-0 focus-visible:ring-offset-0"
                              style={{ border: '1px solid rgba(139, 92, 246, 0.22)' }}
                            />
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                  {/* Quick prompts */}
                  {!selectedChatId && (
                    <motion.div 
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="pt-1"
                    >
                      <div className="w-full flex items-center gap-1 text-xs text-white/80 font-medium mb-2">
                        <Sparkles className="h-3 w-3" style={{ color: '#a78bfa' }} />
                        Try these research prompts
                      </div>
                      <div className="w-full flex flex-wrap gap-2">
                      {[
                        "AI marketing trends 2024",
                        "Competitor analysis Amazon",
                        "Customer behavior e-commerce",
                        "SaaS market opportunities"
                      ].map((prompt, i) => (
                        <motion.button
                          key={i}
                          type="button"
                          initial={{ scale: 0.95, opacity: 0 }}
                          animate={{ scale: 1, opacity: 1 }}
                          transition={{ delay: i * 0.05 }}
                          whileHover={{ scale: 1.05, y: -2 }}
                          whileTap={{ scale: 0.95 }}
                          className="text-xs h-7 rounded-xl px-3 text-left transition-all shadow-sm hover:shadow-md flex items-center text-white/90 border"
                          style={{
                            background: 'rgba(255,255,255,0.05)',
                            borderColor: 'rgba(255,255,255,0.10)',
                          }}
                          onClick={() => setTopic(prompt)}
                        >
                          {prompt}
                        </motion.button>
                      ))}
                      </div>
                    </motion.div>
                  )}

                 
                </div>
              </div>
            </form>
          </div>
        </Card>
      </motion.div>
    </motion.div>
  );
};

export default MarketResearch;