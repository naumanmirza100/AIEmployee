import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import pmAgentService from '@/services/pmAgentService';
import {
  Loader2, Send, CalendarPlus, CheckCircle, XCircle, Clock,
  ArrowRightLeft, Trash2, Calendar, MessageCircle, RefreshCw,
  Plus, ChevronsLeft, ChevronsRight, Bot, Download
} from 'lucide-react';
import Skeleton from '@/components/common/Skeleton';

function markdownToHtml(markdown) {
  if (!markdown || typeof markdown !== 'string') return '';
  const escape = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const bold = (s) => s.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-violet-300">$1</strong>');
  const italic = (s) => s.replace(/\*(.+?)\*/g, '<em class="text-gray-400">$1</em>');
  const lines = markdown.split('\n');
  const out = [];
  for (const line of lines) {
    const t = line.trim();
    if (!t) { out.push('<br/>'); continue; }
    if (t.startsWith('# ')) { out.push(`<h2 class="text-lg font-bold text-violet-300 mt-3 mb-1">${bold(escape(t.slice(2)))}</h2>`); continue; }
    if (t.startsWith('## ')) { out.push(`<h3 class="text-base font-semibold text-violet-300 mt-2 mb-1">${bold(escape(t.slice(3)))}</h3>`); continue; }
    if (/^[-*]\s/.test(t)) { out.push(`<div class="flex items-start gap-2 ml-2"><span class="text-violet-400 mt-0.5">•</span><span class="text-gray-200">${italic(bold(escape(t.replace(/^[-*]\s+/, ''))))}</span></div>`); continue; }
    out.push(`<p class="text-gray-300 my-0.5">${italic(bold(escape(t)))}</p>`);
  }
  return out.join('\n');
}

const STATUS_CONFIG = {
  pending: { color: 'text-yellow-400', bg: 'bg-yellow-500/20', icon: Clock, label: 'Pending' },
  accepted: { color: 'text-green-400', bg: 'bg-green-500/20', icon: CheckCircle, label: 'Accepted' },
  rejected: { color: 'text-red-400', bg: 'bg-red-500/20', icon: XCircle, label: 'Rejected' },
  counter_proposed: { color: 'text-blue-400', bg: 'bg-blue-500/20', icon: ArrowRightLeft, label: 'Counter Proposed' },
  withdrawn: { color: 'text-gray-400', bg: 'bg-gray-500/20', icon: Trash2, label: 'Withdrawn' },
};

export default function MeetingScheduler() {
  const { toast } = useToast();
  const messagesEndRef = useRef(null);

  // Chat state
  const [chats, setChats] = useState([]);
  const [selectedChatId, setSelectedChatId] = useState(null);
  const [loadingChats, setLoadingChats] = useState(true);
  const [showChatHistory, setShowChatHistory] = useState(true);
  const [showSidebarSearch, setShowSidebarSearch] = useState(false);
  const [sidebarSearch, setSidebarSearch] = useState('');

  // Input state
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  // Meetings tab state
  const [activeTab, setActiveTab] = useState('chat');
  const [meetings, setMeetings] = useState([]);
  const [meetingsLoading, setMeetingsLoading] = useState(false);
  const [respondingTo, setRespondingTo] = useState(null);
  const [rejectReason, setRejectReason] = useState('');
  const [counterDate, setCounterDate] = useState('');
  const [counterTime, setCounterTime] = useState('');
  const [respondLoading, setRespondLoading] = useState(false);

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

  // Auto-hide sidebar on mobile
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)');
    if (mq.matches) setShowChatHistory(false);
    const handler = (e) => { if (e.matches) setShowChatHistory(false); };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  const loadChats = async () => {
    try {
      setLoadingChats(true);
      const res = await pmAgentService.listMeetingSchedulerChats();
      // companyApi returns raw JSON: { status, data: [...] } or just the data array
      const chatList = res?.data || (Array.isArray(res) ? res : []);
      setChats((Array.isArray(chatList) ? chatList : []).map(normalizeChat));
    } catch {
      setChats([]);
    } finally {
      setLoadingChats(false);
    }
  };

  useEffect(() => { loadChats(); }, []);

  const selectedChat = chats.find((c) => c.id === selectedChatId);
  const currentMessages = selectedChat?.messages ?? [];
  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  const addMessagePairToChat = async (userMsg, assistantMsg, titleSnippet) => {
    const title = titleSnippet.slice(0, 40);
    // companyApi uses fetch and returns raw JSON — response.data gives the inner object directly
    // So the result is { id, title, messages, ... } NOT { status, data: { ... } }
    const extractChat = (res) => {
      // Handle both wrapped { status, data: {...} } and unwrapped { id, title, ... } formats
      if (res?.data?.id) return normalizeChat(res.data);
      if (res?.id) return normalizeChat(res);
      return null;
    };

    if (selectedChatId) {
      const existing = chats.find((c) => c.id === selectedChatId);
      if (existing) {
        const updRes = await pmAgentService.updateMeetingSchedulerChat(selectedChatId, {
          messages: [userMsg, assistantMsg],
          title: existing.title || title,
        });
        const updated = extractChat(updRes);
        if (updated) {
          setChats((prev) => [updated, ...prev.filter((c) => c.id !== selectedChatId)]);
        }
      } else {
        const createRes = await pmAgentService.createMeetingSchedulerChat({ title, messages: [userMsg, assistantMsg] });
        const newChat = extractChat(createRes);
        if (newChat) {
          setChats((prev) => [newChat, ...prev]);
          setSelectedChatId(newChat.id);
        }
      }
    } else {
      const createRes = await pmAgentService.createMeetingSchedulerChat({ title, messages: [userMsg, assistantMsg] });
      const newChat = extractChat(createRes);
      if (newChat) {
        setChats((prev) => [newChat, ...prev]);
        setSelectedChatId(newChat.id);
      }
    }
    setTimeout(scrollToBottom, 100);
  };

  const handleSend = async () => {
    const msg = input.trim();
    if (!msg || loading) return;
    setInput('');
    setLoading(true);

    // Optimistic: show user message immediately
    const tempUserMsg = { role: 'user', content: msg };
    if (selectedChat) {
      setChats((prev) => prev.map((c) =>
        c.id === selectedChatId ? { ...c, messages: [...c.messages, tempUserMsg] } : c
      ));
    }
    setTimeout(scrollToBottom, 50);

    try {
      const res = await pmAgentService.meetingSchedule(msg);
      const data = res?.data?.data || res?.data || {};
      const response = data.response || data.message || 'Something went wrong. Please try again.';

      const userMsg = { role: 'user', content: msg };
      const assistantMsg = {
        role: 'assistant',
        content: response,
        responseData: { meeting: data.meeting, action: data.action },
      };

      // Remove optimistic message before saving to avoid duplicates
      if (selectedChat) {
        setChats((prev) => prev.map((c) =>
          c.id === selectedChatId ? { ...c, messages: c.messages.filter((m) => m !== tempUserMsg) } : c
        ));
      }

      await addMessagePairToChat(userMsg, assistantMsg, msg);

      if (data.action === 'scheduled' && data.meeting) {
        fetchMeetings();
      }
    } catch (err) {
      console.error('Meeting schedule error:', err);
      if (selectedChat) {
        setChats((prev) => prev.map((c) =>
          c.id === selectedChatId ? { ...c, messages: c.messages.filter((m) => m !== tempUserMsg) } : c
        ));
      }
      const userMsg = { role: 'user', content: msg };
      const assistantMsg = { role: 'assistant', content: 'Sorry, something went wrong. Please try again.' };
      await addMessagePairToChat(userMsg, assistantMsg, msg);
    } finally {
      setLoading(false);
    }
  };

  const downloadIcs = (meeting) => {
    const start = new Date(meeting.proposed_time);
    const end = new Date(start.getTime() + (meeting.duration_minutes || 30) * 60000);
    const fmt = (d) => d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
    const agenda = (meeting.agenda || []).map(a => `- ${a.item}`).join('\\n');
    const desc = (meeting.description || '') + (agenda ? '\\n\\nAgenda:\\n' + agenda : '');
    const participants = (meeting.participants || []).map(p =>
      p.email ? `ATTENDEE;CN=${p.name}:mailto:${p.email}` : ''
    ).filter(Boolean).join('\r\n');

    const ics = [
      'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//AIEmployee//Meeting//EN', 'METHOD:REQUEST',
      'BEGIN:VEVENT',
      `UID:meeting-${meeting.id}@aiemployee.app`,
      `DTSTAMP:${fmt(new Date())}`,
      `DTSTART:${fmt(start)}`,
      `DTEND:${fmt(end)}`,
      `SUMMARY:${meeting.title}`,
      `DESCRIPTION:${desc}`,
      participants,
      'BEGIN:VALARM', 'TRIGGER:-PT15M', 'ACTION:DISPLAY', `DESCRIPTION:Reminder: ${meeting.title}`, 'END:VALARM',
      'END:VEVENT', 'END:VCALENDAR',
    ].filter(Boolean).join('\r\n');

    const blob = new Blob([ics], { type: 'text/calendar;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${meeting.title.replace(/[^a-zA-Z0-9 ]/g, '').trim()}.ics`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Meeting stats
  const meetingStats = {
    pending: meetings.filter(m => m.status === 'pending').length,
    accepted: meetings.filter(m => m.status === 'accepted').length,
    counter: meetings.filter(m => m.status === 'counter_proposed' || m.status === 'partially_accepted').length,
    total: meetings.length,
  };
  const nextMeeting = meetings
    .filter(m => m.status === 'accepted' && new Date(m.proposed_time) > new Date())
    .sort((a, b) => new Date(a.proposed_time) - new Date(b.proposed_time))[0];

  const handleKeyDown = (e) => {
    if ((e.key === 'Enter' && !e.shiftKey) || (e.key === 'Enter' && (e.ctrlKey || e.metaKey))) {
      e.preventDefault();
      handleSend();
    }
    if (e.key === 'Escape') {
      setRespondingTo(null);
    }
  };

  const newChat = () => {
    setSelectedChatId(null);
    setInput('');
  };

  const deleteChat = async (e, chatId) => {
    e.stopPropagation();
    // Remove from UI immediately
    setChats((prev) => prev.filter((c) => c.id !== chatId));
    if (selectedChatId === chatId) setSelectedChatId(null);
    try {
      await pmAgentService.deleteMeetingSchedulerChat(chatId);
    } catch {
      // Already removed from UI — if API fails (e.g. already deleted), that's fine
    }
  };

  const fetchMeetings = async () => {
    setMeetingsLoading(true);
    try {
      const res = await pmAgentService.meetingList();
      const data = res?.data?.data || res?.data || {};
      setMeetings(data.meetings || []);
    } catch { setMeetings([]); }
    finally { setMeetingsLoading(false); }
  };

  useEffect(() => { if (activeTab === 'meetings') fetchMeetings(); }, [activeTab]);

  const handleRespond = async (meetingId, action) => {
    setRespondLoading(true);
    try {
      let counterTimeISO = null;
      if (action === 'counter_proposed' && counterDate && counterTime) {
        counterTimeISO = new Date(`${counterDate}T${counterTime}`).toISOString();
      }
      await pmAgentService.meetingRespond(meetingId, action, rejectReason, counterTimeISO);
      toast({
        title: action === 'accepted' ? 'Meeting Accepted' : action === 'rejected' ? 'Meeting Rejected' : action === 'counter_proposed' ? 'New Time Proposed' : 'Meeting Withdrawn',
        description: `Meeting has been ${action.replace('_', ' ')}.`,
      });
      setRespondingTo(null);
      setRejectReason('');
      setCounterDate('');
      setCounterTime('');
      fetchMeetings();
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to respond', variant: 'destructive' });
    } finally {
      setRespondLoading(false);
    }
  };

  const truncate = (s, n = 50) => (s.length <= n ? s : s.slice(0, n) + '…');
  const formatDate = (iso) => {
    try { return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); }
    catch { return ''; }
  };

  return (
    <div
      className="w-full rounded-2xl border border-white/[0.06] p-0 overflow-hidden"
      style={{ background: 'linear-gradient(90deg, #020308 0%, #020308 55%, rgba(10,37,64,0.68) 85%, rgba(14,39,71,0.52) 100%)' }}
    >
      <div className="flex w-full max-w-full relative max-h-[calc(100vh-40px)]">
        {/* ========== SIDEBAR ========== */}
        <div
          className={`shrink-0 rounded-xl border border-white/15 shadow-[0_2px_24px_0_rgba(80,36,180,0.18)] backdrop-blur-lg overflow-hidden transition-all duration-300 ease-in-out ${
            showChatHistory ? 'w-64 opacity-100 mr-4' : 'w-0 opacity-0 border-0 mr-0'
          }`}
          style={{
            minWidth: showChatHistory ? '16rem' : '0',
            background: 'linear-gradient(90deg, rgba(139,92,246,0.13) 0%, rgba(36,18,54,0.18) 18%, #0a0a0f 55%, #0a0a0f 100%)',
            borderRight: '1.5px solid rgba(255,255,255,0.10)',
            boxShadow: '0 2px 24px 0 rgba(80, 36, 180, 0.18), 0 0 0 1.5px rgba(120, 80, 255, 0.10) inset',
            borderTopLeftRadius: 16, borderBottomLeftRadius: 16,
            backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)',
            overflow: 'hidden',
          }}
        >
          <div className="w-64 h-full flex flex-col">
            <div className="px-3 pt-3 pb-2 border-b border-white/15 flex flex-col gap-2 shrink-0"
              style={{ background: 'linear-gradient(180deg, rgba(60, 30, 90, 0.22) 0%, rgba(36, 18, 54, 0.85) 100%)', borderTopLeftRadius: 16 }}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-base font-semibold text-white/90 tracking-wide">Meetings</span>
                <button onClick={() => setShowChatHistory(false)} title="Close sidebar"
                  className="h-8 w-8 flex items-center justify-center rounded-full border border-white/20 hover:border-violet-400/60 bg-black/30 hover:bg-violet-700/20 transition-all duration-150">
                  <ChevronsLeft className="h-4 w-4 text-white/80" />
                </button>
              </div>
              {showSidebarSearch ? (
                <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg w-full"
                  style={{ border: '1.5px solid rgba(139,92,246,0.22)', background: 'linear-gradient(90deg, rgba(80,36,180,0.10) 0%, rgba(36,18,54,0.18) 100%)' }}>
                  <input autoFocus value={sidebarSearch} onChange={(e) => setSidebarSearch(e.target.value)}
                    placeholder="Search..." className="flex-1 bg-transparent outline-none border-0 text-white/90 text-sm px-2 py-1.5 placeholder-white/40" />
                  <button onClick={() => { setSidebarSearch(''); setShowSidebarSearch(false); }}
                    className="h-7 w-7 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60 bg-black/20 hover:bg-violet-700/20 transition-all duration-150">
                    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-white/70">
                      <line x1="4" y1="4" x2="12" y2="12" /><line x1="12" y1="4" x2="4" y2="12" />
                    </svg>
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg w-full"
                  style={{ border: '1.5px solid rgba(139,92,246,0.22)', background: 'linear-gradient(90deg, rgba(80,36,180,0.10) 0%, rgba(36,18,54,0.18) 100%)' }}>
                  <span className="text-sm font-medium text-white/80 flex-1">Conversations</span>
                  <button title="Search" onClick={() => setShowSidebarSearch(true)}
                    className="h-7 w-7 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60 bg-black/20 hover:bg-violet-700/20 transition-all duration-150">
                    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-white/70">
                      <circle cx="7" cy="7" r="5" /><line x1="15" y1="15" x2="11" y2="11" />
                    </svg>
                  </button>
                  <button onClick={newChat} title="New chat"
                    className="h-7 w-7 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60 bg-black/20 hover:bg-violet-700/20 transition-all duration-150">
                    <Plus className="h-4 w-4 text-white/80" />
                  </button>
                </div>
              )}
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto custom-sidebar-scroll">
              {loadingChats ? (
                <Skeleton.ChatList count={4} />
              ) : chats.length === 0 ? (
                <div className="p-4 text-center text-sm text-muted-foreground">No conversations yet. Send a request to start.</div>
              ) : (
                <div className="p-2 space-y-1" style={{ background: 'linear-gradient(180deg, rgba(36, 18, 54, 0.10) 0%, rgba(24, 18, 43, 0.18) 100%)', borderRadius: 12 }}>
                  {(() => {
                    const term = sidebarSearch.trim().toLowerCase();
                    const filtered = term
                      ? chats.filter((c) => (c.title || '').toLowerCase().includes(term) || (c.messages || []).some((m) => (m.content || '').toLowerCase().includes(term)))
                      : chats;
                    if (term && !filtered.length) return <div className="p-4 text-center text-sm text-muted-foreground">No matching conversations.</div>;
                    return filtered.map((c) => (
                      <div key={c.id}
                        className={`flex items-center gap-1 rounded-lg border text-sm transition-all duration-200 ${
                          selectedChatId === c.id
                            ? 'border-violet-500/60 bg-gradient-to-r from-violet-900/40 to-violet-700/20 shadow-[0_0_12px_rgba(139,92,246,0.18)]'
                            : 'border-white/10 bg-white/2 hover:bg-white/5 hover:border-violet-400/20'
                        }`}
                        style={{ boxShadow: selectedChatId === c.id ? '0 0 12px 0 rgba(139,92,246,0.18)' : 'none', borderWidth: 1.5 }}>
                        <button type="button" onClick={() => setSelectedChatId(c.id)} className="flex-1 min-w-0 text-left p-3 rounded-lg">
                          <div className={`font-medium truncate ${selectedChatId === c.id ? 'text-violet-300' : ''}`}>
                            {truncate(c.title || c.messages?.[0]?.content || 'Chat', 40)}
                          </div>
                          <div className={`text-xs mt-0.5 ${selectedChatId === c.id ? 'text-violet-400/70' : 'text-muted-foreground'}`}>
                            {formatDate(c.updatedAt || c.timestamp)}
                          </div>
                        </button>
                        <Button type="button" variant="ghost" size="icon"
                          className="h-8 w-8 shrink-0 opacity-60 hover:opacity-100 hover:bg-destructive/10 hover:text-destructive"
                          onClick={(e) => deleteChat(e, c.id)} title="Delete chat">
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    ));
                  })()}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ========== MAIN AREA ========== */}
        <Card className="flex-1 min-w-0 flex flex-col max-h-[calc(100vh-40px)] border-0 shadow-none" style={{ background: 'transparent' }}>
          <CardHeader className="shrink-0 flex flex-row items-start justify-between gap-3 border-b border-white/[0.07] px-0 py-4" style={{ background: 'transparent' }}>
            <div className="flex items-center gap-3 min-w-0 w-full">
              <div style={{ width: '7px', height: '48px', borderRadius: '8px', background: 'linear-gradient(to bottom, #a259ff 0%, #6a1b9a 60%, #18122B 100%)', marginLeft: '24px', marginRight: '18px', boxShadow: '0 0 8px 2px #a259ff44' }} />
              <div className="h-10 w-10 rounded-lg flex items-center justify-center shrink-0" style={{ background: 'rgba(124, 58, 237, 0.15)' }}>
                <CalendarPlus className="h-5 w-5" style={{ color: '#a78bfa' }} />
              </div>
              <div className="min-w-0 flex-1">
                <CardTitle className="flex items-center gap-2 truncate text-white text-lg">
                  Meeting Scheduler
                  <span className="text-[10px] rounded-full px-2.5 py-0.5 font-medium" style={{ background: 'rgba(124, 58, 237, 0.15)', color: '#a78bfa' }}>AI-Powered</span>
                </CardTitle>
                <CardDescription className="text-white/50 text-sm mt-0.5">
                  Schedule meetings with your team using natural language. Try: "Schedule a meeting with Sarah tomorrow at 2 PM"
                </CardDescription>
              </div>
              {/* Tab toggle */}
              <div className="flex items-center gap-1 bg-muted/30 rounded-lg p-1 mr-2">
                <button onClick={() => setActiveTab('chat')}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${activeTab === 'chat' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>
                  <MessageCircle className="h-3.5 w-3.5 inline mr-1" /> Chat
                </button>
                <button onClick={() => setActiveTab('meetings')}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${activeTab === 'meetings' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>
                  <Calendar className="h-3.5 w-3.5 inline mr-1" /> Meetings
                </button>
              </div>
            </div>
            <Button variant={showChatHistory ? 'ghost' : 'outline'} size="sm" onClick={() => setShowChatHistory((v) => !v)}
              title={showChatHistory ? 'Hide chat history' : 'Show chat history'}
              className={`gap-1.5 transition-all duration-200 ${!showChatHistory ? 'bg-primary/5 hover:bg-primary/10 border-primary/20 text-primary' : 'hover:bg-muted'}`}
              style={{ marginRight: '24px' }}>
              {showChatHistory ? <><ChevronsLeft className="h-4 w-4" /><span className="text-xs hidden sm:inline">Hide</span></> : <><ChevronsRight className="h-4 w-4" /><span className="text-xs hidden sm:inline">History</span></>}
            </Button>
          </CardHeader>

          <CardContent className="p-0 flex flex-col flex-1 min-h-0">
            {/* ========== CHAT TAB ========== */}
            {activeTab === 'chat' && (
              <>
                <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-4 py-4 space-y-4">
                  {!selectedChatId && !loading && chats.length === 0 && (
                    <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground max-w-md mx-auto">
                      <CalendarPlus className="h-12 w-12 mb-4 opacity-50" />
                      <p className="font-medium text-white/80 text-lg mb-3">Schedule your first meeting</p>
                      <div className="space-y-2 text-left w-full">
                        <p className="text-xs text-white/30 uppercase tracking-wide mb-1">Quick Start Examples:</p>
                        {[
                          'Schedule a meeting with developer1 tomorrow at 2 PM',
                          'Set up a weekly standup with the team at 9 AM',
                          'Book a 1-on-1 with Sarah on Friday at 3 PM to discuss the API',
                          'Show my upcoming meetings',
                          'Reschedule my meeting with hamza to Thursday',
                        ].map((example, i) => (
                          <button key={i} onClick={() => { setInput(example); }}
                            className="w-full text-left text-xs px-3 py-2 rounded-lg bg-white/[0.03] hover:bg-white/[0.06] text-white/50 hover:text-white/80 transition-colors border border-white/5 hover:border-violet-500/20">
                            "{example}"
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  {!selectedChatId && !loading && chats.length > 0 && (
                    <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                      <MessageCircle className="h-12 w-12 mb-4 opacity-50" />
                      <p className="font-medium">Select a conversation or start a new one</p>
                      <p className="text-sm">Click a chat in the sidebar or type below.</p>
                    </div>
                  )}
                  {currentMessages.map((msg, i) => (
                    <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                      <div className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                        msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted border'
                      }`}>
                        {msg.role === 'user' ? (
                          <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                        ) : (
                          <div>
                            <div className="text-sm leading-relaxed" dangerouslySetInnerHTML={{ __html: markdownToHtml(msg.content) }} />
                            {msg.responseData?.meeting && (
                              <div className="mt-3 p-3 rounded-lg bg-green-500/10 border border-green-500/20">
                                <div className="flex items-center gap-2 text-green-400 text-xs font-medium mb-1">
                                  <CheckCircle className="h-3.5 w-3.5" /> Meeting Created
                                </div>
                                <div className="text-xs text-gray-300 space-y-0.5">
                                  <div><strong>With:</strong> {msg.responseData.meeting.invitee_name}</div>
                                  <div><strong>When:</strong> {new Date(msg.responseData.meeting.proposed_time).toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })}</div>
                                  <div><strong>Duration:</strong> {msg.responseData.meeting.duration_minutes} min</div>
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                  {loading && (
                    <div className="flex justify-start">
                      <div className="bg-muted border rounded-2xl px-4 py-3 flex items-center gap-2">
                        <Loader2 className="h-4 w-4 animate-spin text-violet-400" />
                        <span className="text-sm text-muted-foreground">Scheduling...</span>
                      </div>
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                </div>

                {/* Input area */}
                <div className="shrink-0 border-t border-white/[0.07] p-4">
                  <div className="flex gap-2">
                    <textarea
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={handleKeyDown}
                      placeholder="Schedule a meeting with Sarah tomorrow at 2 PM..."
                      className="flex-1 min-h-[44px] max-h-[120px] resize-none rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-white placeholder:text-white/30 focus:outline-none focus:ring-1 focus:ring-violet-500/50 focus:border-violet-500/30"
                      rows={1}
                    />
                    <Button onClick={handleSend} disabled={!input.trim() || loading} className="bg-violet-600 hover:bg-violet-700 h-[44px] px-4" size="icon">
                      <Send className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </>
            )}

            {/* ========== MEETINGS TAB ========== */}
            {activeTab === 'meetings' && (
              <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4 space-y-4">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <h3 className="text-sm font-medium text-gray-300">Your Meetings</h3>
                  <Button onClick={fetchMeetings} disabled={meetingsLoading} variant="outline" size="sm" className="border-gray-600 text-gray-300">
                    <RefreshCw className={`w-3.5 h-3.5 mr-1 ${meetingsLoading ? 'animate-spin' : ''}`} /> Refresh
                  </Button>
                </div>

                {/* Stats summary */}
                {meetingStats.total > 0 && (
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className="text-[11px] px-2 py-0.5 rounded-full bg-yellow-500/15 text-yellow-400">{meetingStats.pending} pending</span>
                    <span className="text-[11px] px-2 py-0.5 rounded-full bg-green-500/15 text-green-400">{meetingStats.accepted} accepted</span>
                    {meetingStats.counter > 0 && <span className="text-[11px] px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-400">{meetingStats.counter} counter-proposed</span>}
                    {nextMeeting && (
                      <span className="text-[11px] text-violet-400 flex items-center gap-1">
                        <Clock className="h-3 w-3" /> Next: {nextMeeting.title} — {new Date(nextMeeting.proposed_time).toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}
                      </span>
                    )}
                  </div>
                )}

                {meetingsLoading && <Skeleton.MeetingList count={3} />}

                {!meetingsLoading && meetings.length === 0 && (
                  <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                    <Calendar className="h-10 w-10 mb-3 opacity-50" />
                    <p className="text-sm">No meetings yet. Use the chat to schedule one.</p>
                  </div>
                )}

                {meetings.map((m) => {
                  const sc = STATUS_CONFIG[m.status] || STATUS_CONFIG.pending;
                  const StatusIcon = sc.icon;
                  return (
                    <div key={m.id} className="rounded-xl border border-white/10 bg-white/[0.02] p-4 space-y-3">
                      <div className="flex items-start justify-between">
                        <div>
                          <h4 className="text-sm font-medium text-white">{m.title}</h4>
                          <p className="text-xs text-gray-400 mt-0.5">With: {m.invitee_name}</p>
                        </div>
                        <span className={`flex items-center gap-1 text-xs px-2 py-1 rounded-full ${sc.bg} ${sc.color}`}>
                          <StatusIcon className="h-3 w-3" /> {sc.label}
                        </span>
                      </div>
                      <div className="flex items-center gap-4 text-xs text-gray-400 flex-wrap">
                        <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {new Date(m.proposed_time).toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</span>
                        <span>{m.duration_minutes} min</span>
                        {m.is_recurring && (
                          <span className="flex items-center gap-1 text-violet-400">
                            <RefreshCw className="h-3 w-3" /> {m.recurrence?.replace('_', ' ')}
                            {m.occurrences_count > 0 && ` (${m.occurrences_count} more)`}
                          </span>
                        )}
                        <button onClick={() => downloadIcs(m)} title="Download .ics calendar file"
                          className="flex items-center gap-1 text-violet-400 hover:text-violet-300 transition-colors">
                          <Download className="h-3 w-3" /> .ics
                        </button>
                      </div>

                      {/* Participants */}
                      {m.participants?.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 pt-1">
                          {m.participants.map((p, pi) => {
                            const psc = STATUS_CONFIG[p.status] || STATUS_CONFIG.pending;
                            return (
                              <span key={pi} className={`text-[10px] px-2 py-0.5 rounded-full border ${psc.bg} ${psc.color} border-white/10`}>
                                {p.name}: {p.status}
                              </span>
                            );
                          })}
                        </div>
                      )}

                      {/* Agenda */}
                      {m.agenda?.length > 0 && (
                        <div className="pt-1 space-y-1">
                          <span className="text-[10px] text-gray-500 uppercase tracking-wide">Agenda</span>
                          {m.agenda.map((a, ai) => (
                            <div key={ai} className="flex items-start gap-2 text-xs text-gray-300">
                              <span className="text-violet-400 mt-0.5">{a.done ? '✓' : '•'}</span>
                              <span className={a.done ? 'line-through text-gray-500' : ''}>{a.item}</span>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Response history */}
                      {m.responses?.length > 0 && (
                        <div className="space-y-1 pt-1 border-t border-white/5">
                          {m.responses.map((r, ri) => (
                            <div key={ri} className="text-xs text-gray-400 flex items-center gap-2">
                              <span className="font-medium text-gray-300">{r.responder_name}</span>
                              <span className={`px-1.5 py-0.5 rounded text-[10px] ${STATUS_CONFIG[r.action]?.bg || 'bg-gray-500/20'} ${STATUS_CONFIG[r.action]?.color || 'text-gray-400'}`}>
                                {r.action}
                              </span>
                              {r.proposed_time && <span>→ {new Date(r.proposed_time).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</span>}
                              {r.reason && <span className="italic">"{r.reason}"</span>}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Actions */}
                      {m.status !== 'accepted' && m.status !== 'withdrawn' && (
                        <div className="flex gap-2 pt-1 flex-wrap">
                          {respondingTo === m.id ? (
                            <div className="w-full space-y-2 bg-white/[0.03] rounded-lg p-3">
                              <input value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} placeholder="Reason (optional)"
                                className="w-full bg-transparent border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder:text-white/30 focus:outline-none focus:ring-1 focus:ring-violet-500/50" />
                              <div className="flex items-center gap-2">
                                <input type="date" value={counterDate} onChange={(e) => setCounterDate(e.target.value)}
                                  className="bg-transparent border border-white/10 rounded-lg px-2 py-1.5 text-xs text-white focus:outline-none focus:ring-1 focus:ring-violet-500/50" />
                                <input type="time" value={counterTime} onChange={(e) => setCounterTime(e.target.value)}
                                  className="bg-transparent border border-white/10 rounded-lg px-2 py-1.5 text-xs text-white focus:outline-none focus:ring-1 focus:ring-violet-500/50" />
                              </div>
                              <div className="flex gap-2">
                                <Button size="sm" onClick={() => handleRespond(m.id, 'counter_proposed')} disabled={respondLoading || !counterDate || !counterTime}
                                  className="bg-blue-600 hover:bg-blue-700 text-xs h-7">
                                  {respondLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <><ArrowRightLeft className="h-3 w-3 mr-1" /> Suggest Time</>}
                                </Button>
                                <Button size="sm" variant="ghost" onClick={() => setRespondingTo(null)} className="text-xs h-7">Cancel</Button>
                              </div>
                            </div>
                          ) : (
                            <>
                              {/* Accept button — shown when invitee counter-proposed a new time */}
                              {m.status === 'counter_proposed' && (
                                <Button size="sm" onClick={() => handleRespond(m.id, 'accepted')} disabled={respondLoading}
                                  className="bg-green-600 hover:bg-green-700 text-xs h-7">
                                  <CheckCircle className="h-3 w-3 mr-1" /> Accept Proposed Time
                                </Button>
                              )}
                              <Button size="sm" onClick={() => handleRespond(m.id, 'withdrawn')} variant="outline" className="text-xs h-7 border-red-500/30 text-red-400 hover:bg-red-500/10">
                                <Trash2 className="h-3 w-3 mr-1" /> Withdraw
                              </Button>
                              <Button size="sm" onClick={() => setRespondingTo(m.id)} variant="outline" className="text-xs h-7 border-blue-500/30 text-blue-400 hover:bg-blue-500/10">
                                <ArrowRightLeft className="h-3 w-3 mr-1" /> Change Time
                              </Button>
                            </>
                          )}
                        </div>
                      )}

                      {/* Meeting Notes link — show for past accepted meetings */}
                      {m.status === 'accepted' && new Date(m.proposed_time) < new Date() && (
                        <div className="pt-1 border-t border-white/5">
                          <span className="text-[10px] text-green-400 flex items-center gap-1">
                            <CheckCircle className="h-3 w-3" /> Meeting completed — add notes in the AI Tools → Meeting Notes tab
                          </span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
