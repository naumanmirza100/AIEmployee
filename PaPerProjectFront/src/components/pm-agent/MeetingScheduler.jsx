import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/components/ui/use-toast';
import pmAgentService from '@/services/pmAgentService';
import {
  Loader2, Send, CalendarPlus, CheckCircle, XCircle, Clock,
  ArrowRightLeft, Trash2, User, Calendar, MessageSquare, RefreshCw
} from 'lucide-react';

function markdownToHtml(markdown) {
  if (!markdown || typeof markdown !== 'string') return '';
  const escape = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const bold = (s) => s.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-violet-300">$1</strong>');
  const lines = markdown.split('\n');
  const out = [];
  for (const line of lines) {
    const t = line.trim();
    if (!t) { out.push('<br/>'); continue; }
    if (t.startsWith('# ')) { out.push(`<h2 class="text-lg font-bold text-violet-300 mt-3 mb-1">${bold(escape(t.slice(2)))}</h2>`); continue; }
    if (t.startsWith('## ')) { out.push(`<h3 class="text-base font-semibold text-violet-300 mt-2 mb-1">${bold(escape(t.slice(3)))}</h3>`); continue; }
    if (/^[-*]\s/.test(t)) { out.push(`<div class="flex items-start gap-2 ml-2"><span class="text-violet-400 mt-0.5">•</span><span class="text-gray-200">${bold(escape(t.replace(/^[-*]\s+/, '')))}</span></div>`); continue; }
    out.push(`<p class="text-gray-300 my-0.5">${bold(escape(t))}</p>`);
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
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: "I'm your **Meeting Scheduler**. I can help you schedule meetings with your team members.\n\nTry something like:\n- \"Schedule a meeting with Sarah tomorrow at 2 PM\"\n- \"Set up a 1-hour meeting with Ahmed on Friday at 10 AM to discuss the API\"\n- \"Meet with John next Monday at 3:30 PM\"",
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [meetings, setMeetings] = useState([]);
  const [meetingsLoading, setMeetingsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('chat'); // 'chat' or 'meetings'
  const [respondingTo, setRespondingTo] = useState(null); // meeting ID being responded to
  const [rejectReason, setRejectReason] = useState('');
  const [counterDate, setCounterDate] = useState('');
  const [counterTime, setCounterTime] = useState('');
  const [respondLoading, setRespondLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => { scrollToBottom(); }, [messages]);

  useEffect(() => {
    if (activeTab === 'meetings') fetchMeetings();
  }, [activeTab]);

  const fetchMeetings = async () => {
    setMeetingsLoading(true);
    try {
      const res = await pmAgentService.meetingList();
      const data = res?.data?.data?.meetings || [];
      setMeetings(data);
    } catch (e) {
      console.error(e);
    } finally {
      setMeetingsLoading(false);
    }
  };

  const handleSend = async () => {
    const msg = input.trim();
    if (!msg || loading) return;

    setMessages(prev => [...prev, { role: 'user', content: msg }]);
    setInput('');
    setLoading(true);

    try {
      const res = await pmAgentService.meetingSchedule(msg);
      console.log('[MEETING DEBUG] Full response:', JSON.stringify(res?.data, null, 2));
      const data = res?.data?.data || res?.data || {};
      console.log('[MEETING DEBUG] Extracted data:', JSON.stringify(data, null, 2));
      const response = data.response || data.message || 'Something went wrong. Please try again.';

      setMessages(prev => [...prev, {
        role: 'assistant',
        content: response,
        meeting: data.meeting,
      }]);

      // If a meeting was scheduled, refresh the meetings list
      if (data.action === 'scheduled' && data.meeting) {
        fetchMeetings();
      }
    } catch (e) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Sorry, something went wrong. Please try again.',
      }]);
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

  const handleRespond = async (meetingId, action) => {
    setRespondLoading(true);
    try {
      let counterTimeISO = null;
      if (action === 'counter_proposed' && counterDate && counterTime) {
        counterTimeISO = new Date(`${counterDate}T${counterTime}`).toISOString();
      }

      const res = await pmAgentService.meetingRespond(meetingId, action, rejectReason, counterTimeISO);
      const data = res?.data?.data || {};

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
      toast({ title: 'Error', description: e.message || 'Failed to respond.', variant: 'destructive' });
    } finally {
      setRespondLoading(false);
    }
  };

  const formatTime = (isoString) => {
    try {
      return new Date(isoString).toLocaleString('en-US', {
        weekday: 'short', month: 'short', day: 'numeric', year: 'numeric',
        hour: 'numeric', minute: '2-digit', hour12: true,
      });
    } catch { return isoString; }
  };

  return (
    <div className="space-y-4">
      {/* Tab Switcher */}
      <div className="flex gap-2">
        <Button
          variant={activeTab === 'chat' ? 'default' : 'outline'}
          onClick={() => setActiveTab('chat')}
          className={activeTab === 'chat' ? 'bg-violet-600 hover:bg-violet-700' : 'border-gray-600 text-gray-300'}
          size="sm"
        >
          <MessageSquare className="w-4 h-4 mr-2" /> Schedule Meeting
        </Button>
        <Button
          variant={activeTab === 'meetings' ? 'default' : 'outline'}
          onClick={() => setActiveTab('meetings')}
          className={activeTab === 'meetings' ? 'bg-violet-600 hover:bg-violet-700' : 'border-gray-600 text-gray-300'}
          size="sm"
        >
          <Calendar className="w-4 h-4 mr-2" /> My Meetings
          {meetings.filter(m => m.status === 'pending' || m.status === 'counter_proposed').length > 0 && (
            <span className="ml-1.5 px-1.5 py-0.5 text-[10px] bg-red-500 text-white rounded-full">
              {meetings.filter(m => m.status === 'pending' || m.status === 'counter_proposed').length}
            </span>
          )}
        </Button>
      </div>

      {/* ========== CHAT TAB ========== */}
      {activeTab === 'chat' && (
        <Card className="bg-gray-900/50 border-gray-700">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg text-violet-300 flex items-center gap-2">
              <CalendarPlus className="w-5 h-5" /> Meeting Scheduler
            </CardTitle>
            <CardDescription className="text-gray-400">
              Chat with AI to schedule meetings with your team members
            </CardDescription>
          </CardHeader>
          <CardContent>
            {/* Messages */}
            <div className="h-[400px] overflow-y-auto mb-3 space-y-3 pr-1">
              {messages.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[85%] rounded-lg px-4 py-2.5 ${
                    msg.role === 'user'
                      ? 'bg-violet-600/30 text-gray-100 border border-violet-500/30'
                      : 'bg-gray-800 text-gray-200 border border-gray-700'
                  }`}>
                    {msg.role === 'assistant' ? (
                      <div
                        className="text-sm leading-relaxed"
                        dangerouslySetInnerHTML={{ __html: markdownToHtml(msg.content) }}
                      />
                    ) : (
                      <p className="text-sm">{msg.content}</p>
                    )}
                    {/* Show meeting card if one was created */}
                    {msg.meeting && (
                      <div className="mt-2 p-2.5 bg-green-900/20 border border-green-700/30 rounded-md">
                        <div className="flex items-center gap-2 text-green-400 text-xs font-medium mb-1">
                          <CheckCircle className="w-3.5 h-3.5" /> Meeting Created
                        </div>
                        <div className="text-xs text-gray-300 space-y-0.5">
                          <div><span className="text-gray-500">With:</span> {msg.meeting.invitee_name}</div>
                          <div><span className="text-gray-500">When:</span> {formatTime(msg.meeting.proposed_time)}</div>
                          <div><span className="text-gray-500">Duration:</span> {msg.meeting.duration_minutes} min</div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex justify-start">
                  <div className="bg-gray-800 text-gray-400 rounded-lg px-4 py-3 border border-gray-700 flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" /> Scheduling...
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="flex gap-2">
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="e.g., Schedule a meeting with Sarah tomorrow at 2 PM..."
                className="flex-1 bg-gray-800 border-gray-600 text-white placeholder:text-gray-500"
                disabled={loading}
              />
              <Button
                onClick={handleSend}
                disabled={!input.trim() || loading}
                className="bg-violet-600 hover:bg-violet-700"
                size="icon"
              >
                <Send className="w-4 h-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ========== MEETINGS TAB ========== */}
      {activeTab === 'meetings' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-gray-300">Your Meetings</h3>
            <Button onClick={fetchMeetings} disabled={meetingsLoading} variant="outline" size="sm" className="border-gray-600 text-gray-300">
              <RefreshCw className={`w-3.5 h-3.5 mr-1 ${meetingsLoading ? 'animate-spin' : ''}`} /> Refresh
            </Button>
          </div>

          {meetingsLoading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-violet-400" />
              <span className="ml-2 text-gray-400 text-sm">Loading meetings...</span>
            </div>
          )}

          {!meetingsLoading && meetings.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16 text-gray-500">
              <Calendar className="w-10 h-10 mb-3 text-gray-600" />
              <p className="text-sm">No meetings yet. Use the chat to schedule one!</p>
            </div>
          )}

          {!meetingsLoading && meetings.map((meeting) => {
            const statusConf = STATUS_CONFIG[meeting.status] || STATUS_CONFIG.pending;
            const StatusIcon = statusConf.icon;
            const isOrganizer = true; // We'll need user context, but for now show all actions
            const isPending = meeting.status === 'pending' || meeting.status === 'counter_proposed';
            const isResponding = respondingTo === meeting.id;

            return (
              <Card key={meeting.id} className="bg-gray-800/50 border-gray-700">
                <CardContent className="pt-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      {/* Title + Status */}
                      <div className="flex items-center gap-2 flex-wrap">
                        <h4 className="text-sm font-semibold text-white">{meeting.title}</h4>
                        <span className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full ${statusConf.bg} ${statusConf.color}`}>
                          <StatusIcon className="w-3 h-3" /> {statusConf.label}
                        </span>
                      </div>

                      {/* Details */}
                      <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-1 text-xs text-gray-400">
                        <div className="flex items-center gap-1.5">
                          <User className="w-3 h-3" />
                          <span>
                            <span className="text-gray-500">Organizer:</span> {meeting.organizer_name}
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <User className="w-3 h-3" />
                          <span>
                            <span className="text-gray-500">Invitee:</span> {meeting.invitee_name}
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Calendar className="w-3 h-3" />
                          <span>{formatTime(meeting.proposed_time)}</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Clock className="w-3 h-3" />
                          <span>{meeting.duration_minutes} minutes</span>
                        </div>
                      </div>

                      {meeting.description && (
                        <p className="mt-1.5 text-xs text-gray-500">{meeting.description}</p>
                      )}

                      {/* Negotiation History */}
                      {meeting.responses && meeting.responses.length > 1 && (
                        <div className="mt-3 border-t border-gray-700/50 pt-2">
                          <div className="text-[10px] text-gray-500 uppercase tracking-wide mb-1">Negotiation History</div>
                          <div className="space-y-1">
                            {meeting.responses.map((resp, ri) => (
                              <div key={ri} className="text-xs text-gray-400 flex items-start gap-2">
                                <span className={`mt-0.5 ${
                                  resp.action === 'accepted' ? 'text-green-400' :
                                  resp.action === 'rejected' ? 'text-red-400' :
                                  resp.action === 'counter_proposed' ? 'text-blue-400' :
                                  resp.action === 'withdrawn' ? 'text-gray-400' :
                                  'text-yellow-400'
                                }`}>●</span>
                                <span>
                                  <strong>{resp.responder_name}</strong>{' '}
                                  {resp.action === 'proposed' && `proposed ${formatTime(resp.proposed_time)}`}
                                  {resp.action === 'accepted' && 'accepted the meeting'}
                                  {resp.action === 'rejected' && `rejected${resp.reason ? ': ' + resp.reason : ''}`}
                                  {resp.action === 'counter_proposed' && `suggested ${formatTime(resp.proposed_time)}${resp.reason ? ' — ' + resp.reason : ''}`}
                                  {resp.action === 'withdrawn' && 'withdrew the meeting'}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Action Buttons */}
                  {isPending && !isResponding && (
                    <div className="mt-3 flex flex-wrap gap-2 pt-2 border-t border-gray-700/50">
                      <Button size="sm" className="bg-green-600 hover:bg-green-700 text-xs" onClick={() => handleRespond(meeting.id, 'accepted')}>
                        <CheckCircle className="w-3.5 h-3.5 mr-1" /> Accept
                      </Button>
                      <Button size="sm" variant="outline" className="border-red-600 text-red-400 hover:bg-red-600/20 text-xs" onClick={() => setRespondingTo(meeting.id)}>
                        <XCircle className="w-3.5 h-3.5 mr-1" /> Reject / Suggest Time
                      </Button>
                      <Button size="sm" variant="outline" className="border-gray-600 text-gray-400 hover:bg-gray-600/20 text-xs" onClick={() => handleRespond(meeting.id, 'withdrawn')}>
                        <Trash2 className="w-3.5 h-3.5 mr-1" /> Withdraw
                      </Button>
                    </div>
                  )}

                  {/* Reject / Counter-propose Form */}
                  {isResponding && (
                    <div className="mt-3 pt-3 border-t border-gray-700/50 space-y-3">
                      <div>
                        <label className="text-xs text-gray-400 mb-1 block">Reason (optional):</label>
                        <Textarea
                          value={rejectReason}
                          onChange={(e) => setRejectReason(e.target.value)}
                          placeholder="e.g., I have a conflicting meeting at that time..."
                          className="bg-gray-900 border-gray-600 text-white text-sm h-16"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-400 mb-1 block">Suggest alternative time (optional — leave empty to just reject):</label>
                        <div className="flex gap-2">
                          <Input
                            type="date"
                            value={counterDate}
                            onChange={(e) => setCounterDate(e.target.value)}
                            className="bg-gray-900 border-gray-600 text-white text-sm flex-1"
                          />
                          <Input
                            type="time"
                            value={counterTime}
                            onChange={(e) => setCounterTime(e.target.value)}
                            className="bg-gray-900 border-gray-600 text-white text-sm w-32"
                          />
                        </div>
                      </div>
                      <div className="flex gap-2">
                        {counterDate && counterTime ? (
                          <Button
                            size="sm"
                            className="bg-blue-600 hover:bg-blue-700 text-xs"
                            disabled={respondLoading}
                            onClick={() => handleRespond(meeting.id, 'counter_proposed')}
                          >
                            {respondLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" /> : <ArrowRightLeft className="w-3.5 h-3.5 mr-1" />}
                            Suggest This Time
                          </Button>
                        ) : (
                          <Button
                            size="sm"
                            className="bg-red-600 hover:bg-red-700 text-xs"
                            disabled={respondLoading}
                            onClick={() => handleRespond(meeting.id, 'rejected')}
                          >
                            {respondLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" /> : <XCircle className="w-3.5 h-3.5 mr-1" />}
                            Reject Meeting
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="outline"
                          className="border-gray-600 text-gray-400 text-xs"
                          onClick={() => { setRespondingTo(null); setRejectReason(''); setCounterDate(''); setCounterTime(''); }}
                        >
                          Cancel
                        </Button>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
