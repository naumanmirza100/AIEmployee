import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Sparkles, Search, Plus, FileSearch, Send } from 'lucide-react';
import marketingAgentService from '@/services/marketingAgentService';

const STORAGE_KEY = 'marketing_research_chats';

/** Research types matching backend */
const RESEARCH_TYPES = [
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
    localStorage.setItem(STORAGE_KEY, JSON.stringify(chats.slice(-50)));
  } catch { }
}

const MarketResearch = () => {
  const { toast } = useToast();
  const [chats, setChats] = useState([]);
  const [selectedChatId, setSelectedChatId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [researchType, setResearchType] = useState('market_trend');
  const [topic, setTopic] = useState('');
  const [competitors, setCompetitors] = useState('');
  const [industry, setIndustry] = useState('');
  const [geographicRegion, setGeographicRegion] = useState('');
  const messagesEndRef = useRef(null);

  useEffect(() => {
    setChats(loadChats());
  }, []);

  const selectedChat = chats.find((c) => c.id === selectedChatId);

  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!topic.trim()) {
      toast({ title: 'Error', description: 'Please enter a research topic', variant: 'destructive' });
      return;
    }
    try {
      setLoading(true);
      setSelectedChatId(null);
      const context = {};
      if (competitors.trim()) context.competitors = competitors.split(',').map((c) => c.trim()).filter(Boolean);
      if (industry.trim()) context.industry = industry.trim();
      if (geographicRegion.trim()) context.geographic_region = geographicRegion.trim();

      const result = await marketingAgentService.marketResearch(researchType, topic.trim(), context);

      if (result?.status === 'success' && result?.data) {
        const data = result.data;
        const newChat = {
          id: Date.now().toString(),
          researchType,
          topic: topic.trim(),
          context: { competitors, industry, geographicRegion },
          response: data,
          timestamp: new Date().toISOString(),
        };
        const updated = [newChat, ...chats];
        setChats(updated);
        saveChats(updated);
        setSelectedChatId(newChat.id);
        setTopic('');
        setCompetitors('');
        setIndustry('');
        setGeographicRegion('');
        toast({ title: 'Success', description: 'Research completed. Saved to sidebar.' });
        setTimeout(scrollToBottom, 100);
      } else {
        throw new Error(result?.message || result?.error || 'Failed to conduct research');
      }
    } catch (error) {
      toast({ title: 'Error', description: error?.message || 'Failed to conduct research', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const newChat = () => {
    setSelectedChatId(null);
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
    <div className="flex gap-4 h-[calc(100vh-12rem)] min-h-[500px]">
      {/* Sidebar - Previous research */}
      <div className="w-64 shrink-0 flex flex-col rounded-lg border bg-card overflow-hidden">
        <div className="p-3 border-b flex items-center justify-between">
          <span className="text-sm font-semibold">Previous research</span>
          <Button variant="ghost" size="icon" onClick={newChat} title="New research">
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {chats.length === 0 ? (
            <div className="p-4 text-center text-sm text-muted-foreground">No research yet. Conduct research to see history here.</div>
          ) : (
            <div className="p-2 space-y-1">
              {chats.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => setSelectedChatId(c.id)}
                  className={`w-full text-left p-3 rounded-lg text-sm transition-colors ${selectedChatId === c.id ? 'bg-primary/10 border border-primary/20' : 'hover:bg-muted'
                    }`}
                >
                  <div className="font-medium truncate">{truncate(c.topic, 40)}</div>
                  <div className="text-xs text-muted-foreground mt-0.5">{RESEARCH_TYPES.find((t) => t.value === c.researchType)?.label || c.researchType} • {formatDate(c.timestamp)}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Main area */}
      <Card className="flex-1 flex flex-col min-w-0">
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
          <div className="flex-1 overflow-y-auto px-4 pb-4">
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
                {/* Chat-style: user query bubble */}
                <div className="flex justify-end">
                  <div className="max-w-[85%] rounded-2xl px-4 py-3 bg-primary text-primary-foreground">
                    <p className="text-xs opacity-80">{RESEARCH_TYPES.find((t) => t.value === selectedChat.researchType)?.label}</p>
                    <p className="text-sm font-medium mt-1">{selectedChat.topic}</p>
                  </div>
                </div>
                {/* AI response bubble */}
                <div className="flex justify-start">
                  <div className="max-w-[95%] rounded-2xl px-4 py-3 bg-muted border">
                    <h4 className="font-semibold mb-2">Research Findings</h4>
                    {selectedChat.response.research_id && (
                      <p className="text-xs text-muted-foreground mb-2">Saved (ID: {selectedChat.response.research_id})</p>
                    )}
                    {selectedChat.response.insights && (
                      <div
                        className="prose prose-sm max-w-none [&_h2]:text-primary"
                        dangerouslySetInnerHTML={{ __html: markdownToHtml(selectedChat.response.insights) }}
                      />
                    )}
                    {selectedChat.response.opportunities?.length > 0 && (
                      <div className="mt-3">
                        <h5 className="font-medium mb-1">Opportunities</h5>
                        <ul className="list-disc pl-4 text-sm">{selectedChat.response.opportunities.map((o, i) => <li key={i}>{o}</li>)}</ul>
                      </div>
                    )}
                    {selectedChat.response.risks?.length > 0 && (
                      <div className="mt-2">
                        <h5 className="font-medium mb-1">Risks</h5>
                        <ul className="list-disc pl-4 text-sm">{selectedChat.response.risks.map((r, i) => <li key={i}>{r}</li>)}</ul>
                      </div>
                    )}
                    {selectedChat.response.recommendations?.length > 0 && (
                      <div className="mt-2">
                        <h5 className="font-medium mb-1">Recommendations</h5>
                        <ul className="list-disc pl-4 text-sm">{selectedChat.response.recommendations.map((r, i) => <li key={i}>{r}</li>)}</ul>
                      </div>
                    )}
                  </div>
                </div>
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
