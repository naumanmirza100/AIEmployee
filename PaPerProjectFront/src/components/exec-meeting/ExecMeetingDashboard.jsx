import React, { useState, useEffect } from 'react';
import { format } from 'date-fns';
import {
  Card, CardContent, CardHeader, CardTitle, CardDescription,
} from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Loader2, LayoutDashboard, CalendarClock, ListChecks, CalendarDays,
  FileText, Bell, Plus, Menu, Clock, AlertTriangle,
  RefreshCw, Trash2, MoreHorizontal, ChevronRight,
  Download, Sparkles, Pencil, GraduationCap,
} from 'lucide-react';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import ErrorBoundary from '@/components/common/ErrorBoundary';
import execMeetingService from '@/services/execMeetingService';
import {
  markdownToHtml, CARD_STYLE, ROW_STYLE, fmtUtc,
  StatCard, priorityBadge, statusBadge,
  AssigneeAvatars, EmptyState, BulkSelectBar, SelectCheckbox, FilterBar, Pagination,
} from './shared';
import {
  ScheduleMeetingDialog, MeetingEditDialog,
  AddTaskDialog, TaskEditDialog,
} from './dialogs';
import { TasksPanel } from './panels/TasksPanel';
import { CalendarPanel } from './panels/CalendarPanel';
import { DocumentsPanel } from './panels/DocumentsPanel';
import { MeetingsPanel } from './panels/MeetingsPanel';
import FrontlineTutorial, { hasSeenTutorial, resetTutorial } from '@/components/frontline/FrontlineTutorial';
import { EXEC_MEETING_TOUR_STEPS, EXEC_MEETING_TOUR_KEY } from './execMeetingTourSteps';

const TAB_ITEMS = [
  { value: 'overview',      label: 'Overview',      icon: LayoutDashboard },
  { value: 'meetings',      label: 'Meetings',       icon: CalendarClock },
  { value: 'tasks',         label: 'Tasks',          icon: ListChecks },
  { value: 'calendar',      label: 'Calendar',       icon: CalendarDays },
  { value: 'documents',     label: 'Documents',      icon: FileText },
  { value: 'notifications', label: 'Notifications',  icon: Bell },
];

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

  // ── Per-tab filters (search / dropdowns / date). Server-side: each change
  // re-fetches the list with query params. `search` is debounced (see effect).
  const [meetingFilters, setMeetingFilters] = useState({ search: '', status: '', date: '', participant: '' });
  const [taskFilters, setTaskFilters] = useState({ search: '', status: '', priority: '', date: '' });
  const [docFilters, setDocFilters] = useState({ search: '', doc_type: '', date: '' });
  const [notifFilters, setNotifFilters] = useState({ search: '', category: '', unread_only: false });
  const [meetingFilterUsers, setMeetingFilterUsers] = useState([]); // for the "by user" dropdown

  // ── Pagination. `page` is the current page per tab; `*Page` meta holds the
  // backend's { page, total_pages, total, has_next, has_prev } for the controls.
  const PAGE_SIZE = 8;
  const [meetingPage, setMeetingPage] = useState(1);
  const [taskPage, setTaskPage] = useState(1);
  const [docPage, setDocPage] = useState(1);
  const [notifPage, setNotifPage] = useState(1);
  const [meetingPageMeta, setMeetingPageMeta] = useState(null);
  const [taskPageMeta, setTaskPageMeta] = useState(null);
  const [docPageMeta, setDocPageMeta] = useState(null);
  const [notifPageMeta, setNotifPageMeta] = useState(null);

  // Dialogs
  const [showMeetingDialog, setShowMeetingDialog] = useState(false);
  const [showTaskDialog, setShowTaskDialog] = useState(false);
  const [expandedTaskId, setExpandedTaskId] = useState(null); // inline-expanded task
  const [expandedSubtasksId, setExpandedSubtasksId] = useState(null); // task whose subtasks accordion is open
  const [focusMeetingId, setFocusMeetingId] = useState(null); // meeting to highlight/scroll to (from a notification)
  const [editingTask, setEditingTask] = useState(null);
  const [editingMeeting, setEditingMeeting] = useState(null);
  const [confirmDeleteTaskId, setConfirmDeleteTaskId] = useState(null);
  const [subtaskParentTask, setSubtaskParentTask] = useState(null); // task being added a subtask to

  // Bulk-select state (each is a Set of ids) for Tasks / Documents / Notifications
  const [selectedTaskIds, setSelectedTaskIds] = useState(() => new Set());
  const [selectedDocIds, setSelectedDocIds] = useState(() => new Set());
  const [selectedNotifIds, setSelectedNotifIds] = useState(() => new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);

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
  const [workStartHour, setWorkStartHour] = useState(9);  // task-scheduling window
  const [workEndHour, setWorkEndHour] = useState(17);

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
  // Action-item ids the user has already converted to a task this session — used
  // only to hide the "Convert to task" button afterwards (the action item data
  // itself is intentionally left untouched).
  const [convertedActionItemIds, setConvertedActionItemIds] = useState(() => new Set());

  // Guided tour
  const [tourOpen, setTourOpen] = useState(false);

  useEffect(() => { loadStats(); }, []);

  // Auto-launch the tour the first time this user lands on the dashboard.
  useEffect(() => {
    if (!hasSeenTutorial(EXEC_MEETING_TOUR_KEY)) {
      const t = setTimeout(() => setTourOpen(true), 600);
      return () => clearTimeout(t);
    }
  }, []);

  const handleReplayTour = () => {
    resetTutorial(EXEC_MEETING_TOUR_KEY);
    setTourOpen(true);
  };

  useEffect(() => {
    if (activeTab === 'meetings') { if (meetings.length === 0) loadMeetings(); if (meetingFilterUsers.length === 0) loadMeetingFilterUsers(); }
    if (activeTab === 'tasks' && tasks.length === 0) loadTasks();
    if (activeTab === 'notifications') loadNotifications();
    if (activeTab === 'overview' && !digest) loadDigest();
    if (activeTab === 'documents') { loadDocuments(); loadMeetings(); }
  }, [activeTab]);

  // ── Filter-driven refetch. The search box is debounced (300ms) so typing
  // doesn't fire a request per keystroke; dropdown / date changes apply at once.
  // Each effect only runs while its tab is active to avoid background fetches.
  // Any filter change jumps back to page 1 (the old page may not exist in the
  // newly-filtered, smaller result set).
  useEffect(() => {
    if (activeTab !== 'meetings') return;
    const t = setTimeout(() => { setMeetingPage(1); loadMeetings(meetingFilters, 1); }, 300);
    return () => clearTimeout(t);
  }, [meetingFilters.search, meetingFilters.status, meetingFilters.date, meetingFilters.participant]);

  useEffect(() => {
    if (activeTab !== 'tasks') return;
    const t = setTimeout(() => { setTaskPage(1); loadTasks(taskFilters, 1); }, 300);
    return () => clearTimeout(t);
  }, [taskFilters.search, taskFilters.status, taskFilters.priority, taskFilters.date]);

  useEffect(() => {
    if (activeTab !== 'documents') return;
    const t = setTimeout(() => { setDocPage(1); loadDocuments(docFilters, 1); }, 300);
    return () => clearTimeout(t);
  }, [docFilters.search, docFilters.doc_type, docFilters.date]);

  useEffect(() => {
    if (activeTab !== 'notifications') return;
    const t = setTimeout(() => { setNotifPage(1); loadNotifications(notifFilters, 1); }, 300);
    return () => clearTimeout(t);
  }, [notifFilters.search, notifFilters.category, notifFilters.unread_only]);

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

  const loadMeetings = async (filters = meetingFilters, page = meetingPage) => {
    setMeetingsLoading(true);
    try {
      const data = await execMeetingService.getMeetings({ ...filters, page, page_size: PAGE_SIZE });
      setMeetings(data.meetings || []);
      setMeetingPageMeta(data.pagination || null);
    } catch {
      setMeetings([]);
      setMeetingPageMeta(null);
    } finally {
      setMeetingsLoading(false);
    }
  };

  // Change page: update state + fetch that page immediately (the debounced
  // filter effects don't watch `page`, so we drive the fetch here).
  const goToMeetingPage = (p) => { setMeetingPage(p); loadMeetings(meetingFilters, p); };

  // One-time load of the user list that powers the Meetings "by user" dropdown.
  const loadMeetingFilterUsers = async () => {
    try {
      const data = await execMeetingService.getMeetingFilterUsers();
      setMeetingFilterUsers(data.users || []);
    } catch {
      setMeetingFilterUsers([]);
    }
  };

  // The reload button — re-fetches the meeting list AND re-fetches any Notes /
  // Participants panel that's currently open (those are cached separately, so a
  // plain loadMeetings left them showing stale data until a full browser
  // reload).
  const refreshMeetings = async () => {
    await loadMeetings();
    if (notesOpenId) {
      try {
        const res = await execMeetingService.getMeetingNotes(notesOpenId);
        setMeetingNotes(prev => ({ ...prev, [notesOpenId]: res.notes || null }));
      } catch { /* leave cached notes */ }
    }
    if (participantsOpenId) {
      try {
        const res = await execMeetingService.getParticipants(participantsOpenId);
        setParticipantsMap(prev => ({ ...prev, [participantsOpenId]: res.participants || [] }));
      } catch { /* leave cached participants */ }
    }
  };

  const loadTasks = async (filters = taskFilters, page = taskPage) => {
    setTasksLoading(true);
    try {
      const data = await execMeetingService.getTasks({ ...filters, page, page_size: PAGE_SIZE });
      setTasks(data.tasks || []);
      setTaskPageMeta(data.pagination || null);
    } catch {
      setTasks([]);
      setTaskPageMeta(null);
    } finally {
      setTasksLoading(false);
    }
  };

  const loadNotifications = async (filters = notifFilters, page = notifPage) => {
    setNotifsLoading(true);
    try {
      const data = await execMeetingService.getNotifications({ ...filters, page, page_size: PAGE_SIZE });
      setNotifications(data.notifications || []);
      setNotifPageMeta(data.pagination || null);
    } catch {
      setNotifications([]);
      setNotifPageMeta(null);
    } finally {
      setNotifsLoading(false);
    }
  };
  const goToTaskPage = (p) => { setTaskPage(p); loadTasks(taskFilters, p); };
  const goToNotifPage = (p) => { setNotifPage(p); loadNotifications(notifFilters, p); };

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

  const loadDocuments = async (filters = docFilters, page = docPage) => {
    setDocsLoading(true);
    try {
      const data = await execMeetingService.listDocuments({ ...filters, page, page_size: PAGE_SIZE });
      setSavedDocs(data.documents || []);
      setDocPageMeta(data.pagination || null);
    } catch {
      setSavedDocs([]);
      setDocPageMeta(null);
    } finally {
      setDocsLoading(false);
    }
  };
  const goToDocPage = (p) => { setDocPage(p); loadDocuments(docFilters, p); };

  // When a meeting is linked in the document generator, pull whatever the AI
  // Notetaker already extracted for it (summary, key decisions, action items)
  // and pre-fill the "Meeting Summary / Key Discussion Points" box for a
  // Minutes document. Meeting rows from listMeetings don't carry notes, so we
  // fetch them here. Falls back to the meeting's description if there are no
  // notes yet.
  const applyMeetingNotesToDoc = async (meetingId, docType) => {
    if (docType !== 'minutes') return;
    // Always clear first so switching to a meeting with no notes doesn't leave
    // the previous meeting's summary sitting in the box.
    setAiDocSummary('');
    try {
      const res = await execMeetingService.getMeetingNotes(meetingId);
      const n = res.notes;
      if (!n) return;
      const parts = [];
      if (n.ai_summary) parts.push(`Summary:\n${n.ai_summary}`);
      if (Array.isArray(n.key_decisions) && n.key_decisions.length) {
        parts.push('Key Decisions:\n' + n.key_decisions.map(d => `- ${d}`).join('\n'));
      }
      if (Array.isArray(n.action_items) && n.action_items.length) {
        parts.push('Action Items:\n' + n.action_items.map(a => `- ${a.title}`).join('\n'));
      }
      const text = parts.join('\n\n').trim();
      if (text) setAiDocSummary(text.slice(0, 800));
    } catch { /* no notes yet — box already cleared above */ }
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
      await execMeetingService.generateNotes(meetingId, { transcript: transcriptInput });
      // Re-fetch the full notes so the extracted action items (with their ids)
      // show up — the POST response only returns a created-count, not the list.
      const fresh = await execMeetingService.getMeetingNotes(meetingId);
      if (fresh.notes) setMeetingNotes(prev => ({ ...prev, [meetingId]: fresh.notes }));
      setTranscriptInput('');
      loadStats(); // an "action items added" notification may have been created
      toast({ title: 'Notes generated!', description: 'Summary, decisions and action items extracted.' });
    } catch (err) {
      toast({ title: 'Notetaker failed', description: err.message, variant: 'destructive' });
    } finally {
      setNotesLoading(false);
    }
  };

  // Create a standalone task from a meeting action item. The action item is
  // left untouched (no 'done' flag, no link), so we only refresh the tasks list.
  const convertActionItem = async (meetingId, itemId) => {
    try {
      await execMeetingService.convertActionItemToTask(itemId);
      setConvertedActionItemIds(prev => new Set(prev).add(itemId));
      loadTasks(); loadStats();
      toast({ title: 'Task created', description: 'Find it in the Tasks tab.' });
    } catch (err) {
      toast({ title: 'Failed to create task', description: err.message, variant: 'destructive' });
    }
  };

  // Clear a meeting's whole AI notes block (summary + decisions + non-converted
  // action items).
  const clearMeetingNotes = async (meetingId) => {
    try {
      await execMeetingService.clearMeetingNotes(meetingId);
      setMeetingNotes(prev => { const next = { ...prev }; delete next[meetingId]; return next; });
      loadStats();
      toast({ title: 'Notes cleared' });
    } catch (err) {
      toast({ title: 'Failed to clear notes', description: err.message, variant: 'destructive' });
    }
  };

  // Remove a meeting's agenda (keep the meeting itself).
  const removeMeetingAgenda = async (meetingId) => {
    try {
      await execMeetingService.updateMeeting(meetingId, { agenda: [] });
      setMeetings(prev => prev.map(m => (m.id === meetingId ? { ...m, agenda: [] } : m)));
      toast({ title: 'Agenda removed' });
    } catch (err) {
      toast({ title: 'Failed to remove agenda', description: err.message, variant: 'destructive' });
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

  // Toggle one id in a Set-based selection state.
  const toggleSelected = (setFn, id) => {
    setFn(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const bulkDeleteTasks = async () => {
    const ids = Array.from(selectedTaskIds);
    if (ids.length === 0) return;
    setBulkDeleting(true);
    try {
      await Promise.all(ids.map(id => execMeetingService.deleteTask(id)));
      setSelectedTaskIds(new Set());
      loadTasks(); loadStats();
      toast({ title: `${ids.length} task(s) deleted`, description: 'Assignees have been notified by email.' });
    } catch {
      toast({ title: 'Failed to delete some tasks', variant: 'destructive' });
      loadTasks();
    } finally { setBulkDeleting(false); }
  };

  const bulkDeleteDocs = async () => {
    const ids = Array.from(selectedDocIds);
    if (ids.length === 0) return;
    setBulkDeleting(true);
    try {
      await Promise.all(ids.map(id => execMeetingService.deleteDocument(id)));
      setSavedDocs(prev => prev.filter(d => !selectedDocIds.has(d.id)));
      setSelectedDocIds(new Set());
      toast({ title: `${ids.length} document(s) deleted` });
    } catch {
      toast({ title: 'Failed to delete some documents', variant: 'destructive' });
      loadDocuments();
    } finally { setBulkDeleting(false); }
  };

  const bulkDeleteNotifs = async () => {
    const ids = Array.from(selectedNotifIds);
    if (ids.length === 0) return;
    setBulkDeleting(true);
    try {
      await execMeetingService.bulkDeleteNotifications(ids);
      setNotifications(prev => prev.filter(n => !selectedNotifIds.has(n.id)));
      setSelectedNotifIds(new Set());
      loadStats();
      toast({ title: `${ids.length} notification(s) deleted` });
    } catch {
      toast({ title: 'Failed to delete notifications', variant: 'destructive' });
      loadNotifications();
    } finally { setBulkDeleting(false); }
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
      loadStats(); // keep the unread badge/count in sync
    } catch {
      toast({ title: 'Failed to mark as read', variant: 'destructive' });
    }
  };

  // Clicking a notification marks it read and jumps to whatever it's about —
  // the linked task (expanded) or the linked meeting's tab.
  const handleNotificationClick = (n) => {
    if (!n.is_read) markNotifRead(n.id);
    const taskId = n.data?.task_id;
    const meetingId = n.meeting_id || n.data?.meeting_id;
    if (taskId) {
      loadTasks();
      setActiveTab('tasks');
      setExpandedTaskId(taskId);
    } else if (meetingId) {
      loadMeetings();
      setActiveTab('meetings');
      setFocusMeetingId(meetingId);
    }
  };


  // ── Render ────────────────────────────────────────────────────────────────

  const overviewPanel = () => (
    <div className="space-y-6">
      {/* Stat cards */}
      <div data-tour-em="stats" className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {statsLoading ? (
          <div className="col-span-full flex justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-violet-400" />
          </div>
        ) : (
          <>
            <StatCard label="Upcoming Meetings"   value={stats?.upcoming_meetings}    icon={CalendarClock} palette="violet" />
            <StatCard label="Total Tasks"         value={stats?.total_tasks}          icon={ListChecks}    palette="sky" />
            <StatCard label="Overdue Tasks"       value={stats?.overdue_tasks}        icon={AlertTriangle} palette="rose" />
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

  const notificationsPanel = () => (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-white font-semibold flex items-center gap-2">
          <Bell className="h-4 w-4 text-amber-400" />
          Notifications
        </h3>
        <Button size="sm" variant="ghost" onClick={() => loadNotifications()} disabled={notifsLoading} className="text-white/50 hover:text-white">
          <RefreshCw className={`h-4 w-4 ${notifsLoading ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      <FilterBar
        search={notifFilters.search}
        onSearchChange={v => setNotifFilters(f => ({ ...f, search: v }))}
        searchPlaceholder="Search notifications…"
        selects={[
          {
            value: notifFilters.category,
            onChange: v => setNotifFilters(f => ({ ...f, category: v })),
            placeholder: 'All types', allLabel: 'All types',
            options: [
              { value: 'meeting', label: 'Meeting notifications' },
              { value: 'task', label: 'Task notifications' },
            ],
          },
          {
            value: notifFilters.unread_only ? 'unread' : '',
            onChange: v => setNotifFilters(f => ({ ...f, unread_only: v === 'unread' })),
            placeholder: 'Read & unread', allLabel: 'Read & unread',
            options: [{ value: 'unread', label: 'Unread only' }],
          },
        ]}
        active={!!(notifFilters.search || notifFilters.category || notifFilters.unread_only)}
        onClear={() => setNotifFilters({ search: '', category: '', unread_only: false })}
      />

      {notifsLoading ? (
        <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-violet-400" /></div>
      ) : !Array.isArray(notifications) || notifications.length === 0 ? (
        <EmptyState icon={Bell} label={(notifFilters.search || notifFilters.category || notifFilters.unread_only) ? 'No notifications match these filters' : 'No notifications'} />
      ) : (
        <>
        <BulkSelectBar
          allIds={notifications.map(n => n.id)}
          selected={selectedNotifIds}
          onToggleAll={() => setSelectedNotifIds(selectedNotifIds.size === notifications.length ? new Set() : new Set(notifications.map(n => n.id)))}
          onDelete={bulkDeleteNotifs}
          deleting={bulkDeleting}
          label="notification"
        />
        <div className="rounded-2xl overflow-hidden" style={CARD_STYLE}>
          {notifications.map(n => (
            <div
              key={n.id}
              className={`flex items-start gap-4 px-4 py-3 cursor-pointer transition-colors hover:bg-white/[0.05] ${!n.is_read ? 'bg-white/[0.03]' : ''}`}
              style={ROW_STYLE}
              onClick={() => handleNotificationClick(n)}
            >
              <SelectCheckbox
                checked={selectedNotifIds.has(n.id)}
                onChange={() => toggleSelected(setSelectedNotifIds, n.id)}
              />
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
              <div className="flex items-center gap-2 flex-shrink-0 mt-1">
                {!n.is_read && (
                  <div className="h-2 w-2 rounded-full bg-red-500" />
                )}
                {(n.data?.task_id || n.meeting_id || n.data?.meeting_id) && (
                  <ChevronRight className="h-4 w-4 text-white/30" />
                )}
              </div>
            </div>
          ))}
        </div>
        </>
      )}
      <Pagination meta={notifPageMeta} onChange={goToNotifPage} itemLabel="notification" />
    </div>
  );

  const PANEL_MAP = {
    overview: overviewPanel,
    meetings: () => (
      <MeetingsPanel
        meetings={meetings} meetingsLoading={meetingsLoading}
        notesOpenId={notesOpenId} participantsOpenId={participantsOpenId}
        meetingNotes={meetingNotes} participantsMap={participantsMap}
        pendingAddMap={pendingAddMap} confirmRemoveMap={confirmRemoveMap}
        userSearchQ={userSearchQ} userSearchLoading={userSearchLoading}
        userSearchResults={userSearchResults} transcriptInput={transcriptInput}
        notesLoading={notesLoading}
        loadMeetings={refreshMeetings} setShowMeetingDialog={setShowMeetingDialog}
        setEditingMeeting={setEditingMeeting} openParticipants={openParticipants}
        openNotes={openNotes} removeParticipant={removeParticipant}
        setConfirmRemoveMap={setConfirmRemoveMap} addParticipant={addParticipant}
        setPendingAddMap={setPendingAddMap} setUserSearchQ={setUserSearchQ}
        setUserSearchResults={setUserSearchResults} searchUsers={searchUsers}
        submitTranscript={submitTranscript} setTranscriptInput={setTranscriptInput}
        convertActionItem={convertActionItem}
        convertedActionItemIds={convertedActionItemIds}
        clearMeetingNotes={clearMeetingNotes}
        removeMeetingAgenda={removeMeetingAgenda}
        focusMeetingId={focusMeetingId} setFocusMeetingId={setFocusMeetingId}
        filters={meetingFilters} setFilters={setMeetingFilters}
        filterUsers={meetingFilterUsers}
        pageMeta={meetingPageMeta} onPageChange={goToMeetingPage}
      />
    ),
    tasks: () => (
      <TasksPanel
        tasks={tasks} tasksLoading={tasksLoading}
        expandedTaskId={expandedTaskId} expandedSubtasksId={expandedSubtasksId}
        loadTasks={loadTasks}
        setShowTaskDialog={setShowTaskDialog}
        setExpandedTaskId={setExpandedTaskId} setExpandedSubtasksId={setExpandedSubtasksId}
        setEditingTask={setEditingTask} setSubtaskParentTask={setSubtaskParentTask}
        setConfirmDeleteTaskId={setConfirmDeleteTaskId}
        selectedTaskIds={selectedTaskIds} toggleSelected={toggleSelected}
        setSelectedTaskIds={setSelectedTaskIds} bulkDeleteTasks={bulkDeleteTasks}
        bulkDeleting={bulkDeleting}
        filters={taskFilters} setFilters={setTaskFilters}
        pageMeta={taskPageMeta} onPageChange={goToTaskPage}
      />
    ),
    calendar: () => (
      <CalendarPanel
        weekPlan={weekPlan} weekPlanLoading={weekPlanLoading} includePastTasks={includePastTasks}
        setWeekPlanLoading={setWeekPlanLoading} setWeekPlan={setWeekPlan}
        setIncludePastTasks={setIncludePastTasks} setShowPastTasksConfirm={setShowPastTasksConfirm}
        workStartHour={workStartHour} setWorkStartHour={setWorkStartHour}
        workEndHour={workEndHour} setWorkEndHour={setWorkEndHour}
        toast={toast}
      />
    ),
    documents: () => (
      <DocumentsPanel
        aiDocType={aiDocType} aiDocMeetingId={aiDocMeetingId} meetings={meetings}
        aiDocInput={aiDocInput} aiDocTopics={aiDocTopics} aiDocSummary={aiDocSummary}
        aiDocContext={aiDocContext} aiDocAudience={aiDocAudience} aiDocPeriod={aiDocPeriod}
        aiDocLoading={aiDocLoading} docsLoading={docsLoading} savedDocs={savedDocs}
        setAiDocType={setAiDocType} setAiDocTopics={setAiDocTopics} setAiDocSummary={setAiDocSummary}
        setAiDocContext={setAiDocContext} setAiDocAudience={setAiDocAudience} setAiDocPeriod={setAiDocPeriod}
        setAiDocMeetingId={setAiDocMeetingId} setAiDocInput={setAiDocInput}
        generateAiDoc={generateAiDoc} loadDocuments={loadDocuments}
        applyMeetingNotesToDoc={applyMeetingNotesToDoc}
        setViewDoc={setViewDoc} downloadDocPdf={downloadDocPdf} deleteDoc={deleteDoc}
        selectedDocIds={selectedDocIds} toggleSelected={toggleSelected}
        setSelectedDocIds={setSelectedDocIds} bulkDeleteDocs={bulkDeleteDocs}
        bulkDeleting={bulkDeleting}
        filters={docFilters} setFilters={setDocFilters}
        pageMeta={docPageMeta} onPageChange={goToDocPage}
      />
    ),
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
          <div className="flex items-center gap-2">
            {/* Take the Tour */}
            <button
              type="button"
              onClick={handleReplayTour}
              data-tour-em="replay"
              title="Replay the guided tour"
              className="hidden sm:inline-flex items-center gap-2 px-3.5 py-2 rounded-lg border border-violet-400/40 bg-violet-400/10 text-violet-300 text-sm font-semibold hover:bg-violet-400/20 hover:text-violet-200 transition"
            >
              <GraduationCap className="h-4 w-4" />
              Take the Tour
            </button>
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
                    {t.value === 'notifications' && stats?.unread_notifications > 0 && (
                      <span className="ml-auto inline-flex items-center justify-center min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-white text-[10px] font-bold leading-none">
                        {stats.unread_notifications > 99 ? '99+' : stats.unread_notifications}
                      </span>
                    )}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          </div>
        </div>

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList data-tour-em="tabs" className="hidden md:flex flex-wrap gap-1.5 h-auto p-1.5 mb-6 bg-[#1a1333] border border-[#3a295a] rounded-xl">
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
                {t.value === 'notifications' && stats?.unread_notifications > 0 && (
                  <span className="ml-1 inline-flex items-center justify-center min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-white text-[10px] font-bold leading-none">
                    {stats.unread_notifications > 99 ? '99+' : stats.unread_notifications}
                  </span>
                )}
              </TabsTrigger>
            ))}
          </TabsList>

          {TAB_ITEMS.map(t => (
            <TabsContent key={t.value} value={t.value} className="mt-0" data-tour-em={`tab-${t.value}`}>
              <ErrorBoundary key={t.value}>
                {PANEL_MAP[t.value]?.()}
              </ErrorBoundary>
            </TabsContent>
          ))}
        </Tabs>
      </div>

      {/* Guided tour overlay (reuses the generic tutorial component) */}
      <FrontlineTutorial
        open={tourOpen}
        onClose={() => setTourOpen(false)}
        setActiveTab={setActiveTab}
        steps={EXEC_MEETING_TOUR_STEPS}
        storageKey={EXEC_MEETING_TOUR_KEY}
      />

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
