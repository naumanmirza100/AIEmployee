import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Send, MessageSquare, Plus, MessageCircle, Trash2 } from 'lucide-react';
import marketingAgentService from '@/services/marketingAgentService';

const STORAGE_KEY = 'marketing_qa_chats';

/** Markdown to HTML for Q&A answers - readable paragraphs, headings, bullets, tables */
function markdownToHtml(markdown) {
  if (!markdown || typeof markdown !== 'string') return '';
  const escape = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const bold = (s) => s.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-foreground">$1</strong>');
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
        if (cells.length > 0 && cells.every(c => /^[-:\s]+$/.test(c))) { j++; continue; }
        tableRows.push(cells);
        j++;
      }
      i = j;
      if (tableRows.length > 0) {
        out.push('<div class="my-5 overflow-x-auto rounded-lg border border-border"><table class="w-full text-base">');
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
      if (inList) { out.push('</ul>'); inList = false; }
      out.push('<hr class="my-5 border-border"/>');
      i++; continue;
    }
    if (/^## /.test(t)) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<h2 class="text-xl font-bold mt-6 mb-3 text-violet-600 dark:text-violet-400 border-b border-violet-200 dark:border-violet-800 pb-2">${bold(escape(t.slice(3)))}</h2>`);
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
      out.push(`<h2 class="text-xl font-bold mt-6 mb-3 text-violet-600 dark:text-violet-400 border-b border-violet-200 dark:border-violet-800 pb-2">${bold(escape(t))}</h2>`);
      i++; continue;
    }
    if (/^[\s]*(?:•|-|\*|\d+\.)\s+/.test(t)) {
      if (!inList) { out.push('<ul class="list-disc pl-6 my-4 space-y-2">'); inList = true; }
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
  { group: 'Performance & Analytics', options: [
    'What campaigns are performing best?',
    'What is our overall ROI?',
    'Which marketing channels are most effective?',
    'What is our conversion rate?',
    'How are our campaigns performing this month?',
    'What is our customer acquisition cost (CAC)?',
  ]},
  { group: 'Analysis & Insights', options: [
    'Why are sales dropping?',
    'What should we focus on to improve performance?',
    'What are the key trends in our marketing data?',
    'Which campaigns need optimization?',
    'What are our top performing campaigns and why?',
  ]},
  { group: 'Goals & Targets', options: [
    'How many leads have we generated this month?',
    'What is our lead conversion rate?',
    'Are we on track to meet our campaign goals?',
  ]},
  { group: 'Strategy & Recommendations', options: [
    'What marketing strategies should we implement?',
    'What opportunities are we missing?',
    'How can we improve our campaign performance?',
    'What are the best practices for our industry?',
  ]},
];

function loadChats() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveChats(chats) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(chats.slice(-50))); // Keep last 50
  } catch {}
}

const MarketingQA = () => {
  const { toast } = useToast();
  const [chats, setChats] = useState([]);
  const [selectedChatId, setSelectedChatId] = useState(null);
  const [question, setQuestion] = useState('');
  const [suggestedValue, setSuggestedValue] = useState('__none__');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    setChats(loadChats());
  }, []);

  const selectedChat = chats.find((c) => c.id === selectedChatId);
  const currentMessages = selectedChat ? [{ role: 'user', content: selectedChat.question }, { role: 'assistant', content: selectedChat.response }] : [];

  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  const fillFromSuggestion = (value) => {
    const v = value || '__none__';
    setSuggestedValue(v);
    if (v !== '__none__') setQuestion(v);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!question.trim()) {
      toast({ title: 'Error', description: 'Please enter a question.', variant: 'destructive' });
      return;
    }
    const q = question.trim();
    try {
      setLoading(true);
      setSelectedChatId(null);
      const result = await marketingAgentService.marketingQA(q);
      if (result.status === 'success' && result.data) {
        const response = result.data;
        const answer = response.answer || 'No answer provided.';
        const insights = response.insights || [];
        const hasMultiple = insights.some((i) => i.value && String(i.value).includes(':')) || insights.length > 3;
        let responseText = answer;
        if (insights.length > 0) {
          responseText += '\n\n**Key Insights & Metrics**\n';
          insights.forEach((i) => {
            responseText += `• **${i.title || 'N/A'}**: ${i.value || 'N/A'}\n`;
          });
        }
        const newChat = {
          id: Date.now().toString(),
          question: q,
          response: responseText,
          responseData: response,
          timestamp: new Date().toISOString(),
        };
        const updated = [newChat, ...chats];
        setChats(updated);
        saveChats(updated);
        setSelectedChatId(newChat.id);
        setQuestion('');
        setSuggestedValue('__none__');
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
    setSuggestedValue('__none__');
  };

  const deleteChat = (e, chatId) => {
    e.stopPropagation();
    const updated = chats.filter((c) => c.id !== chatId);
    setChats(updated);
    saveChats(updated);
    if (selectedChatId === chatId) setSelectedChatId(null);
    toast({ title: 'Deleted', description: 'Conversation removed.' });
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
    <div className="flex gap-4 h-[calc(100vh-12rem)] min-h-[500px]">
      {/* Sidebar - Previous chats */}
      <div className="w-64 shrink-0 flex flex-col rounded-lg border bg-card overflow-hidden">
        <div className="p-3 border-b flex items-center justify-between">
          <span className="text-sm font-semibold">Previous conversations</span>
          <Button variant="ghost" size="icon" onClick={newChat} title="New chat">
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {chats.length === 0 ? (
            <div className="p-4 text-center text-sm text-muted-foreground">No conversations yet. Ask a question to start.</div>
          ) : (
            <div className="p-2 space-y-1">
              {chats.map((c) => (
                <div
                  key={c.id}
                  className={`group flex items-start gap-1 w-full text-left p-3 rounded-lg text-sm transition-colors cursor-pointer ${
                    selectedChatId === c.id ? 'bg-primary/10 border border-primary/20' : 'hover:bg-muted'
                  }`}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelectedChatId(c.id)}
                  onKeyDown={(e) => e.key === 'Enter' && setSelectedChatId(c.id)}
                >
                  <div className="flex-1 min-w-0">
                    <div className="font-medium truncate">{truncate(c.question, 40)}</div>
                    <div className="text-xs text-muted-foreground mt-0.5">{formatDate(c.timestamp)}</div>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 shrink-0 opacity-0 group-hover:opacity-100 hover:bg-destructive/10 hover:text-destructive"
                    onClick={(e) => deleteChat(e, c.id)}
                    title="Delete conversation"
                  >
                    <Trash2 className="h-3.5 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Main chat area */}
      <Card className="flex-1 flex flex-col min-w-0">
        <CardHeader className="shrink-0">
          <CardTitle className="flex items-center gap-2">
            <MessageSquare className="h-5 w-5" />
            Knowledge Q&A + Analytics Agent
          </CardTitle>
          <CardDescription>
            Ask marketing questions and get data-driven answers. Previous conversations are shown in the sidebar.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex-1 flex flex-col min-h-0 p-0">
          {/* Messages area */}
          <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-4">
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
                      <div
                        className="prose prose-base max-w-none [&_h2]:text-violet-600 [&_h2]:dark:text-violet-400 [&_strong]:font-semibold [&_p]:text-base [&_li]:text-base"
                        dangerouslySetInnerHTML={{ __html: markdownToHtml(selectedChat?.responseData?.answer || msg.content) }}
                      />
                      {selectedChat?.responseData?.insights?.length > 0 && (
                        <div className="mt-3 pt-3 border-t border-border/50">
                          <p className="text-xs font-semibold mb-2">Key Insights</p>
                          <div className="overflow-x-auto">
                            <table className="w-full text-xs">
                              <tbody>
                                {selectedChat.responseData.insights.map((insight, j) => (
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

          {/* Input form */}
          <form onSubmit={handleSubmit} className="shrink-0 border-t p-4 space-y-3 bg-muted/30">
            <div className="flex gap-2">
              <Textarea
                placeholder="Ask a marketing question..."
                value={question}
                onChange={(e) => { setQuestion(e.target.value); setSuggestedValue('__none__'); }}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(e); } }}
                rows={2}
                disabled={loading}
                className="min-h-[60px] resize-none"
              />
              <Button type="submit" disabled={loading} size="icon" className="h-[60px] w-12 shrink-0">
                {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
              </Button>
            </div>
            <div className="flex flex-wrap gap-2 items-center">
              <Select value={suggestedValue} onValueChange={fillFromSuggestion}>
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Suggested questions" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">Suggested questions</SelectItem>
                  {SUGGESTED_QUESTIONS.map((g) => (
                    <React.Fragment key={g.group}>
                      {g.options.map((opt) => (
                        <SelectItem key={opt} value={opt}>{truncate(opt, 45)}</SelectItem>
                      ))}
                    </React.Fragment>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
};

export default MarketingQA;
