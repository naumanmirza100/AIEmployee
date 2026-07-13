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
import {
  markdownToHtml, CARD_STYLE, ROW_STYLE, STAT_PALETTE,
  DateTimePicker, DateOnlyPicker, StatCard, priorityBadge, statusBadge,
  AssigneeAvatars, EmptyState, validateMeetingLink,
} from './shared';
import {
  ScheduleMeetingDialog, MeetingEditDialog, AssigneePicker,
  AddTaskDialog, TaskEditDialog,
} from './dialogs';

const TAB_ITEMS = [
  { value: 'overview',      label: 'Overview',      icon: LayoutDashboard },
  { value: 'meetings',      label: 'Meetings',       icon: CalendarClock },
  { value: 'tasks',         label: 'Tasks',          icon: ListChecks },
  { value: 'calendar',      label: 'Calendar',       icon: CalendarDays },
  { value: 'documents',     label: 'Documents',      icon: FileText },
  { value: 'notifications', label: 'Notifications',  icon: Bell },
];

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
  const [subtaskParentTask, setSubtaskParentTask] = useState(null); // task being added a subtask to

  // AI Documents
  const [aiDocLoading, setAiDocLoading] = useState(false);
  const [aiDocType, setAiDocType] = useState('agenda');
  const [aiDocInput, setAiDocInput] = useState('');
  const [aiDocMeetingId, setAiDocMeetingId] = useState('');
  const [aiDocTopics, setAiDocTopics] = useState('');
  const [aiDocSummary, setAiDocSummary] = useState('');
  const [aiDocContext, setAiDocContext] = useState('');
  const [aiDocAudience, setAiDocAudience] = useState('');
  const [aiDocPeriod, setAiDocPeriod] = useState('');
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
    if (activeTab === 'documents') { loadDocuments(); loadMeetings(); }
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
        ? aiDocTopics.split(',').map(t => t.trim().slice(0, 40)).filter(Boolean)
        : [];

      const payload = {
        action: aiDocType,
        title: resolvedTitle,
        topics: resolvedTopics,
        duration_minutes: resolvedDuration,
        attendees: resolvedAttendees,
      };

      if (linkedMeeting) {
        payload.meeting_id = linkedMeeting.id;
        if (linkedMeeting.scheduled_at) payload.scheduled_at = linkedMeeting.scheduled_at;
      }
      if (aiDocType === 'minutes') payload.summary = aiDocSummary.trim();
      if (aiDocType === 'briefing') {
        payload.topic = resolvedTitle;
        if (aiDocContext.trim()) payload.context = aiDocContext.trim();
        if (aiDocAudience.trim()) payload.audience = aiDocAudience.trim();
      }
      if (aiDocType === 'report') {
        if (aiDocPeriod.trim()) payload.period = aiDocPeriod.trim();
        if (aiDocContext.trim()) payload.context = aiDocContext.trim();
        payload.report_type = resolvedTitle;
      }

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
      setAiDocContext('');
      setAiDocAudience('');
      setAiDocPeriod('');
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
      // id may belong to a top-level task or to a subtask nested under one —
      // strip it from both places so the row disappears immediately.
      setTasks(prev => prev
        .filter(t => t.id !== id)
        .map(t => (t.subtasks?.some(st => st.id === id)
          ? { ...t, subtasks: t.subtasks.filter(st => st.id !== id), subtask_count: (t.subtask_count || 1) - 1 }
          : t)));
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

            {/* Pending Action Items */}
            {Array.isArray(digest.pending_action_items) && digest.pending_action_items.length > 0 && (
              <div className="rounded-xl p-3 bg-amber-500/10 border border-amber-500/20">
                <p className="text-amber-300 text-xs font-semibold uppercase tracking-wide mb-2 flex items-center gap-1.5">
                  <AlertTriangle className="h-3 w-3" /> Pending Action Items ({digest.pending_action_items.length})
                </p>
                <ul className="space-y-1.5">
                  {digest.pending_action_items.map((a, i) => (
                    <li key={i} className="flex items-start gap-2 text-white/80 text-xs">
                      <ChevronRight className="h-3 w-3 mt-0.5 flex-shrink-0 text-amber-400" />
                      <span>
                        <span className="font-medium">{a.title}</span>
                        {a.meeting && <span className="text-white/40 ml-1">· {a.meeting}</span>}
                        {a.due_date && <span className="text-amber-400/70 ml-1">· due {a.due_date}</span>}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Due / Overdue Tasks */}
            {Array.isArray(digest.due_tasks) && digest.due_tasks.length > 0 && (
              <div className="rounded-xl p-3 bg-rose-500/10 border border-rose-500/20">
                <p className="text-rose-300 text-xs font-semibold uppercase tracking-wide mb-2 flex items-center gap-1.5">
                  <AlertTriangle className="h-3 w-3" /> Due / Overdue Tasks ({digest.due_tasks.length})
                </p>
                <ul className="space-y-1.5">
                  {digest.due_tasks.map((t, i) => (
                    <li key={i} className="flex items-start gap-2 text-white/80 text-xs">
                      <ChevronRight className="h-3 w-3 mt-0.5 flex-shrink-0 text-rose-400" />
                      <span>
                        <span className="font-medium">{t.title}</span>
                        {t.due_date && <span className="text-rose-400/70 ml-1">· due {t.due_date}</span>}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

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
        <h3 className="text-white font-semibold flex items-center gap-2">
          <CalendarClock className="h-4 w-4 text-violet-400" />
          All Meetings
        </h3>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={loadMeetings} disabled={meetingsLoading} className="text-white/40 hover:text-white">
            <RefreshCw className={`h-3.5 w-3.5 ${meetingsLoading ? 'animate-spin' : ''}`} />
          </Button>
          <Button size="sm" onClick={() => setShowMeetingDialog(true)} style={{ background: 'linear-gradient(90deg, #a259ff 0%, #7c3aed 100%)' }} className="text-white border-0 hover:opacity-90">
            <Plus className="h-4 w-4 mr-1" /> Schedule
          </Button>
        </div>
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
        <h3 className="text-white font-semibold flex items-center gap-2">
          <ListChecks className="h-4 w-4 text-sky-400" />
          Tasks
        </h3>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={loadTasks} disabled={tasksLoading} className="text-white/40 hover:text-white">
            <RefreshCw className={`h-3.5 w-3.5 ${tasksLoading ? 'animate-spin' : ''}`} />
          </Button>
          <Button size="sm" variant="outline"
            onClick={runAiPrioritize} disabled={prioritizeLoading || tasks.length === 0}
            className="border-violet-500/40 text-violet-300 hover:bg-violet-500/10 text-xs gap-1.5">
            {prioritizeLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
            AI Prioritize
          </Button>
          <Button size="sm" onClick={() => setShowTaskDialog(true)} style={{ background: 'linear-gradient(90deg, #a259ff 0%, #7c3aed 100%)' }} className="text-white border-0 hover:opacity-90">
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
            <div className="flex items-center gap-2">
              <Button size="sm" variant="ghost" className="text-white/40 hover:text-white h-6 px-2 text-xs gap-1"
                onClick={async () => {
                  try {
                    const { default: jsPDF } = await import('jspdf');
                    const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
                    const pageW = pdf.internal.pageSize.getWidth();
                    const pageH = pdf.internal.pageSize.getHeight();
                    const margin = 18;
                    const contentW = pageW - margin * 2;

                    pdf.setFillColor(109, 40, 217);
                    pdf.rect(0, 0, pageW, 12, 'F');

                    pdf.setFont('helvetica', 'bold');
                    pdf.setFontSize(18);
                    pdf.setTextColor(30, 10, 60);
                    pdf.text('AI Task Prioritization', margin, 24);
                    let y = 32;

                    pdf.setFont('helvetica', 'normal');
                    pdf.setFontSize(8.5);
                    pdf.setTextColor(120, 100, 160);
                    pdf.text(`Generated by AI Executive Meeting Assistant · ${new Date().toLocaleDateString()}`, margin, y);
                    y += 5;
                    pdf.setDrawColor(109, 40, 217); pdf.setLineWidth(0.4);
                    pdf.line(margin, y, pageW - margin, y); y += 7;

                    prioritizeResult.forEach((t, i) => {
                      if (y > pageH - 25) { pdf.addPage(); y = 18; }
                      const priorityColors = { critical: [185,28,28], high: [194,65,12], medium: [161,98,7], low: [21,128,61] };
                      const [r,g,b] = priorityColors[t.priority] || [109,40,217];
                      pdf.setFillColor(r, g, b);
                      pdf.roundedRect(margin, y - 3, 18, 5.5, 1, 1, 'F');
                      pdf.setFont('helvetica', 'bold'); pdf.setFontSize(7); pdf.setTextColor(255,255,255);
                      pdf.text((t.priority || 'medium').toUpperCase(), margin + 1.5, y + 1);

                      pdf.setFont('helvetica', 'bold'); pdf.setFontSize(11); pdf.setTextColor(30,10,60);
                      const titleW = pdf.splitTextToSize(`${i+1}. ${t.title || 'Untitled Task'}`, contentW - 22);
                      pdf.text(titleW, margin + 21, y + 1);
                      y += titleW.length * 6 + 2;

                      if (t.ai_reasoning) {
                        pdf.setFont('helvetica', 'normal'); pdf.setFontSize(9.5); pdf.setTextColor(80,60,120);
                        const rLines = pdf.splitTextToSize(t.ai_reasoning, contentW - 4);
                        rLines.forEach(l => { if (y > pageH-20){pdf.addPage();y=18;} pdf.text(l, margin+2, y); y+=5; });
                      }
                      if (t.suggested_due_date) {
                        pdf.setFont('helvetica', 'italic'); pdf.setFontSize(8.5); pdf.setTextColor(109,40,217);
                        pdf.text(`Suggested deadline: ${t.suggested_due_date}`, margin+2, y); y+=5;
                      }
                      pdf.setDrawColor(220,210,240); pdf.setLineWidth(0.2);
                      pdf.line(margin, y, pageW-margin, y); y+=5;
                    });

                    const totalPages = pdf.internal.getNumberOfPages();
                    for (let i=1; i<=totalPages; i++) {
                      pdf.setPage(i); pdf.setFontSize(7.5); pdf.setTextColor(160,140,190);
                      pdf.text(`Page ${i} of ${totalPages}  ·  AI Executive Meeting Assistant`, margin, pageH-7);
                    }
                    pdf.save(`task-prioritization-${new Date().toISOString().slice(0,10)}.pdf`);
                  } catch(err) {
                    toast({ title: 'PDF download failed', description: err?.message, variant: 'destructive' });
                  }
                }}>
                <Download className="h-3 w-3" /> PDF
              </Button>
              <button onClick={() => setPrioritizeResult(null)} className="text-white/30 hover:text-white text-xs">✕ Close</button>
            </div>
          </div>
          {prioritizeResult.map((t, i) => (
            <div key={t.id || i} className="rounded-xl p-3 bg-white/5 border border-white/10 space-y-0.5">
              <div className="flex items-center gap-2">
                {priorityBadge(t.priority)}
                <p className="text-white text-xs font-medium truncate">{i+1}. {t.title || 'Untitled Task'}</p>
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
            const subtasks = t.subtasks || [];
            const subtaskDone = t.subtask_done_count || 0;
            const subtaskTotal = t.subtask_count ?? subtasks.length;
            return (
              <div key={t.id} style={ROW_STYLE}>
                {/* ── Row ── */}
                <div
                  className="flex items-center gap-4 px-4 py-3 cursor-pointer hover:bg-white/[0.04] transition-colors"
                  onClick={() => setExpandedTaskId(isOpen ? null : t.id)}
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-white text-sm font-medium truncate">{t.title}</p>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <p className="text-white/40 text-xs">
                        {t.due_date ? `Due: ${t.due_date}` : 'No due date'}
                      </p>
                      {subtaskTotal > 0 && (
                        <span className="text-white/30 text-xs flex items-center gap-1">
                          · <ListChecks className="h-3 w-3" />{subtaskDone}/{subtaskTotal}
                        </span>
                      )}
                      <AssigneeAvatars assignees={t.assignees} />
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {priorityBadge(t.priority)}
                    {statusBadge(t.status)}
                    <ChevronRight className={`h-4 w-4 text-white/30 transition-transform ${isOpen ? 'rotate-90' : ''}`} />
                  </div>
                </div>

                {/* ── Inline detail panel ── */}
                {isOpen && (
                  <div className="px-4 pb-4 pt-2 border-t border-white/5 space-y-3">
                    {t.description && (
                      <p className="text-white/60 text-xs whitespace-pre-wrap">{t.description}</p>
                    )}
                    {(t.assignees || []).length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {t.assignees.map(a => (
                          <span key={a.id} className="inline-flex items-center gap-1.5 pl-1 pr-2.5 py-0.5 rounded-full bg-violet-500/20 border border-violet-500/30 text-violet-200 text-xs">
                            <span className="h-4 w-4 rounded-full bg-violet-500/40 flex items-center justify-center text-[9px] font-semibold">
                              {a.full_name?.[0]?.toUpperCase() || '?'}
                            </span>
                            {a.full_name}
                          </span>
                        ))}
                      </div>
                    )}
                    {t.ai_reasoning && (
                      <p className="text-white/40 text-xs italic">{t.ai_reasoning}</p>
                    )}
                    <div className="flex gap-2">
                      <Button size="sm" variant="outline"
                        className="border-violet-500/40 text-violet-300 hover:bg-violet-500/10 text-xs h-7 px-3"
                        onClick={e => { e.stopPropagation(); setEditingTask(t); }}>
                        <Pencil className="h-3 w-3 mr-1" /> Edit
                      </Button>
                      <Button size="sm" variant="outline"
                        className="border-sky-500/40 text-sky-300 hover:bg-sky-500/10 text-xs h-7 px-3"
                        onClick={e => { e.stopPropagation(); setSubtaskParentTask(t); }}>
                        <Plus className="h-3 w-3 mr-1" /> Add Subtask
                      </Button>
                      <Button size="sm" variant="ghost"
                        className="text-red-400 hover:text-red-300 hover:bg-red-500/10 text-xs h-7 px-3"
                        onClick={e => { e.stopPropagation(); setConfirmDeleteTaskId(t.id); }}>
                        <Trash2 className="h-3 w-3 mr-1" /> Delete
                      </Button>
                    </div>

                    {/* Subtasks */}
                    {subtasks.length > 0 && (
                      <div className="space-y-1.5 pt-1">
                        <p className="text-white/30 text-[10px] uppercase tracking-wide">Subtasks ({subtaskDone}/{subtaskTotal})</p>
                        {subtasks.map(st => (
                          <div key={st.id}
                            className="flex items-center gap-3 rounded-lg px-3 py-2 bg-white/[0.03] border border-white/5 cursor-pointer hover:bg-white/[0.06]"
                            onClick={e => { e.stopPropagation(); setEditingTask(st); }}>
                            <div className="flex-1 min-w-0">
                              <p className={`text-xs font-medium truncate ${st.status === 'done' ? 'text-white/40 line-through' : 'text-white/80'}`}>{st.title}</p>
                              {st.due_date && <p className="text-white/30 text-[10px]">Due: {st.due_date}</p>}
                            </div>
                            <AssigneeAvatars assignees={st.assignees} size="sm" />
                            {priorityBadge(st.priority)}
                            {statusBadge(st.status)}
                            <button
                              className="text-white/20 hover:text-red-400 text-xs px-1"
                              onClick={e => { e.stopPropagation(); setConfirmDeleteTaskId(st.id); }}>
                              <Trash2 className="h-3 w-3" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
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
          <div className="flex items-center gap-2">
            {weekPlan && (
              <Button size="sm" variant="ghost" onClick={async () => {
                setWeekPlanLoading(true);
                try {
                  const today = new Date();
                  const weekStart = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;
                  const res = await execMeetingService.planWeek({ include_past_tasks: includePastTasks, week_start: weekStart });
                  setWeekPlan(res.plan || res);
                  toast({ title: 'Plan refreshed!' });
                } catch (err) {
                  toast({ title: 'Refresh failed', description: err.message, variant: 'destructive' });
                } finally { setWeekPlanLoading(false); }
              }} disabled={weekPlanLoading} className="text-white/40 hover:text-white">
                <RefreshCw className={`h-3.5 w-3.5 ${weekPlanLoading ? 'animate-spin' : ''}`} />
              </Button>
            )}
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
            }} disabled={weekPlanLoading} style={{ background: 'linear-gradient(90deg, #a259ff 0%, #7c3aed 100%)' }} className="text-white border-0 hover:opacity-90">
              {weekPlanLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <CalendarDays className="h-4 w-4 mr-2" />}
              {weekPlanLoading ? 'Planning…' : 'Plan This Week'}
            </Button>
          </div>
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
              onClick={async () => {
                try {
                  const { default: jsPDF } = await import('jspdf');
                  const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
                  const pageW = pdf.internal.pageSize.getWidth();
                  const pageH = pdf.internal.pageSize.getHeight();
                  const margin = 18;
                  const contentW = pageW - margin * 2;
                  const weekLabel = weekPlan.week_start || '';

                  const checkPage = (y, needed = 8) => {
                    if (y > pageH - needed) { pdf.addPage(); return 18; }
                    return y;
                  };

                  // Purple header bar
                  pdf.setFillColor(109, 40, 217);
                  pdf.rect(0, 0, pageW, 12, 'F');

                  // Title
                  pdf.setFont('helvetica', 'bold');
                  pdf.setFontSize(18);
                  pdf.setTextColor(30, 10, 60);
                  const titleText = `AI Weekly Plan${weekLabel ? ' — ' + weekLabel : ''}`;
                  const titleLines = pdf.splitTextToSize(titleText, contentW);
                  pdf.text(titleLines, margin, 24);
                  let y = 24 + titleLines.length * 7;

                  // Meta line
                  pdf.setFont('helvetica', 'normal');
                  pdf.setFontSize(8.5);
                  pdf.setTextColor(120, 100, 160);
                  pdf.text('Generated by AI Executive Meeting Assistant', margin, y);
                  y += 5;

                  // Divider
                  pdf.setDrawColor(109, 40, 217);
                  pdf.setLineWidth(0.4);
                  pdf.line(margin, y, pageW - margin, y);
                  y += 6;

                  // Summary
                  if (weekPlan.weekly_summary) {
                    y = checkPage(y, 14);
                    pdf.setFont('helvetica', 'bold');
                    pdf.setFontSize(10);
                    pdf.setTextColor(76, 29, 149);
                    pdf.text('SUMMARY', margin, y);
                    y += 5;
                    pdf.setFont('helvetica', 'normal');
                    pdf.setFontSize(10);
                    pdf.setTextColor(40, 30, 60);
                    const sumLines = pdf.splitTextToSize(weekPlan.weekly_summary, contentW);
                    sumLines.forEach(l => { y = checkPage(y); pdf.text(l, margin, y); y += 5.5; });
                    y += 3;
                  }

                  // Conflicts
                  if (weekPlan.conflicts_detected?.length) {
                    y = checkPage(y, 14);
                    pdf.setFont('helvetica', 'bold');
                    pdf.setFontSize(10);
                    pdf.setTextColor(185, 28, 28);
                    pdf.text('CONFLICTS DETECTED', margin, y);
                    y += 5;
                    pdf.setFont('helvetica', 'normal');
                    pdf.setFontSize(10);
                    pdf.setTextColor(40, 30, 60);
                    weekPlan.conflicts_detected.forEach(c => {
                      y = checkPage(y);
                      const wrapped = pdf.splitTextToSize(`• ${c}`, contentW - 4);
                      pdf.text(wrapped, margin + 3, y); y += wrapped.length * 5.5 + 1;
                    });
                    y += 3;
                  }

                  // Recommendations
                  if (weekPlan.recommendations?.length) {
                    y = checkPage(y, 14);
                    pdf.setFont('helvetica', 'bold');
                    pdf.setFontSize(10);
                    pdf.setTextColor(76, 29, 149);
                    pdf.text('RECOMMENDATIONS', margin, y);
                    y += 5;
                    pdf.setFont('helvetica', 'normal');
                    pdf.setFontSize(10);
                    pdf.setTextColor(40, 30, 60);
                    weekPlan.recommendations.forEach(r => {
                      y = checkPage(y);
                      const wrapped = pdf.splitTextToSize(`› ${r}`, contentW - 4);
                      pdf.text(wrapped, margin + 3, y); y += wrapped.length * 5.5 + 1;
                    });
                    y += 4;
                  }

                  // Day cards
                  (weekPlan.daily_plans || []).forEach(day => {
                    const hasMeetings = day.scheduled_meetings?.length > 0;
                    const hasTasks = day.suggested_task_slots?.length > 0;
                    const hasFocus = day.focus_blocks?.length > 0;
                    if (!hasMeetings && !hasTasks && !hasFocus) return;

                    y = checkPage(y, 20);

                    // Day header bar (light purple)
                    pdf.setFillColor(237, 233, 254);
                    pdf.rect(margin, y - 4, contentW, 9, 'F');
                    pdf.setFont('helvetica', 'bold');
                    pdf.setFontSize(11);
                    pdf.setTextColor(45, 27, 105);
                    pdf.text(`${day.day_name}  ${day.date}`, margin + 2, y + 2);
                    if (day.workload_level) {
                      const wlText = day.workload_level.toUpperCase();
                      pdf.setFontSize(8);
                      pdf.setTextColor(109, 40, 217);
                      pdf.text(wlText, pageW - margin - pdf.getTextWidth(wlText), y + 2);
                    }
                    y += 8;

                    if (hasMeetings) {
                      y = checkPage(y, 8);
                      pdf.setFont('helvetica', 'bold'); pdf.setFontSize(8.5); pdf.setTextColor(109, 40, 217);
                      pdf.text('MEETINGS', margin + 2, y); y += 4.5;
                      pdf.setFont('helvetica', 'normal'); pdf.setFontSize(10); pdf.setTextColor(40, 30, 60);
                      day.scheduled_meetings.forEach(m => {
                        y = checkPage(y);
                        const title = typeof m === 'string' ? m : m.title;
                        const timePart = m.time ? `  ${m.time}` : '';
                        const durPart = m.duration_minutes ? `  (${m.duration_minutes}min)` : '';
                        const wrapped = pdf.splitTextToSize(`• ${title}${timePart}${durPart}`, contentW - 6);
                        pdf.text(wrapped, margin + 4, y); y += wrapped.length * 5.5 + 1;
                      });
                      y += 2;
                    }

                    if (hasTasks) {
                      y = checkPage(y, 8);
                      pdf.setFont('helvetica', 'bold'); pdf.setFontSize(8.5); pdf.setTextColor(109, 40, 217);
                      pdf.text('TASK SLOTS', margin + 2, y); y += 4.5;
                      pdf.setFont('helvetica', 'normal'); pdf.setFontSize(10); pdf.setTextColor(40, 30, 60);
                      day.suggested_task_slots.forEach(s => {
                        y = checkPage(y);
                        const durPart = s.duration_minutes ? `  (${s.duration_minutes}min)` : '';
                        const wrapped = pdf.splitTextToSize(`${s.time}  ${s.task}${durPart}`, contentW - 6);
                        pdf.setTextColor(109, 40, 217);
                        pdf.text(s.time, margin + 4, y);
                        pdf.setTextColor(40, 30, 60);
                        const taskW = pdf.splitTextToSize(`${s.task}${durPart}`, contentW - 6 - 14);
                        pdf.text(taskW, margin + 18, y); y += Math.max(wrapped.length, taskW.length) * 5.5 + 1;
                      });
                      y += 2;
                    }

                    if (hasFocus) {
                      y = checkPage(y, 8);
                      pdf.setFont('helvetica', 'bold'); pdf.setFontSize(8.5); pdf.setTextColor(109, 40, 217);
                      pdf.text('FOCUS BLOCKS', margin + 2, y); y += 4.5;
                      pdf.setFont('helvetica', 'normal'); pdf.setFontSize(10); pdf.setTextColor(40, 30, 60);
                      day.focus_blocks.forEach(b => {
                        y = checkPage(y);
                        pdf.setTextColor(109, 40, 217);
                        pdf.text(`${b.start}–${b.end}`, margin + 4, y);
                        pdf.setTextColor(40, 30, 60);
                        pdf.text(b.label || 'Deep Work', margin + 28, y);
                        y += 6;
                      });
                      y += 2;
                    }

                    // Thin divider between days
                    pdf.setDrawColor(200, 190, 220); pdf.setLineWidth(0.2);
                    pdf.line(margin, y, pageW - margin, y); y += 5;
                  });

                  // Page numbers
                  const totalPages = pdf.internal.getNumberOfPages();
                  for (let i = 1; i <= totalPages; i++) {
                    pdf.setPage(i);
                    pdf.setFontSize(7.5); pdf.setTextColor(160, 140, 190);
                    pdf.text(`Page ${i} of ${totalPages}  ·  AI Executive Meeting Assistant`, margin, pageH - 7);
                  }

                  pdf.save(`weekly-plan${weekLabel ? '-' + weekLabel : ''}.pdf`);
                } catch (err) {
                  toast({ title: 'PDF download failed', description: err?.message || 'Please try again.', variant: 'destructive' });
                }
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
                          {typeof m !== 'string' && m.time && (
                            <span className="text-sky-400/70 font-mono text-xs ml-1">{m.time}</span>
                          )}
                          {typeof m !== 'string' && m.duration_minutes > 0 && (
                            <span className="text-white/30 text-xs ml-auto">{m.duration_minutes}min</span>
                          )}
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
            <Select value={aiDocType} onValueChange={v => { setAiDocType(v); setAiDocTopics(''); setAiDocSummary(''); setAiDocContext(''); setAiDocAudience(''); setAiDocPeriod(''); }}>
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
            <p className="text-[11px] text-amber-400/80 leading-snug">
              ⚠ Use short topic names only (e.g. "UI Review, Budget Update"). Do not paste meeting notes or long sentences — these become agenda headings.
            </p>
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
            <div className="flex items-center justify-between">
              <Label className="text-white/70 text-xs">Meeting Summary / Key Discussion Points</Label>
              <span className={`text-xs ${aiDocSummary.length > 800 ? 'text-red-400' : aiDocSummary.length > 600 ? 'text-yellow-400' : 'text-white/30'}`}>
                {aiDocSummary.length}/800
              </span>
            </div>
            <p className="text-[11px] text-amber-400/80 leading-snug">
              ⚠ This text appears directly in the document as the Discussion Summary. Write only what was discussed in the meeting — do not paste unrelated content.
            </p>
            <textarea
              value={aiDocSummary}
              onChange={e => { if (e.target.value.length <= 800) setAiDocSummary(e.target.value); }}
              rows={5}
              placeholder="Briefly describe what was discussed, decisions made, outcomes…"
              className="w-full rounded-md px-3 py-2 text-sm text-white placeholder:text-white/30 bg-white/5 border border-white/10 resize-none focus:outline-none focus:ring-1 focus:ring-violet-500 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]"
            />
          </div>
        )}

        {/* Briefing fields */}
        {aiDocType === 'briefing' && (
          <>
            <div className="space-y-1">
              <Label className="text-white/70 text-xs">Audience <span className="text-white/30">(optional)</span></Label>
              <Input
                value={aiDocAudience}
                onChange={e => setAiDocAudience(e.target.value)}
                placeholder="e.g. Board of Directors, Executive Team"
                className="bg-white/5 border-white/10 text-white"
              />
            </div>
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <Label className="text-white/70 text-xs">Background / Context <span className="text-white/30">(optional)</span></Label>
                <span className={`text-xs ${aiDocContext.length > 800 ? 'text-red-400' : aiDocContext.length > 600 ? 'text-yellow-400' : 'text-white/30'}`}>
                  {aiDocContext.length}/800
                </span>
              </div>
              <p className="text-[11px] text-amber-400/80 leading-snug">
                ⚠ This text appears directly in the document. Write only relevant facts — do not paste raw research, chat logs, or unrelated content.
              </p>
              <textarea
                value={aiDocContext}
                onChange={e => { if (e.target.value.length <= 800) setAiDocContext(e.target.value); }}
                rows={5}
                placeholder="Describe the situation, problem, or opportunity. Key facts, risks, or data points to include…"
                className="w-full rounded-md px-3 py-2 text-sm text-white placeholder:text-white/30 bg-white/5 border border-white/10 resize-none focus:outline-none focus:ring-1 focus:ring-violet-500 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]"
              />
            </div>
          </>
        )}

        {/* Report fields */}
        {aiDocType === 'report' && (
          <>
            <div className="space-y-1">
              <Label className="text-white/70 text-xs">Period <span className="text-white/30">(optional)</span></Label>
              <Input
                value={aiDocPeriod}
                onChange={e => setAiDocPeriod(e.target.value)}
                placeholder="e.g. Q3 2026, Week of 30 Jun, July 2026"
                className="bg-white/5 border-white/10 text-white"
              />
            </div>
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <Label className="text-white/70 text-xs">Context / Progress Notes <span className="text-white/30">(optional)</span></Label>
                <span className={`text-xs ${aiDocContext.length > 800 ? 'text-red-400' : aiDocContext.length > 600 ? 'text-yellow-400' : 'text-white/30'}`}>
                  {aiDocContext.length}/800
                </span>
              </div>
              <p className="text-[11px] text-amber-400/80 leading-snug">
                ⚠ This text appears directly in the document. Write only relevant facts — do not paste raw research, chat logs, or unrelated content.
              </p>
              <textarea
                value={aiDocContext}
                onChange={e => { if (e.target.value.length <= 800) setAiDocContext(e.target.value); }}
                rows={5}
                placeholder="Describe current status, what was completed, blockers, metrics, key highlights…"
                className="w-full rounded-md px-3 py-2 text-sm text-white placeholder:text-white/30 bg-white/5 border border-white/10 resize-none focus:outline-none focus:ring-1 focus:ring-violet-500 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]"
              />
            </div>
          </>
        )}

        <div className="flex justify-end">
          <Button onClick={generateAiDoc} disabled={aiDocLoading} style={{ background: 'linear-gradient(90deg, #a259ff 0%, #7c3aed 100%)' }} className="text-white border-0 hover:opacity-90">
            {aiDocLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <FileText className="h-4 w-4 mr-2" />}
            {aiDocLoading ? 'Generating…' : 'Generate & Save'}
          </Button>
        </div>
      </div>

      {/* Saved documents list */}
      <div className="rounded-2xl overflow-hidden" style={CARD_STYLE}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-white/10">
          <h3 className="text-white font-semibold text-sm flex items-center gap-2">
            <FileText className="h-3.5 w-3.5 text-violet-400" />
            Saved Documents
          </h3>
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
        <h3 className="text-white font-semibold flex items-center gap-2">
          <Bell className="h-4 w-4 text-amber-400" />
          Notifications
        </h3>
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
          background: 'linear-gradient(90deg, #020308 0%, #020308 55%, rgba(10,37,64,0.68) 85%, rgba(14,39,71,0.52) 100%)',
          border: '1px solid rgba(162,89,255,0.13)',
          boxShadow: '0 0 40px 0 rgba(162,89,255,0.06)',
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="rounded-xl p-2.5" style={{ background: 'linear-gradient(135deg, rgba(162,89,255,0.25), rgba(124,58,237,0.15))', boxShadow: '0 0 16px 0 rgba(162,89,255,0.2)' }}>
              <CalendarClock className="h-6 w-6 text-violet-400" />
            </div>
            <div>
              <h1 className="text-white text-xl font-bold tracking-tight">Executive Meeting Assistant</h1>
              <p className="text-white/40 text-sm">Manage meetings, tasks & get AI-powered insights</p>
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
          <TabsList className="hidden md:flex flex-wrap gap-1.5 h-auto p-1.5 mb-6 bg-[#1a1333] border border-[#3a295a] rounded-xl">
            {TAB_ITEMS.map(t => (
              <TabsTrigger
                key={t.value}
                value={t.value}
                className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-all duration-200 data-[state=inactive]:text-white/50 data-[state=inactive]:hover:text-white/80 data-[state=active]:text-white data-[state=active]:border-none data-[state=inactive]:border-[#2d2342] data-[state=inactive]:border"
                style={activeTab === t.value ? {
                  background: 'linear-gradient(90deg, #a259ff 0%, #7c3aed 100%)',
                  boxShadow: '0 0 12px 0 rgba(162,89,255,0.45)',
                } : {
                  background: 'rgba(60,30,90,0.22)',
                }}
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

      <AddTaskDialog
        open={!!subtaskParentTask}
        parentTask={subtaskParentTask}
        onClose={() => setSubtaskParentTask(null)}
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
