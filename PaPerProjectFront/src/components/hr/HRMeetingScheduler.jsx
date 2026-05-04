/**
 * HRMeetingScheduler — port of pm-agent/MeetingScheduler.jsx adapted for HR.
 *
 * Same shape (collapsible chat-history sidebar + Chat / Meetings tabs +
 * markdown-rendered assistant turns + .ics export) but talks to
 * `hrAgentService` and the HR data model. Differences vs. PM:
 *   * No accept/reject/counter-propose flow — HR meetings are
 *     organizer-driven, so we expose Edit + Cancel instead.
 *   * Participants come from the company's employees (auth.User-backed),
 *     not the M2M-with-status PM model.
 *   * Sensitive types (`exit_interview`, `grievance_hearing`,
 *     `performance_review`) are auto-marked private at create time on the
 *     backend.
 */
import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import {
  Loader2, Send, Calendar, MessageCircle, RefreshCw, Plus, Trash2,
  ChevronsLeft, ChevronsRight, Bot, Download, Pencil, X, ListChecks,
  Sparkles,
} from 'lucide-react';
import hrAgentService from '@/services/hrAgentService';

// ---------- markdown helper (lifted from PM/HR Q&A) ----------
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
    if (t.startsWith('## ')) { out.push(`<h3 class="text-base font-semibold text-violet-300 mt-2 mb-1">${bold(escape(t.slice(3)))}</h3>`); continue; }
    if (/^[-*]\s/.test(t)) { out.push(`<div class="flex items-start gap-2 ml-2"><span class="text-violet-400 mt-0.5">•</span><span class="text-gray-200 text-sm">${italic(bold(escape(t.replace(/^[-*]\s+/, ''))))}</span></div>`); continue; }
    out.push(`<p class="text-gray-300 my-0.5 text-sm">${italic(bold(escape(t)))}</p>`);
  }
  return out.join('\n');
}

const STATUS_BADGE = {
  scheduled: { color: 'text-emerald-400', bg: 'bg-emerald-500/15', border: 'border-emerald-400/30' },
  completed: { color: 'text-sky-400', bg: 'bg-sky-500/15', border: 'border-sky-400/30' },
  cancelled: { color: 'text-rose-400', bg: 'bg-rose-500/15', border: 'border-rose-400/30' },
  rescheduled: { color: 'text-amber-400', bg: 'bg-amber-500/15', border: 'border-amber-400/30' },
};

const MEETING_TYPE_LABEL = {
  onboarding_orientation: 'Onboarding',
  one_on_one: '1:1',
  performance_review: 'Performance review',
  mid_year_check_in: 'Mid-year check-in',
  exit_interview: 'Exit interview',
  grievance_hearing: 'Grievance hearing',
  training_session: 'Training',
  benefits_consult: 'Benefits',
  other: 'Other',
};

export default function HRMeetingScheduler() {
  const { toast } = useToast();
  const messagesEndRef = useRef(null);

  // Chat sidebar state
  const [chats, setChats] = useState([]);
  const [selectedChatId, setSelectedChatId] = useState(null);
  const [loadingChats, setLoadingChats] = useState(true);
  const [showChatHistory, setShowChatHistory] = useState(true);
  const [showSidebarSearch, setShowSidebarSearch] = useState(false);
  const [sidebarSearch, setSidebarSearch] = useState('');

  // Input
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  // Meetings tab
  const [activeTab, setActiveTab] = useState('chat');
  const [meetings, setMeetings] = useState([]);
  const [meetingsLoading, setMeetingsLoading] = useState(false);

  // Edit / cancel dialogs
  const [editDialog, setEditDialog] = useState({ open: false, meeting: null });
  const [cancelDialog, setCancelDialog] = useState({ open: false, meeting: null, reason: '' });
  const [savingEdit, setSavingEdit] = useState(false);
  const [extractingFor, setExtractingFor] = useState(null);

  // ---------- Load + auto-hide on small screens ----------
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)');
    if (mq.matches) setShowChatHistory(false);
    const handler = (e) => { if (e.matches) setShowChatHistory(false); };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  const normalizeChat = (chat) => {
    if (!chat) return chat;
    return {
      ...chat,
      id: String(chat.id),
      title: chat.title || 'Meeting chat',
      messages: chat.messages || [],
      updatedAt: chat.updatedAt || chat.timestamp,
    };
  };

  const loadChats = async () => {
    setLoadingChats(true);
    try {
      const res = await hrAgentService.listHRMeetingSchedulerChats();
      const list = res?.data || (Array.isArray(res) ? res : []);
      setChats((Array.isArray(list) ? list : []).map(normalizeChat));
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

  useEffect(() => { scrollToBottom(); }, [currentMessages.length, loading]);

  // ---------- Chat send ----------
  const persistTurn = async (userMsg, assistantMsg, titleSnippet) => {
    const title = titleSnippet.slice(0, 40);
    const extract = (res) => {
      if (res?.data?.id) return normalizeChat(res.data);
      if (res?.id) return normalizeChat(res);
      return null;
    };
    if (selectedChatId) {
      const existing = chats.find((c) => c.id === selectedChatId);
      const allMsgs = [...(existing?.messages || []), userMsg, assistantMsg];
      const updRes = await hrAgentService.updateHRMeetingSchedulerChat(selectedChatId, {
        messages: allMsgs, title: existing?.title || title,
      });
      const updated = extract(updRes);
      if (updated) {
        setChats((prev) => [updated, ...prev.filter((c) => c.id !== selectedChatId)]);
      }
    } else {
      const createRes = await hrAgentService.createHRMeetingSchedulerChat({
        title, messages: [userMsg, assistantMsg],
      });
      const newChat = extract(createRes);
      if (newChat) {
        setChats((prev) => [newChat, ...prev]);
        setSelectedChatId(newChat.id);
      }
    }
  };

  const handleSend = async () => {
    const msg = input.trim();
    if (!msg || loading) return;
    setInput('');
    setLoading(true);

    // Optimistic user bubble
    const tempUser = { role: 'user', content: msg };
    if (selectedChat) {
      setChats((prev) => prev.map((c) =>
        c.id === selectedChatId ? { ...c, messages: [...c.messages, tempUser] } : c,
      ));
    }
    setTimeout(scrollToBottom, 30);

    try {
      const history = (selectedChat?.messages || []).slice(-6)
        .map((m) => ({ role: m.role, content: m.content }));
      const res = await hrAgentService.hrMeetingSchedule(msg, history);
      const data = res?.data || {};
      const reply = data.reply || 'Done.';

      const userMsg = { role: 'user', content: msg };
      const assistantMsg = {
        role: 'assistant',
        content: reply,
        responseData: { meeting: data.meeting, parsed: data.parsed },
      };
      // Drop optimistic before persisting
      if (selectedChat) {
        setChats((prev) => prev.map((c) =>
          c.id === selectedChatId ? { ...c, messages: c.messages.filter((m) => m !== tempUser) } : c,
        ));
      }
      await persistTurn(userMsg, assistantMsg, msg);
      if (data.meeting) fetchMeetings();
    } catch (err) {
      console.error('HR meeting schedule failed:', err);
      if (selectedChat) {
        setChats((prev) => prev.map((c) =>
          c.id === selectedChatId ? { ...c, messages: c.messages.filter((m) => m !== tempUser) } : c,
        ));
      }
      await persistTurn(
        { role: 'user', content: msg },
        { role: 'assistant', content: 'Sorry, I had trouble with that. Please try again.' },
        msg,
      );
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const newChat = () => { setSelectedChatId(null); setInput(''); };

  const deleteChat = async (e, chatId) => {
    e.stopPropagation();
    setChats((prev) => prev.filter((c) => c.id !== chatId));
    if (selectedChatId === chatId) setSelectedChatId(null);
    try { await hrAgentService.deleteHRMeetingSchedulerChat(chatId); } catch { /* already gone — fine */ }
  };

  // ---------- Meetings ----------
  const fetchMeetings = async () => {
    setMeetingsLoading(true);
    try {
      const res = await hrAgentService.listHRMeetings();
      setMeetings(res?.data || []);
    } catch { setMeetings([]); }
    finally { setMeetingsLoading(false); }
  };

  useEffect(() => { if (activeTab === 'meetings') fetchMeetings(); }, [activeTab]);

  const downloadIcs = (m) => {
    if (!m.scheduled_at) return;
    const start = new Date(m.scheduled_at);
    const end = new Date(start.getTime() + (m.duration_minutes || 30) * 60000);
    const fmt = (d) => d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
    const desc = (m.description || '');
    const attendees = (m.participants || [])
      .map((p) => (p.work_email ? `ATTENDEE;CN=${p.full_name || p.work_email}:mailto:${p.work_email}` : ''))
      .filter(Boolean).join('\r\n');
    const ics = [
      'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//AIEmployee//HRMeeting//EN', 'METHOD:REQUEST',
      'BEGIN:VEVENT',
      `UID:hr-meeting-${m.id}@aiemployee.app`,
      `DTSTAMP:${fmt(new Date())}`,
      `DTSTART:${fmt(start)}`,
      `DTEND:${fmt(end)}`,
      `SUMMARY:${m.title}`,
      `DESCRIPTION:${desc}`,
      attendees,
      'BEGIN:VALARM', 'TRIGGER:-PT15M', 'ACTION:DISPLAY', `DESCRIPTION:Reminder: ${m.title}`, 'END:VALARM',
      'END:VEVENT', 'END:VCALENDAR',
    ].filter(Boolean).join('\r\n');
    const url = URL.createObjectURL(new Blob([ics], { type: 'text/calendar;charset=utf-8' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = `${(m.title || 'meeting').replace(/[^a-zA-Z0-9 ]/g, '').trim() || 'meeting'}.ics`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleSaveEdit = async () => {
    const m = editDialog.meeting;
    if (!m) return;
    setSavingEdit(true);
    try {
      const payload = {
        title: m.title, description: m.description,
        scheduled_at: m.scheduled_at, duration_minutes: m.duration_minutes,
        meeting_link: m.meeting_link || null,
        location: m.location || '',
        notes: m.notes || '',
        status: m.status,
      };
      const res = await hrAgentService.updateHRMeeting(m.id, payload);
      const updated = res?.data;
      if (updated) {
        setMeetings((arr) => arr.map((x) => (x.id === updated.id ? updated : x)));
      }
      toast({ title: 'Meeting updated' });
      setEditDialog({ open: false, meeting: null });
    } catch (e) {
      toast({ title: 'Update failed', description: e.message, variant: 'destructive' });
    } finally {
      setSavingEdit(false);
    }
  };

  const handleConfirmCancel = async () => {
    const m = cancelDialog.meeting;
    if (!m) return;
    try {
      const res = await hrAgentService.cancelHRMeeting(m.id, cancelDialog.reason);
      const updated = res?.data;
      if (updated) {
        setMeetings((arr) => arr.map((x) => (x.id === updated.id ? updated : x)));
      }
      toast({ title: 'Meeting cancelled' });
      setCancelDialog({ open: false, meeting: null, reason: '' });
    } catch (e) {
      toast({ title: 'Cancel failed', description: e.message, variant: 'destructive' });
    }
  };

  const handleExtractActionItems = async (m) => {
    if (!m.transcript) {
      toast({
        title: 'No transcript',
        description: 'Add a transcript via Edit before extracting action items.',
        variant: 'destructive',
      });
      return;
    }
    setExtractingFor(m.id);
    try {
      const res = await hrAgentService.extractHRMeetingActionItems(m.id);
      const items = res?.data?.action_items || [];
      setMeetings((arr) => arr.map((x) => (x.id === m.id ? { ...x, action_items: items } : x)));
      toast({ title: `Extracted ${items.length} action items` });
    } catch (e) {
      toast({ title: 'Extract failed', description: e.message, variant: 'destructive' });
    } finally {
      setExtractingFor(null);
    }
  };

  // ---------- Stats banner ----------
  const stats = {
    total: meetings.length,
    upcoming: meetings.filter((m) => m.status === 'scheduled' && m.scheduled_at && new Date(m.scheduled_at) > new Date()).length,
    completed: meetings.filter((m) => m.status === 'completed').length,
    cancelled: meetings.filter((m) => m.status === 'cancelled').length,
  };

  // ---------- Render ----------
  return (
    <div
      className="w-full rounded-2xl border border-white/[0.06] p-0 overflow-hidden"
      style={{ background: 'linear-gradient(90deg, #020308 0%, #020308 55%, rgba(10,37,64,0.68) 85%, rgba(14,39,71,0.52) 100%)' }}
    >
      <div className="flex w-full max-w-full relative max-h-[calc(100vh-200px)]">
        {/* SIDEBAR */}
        <div
          className={`shrink-0 rounded-xl border border-white/15 shadow-[0_2px_24px_0_rgba(80,36,180,0.18)] overflow-hidden transition-all duration-300 ease-in-out ${
            showChatHistory ? 'w-64 opacity-100 mr-4' : 'w-0 opacity-0 border-0 mr-0'
          }`}
          style={{
            minWidth: showChatHistory ? '16rem' : '0',
            background: 'linear-gradient(90deg, rgba(139,92,246,0.13) 0%, rgba(36,18,54,0.18) 18%, #0a0a0f 55%, #0a0a0f 100%)',
            backdropFilter: 'blur(12px)',
          }}
        >
          <div className="w-64 h-full flex flex-col">
            <div className="px-3 pt-3 pb-2 border-b border-white/15 flex flex-col gap-2 shrink-0"
                 style={{ background: 'linear-gradient(180deg, rgba(60,30,90,0.22) 0%, rgba(36,18,54,0.85) 100%)' }}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-base font-semibold text-white/90 tracking-wide">Meetings</span>
                <button onClick={() => setShowChatHistory(false)} title="Close sidebar"
                  className="h-8 w-8 flex items-center justify-center rounded-full border border-white/20 hover:border-violet-400/60 bg-black/30 hover:bg-violet-700/20">
                  <ChevronsLeft className="h-4 w-4 text-white/80" />
                </button>
              </div>

              {showSidebarSearch ? (
                <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg w-full"
                  style={{ border: '1.5px solid rgba(139,92,246,0.22)', background: 'linear-gradient(90deg, rgba(80,36,180,0.10) 0%, rgba(36,18,54,0.18) 100%)' }}>
                  <input autoFocus value={sidebarSearch} onChange={(e) => setSidebarSearch(e.target.value)}
                    placeholder="Search..." className="flex-1 bg-transparent outline-none text-white/90 text-sm px-2 py-1.5 placeholder-white/40" />
                  <button onClick={() => { setSidebarSearch(''); setShowSidebarSearch(false); }}
                    className="h-7 w-7 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60">
                    <X className="h-3 w-3 text-white/70" />
                  </button>
                </div>
              ) : (
                <div className="flex items-center justify-between text-xs uppercase tracking-wider text-white/50">
                  <span>Conversations</span>
                  <div className="flex items-center gap-1">
                    <button title="Search" onClick={() => setShowSidebarSearch(true)}
                            className="h-7 w-7 flex items-center justify-center rounded-full hover:bg-white/5">
                      <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" className="text-white/60" viewBox="0 0 24 24">
                        <circle cx="11" cy="11" r="7" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
                      </svg>
                    </button>
                    <button title="New chat" onClick={newChat}
                            className="h-7 w-7 flex items-center justify-center rounded-full hover:bg-white/5">
                      <Plus className="h-4 w-4 text-violet-400" />
                    </button>
                  </div>
                </div>
              )}
            </div>

            <div className="flex-1 overflow-y-auto px-2 py-2">
              {loadingChats ? (
                <div className="flex justify-center py-6"><Loader2 className="h-4 w-4 animate-spin text-white/50" /></div>
              ) : (() => {
                const term = sidebarSearch.trim().toLowerCase();
                const filtered = term ? chats.filter((c) => (c.title || '').toLowerCase().includes(term)) : chats;
                if (filtered.length === 0) {
                  return <div className="text-center text-xs text-white/40 py-6">{term ? 'No matches.' : 'No conversations yet.'}</div>;
                }
                return (
                  <div className="space-y-1">
                    {filtered.map((c) => {
                      const active = c.id === selectedChatId;
                      return (
                        <div key={c.id} onClick={() => setSelectedChatId(c.id)}
                             className={`group rounded-lg p-2 cursor-pointer transition-all duration-100 border ${
                               active
                                 ? 'bg-violet-600/20 border-violet-400/40'
                                 : 'bg-white/[0.02] border-white/[0.05] hover:border-violet-400/20 hover:bg-white/[0.04]'
                             }`}>
                          <div className="flex items-center justify-between gap-2">
                            <div className="min-w-0 flex-1">
                              <div className="text-sm text-white/90 truncate">{c.title || 'Chat'}</div>
                              <div className="text-[10px] text-white/40 mt-0.5">
                                {c.updatedAt ? new Date(c.updatedAt).toLocaleString() : '—'}
                              </div>
                            </div>
                            <button title="Delete" onClick={(e) => deleteChat(e, c.id)}
                              className="opacity-0 group-hover:opacity-100 transition-opacity h-6 w-6 flex items-center justify-center rounded-full hover:bg-rose-500/20">
                              <Trash2 className="h-3.5 w-3.5 text-rose-400" />
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                );
              })()}
            </div>
          </div>
        </div>

        {/* MAIN PANEL */}
        <Card className="flex-1 min-w-0 border-white/[0.06] bg-transparent flex flex-col">
          <CardHeader className="flex flex-row items-center justify-between gap-2 border-b border-white/[0.06] py-3">
            <div className="flex items-center gap-2 min-w-0">
              {!showChatHistory && (
                <button onClick={() => setShowChatHistory(true)} title="Open conversations"
                  className="h-8 w-8 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60 hover:bg-violet-700/20">
                  <ChevronsRight className="h-4 w-4 text-white/80" />
                </button>
              )}
              <div className="min-w-0">
                <CardTitle className="text-base flex items-center gap-2">
                  <Calendar className="h-4 w-4 text-violet-400" />
                  HR Meeting Scheduler
                </CardTitle>
                <CardDescription className="text-xs">
                  Schedule HR meetings in plain English. The agent figures out who, when, and what type.
                </CardDescription>
              </div>
            </div>
            <div className="flex gap-1 rounded-lg border border-white/[0.08] p-0.5">
              <button onClick={() => setActiveTab('chat')}
                className={`px-3 py-1.5 text-xs rounded-md flex items-center gap-1 ${activeTab === 'chat' ? 'bg-violet-600/30 text-violet-200' : 'text-white/60 hover:bg-white/[0.04]'}`}>
                <MessageCircle className="h-3.5 w-3.5" /> Chat
              </button>
              <button onClick={() => setActiveTab('meetings')}
                className={`px-3 py-1.5 text-xs rounded-md flex items-center gap-1 ${activeTab === 'meetings' ? 'bg-violet-600/30 text-violet-200' : 'text-white/60 hover:bg-white/[0.04]'}`}>
                <Calendar className="h-3.5 w-3.5" /> Meetings ({stats.total})
              </button>
            </div>
          </CardHeader>

          <CardContent className="flex-1 flex flex-col min-h-0 p-0">
            {/* CHAT TAB */}
            {activeTab === 'chat' && (
              <>
                <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 min-h-[280px]">
                  {currentMessages.length === 0 && !loading ? (
                    <div className="h-full min-h-[260px] flex flex-col items-center justify-center text-center text-white/60 px-6">
                      <div className="h-12 w-12 rounded-2xl bg-violet-500/10 border border-violet-400/20 flex items-center justify-center mb-3">
                        <Bot className="h-6 w-6 text-violet-400" />
                      </div>
                      <div className="text-sm font-medium text-white/90 mb-1">Schedule HR meetings in plain English</div>
                      <div className="text-xs max-w-md space-y-1">
                        <div><em>"Schedule a 1:1 with Bilal tomorrow at 3pm for 30 minutes"</em></div>
                        <div><em>"Book a performance review with Noor next Tuesday at 10am"</em></div>
                        <div><em>"Set up an exit interview with Abdullah for Friday afternoon"</em></div>
                      </div>
                    </div>
                  ) : (
                    currentMessages.map((msg, idx) => (
                      <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                        <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm ${
                          msg.role === 'user'
                            ? 'bg-violet-600/20 border border-violet-400/30 text-white/95'
                            : 'bg-white/[0.04] border border-white/[0.08] text-white/90'
                        }`}>
                          {msg.role === 'user' ? (
                            <div className="whitespace-pre-wrap">{msg.content}</div>
                          ) : (
                            <>
                              <div className="prose prose-invert max-w-none"
                                   dangerouslySetInnerHTML={{ __html: markdownToHtml(msg.content) }} />
                              {msg.responseData?.meeting && (
                                <div className="mt-3 pt-2 border-t border-white/10 text-xs text-white/70">
                                  <div className="font-medium text-emerald-300 flex items-center gap-1">
                                    <Sparkles className="h-3 w-3" /> Meeting created
                                  </div>
                                  <div className="mt-1">
                                    <span className="font-medium">{msg.responseData.meeting.title}</span>
                                    {' · '}{MEETING_TYPE_LABEL[msg.responseData.meeting.meeting_type] || msg.responseData.meeting.meeting_type}
                                    {' · '}{msg.responseData.meeting.scheduled_at
                                      ? new Date(msg.responseData.meeting.scheduled_at).toLocaleString()
                                      : 'unscheduled'}
                                    {' · '}{msg.responseData.meeting.duration_minutes}m
                                  </div>
                                </div>
                              )}
                            </>
                          )}
                        </div>
                      </div>
                    ))
                  )}

                  {loading && (
                    <div className="flex justify-start">
                      <div className="rounded-2xl px-4 py-2.5 bg-white/[0.04] border border-white/[0.08] text-white/70 text-sm flex items-center gap-2">
                        <Loader2 className="h-3.5 w-3.5 animate-spin text-violet-400" /> Thinking...
                      </div>
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                </div>

                <div className="border-t border-white/[0.06] px-3 py-3 flex items-end gap-2">
                  <Textarea
                    rows={2}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder='e.g. "Schedule a 1:1 with Bilal tomorrow at 3pm"'
                    className="flex-1 resize-none bg-white/[0.03] border-white/[0.08]"
                  />
                  <Button onClick={handleSend} disabled={loading || !input.trim()}>
                    {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                    <span className="ml-1 hidden sm:inline">Send</span>
                  </Button>
                </div>
              </>
            )}

            {/* MEETINGS TAB */}
            {activeTab === 'meetings' && (
              <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
                {/* Stats banner */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <StatCard label="Total" value={stats.total} />
                  <StatCard label="Upcoming" value={stats.upcoming} />
                  <StatCard label="Completed" value={stats.completed} />
                  <StatCard label="Cancelled" value={stats.cancelled} />
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-xs text-white/50">{meetings.length} meeting{meetings.length === 1 ? '' : 's'}</span>
                  <Button variant="outline" size="sm" onClick={fetchMeetings} disabled={meetingsLoading}>
                    {meetingsLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                    <span className="ml-1">Refresh</span>
                  </Button>
                </div>

                {meetingsLoading ? (
                  <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-white/40" /></div>
                ) : meetings.length === 0 ? (
                  <div className="text-center text-sm text-white/50 py-12">
                    No meetings yet. Use the Chat tab to schedule one.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {meetings.map((m) => {
                      const sb = STATUS_BADGE[m.status] || STATUS_BADGE.scheduled;
                      const upcoming = m.scheduled_at && new Date(m.scheduled_at) > new Date();
                      return (
                        <div key={m.id} className="rounded-xl border border-white/[0.08] p-3 bg-gradient-to-br from-white/[0.03] to-white/[0.005]">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2 flex-wrap">
                                <div className="font-medium truncate">{m.title}</div>
                                <Badge className={`text-[10px] ${sb.bg} ${sb.color} ${sb.border}`} variant="outline">{m.status}</Badge>
                                <Badge className="text-[10px]" variant="outline">{MEETING_TYPE_LABEL[m.meeting_type] || m.meeting_type}</Badge>
                                {m.visibility === 'private' && (
                                  <Badge className="text-[10px] bg-rose-500/10 text-rose-300 border-rose-400/30" variant="outline">Private</Badge>
                                )}
                              </div>
                              <div className="text-xs text-white/60 mt-1">
                                {m.scheduled_at ? new Date(m.scheduled_at).toLocaleString() : 'Unscheduled'}
                                {' · '}{m.duration_minutes}m
                                {m.organizer_name ? ` · organized by ${m.organizer_name}` : ''}
                              </div>
                              {m.participants?.length > 0 && (
                                <div className="text-xs text-white/50 mt-1 flex flex-wrap gap-1">
                                  {m.participants.slice(0, 4).map((p) => (
                                    <span key={p.id} className="px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.06]">
                                      {p.full_name || p.work_email}
                                    </span>
                                  ))}
                                  {m.participants.length > 4 && (
                                    <span className="text-white/40">+{m.participants.length - 4} more</span>
                                  )}
                                </div>
                              )}
                              {m.action_items?.length > 0 && (
                                <div className="mt-2 text-xs">
                                  <div className="text-white/60 font-medium flex items-center gap-1 mb-1">
                                    <ListChecks className="h-3 w-3" /> Action items
                                  </div>
                                  <ul className="list-disc list-inside space-y-0.5 text-white/70">
                                    {m.action_items.slice(0, 5).map((a, i) => (
                                      <li key={i}>
                                        {a.text}
                                        {a.owner_name && <span className="text-white/40"> · {a.owner_name}</span>}
                                        {a.due_date && <span className="text-white/40"> · due {a.due_date}</span>}
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                            </div>
                            <div className="flex flex-col gap-1 shrink-0">
                              <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => downloadIcs(m)} disabled={!m.scheduled_at}>
                                <Download className="h-3 w-3 mr-1" /> .ics
                              </Button>
                              <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setEditDialog({ open: true, meeting: { ...m } })}>
                                <Pencil className="h-3 w-3 mr-1" /> Edit
                              </Button>
                              <Button variant="outline" size="sm" className="h-7 text-xs"
                                onClick={() => handleExtractActionItems(m)} disabled={extractingFor === m.id}>
                                {extractingFor === m.id
                                  ? <Loader2 className="h-3 w-3 animate-spin" />
                                  : <ListChecks className="h-3 w-3 mr-1" />}
                                <span className="ml-1">Extract</span>
                              </Button>
                              {m.status !== 'cancelled' && (
                                <Button variant="outline" size="sm"
                                  className="h-7 text-xs text-rose-400 hover:text-rose-300"
                                  onClick={() => setCancelDialog({ open: true, meeting: m, reason: '' })}>
                                  <X className="h-3 w-3 mr-1" /> Cancel
                                </Button>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* EDIT DIALOG */}
      <Dialog open={editDialog.open} onOpenChange={(open) => setEditDialog((s) => ({ ...s, open }))}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Edit meeting</DialogTitle>
            <DialogDescription>Reschedule, update notes, or change status.</DialogDescription>
          </DialogHeader>
          {editDialog.meeting && (
            <div className="space-y-3">
              <div>
                <Label>Title</Label>
                <Input value={editDialog.meeting.title || ''}
                  onChange={(e) => setEditDialog((s) => ({ ...s, meeting: { ...s.meeting, title: e.target.value } }))} />
              </div>
              <div>
                <Label>Description</Label>
                <Textarea rows={2} value={editDialog.meeting.description || ''}
                  onChange={(e) => setEditDialog((s) => ({ ...s, meeting: { ...s.meeting, description: e.target.value } }))} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Scheduled at</Label>
                  <Input type="datetime-local"
                    value={editDialog.meeting.scheduled_at ? editDialog.meeting.scheduled_at.slice(0, 16) : ''}
                    onChange={(e) => {
                      const iso = e.target.value ? new Date(e.target.value).toISOString() : null;
                      setEditDialog((s) => ({ ...s, meeting: { ...s.meeting, scheduled_at: iso } }));
                    }} />
                </div>
                <div>
                  <Label>Duration (min)</Label>
                  <Input type="number" min="5" max="480"
                    value={editDialog.meeting.duration_minutes || 30}
                    onChange={(e) => setEditDialog((s) => ({ ...s, meeting: { ...s.meeting, duration_minutes: Number(e.target.value) || 30 } }))} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Location</Label>
                  <Input value={editDialog.meeting.location || ''}
                    onChange={(e) => setEditDialog((s) => ({ ...s, meeting: { ...s.meeting, location: e.target.value } }))} />
                </div>
                <div>
                  <Label>Status</Label>
                  <Select value={editDialog.meeting.status}
                    onValueChange={(v) => setEditDialog((s) => ({ ...s, meeting: { ...s.meeting, status: v } }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="scheduled">Scheduled</SelectItem>
                      <SelectItem value="rescheduled">Rescheduled</SelectItem>
                      <SelectItem value="completed">Completed</SelectItem>
                      <SelectItem value="cancelled">Cancelled</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div>
                <Label>Meeting link</Label>
                <Input placeholder="https://..."
                  value={editDialog.meeting.meeting_link || ''}
                  onChange={(e) => setEditDialog((s) => ({ ...s, meeting: { ...s.meeting, meeting_link: e.target.value } }))} />
              </div>
              <div>
                <Label>Notes</Label>
                <Textarea rows={2} value={editDialog.meeting.notes || ''}
                  onChange={(e) => setEditDialog((s) => ({ ...s, meeting: { ...s.meeting, notes: e.target.value } }))} />
              </div>
              <div>
                <Label>Transcript (paste here for action-item extraction)</Label>
                <Textarea rows={3} value={editDialog.meeting.transcript || ''}
                  onChange={(e) => setEditDialog((s) => ({ ...s, meeting: { ...s.meeting, transcript: e.target.value } }))} />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditDialog({ open: false, meeting: null })} disabled={savingEdit}>Cancel</Button>
            <Button onClick={handleSaveEdit} disabled={savingEdit}>
              {savingEdit ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* CANCEL DIALOG */}
      <Dialog open={cancelDialog.open} onOpenChange={(open) => setCancelDialog((s) => ({ ...s, open }))}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Cancel meeting?</DialogTitle>
            <DialogDescription>{cancelDialog.meeting?.title}</DialogDescription>
          </DialogHeader>
          <Textarea rows={2} placeholder="Optional reason..."
            value={cancelDialog.reason}
            onChange={(e) => setCancelDialog((s) => ({ ...s, reason: e.target.value }))} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelDialog({ open: false, meeting: null, reason: '' })}>Keep</Button>
            <Button onClick={handleConfirmCancel} className="bg-rose-600 hover:bg-rose-500">Cancel meeting</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

const StatCard = ({ label, value }) => (
  <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2">
    <div className="text-[10px] uppercase tracking-wider text-white/50">{label}</div>
    <div className="text-2xl font-semibold mt-0.5">{value}</div>
  </div>
);
