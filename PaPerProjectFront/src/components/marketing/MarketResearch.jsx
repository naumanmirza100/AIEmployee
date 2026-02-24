import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Sparkles, Search, Plus, FileSearch, Send, Trash2 } from 'lucide-react';
import marketingAgentService from '@/services/marketingAgentService';

const STORAGE_KEY = 'marketing_research_chats';

/** Research types matching backend. General = verify/question fits any type; others = must match selected type. */
const RESEARCH_TYPES = [
  { value: 'general', label: 'General' },
  { value: 'market_trend', label: 'Market Trend Analysis' },
  { value: 'competitor', label: 'Competitor Analysis' },
  { value: 'customer_behavior', label: 'Customer Behavior Analysis' },
  { value: 'opportunity', label: 'Opportunity Identification' },
  { value: 'threat', label: 'Risk & Threat Analysis' },
];

/** Simple markdown to HTML */
function markdownToHtml(markdown) {
  if (!markdown || typeof markdown !== 'string') return '';
  const escape = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const bold = (s) => s.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-foreground">$1</strong>');
  const lines = markdown.split('\n');
  const out = [];
  let inList = false;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const t = line.trim();
    if (/^---+$/.test(t)) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push('<hr class="my-4 border-border"/>');
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
      if (!inList) { out.push('<ul class="list-disc pl-4 my-2 space-y-1">'); inList = true; }
      const content = t.replace(/^[\s]*(?:•|-|\*|\d+\.)\s+/, '');
      out.push(`<li>${bold(escape(content))}</li>`);
      continue;
    }
    if (t === '' && inList) {
      out.push('</ul>');
      inList = false;
      continue;
    }
    if (t && !t.startsWith('<')) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<p class="my-2">${bold(escape(t)).replace(/\n/g, '<br/>')}</p>`);
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
  insights: 'You can research **market trends**, **competitors**, **customer behavior**, **opportunities**, or **risks**. Enter a topic (e.g. "cloud adoption in UK", "competitor analysis for Amazon") and choose a research type above. Ask for a specific topic when you want a full report.',
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
  insights: 'For details about **your campaigns**, **company data**, or **marketing analytics**, please use the **Q&A** tab. This Research agent is for market and competitive research (trends, competitors, opportunities). Use the Q&A agent to ask things like "How many campaigns do I have?" or "What is our ROI?"',
  opportunities: [],
  risks: [],
  recommendations: [],
};

/** Short response for definition/general questions – this agent does research only */
const NOT_RESEARCH_RESPONSE = {
  success: true,
  research_id: null,
  insights: 'This agent does **market and competitive research** only (trends, competitors, opportunities). For full forms, definitions, or general knowledge, use a search engine or rephrase as a research topic—e.g. "market for [product]" or "competitor analysis for [company]".',
  opportunities: [],
  risks: [],
  recommendations: [],
};

/** Short response for dismissive/off-topic input – prompt for a real research topic */
const OFF_TOPIC_RESPONSE = {
  success: true,
  research_id: null,
  insights: 'That doesn\'t look like a research topic. Ask about a **specific market**, **competitor**, or **trend**—e.g. "cloud adoption in UK", "competitor analysis for Amazon", or "customer behavior in e-commerce".',
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
  const messagesEndRef = useRef(null);

  useEffect(() => {
    setChats(loadChats());
  }, []);

  const selectedChat = chats.find((c) => c.id === selectedChatId);
  const currentMessages = selectedChat?.messages ?? [];

  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!topic.trim()) {
      toast({ title: 'Error', description: 'Please enter a research topic', variant: 'destructive' });
      return;
    }
    const trimmedTopic = topic.trim();
    const context = {};
    if (competitors.trim()) context.competitors = competitors.split(',').map((c) => c.trim()).filter(Boolean);
    if (industry.trim()) context.industry = industry.trim();
    if (geographicRegion.trim()) context.geographic_region = geographicRegion.trim();
    const userMsg = { role: 'user', topic: trimmedTopic, researchType, context: { competitors, industry, geographicRegion } };

    if (isGreetingOrSmallTalk(trimmedTopic)) {
      const friendlyResponse = {
        success: true,
        research_id: null,
        insights: "Hi! Enter a research topic to get started (e.g. market trends for cloud, competitor analysis for X). Choose a research type and add optional context above.",
        opportunities: [],
        risks: [],
        recommendations: [],
      };
      const assistantMsg = { role: 'assistant', response: friendlyResponse };
      const now = new Date().toISOString();
      if (selectedChatId) {
        const chat = chats.find((c) => c.id === selectedChatId);
        if (chat) {
          const updatedChat = { ...chat, messages: [...(chat.messages || []), userMsg, assistantMsg], timestamp: now };
          const updated = chats.map((c) => (c.id === selectedChatId ? updatedChat : c));
          setChats(updated);
          saveChats(updated);
        } else {
          createNewChat(userMsg, assistantMsg, now);
        }
      } else {
        createNewChat(userMsg, assistantMsg, now);
      }
      setTopic('');
      setCompetitors('');
      setIndustry('');
      setGeographicRegion('');
      setTimeout(scrollToBottom, 100);
      return;
    }

    if (isMetaQuestion(trimmedTopic)) {
      const assistantMsg = { role: 'assistant', response: META_RESPONSE };
      const now = new Date().toISOString();
      if (selectedChatId) {
        const chat = chats.find((c) => c.id === selectedChatId);
        if (chat) {
          const updatedChat = { ...chat, messages: [...(chat.messages || []), userMsg, assistantMsg], timestamp: now };
          const updated = chats.map((c) => (c.id === selectedChatId ? updatedChat : c));
          setChats(updated);
          saveChats(updated);
        } else {
          createNewChat(userMsg, assistantMsg, now);
        }
      } else {
        createNewChat(userMsg, assistantMsg, now);
      }
      setTopic('');
      setCompetitors('');
      setIndustry('');
      setGeographicRegion('');
      setTimeout(scrollToBottom, 100);
      return;
    }

    if (isCampaignOrCompanyQuestion(trimmedTopic)) {
      const assistantMsg = { role: 'assistant', response: CAMPAIGN_QA_RESPONSE };
      const now = new Date().toISOString();
      if (selectedChatId) {
        const chat = chats.find((c) => c.id === selectedChatId);
        if (chat) {
          const updatedChat = { ...chat, messages: [...(chat.messages || []), userMsg, assistantMsg], timestamp: now };
          const updated = chats.map((c) => (c.id === selectedChatId ? updatedChat : c));
          setChats(updated);
          saveChats(updated);
        } else {
          createNewChat(userMsg, assistantMsg, now);
        }
      } else {
        createNewChat(userMsg, assistantMsg, now);
      }
      setTopic('');
      setCompetitors('');
      setIndustry('');
      setGeographicRegion('');
      setTimeout(scrollToBottom, 100);
      return;
    }

    if (isDefinitionOrGeneralQuestion(trimmedTopic)) {
      const assistantMsg = { role: 'assistant', response: NOT_RESEARCH_RESPONSE };
      const now = new Date().toISOString();
      if (selectedChatId) {
        const chat = chats.find((c) => c.id === selectedChatId);
        if (chat) {
          const updatedChat = { ...chat, messages: [...(chat.messages || []), userMsg, assistantMsg], timestamp: now };
          const updated = chats.map((c) => (c.id === selectedChatId ? updatedChat : c));
          setChats(updated);
          saveChats(updated);
        } else {
          createNewChat(userMsg, assistantMsg, now);
        }
      } else {
        createNewChat(userMsg, assistantMsg, now);
      }
      setTopic('');
      setCompetitors('');
      setIndustry('');
      setGeographicRegion('');
      setTimeout(scrollToBottom, 100);
      return;
    }

    if (isDismissiveOrOffTopic(trimmedTopic)) {
      const assistantMsg = { role: 'assistant', response: OFF_TOPIC_RESPONSE };
      const now = new Date().toISOString();
      if (selectedChatId) {
        const chat = chats.find((c) => c.id === selectedChatId);
        if (chat) {
          const updatedChat = { ...chat, messages: [...(chat.messages || []), userMsg, assistantMsg], timestamp: now };
          const updated = chats.map((c) => (c.id === selectedChatId ? updatedChat : c));
          setChats(updated);
          saveChats(updated);
        } else {
          createNewChat(userMsg, assistantMsg, now);
        }
      } else {
        createNewChat(userMsg, assistantMsg, now);
      }
      setTopic('');
      setCompetitors('');
      setIndustry('');
      setGeographicRegion('');
      setTimeout(scrollToBottom, 100);
      return;
    }

    try {
      setLoading(true);
      const result = await marketingAgentService.marketResearch(researchType, trimmedTopic, context);

      if (result?.status === 'success' && result?.data) {
        const data = result.data;
        const assistantMsg = { role: 'assistant', response: data };
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
            setTopic('');
            setCompetitors('');
            setIndustry('');
            setGeographicRegion('');
            setTimeout(scrollToBottom, 100);
          } else {
            createNewChat(userMsg, assistantMsg, now);
          }
        } else {
          createNewChat(userMsg, assistantMsg, now);
        }
        toast({ title: 'Success', description: 'Research completed.' });
      } else {
        throw new Error(result?.message || result?.error || 'Failed to conduct research');
      }
    } catch (error) {
      toast({ title: 'Error', description: 'Something went wrong. Please try again.', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
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
    setTopic('');
    setCompetitors('');
    setIndustry('');
    setGeographicRegion('');
    setTimeout(scrollToBottom, 100);
  };

  const newChat = () => {
    setSelectedChatId(null);
  };

  const deleteChat = (e, chatId) => {
    e.stopPropagation();
    const updated = chats.filter((c) => c.id !== chatId);
    setChats(updated);
    saveChats(updated);
    if (selectedChatId === chatId) setSelectedChatId(null);
    toast({ title: 'Deleted', description: 'Research removed.' });
  };

  const truncate = (s, n = 45) => (s.length <= n ? s : s.slice(0, n) + '…');
  const formatDate = (iso) => {
    try {
      const d = new Date(iso);
      return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  return (
    <div className="h-full min-h-0 flex gap-4">
      {/* Sidebar - Previous research */}
      <div className="w-80 shrink-0 flex flex-col rounded-lg border bg-card overflow-hidden">
        <div className="p-4 border-b flex items-center justify-between">
          <span className="text-sm font-semibold">Previous research</span>
          <Button variant="ghost" size="icon" onClick={newChat} title="New research">
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {chats.length === 0 ? (
            <div className="p-6 text-center text-sm text-muted-foreground">No research yet. Conduct research to see history here.</div>
          ) : (
            <div className="p-3 space-y-2">
              {[...chats].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp)).map((c) => (
                <div
                  key={c.id}
                  className={`group flex items-start gap-1 w-full text-left p-4 rounded-lg text-sm transition-colors cursor-pointer ${selectedChatId === c.id ? 'bg-primary/10 border border-primary/20' : 'hover:bg-muted'}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelectedChatId(c.id)}
                  onKeyDown={(e) => e.key === 'Enter' && setSelectedChatId(c.id)}
                >
                  <div className="flex-1 min-w-0">
                    <div className="font-medium truncate">{truncate(c.messages?.find((m) => m.role === 'user')?.topic || 'Research', 40)}</div>
                    <div className="text-xs text-muted-foreground mt-0.5">{formatDate(c.timestamp)}</div>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 shrink-0 opacity-0 group-hover:opacity-100 hover:bg-destructive/10 hover:text-destructive"
                    onClick={(e) => deleteChat(e, c.id)}
                    title="Delete research"
                  >
                    <Trash2 className="h-3.5 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Main area */}
      <Card className="flex-1 flex flex-col min-w-0 min-h-0">
        <CardHeader className="shrink-0">
          <CardTitle className="flex items-center gap-2">
            <Search className="h-5 w-5" />
            Market & Competitive Research Agent
          </CardTitle>
          <CardDescription>
            Analyzes market trends, competitors, and customer behavior. Previous research is shown in the sidebar.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex-1 flex flex-col min-h-0 p-0">
          {/* Content area: selected chat or form */}
          <div className="flex-1 min-h-0 overflow-y-auto px-4 pb-4">
            {!selectedChatId && chats.length === 0 && (
              <div className="py-6">
                <form onSubmit={handleSubmit} className="space-y-4">
                  <div className="space-y-2">
                    <Label>Research Type</Label>
                    <Select value={researchType} onValueChange={setResearchType}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {RESEARCH_TYPES.map((t) => (
                          <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Research Topic *</Label>
                    <Textarea
                      placeholder="e.g., AI marketing tools market trends..."
                      value={topic}
                      onChange={(e) => setTopic(e.target.value)}
                      rows={4}
                      required
                      className="resize-none"
                    />
                  </div>
                  <div className="rounded-lg border bg-muted/30 p-4 space-y-4">
                    <h4 className="text-sm font-semibold flex items-center gap-2">
                      <Sparkles className="h-4 w-4" />
                      Additional Context (Optional)
                    </h4>
                    <div className="grid gap-4 sm:grid-cols-3">
                      <div className="space-y-2">
                        <Label>Competitors</Label>
                        <Input placeholder="e.g., Competitor A, B" value={competitors} onChange={(e) => setCompetitors(e.target.value)} />
                      </div>
                      <div className="space-y-2">
                        <Label>Industry</Label>
                        <Input placeholder="e.g., Technology" value={industry} onChange={(e) => setIndustry(e.target.value)} />
                      </div>
                      <div className="space-y-2">
                        <Label>Region</Label>
                        <Input placeholder="e.g., North America" value={geographicRegion} onChange={(e) => setGeographicRegion(e.target.value)} />
                      </div>
                    </div>
                  </div>
                  <Button type="submit" disabled={loading}>
                    {loading ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Researching...</> : <><Search className="h-4 w-4 mr-2" />Conduct Research</>}
                  </Button>
                </form>
              </div>
            )}

            {!selectedChatId && chats.length > 0 && (
              <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                <FileSearch className="h-12 w-12 mb-4 opacity-50" />
                <p className="font-medium">Select a previous research or start new</p>
                <p className="text-sm">Click an item in the sidebar or use the form below.</p>
              </div>
            )}

            {selectedChat && (
              <div className="space-y-4 pb-4">
                {currentMessages.map((msg, i) => (
                  msg.role === 'user' ? (
                    <div key={i} className="flex justify-end">
                      <div className="max-w-[85%] rounded-2xl px-4 py-3 bg-primary text-primary-foreground">
                        <p className="text-xs opacity-80">{RESEARCH_TYPES.find((t) => t.value === msg.researchType)?.label}</p>
                        <p className="text-sm font-medium mt-1">{msg.topic}</p>
                      </div>
                    </div>
                  ) : (
                    <div key={i} className="flex justify-start">
                      <div className="max-w-[95%] rounded-2xl px-4 py-3 bg-muted border">
                        <h4 className="font-semibold mb-2">Research Findings</h4>
                        {msg.response?.research_id && (
                          <p className="text-xs text-muted-foreground mb-2">Saved (ID: {msg.response.research_id})</p>
                        )}
                        {msg.response?.insights && (
                          <div
                            className="prose prose-sm max-w-none [&_h2]:text-primary"
                            dangerouslySetInnerHTML={{ __html: markdownToHtml(msg.response.insights) }}
                          />
                        )}
                        {msg.response?.opportunities?.length > 0 && (
                          <div className="mt-3">
                            <h5 className="font-medium mb-1">Opportunities</h5>
                            <ul className="list-disc pl-4 text-sm">{msg.response.opportunities.map((o, j) => <li key={j}>{o}</li>)}</ul>
                          </div>
                        )}
                        {msg.response?.risks?.length > 0 && (
                          <div className="mt-2">
                            <h5 className="font-medium mb-1">Risks</h5>
                            <ul className="list-disc pl-4 text-sm">{msg.response.risks.map((r, j) => <li key={j}>{r}</li>)}</ul>
                          </div>
                        )}
                        {msg.response?.recommendations?.length > 0 && (
                          <div className="mt-2">
                            <h5 className="font-medium mb-1">Recommendations</h5>
                            <ul className="list-disc pl-4 text-sm">{msg.response.recommendations.map((r, j) => <li key={j}>{r}</li>)}</ul>
                          </div>
                        )}
                      </div>
                    </div>
                  )
                ))}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          {/* Input form - always visible */}
          <form onSubmit={handleSubmit} className="shrink-0 border-t p-4 bg-muted/30">
            <div className="flex flex-col gap-3">

            <div className="flex gap-3 items-end">
  {/* Type */}
  <div className="flex-[1.5] space-y-1">
    <Select value={researchType} onValueChange={setResearchType}>
      <SelectTrigger className="h-10 w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {RESEARCH_TYPES.map((t) => (
          <SelectItem key={t.value} value={t.value}>
            {t.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  </div>

  {/* Topic - more space */}
  <div className="flex-[3] space-y-1">
    <Input
      placeholder="e.g., AI marketing tools market trends"
      value={topic}
      onChange={(e) => setTopic(e.target.value)}
      className="h-10 w-full"
    />
  </div>

  {/* Button - less space */}
  <div className="flex-[0.4]">
    <Button
      type="submit"
      disabled={loading}
      className="h-9 w-full p-0 mb-1"
    >
      <Send className="h-4 w-4" />
    </Button>
  </div>
</div>


              <div className='flex gap-3'>
                {/* Row 2 - Optional inputs */}
                <div className="flex-1 space-y-1">
                  <Input
                    placeholder="Competitors (opt)"
                    value={competitors}
                    onChange={(e) => setCompetitors(e.target.value)}
                    className="h-10"
                  />
                </div>

                <div className="flex-1 space-y-1">
                  <Input
                    placeholder="Industry (opt)"
                    value={industry}
                    onChange={(e) => setIndustry(e.target.value)}
                    className="h-10"
                  />
                </div>

                <div className="flex-1 space-y-1">
                  <Input
                    placeholder="Region (opt)"
                    value={geographicRegion}
                    onChange={(e) => setGeographicRegion(e.target.value)}
                    className="h-10"
                  />
                </div>
              </div>

            </div>
          </form>

        </CardContent>
      </Card>
    </div>
  );
};

export default MarketResearch;
