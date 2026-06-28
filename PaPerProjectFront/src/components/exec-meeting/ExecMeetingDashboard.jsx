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
} from 'lucide-react';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import ErrorBoundary from '@/components/common/ErrorBoundary';
import execMeetingService from '@/services/execMeetingService';

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
const DateTimePicker = ({ value, onChange }) => {
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
            fromDate={new Date()}
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
    title: '', description: '', scheduled_at: '', duration_minutes: '60',
    location: '', meeting_type: 'internal',
  });

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const handleSubmit = async () => {
    if (!form.title || !form.scheduled_at) {
      toast({ title: 'Title and date are required', variant: 'destructive' });
      return;
    }
    setLoading(true);
    try {
      const payload = {
        title: form.title,
        description: form.description,
        scheduled_at: form.scheduled_at,
        duration_minutes: parseInt(form.duration_minutes) || 60,
        location: form.location,
        meeting_type: form.meeting_type,
      };
      await execMeetingService.createMeeting(payload);
      toast({ title: 'Meeting scheduled!' });
      onCreated();
      onClose();
      setForm({ title: '', description: '', scheduled_at: '', duration_minutes: '60', location: '', meeting_type: 'internal' });
    } catch (err) {
      toast({ title: 'Failed to schedule meeting', description: err.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-lg bg-[#0d0b1f] border-white/10 text-white">
        <DialogHeader>
          <DialogTitle>Schedule Meeting</DialogTitle>
          <DialogDescription className="text-white/50">Fill in the meeting details below.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1">
            <Label>Title *</Label>
            <Input value={form.title} onChange={e => set('title', e.target.value)} placeholder="Q3 Strategy Review" className="bg-white/5 border-white/10 text-white" />
          </div>
          <div className="space-y-1">
            <Label>Description</Label>
            <Textarea value={form.description} onChange={e => set('description', e.target.value)} placeholder="Meeting agenda..." className="bg-white/5 border-white/10 text-white" rows={3} />
          </div>
          <div className="space-y-1">
            <Label>Date & Time *</Label>
            <DateTimePicker value={form.scheduled_at} onChange={v => set('scheduled_at', v)} />
          </div>
          <div className="space-y-1">
            <Label>Duration (minutes)</Label>
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
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Location</Label>
              <Input value={form.location} onChange={e => set('location', e.target.value)} placeholder="Conference Room A" className="bg-white/5 border-white/10 text-white" />
            </div>
            <div className="space-y-1">
              <Label>Type</Label>
              <Select value={form.meeting_type} onValueChange={v => set('meeting_type', v)}>
                <SelectTrigger className="bg-white/5 border-white/10 text-white">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {['internal','external','one_on_one','team','client','board'].map(t => (
                    <SelectItem key={t} value={t}>{t.replace('_', ' ')}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
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

// ── Add task dialog ─────────────────────────────────────────────────────────
const AddTaskDialog = ({ open, onClose, onCreated }) => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ title: '', description: '', priority: 'medium', due_date: '' });
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const handleSubmit = async () => {
    if (!form.title) {
      toast({ title: 'Title is required', variant: 'destructive' });
      return;
    }
    setLoading(true);
    try {
      await execMeetingService.createTask({ ...form });
      toast({ title: 'Task created!' });
      onCreated();
      onClose();
      setForm({ title: '', description: '', priority: 'medium', due_date: '' });
    } catch (err) {
      toast({ title: 'Failed to create task', description: err.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-md bg-[#0d0b1f] border-white/10 text-white">
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
          <div className="space-y-1">
            <Label>Priority</Label>
            <Select value={form.priority} onValueChange={v => set('priority', v)}>
              <SelectTrigger className="bg-white/5 border-white/10 text-white">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {['low','medium','high','critical'].map(p => (
                  <SelectItem key={p} value={p}>{p}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Due Date</Label>
            <DateOnlyPicker value={form.due_date} onChange={v => set('due_date', v)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} className="border-white/10 text-white/70">Cancel</Button>
          <Button onClick={handleSubmit} disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
            Add Task
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
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

  // AI Documents
  const [aiDocLoading, setAiDocLoading] = useState(false);
  const [aiDocType, setAiDocType] = useState('agenda');
  const [aiDocInput, setAiDocInput] = useState('');
  const [savedDocs, setSavedDocs] = useState([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [viewDoc, setViewDoc] = useState(null);   // { id, title, doc_type, content, created_at }

  useEffect(() => { loadStats(); }, []);

  useEffect(() => {
    if (activeTab === 'meetings' && meetings.length === 0) loadMeetings();
    if (activeTab === 'tasks' && tasks.length === 0) loadTasks();
    if (activeTab === 'notifications') loadNotifications();
    if (activeTab === 'overview' && !digest) loadDigest();
    if (activeTab === 'documents') loadDocuments();
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
    if (!aiDocInput.trim()) {
      toast({ title: 'Enter a meeting title or topic first', variant: 'destructive' });
      return;
    }
    setAiDocLoading(true);
    try {
      const res = await execMeetingService.generateDocument({
        action: aiDocType,
        title: aiDocInput,
        topics: [],
        duration_minutes: 60,
      });
      toast({ title: 'Document generated and saved!' });
      // Reload list so new doc appears
      loadDocuments();
      // Auto-open viewer
      if (res.document_id) {
        setViewDoc({
          id: res.document_id,
          title: `${aiDocType.charAt(0).toUpperCase() + aiDocType.slice(1)} — ${aiDocInput}`,
          doc_type: aiDocType,
          content: res.content || '',
          created_at: new Date().toISOString(),
        });
      }
      setAiDocInput('');
    } catch (err) {
      toast({ title: 'AI generation failed', description: err.message, variant: 'destructive' });
    } finally {
      setAiDocLoading(false);
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

  const downloadDocPdf = (doc) => {
    // Build a printable HTML page and trigger browser print-to-PDF
    const html = `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<title>${doc.title}</title>
<style>
  body { font-family: Georgia, serif; max-width: 780px; margin: 40px auto; color: #111; line-height: 1.7; }
  h1,h2,h3 { color: #1a1a2e; } pre { white-space: pre-wrap; }
  @media print { body { margin: 20mm; } }
</style>
</head>
<body>
<h1>${doc.title}</h1>
<p style="color:#666;font-size:0.85em">Generated: ${new Date(doc.created_at).toLocaleString()}</p>
<hr/>
<div style="white-space:pre-wrap;font-family:inherit">${doc.content.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>
</body>
</html>`;
    const blob = new Blob([html], { type: 'text/html' });
    const url  = URL.createObjectURL(blob);
    const win  = window.open(url, '_blank');
    if (win) { win.onload = () => { win.print(); }; }
  };

  const markNotifRead = async (id) => {
    try {
      await execMeetingService.markNotificationRead(id);
      setNotifications(prev => prev.map(n => n.id === id ? { ...n, is_read: true } : n));
    } catch {
      toast({ title: 'Failed to mark as read', variant: 'destructive' });
    }
  };

  const deleteTask = async (id) => {
    try {
      await execMeetingService.deleteTask(id);
      setTasks(prev => prev.filter(t => t.id !== id));
      toast({ title: 'Task deleted' });
    } catch {
      toast({ title: 'Failed to delete task', variant: 'destructive' });
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
                <p className="text-white/40 text-xs">{m.scheduled_at ? new Date(m.scheduled_at).toLocaleString() : '—'}</p>
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
          {meetings.map(m => (
            <div key={m.id} className="flex items-center gap-4 px-4 py-3" style={ROW_STYLE}>
              <div className="rounded-lg p-2 bg-violet-500/20 flex-shrink-0">
                <CalendarClock className="h-4 w-4 text-violet-400" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-white text-sm font-medium truncate">{m.title}</p>
                <p className="text-white/40 text-xs">
                  {m.scheduled_at ? new Date(m.scheduled_at).toLocaleString() : '—'}
                  {m.duration_minutes ? ` · ${m.duration_minutes}min` : ''}
                  {m.location ? ` · ${m.location}` : ''}
                </p>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                {statusBadge(m.status)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const tasksPanel = () => (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-white font-semibold">Tasks</h3>
        <Button size="sm" onClick={() => setShowTaskDialog(true)}>
          <Plus className="h-4 w-4 mr-1" /> Add Task
        </Button>
      </div>
      {tasksLoading ? (
        <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-violet-400" /></div>
      ) : !Array.isArray(tasks) || tasks.length === 0 ? (
        <EmptyState icon={ListChecks} label="No tasks yet" />
      ) : (
        <div className="rounded-2xl overflow-hidden" style={CARD_STYLE}>
          {tasks.map(t => (
            <div key={t.id} className="flex items-center gap-4 px-4 py-3" style={ROW_STYLE}>
              <div className="flex-1 min-w-0">
                <p className="text-white text-sm font-medium truncate">{t.title}</p>
                <p className="text-white/40 text-xs">
                  {t.due_date ? `Due: ${t.due_date}` : 'No due date'}
                </p>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                {priorityBadge(t.priority)}
                {statusBadge(t.status)}
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button size="icon" variant="ghost" className="h-7 w-7 text-white/40 hover:text-white">
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent>
                    <DropdownMenuItem className="text-red-400" onClick={() => deleteTask(t.id)}>
                      <Trash2 className="h-4 w-4 mr-2" /> Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const calendarPanel = () => (
    <div className="space-y-4">
      <h3 className="text-white font-semibold">Calendar Planning</h3>
      <div className="rounded-2xl p-5 space-y-3" style={CARD_STYLE}>
        <p className="text-white/60 text-sm">
          Use the AI Calendar Planner to auto-schedule your tasks and find free slots for the week.
        </p>
        <Button onClick={async () => {
          toast({ title: 'Planning week…' });
          try {
            const res = await execMeetingService.planWeek();
            toast({ title: 'Week plan generated', description: res.plan?.schedule_summary || 'Done' });
          } catch (err) {
            toast({ title: 'Failed', description: err.message, variant: 'destructive' });
          }
        }}>
          <CalendarDays className="h-4 w-4 mr-2" /> Plan This Week with AI
        </Button>
      </div>
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
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1">
            <Label className="text-white/70 text-xs">Document Type</Label>
            <Select value={aiDocType} onValueChange={setAiDocType}>
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
            <Label className="text-white/70 text-xs">Meeting / Topic</Label>
            <Input
              value={aiDocInput}
              onChange={e => setAiDocInput(e.target.value)}
              placeholder="e.g. Q3 Strategy Review"
              className="bg-white/5 border-white/10 text-white"
              onKeyDown={e => e.key === 'Enter' && generateAiDoc()}
            />
          </div>
        </div>
        <Button onClick={generateAiDoc} disabled={aiDocLoading}>
          {aiDocLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <FileText className="h-4 w-4 mr-2" />}
          {aiDocLoading ? 'Generating…' : 'Generate & Save'}
        </Button>
      </div>

      {/* Document viewer (shown when a doc is open) */}
      {viewDoc && (
        <div className="rounded-2xl overflow-hidden" style={{ ...CARD_STYLE, border: '1px solid rgba(167,139,250,0.3)' }}>
          {/* Viewer toolbar */}
          <div className="flex items-center justify-between px-5 py-3 border-b border-white/10">
            <div className="flex items-center gap-3 min-w-0">
              <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs border flex-shrink-0 ${DOC_TYPE_COLORS[viewDoc.doc_type] || DOC_TYPE_COLORS.other}`}>
                {DOC_TYPE_LABELS[viewDoc.doc_type] || viewDoc.doc_type}
              </span>
              <h4 className="text-white font-medium text-sm truncate">{viewDoc.title}</h4>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <Button size="sm" variant="ghost" onClick={() => downloadDocPdf(viewDoc)}
                className="text-white/60 hover:text-white gap-1.5 text-xs">
                <span>⬇</span> PDF
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setViewDoc(null)}
                className="text-white/40 hover:text-white text-xs">
                ✕ Close
              </Button>
            </div>
          </div>
          {/* Content */}
          <div className="p-5 max-h-[520px] overflow-y-auto">
            <pre className="text-white/80 text-sm whitespace-pre-wrap font-mono leading-relaxed">{viewDoc.content}</pre>
          </div>
        </div>
      )}

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
    </ErrorBoundary>
  );
};

export default ExecMeetingDashboard;
