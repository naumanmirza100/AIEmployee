import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Send, MessageSquare, Plus, MessageCircle, Trash2 } from 'lucide-react';
import { recruitmentQA, listQAChats, createQAChat, updateQAChat, deleteQAChat } from '@/services/recruitmentAgentService';

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
        out.push('<div class="my-5 rounded-lg border border-border"><table class="w-full text-base">');
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

/** Suggested questions – recruitment data + stack/interview knowledge */
const SUGGESTED_QUESTIONS = [
  { group: 'Your Data (Jobs, Candidates, CVs)', options: [
    'Which candidates are best suited for the open role?',
    'How many jobs do I have? Which are active?',
    'Summarize the top candidates for this job.',
    'What are my qualification settings?',
  ]},
  { group: 'Tech Stack Interview Questions', options: [
    'What are basic and advanced React interview questions?',
    'Suggest MERN stack questions for a fresher candidate',
    'Python Django interview questions for senior developers',
    'Node.js questions to ask in technical screening',
    'What JavaScript/TypeScript questions should I ask?',
  ]},
  { group: 'General Interview & Recruitment', options: [
    'What questions to ask a Java Spring Boot candidate?',
    'How to assess a frontend developer in an interview?',
    'Best practices for technical phone screening',
    'What to ask a DevOps engineer in first round?',
    'Recruitment tips for hiring full-stack developers',
  ]},
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
  const [suggestedValue, setSuggestedValue] = useState('__none__');
  const [loading, setLoading] = useState(false);
  const [loadingChats, setLoadingChats] = useState(true);
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

  const deleteChat = async (e, chatId) => {
    e.stopPropagation();
    try {
      const res = await deleteQAChat(chatId);
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
                    <div className="font-medium truncate">{truncate(c.title || (c.messages?.[0]?.content) || c.question || 'Chat', 40)}</div>
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
            Ask about your jobs & candidates, or get tech stack interview questions (React, Node, MERN, etc.) and recruitment tips.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {/* Messages area - flows naturally like JobDescriptions, no inner scroll */}
          <div className="px-4 pb-4 space-y-4">
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
                        dangerouslySetInnerHTML={{ __html: markdownToHtml(msg.responseData?.answer ?? msg.content) }}
                      />
                      {msg.responseData?.insights?.length > 0 && (
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

          {/* Input form */}
          <form onSubmit={handleSubmit} className="shrink-0 border-t p-4 space-y-3 bg-muted/30">
            <div className="flex gap-2">
              <Textarea
                placeholder="Ask a recruitment question..."
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

export default AiInterviewQuestions;
