// Stateless dialog components for the AI Executive Meeting Assistant dashboard.
// Extracted from ExecMeetingDashboard.jsx — each takes only props (open/onClose/
// onCreated/onUpdated/task/meeting) and talks to execMeetingService directly, so
// none of them close over dashboard state.

import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { useToast } from '@/components/ui/use-toast';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Loader2, Sparkles } from 'lucide-react';
import execMeetingService from '@/services/execMeetingService';
import { DateTimePicker, DateOnlyPicker, validateMeetingLink } from './shared';

// ── Schedule meeting dialog ─────────────────────────────────────────────────
export const ScheduleMeetingDialog = ({ open, onClose, onCreated }) => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    title: '', description: '', scheduled_at: '', duration_minutes: '60', meeting_link: '',
  });
  const [agenda, setAgenda] = useState([]);
  const [generatingDesc, setGeneratingDesc] = useState(false);
  const [linkError, setLinkError] = useState('');
  const set = (k, v) => {
    setForm(f => ({ ...f, [k]: v }));
    if (k === 'meeting_link') {
      setLinkError(v && !validateMeetingLink(v) ? 'Please enter a valid meeting link (Google Meet, Zoom, Teams, Jitsi, Webex, etc.)' : '');
    }
  };

  // Participant search state (local to dialog)
  const [searchQ, setSearchQ] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [participants, setParticipants] = useState([]);

  const searchUsers = async (q) => {
    setSearchQ(q);
    if (q.length < 2) { setSearchResults([]); return; }
    setSearchLoading(true);
    try {
      const data = await execMeetingService.searchUsers(q);
      const addedKeys = participants.map(p => `${p.user_type || 'company_user'}-${p.id}`);
      setSearchResults((data.users || []).filter(u => !addedKeys.includes(`${u.user_type || 'company_user'}-${u.id}`)));
    } catch { setSearchResults([]); }
    finally { setSearchLoading(false); }
  };

  const addUser = (u) => {
    setParticipants(prev => [...prev, u]);
    setSearchQ(''); setSearchResults([]);
  };

  const removeUser = (id) => setParticipants(prev => prev.filter(p => p.id !== id));

  const handleGenerateDescription = async () => {
    if (!form.description.trim()) {
      toast({ title: 'Add a few points first', description: 'Type what the meeting should cover, then generate.', variant: 'destructive' });
      return;
    }
    setGeneratingDesc(true);
    try {
      const res = await execMeetingService.generateMeetingDescription(form.title, form.description);
      const data = res.data || {};
      if (data.description) set('description', data.description);
      if (Array.isArray(data.agenda) && data.agenda.length > 0) setAgenda(data.agenda);
      toast({ title: 'Description generated', description: 'Review and edit before scheduling.' });
    } catch (err) {
      toast({ title: 'Failed to generate description', description: err.message, variant: 'destructive' });
    } finally {
      setGeneratingDesc(false);
    }
  };

  const handleSubmit = async () => {
    if (!form.title || !form.scheduled_at) {
      toast({ title: 'Title and date are required', variant: 'destructive' });
      return;
    }
    if (form.meeting_link && !validateMeetingLink(form.meeting_link)) {
      toast({ title: 'Invalid meeting link', description: 'Use Google Meet, Zoom, Teams, Jitsi, or Webex links.', variant: 'destructive' });
      return;
    }
    setLoading(true);
    try {
      const res = await execMeetingService.createMeeting({
        title: form.title,
        description: form.description,
        agenda,
        scheduled_at: form.scheduled_at,
        duration_minutes: parseInt(form.duration_minutes) || 60,
        meeting_link: form.meeting_link.trim() || '',
      });
      // Add participants if any
      const meetingId = res.meeting?.id;
      if (meetingId && participants.length > 0) {
        await Promise.all(participants.map(p => execMeetingService.addParticipant(meetingId, p.id, p.user_type)));
      }
      toast({ title: 'Meeting scheduled!' });
      onCreated();
      onClose();
      setForm({ title: '', description: '', scheduled_at: '', duration_minutes: '60', meeting_link: '' });
      setAgenda([]);
      setParticipants([]); setSearchQ(''); setSearchResults([]);
    } catch (err) {
      toast({ title: 'Failed to schedule meeting', description: err.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-3xl bg-[#0d0b1f] border-white/10 text-white">
        <DialogHeader>
          <DialogTitle>Schedule Meeting</DialogTitle>
          <DialogDescription className="text-white/50">Fill in the meeting details below.</DialogDescription>
        </DialogHeader>
        {/* Two-column layout */}
        <div className="grid grid-cols-2 gap-6 py-2">
          {/* LEFT column — core meeting fields */}
          <div className="space-y-4">
            <div className="space-y-1">
              <Label>Title *</Label>
              <Input value={form.title} onChange={e => set('title', e.target.value)} placeholder="Q3 Strategy Review" className="bg-white/5 border-white/10 text-white" />
            </div>
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <Label>Description</Label>
                <button
                  type="button"
                  onClick={handleGenerateDescription}
                  disabled={generatingDesc}
                  className="flex items-center gap-1 text-[11px] text-violet-300 hover:text-violet-200 disabled:opacity-50"
                >
                  {generatingDesc ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
                  Generate with AI
                </button>
              </div>
              <Textarea value={form.description} onChange={e => set('description', e.target.value)} placeholder="Jot a few points — title + these will be expanded into a description and agenda" rows={3}
                className="bg-white/5 border-white/10 text-white [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]" />
              {agenda.length > 0 && (
                <div className="mt-1.5 rounded-md border border-white/10 bg-white/[0.03] p-2">
                  <p className="text-[10px] text-white/40 mb-1">Agenda (generated)</p>
                  <ul className="space-y-0.5">
                    {agenda.map((item, i) => (
                      <li key={i} className="text-xs text-white/70 flex gap-1.5">
                        <span className="text-violet-400">•</span>{item}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
            <div className="space-y-1">
              <Label>Date & Time *</Label>
              <DateTimePicker value={form.scheduled_at} onChange={v => set('scheduled_at', v)} />
            </div>
            <div className="space-y-1">
              <Label>Duration</Label>
              <Select value={form.duration_minutes} onValueChange={v => set('duration_minutes', v)}>
                <SelectTrigger className="bg-white/5 border-white/10 text-white">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {['15','30','45','60','90','120','180'].map(d => (
                    <SelectItem key={d} value={d}>{d} min</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

          </div>

          {/* RIGHT column — participants */}
          <div className="space-y-3 flex flex-col">
            <Label>Add Participants</Label>

            {/* Added chips */}
            {participants.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {participants.map(p => (
                  <span key={p.id} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-violet-500/20 border border-violet-500/30 text-violet-200 text-xs">
                    {p.full_name}
                    <button onClick={() => removeUser(p.id)} className="text-violet-300/60 hover:text-white leading-none">✕</button>
                  </span>
                ))}
              </div>
            )}

            {/* Search input */}
            <div className="relative">
              <Input
                value={searchQ}
                onChange={e => searchUsers(e.target.value)}
                placeholder="Type name or email to add…"
                autoComplete="off"
                className="bg-white/5 border-white/10 text-white text-sm"
              />
              {searchLoading && <Loader2 className="absolute right-3 top-2.5 h-4 w-4 animate-spin text-white/40" />}
              {searchResults.length > 0 && (
                <div className="absolute z-50 w-full mt-1 rounded-xl border border-white/10 bg-[#1a1333] shadow-xl overflow-hidden">
                  {searchResults.map(u => (
                    <button key={`${u.user_type || 'cu'}-${u.id}`} onClick={() => addUser(u)}
                      className="w-full flex items-center gap-3 px-3 py-2 hover:bg-violet-500/20 transition-colors text-left">
                      <div className="h-7 w-7 rounded-full bg-violet-500/30 flex items-center justify-center text-violet-300 text-xs font-bold flex-shrink-0">
                        {u.full_name?.[0]?.toUpperCase() || '?'}
                      </div>
                      <div>
                        <p className="text-white text-xs font-medium">{u.full_name}</p>
                        <p className="text-white/40 text-[10px]">{u.email} · {u.role}</p>
                      </div>
                    </button>
                  ))}
                </div>
              )}
              {searchQ.length >= 2 && !searchLoading && searchResults.length === 0 && (
                <p className="text-white/30 text-xs mt-1">No users found</p>
              )}
            </div>

            {/* Placeholder when no participants yet */}
            {participants.length === 0 && (
              <p className="text-white/20 text-xs mt-2">Search above to add team members.</p>
            )}
           <div className="space-y-1">
              <Label>Video Call Link <span className="text-white/30 text-xs">(leave blank to auto-generate)</span></Label>
              <Input value={form.meeting_link} onChange={e => set('meeting_link', e.target.value)}
                placeholder="https://meet.google.com/xxx-yyyy-zzz"
                className={`bg-white/5 border-white/10 text-white ${linkError ? 'border-red-500/60' : ''}`} />
              {linkError && <p className="text-red-400 text-[11px] mt-0.5">{linkError}</p>}
              <p className="text-white/25 text-[10px]">Supported: Google Meet, Zoom, Teams, Jitsi, Webex</p>
            </div>
          </div>

        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} className="border-white/10 text-white/70">Cancel</Button>
          <Button onClick={handleSubmit} disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
            Schedule
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

// ── Edit meeting dialog ─────────────────────────────────────────────────────
export const MeetingEditDialog = ({ meeting, open, onClose, onUpdated }) => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    title: '', description: '', scheduled_at: '', duration_minutes: '60',
    meeting_link: '', status: 'scheduled',
  });
  const [agenda, setAgenda] = useState([]);
  const [generatingDesc, setGeneratingDesc] = useState(false);
  const [linkError, setLinkError] = useState('');
  const set = (k, v) => {
    setForm(f => ({ ...f, [k]: v }));
    if (k === 'meeting_link') {
      setLinkError(v && !validateMeetingLink(v) ? 'Please enter a valid meeting link (Google Meet, Zoom, Teams, Jitsi, Webex, etc.)' : '');
    }
  };

  // Populate form when meeting changes
  useEffect(() => {
    if (meeting) {
      setForm({
        title: meeting.title || '',
        description: meeting.description || '',
        scheduled_at: meeting.scheduled_at ? meeting.scheduled_at.slice(0, 16) : '',
        duration_minutes: String(meeting.duration_minutes || 60),
        meeting_link: meeting.meeting_link || '',
        status: meeting.status || 'scheduled',
      });
      setAgenda(Array.isArray(meeting.agenda) ? meeting.agenda : []);
    }
  }, [meeting]);

  const handleGenerateDescription = async () => {
    if (!form.description.trim()) {
      toast({ title: 'Add a few points first', description: 'Type what the meeting should cover, then generate.', variant: 'destructive' });
      return;
    }
    setGeneratingDesc(true);
    try {
      const res = await execMeetingService.generateMeetingDescription(form.title, form.description);
      const data = res.data || {};
      if (data.description) set('description', data.description);
      if (Array.isArray(data.agenda) && data.agenda.length > 0) setAgenda(data.agenda);
      toast({ title: 'Description generated', description: 'Review and edit before saving.' });
    } catch (err) {
      toast({ title: 'Failed to generate description', description: err.message, variant: 'destructive' });
    } finally {
      setGeneratingDesc(false);
    }
  };

  const handleSave = async () => {
    if (!form.title || !form.scheduled_at) {
      toast({ title: 'Title and date are required', variant: 'destructive' });
      return;
    }
    if (form.meeting_link && !validateMeetingLink(form.meeting_link)) {
      toast({ title: 'Invalid meeting link', description: 'Use Google Meet, Zoom, Teams, Jitsi, or Webex links.', variant: 'destructive' });
      return;
    }
    setLoading(true);
    try {
      await execMeetingService.updateMeeting(meeting.id, {
        title: form.title,
        description: form.description,
        agenda,
        scheduled_at: form.scheduled_at,
        duration_minutes: parseInt(form.duration_minutes) || 60,
        meeting_link: form.meeting_link.trim(),
        status: form.status,
      });
      toast({ title: 'Meeting updated', description: 'Participants have been notified by email.' });
      onUpdated();
      onClose();
    } catch (err) {
      toast({ title: 'Update failed', description: err.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-3xl bg-[#0d0b1f] border-white/10 text-white">
        <DialogHeader>
          <DialogTitle>Edit Meeting</DialogTitle>
          <DialogDescription className="text-white/50">Update meeting details. All participants will receive an email notification.</DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-8 py-2">
          {/* LEFT */}
          <div className="space-y-4">
            <div className="space-y-1">
              <Label>Title *</Label>
              <Input value={form.title} onChange={e => set('title', e.target.value)}
                className="bg-white/5 border-white/10 text-white" />
            </div>
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <Label>Description</Label>
                <button
                  type="button"
                  onClick={handleGenerateDescription}
                  disabled={generatingDesc}
                  className="flex items-center gap-1 text-[11px] text-violet-300 hover:text-violet-200 disabled:opacity-50"
                >
                  {generatingDesc ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
                  Generate with AI
                </button>
              </div>
              <Textarea value={form.description} onChange={e => set('description', e.target.value)}
                rows={3} className="bg-white/5 border-white/10 text-white [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]" />
              {agenda.length > 0 && (
                <div className="mt-1.5 rounded-md border border-white/10 bg-white/[0.03] p-2">
                  <p className="text-[10px] text-white/40 mb-1">Agenda</p>
                  <ul className="space-y-0.5">
                    {agenda.map((item, i) => (
                      <li key={i} className="text-xs text-white/70 flex gap-1.5">
                        <span className="text-violet-400">•</span>{item}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
            <div className="space-y-1">
              <Label>Date & Time *</Label>
              <DateTimePicker value={form.scheduled_at} onChange={v => set('scheduled_at', v)} allowPast />
            </div>
          </div>

          {/* RIGHT */}
          <div className="space-y-4">
            <div className="space-y-1">
              <Label>Duration</Label>
              <Select value={form.duration_minutes} onValueChange={v => set('duration_minutes', v)}>
                <SelectTrigger className="bg-white/5 border-white/10 text-white"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {['15','30','45','60','90','120','180'].map(d => (
                    <SelectItem key={d} value={d}>{d} min</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Status</Label>
              <Select value={form.status} onValueChange={v => set('status', v)}>
                <SelectTrigger className="bg-white/5 border-white/10 text-white"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {['scheduled','in_progress','completed','cancelled'].map(s => (
                    <SelectItem key={s} value={s}>{s.replace('_', ' ')}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Video Call Link</Label>
              <Input value={form.meeting_link} onChange={e => set('meeting_link', e.target.value)}
                placeholder="https://meet.google.com/xxx"
                className={`bg-white/5 border-white/10 text-white ${linkError ? 'border-red-500/60' : ''}`} />
              {linkError && <p className="text-red-400 text-[11px] mt-0.5">{linkError}</p>}
              <p className="text-white/25 text-[10px]">Supported: Google Meet, Zoom, Teams, Jitsi, Webex</p>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} className="border-white/10 text-white/70">Cancel</Button>
          <Button onClick={handleSave} disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
            Save Changes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

// ── Shared: multi-assignee picker (used by Add + Detail dialogs) ────────────
export const AssigneePicker = ({ assignees, onChange }) => {
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);

  const search = async (val) => {
    setQ(val);
    if (val.length < 2) { setResults([]); return; }
    setSearching(true);
    try {
      const data = await execMeetingService.searchUsers(val);
      const addedKeys = assignees.map(a => `${a.user_type || 'cu'}-${a.id}`);
      setResults((data.users || []).filter(u => !addedKeys.includes(`${u.user_type || 'cu'}-${u.id}`)));
    } catch { setResults([]); }
    finally { setSearching(false); }
  };

  const add = (u) => { onChange([...assignees, u]); setQ(''); setResults([]); };
  const remove = (key) => onChange(assignees.filter(a => `${a.user_type || 'cu'}-${a.id}` !== key));

  return (
    <div className="space-y-2">
      {assignees.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {assignees.map(a => {
            const key = `${a.user_type || 'cu'}-${a.id}`;
            return (
              <span key={key} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-violet-500/20 border border-violet-500/30 text-violet-200 text-xs">
                {a.full_name}
                <button onClick={() => remove(key)} className="text-violet-300/60 hover:text-white leading-none">✕</button>
              </span>
            );
          })}
        </div>
      )}
      <div className="relative">
        <Input
          value={q}
          onChange={e => search(e.target.value)}
          placeholder="Type name or email to add…"
          autoComplete="off"
          className="bg-white/5 border-white/10 text-white text-sm"
        />
        {searching && <Loader2 className="absolute right-3 top-2.5 h-4 w-4 animate-spin text-white/40" />}
        {results.length > 0 && (
          <div className="absolute z-50 w-full mt-1 rounded-xl border border-white/10 bg-[#1a1333] shadow-xl overflow-hidden">
            {results.map(u => (
              <button key={`${u.user_type || 'cu'}-${u.id}`} onClick={() => add(u)}
                className="w-full flex items-center gap-3 px-3 py-2 hover:bg-violet-500/20 transition-colors text-left">
                <div className="h-7 w-7 rounded-full bg-violet-500/30 flex items-center justify-center text-violet-300 text-xs font-bold flex-shrink-0">
                  {u.full_name?.[0]?.toUpperCase() || '?'}
                </div>
                <div>
                  <p className="text-white text-xs font-medium">{u.full_name}</p>
                  <p className="text-white/40 text-[10px]">{u.email} · {u.role}</p>
                </div>
              </button>
            ))}
          </div>
        )}
        {q.length >= 2 && !searching && results.length === 0 && (
          <p className="text-white/30 text-xs mt-1">No users found</p>
        )}
      </div>
    </div>
  );
};

// ── Add task dialog ─────────────────────────────────────────────────────────
export const AddTaskDialog = ({ open, onClose, onCreated, parentTask }) => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ title: '', description: '', priority: 'medium', due_date: '' });
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const [assignees, setAssignees] = useState([]);
  const [generatingDesc, setGeneratingDesc] = useState(false);

  const reset = () => {
    setForm({ title: '', description: '', priority: 'medium', due_date: '' });
    setAssignees([]);
  };

  const handleGenerateDescription = async () => {
    if (!form.description.trim()) {
      toast({ title: 'Add a few points first', description: 'Type what the task should cover, then generate.', variant: 'destructive' });
      return;
    }
    setGeneratingDesc(true);
    try {
      const res = await execMeetingService.generateTaskDescription(form.title, form.description);
      const data = res.data || {};
      if (data.description) set('description', data.description);
      toast({ title: 'Description generated', description: 'Review and edit before saving.' });
    } catch (err) {
      toast({ title: 'Failed to generate description', description: err.message, variant: 'destructive' });
    } finally {
      setGeneratingDesc(false);
    }
  };

  const handleSubmit = async () => {
    if (!form.title) { toast({ title: 'Title is required', variant: 'destructive' }); return; }
    // A subtask can't be due after its parent task.
    if (parentTask?.due_date && form.due_date && form.due_date > parentTask.due_date) {
      toast({ title: 'Due date too late', description: `Subtask can't be due after the parent task (${parentTask.due_date}).`, variant: 'destructive' });
      return;
    }
    setLoading(true);
    try {
      await execMeetingService.createTask({
        ...form,
        parent_task_id: parentTask?.id || null,
        assignees: assignees.map(a => ({ id: a.id, user_type: a.user_type || 'company_user' })),
      });
      toast({ title: parentTask ? 'Subtask created!' : 'Task created!' });
      onCreated(); onClose(); reset();
    } catch (err) {
      toast({ title: 'Failed to create task', description: err.message, variant: 'destructive' });
    } finally { setLoading(false); }
  };

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) reset(); onClose(); }}>
      <DialogContent className="max-w-lg bg-[#0d0b1f] border-white/10 text-white">
        <DialogHeader>
          <DialogTitle>{parentTask ? `Add Subtask to "${parentTask.title}"` : 'Add Task'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1">
            <Label>Title *</Label>
            <Input value={form.title} onChange={e => set('title', e.target.value)} placeholder="Review Q3 report" className="bg-white/5 border-white/10 text-white" />
          </div>
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <Label>Description</Label>
              <button
                type="button"
                onClick={handleGenerateDescription}
                disabled={generatingDesc}
                className="flex items-center gap-1 text-[11px] text-violet-300 hover:text-violet-200 disabled:opacity-50"
              >
                {generatingDesc ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
                Generate with AI
              </button>
            </div>
            <Textarea value={form.description} onChange={e => set('description', e.target.value)} placeholder="Jot a few points — title + these will be expanded into a description" className="bg-white/5 border-white/10 text-white" rows={3} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Priority</Label>
              <Select value={form.priority} onValueChange={v => set('priority', v)}>
                <SelectTrigger className="bg-white/5 border-white/10 text-white"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {['low','medium','high','critical'].map(p => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Due Date</Label>
              <DateOnlyPicker value={form.due_date} onChange={v => set('due_date', v)} />
              {parentTask?.due_date && (
                <p className="text-white/30 text-[10px]">Must be on or before parent's due date: {parentTask.due_date}</p>
              )}
            </div>
          </div>
          <div className="space-y-1">
            <Label>Assign To</Label>
            <AssigneePicker assignees={assignees} onChange={setAssignees} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} className="border-white/10 text-white/70">Cancel</Button>
          <Button onClick={handleSubmit} disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}{parentTask ? 'Add Subtask' : 'Add Task'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

// ── Task edit dialog (opens when Edit button clicked) ───────────────────────
export const TaskEditDialog = ({ task, onClose, onUpdated }) => {
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);
  const [generatingDesc, setGeneratingDesc] = useState(false);
  const [form, setForm] = useState(null);
  const [assignees, setAssignees] = useState([]);

  useEffect(() => {
    if (task) {
      setForm({
        title: task.title || '',
        description: task.description || '',
        status: task.status || 'todo',
        priority: task.priority || 'medium',
        due_date: task.due_date || '',
      });
      setAssignees((task.assignees || []).map(a => ({ ...a, user_type: 'company_user' })));
    }
  }, [task]);

  if (!task || !form) return null;
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const handleGenerateDescription = async () => {
    if (!form.description.trim()) {
      toast({ title: 'Add a few points first', description: 'Type what the task should cover, then generate.', variant: 'destructive' });
      return;
    }
    setGeneratingDesc(true);
    try {
      const res = await execMeetingService.generateTaskDescription(form.title, form.description);
      const data = res.data || {};
      if (data.description) set('description', data.description);
      toast({ title: 'Description generated', description: 'Review and edit before saving.' });
    } catch (err) {
      toast({ title: 'Failed to generate description', description: err.message, variant: 'destructive' });
    } finally {
      setGeneratingDesc(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await execMeetingService.updateTask(task.id, {
        ...form,
        assignees: assignees.map(a => ({ id: a.id, user_type: a.user_type || 'company_user' })),
      });
      toast({ title: 'Task updated!' });
      onUpdated();
      onClose();
    } catch (err) {
      toast({ title: 'Failed to save', description: err.message, variant: 'destructive' });
    } finally { setSaving(false); }
  };

  return (
    <Dialog open={!!task} onOpenChange={v => { if (!v) onClose(); }}>
      <DialogContent className="max-w-lg bg-[#0d0b1f] border-white/10 text-white">
        <DialogHeader>
          <DialogTitle>Edit Task</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1">
            <Label>Title *</Label>
            <Input value={form.title} onChange={e => set('title', e.target.value)} className="bg-white/5 border-white/10 text-white" />
          </div>
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <Label>Description</Label>
              <button
                type="button"
                onClick={handleGenerateDescription}
                disabled={generatingDesc}
                className="flex items-center gap-1 text-[11px] text-violet-300 hover:text-violet-200 disabled:opacity-50"
              >
                {generatingDesc ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
                Generate with AI
              </button>
            </div>
            <Textarea value={form.description} onChange={e => set('description', e.target.value)} className="bg-white/5 border-white/10 text-white" rows={3} />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1">
              <Label>Status</Label>
              <Select value={form.status} onValueChange={v => set('status', v)}>
                <SelectTrigger className="bg-white/5 border-white/10 text-white"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {['todo','in_progress','review','done','blocked'].map(s => (
                    <SelectItem key={s} value={s}>{s.replace('_',' ')}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Priority</Label>
              <Select value={form.priority} onValueChange={v => set('priority', v)}>
                <SelectTrigger className="bg-white/5 border-white/10 text-white"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {['low','medium','high','critical'].map(p => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Due Date</Label>
              <DateOnlyPicker value={form.due_date} onChange={v => set('due_date', v)} />
            </div>
          </div>
          <div className="space-y-1">
            <Label>Assigned To</Label>
            <AssigneePicker assignees={assignees} onChange={setAssignees} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} className="border-white/10 text-white/70">Cancel</Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
