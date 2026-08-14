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
import { Loader2, Sparkles, Users, ChevronRight, Wand2 } from 'lucide-react';
import execMeetingService from '@/services/execMeetingService';
import { DateTimePicker, DateOnlyPicker, validateMeetingLink, todayStr } from './shared';
import HoverTip from '@/components/common/HoverTip';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import { AllMembersPanel } from './AllMembersPanel';

// ── Schedule meeting dialog ─────────────────────────────────────────────────
// `prefill` (optional) seeds the form when opened from "Create with AI":
// { title, description, scheduled_at, duration_minutes, meeting_link, agenda,
//   participants }. Absent for the normal (blank) Schedule flow.
export const ScheduleMeetingDialog = ({ open, onClose, onCreated, prefill = null, onEditAiPrompt = null, onCreateWithAI = null }) => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    title: '', description: '', scheduled_at: '', duration_minutes: '60', meeting_link: '',
  });
  const [agenda, setAgenda] = useState([]);
  const [generatingDesc, setGeneratingDesc] = useState(false);
  const [linkError, setLinkError] = useState('');
  const [conflicts, setConflicts] = useState(null); // clashing meetings awaiting confirmation
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

  // On every open, (re)initialise from the AI draft if present, else to a
  // clean blank state. The dialog persists its local state while closed, so
  // without clearing here, participants from a cancelled AI draft would
  // linger and merge into the next one.
  useEffect(() => {
    if (!open) return;
    if (prefill) {
      setForm({
        title: prefill.title || '',
        description: prefill.description || '',
        scheduled_at: prefill.scheduled_at || '',
        duration_minutes: String(prefill.duration_minutes || 60),
        meeting_link: prefill.meeting_link || '',
      });
      setAgenda(Array.isArray(prefill.agenda) ? prefill.agenda : []);
      setParticipants(Array.isArray(prefill.participants) ? prefill.participants : []);
    } else {
      setForm({ title: '', description: '', scheduled_at: '', duration_minutes: '60', meeting_link: '' });
      setAgenda([]);
      setParticipants([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, prefill]);

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

  // "View all members" side panel — lets the user pick from the whole roster
  // instead of typing. Clicking a member in the panel toggles them here.
  const [showAllMembers, setShowAllMembers] = useState(false);
  const pKey = (u) => `${u?.user_type || 'company_user'}-${u?.id}`;
  const toggleUser = (u) => {
    setParticipants(prev =>
      prev.some(p => pKey(p) === pKey(u))
        ? prev.filter(p => pKey(p) !== pKey(u))
        : [...prev, u]
    );
  };

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

  // Actually creates the meeting (called directly, or after the user confirms
  // past a scheduling conflict).
  const doCreate = async () => {
    setConflicts(null);
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

  const handleSubmit = async () => {
    if (!form.title || !form.scheduled_at) {
      toast({ title: 'Title and date are required', variant: 'destructive' });
      return;
    }
    if (form.meeting_link && !validateMeetingLink(form.meeting_link)) {
      toast({ title: 'Invalid meeting link', description: 'Use Google Meet, Zoom, Teams, Jitsi, or Webex links.', variant: 'destructive' });
      return;
    }
    // Warn about any meeting already scheduled/in-progress at this time before
    // creating — let the user confirm they want a second meeting in that slot.
    setLoading(true);
    try {
      const res = await execMeetingService.checkMeetingConflicts({
        scheduled_at: form.scheduled_at,
        duration_minutes: parseInt(form.duration_minutes) || 60,
      });
      const found = res.conflicts || [];
      if (found.length > 0) {
        setConflicts(found);
        setLoading(false);
        return;
      }
    } catch {
      // If the conflict check itself fails, don't block creation — just proceed.
    }
    await doCreate();
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      {/* When the members panel is open the dialog widens and lays its
          content + the panel side by side (panel sits beside the dialog
          body, not on top of it). */}
      <DialogContent className={`bg-[#0d0b1f] border-white/10 text-white transition-[max-width] ${showAllMembers ? 'max-w-5xl' : 'max-w-3xl'}`}>
        <div className="flex gap-4 items-stretch">
          <div className="min-w-0 flex-1">
        <DialogHeader>
          {/* Title + an AI button sitting right after it (kept away from the
              dialog's own close ✕ in the top-right corner, with pr-8 padding).
              When opened from AI → "Edit AI prompt" (reopen/regenerate);
              otherwise → "Create with AI" (switch to the prompt flow). */}
          <div className="flex items-center gap-3 flex-wrap pr-8">
            <DialogTitle>Schedule Meeting</DialogTitle>
            {onEditAiPrompt ? (
              <HoverTip tip="Edit the AI prompt and generate a new draft">
                <button
                  type="button"
                  onClick={onEditAiPrompt}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-violet-400/40 bg-violet-400/10 text-violet-200 text-xs font-medium hover:bg-violet-400/20 hover:text-violet-100 transition"
                >
                  <Wand2 className="h-3.5 w-3.5" />
                  Edit AI prompt
                </button>
              </HoverTip>
            ) : onCreateWithAI ? (
              <HoverTip tip="Describe this meeting in plain language and let AI draft it">
                <button
                  type="button"
                  onClick={onCreateWithAI}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-violet-400/40 bg-violet-400/10 text-violet-200 text-xs font-medium hover:bg-violet-400/20 hover:text-violet-100 transition"
                >
                  <Wand2 className="h-3.5 w-3.5" />
                  Create with AI
                </button>
              </HoverTip>
            ) : null}
          </div>
          <DialogDescription className="text-white/50">Fill in the meeting details below.</DialogDescription>
        </DialogHeader>
        {/* Two-column layout */}
        <div className="grid grid-cols-2 gap-6 py-2">
          {/* LEFT column — core meeting fields */}
          <div className="space-y-4">
            <div className="space-y-1">
              <Label>Title *</Label>
              <Input value={form.title} onChange={e => set('title', e.target.value)} disabled={loading} placeholder="Q3 Strategy Review" className="bg-white/5 border-white/10 text-white disabled:opacity-60 disabled:cursor-not-allowed" />
            </div>
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <Label>Description</Label>
                <HoverTip tip="Add little description to convert into a proper description and agenda">
                  <button
                    type="button"
                    onClick={handleGenerateDescription}
                    disabled={generatingDesc}
                    className="flex items-center gap-1 text-[11px] text-violet-300 hover:text-violet-200 disabled:opacity-50"
                  >
                    {generatingDesc ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
                    Generate with AI
                  </button>
                </HoverTip>
              </div>
              <Textarea value={form.description} onChange={e => set('description', e.target.value)} disabled={loading} placeholder="Jot a few points — title + these will be expanded into a description and agenda" rows={3}
                className="bg-white/5 border-white/10 text-white disabled:opacity-60 disabled:cursor-not-allowed [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]" />
            </div>
            <div className="space-y-1">
              <Label>Date & Time *</Label>
              <DateTimePicker value={form.scheduled_at} onChange={v => set('scheduled_at', v)} disabled={loading} />
            </div>
            <div className="space-y-1">
              <Label>Duration</Label>
              <Select value={form.duration_minutes} disabled={loading} onValueChange={v => set('duration_minutes', v)}>
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
            <div className="flex items-center justify-between">
              <Label>Add Participants</Label>
              {/* Opens the "all members" side panel instead of typing. */}
              <button
                type="button"
                onClick={() => setShowAllMembers(v => !v)}
                className="flex items-center gap-1 text-[11px] text-violet-300 hover:text-violet-200"
              >
                <Users className="h-3 w-3" />
                View all members
                <ChevronRight className={`h-3 w-3 transition-transform ${showAllMembers ? 'rotate-90' : ''}`} />
              </button>
            </div>

            {/* Added chips */}
            {participants.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {participants.map(p => (
                  <span key={p.id} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-violet-500/20 border border-violet-500/30 text-violet-200 text-xs">
                    {p.full_name}
                    <HoverTip tip="Remove this participant">
                      <button onClick={() => removeUser(p.id)} className="text-violet-300/60 hover:text-white leading-none">✕</button>
                    </HoverTip>
                  </span>
                ))}
              </div>
            )}

            {/* Search input */}
            <div className="relative">
              <Input
                value={searchQ}
                onChange={e => searchUsers(e.target.value)}
                disabled={loading}
                placeholder="Type name or email to add…"
                autoComplete="off"
                className="bg-white/5 border-white/10 text-white text-sm disabled:opacity-60 disabled:cursor-not-allowed" />
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
              <p className="text-white/20 text-xs mt-2">Search above to add team members.</p>)}
           <div className="space-y-1">
              <Label>Video Call Link <span className="text-white/30 text-xs">(leave blank to auto-generate)</span></Label>
              <Input value={form.meeting_link} onChange={e => set('meeting_link', e.target.value)} disabled={loading}
                placeholder="https://meet.google.com/xxx-yyyy-zzz"
                className={`bg-white/5 border-white/10 text-white disabled:opacity-60 disabled:cursor-not-allowed ${linkError ? 'border-red-500/60' : ''}`} />
              {linkError && <p className="text-red-400 text-[11px] mt-0.5">{linkError}</p>}
              <p className="text-white/25 text-[10px]">Supported: Google Meet, Zoom, Teams, Jitsi, Webex</p>
            </div>
          </div>
        </div>
        {/* Agenda — full width below both columns so generating it doesn't
            stretch the left column and misalign the fields. */}
        {agenda.length > 0 && (
          <div className="rounded-md border border-white/10 bg-white/[0.03] p-3 max-h-40 overflow-y-auto mt-2 mb-5">
            <p className="text-[10px] text-white/40 mb-1.5 uppercase tracking-wide">Agenda (generated)</p>
            <ul className="space-y-1">
              {agenda.map((item, i) => (
                <li key={i} className="text-xs text-white/70 flex gap-1.5">
                  <span className="text-violet-400">•</span>{item}
                </li>
              ))}
            </ul>
          </div>
        )}


        <DialogFooter>
          <Button variant="outline" onClick={onClose} className="border-white/10 text-white/70">Cancel</Button>
          <HoverTip tip="Schedule this meeting">
            <Button onClick={handleSubmit} disabled={loading}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Schedule
            </Button>
          </HoverTip>
        </DialogFooter>
          </div>

          {/* Side panel — all company members, attached to the right. */}
          <AllMembersPanel
            open={showAllMembers}
            onClose={() => setShowAllMembers(false)}
            selected={participants}
            onToggle={toggleUser}
          />
        </div>
      </DialogContent>


      <MeetingConflictDialog
        conflicts={conflicts}
        onCancel={() => setConflicts(null)}
        onConfirm={doCreate}
        loading={loading}/>
    </Dialog>
  );
};

// Shown when a meeting already occupies the chosen time slot — lets the user
// double-book on purpose or go back and pick another time.
const MeetingConflictDialog = ({ conflicts, onCancel, onConfirm, loading }) => (
  <Dialog open={!!conflicts && conflicts.length > 0} onOpenChange={v => { if (!v) onCancel(); }}>
    <DialogContent className="max-w-md bg-[#0d0b1f] border-white/10 text-white">
      <DialogHeader>
        <DialogTitle className="text-amber-300">Time slot already booked</DialogTitle>
        <DialogDescription className="text-white/50">
          You already have {conflicts?.length === 1 ? 'a meeting' : `${conflicts?.length} meetings`} at this time.
        </DialogDescription>
      </DialogHeader>
      <div className="space-y-2 py-2">
        {(conflicts || []).map(c => (
          <div key={c.id} className="rounded-lg border-b border-amber-500/20 px-3 py-2">
            <p className="text-sm font-medium text-white">{c.title}</p>
            <p className="text-xs text-white/50">
              {c.status === 'in_progress' ? 'In progress' : 'Scheduled'}
              {c.scheduled_at ? ` · ${new Date(c.scheduled_at).toLocaleString()}` : ''}
              {c.duration_minutes ? ` · ${c.duration_minutes} min` : ''}
            </p>
          </div>
        ))}
        <p className="text-xs text-white/40 pt-1">Do you still want to add another meeting in this slot?</p>
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onCancel} className="border-white/10 text-white/70">Pick another time</Button>
        <HoverTip tip="Book this slot despite the conflict">
          <Button onClick={onConfirm} disabled={loading} className="bg-amber-600 hover:bg-amber-700 text-white border-0">
            {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
            Add anyway
          </Button>
        </HoverTip>
      </DialogFooter>
    </DialogContent>
  </Dialog>
);

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
  const [conflicts, setConflicts] = useState(null);
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

  const doSave = async () => {
    setConflicts(null);
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

  const handleSave = async () => {
    if (!form.title || !form.scheduled_at) {
      toast({ title: 'Title and date are required', variant: 'destructive' });
      return;
    }
    if (form.meeting_link && !validateMeetingLink(form.meeting_link)) {
      toast({ title: 'Invalid meeting link', description: 'Use Google Meet, Zoom, Teams, Jitsi, or Webex links.', variant: 'destructive' });
      return;
    }
    // Only warn about clashes when the meeting is (or stays) active. Marking a
    // meeting completed or cancelled frees its slot, so there's nothing to
    // conflict with — save straight through.
    if (form.status === 'completed' || form.status === 'cancelled') {
      await doSave();
      return;
    }
    setLoading(true);
    try {
      // Exclude this meeting itself from the clash check (it legitimately
      // occupies its own slot).
      const res = await execMeetingService.checkMeetingConflicts({
        scheduled_at: form.scheduled_at,
        duration_minutes: parseInt(form.duration_minutes) || 60,
        exclude_meeting_id: meeting.id,
      });
      const found = res.conflicts || [];
      if (found.length > 0) {
        setConflicts(found);
        setLoading(false);
        return;
      }
    } catch {
      // conflict check failed — don't block the update
    }
    await doSave();
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
              <Input value={form.title} onChange={e => set('title', e.target.value)} disabled={loading}
                className="bg-white/5 border-white/10 text-white disabled:opacity-60 disabled:cursor-not-allowed" />
            </div>
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <Label>Description</Label>
                <HoverTip tip="Add little description to convert into a proper description and agenda">
                  <button
                    type="button"
                    onClick={handleGenerateDescription}
                    disabled={generatingDesc || loading}
                    className="flex items-center gap-1 text-[11px] text-violet-300 hover:text-violet-200 disabled:opacity-50"
                  >
                    {generatingDesc ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
                    Generate with AI
                  </button>
                </HoverTip>
              </div>
              <Textarea value={form.description} onChange={e => set('description', e.target.value)} disabled={loading}
                rows={3} className="bg-white/5 border-white/10 text-white disabled:opacity-60 disabled:cursor-not-allowed [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]" />
            </div>
            <div className="space-y-1">
              <Label>Date & Time *</Label>
              <DateTimePicker value={form.scheduled_at} onChange={v => set('scheduled_at', v)} disabled={loading} />
            </div>
          </div>

          {/* RIGHT */}
          <div className="space-y-4">
            <div className="space-y-1">
              <Label>Duration</Label>
              <Select value={form.duration_minutes} disabled={loading} onValueChange={v => set('duration_minutes', v)}>
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
              <Select value={form.status} disabled={loading} onValueChange={v => set('status', v)}>
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
              <Input value={form.meeting_link} onChange={e => set('meeting_link', e.target.value)} disabled={loading}
                placeholder="https://meet.google.com/xxx"
                className={`bg-white/5 border-white/10 text-white disabled:opacity-60 disabled:cursor-not-allowed ${linkError ? 'border-red-500/60' : ''}`} />
              {linkError && <p className="text-red-400 text-[11px] mt-0.5">{linkError}</p>}
              <p className="text-white/25 text-[10px]">Supported: Google Meet, Zoom, Teams, Jitsi, Webex</p>
            </div>
          </div>
        </div>

        {/* Agenda — full width below the two columns so it doesn't stretch the
            left column and knock the right column's fields out of alignment. */}
        {agenda.length > 0 && (
          <div className="rounded-md border border-white/10 bg-white/[0.03] p-3 max-h-40 overflow-y-auto">
            <p className="text-[10px] text-white/40 mb-1.5 uppercase tracking-wide">Agenda</p>
            <ul className="space-y-1">
              {agenda.map((item, i) => (
                <li key={i} className="text-xs text-white/70 flex gap-1.5">
                  <span className="text-violet-400">•</span>{item}
                </li>
              ))}
            </ul>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} className="border-white/10 text-white/70">Cancel</Button>
          <HoverTip tip="Save changes and notify participants">
            <Button onClick={handleSave} disabled={loading}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Save Changes
            </Button>
          </HoverTip>
        </DialogFooter>
      </DialogContent>

      <MeetingConflictDialog
        conflicts={conflicts}
        onCancel={() => setConflicts(null)}
        onConfirm={doSave}
        loading={loading}
      />
    </Dialog>
  );
};

// ── Shared: multi-assignee picker (used by Add + Detail dialogs) ────────────
// `onViewAll` + `viewingAll` are optional: when provided, the picker shows a
// "View all members" toggle whose panel is rendered by the parent dialog to
// the side (so it isn't cramped inside this narrow field). Without them the
// picker is just the search box + chips.
export const AssigneePicker = ({ assignees, onChange, onViewAll, viewingAll = false }) => {
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
      {/* {onViewAll && (
        <div className="flex items-center justify-end -mb-1">
          <button
            type="button"
            onClick={onViewAll}
            className="flex items-center gap-1 text-[11px] text-violet-300 hover:text-violet-200"
          >
            <Users className="h-3 w-3" />
            View all members
            <ChevronRight className={`h-3 w-3 transition-transform ${viewingAll ? 'rotate-90' : ''}`} />
          </button>
        </div>
      )} */}
      {assignees.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {assignees.map(a => {
            const key = `${a.user_type || 'cu'}-${a.id}`;
            return (
              <span key={key} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-violet-500/20 border border-violet-500/30 text-violet-200 text-xs">
                {a.full_name}
                <HoverTip tip="Remove this assignee">
                  <button onClick={() => remove(key)} className="text-violet-300/60 hover:text-white leading-none">✕</button>
                </HoverTip>
              </span>
            );
          })}
        </div>
      )}
      
     <div className="flex items-center gap-2">
        <div className="relative flex-1">
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

        {onViewAll && (
          <button
            type="button"
            onClick={onViewAll}
            className="flex items-center gap-1 text-[11px] text-violet-300 hover:text-violet-200 whitespace-nowrap flex-shrink-0"
          >
            <Users className="h-3 w-3" />
            View all
            <ChevronRight className={`h-3 w-3 transition-transform ${viewingAll ? 'rotate-90' : ''}`} />
          </button>
        )}
      </div>
    </div>
  );
};

// ── Add task dialog ─────────────────────────────────────────────────────────
// `prefill` (optional) seeds the form when opened from "Create with AI":
// { title, description, priority, due_date, assignees }. Absent for the
// normal blank Add-Task flow.
export const AddTaskDialog = ({ open, onClose, onCreated, parentTask, prefill = null, onEditAiPrompt = null, onCreateWithAI = null }) => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ title: '', description: '', priority: 'medium', due_date: '' });
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const [assignees, setAssignees] = useState([]);
  const [generatingDesc, setGeneratingDesc] = useState(false);
  // When adding a subtask, allow its due date to be after the parent's.
  const [allowAfterParent, setAllowAfterParent] = useState(false);

  // On every open, (re)initialise the form from the AI draft if there is one,
  // or to a clean blank state if there isn't. The dialog is not unmounted when
  // closed (only `open` flips), so its local state persists between opens —
  // without this reset, assignees from a previous AI draft that was cancelled
  // would linger and get merged into the next one.
  useEffect(() => {
    if (!open) return;
    if (prefill) {
      setForm({
        title: prefill.title || '',
        description: prefill.description || '',
        priority: prefill.priority || 'medium',
        due_date: prefill.due_date || '',
      });
      setAssignees(Array.isArray(prefill.assignees) ? prefill.assignees : []);
    } else {
      setForm({ title: '', description: '', priority: 'medium', due_date: '' });
      setAssignees([]);
    }
    setAllowAfterParent(false);
    setShowAllMembers(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, prefill]);
  // "View all members" side panel (rendered at dialog level so it sits beside
  // the form, not cramped inside the Assign-To field).
  const [showAllMembers, setShowAllMembers] = useState(false);
  const aKey = (u) => `${u?.user_type || 'company_user'}-${u?.id}`;
  const toggleAssignee = (u) => {
    setAssignees(prev =>
      prev.some(a => aKey(a) === aKey(u))
        ? prev.filter(a => aKey(a) !== aKey(u))
        : [...prev, u]
    );
  };

  const reset = () => {
    setForm({ title: '', description: '', priority: 'medium', due_date: '' });
    setAssignees([]);
    setShowAllMembers(false);
  };

  const handleGenerateDescription = async () => {
    // Only the task name is required — the AI can draft a description from
    // the title alone. Any notes already in the description box are passed
    // along as extra context, but they're optional.
    if (!form.title.trim()) {
      toast({ title: 'Add a task name first', description: 'Enter the task name, then generate — the AI will draft the description from it.', variant: 'destructive' });
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

  // Past-date confirmation is shown via the shared ConfirmDialog (not the native
  // browser alert). When a past due date is detected, we stash the intent and
  // open the dialog; confirming runs the actual create.
  const [pastDateConfirm, setPastDateConfirm] = useState(false);

  const handleSubmit = async () => {
    if (!form.title) { toast({ title: 'Title is required', variant: 'destructive' }); return; }
    // A subtask can't be due after its parent task — unless the user ticked
    // "Allow due date after parent".
    if (!allowAfterParent && parentTask?.due_date && form.due_date && form.due_date > parentTask.due_date) {
      toast({ title: 'Due date too late', description: `Subtask can't be due after the parent task (${parentTask.due_date}). Tick "Allow due date after parent" to override.`, variant: 'destructive' });
      return;
    }
    // Warn (but allow) when the due date is in the past. due_date is a plain
    // YYYY-MM-DD string, so comparing against today's local date string works
    // without timezone drift.
    if (form.due_date && form.due_date < todayStr()) {
      setPastDateConfirm(true);
      return;
    }
    await doCreate();
  };

  const doCreate = async () => {
    setLoading(true);
    try {
      await execMeetingService.createTask({
        ...form,
        parent_task_id: parentTask?.id || null,
        allow_after_parent: allowAfterParent,
        assignees: assignees.map(a => ({ id: a.id, user_type: a.user_type || 'company_user' })),
      });
      toast({ title: parentTask ? 'Subtask created!' : 'Task created!' });
      setPastDateConfirm(false);
      onCreated(); onClose(); reset();
    } catch (err) {
      const dup = err?.status === 409 || /already exists/i.test(err?.message || '');
      toast({
        title: dup ? 'Duplicate title' : 'Failed to create task',
        description: err.message,
        variant: 'destructive',
      });
    } finally { setLoading(false); }
  };

  return (
    <>
    <Dialog open={open} onOpenChange={v => { if (!v) reset(); onClose(); }}>
      <DialogContent className={`bg-[#0d0b1f] border-white/10 text-white transition-[max-width] ${showAllMembers ? 'max-w-3xl' : 'max-w-lg'}`}>
        <div className="flex gap-4 items-stretch">
          <div className="min-w-0 flex-1">
        <DialogHeader>
          {/* Title + AI button after it (clear of the dialog's close ✕ via
              pr-8). AI-opened → "Edit AI prompt"; manual → "Create with AI". */}
          <div className="flex items-center gap-3 flex-wrap pr-8">
            <DialogTitle>{parentTask ? `Add Subtask to "${parentTask.title}"` : 'Add Task'}</DialogTitle>
            {onEditAiPrompt ? (
              <HoverTip tip="Edit the AI prompt and generate a new draft">
                <button
                  type="button"
                  onClick={onEditAiPrompt}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-violet-400/40 bg-violet-400/10 text-violet-200 text-xs font-medium hover:bg-violet-400/20 hover:text-violet-100 transition"
                >
                  <Wand2 className="h-3.5 w-3.5" />
                  Edit AI prompt
                </button>
              </HoverTip>
            ) : onCreateWithAI ? (
              <HoverTip tip="Describe this task in plain language and let AI draft it">
                <button
                  type="button"
                  onClick={onCreateWithAI}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-violet-400/40 bg-violet-400/10 text-violet-200 text-xs font-medium hover:bg-violet-400/20 hover:text-violet-100 transition"
                >
                  <Wand2 className="h-3.5 w-3.5" />
                  Create with AI
                </button>
              </HoverTip>
            ) : null}
          </div>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1">
            <Label>Title *</Label>
            <Input value={form.title} onChange={e => set('title', e.target.value)} disabled={loading} placeholder="Review Q3 report" className="bg-white/5 border-white/10 text-white disabled:opacity-60 disabled:cursor-not-allowed" />
          </div>
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <Label>Description</Label>
              <HoverTip tip="Draft a description from the task name (add little description for more context)">
                <button
                  type="button"
                  onClick={handleGenerateDescription}
                  disabled={generatingDesc}
                  className="flex items-center gap-1 text-[11px] text-violet-300 hover:text-violet-200 disabled:opacity-50"
                >
                  {generatingDesc ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
                  Generate with AI
                </button>
              </HoverTip>
            </div>
            <Textarea value={form.description} onChange={e => set('description', e.target.value)} disabled={loading} placeholder="Optional — leave blank and Generate with AI drafts it from the task name, or jot a few points for more context" className="bg-white/5 border-white/10 text-white disabled:opacity-60 disabled:cursor-not-allowed" rows={3} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Priority</Label>
              <Select value={form.priority} disabled={loading} onValueChange={v => set('priority', v)}>
                <SelectTrigger className="bg-white/5 border-white/10 text-white"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {['low','medium','high'].map(p => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Due Date</Label>
              <DateOnlyPicker value={form.due_date} onChange={v => set('due_date', v)} disabled={loading} />
              {parentTask?.due_date && (
                <>
                  <label className="flex items-center gap-2 mt-1.5 cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={allowAfterParent}
                      onChange={e => setAllowAfterParent(e.target.checked)}
                      disabled={loading}
                      className="h-3.5 w-3.5 rounded border-white/20 bg-white/5 accent-violet-500 cursor-pointer disabled:cursor-not-allowed"
                    />
                    <span className="text-white/60 text-[11px]">Allow due date after parent</span>
                  </label>
                  <p className="text-white/30 text-[10px]">
                    {allowAfterParent
                      ? `Any date allowed (parent is due ${parentTask.due_date}).`
                      : `Must be on or before parent's due date: ${parentTask.due_date}`}
                  </p>
                </>
              )}
            </div>
          </div>
         <div className="space-y-1">
  <Label>Assign To</Label>
  <AssigneePicker
    assignees={assignees}
    onChange={setAssignees}
    onViewAll={() => setShowAllMembers(v => !v)}
    viewingAll={showAllMembers}
  />
</div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} className="border-white/10 text-white/70">Cancel</Button>
          <HoverTip tip={parentTask ? 'Create this subtask' : 'Create this task'}>
            <Button onClick={handleSubmit} disabled={loading}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}{parentTask ? 'Add Subtask' : 'Add Task'}
            </Button>
          </HoverTip>
        </DialogFooter>
          </div>

          {/* Side panel — all company members, attached to the right. */}
          <AllMembersPanel
            open={showAllMembers}
            onClose={() => setShowAllMembers(false)}
            selected={assignees}
            onToggle={toggleAssignee}
          />
        </div>
      </DialogContent>
    </Dialog>

    <ConfirmDialog
      open={pastDateConfirm}
      onOpenChange={setPastDateConfirm}
      title="Add task with a past date?"
      description={`The due date (${form.due_date}) is in the past. Do you still want to add this task with a previous date?`}
      confirmLabel="Add anyway"
      cancelLabel="Cancel"
      onConfirm={doCreate}
      loading={loading}
    />
    </>
  );
};

// ── Task edit dialog (opens when Edit button clicked) ───────────────────────
export const TaskEditDialog = ({ task, onClose, onUpdated }) => {
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);
  const [generatingDesc, setGeneratingDesc] = useState(false);
  const [form, setForm] = useState(null);
  const [assignees, setAssignees] = useState([]);
  // "View all members" side panel (rendered at dialog level, beside the form).
  const [showAllMembers, setShowAllMembers] = useState(false);
  // Must live above the early `return null` below — a hook after a conditional
  // return breaks the rules-of-hooks ("rendered more hooks…") error.
  const [pastDateConfirm, setPastDateConfirm] = useState(false);
  const aKey = (u) => `${u?.user_type || 'company_user'}-${u?.id}`;
  const toggleAssignee = (u) => {
    setAssignees(prev =>
      prev.some(a => aKey(a) === aKey(u))
        ? prev.filter(a => aKey(a) !== aKey(u))
        : [...prev, u]
    );
  };

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
      setShowAllMembers(false);
    }
  }, [task]);

  if (!task || !form) return null;
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const handleGenerateDescription = async () => {
    // Only the task name is required — the AI can draft a description from
    // the title alone. Any notes already in the description box are passed
    // along as extra context, but they're optional.
    if (!form.title.trim()) {
      toast({ title: 'Add a task name first', description: 'Enter the task name, then generate — the AI will draft the description from it.', variant: 'destructive' });
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
    // Warn (but allow) when the due date is newly set to a past date. Skip when
    // the date is unchanged from the original, so editing other fields on an
    // already-past task doesn't nag.
    if (form.due_date && form.due_date < todayStr() && form.due_date !== (task.due_date || '')) {
      setPastDateConfirm(true);
      return;
    }
    await doSave();
  };

  const doSave = async () => {
    setSaving(true);
    try {
      await execMeetingService.updateTask(task.id, {
        ...form,
        assignees: assignees.map(a => ({ id: a.id, user_type: a.user_type || 'company_user' })),
      });
      toast({ title: 'Task updated!' });
      setPastDateConfirm(false);
      onUpdated();
      onClose();
    } catch (err) {
      toast({ title: 'Failed to save', description: err.message, variant: 'destructive' });
    } finally { setSaving(false); }
  };

  return (
    <>
    <Dialog open={!!task} onOpenChange={v => { if (!v) onClose(); }}>
      <DialogContent className={`bg-[#0d0b1f] border-white/10 text-white transition-[max-width] ${showAllMembers ? 'max-w-3xl' : 'max-w-lg'}`}>
        <div className="flex gap-4 items-stretch">
          <div className="min-w-0 flex-1">
        <DialogHeader>
          <DialogTitle>Edit Task</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1">
            <Label>Title *</Label>
            <Input value={form.title} onChange={e => set('title', e.target.value)} disabled={saving} className="bg-white/5 border-white/10 text-white disabled:opacity-60 disabled:cursor-not-allowed" />
          </div>
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <Label>Description</Label>
              <HoverTip tip="Draft a description from the task name (add little description for more context)">
                <button
                  type="button"
                  onClick={handleGenerateDescription}
                  disabled={generatingDesc || saving}
                  className="flex items-center gap-1 text-[11px] text-violet-300 hover:text-violet-200 disabled:opacity-50"
                >
                  {generatingDesc ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
                  Generate with AI
                </button>
              </HoverTip>
            </div>
            <Textarea value={form.description} onChange={e => set('description', e.target.value)} disabled={saving} className="bg-white/5 border-white/10 text-white disabled:opacity-60 disabled:cursor-not-allowed" rows={3} />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1">
              <Label>Status</Label>
              <Select value={form.status} disabled={saving} onValueChange={v => set('status', v)}>
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
              <Select value={form.priority} disabled={saving} onValueChange={v => set('priority', v)}>
                <SelectTrigger className="bg-white/5 border-white/10 text-white"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {['low','medium','high'].map(p => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Due Date</Label>
              <DateOnlyPicker value={form.due_date} onChange={v => set('due_date', v)} disabled={saving} />
            </div>
          </div>
          <div className="space-y-1">
            <Label>Assigned To</Label>
            <AssigneePicker
              assignees={assignees}
              onChange={setAssignees}
              onViewAll={() => setShowAllMembers(v => !v)}
              viewingAll={showAllMembers}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} className="border-white/10 text-white/70">Cancel</Button>
          <HoverTip tip="Save changes to this task">
            <Button onClick={handleSave} disabled={saving}>
              {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}Save
            </Button>
          </HoverTip>
        </DialogFooter>
          </div>

          {/* Side panel — all company members, attached to the right. */}
          <AllMembersPanel
            open={showAllMembers}
            onClose={() => setShowAllMembers(false)}
            selected={assignees}
            onToggle={toggleAssignee}
          />
        </div>
      </DialogContent>
    </Dialog>

    <ConfirmDialog
      open={pastDateConfirm}
      onOpenChange={setPastDateConfirm}
      title="Save task with a past date?"
      description={`The due date (${form.due_date}) is in the past. Do you still want to save this task with a previous date?`}
      confirmLabel="Save anyway"
      cancelLabel="Cancel"
      onConfirm={doSave}
      loading={saving}
    />
    </>
  );
};
