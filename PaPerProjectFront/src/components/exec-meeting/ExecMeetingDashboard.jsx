import React, { useState, useEffect } from 'react';
import { format } from 'date-fns';
import {
  Card, CardContent, CardHeader, CardTitle, CardDescription,
} from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  Loader2, LayoutDashboard, CalendarClock, ListChecks, CalendarDays,
  FileText, Bell, Plus, Menu, Clock, AlertTriangle, CheckCircle2,
  RefreshCw, Trash2, MoreHorizontal, ChevronRight, Calendar as CalendarIcon,
  Download, X, Sparkles, Pencil,
} from 'lucide-react';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import ErrorBoundary from '@/components/common/ErrorBoundary';
import execMeetingService from '@/services/execMeetingService';

// ── Markdown → HTML renderer (violet theme, matches this dashboard) ─────────
function markdownToHtml(md) {
  if (!md || typeof md !== 'string') return '';
  const escape = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const inline = (s) => {
    let out = escape(s);
    out = out.replace(/`([^`]+)`/g, '<code class="px-1.5 py-0.5 rounded bg-white/10 text-violet-200 text-[0.85em] font-mono">$1</code>');
    out = out.replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold text-violet-200">$1</strong>');
    out = out.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em class="italic text-white/85">$2</em>');
    return out;
  };
  const getIndent = (line) => {
    const m = line.match(/^(\s*)(?:[-*•]|\d+\.)\s+/);
    if (!m) return -1;
    return Math.floor(m[1].length / 2);
  };
  const lines = md.replace(/\r\n/g, '\n').split('\n');
  const out = [];
  let listDepth = -1;
  const closeLists = (target) => { while (listDepth > target) { out.push('</ul>'); listDepth--; } };
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const t = line.trim();
    if (t.startsWith('|') && t.endsWith('|')) {
      closeLists(-1);
      const rows = [];
      let j = i;
      while (j < lines.length && lines[j].trim().startsWith('|')) {
        const cells = lines[j].trim().split('|').map((c) => c.trim()).filter(Boolean);
        if (cells.length && cells.every((c) => /^[-:\s]+$/.test(c))) { j++; continue; }
        rows.push(cells);
        j++;
      }
      i = j;
      if (rows.length) {
        out.push('<div class="my-4 overflow-x-auto rounded-lg border border-white/10">');
        out.push('<table class="w-full text-sm"><thead><tr class="bg-violet-500/10">');
        rows[0].forEach((c) => out.push(`<th class="px-3 py-2 text-left font-semibold text-violet-300">${inline(c)}</th>`));
        out.push('</tr></thead><tbody>');
        rows.slice(1).forEach((r, idx) => {
          out.push(`<tr class="${idx % 2 === 0 ? 'bg-white/[0.02]' : ''} hover:bg-white/[0.04]">`);
          r.forEach((c) => out.push(`<td class="px-3 py-2 border-t border-white/5 text-white/85">${inline(c)}</td>`));
          out.push('</tr>');
        });
        out.push('</tbody></table></div>');
      }
      continue;
    }
    if (/^---+$/.test(t)) { closeLists(-1); out.push('<hr class="my-5 border-white/20" />'); i++; continue; }
    if (/^#### /.test(t)) { closeLists(-1); out.push(`<h4 class="text-sm font-semibold mt-3 mb-1.5 text-violet-100/90">${inline(t.slice(5))}</h4>`); i++; continue; }
    if (/^### /.test(t))  { closeLists(-1); out.push(`<h3 class="text-base font-bold mt-5 mb-2 text-violet-200">${inline(t.slice(4))}</h3>`); i++; continue; }
    if (/^## /.test(t))   { closeLists(-1); out.push(`<h2 class="text-lg font-bold mt-6 mb-2.5 text-violet-300 border-b border-violet-500/30 pb-1.5">${inline(t.slice(3))}</h2>`); i++; continue; }
    if (/^# /.test(t))    { closeLists(-1); out.push(`<h1 class="text-2xl font-bold mt-2 mb-4 text-white">${inline(t.slice(2))}</h1>`); i++; continue; }
    const indent = getIndent(line);
    if (indent >= 0) {
      const content = t.replace(/^[\s]*(?:[-*•]|\d+\.)\s+/, '');
      if (indent > listDepth) {
        while (listDepth < indent) {
          const isTop = listDepth === -1;
          out.push(`<ul class="${isTop ? 'pl-4 my-2 space-y-1.5' : 'pl-5 mt-1 mb-1 space-y-1 border-l border-white/[0.06]'}">`);
          listDepth++;
        }
      } else if (indent < listDepth) {
        closeLists(indent);
      }
      const bullet = indent === 0 ? '•' : '›';
      const color  = indent === 0 ? 'text-violet-400' : 'text-white/30';
      const textColor = indent === 0 ? 'text-white/90' : 'text-white/70';
      out.push(
        `<li class="text-sm leading-relaxed ${textColor} flex gap-2 ${indent === 0 ? 'pt-1' : ''}">` +
        `<span class="${color} shrink-0 mt-0.5">${bullet}</span><span>${inline(content)}</span></li>`,
      );
      i++; continue;
    }
    if (t === '' && listDepth >= 0) {
      let k = i + 1;
      while (k < lines.length && lines[k].trim() === '') k++;
      if (k >= lines.length || getIndent(lines[k]) < 0) closeLists(-1);
      i++; continue;
    }
    if (t === '') { i++; continue; }
    closeLists(-1);
    out.push(`<p class="text-sm leading-relaxed text-white/85 my-2.5">${inline(t)}</p>`);
    i++;
  }
  closeLists(-1);
  return out.join('\n');
}

const TAB_ITEMS = [
  { value: 'overview',      label: 'Overview',      icon: LayoutDashboard },
  { value: 'meetings',      label: 'Meetings',       icon: CalendarClock },
  { value: 'tasks',         label: 'Tasks',          icon: ListChecks },
  { value: 'calendar',      label: 'Calendar',       icon: CalendarDays },
  { value: 'documents',     label: 'Documents',      icon: FileText },
  { value: 'notifications', label: 'Notifications',  icon: Bell },
];

// ── Hour / minute options ───────────────────────────────────────────────────
const HOURS = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0'));
const MINUTES = ['00', '15', '30', '45'];

// ── DateTimePicker component ────────────────────────────────────────────────
const DateTimePicker = ({ value, onChange, allowPast = false }) => {
  const [calOpen, setCalOpen] = useState(false);

  // Parse ISO string → { date, hour, minute }
  const parsed = value ? new Date(value) : null;
  const selectedDate = parsed && !isNaN(parsed) ? parsed : null;
  const selectedHour  = selectedDate ? String(selectedDate.getHours()).padStart(2, '0') : '09';
  const selectedMin   = selectedDate
    ? (['00','15','30','45'].includes(String(selectedDate.getMinutes()).padStart(2,'0'))
        ? String(selectedDate.getMinutes()).padStart(2,'0')
        : '00')
    : '00';

  const buildISO = (date, hour, minute) => {
    if (!date) return '';
    const d = new Date(date);
    d.setHours(parseInt(hour, 10), parseInt(minute, 10), 0, 0);
    // return local ISO-like string backend can parse
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:00`;
  };

  const handleDateSelect = (date) => {
    setCalOpen(false);
    onChange(buildISO(date, selectedHour, selectedMin));
  };

  const handleHourChange = (h) => onChange(buildISO(selectedDate, h, selectedMin));
  const handleMinChange  = (m) => onChange(buildISO(selectedDate, selectedHour, m));

  return (
    <div className="flex gap-2">
      {/* Calendar popover */}
      <Popover open={calOpen} onOpenChange={setCalOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            className="flex-1 justify-start text-left font-normal bg-white/5 border-white/10 text-white hover:bg-white/10 hover:text-white"
          >
            <CalendarIcon className="mr-2 h-4 w-4 text-violet-400 flex-shrink-0" />
            {selectedDate ? format(selectedDate, 'dd MMM yyyy') : <span className="text-white/40">Pick a date</span>}
          </Button>
        </PopoverTrigger>
        <PopoverContent
          className="w-auto p-0 bg-[#0d0b1f] border-white/10"
          align="start"
          style={{ zIndex: 9999 }}
        >
          <Calendar
            mode="single"
            selected={selectedDate}
            onSelect={handleDateSelect}
            fromDate={allowPast ? undefined : new Date()}
            initialFocus
            classNames={{
              months: 'flex flex-col',
              month: 'space-y-2',
              caption: 'flex justify-center pt-1 relative items-center text-white',
              caption_label: 'text-sm font-medium text-white',
              nav: 'space-x-1 flex items-center',
              nav_button: 'h-7 w-7 bg-white/10 border border-white/10 rounded p-0 hover:bg-white/20 text-white',
              nav_button_previous: 'absolute left-1',
              nav_button_next: 'absolute right-1',
              table: 'w-full border-collapse',
              head_row: 'flex',
              head_cell: 'text-white/40 rounded-md w-9 font-normal text-[0.8rem]',
              row: 'flex w-full mt-1',
              cell: 'h-9 w-9 text-center text-sm p-0 relative focus-within:relative focus-within:z-20',
              day: 'h-9 w-9 p-0 font-normal text-white/70 rounded hover:bg-violet-600/40 hover:text-white transition-colors',
              day_selected: 'bg-violet-600 text-white hover:bg-violet-600 hover:text-white',
              day_today: 'bg-white/10 text-white',
              day_outside: 'text-white/20',
              day_disabled: 'text-white/20 cursor-not-allowed',
            }}
          />
        </PopoverContent>
      </Popover>

      {/* Hour select */}
      <Select value={selectedHour} onValueChange={handleHourChange}>
        <SelectTrigger className="w-20 bg-white/5 border-white/10 text-white">
          <SelectValue />
        </SelectTrigger>
        <SelectContent className="max-h-48 overflow-y-auto">
          {HOURS.map(h => <SelectItem key={h} value={h}>{h}:00</SelectItem>)}
        </SelectContent>
      </Select>

      {/* Minute select */}
      <Select value={selectedMin} onValueChange={handleMinChange}>
        <SelectTrigger className="w-20 bg-white/5 border-white/10 text-white">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {MINUTES.map(m => <SelectItem key={m} value={m}>:{m}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  );
};

const STAT_PALETTE = {
  violet: { color: '#a78bfa', bg: 'rgba(167,139,250,0.2)', border: 'rgba(167,139,250,0.2)', from: 'rgba(167,139,250,0.2)', to: 'rgba(147,51,234,0.1)' },
  emerald:{ color: '#34d399', bg: 'rgba(52,211,153,0.2)',  border: 'rgba(52,211,153,0.2)',  from: 'rgba(52,211,153,0.2)',  to: 'rgba(22,163,74,0.1)' },
  amber:  { color: '#fbbf24', bg: 'rgba(251,191,36,0.2)',  border: 'rgba(251,191,36,0.2)',  from: 'rgba(251,191,36,0.15)', to: 'rgba(245,158,11,0.08)' },
  sky:    { color: '#60a5fa', bg: 'rgba(96,165,250,0.2)',  border: 'rgba(96,165,250,0.2)',  from: 'rgba(96,165,250,0.2)',  to: 'rgba(34,211,238,0.1)' },
  rose:   { color: '#fb7185', bg: 'rgba(251,113,133,0.2)', border: 'rgba(251,113,133,0.2)', from: 'rgba(251,113,133,0.18)', to: 'rgba(225,29,72,0.08)' },
};

const StatCard = ({ label, value, icon: Icon, palette }) => {
  const p = STAT_PALETTE[palette] || STAT_PALETTE.violet;
  return (
    <div
      className="rounded-xl p-4 flex items-center gap-4"
      style={{
        background: `linear-gradient(135deg, ${p.from}, ${p.to})`,
        border: `1px solid ${p.border}`,
      }}
    >
      <div className="rounded-lg p-2.5 flex-shrink-0" style={{ background: p.bg }}>
        <Icon className="h-5 w-5" style={{ color: p.color }} />
      </div>
      <div>
        <p className="text-2xl font-bold text-white">{value ?? '—'}</p>
        <p className="text-xs text-white/60">{label}</p>
      </div>
    </div>
  );
};

const priorityBadge = (priority) => {
  const map = {
    critical: 'bg-red-500/20 text-red-400 border-red-500/30',
    high:     'bg-orange-500/20 text-orange-400 border-orange-500/30',
    medium:   'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    low:      'bg-green-500/20 text-green-400 border-green-500/30',
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs border ${map[priority] || map.medium}`}>
      {priority}
    </span>
  );
};

const statusBadge = (status) => {
  const map = {
    scheduled:   'bg-blue-500/20 text-blue-400 border-blue-500/30',
    in_progress: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
    completed:   'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
    cancelled:   'bg-red-500/20 text-red-400 border-red-500/30',
    todo:        'bg-slate-500/20 text-slate-400 border-slate-500/30',
    review:      'bg-purple-500/20 text-purple-400 border-purple-500/30',
    done:        'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs border ${map[status] || map.todo}`}>
      {status?.replace('_', ' ')}
    </span>
  );
};

const CARD_STYLE = {
  background: 'rgba(0,0,0,0.2)',
  border: '1px solid rgba(255,255,255,0.1)',
  backdropFilter: 'blur(4px)',
};

const ROW_STYLE = {
  borderBottom: '1px solid rgba(255,255,255,0.05)',
};

const EmptyState = ({ icon: Icon, label }) => (
  <div className="flex flex-col items-center justify-center py-16 gap-3 text-white/40">
    <div className="rounded-xl p-4 bg-white/5">
      <Icon className="h-8 w-8" />
    </div>
    <p className="text-sm">{label}</p>
  </div>
);

// ── Date-only picker (for tasks) ────────────────────────────────────────────
const DateOnlyPicker = ({ value, onChange }) => {
  const [open, setOpen] = useState(false);
  const selected = value ? new Date(value + 'T00:00:00') : null;

  const handleSelect = (date) => {
    setOpen(false);
    if (!date) { onChange(''); return; }
    const pad = n => String(n).padStart(2, '0');
    onChange(`${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}`);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          className="w-full justify-start text-left font-normal bg-white/5 border-white/10 text-white hover:bg-white/10 hover:text-white"
        >
          <CalendarIcon className="mr-2 h-4 w-4 text-violet-400 flex-shrink-0" />
          {selected && !isNaN(selected)
            ? format(selected, 'dd MMM yyyy')
            : <span className="text-white/40">Pick a date</span>}
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="w-auto p-0 bg-[#0d0b1f] border-white/10"
        align="start"
        style={{ zIndex: 9999 }}
      >
        <Calendar
          mode="single"
          selected={selected && !isNaN(selected) ? selected : undefined}
          onSelect={handleSelect}
          initialFocus
          classNames={{
            months: 'flex flex-col',
            month: 'space-y-2',
            caption: 'flex justify-center pt-1 relative items-center text-white',
            caption_label: 'text-sm font-medium text-white',
            nav: 'space-x-1 flex items-center',
            nav_button: 'h-7 w-7 bg-white/10 border border-white/10 rounded p-0 hover:bg-white/20 text-white',
            nav_button_previous: 'absolute left-1',
            nav_button_next: 'absolute right-1',
            table: 'w-full border-collapse',
            head_row: 'flex',
            head_cell: 'text-white/40 rounded-md w-9 font-normal text-[0.8rem]',
            row: 'flex w-full mt-1',
            cell: 'h-9 w-9 text-center text-sm p-0 relative focus-within:relative focus-within:z-20',
            day: 'h-9 w-9 p-0 font-normal text-white/70 rounded hover:bg-violet-600/40 hover:text-white transition-colors',
            day_selected: 'bg-violet-600 text-white hover:bg-violet-600 hover:text-white',
            day_today: 'bg-white/10 text-white',
            day_outside: 'text-white/20',
            day_disabled: 'text-white/20 cursor-not-allowed',
          }}
        />
      </PopoverContent>
    </Popover>
  );
};

// ── Schedule meeting dialog ─────────────────────────────────────────────────
const ScheduleMeetingDialog = ({ open, onClose, onCreated }) => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    title: '', description: '', scheduled_at: '', duration_minutes: '60', meeting_link: '',
  });
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
              <Label>Description</Label>
              <Textarea value={form.description} onChange={e => set('description', e.target.value)} placeholder="Meeting agenda..." rows={3}
                className="bg-white/5 border-white/10 text-white [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]" />
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

const VALID_MEETING_LINK_PATTERN = /^https?:\/\/(meet\.google\.com|zoom\.us|[\w-]+\.zoom\.us|us\d+web\.zoom\.us|teams\.microsoft\.com|[\w-]+\.jitsi\.meet|meet\.jit\.si|webex\.com|[\w-]+\.webex\.com|whereby\.com|[\w-]+\.whereby\.com|bluejeans\.com|gotomeet\.me|goto\.meeting)[\w\-/?=&#%+.]*$/i;

const validateMeetingLink = (url) => {
  if (!url || !url.trim()) return true; // blank is OK (auto-generated)
  return VALID_MEETING_LINK_PATTERN.test(url.trim());
};

// ── Edit meeting dialog ─────────────────────────────────────────────────────
const MeetingEditDialog = ({ meeting, open, onClose, onUpdated }) => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    title: '', description: '', scheduled_at: '', duration_minutes: '60',
    meeting_link: '', status: 'scheduled',
  });
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
    }
  }, [meeting]);

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
              <Label>Description</Label>
              <Textarea value={form.description} onChange={e => set('description', e.target.value)}
                rows={3} className="bg-white/5 border-white/10 text-white [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]" />
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
const AssigneePicker = ({ assignees, onChange }) => {
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
const AddTaskDialog = ({ open, onClose, onCreated }) => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ title: '', description: '', priority: 'medium', due_date: '' });
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const [assignees, setAssignees] = useState([]);

  const reset = () => {
    setForm({ title: '', description: '', priority: 'medium', due_date: '' });
    setAssignees([]);
  };

  const handleSubmit = async () => {
    if (!form.title) { toast({ title: 'Title is required', variant: 'destructive' }); return; }
    setLoading(true);
    try {
      await execMeetingService.createTask({
        ...form,
        assignees: assignees.map(a => ({ id: a.id, user_type: a.user_type || 'company_user' })),
      });
      toast({ title: 'Task created!' });
      onCreated(); onClose(); reset();
    } catch (err) {
      toast({ title: 'Failed to create task', description: err.message, variant: 'destructive' });
    } finally { setLoading(false); }
  };

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) reset(); onClose(); }}>
      <DialogContent className="max-w-lg bg-[#0d0b1f] border-white/10 text-white">
        <DialogHeader>
          <DialogTitle>Add Task</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1">
            <Label>Title *</Label>
            <Input value={form.title} onChange={e => set('title', e.target.value)} placeholder="Review Q3 report" className="bg-white/5 border-white/10 text-white" />
          </div>
          <div className="space-y-1">
            <Label>Description</Label>
            <Textarea value={form.description} onChange={e => set('description', e.target.value)} className="bg-white/5 border-white/10 text-white" rows={3} />
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
            {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}Add Task
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

// ── Task edit dialog (opens when Edit button clicked) ───────────────────────
const TaskEditDialog = ({ task, onClose, onUpdated }) => {
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);
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
            <Label>Description</Label>
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

// Display ISO datetime string as UTC — avoids browser timezone shifting the date
const fmtUtc = (isoStr) => {
  if (!isoStr) return '—';
  const [datePart, timePart] = isoStr.replace('Z', '').replace('+00:00', '').split('T');
  if (!datePart) return '—';
  const [y, mo, d] = datePart.split('-');
  if (!timePart) return `${mo}/${d}/${y}`;
  const [h, m] = timePart.split(':');
  const hour = parseInt(h, 10);
  const ampm = hour >= 12 ? 'PM' : 'AM';
  const h12 = hour % 12 || 12;
  return `${mo}/${d}/${y}, ${h12}:${m} ${ampm}`;
};

// ── Main dashboard ──────────────────────────────────────────────────────────
const ExecMeetingDashboard = () => {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState('overview');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Data state
  const [stats, setStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [meetings, setMeetings] = useState([]);
  const [meetingsLoading, setMeetingsLoading] = useState(false);
  const [tasks, setTasks] = useState([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [notifsLoading, setNotifsLoading] = useState(false);
  const [digest, setDigest] = useState(null);
  const [digestLoading, setDigestLoading] = useState(false);

  // Dialogs
  const [showMeetingDialog, setShowMeetingDialog] = useState(false);
  const [showTaskDialog, setShowTaskDialog] = useState(false);
  const [expandedTaskId, setExpandedTaskId] = useState(null); // inline-expanded task
  const [editingTask, setEditingTask] = useState(null);
  const [editingMeeting, setEditingMeeting] = useState(null);
  const [confirmDeleteTaskId, setConfirmDeleteTaskId] = useState(null);

  // AI Documents
  const [aiDocLoading, setAiDocLoading] = useState(false);
  const [aiDocType, setAiDocType] = useState('agenda');
  const [aiDocInput, setAiDocInput] = useState('');
  const [aiDocMeetingId, setAiDocMeetingId] = useState('');
  const [aiDocTopics, setAiDocTopics] = useState('');
  const [aiDocSummary, setAiDocSummary] = useState('');
  const [savedDocs, setSavedDocs] = useState([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [viewDoc, setViewDoc] = useState(null);

  // Calendar plan
  const [weekPlan, setWeekPlan] = useState(null);
  const [weekPlanLoading, setWeekPlanLoading] = useState(false);
  const [includePastTasks, setIncludePastTasks] = useState(false);
  const [showPastTasksConfirm, setShowPastTasksConfirm] = useState(false);

  // Participants
  const [participantsOpenId, setParticipantsOpenId] = useState(null);
  const [participantsMap, setParticipantsMap] = useState({});  // { [meetingId]: [...] }
  const [userSearchQ, setUserSearchQ] = useState('');
  const [userSearchResults, setUserSearchResults] = useState([]);
  const [userSearchLoading, setUserSearchLoading] = useState(false);
  const [pendingAddMap, setPendingAddMap] = useState({});     // { [meetingId]: userObj | null }
  const [confirmRemoveMap, setConfirmRemoveMap] = useState({}); // { [meetingId]: userId | null }

  // Meeting Notetaker
  const [notesOpenId, setNotesOpenId] = useState(null);
  const [transcriptInput, setTranscriptInput] = useState('');
  const [notesLoading, setNotesLoading] = useState(false);
  const [meetingNotes, setMeetingNotes] = useState({});  // { [meetingId]: notesObj }

  // Task Prioritization
  const [prioritizeLoading, setPrioritizeLoading] = useState(false);
  const [prioritizeResult, setPrioritizeResult] = useState(null);

  useEffect(() => { loadStats(); }, []);

  useEffect(() => {
    if (activeTab === 'meetings' && meetings.length === 0) loadMeetings();
    if (activeTab === 'tasks' && tasks.length === 0) loadTasks();
    if (activeTab === 'notifications') loadNotifications();
    if (activeTab === 'overview' && !digest) loadDigest();
    if (activeTab === 'documents') { loadDocuments(); if (meetings.length === 0) loadMeetings(); }
  }, [activeTab]);

  const loadStats = async () => {
    setStatsLoading(true);
    try {
      const data = await execMeetingService.getStats();
      setStats(data);
    } catch {
      setStats({ upcoming_meetings: 0, total_tasks: 0, pending_action_items: 0, unread_notifications: 0, overdue_tasks: 0 });
    } finally {
      setStatsLoading(false);
    }
  };

  const loadMeetings = async () => {
    setMeetingsLoading(true);
    try {
      const data = await execMeetingService.getMeetings();
      setMeetings(data.meetings || []);
    } catch {
      setMeetings([]);
    } finally {
      setMeetingsLoading(false);
    }
  };

  const loadTasks = async () => {
    setTasksLoading(true);
    try {
      const data = await execMeetingService.getTasks();
      setTasks(data.tasks || []);
    } catch {
      setTasks([]);
    } finally {
      setTasksLoading(false);
    }
  };

  const loadNotifications = async () => {
    setNotifsLoading(true);
    try {
      const data = await execMeetingService.getNotifications();
      setNotifications(data.notifications || []);
    } catch {
      setNotifications([]);
    } finally {
      setNotifsLoading(false);
    }
  };

  const loadDigest = async () => {
    setDigestLoading(true);
    try {
      const data = await execMeetingService.getDailyDigest();
      const d = data.digest || data;
      // only store if it looks like a real digest object, not an error response
      setDigest(d && typeof d === 'object' && !d.status ? d : null);
    } catch {
      setDigest(null);
    } finally {
      setDigestLoading(false);
    }
  };

  const loadDocuments = async () => {
    setDocsLoading(true);
    try {
      const data = await execMeetingService.listDocuments();
      setSavedDocs(data.documents || []);
    } catch {
      setSavedDocs([]);
    } finally {
      setDocsLoading(false);
    }
  };

  const generateAiDoc = async () => {
    if (!aiDocInput.trim() && !aiDocMeetingId) {
      toast({ title: 'Select a meeting or enter a topic first', variant: 'destructive' });
      return;
    }
    setAiDocLoading(true);
    try {
      // If a saved meeting is selected, pull its data to enrich the prompt
      const linkedMeeting = aiDocMeetingId ? meetings.find(m => String(m.id) === String(aiDocMeetingId)) : null;
      const resolvedTitle = linkedMeeting ? linkedMeeting.title : aiDocInput.trim();
      const resolvedAttendees = linkedMeeting?.attendees || [];
      const resolvedDuration = linkedMeeting?.duration_minutes || 60;
      const resolvedTopics = aiDocTopics.trim()
        ? aiDocTopics.split(',').map(t => t.trim()).filter(Boolean)
        : [];

      const payload = {
        action: aiDocType,
        title: resolvedTitle,
        topics: resolvedTopics,
        duration_minutes: resolvedDuration,
        attendees: resolvedAttendees,
      };

      if (linkedMeeting) payload.meeting_id = linkedMeeting.id;
      if (aiDocType === 'minutes') payload.summary = aiDocSummary.trim();
      if (aiDocType === 'briefing') payload.topic = resolvedTitle;

      const res = await execMeetingService.generateDocument(payload);
      toast({ title: 'Document generated and saved!' });
      // Reload list so new doc appears
      loadDocuments();
      // Auto-open viewer
      const linkedMeetingTitle = aiDocMeetingId ? (meetings.find(m => String(m.id) === String(aiDocMeetingId))?.title || aiDocInput) : aiDocInput;
      if (res.document_id) {
        setViewDoc({
          id: res.document_id,
          title: `${aiDocType.charAt(0).toUpperCase() + aiDocType.slice(1)} — ${linkedMeetingTitle}`,
          doc_type: aiDocType,
          content: res.content || '',
          created_at: new Date().toISOString(),
        });
      }
      setAiDocInput('');
      setAiDocTopics('');
      setAiDocSummary('');
      setAiDocMeetingId('');
    } catch (err) {
      toast({ title: 'AI generation failed', description: err.message, variant: 'destructive' });
    } finally {
      setAiDocLoading(false);
    }
  };

  const openParticipants = async (meetingId) => {
    if (participantsOpenId === meetingId) { setParticipantsOpenId(null); setUserSearchQ(''); setUserSearchResults([]); setPendingAddMap(prev => ({ ...prev, [meetingId]: null })); setConfirmRemoveMap(prev => ({ ...prev, [meetingId]: null })); return; }
    setParticipantsOpenId(meetingId);
    setNotesOpenId(null);
    setUserSearchQ(''); setUserSearchResults([]);
    // Always re-fetch to get fresh participant_id values needed for remove
    try {
      const data = await execMeetingService.getParticipants(meetingId);
      setParticipantsMap(prev => ({ ...prev, [meetingId]: data.participants || [] }));
    } catch { setParticipantsMap(prev => ({ ...prev, [meetingId]: [] })); }
  };

  const searchUsers = async (q, meetingId) => {
    setUserSearchQ(q);
    if (q.length < 2) { setUserSearchResults([]); return; }
    setUserSearchLoading(true);
    try {
      const data = await execMeetingService.searchUsers(q);
      const existing = (participantsMap[meetingId] || []).map(p => p.user_id);
      setUserSearchResults((data.users || []).filter(u => !existing.includes(u.id)));
    } catch { setUserSearchResults([]); }
    finally { setUserSearchLoading(false); }
  };

  const addParticipant = async (meetingId, user) => {
    // Optimistic update — show instantly, sync with real IDs in background
    const optimistic = { user_id: user.id, full_name: user.full_name, email: user.email, role: user.role, response: 'pending' };
    setParticipantsMap(prev => ({ ...prev, [meetingId]: [...(prev[meetingId] || []), optimistic] }));
    setUserSearchQ(''); setUserSearchResults([]);
    try {
      await execMeetingService.addParticipant(meetingId, user.id, user.user_type);
      // Reload from backend to replace optimistic entry with real CompanyUser ID (needed for correct DELETE)
      const data = await execMeetingService.getParticipants(meetingId);
      setParticipantsMap(prev => ({ ...prev, [meetingId]: data.participants || [] }));
      toast({ title: `${user.full_name} added`, description: 'An invitation email has been sent to them.' });
    } catch (err) {
      // Roll back optimistic update on failure
      setParticipantsMap(prev => ({ ...prev, [meetingId]: (prev[meetingId] || []).filter(p => p.user_id !== user.id) }));
      toast({ title: 'Failed to add participant', description: err.message, variant: 'destructive' });
    }
  };

  const removeParticipant = async (meetingId, participantId, userId, name) => {
    // Optimistic remove — hide instantly
    setParticipantsMap(prev => ({ ...prev, [meetingId]: (prev[meetingId] || []).filter(p => p.id !== participantId && p.user_id !== userId) }));
    try {
      await execMeetingService.removeParticipant(meetingId, participantId, userId);
      toast({ title: `${name} removed`, description: 'They have been notified by email.' });
    } catch (err) {
      // Roll back on failure
      const data = await execMeetingService.getParticipants(meetingId).catch(() => ({ participants: [] }));
      setParticipantsMap(prev => ({ ...prev, [meetingId]: data.participants || [] }));
      toast({ title: 'Failed to remove', description: err.message, variant: 'destructive' });
    }
  };

  const openNotes = async (meetingId) => {
    if (notesOpenId === meetingId) { setNotesOpenId(null); return; }
    setNotesOpenId(meetingId);
    setParticipantsOpenId(null);
    if (meetingNotes[meetingId]) return;
    try {
      const data = await execMeetingService.getMeetingNotes(meetingId);
      if (data.notes) setMeetingNotes(prev => ({ ...prev, [meetingId]: data.notes }));
    } catch { /* no notes yet */ }
  };

  const submitTranscript = async (meetingId) => {
    if (!transcriptInput.trim()) {
      toast({ title: 'Paste a transcript first', variant: 'destructive' }); return;
    }
    setNotesLoading(true);
    try {
      const data = await execMeetingService.generateNotes(meetingId, { transcript: transcriptInput });
      setMeetingNotes(prev => ({ ...prev, [meetingId]: data.notes }));
      setTranscriptInput('');
      toast({ title: 'Notes generated!', description: 'Summary, decisions and action items extracted.' });
    } catch (err) {
      toast({ title: 'Notetaker failed', description: err.message, variant: 'destructive' });
    } finally {
      setNotesLoading(false);
    }
  };

  const [deletingTaskId, setDeletingTaskId] = useState(null);

  const deleteTask = async (id) => {
    setDeletingTaskId(id);
    try {
      await execMeetingService.deleteTask(id);
      setTasks(prev => prev.filter(t => t.id !== id));
      setExpandedTaskId(null);
      loadStats();
      toast({ title: 'Task deleted', description: 'Assignees have been notified by email.' });
    } catch { toast({ title: 'Failed to delete task', variant: 'destructive' }); }
    finally { setDeletingTaskId(null); }
  };

  const runAiPrioritize = async () => {
    setPrioritizeLoading(true);
    try {
      const data = await execMeetingService.prioritizeTasks();
      setPrioritizeResult(data.tasks || data.prioritized || []);
      if ((data.tasks || data.prioritized || []).length) {
        toast({ title: 'Tasks reprioritized by AI!' });
        loadTasks();
      } else {
        toast({ title: 'No prioritization result returned', variant: 'destructive' });
      }
    } catch (err) {
      toast({ title: 'Prioritization failed', description: err.message, variant: 'destructive' });
    } finally {
      setPrioritizeLoading(false);
    }
  };

  const deleteDoc = async (id) => {
    try {
      await execMeetingService.deleteDocument(id);
      setSavedDocs(prev => prev.filter(d => d.id !== id));
      if (viewDoc?.id === id) setViewDoc(null);
      toast({ title: 'Document deleted' });
    } catch {
      toast({ title: 'Failed to delete document', variant: 'destructive' });
    }
  };

  const downloadDocPdf = async (doc) => {
    try {
      const { default: jsPDF } = await import('jspdf');
      const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
      const pageW = pdf.internal.pageSize.getWidth();
      const pageH = pdf.internal.pageSize.getHeight();
      const margin = 18;
      const contentW = pageW - margin * 2;

      // Header bar
      pdf.setFillColor(109, 40, 217);
      pdf.rect(0, 0, pageW, 12, 'F');

      // Title
      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(18);
      pdf.setTextColor(30, 10, 60);
      const titleLines = pdf.splitTextToSize(doc.title || 'Document', contentW);
      pdf.text(titleLines, margin, 24);
      let y = 24 + titleLines.length * 7;

      // Meta line
      pdf.setFont('helvetica', 'normal');
      pdf.setFontSize(8.5);
      pdf.setTextColor(120, 100, 160);
      const metaDate = doc.created_at ? new Date(doc.created_at).toLocaleString() : '';
      pdf.text(`Generated: ${metaDate}  ·  AI Executive Meeting Assistant`, margin, y);
      y += 5;

      // Divider
      pdf.setDrawColor(109, 40, 217);
      pdf.setLineWidth(0.4);
      pdf.line(margin, y, pageW - margin, y);
      y += 6;

      // Render markdown content line by line
      const lines = (doc.content || '').split('\n');
      for (const raw of lines) {
        const line = raw.trimEnd();

        if (y > pageH - 20) {
          pdf.addPage();
          y = 18;
        }

        if (/^######\s/.test(line)) {
          pdf.setFont('helvetica', 'bold'); pdf.setFontSize(9); pdf.setTextColor(76, 29, 149);
          const wrapped = pdf.splitTextToSize(line.replace(/^######\s/, ''), contentW);
          pdf.text(wrapped, margin, y); y += wrapped.length * 5 + 1;
        } else if (/^#####\s/.test(line)) {
          pdf.setFont('helvetica', 'bold'); pdf.setFontSize(10); pdf.setTextColor(76, 29, 149);
          const wrapped = pdf.splitTextToSize(line.replace(/^#####\s/, ''), contentW);
          pdf.text(wrapped, margin, y); y += wrapped.length * 5.5 + 1;
        } else if (/^####\s/.test(line)) {
          pdf.setFont('helvetica', 'bold'); pdf.setFontSize(11); pdf.setTextColor(76, 29, 149);
          const wrapped = pdf.splitTextToSize(line.replace(/^####\s/, ''), contentW);
          pdf.text(wrapped, margin, y); y += wrapped.length * 6 + 2;
        } else if (/^###\s/.test(line)) {
          pdf.setFont('helvetica', 'bold'); pdf.setFontSize(12); pdf.setTextColor(59, 7, 100);
          const wrapped = pdf.splitTextToSize(line.replace(/^###\s/, ''), contentW);
          pdf.text(wrapped, margin, y); y += wrapped.length * 6.5 + 2;
        } else if (/^##\s/.test(line)) {
          pdf.setFont('helvetica', 'bold'); pdf.setFontSize(14); pdf.setTextColor(45, 27, 105);
          const wrapped = pdf.splitTextToSize(line.replace(/^##\s/, ''), contentW);
          pdf.text(wrapped, margin, y); y += wrapped.length * 7 + 3;
        } else if (/^#\s/.test(line)) {
          pdf.setFont('helvetica', 'bold'); pdf.setFontSize(16); pdf.setTextColor(26, 26, 46);
          const wrapped = pdf.splitTextToSize(line.replace(/^#\s/, ''), contentW);
          pdf.text(wrapped, margin, y); y += wrapped.length * 8 + 4;
        } else if (/^---+$/.test(line.trim())) {
          pdf.setDrawColor(200, 190, 220); pdf.setLineWidth(0.3);
          pdf.line(margin, y, pageW - margin, y); y += 5;
        } else if (/^[-*]\s/.test(line)) {
          pdf.setFont('helvetica', 'normal'); pdf.setFontSize(10); pdf.setTextColor(40, 30, 60);
          const bulletText = line.replace(/^[-*]\s/, '');
          const clean = bulletText.replace(/\*\*(.*?)\*\*/g, '$1').replace(/\*(.*?)\*/g, '$1');
          const wrapped = pdf.splitTextToSize(`• ${clean}`, contentW - 4);
          pdf.text(wrapped, margin + 4, y); y += wrapped.length * 5.5 + 1;
        } else if (line.trim() === '') {
          y += 3;
        } else {
          pdf.setFont('helvetica', 'normal'); pdf.setFontSize(10); pdf.setTextColor(40, 30, 60);
          const clean = line.replace(/\*\*(.*?)\*\*/g, '$1').replace(/\*(.*?)\*/g, '$1').replace(/`(.*?)`/g, '$1');
          const wrapped = pdf.splitTextToSize(clean, contentW);
          pdf.text(wrapped, margin, y); y += wrapped.length * 5.5 + 1;
        }
      }

      // Page numbers
      const totalPages = pdf.internal.getNumberOfPages();
      for (let i = 1; i <= totalPages; i++) {
        pdf.setPage(i);
        pdf.setFontSize(7.5); pdf.setTextColor(160, 140, 190);
        pdf.text(`Page ${i} of ${totalPages}  ·  AI Executive Meeting Assistant`, margin, pageH - 7);
      }

      const filename = (doc.title || 'document').replace(/[^a-z0-9-_\s]/gi, '_').trim().slice(0, 80) || 'document';
      pdf.save(`${filename}.pdf`);
    } catch (err) {
      toast({ title: 'PDF download failed', description: err?.message || 'Please try again.', variant: 'destructive' });
    }
  };

  const markNotifRead = async (id) => {
    try {
      await execMeetingService.markNotificationRead(id);
      setNotifications(prev => prev.map(n => n.id === id ? { ...n, is_read: true } : n));
    } catch {
      toast({ title: 'Failed to mark as read', variant: 'destructive' });
    }
  };


  // ── Render ────────────────────────────────────────────────────────────────

  const overviewPanel = () => (
    <div className="space-y-6">
      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {statsLoading ? (
          <div className="col-span-full flex justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-violet-400" />
          </div>
        ) : (
          <>
            <StatCard label="Upcoming Meetings"   value={stats?.upcoming_meetings}    icon={CalendarClock} palette="violet" />
            <StatCard label="Total Tasks"         value={stats?.total_tasks}          icon={ListChecks}    palette="sky" />
            <StatCard label="Overdue Tasks"       value={stats?.overdue_tasks}        icon={AlertTriangle} palette="rose" />
            <StatCard label="Action Items"        value={stats?.pending_action_items} icon={CheckCircle2}  palette="emerald" />
            <StatCard label="Unread Notifications" value={stats?.unread_notifications} icon={Bell}         palette="amber" />
          </>
        )}
      </div>

      {/* Daily digest */}
      <div className="rounded-2xl p-5" style={CARD_STYLE}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-white font-semibold flex items-center gap-2">
            <LayoutDashboard className="h-4 w-4 text-violet-400" />
            Daily Digest
          </h3>
          <Button size="sm" variant="ghost" onClick={loadDigest} disabled={digestLoading} className="text-white/50 hover:text-white">
            <RefreshCw className={`h-4 w-4 ${digestLoading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
        {digestLoading ? (
          <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-violet-400" /></div>
        ) : digest ? (
          <div className="space-y-3 text-sm">
            {digest.greeting && <p className="text-violet-300 font-medium">{digest.greeting}</p>}
            {digest.summary && <p className="text-white/70">{digest.summary}</p>}
            {Array.isArray(digest.top_priorities) && digest.top_priorities.length > 0 && (
              <div>
                <p className="text-white/50 text-xs mb-1 uppercase tracking-wide">Top Priorities</p>
                <ul className="space-y-1">
                  {digest.top_priorities.map((p, i) => (
                    <li key={i} className="flex items-start gap-2 text-white/80">
                      <ChevronRight className="h-3 w-3 mt-0.5 flex-shrink-0 text-violet-400" />{p}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {digest.focus_recommendation && (
              <p className="text-emerald-400 text-xs mt-2">
                <span className="font-semibold">Focus: </span>{digest.focus_recommendation}
              </p>
            )}
          </div>
        ) : (
          <p className="text-white/40 text-sm text-center py-6">No digest yet — click refresh to generate.</p>
        )}
      </div>

      {/* Recent meetings preview */}
      <div className="rounded-2xl p-5" style={CARD_STYLE}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-white font-semibold flex items-center gap-2">
            <CalendarClock className="h-4 w-4 text-sky-400" />
            Recent Meetings
          </h3>
          <Button size="sm" variant="ghost" onClick={() => setActiveTab('meetings')} className="text-white/50 hover:text-white text-xs">
            View all <ChevronRight className="h-3 w-3 ml-1" />
          </Button>
        </div>
        {meetingsLoading ? (
          <div className="flex justify-center py-6"><Loader2 className="h-4 w-4 animate-spin text-violet-400" /></div>
        ) : Array.isArray(meetings) && meetings.length > 0 ? (
          meetings.slice(0, 5).map(m => (
            <div key={m.id} className="flex items-center justify-between py-2.5" style={ROW_STYLE}>
              <div className="min-w-0">
                <p className="text-white text-sm font-medium truncate">{m.title}</p>
                <p className="text-white/40 text-xs">{fmtUtc(m.scheduled_at)}</p>
              </div>
              {statusBadge(m.status)}
            </div>
          ))
        ) : (
          <p className="text-white/40 text-sm text-center py-4">No meetings yet</p>
        )}
      </div>
    </div>
  );

  const meetingsPanel = () => (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-white font-semibold">All Meetings</h3>
        <Button size="sm" onClick={() => setShowMeetingDialog(true)}>
          <Plus className="h-4 w-4 mr-1" /> Schedule
        </Button>
      </div>
      {meetingsLoading ? (
        <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-violet-400" /></div>
      ) : !Array.isArray(meetings) || meetings.length === 0 ? (
        <EmptyState icon={CalendarClock} label="No meetings scheduled yet" />
      ) : (
        <div className="rounded-2xl overflow-hidden" style={CARD_STYLE}>
          {meetings.map(m => {
            const isNotesOpen = notesOpenId === m.id;
            const isPartsOpen = participantsOpenId === m.id;
            const notes = meetingNotes[m.id];
            const parts = participantsMap[m.id] || [];
            return (
              <div key={m.id} style={ROW_STYLE}>
                {/* Meeting row */}
                <div className="flex items-center gap-4 px-4 py-3">
                  <div className="rounded-lg p-2 bg-violet-500/20 flex-shrink-0">
                    <CalendarClock className="h-4 w-4 text-violet-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-white text-sm font-medium truncate">{m.title}</p>
                    <p className="text-white/40 text-xs">
                      {fmtUtc(m.scheduled_at)}
                      {m.duration_minutes ? ` · ${m.duration_minutes}min` : ''}
                    </p>
                    {m.meeting_link && (
                      <a href={m.meeting_link} target="_blank" rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-xs text-violet-400 hover:text-violet-300 mt-0.5 truncate max-w-xs">
                        <span>🔗</span> Join Meeting
                      </a>
                    )}
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {statusBadge(m.status)}
                    <Button size="sm" variant="ghost"
                      onClick={() => setEditingMeeting(m)}
                      className="text-white/40 hover:text-violet-300 p-1" title="Edit meeting">
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button size="sm" variant="ghost"
                      onClick={() => openParticipants(m.id)}
                      className={`text-xs gap-1 ${isPartsOpen ? 'text-violet-300' : 'text-white/40 hover:text-violet-300'}`}>
                      <span className="text-[11px]">👥</span>
                      People
                      <ChevronRight className={`h-3 w-3 transition-transform ${isPartsOpen ? 'rotate-90' : ''}`} />
                    </Button>
                    <Button size="sm" variant="ghost"
                      onClick={() => openNotes(m.id)}
                      className={`text-xs gap-1 ${isNotesOpen ? 'text-violet-300' : 'text-white/40 hover:text-violet-300'}`}>
                      <FileText className="h-3.5 w-3.5" />
                      {notes ? 'Notes' : 'Notes'}
                      <ChevronRight className={`h-3 w-3 transition-transform ${isNotesOpen ? 'rotate-90' : ''}`} />
                    </Button>
                  </div>
                </div>

                {/* Participants panel */}
                {isPartsOpen && (() => {
                  const pendingUser = pendingAddMap[m.id] || null;
                  const confirmRemoveId = confirmRemoveMap[m.id] || null;
                  return (
                  <div className="px-4 pb-4 space-y-3 border-t border-white/5 pt-3">
                    <p className="text-white/60 text-xs font-semibold">Participants</p>

                    {/* Current participants */}
                    {parts.length > 0 && (
                      <div className="space-y-1">
                        {parts.map(p => (
                          <div key={p.user_id}>
                            <div className="flex items-center justify-between rounded-lg px-3 py-2 bg-white/5">
                              <div>
                                <span className="text-white text-xs font-medium">{p.full_name}</span>
                                <span className="text-white/40 text-xs ml-2">{p.email}</span>
                              </div>
                              <div className="flex items-center gap-2">
                                {p.response && p.response !== 'pending' && (
                                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                                    p.response === 'accepted' ? 'bg-emerald-500/20 text-emerald-400' :
                                    p.response === 'rejected' ? 'bg-red-500/20 text-red-400' :
                                    p.response === 'tentative' ? 'bg-yellow-500/20 text-yellow-400' :
                                    'bg-white/10 text-white/40'
                                  }`}>{p.response}</span>
                                )}
                                {!p.id ? (
                                  <span className="text-white/20 text-[10px]">syncing…</span>
                                ) : confirmRemoveId === p.id ? (
                                  <div className="flex items-center gap-1">
                                    <span className="text-white/50 text-[10px]">Remove?</span>
                                    <button
                                      onClick={() => { removeParticipant(m.id, p.id, p.user_id, p.full_name); setConfirmRemoveMap(prev => ({ ...prev, [m.id]: null })); }}
                                      className="px-2 py-0.5 rounded text-[10px] bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors">
                                      Yes
                                    </button>
                                    <button
                                      onClick={() => setConfirmRemoveMap(prev => ({ ...prev, [m.id]: null }))}
                                      className="px-2 py-0.5 rounded text-[10px] bg-white/10 text-white/50 hover:bg-white/20 transition-colors">
                                      No
                                    </button>
                                  </div>
                                ) : (
                                  <button
                                    onClick={() => setConfirmRemoveMap(prev => ({ ...prev, [m.id]: p.id }))}
                                    className="text-white/30 hover:text-red-400 text-xs transition-colors">✕</button>
                                )}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Pending add confirmation bar */}
                    {pendingUser && (
                      <div className="flex items-center justify-between rounded-lg px-3 py-2 bg-violet-500/10 border border-violet-500/30">
                        <div className="flex items-center gap-2">
                          <div className="h-6 w-6 rounded-full bg-violet-500/30 flex items-center justify-center text-violet-300 text-xs font-bold flex-shrink-0">
                            {pendingUser.full_name?.[0]?.toUpperCase() || '?'}
                          </div>
                          <div>
                            <p className="text-violet-200 text-xs font-medium">{pendingUser.full_name}</p>
                            <p className="text-white/40 text-[10px]">{pendingUser.email}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-violet-300/60 text-[10px]">An email will be sent</span>
                          <button
                            onClick={() => { addParticipant(m.id, pendingUser); setPendingAddMap(prev => ({ ...prev, [m.id]: null })); setUserSearchQ(''); setUserSearchResults([]); }}
                            className="px-2.5 py-1 rounded text-[11px] bg-violet-600 text-white hover:bg-violet-700 transition-colors font-medium">
                            Confirm
                          </button>
                          <button
                            onClick={() => { setPendingAddMap(prev => ({ ...prev, [m.id]: null })); setUserSearchQ(''); setUserSearchResults([]); }}
                            className="text-white/30 hover:text-white/60 text-xs transition-colors">✕</button>
                        </div>
                      </div>
                    )}

                    {/* Search + add */}
                    {!pendingUser && (
                      <div className="relative">
                        <Input
                          value={participantsOpenId === m.id ? userSearchQ : ''}
                          onChange={e => searchUsers(e.target.value, m.id)}
                          placeholder="Type a name or email to add…"
                          autoComplete="off"
                          className="bg-white/5 border-white/10 text-white text-xs h-8"
                        />
                        {userSearchLoading && (
                          <Loader2 className="absolute right-2 top-2 h-4 w-4 animate-spin text-white/40" />
                        )}
                        {userSearchResults.length > 0 && (
                          <div className="absolute z-50 w-full mt-1 rounded-xl border border-white/10 bg-[#1a1333] shadow-xl overflow-hidden">
                            {userSearchResults.map(u => (
                              <button key={u.id}
                                onClick={() => { setPendingAddMap(prev => ({ ...prev, [m.id]: u })); setUserSearchResults([]); }}
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
                        {userSearchQ.length >= 2 && !userSearchLoading && userSearchResults.length === 0 && (
                          <p className="text-white/30 text-xs mt-1 px-1">No users found</p>
                        )}
                      </div>
                    )}
                  </div>
                  );
                })()}

                {/* Notetaker panel — expands inline */}
                {isNotesOpen && (
                  <div className="px-4 pb-4 space-y-3 border-t border-white/5 pt-3">
                    {/* Existing notes */}
                    {notes && (
                      <div className="space-y-2">
                        {notes.ai_summary && (
                          <div className="rounded-xl p-3 bg-violet-500/10 border border-violet-500/20">
                            <p className="text-violet-300 text-xs font-semibold mb-1">AI Summary</p>
                            <p className="text-white/80 text-xs whitespace-pre-wrap">{notes.ai_summary}</p>
                          </div>
                        )}
                        {Array.isArray(notes.key_decisions) && notes.key_decisions.length > 0 && (
                          <div className="rounded-xl p-3 bg-white/5 border border-white/10">
                            <p className="text-white/60 text-xs font-semibold mb-1">Key Decisions</p>
                            {notes.key_decisions.map((d, i) => (
                              <p key={i} className="text-white/70 text-xs">• {d}</p>
                            ))}
                          </div>
                        )}
                        {Array.isArray(notes.action_items) && notes.action_items.length > 0 && (
                          <div className="rounded-xl p-3 bg-white/5 border border-white/10">
                            <p className="text-white/60 text-xs font-semibold mb-1">Action Items ({notes.action_items.length})</p>
                            {notes.action_items.map((a, i) => (
                              <p key={i} className="text-white/70 text-xs">
                                • {a.title}
                                {a.assignee_hint ? <span className="text-violet-300/70"> → {a.assignee_hint}</span> : ''}
                                {a.due_date ? <span className="text-white/40"> · {a.due_date}</span> : ''}
                              </p>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Transcript input */}
                    <div className="space-y-2">
                      <Label className="text-white/60 text-xs">
                        {notes ? 'Update Transcript (re-generate notes)' : 'Paste Meeting Transcript'}
                      </Label>
                      <textarea
                        value={notesOpenId === m.id ? transcriptInput : ''}
                        onChange={e => setTranscriptInput(e.target.value)}
                        rows={4}
                        placeholder="Paste the meeting transcript or key discussion notes here…"
                        className="w-full rounded-md px-3 py-2 text-xs text-white placeholder:text-white/25 bg-white/5 border border-white/10 resize-none focus:outline-none focus:ring-1 focus:ring-violet-500"
                      />
                      <Button size="sm" onClick={() => submitTranscript(m.id)} disabled={notesLoading}
                        className="bg-violet-600 hover:bg-violet-700 text-white">
                        {notesLoading ? <><Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />Processing…</> : <><FileText className="h-3.5 w-3.5 mr-1.5" />Generate Notes with AI</>}
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );

  const tasksPanel = () => (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-white font-semibold">Tasks</h3>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline"
            onClick={runAiPrioritize} disabled={prioritizeLoading || tasks.length === 0}
            className="border-violet-500/40 text-violet-300 hover:bg-violet-500/10 text-xs gap-1.5">
            {prioritizeLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
            AI Prioritize
          </Button>
          <Button size="sm" onClick={() => setShowTaskDialog(true)}>
            <Plus className="h-4 w-4 mr-1" /> Add Task
          </Button>
        </div>
      </div>

      {/* AI prioritization result */}
      {Array.isArray(prioritizeResult) && prioritizeResult.length > 0 && (
        <div className="rounded-2xl p-4 space-y-2" style={CARD_STYLE}>
          <div className="flex items-center justify-between mb-1">
            <p className="text-violet-300 text-xs font-semibold flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5" /> AI Prioritization Result
            </p>
            <button onClick={() => setPrioritizeResult(null)} className="text-white/30 hover:text-white text-xs">✕ Close</button>
          </div>
          {prioritizeResult.map((t, i) => (
            <div key={t.id || i} className="rounded-xl p-3 bg-white/5 border border-white/10 space-y-0.5">
              <div className="flex items-center gap-2">
                {priorityBadge(t.priority)}
                <p className="text-white text-xs font-medium truncate">{t.title}</p>
              </div>
              {t.ai_reasoning && <p className="text-white/50 text-xs">{t.ai_reasoning}</p>}
              {t.suggested_due_date && <p className="text-violet-300/60 text-xs">Suggested deadline: {t.suggested_due_date}</p>}
            </div>
          ))}
        </div>
      )}

      {tasksLoading ? (
        <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-violet-400" /></div>
      ) : !Array.isArray(tasks) || tasks.length === 0 ? (
        <EmptyState icon={ListChecks} label="No tasks yet" />
      ) : (
        <div className="rounded-2xl overflow-hidden" style={CARD_STYLE}>
          {tasks.map(t => {
            const isOpen = expandedTaskId === t.id;
            return (
              <div key={t.id} style={ROW_STYLE}>
                {/* ── Row ── */}
                <div
                  className="flex items-center gap-4 px-4 py-3 cursor-pointer hover:bg-white/[0.04] transition-colors"
                  onClick={() => setExpandedTaskId(isOpen ? null : t.id)}
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-white text-sm font-medium truncate">{t.title}</p>
                    <p className="text-white/40 text-xs">
                      {t.due_date ? `Due: ${t.due_date}` : 'No due date'}
                      {(t.assignees || []).length > 0 && (
                        <span className="text-violet-300/70 ml-1.5">
                          · {t.assignees.map(a => a.full_name).join(', ')}
                        </span>
                      )}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {priorityBadge(t.priority)}
                    {statusBadge(t.status)}
                    <ChevronRight className={`h-4 w-4 text-white/30 transition-transform ${isOpen ? 'rotate-90' : ''}`} />
                  </div>
                </div>

                {/* ── Inline detail panel ── */}
                {isOpen && (
                  <div className="px-4 pb-4 pt-2 border-t border-white/5 space-y-2">
                    {t.description && (
                      <p className="text-white/60 text-xs whitespace-pre-wrap">{t.description}</p>
                    )}
                    {(t.assignees || []).length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {t.assignees.map(a => (
                          <span key={a.id} className="px-2 py-0.5 rounded-full bg-violet-500/20 border border-violet-500/30 text-violet-200 text-xs">
                            {a.full_name}
                          </span>
                        ))}
                      </div>
                    )}
                    {t.ai_reasoning && (
                      <p className="text-white/40 text-xs italic">{t.ai_reasoning}</p>
                    )}
                    <div className="flex gap-2 pt-1">
                      <Button size="sm" variant="outline"
                        className="border-violet-500/40 text-violet-300 hover:bg-violet-500/10 text-xs h-7 px-3"
                        onClick={e => { e.stopPropagation(); setEditingTask(t); }}>
                        <Pencil className="h-3 w-3 mr-1" /> Edit
                      </Button>
                      <Button size="sm" variant="ghost"
                        className="text-red-400 hover:text-red-300 hover:bg-red-500/10 text-xs h-7 px-3"
                        onClick={e => { e.stopPropagation(); setConfirmDeleteTaskId(t.id); }}>
                        <Trash2 className="h-3 w-3 mr-1" /> Delete
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );

  const WORKLOAD_COLORS = {
    light:    'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
    moderate: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
    heavy:    'bg-red-500/20 text-red-400 border-red-500/30',
  };

  const calendarPanel = () => (
    <div className="space-y-5">
      {/* Generate button + settings */}
      <div className="rounded-2xl p-5 space-y-4" style={CARD_STYLE}>
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-white font-semibold flex items-center gap-2">
              <CalendarDays className="h-4 w-4 text-violet-400" /> AI Weekly Planner
            </h3>
            <p className="text-white/50 text-xs mt-1">
              AI analyses your meetings and tasks and builds an optimized schedule for the week.
            </p>
          </div>
          <Button onClick={async () => {
            setWeekPlanLoading(true);
            try {
              const today = new Date();
              const weekStart = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;
              const res = await execMeetingService.planWeek({ include_past_tasks: includePastTasks, week_start: weekStart });
              console.log('[WeekPlan] response:', res);
              const plan = res.plan || res;
              setWeekPlan(plan);
              if (!plan || (!plan.daily_plans?.length && !plan.weekly_summary)) {
                toast({ title: 'Plan generated but empty', description: 'No meetings or tasks found for this week. Add some first!', variant: 'destructive' });
              } else {
                toast({ title: 'Week plan ready!' });
              }
            } catch (err) {
              console.error('[WeekPlan] error:', err);
              toast({ title: 'Planning failed', description: err?.data?.message || err.message || 'Unknown error', variant: 'destructive' });
            } finally {
              setWeekPlanLoading(false);
            }
          }} disabled={weekPlanLoading}>
            {weekPlanLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <CalendarDays className="h-4 w-4 mr-2" />}
            {weekPlanLoading ? 'Planning…' : 'Plan This Week'}
          </Button>
        </div>

        {/* Settings row */}
        <div className="flex items-center justify-between rounded-xl px-4 py-3 bg-white/5 border border-white/10">
          <div>
            <p className="text-white/80 text-sm font-medium">Include overdue / older tasks</p>
            <p className="text-white/40 text-xs mt-0.5">
              {includePastTasks
                ? 'All todo & in-progress tasks included regardless of due date'
                : 'Only tasks due this week or later are included'}
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              if (!includePastTasks) {
                setShowPastTasksConfirm(true);
              } else {
                setIncludePastTasks(false);
              }
            }}
            className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none ${
              includePastTasks ? 'bg-violet-600' : 'bg-white/20'
            }`}
          >
            <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform duration-200 ${
              includePastTasks ? 'translate-x-5' : 'translate-x-0'
            }`} />
          </button>
        </div>
      </div>

      {/* Plan results */}
      {weekPlan && !weekPlan.daily_plans?.length && !weekPlan.weekly_summary && (
        <div className="rounded-2xl p-8 text-center" style={CARD_STYLE}>
          <CalendarDays className="h-10 w-10 text-white/20 mx-auto mb-3" />
          <p className="text-white/50 text-sm">No meetings or tasks found for this week.</p>
          <p className="text-white/30 text-xs mt-1">Schedule some meetings or add tasks first, then try again.</p>
        </div>
      )}
      {weekPlan && (weekPlan.daily_plans?.length > 0 || weekPlan.weekly_summary) && (
        <div className="space-y-4">
          {/* Download button */}
          <div className="flex justify-end">
            <Button
              size="sm"
              variant="outline"
              className="border-violet-500/40 text-violet-300 hover:bg-violet-500/10 gap-2"
              onClick={() => {
                const weekLabel = weekPlan.week_start || '';
                const lines = [];
                lines.push(`AI EXECUTIVE WEEKLY PLAN${weekLabel ? ' — ' + weekLabel : ''}`);
                lines.push('='.repeat(60));
                if (weekPlan.weekly_summary) {
                  lines.push('');
                  lines.push('SUMMARY');
                  lines.push(weekPlan.weekly_summary);
                }
                if (weekPlan.conflicts_detected?.length) {
                  lines.push('');
                  lines.push('CONFLICTS DETECTED');
                  weekPlan.conflicts_detected.forEach(c => lines.push('  • ' + c));
                }
                if (weekPlan.recommendations?.length) {
                  lines.push('');
                  lines.push('RECOMMENDATIONS');
                  weekPlan.recommendations.forEach(r => lines.push('  › ' + r));
                }
                (weekPlan.daily_plans || []).forEach(day => {
                  lines.push('');
                  lines.push('-'.repeat(60));
                  lines.push(`${day.day_name}  ${day.date}${day.workload_level ? '  [' + day.workload_level.toUpperCase() + ']' : ''}`);
                  lines.push('-'.repeat(60));
                  if (day.scheduled_meetings?.length) {
                    lines.push('MEETINGS');
                    day.scheduled_meetings.forEach(m => lines.push('  • ' + (typeof m === 'string' ? m : m.title)));
                  }
                  if (day.suggested_task_slots?.length) {
                    lines.push('SUGGESTED TASK SLOTS');
                    day.suggested_task_slots.forEach(s => lines.push(`  ${s.time}  ${s.task}${s.duration_minutes ? '  ('+s.duration_minutes+'min)' : ''}`));
                  }
                  if (day.focus_blocks?.length) {
                    lines.push('FOCUS BLOCKS');
                    day.focus_blocks.forEach(b => lines.push(`  ${b.start}–${b.end}  ${b.label}`));
                  }
                });
                lines.push('');
                lines.push('='.repeat(60));
                lines.push('Generated by AI Executive Meeting Assistant');

                const blob = new Blob([lines.join('\n')], { type: 'text/plain' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `weekly-plan${weekLabel ? '-' + weekLabel : ''}.txt`;
                a.click();
                URL.revokeObjectURL(url);

                // Open print dialog for PDF
                const printWin = window.open('', '_blank', 'width=800,height=900');
                printWin.document.write(`<!DOCTYPE html><html><head><title>Weekly Plan${weekLabel ? ' — ' + weekLabel : ''}</title>
                <style>
                  body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; margin: 0; padding: 32px; color: #111; background: #fff; }
                  h1 { font-size: 22px; font-weight: 700; margin: 0 0 4px; color: #1e1b4b; }
                  .subtitle { font-size: 13px; color: #6b7280; margin-bottom: 24px; }
                  .summary-box { background: #f5f3ff; border: 1px solid #ddd6fe; border-radius: 8px; padding: 14px 18px; margin-bottom: 20px; }
                  .summary-box p { margin: 0; font-size: 14px; color: #374151; line-height: 1.6; }
                  .conflicts { background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 12px 18px; margin-bottom: 12px; }
                  .conflicts .label { color: #ef4444; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; margin-bottom: 6px; }
                  .recs { background: #f5f3ff; border: 1px solid #ddd6fe; border-radius: 8px; padding: 12px 18px; margin-bottom: 20px; }
                  .recs .label { color: #7c3aed; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; margin-bottom: 6px; }
                  .recs li, .conflicts li { font-size: 13px; color: #374151; margin-bottom: 3px; }
                  .day-card { border: 1px solid #e5e7eb; border-radius: 10px; margin-bottom: 18px; overflow: hidden; page-break-inside: avoid; }
                  .day-header { display: flex; align-items: center; justify-content: space-between; background: #f9fafb; padding: 12px 18px; border-bottom: 1px solid #e5e7eb; }
                  .day-name { font-size: 16px; font-weight: 700; color: #1e1b4b; }
                  .day-date { font-size: 12px; color: #6b7280; margin-top: 2px; }
                  .workload { font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 999px; }
                  .workload.light { background: #dcfce7; color: #166534; }
                  .workload.moderate { background: #fef9c3; color: #854d0e; }
                  .workload.heavy { background: #fee2e2; color: #991b1b; }
                  .day-body { padding: 14px 18px; }
                  .section-label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: #9ca3af; margin: 10px 0 6px; }
                  .row { display: flex; align-items: baseline; gap: 8px; margin-bottom: 4px; font-size: 13px; color: #374151; }
                  .time { font-family: monospace; color: #7c3aed; min-width: 44px; }
                  .dur { color: #9ca3af; font-size: 12px; margin-left: auto; }
                  .footer { margin-top: 32px; text-align: center; font-size: 11px; color: #9ca3af; border-top: 1px solid #e5e7eb; padding-top: 14px; }
                  @media print { body { padding: 20px; } }
                </style></head><body>`);
                printWin.document.write(`<h1>AI Executive Weekly Plan</h1>`);
                printWin.document.write(`<p class="subtitle">${weekLabel ? 'Week starting ' + weekLabel : ''} &nbsp;·&nbsp; Generated by AI Executive Meeting Assistant</p>`);
                if (weekPlan.weekly_summary) {
                  printWin.document.write(`<div class="summary-box"><p>${weekPlan.weekly_summary}</p></div>`);
                }
                if (weekPlan.conflicts_detected?.length) {
                  printWin.document.write(`<div class="conflicts"><div class="label">Conflicts Detected</div><ul>${weekPlan.conflicts_detected.map(c=>`<li>${c}</li>`).join('')}</ul></div>`);
                }
                if (weekPlan.recommendations?.length) {
                  printWin.document.write(`<div class="recs"><div class="label">Recommendations</div><ul>${weekPlan.recommendations.map(r=>`<li>${r}</li>`).join('')}</ul></div>`);
                }
                (weekPlan.daily_plans || []).forEach(day => {
                  const wl = day.workload_level || 'moderate';
                  printWin.document.write(`<div class="day-card"><div class="day-header"><div><div class="day-name">${day.day_name}</div><div class="day-date">${day.date}</div></div><span class="workload ${wl}">${wl.charAt(0).toUpperCase()+wl.slice(1)}</span></div><div class="day-body">`);
                  if (day.scheduled_meetings?.length) {
                    printWin.document.write(`<div class="section-label">Meetings</div>`);
                    day.scheduled_meetings.forEach(m => printWin.document.write(`<div class="row">📅 ${typeof m==='string'?m:m.title}</div>`));
                  }
                  if (day.suggested_task_slots?.length) {
                    printWin.document.write(`<div class="section-label">Suggested Task Slots</div>`);
                    day.suggested_task_slots.forEach(s => printWin.document.write(`<div class="row"><span class="time">${s.time}</span>${s.task}${s.duration_minutes?`<span class="dur">${s.duration_minutes}min</span>`:''}</div>`));
                  }
                  if (day.focus_blocks?.length) {
                    printWin.document.write(`<div class="section-label">Focus Blocks</div>`);
                    day.focus_blocks.forEach(b => printWin.document.write(`<div class="row"><span class="time">${b.start}–${b.end}</span>${b.label}</div>`));
                  }
                  printWin.document.write(`</div></div>`);
                });
                printWin.document.write(`<div class="footer">AI Executive Meeting Assistant &nbsp;·&nbsp; ${weekLabel}</div></body></html>`);
                printWin.document.close();
                printWin.focus();
                setTimeout(() => { printWin.print(); }, 400);
              }}
            >
              <Download className="h-4 w-4" /> Download PDF
            </Button>
          </div>

          {/* Summary + recommendations */}
          {(weekPlan.weekly_summary || weekPlan.recommendations?.length > 0) && (
            <div className="rounded-2xl p-5 space-y-3" style={CARD_STYLE}>
              {weekPlan.weekly_summary && (
                <p className="text-white/80 text-sm">{weekPlan.weekly_summary}</p>
              )}
              {Array.isArray(weekPlan.conflicts_detected) && weekPlan.conflicts_detected.length > 0 && (
                <div className="rounded-xl p-3 bg-red-500/10 border border-red-500/20">
                  <p className="text-red-400 text-xs font-semibold mb-1">Conflicts Detected</p>
                  {weekPlan.conflicts_detected.map((c, i) => (
                    <p key={i} className="text-red-300/80 text-xs">• {c}</p>
                  ))}
                </div>
              )}
              {Array.isArray(weekPlan.recommendations) && weekPlan.recommendations.length > 0 && (
                <div>
                  <p className="text-white/50 text-xs uppercase tracking-wide mb-1">Recommendations</p>
                  {weekPlan.recommendations.map((r, i) => (
                    <p key={i} className="text-violet-300 text-xs flex gap-1.5"><ChevronRight className="h-3 w-3 mt-0.5 flex-shrink-0" />{r}</p>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Daily plan cards */}
          {Array.isArray(weekPlan.daily_plans) && weekPlan.daily_plans.filter(day =>
            day.scheduled_meetings?.length > 0 ||
            day.suggested_task_slots?.length > 0 ||
            day.focus_blocks?.length > 0
          ).map((day, i) => (
            <div key={i} className="rounded-2xl overflow-hidden" style={CARD_STYLE}>
              <div className="flex items-center justify-between px-5 py-3 border-b border-white/10">
                <div className="flex items-center gap-3">
                  <div className="rounded-lg p-2 bg-violet-500/20">
                    <CalendarDays className="h-4 w-4 text-violet-400" />
                  </div>
                  <div>
                    <p className="text-white font-semibold text-sm">{day.day_name}</p>
                    <p className="text-white/40 text-xs">{day.date}</p>
                  </div>
                </div>
                {day.workload_level && (
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs border ${WORKLOAD_COLORS[day.workload_level] || WORKLOAD_COLORS.moderate}`}>
                    {day.workload_level}
                  </span>
                )}
              </div>
              <div className="p-5 space-y-4">
                {/* Meetings */}
                {Array.isArray(day.scheduled_meetings) && day.scheduled_meetings.length > 0 && (
                  <div>
                    <p className="text-white/40 text-xs uppercase tracking-wide mb-2">Meetings</p>
                    <div className="space-y-1">
                      {day.scheduled_meetings.map((m, j) => (
                        <div key={j} className="flex items-center gap-2 text-sm">
                          <CalendarClock className="h-3.5 w-3.5 text-sky-400 flex-shrink-0" />
                          <span className="text-white/80">{typeof m === 'string' ? m : m.title}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {/* Task slots */}
                {Array.isArray(day.suggested_task_slots) && day.suggested_task_slots.length > 0 && (
                  <div>
                    <p className="text-white/40 text-xs uppercase tracking-wide mb-2">Suggested Task Slots</p>
                    <div className="space-y-1">
                      {day.suggested_task_slots.map((slot, j) => (
                        <div key={j} className="flex items-center gap-2 text-sm">
                          <Clock className="h-3.5 w-3.5 text-violet-400 flex-shrink-0" />
                          <span className="text-violet-300 font-mono text-xs">{slot.time}</span>
                          <span className="text-white/80">{slot.task}</span>
                          {slot.duration_minutes && <span className="text-white/30 text-xs ml-auto">{slot.duration_minutes}min</span>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {/* Focus blocks */}
                {Array.isArray(day.focus_blocks) && day.focus_blocks.length > 0 && (
                  <div>
                    <p className="text-white/40 text-xs uppercase tracking-wide mb-2">Focus Blocks</p>
                    <div className="space-y-1">
                      {day.focus_blocks.map((block, j) => (
                        <div key={j} className="flex items-center gap-2 text-sm">
                          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 flex-shrink-0" />
                          <span className="text-emerald-300 font-mono text-xs">{block.start}–{block.end}</span>
                          <span className="text-white/80">{block.label}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const DOC_TYPE_LABELS = { agenda: 'Agenda', minutes: 'Minutes', briefing: 'Briefing', report: 'Report', other: 'Other' };
  const DOC_TYPE_COLORS = {
    agenda:   'bg-violet-500/20 text-violet-300 border-violet-500/30',
    minutes:  'bg-sky-500/20 text-sky-300 border-sky-500/30',
    briefing: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
    report:   'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
    other:    'bg-white/10 text-white/50 border-white/10',
  };

  const documentsPanel = () => (
    <div className="space-y-5">
      {/* Generator card */}
      <div className="rounded-2xl p-5 space-y-4" style={CARD_STYLE}>
        <h3 className="text-white font-semibold flex items-center gap-2">
          <FileText className="h-4 w-4 text-violet-400" />
          Generate Document with AI
        </h3>

        {/* Row 1: Doc type + meeting picker */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1">
            <Label className="text-white/70 text-xs">Document Type</Label>
            <Select value={aiDocType} onValueChange={v => { setAiDocType(v); setAiDocTopics(''); setAiDocSummary(''); }}>
              <SelectTrigger className="bg-white/5 border-white/10 text-white">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="agenda">Meeting Agenda</SelectItem>
                <SelectItem value="minutes">Meeting Minutes</SelectItem>
                <SelectItem value="briefing">Executive Briefing</SelectItem>
                <SelectItem value="report">Status Report</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label className="text-white/70 text-xs">Link to Saved Meeting <span className="text-white/30">(optional)</span></Label>
            <Select value={aiDocMeetingId || 'none'} onValueChange={v => { const val = v === 'none' ? '' : v; setAiDocMeetingId(val); if (val) setAiDocInput(''); }}>
              <SelectTrigger className="bg-white/5 border-white/10 text-white">
                <SelectValue placeholder="— Select a meeting —" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">— None / manual topic —</SelectItem>
                {Array.isArray(meetings) && meetings.map(m => (
                  <SelectItem key={m.id} value={String(m.id)}>
                    {m.title}{m.scheduled_at ? ` · ${fmtUtc(m.scheduled_at)}` : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {aiDocMeetingId && (() => {
              const m = meetings.find(x => String(x.id) === String(aiDocMeetingId));
              return m ? (
                <p className="text-xs text-violet-300/70 mt-1">
                  {m.attendees?.length ? `Attendees: ${m.attendees.slice(0,3).join(', ')}${m.attendees.length > 3 ? ` +${m.attendees.length - 3}` : ''}` : ''}
                  {m.duration_minutes ? `  ·  ${m.duration_minutes} min` : ''}
                </p>
              ) : null;
            })()}
          </div>
        </div>

        {/* Manual topic — shown only when no meeting selected */}
        {!aiDocMeetingId && (
          <div className="space-y-1">
            <Label className="text-white/70 text-xs">Meeting / Topic Title</Label>
            <Input
              value={aiDocInput}
              onChange={e => setAiDocInput(e.target.value)}
              placeholder="e.g. Q3 Strategy Review"
              className="bg-white/5 border-white/10 text-white"
            />
          </div>
        )}

        {/* Topics — agenda only */}
        {aiDocType === 'agenda' && (
          <div className="space-y-1">
            <Label className="text-white/70 text-xs">
              Topics to Cover <span className="text-white/30">(comma-separated)</span>
            </Label>
            <Input
              value={aiDocTopics}
              onChange={e => setAiDocTopics(e.target.value)}
              placeholder="e.g. Q3 results, Budget review, Hiring plan"
              className="bg-white/5 border-white/10 text-white"
            />
          </div>
        )}

        {/* Summary — minutes only */}
        {aiDocType === 'minutes' && (
          <div className="space-y-1">
            <Label className="text-white/70 text-xs">Meeting Summary / Key Discussion Points</Label>
            <textarea
              value={aiDocSummary}
              onChange={e => setAiDocSummary(e.target.value)}
              rows={3}
              placeholder="Briefly describe what was discussed, decisions made, outcomes…"
              className="w-full rounded-md px-3 py-2 text-sm text-white placeholder:text-white/30 bg-white/5 border border-white/10 resize-none focus:outline-none focus:ring-1 focus:ring-violet-500"
            />
          </div>
        )}

        <Button onClick={generateAiDoc} disabled={aiDocLoading}>
          {aiDocLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <FileText className="h-4 w-4 mr-2" />}
          {aiDocLoading ? 'Generating…' : 'Generate & Save'}
        </Button>
      </div>

      {/* Saved documents list */}
      <div className="rounded-2xl overflow-hidden" style={CARD_STYLE}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-white/10">
          <h3 className="text-white font-semibold text-sm">Saved Documents</h3>
          <Button size="sm" variant="ghost" onClick={loadDocuments} disabled={docsLoading} className="text-white/40 hover:text-white">
            <RefreshCw className={`h-3.5 w-3.5 ${docsLoading ? 'animate-spin' : ''}`} />
          </Button>
        </div>

        {docsLoading ? (
          <div className="flex justify-center py-10"><Loader2 className="h-5 w-5 animate-spin text-violet-400" /></div>
        ) : !Array.isArray(savedDocs) || savedDocs.length === 0 ? (
          <EmptyState icon={FileText} label="No documents yet — generate one above" />
        ) : (
          savedDocs.map(doc => (
            <div key={doc.id} className="flex items-center gap-4 px-5 py-3 hover:bg-white/[0.03] transition-colors" style={ROW_STYLE}>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] border ${DOC_TYPE_COLORS[doc.doc_type] || DOC_TYPE_COLORS.other}`}>
                    {DOC_TYPE_LABELS[doc.doc_type] || doc.doc_type}
                  </span>
                  <p className="text-white text-sm font-medium truncate">{doc.title}</p>
                </div>
                <p className="text-white/30 text-xs">{new Date(doc.created_at).toLocaleString()}</p>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <Button size="sm" variant="ghost" onClick={() => setViewDoc(doc)}
                  className="text-violet-400 hover:text-violet-300 text-xs gap-1">
                  <FileText className="h-3.5 w-3.5" /> Open
                </Button>
                <Button size="sm" variant="ghost" onClick={() => downloadDocPdf(doc)}
                  className="text-sky-400 hover:text-sky-300 text-xs">
                  ⬇ PDF
                </Button>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button size="icon" variant="ghost" className="h-7 w-7 text-white/30 hover:text-white">
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent>
                    <DropdownMenuItem className="text-red-400" onClick={() => deleteDoc(doc.id)}>
                      <Trash2 className="h-4 w-4 mr-2" /> Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );

  const notificationsPanel = () => (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-white font-semibold">Notifications</h3>
        <Button size="sm" variant="ghost" onClick={loadNotifications} disabled={notifsLoading} className="text-white/50 hover:text-white">
          <RefreshCw className={`h-4 w-4 ${notifsLoading ? 'animate-spin' : ''}`} />
        </Button>
      </div>
      {notifsLoading ? (
        <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-violet-400" /></div>
      ) : !Array.isArray(notifications) || notifications.length === 0 ? (
        <EmptyState icon={Bell} label="No notifications" />
      ) : (
        <div className="rounded-2xl overflow-hidden" style={CARD_STYLE}>
          {notifications.map(n => (
            <div
              key={n.id}
              className={`flex items-start gap-4 px-4 py-3 cursor-pointer transition-colors ${!n.is_read ? 'bg-white/[0.03]' : ''}`}
              style={ROW_STYLE}
              onClick={() => !n.is_read && markNotifRead(n.id)}
            >
              <div className={`rounded-lg p-2 flex-shrink-0 ${
                n.severity === 'critical' ? 'bg-red-500/20' :
                n.severity === 'warning'  ? 'bg-amber-500/20' : 'bg-sky-500/20'
              }`}>
                {n.severity === 'critical'
                  ? <AlertTriangle className="h-4 w-4 text-red-400" />
                  : n.severity === 'warning'
                  ? <Clock className="h-4 w-4 text-amber-400" />
                  : <Bell className="h-4 w-4 text-sky-400" />}
              </div>
              <div className="flex-1 min-w-0">
                <p className={`text-sm font-medium truncate ${n.is_read ? 'text-white/50' : 'text-white'}`}>{n.title}</p>
                <p className="text-white/40 text-xs">{n.message}</p>
              </div>
              {!n.is_read && (
                <div className="flex-shrink-0 mt-1.5 h-2 w-2 rounded-full bg-violet-400" />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const PANEL_MAP = {
    overview: overviewPanel,
    meetings: meetingsPanel,
    tasks: tasksPanel,
    calendar: calendarPanel,
    documents: documentsPanel,
    notifications: notificationsPanel,
  };

  return (
    <ErrorBoundary>
      <div
        className="rounded-2xl p-4 sm:p-6"
        style={{
          background: 'linear-gradient(135deg, rgba(167,139,250,0.08) 0%, rgba(139,92,246,0.04) 50%, rgba(0,0,0,0) 100%)',
          border: '1px solid rgba(167,139,250,0.15)',
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="rounded-xl p-2.5 bg-violet-500/20">
              <CalendarClock className="h-6 w-6 text-violet-400" />
            </div>
            <div>
              <h1 className="text-white text-xl font-bold">Executive Meeting Assistant</h1>
              <p className="text-white/50 text-sm">Manage meetings, tasks & get AI-powered insights</p>
            </div>
          </div>
          {/* Mobile tab menu */}
          <div className="md:hidden">
            <DropdownMenu open={mobileMenuOpen} onOpenChange={setMobileMenuOpen}>
              <DropdownMenuTrigger asChild>
                <Button size="icon" variant="ghost" className="text-white/70 hover:text-white">
                  <Menu className="h-5 w-5" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="bg-[#0d0b1f] border-white/10">
                {TAB_ITEMS.map(t => (
                  <DropdownMenuItem
                    key={t.value}
                    className={`text-white/70 hover:text-white cursor-pointer ${activeTab === t.value ? 'text-violet-400' : ''}`}
                    onClick={() => { setActiveTab(t.value); setMobileMenuOpen(false); }}
                  >
                    <t.icon className="h-4 w-4 mr-2" />{t.label}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="hidden md:flex flex-wrap gap-1 h-auto p-1 mb-6 bg-white/5 border border-white/10">
            {TAB_ITEMS.map(t => (
              <TabsTrigger
                key={t.value}
                value={t.value}
                className="flex items-center gap-1.5 text-white/60 data-[state=active]:bg-violet-600 data-[state=active]:text-white"
              >
                <t.icon className="h-3.5 w-3.5" />{t.label}
              </TabsTrigger>
            ))}
          </TabsList>

          {TAB_ITEMS.map(t => (
            <TabsContent key={t.value} value={t.value} className="mt-0">
              <ErrorBoundary key={t.value}>
                {PANEL_MAP[t.value]?.()}
              </ErrorBoundary>
            </TabsContent>
          ))}
        </Tabs>
      </div>

      {/* Dialogs */}
      <ScheduleMeetingDialog
        open={showMeetingDialog}
        onClose={() => setShowMeetingDialog(false)}
        onCreated={() => { loadMeetings(); loadStats(); }}
      />
      <AddTaskDialog
        open={showTaskDialog}
        onClose={() => setShowTaskDialog(false)}
        onCreated={() => { loadTasks(); loadStats(); }}
      />

      <TaskEditDialog
        task={editingTask}
        onClose={() => setEditingTask(null)}
        onUpdated={() => { loadTasks(); loadStats(); setExpandedTaskId(null); }}
      />

      <MeetingEditDialog
        key={editingMeeting?.id}
        meeting={editingMeeting}
        open={!!editingMeeting}
        onClose={() => setEditingMeeting(null)}
        onUpdated={() => { loadMeetings(); loadStats(); }}
      />

      {/* Past tasks confirm dialog */}
      <Dialog open={showPastTasksConfirm} onOpenChange={open => { if (!open) setShowPastTasksConfirm(false); }}>
        <DialogContent className="max-w-sm w-full bg-[#0d0b1f] border-white/10 text-white">
          <div className="flex flex-col items-center gap-4 py-2">
            <div className="w-14 h-14 rounded-full bg-violet-500/10 flex items-center justify-center">
              <CalendarDays className="h-7 w-7 text-violet-400" />
            </div>
            <div className="text-center">
              <h3 className="text-lg font-semibold text-white mb-1">Include older tasks?</h3>
              <p className="text-white/50 text-sm">
                This will include all pending and in-progress tasks from previous weeks and months in your weekly plan, not just tasks due this week.
              </p>
            </div>
            <div className="flex gap-3 w-full mt-2">
              <Button
                variant="outline"
                className="flex-1 border-white/10 text-white/60 hover:bg-white/5"
                onClick={() => setShowPastTasksConfirm(false)}
              >
                No, keep default
              </Button>
              <Button
                className="flex-1 bg-violet-600 hover:bg-violet-700 text-white"
                onClick={() => { setIncludePastTasks(true); setShowPastTasksConfirm(false); }}
              >
                Yes, include all
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Task delete confirm dialog */}
      <Dialog open={!!confirmDeleteTaskId} onOpenChange={open => { if (!open) setConfirmDeleteTaskId(null); }}>
        <DialogContent className="max-w-sm w-full bg-[#0d0b1f] border-white/10 text-white">
          <div className="flex flex-col items-center gap-4 py-2">
            <div className="w-14 h-14 rounded-full bg-red-500/10 flex items-center justify-center">
              <Trash2 className="h-7 w-7 text-red-400" />
            </div>
            <div className="text-center">
              <h3 className="text-lg font-semibold text-white mb-1">Delete Task?</h3>
              <p className="text-white/50 text-sm">
                This task will be permanently deleted and all assignees will be notified by email.
              </p>
            </div>
            <div className="flex gap-3 w-full mt-2">
              <Button
                variant="outline"
                className="flex-1 border-white/10 text-white/60 hover:bg-white/5"
                disabled={!!deletingTaskId}
                onClick={() => setConfirmDeleteTaskId(null)}
              >
                Cancel
              </Button>
              <Button
                className="flex-1 bg-red-500 hover:bg-red-600 text-white"
                disabled={!!deletingTaskId}
                onClick={() => { deleteTask(confirmDeleteTaskId); setConfirmDeleteTaskId(null); }}
              >
                {deletingTaskId ? (
                  <><span className="h-4 w-4 mr-2 rounded-full border-2 border-white/30 border-t-white animate-spin inline-block" /> Deleting…</>
                ) : (
                  <><Trash2 className="h-4 w-4 mr-1" /> Delete</>
                )}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Document viewer modal */}
      <Dialog open={!!viewDoc} onOpenChange={open => { if (!open) setViewDoc(null); }}>
        <DialogContent
          className="max-w-3xl w-full bg-[#0d0b1f] border-white/10 text-white p-0 gap-0"
          style={{ maxHeight: '90vh', display: 'flex', flexDirection: 'column' }}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 flex-shrink-0">
            <div className="flex items-center gap-3 min-w-0">
              {viewDoc && (
                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs border flex-shrink-0 ${{
                  agenda:   'bg-violet-500/20 text-violet-300 border-violet-500/30',
                  minutes:  'bg-sky-500/20 text-sky-300 border-sky-500/30',
                  briefing: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
                  report:   'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
                  other:    'bg-white/10 text-white/50 border-white/10',
                }[viewDoc.doc_type] || 'bg-white/10 text-white/50 border-white/10'}`}>
                  {{ agenda:'Agenda', minutes:'Minutes', briefing:'Briefing', report:'Report', other:'Other' }[viewDoc?.doc_type] || viewDoc?.doc_type}
                </span>
              )}
              <h3 className="text-white font-semibold truncate text-sm">{viewDoc?.title}</h3>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0 ml-4">
              <Button size="sm" variant="ghost" onClick={() => viewDoc && downloadDocPdf(viewDoc)}
                className="text-sky-400 hover:text-sky-300 gap-1.5 text-xs">
                <Download className="h-3.5 w-3.5" /> Download PDF
              </Button>
            </div>
          </div>

          {/* Meta */}
          {viewDoc?.created_at && (
            <div className="px-6 py-2 border-b border-white/5 flex-shrink-0">
              <p className="text-white/30 text-xs">Generated {new Date(viewDoc.created_at).toLocaleString()}</p>
            </div>
          )}

          {/* Rendered markdown content */}
          <div className="flex-1 overflow-y-auto px-6 py-5">
            {viewDoc?.content && (
              <div
                className="prose prose-invert max-w-none"
                dangerouslySetInnerHTML={{ __html: markdownToHtml(viewDoc.content) }}
              />
            )}
          </div>
        </DialogContent>
      </Dialog>
    </ErrorBoundary>
  );
};

export default ExecMeetingDashboard;
