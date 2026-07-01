import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { format, startOfDay } from 'date-fns';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Calendar } from '@/components/ui/calendar';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Calendar as CalendarIcon, Mail, Phone, Clock, CalendarClock, Briefcase, User, Star, MessageSquare, CheckCircle2, Link2, Pencil, Send, LayoutList, Columns, MoreVertical, RefreshCw, Award, Building2, Trophy, ThumbsUp, Lock, Search, ChevronLeft, ChevronRight } from 'lucide-react';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { getInterviews, updateInterview, rescheduleInterview, getJobDescriptions, submitInterviewFeedback } from '@/services/recruitmentAgentService';
import SearchableSelect from '@/components/ui/searchable-select';
import InterviewKanban from './InterviewKanban';

const Interviews = ({ onUpdate }) => {
  const { toast } = useToast();
  const [interviews, setInterviews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [decisionFilter, setDecisionFilter] = useState('');
  const [jobFilter, setJobFilter] = useState('');
  const [jobs, setJobs] = useState([]);
  // Search & date filters
  const [search, setSearch]         = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [dateFrom, setDateFrom]     = useState('');
  const [dateTo, setDateTo]         = useState('');
  // Pagination
  const [currentPage, setCurrentPage]   = useState(1);
  const [totalPages, setTotalPages]     = useState(1);
  const [totalCount, setTotalCount]     = useState(0);
  const [pageSize, setPageSize]         = useState(10);

  const [updatingId, setUpdatingId] = useState(null);
  const [pendingChange, setPendingChange] = useState(null);
  const [showRescheduleModal, setShowRescheduleModal] = useState(false);
  const [rescheduleInterviewObj, setRescheduleInterviewObj] = useState(null);
  const [reschedulePickedDate, setReschedulePickedDate] = useState(null);
  const [reschedulePickedTime, setReschedulePickedTime] = useState('');
  const [rescheduleError, setRescheduleError] = useState('');
  const [rescheduleSubmitting, setRescheduleSubmitting] = useState(false);
  const [feedbackModal, setFeedbackModal] = useState(null);
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const [meetingLinkEdit, setMeetingLinkEdit] = useState({});
  const [searchParams, setSearchParams] = useSearchParams();

  // URL-persisted — survives reload, back/forward, and tab restore
  const viewMode      = searchParams.get('view')    || 'list';
  const kanbanGroupBy = searchParams.get('groupBy') || 'status';

  const setViewMode = (v) =>
    setSearchParams((prev) => { const p = new URLSearchParams(prev); p.set('view', v); return p; }, { replace: true });

  const setKanbanGroupBy = (v) =>
    setSearchParams((prev) => { const p = new URLSearchParams(prev); p.set('groupBy', v); return p; }, { replace: true });

  // Debounce search input
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 400);
    return () => clearTimeout(t);
  }, [search]);

  // Re-fetch (reset to page 1) when any filter changes
  useEffect(() => {
    fetchInterviews(1);
    setCurrentPage(1);
  }, [statusFilter, decisionFilter, jobFilter, dateFrom, dateTo, debouncedSearch, pageSize]);

  useEffect(() => {
    fetchJobs();
  }, []);

  const fetchJobs = async () => {
    try {
      const response = await getJobDescriptions();
      if (response.status === 'success') setJobs(response.data || []);
    } catch (_) {}
  };

  const fetchInterviews = async (page = 1) => {
    try {
      setLoading(true);
      const filters = { page, page_size: pageSize };
      if (statusFilter)          filters.status    = statusFilter;
      if (decisionFilter !== '') filters.outcome   = decisionFilter;
      if (jobFilter)             filters.job_title = jobFilter;
      if (debouncedSearch)       filters.search    = debouncedSearch;
      if (dateFrom)              filters.date_from = dateFrom;
      if (dateTo)                filters.date_to   = dateTo;
      const response = await getInterviews(filters);
      if (response.status === 'success') {
        setInterviews(response.data || []);
        const pg = response.pagination;
        if (pg) {
          setTotalPages(pg.total_pages || 1);
          setTotalCount(pg.total || 0);
        }
      }
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to load interviews', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const goToPage = (page) => {
    if (page < 1 || page > totalPages) return;
    setCurrentPage(page);
    fetchInterviews(page);
  };

  const getStatusBadge = (status) => {
    const variants = {
      PENDING: 'bg-yellow-500', SCHEDULED: 'bg-green-500', COMPLETED: 'bg-blue-500',
      CANCELLED: 'bg-red-500', RESCHEDULED: 'bg-purple-500',
    };
    return <Badge className={variants[status] || 'bg-gray-500'}>{status}</Badge>;
  };

  const getOutcomeBadge = (outcome) => {
    if (!outcome) return null;
    const variants = {
      ONSITE_INTERVIEW: 'bg-indigo-500', HIRED: 'bg-emerald-600', PASSED: 'bg-teal-500', REJECTED: 'bg-red-600',
    };
    const labels = {
      ONSITE_INTERVIEW: 'Onsite Interview', HIRED: 'Hired', PASSED: 'Passed', REJECTED: 'Rejected',
    };
    return <Badge className={variants[outcome] || 'bg-gray-500'}>{labels[outcome] || outcome}</Badge>;
  };

  const STATUS_LABELS  = { PENDING: 'Pending', SCHEDULED: 'Scheduled', COMPLETED: 'Completed', CANCELLED: 'Cancelled', RESCHEDULED: 'Rescheduled' };
  const OUTCOME_LABELS = { ONSITE_INTERVIEW: 'Onsite Interview', HIRED: 'Hired', PASSED: 'Passed', REJECTED: 'Rejected', '': 'None' };

  const handleStatusChange = (interview, v) =>
    setPendingChange({ interview, type: 'status', value: v, label: STATUS_LABELS[v] || v });

  // Decision change → skip confirm modal, open feedback form directly (mandatory reason)
  const handleOutcomeChange = (interview, v) =>
    openFeedbackModal(interview, { outcome: v, label: OUTCOME_LABELS[v] || v || 'None' });

  const handleConfirmChange = async () => {
    if (!pendingChange) return;
    const { interview, type, value } = pendingChange;
    try {
      setUpdatingId(interview.id);
      const payload = type === 'status' ? { status: value } : { outcome: value || '' };
      const response = await updateInterview(interview.id, payload);
      if (response.status === 'success') {
        toast({ title: 'Updated', description: `Interview ${type} updated successfully` });
        fetchInterviews();
        if (onUpdate) onUpdate();
      }
    } catch (error) {
      toast({ title: 'Error', description: error.message || `Failed to update ${type}`, variant: 'destructive' });
    } finally {
      setUpdatingId(null);
      setPendingChange(null);
    }
  };

  const openRescheduleModal = (interview) => {
    setRescheduleInterviewObj(interview);
    setReschedulePickedDate(null);
    setReschedulePickedTime('');
    setRescheduleError('');
    setShowRescheduleModal(true);
    if (interview.scheduled_datetime) {
      try {
        const d = new Date(interview.scheduled_datetime);
        setReschedulePickedDate(d);
        setReschedulePickedTime(`${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`);
      } catch (_) {}
    }
  };

  const handleRescheduleSubmit = async () => {
    if (!rescheduleInterviewObj || !reschedulePickedDate || !reschedulePickedTime) {
      setRescheduleError('Please select a date and time.');
      return;
    }
    setRescheduleError('');
    const [h, m] = reschedulePickedTime.split(':').map(Number);
    const combined = new Date(reschedulePickedDate.getFullYear(), reschedulePickedDate.getMonth(), reschedulePickedDate.getDate(), h || 0, m || 0);
    try {
      setRescheduleSubmitting(true);
      const response = await rescheduleInterview(rescheduleInterviewObj.id, combined.toISOString());
      if (response.status === 'success') {
        toast({ title: 'Rescheduled', description: 'Interview rescheduled; candidate has been notified.' });
        setShowRescheduleModal(false);
        setRescheduleInterviewObj(null);
        setReschedulePickedDate(null);
        setReschedulePickedTime('');
        fetchInterviews();
        if (onUpdate) onUpdate();
      }
    } catch (error) {
      const message = error.response?.data?.message || error.message || 'Reschedule failed';
      setRescheduleError(message);
      toast({ title: 'Reschedule failed', description: message, variant: 'destructive' });
    } finally {
      setRescheduleSubmitting(false);
    }
  };

  // pendingDecision = { outcome, label } when opened from decision change, else null
  const openFeedbackModal = (interview, pendingDecision = null) => {
    setFeedbackModal({
      interview,
      rating: interview.feedback_rating || 0,
      notes: interview.feedback_notes || '',
      strengths: interview.feedback_strengths || '',
      improvements: interview.feedback_improvements || '',
      pendingDecision,
    });
  };

  const handleFeedbackSubmit = async () => {
    if (!feedbackModal) return;
    if (!feedbackModal.rating) {
      toast({ title: 'Rating required', description: 'Please select a star rating before saving.', variant: 'destructive' });
      return;
    }
    try {
      setFeedbackSubmitting(true);
      // 1. Save feedback
      const fbRes = await submitInterviewFeedback(feedbackModal.interview.id, {
        feedback_rating: feedbackModal.rating,
        feedback_notes: feedbackModal.notes,
        feedback_strengths: feedbackModal.strengths,
        feedback_improvements: feedbackModal.improvements,
      });
      // 2. If triggered by decision change, save decision too
      if (feedbackModal.pendingDecision) {
        await updateInterview(feedbackModal.interview.id, {
          outcome: feedbackModal.pendingDecision.outcome,
        });
      }
      if (fbRes.status === 'success') {
        toast({
          title: 'Saved',
          description: feedbackModal.pendingDecision
            ? `Decision set to "${feedbackModal.pendingDecision.label}" and feedback saved.`
            : 'Interview feedback recorded successfully.',
        });
        setFeedbackModal(null);
        fetchInterviews();
        if (onUpdate) onUpdate();
      }
    } catch (error) {
      toast({ title: 'Error', description: error?.message || 'Failed to save', variant: 'destructive' });
    } finally {
      setFeedbackSubmitting(false);
    }
  };

  const openMeetingLinkEdit = (interview) => {
    setMeetingLinkEdit(prev => ({
      ...prev,
      [interview.id]: { open: true, value: interview.meeting_link || '', saving: false },
    }));
  };

  const saveMeetingLink = async (interview) => {
    const state = meetingLinkEdit[interview.id];
    if (!state) return;
    setMeetingLinkEdit(prev => ({ ...prev, [interview.id]: { ...prev[interview.id], saving: true } }));
    try {
      await updateInterview(interview.id, {
        meeting_link: state.value,
        resend_confirmation: true,
      });
      toast({ title: 'Meeting link saved', description: 'Confirmation email resent to candidate with the meeting link.' });
      setMeetingLinkEdit(prev => ({ ...prev, [interview.id]: { open: false, value: '', saving: false } }));
      fetchInterviews();
    } catch (err) {
      toast({ title: 'Error', description: err?.message || 'Failed to save meeting link', variant: 'destructive' });
      setMeetingLinkEdit(prev => ({ ...prev, [interview.id]: { ...prev[interview.id], saving: false } }));
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-4 w-full">
      {/* Header and Filters */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-xl sm:text-2xl py-3 sm:py-5 font-bold text-white">Interviews</h2>
          <p className="text-xs sm:text-sm text-white/60">Manage interview scheduling and tracking</p>
        </div>
        <div className="flex flex-wrap gap-2 justify-end items-center">
          {/* List / Kanban toggle */}
          <div className="flex rounded-lg border border-white/15 overflow-hidden">
            <button
              onClick={() => setViewMode('list')}
              title="List view"
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors ${
                viewMode === 'list' ? 'bg-white/15 text-white' : 'text-white/40 hover:text-white/70 hover:bg-white/5'
              }`}
            >
              <LayoutList className="h-3.5 w-3.5" />
              List
            </button>
            <button
              onClick={() => setViewMode('kanban')}
              title="Kanban view"
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border-l border-white/15 transition-colors ${
                viewMode === 'kanban' ? 'bg-white/15 text-white' : 'text-white/40 hover:text-white/70 hover:bg-white/5'
              }`}
            >
              <Columns className="h-3.5 w-3.5" />
              Kanban
            </button>
          </div>

          <SearchableSelect
            value={statusFilter || 'all'}
            onValueChange={(v) => setStatusFilter(v === 'all' ? '' : v)}
            options={[
              { value: 'all', label: 'All Statuses' },
              { value: 'PENDING', label: 'Pending' },
              { value: 'SCHEDULED', label: 'Scheduled' },
              { value: 'COMPLETED', label: 'Completed' },
              { value: 'CANCELLED', label: 'Cancelled' },
            ]}
            placeholder="All Statuses"
            triggerClassName="w-[140px] sm:w-[160px]"
          />
          <SearchableSelect
            value={decisionFilter === '' ? 'all' : decisionFilter}
            onValueChange={(v) => setDecisionFilter(v === 'all' ? '' : v)}
            options={[
              { value: 'all', label: 'All Decisions' },
              { value: 'NOT_SET', label: 'Not set' },
              { value: 'ONSITE_INTERVIEW', label: 'Onsite Interview' },
              { value: 'HIRED', label: 'Hired' },
              { value: 'PASSED', label: 'Passed' },
              { value: 'REJECTED', label: 'Rejected' },
            ]}
            placeholder="All Decisions"
            triggerClassName="w-[140px] sm:w-[160px]"
          />
          <SearchableSelect
            value={jobFilter || 'all'}
            onValueChange={(v) => setJobFilter(v === 'all' ? '' : v)}
            options={[{ value: 'all', label: 'All Jobs' }, ...jobs.map(j => ({ value: j.title, label: j.title }))]}
            placeholder="All Jobs"
            triggerClassName="w-[140px] sm:w-[180px]"
          />
        </div>
      </div>

      {/* Search + Date range + Rows per page */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[180px] max-w-xs">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-white/30 pointer-events-none" />
          <Input
            placeholder="Search name or email…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="pl-8 h-8 text-xs bg-white/5 border-white/10 text-white placeholder:text-white/30"
          />
        </div>
        <Input
          type="date"
          value={dateFrom}
          onChange={e => setDateFrom(e.target.value)}
          title="Created from"
          className="h-8 w-36 text-xs bg-white/5 border-white/10 text-white [color-scheme:dark]"
        />
        <span className="text-white/30 text-xs">to</span>
        <Input
          type="date"
          value={dateTo}
          onChange={e => setDateTo(e.target.value)}
          title="Created to"
          className="h-8 w-36 text-xs bg-white/5 border-white/10 text-white [color-scheme:dark]"
        />
        {(search || dateFrom || dateTo) && (
          <button
            onClick={() => { setSearch(''); setDateFrom(''); setDateTo(''); }}
            className="text-xs text-white/40 hover:text-white/70 transition-colors px-2 py-1 rounded border border-white/10 hover:border-white/25"
          >
            Clear
          </button>
        )}
        {/* Rows per page dropdown */}
        <div className="ml-auto flex items-center gap-1.5">
          <span className="text-xs text-white/40 whitespace-nowrap">Rows per page:</span>
          <select
            value={pageSize}
            onChange={e => { setPageSize(Number(e.target.value)); setCurrentPage(1); }}
            className="h-8 rounded-lg border border-white/15 bg-white/5 text-white text-xs px-2 pr-6 appearance-none cursor-pointer focus:outline-none focus:border-violet-500"
          >
            {[5, 10, 25, 100].map(n => (
              <option key={n} value={n} className="bg-[#0d0d1a]">{n}</option>
            ))}
          </select>
        </div>
      </div>

      {interviews.length === 0 ? (
        <Card className="border-white/10 bg-black/20 backdrop-blur-sm">
          <CardContent className="py-8 sm:py-12 text-center">
            <CalendarIcon className="h-10 w-10 sm:h-12 sm:w-12 mx-auto text-white/40 mb-4" />
            <p className="text-base sm:text-lg font-medium mb-2 text-white">No interviews yet</p>
            <p className="text-xs sm:text-sm text-white/60 px-4">Interviews appear here when scheduled from Candidates.</p>
          </CardContent>
        </Card>
      ) : viewMode === 'kanban' ? (
        <InterviewKanban
          interviews={interviews}
          groupBy={kanbanGroupBy}
          onGroupByChange={setKanbanGroupBy}
          onStatusChange={(interview, value) => setPendingChange({ interview, type: 'status', value, label: STATUS_LABELS[value] || value })}
          onOutcomeChange={handleOutcomeChange}
          onReschedule={openRescheduleModal}
          onFeedback={openFeedbackModal}
        />
      ) : (
        <div className="space-y-3 sm:space-y-4">
          {interviews.map((interview) => (
            <Card key={interview.id} className="overflow-hidden border-white/10 bg-black/20 backdrop-blur-sm">
              <CardHeader className="p-3 sm:p-6 pb-2 sm:pb-4">
                <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-2 sm:gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <User className="h-4 w-4 text-muted-foreground shrink-0 hidden sm:block" />
                      <CardTitle className="text-base sm:text-lg truncate">{interview.candidate_name}</CardTitle>
                    </div>
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <Briefcase className="h-3 w-3 sm:h-4 sm:w-4 shrink-0" />
                      <CardDescription className="text-xs sm:text-sm truncate">
                        {interview.job_title || interview.job_role}
                      </CardDescription>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap shrink-0">
                    {getStatusBadge(interview.status)}
                    {interview.outcome && getOutcomeBadge(interview.outcome)}
                  </div>
                </div>
              </CardHeader>

              <CardContent className="p-3 sm:p-6 pt-0 sm:pt-0 space-y-3 sm:space-y-4">
                {/* Contact & Schedule Info */}
                <div className="grid grid-cols-1 gap-3 sm:gap-4">
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs sm:text-sm">
                    <div className="flex items-center gap-1.5 sm:gap-2 min-w-0">
                      <Mail className="h-3 w-3 sm:h-4 sm:w-4 text-muted-foreground shrink-0" />
                      <span className="truncate text-muted-foreground">{interview.candidate_email}</span>
                    </div>
                    {interview.candidate_phone && (
                      <div className="flex items-center gap-1.5 sm:gap-2">
                        <Phone className="h-3 w-3 sm:h-4 sm:w-4 text-muted-foreground shrink-0" />
                        <span className="text-muted-foreground">{interview.candidate_phone}</span>
                      </div>
                    )}
                    <Badge variant="outline" className="text-[10px] sm:text-xs">{interview.interview_type}</Badge>
                  </div>

                  {interview.scheduled_datetime && (
                    <div className="flex items-start gap-1.5 sm:gap-2 text-xs sm:text-sm bg-muted/50 rounded-md p-2 sm:p-3">
                      <Clock className="h-3 w-3 sm:h-4 sm:w-4 text-muted-foreground shrink-0 mt-0.5" />
                      <div className="min-w-0">
                        <span className="hidden sm:inline">
                          {format(new Date(interview.scheduled_datetime), 'EEEE, MMMM d, yyyy \'at\' h:mm a')}
                        </span>
                        <span className="sm:hidden">
                          {format(new Date(interview.scheduled_datetime), 'EEE, MMM d, yyyy')}
                          <br />
                          <span className="text-muted-foreground">{format(new Date(interview.scheduled_datetime), 'h:mm a')}</span>
                        </span>
                      </div>
                    </div>
                  )}
                </div>

                {/* Meeting link row — shown for SCHEDULED interviews */}
                {interview.status === 'SCHEDULED' && (() => {
                  const mlState = meetingLinkEdit[interview.id];
                  return (
                    <div className="flex flex-col gap-1.5">
                      {interview.meeting_link && !mlState?.open ? (
                        <div className="flex items-center gap-2 text-xs flex-wrap">
                          <Link2 className="h-3.5 w-3.5 text-blue-400 shrink-0" />
                          <a href={interview.meeting_link} target="_blank" rel="noopener noreferrer"
                            className="text-blue-400 hover:text-blue-300 underline truncate max-w-[260px]">
                            {interview.meeting_link}
                          </a>
                          <button onClick={() => openMeetingLinkEdit(interview)}
                            className="ml-1 text-white/40 hover:text-white/70 transition-colors">
                            <Pencil className="h-3 w-3" />
                          </button>
                        </div>
                      ) : !mlState?.open ? (
                        <button onClick={() => openMeetingLinkEdit(interview)}
                          className="flex items-center gap-1.5 text-xs text-white/40 hover:text-blue-400 transition-colors w-fit">
                          <Link2 className="h-3.5 w-3.5" />
                          Add meeting link (Zoom / Teams / Meet)
                        </button>
                      ) : null}

                      {mlState?.open && (
                        <div className="flex items-center gap-2 flex-wrap">
                          <Input
                            type="url"
                            placeholder="https://zoom.us/j/... or meet.google.com/..."
                            value={mlState.value}
                            onChange={e => setMeetingLinkEdit(prev => ({ ...prev, [interview.id]: { ...prev[interview.id], value: e.target.value } }))}
                            className="h-8 text-xs flex-1 min-w-[200px] border-white/20 bg-white/5"
                            disabled={mlState.saving}
                          />
                          <button onClick={() => saveMeetingLink(interview)} disabled={mlState.saving}
                            className="inline-flex items-center gap-1.5 rounded-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 px-3 py-1 text-xs font-medium text-white transition-colors whitespace-nowrap">
                            {mlState.saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Send className="h-3 w-3" />}
                            Save & Resend Email
                          </button>
                          <button onClick={() => setMeetingLinkEdit(prev => ({ ...prev, [interview.id]: { open: false, value: '', saving: false } }))}
                            className="text-xs text-white/40 hover:text-white/60 transition-colors">
                            Cancel
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })()}

                {/* Actions row */}
                <div className="flex items-center gap-2 pt-3 sm:pt-4 border-t border-white/10">

                  {/* Reschedule quick button */}
                  {(interview.status === 'PENDING' || interview.status === 'SCHEDULED') && (
                    <button
                      type="button"
                      onClick={() => openRescheduleModal(interview)}
                      className="inline-flex items-center gap-1.5 rounded-full border border-amber-800 bg-amber-950/40 px-3 py-1.5 text-xs font-medium text-amber-200 hover:bg-amber-900/50 transition-colors"
                    >
                      <CalendarClock className="h-3.5 w-3.5 text-amber-400" />
                      Reschedule
                    </button>
                  )}

                  {/* Feedback quick button */}
                  {interview.status === 'COMPLETED' && (
                    interview.feedback_submitted_at ? (
                      <button type="button" onClick={() => openFeedbackModal(interview)}
                        className="inline-flex items-center gap-1.5 rounded-full border border-green-800 bg-green-950/40 px-3 py-1.5 text-xs font-medium text-green-300 hover:bg-green-900/50 transition-colors">
                        <CheckCircle2 className="h-3.5 w-3.5 text-green-400" />
                        View Feedback
                        {interview.feedback_rating > 0 && (
                          <span className="flex gap-0.5 ml-0.5">
                            {[1,2,3,4,5].map(s => (
                              <Star key={s} className={`h-2 w-2 ${s <= interview.feedback_rating ? 'text-amber-400 fill-amber-400' : 'text-white/20'}`} />
                            ))}
                          </span>
                        )}
                      </button>
                    ) : (
                      <button type="button" onClick={() => openFeedbackModal(interview)}
                        className="inline-flex items-center gap-1.5 rounded-full border border-blue-800 bg-blue-950/40 px-3 py-1.5 text-xs font-medium text-blue-300 hover:bg-blue-900/50 transition-colors">
                        <MessageSquare className="h-3.5 w-3.5 text-blue-400" />
                        Add Feedback
                      </button>
                    )
                  )}

                  <div className="flex-1" />

                  {updatingId === interview.id && (
                    <Loader2 className="h-4 w-4 animate-spin text-white/40" />
                  )}

                  {/* Three-dots menu */}
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button className="p-1.5 rounded-lg text-white/40 hover:text-white/80 hover:bg-white/10 transition-colors focus:outline-none">
                        <MoreVertical className="h-4 w-4" />
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent className="w-52 bg-[#0d0d1a] border-white/15 text-white z-50" align="end">

                      {/* Change Status */}
                      <DropdownMenuSub>
                        <DropdownMenuSubTrigger className="gap-2 focus:bg-white/10 data-[state=open]:bg-white/10 cursor-pointer">
                          <RefreshCw className="h-3.5 w-3.5 text-white/50" />
                          <span className="text-sm">Change Status</span>
                        </DropdownMenuSubTrigger>
                        <DropdownMenuSubContent className="bg-[#0d0d1a] border-white/15 text-white w-44">
                          {[
                            { v: 'PENDING',     label: 'Pending'     },
                            { v: 'SCHEDULED',   label: 'Scheduled'   },
                            { v: 'COMPLETED',   label: 'Completed'   },
                            { v: 'CANCELLED',   label: 'Cancelled'   },
                            { v: 'RESCHEDULED', label: 'Rescheduled' },
                          ].map(({ v, label }) => {
                            const active = interview.status === v;
                            return (
                              <DropdownMenuItem key={v}
                                className={`gap-2 cursor-pointer focus:bg-white/10 ${active ? 'text-white' : 'text-white/60'}`}
                                onClick={() => !active && handleStatusChange(interview, v)}>
                                <span className={`h-2 w-2 rounded-full shrink-0 ${
                                  v === 'PENDING' ? 'bg-yellow-400' : v === 'SCHEDULED' ? 'bg-green-400' :
                                  v === 'COMPLETED' ? 'bg-blue-400' : v === 'CANCELLED' ? 'bg-red-400' : 'bg-purple-400'
                                }`} />
                                <span className="text-sm">{label}</span>
                                {active && <span className="ml-auto text-[10px] text-violet-400">current</span>}
                              </DropdownMenuItem>
                            );
                          })}
                        </DropdownMenuSubContent>
                      </DropdownMenuSub>

                      {/* Change Decision */}
                      <DropdownMenuSub>
                        <DropdownMenuSubTrigger className="gap-2 focus:bg-white/10 data-[state=open]:bg-white/10 cursor-pointer">
                          <Award className="h-3.5 w-3.5 text-white/50" />
                          <span className="text-sm">Change Decision</span>
                          {interview.status !== 'COMPLETED' && <Lock className="h-3 w-3 text-white/30 ml-auto" />}
                        </DropdownMenuSubTrigger>
                        <DropdownMenuSubContent className="bg-[#0d0d1a] border-white/15 text-white w-52">
                          {interview.status !== 'COMPLETED' ? (
                            <div className="px-3 py-2.5 space-y-1">
                              <div className="flex items-center gap-1.5 text-amber-400/80">
                                <Lock className="h-3.5 w-3.5 shrink-0" />
                                <span className="text-xs font-medium">Decision Locked</span>
                              </div>
                              <p className="text-[11px] text-white/40 leading-snug">
                                Decision can only be set after interview status is <span className="text-white/60 font-medium">Completed</span>.
                              </p>
                            </div>
                          ) : (
                            [
                              { v: '',                 label: 'Not Set',          icon: '—'  },
                              { v: 'ONSITE_INTERVIEW', label: 'Onsite Interview', icon: '🏢' },
                              { v: 'PASSED',           label: 'Passed',           icon: '👍' },
                              { v: 'HIRED',            label: 'Hired',            icon: '🏆' },
                              { v: 'REJECTED',         label: 'Rejected',         icon: '✗'  },
                            ].map(({ v, label, icon }) => {
                              const active = (interview.outcome || '') === v;
                              return (
                                <DropdownMenuItem key={v || 'none'}
                                  className={`gap-2 cursor-pointer focus:bg-white/10 ${active ? 'text-white' : 'text-white/60'}`}
                                  onClick={() => !active && handleOutcomeChange(interview, v)}>
                                  <span className="text-sm w-4 text-center shrink-0">{icon}</span>
                                  <span className="text-sm">{label}</span>
                                  {active && <span className="ml-auto text-[10px] text-violet-400">current</span>}
                                </DropdownMenuItem>
                              );
                            })
                          )}
                        </DropdownMenuSubContent>
                      </DropdownMenuSub>

                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Pagination */}
      <div className="flex items-center justify-center gap-2 pt-2 border-t border-white/8">
        <button
          onClick={() => goToPage(currentPage - 1)}
          disabled={currentPage <= 1}
          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border border-white/15 text-white/60 hover:text-white hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <ChevronLeft className="h-3.5 w-3.5" /> Prev
        </button>
        <span className="text-xs text-white/50 min-w-[130px] text-center">
          Page {currentPage} of {totalPages || 1} &nbsp;·&nbsp; {totalCount} total
        </span>
        <button
          onClick={() => goToPage(currentPage + 1)}
          disabled={currentPage >= totalPages}
          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border border-white/15 text-white/60 hover:text-white hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          Next <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Reschedule Modal */}
      <Dialog open={showRescheduleModal} onOpenChange={(open) => {
        if (!open) { setShowRescheduleModal(false); setRescheduleInterviewObj(null); setReschedulePickedDate(null); setReschedulePickedTime(''); setRescheduleError(''); }
      }}>
        <DialogContent className="w-[95vw] max-w-lg max-h-[85vh] sm:max-h-[90vh] overflow-y-auto p-4 sm:p-6">
          <DialogHeader>
            <DialogTitle className="text-base sm:text-lg">Reschedule Interview</DialogTitle>
            {rescheduleInterviewObj && (
              <DialogDescription className="text-xs sm:text-sm line-clamp-2">
                {rescheduleInterviewObj.candidate_name} – {rescheduleInterviewObj.job_title || rescheduleInterviewObj.job_role}
              </DialogDescription>
            )}
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-xs sm:text-sm text-muted-foreground">Pre-filled with current scheduled time. Change date or time as needed, then confirm.</p>
            <div className="grid grid-cols-1 gap-3 sm:gap-4 sm:grid-cols-2">
              <div className="space-y-2 min-w-0">
                <Label className="text-xs sm:text-sm font-medium">Date</Label>
                <Popover>
                  <PopoverTrigger asChild>
                    <Button variant="outline" className="w-full justify-start h-10 sm:h-[47px] text-left font-normal text-xs sm:text-sm truncate">
                      <CalendarIcon className="mr-2 h-3.5 w-3.5 sm:h-4 sm:w-4 shrink-0" />
                      <span className="truncate">{reschedulePickedDate ? format(reschedulePickedDate, 'PPP') : 'Pick a date'}</span>
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto p-0" align="start">
                    <Calendar mode="single" selected={reschedulePickedDate}
                      onSelect={(d) => { setReschedulePickedDate(d); setRescheduleError(''); }}
                      disabled={{ before: startOfDay(new Date()) }} initialFocus />
                  </PopoverContent>
                </Popover>
              </div>
              <div className="space-y-2 min-w-0">
                <Label htmlFor="reschedule-time" className="text-xs sm:text-sm font-medium">Time</Label>
                <Input id="reschedule-time" type="time" value={reschedulePickedTime}
                  onChange={(e) => { setReschedulePickedTime(e.target.value); setRescheduleError(''); }}
                  className="w-full h-10 sm:h-[47px] text-xs sm:text-sm" />
              </div>
            </div>
            {rescheduleError && <p className="text-xs sm:text-sm text-destructive font-medium">{rescheduleError}</p>}
            <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end sm:gap-2">
              <Button variant="ghost" size="sm"
                onClick={() => { setShowRescheduleModal(false); setRescheduleInterviewObj(null); setReschedulePickedDate(null); setReschedulePickedTime(''); setRescheduleError(''); }}
                disabled={rescheduleSubmitting} className="w-full sm:w-auto h-9 sm:h-10 text-xs sm:text-sm">
                Cancel
              </Button>
              <Button onClick={handleRescheduleSubmit}
                disabled={!reschedulePickedDate || !reschedulePickedTime || rescheduleSubmitting}
                className="w-full sm:w-auto h-10 sm:h-11 text-xs sm:text-sm">
                {rescheduleSubmitting ? (
                  <><Loader2 className="h-3.5 w-3.5 sm:h-4 sm:w-4 mr-2 animate-spin" />Rescheduling...</>
                ) : 'Reschedule & notify candidate'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Feedback Modal */}
      {feedbackModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)' }}
          onClick={() => setFeedbackModal(null)}>
          <div className="w-full max-w-md rounded-2xl p-5 space-y-4"
            style={{ background: 'linear-gradient(135deg, #0d0d1a 0%, #0a1020 100%)', border: '1px solid rgba(167,139,250,0.25)' }}
            onClick={(e) => e.stopPropagation()}>
            <div>
              <h3 className="text-base font-bold text-white">Interview Feedback</h3>
              <p className="text-sm text-white/50 mt-0.5">{feedbackModal.interview.candidate_name} – {feedbackModal.interview.job_title || feedbackModal.interview.job_role}</p>
            </div>

            {/* Decision banner — shown when opened from decision change */}
            {feedbackModal.pendingDecision && (
              <div className="flex items-start gap-2.5 rounded-lg px-3 py-2.5"
                style={{ background: 'rgba(124,58,237,0.15)', border: '1px solid rgba(167,139,250,0.3)' }}>
                <Award className="h-4 w-4 text-violet-400 shrink-0 mt-0.5" />
                <div>
                  <p className="text-xs font-semibold text-violet-300">
                    Decision will be set to: <span className="text-white">{feedbackModal.pendingDecision.label}</span>
                  </p>
                  <p className="text-[11px] text-white/40 mt-0.5">
                    Feedback is required to confirm this decision.
                  </p>
                </div>
              </div>
            )}
            <div>
              <Label className="text-xs text-white/60 mb-2 block">Overall Rating *</Label>
              <div className="flex gap-1">
                {[1,2,3,4,5].map(star => (
                  <button key={star} type="button" onClick={() => setFeedbackModal(f => ({ ...f, rating: star }))}
                    className="transition-transform hover:scale-110 focus:outline-none">
                    <Star className={`h-7 w-7 transition-colors ${star <= feedbackModal.rating ? 'text-amber-400 fill-amber-400' : 'text-white/20 hover:text-amber-300'}`} />
                  </button>
                ))}
                {feedbackModal.rating > 0 && (
                  <span className="text-xs text-white/40 self-center ml-2">{['','Poor','Below Average','Average','Good','Excellent'][feedbackModal.rating]}</span>
                )}
              </div>
            </div>
            <div>
              <Label className="text-xs text-white/60 mb-1.5 block">Strengths Observed</Label>
              <Textarea value={feedbackModal.strengths} onChange={(e) => setFeedbackModal(f => ({ ...f, strengths: e.target.value }))}
                placeholder="e.g. Strong communication skills, solid technical foundation..."
                className="min-h-[70px] text-sm bg-white/5 border-white/10 text-white placeholder:text-white/25 resize-none" />
            </div>
            <div>
              <Label className="text-xs text-white/60 mb-1.5 block">Areas for Improvement</Label>
              <Textarea value={feedbackModal.improvements} onChange={(e) => setFeedbackModal(f => ({ ...f, improvements: e.target.value }))}
                placeholder="e.g. Needs more experience with system design..."
                className="min-h-[70px] text-sm bg-white/5 border-white/10 text-white placeholder:text-white/25 resize-none" />
            </div>
            <div>
              <Label className="text-xs text-white/60 mb-1.5 block">Additional Notes</Label>
              <Textarea value={feedbackModal.notes} onChange={(e) => setFeedbackModal(f => ({ ...f, notes: e.target.value }))}
                placeholder="Any other observations or comments..."
                className="min-h-[60px] text-sm bg-white/5 border-white/10 text-white placeholder:text-white/25 resize-none" />
            </div>
            <div className="flex gap-3 justify-end pt-1">
              <button onClick={() => setFeedbackModal(null)} disabled={feedbackSubmitting}
                className="px-4 py-2 rounded-lg text-sm text-white/60 hover:text-white/90 border border-white/10 hover:border-white/25 transition-colors">
                Cancel
              </button>
              <button onClick={handleFeedbackSubmit} disabled={feedbackSubmitting || !feedbackModal.rating}
                className="px-4 py-2 rounded-lg text-sm font-semibold text-white transition-all disabled:opacity-50 flex items-center gap-2"
                style={{ background: 'linear-gradient(90deg, #7c3aed 0%, #a259ff 100%)' }}>
                {feedbackSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                Save Feedback
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Confirm Status / Decision Change Modal */}
      {pendingChange && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }}
          onClick={() => setPendingChange(null)}>
          <div className="w-full max-w-sm rounded-2xl p-6"
            style={{ background: 'linear-gradient(135deg, #0d0d1a 0%, #0a1020 100%)', border: '1px solid rgba(167,139,250,0.25)' }}
            onClick={(e) => e.stopPropagation()}>
            <h3 className="text-base font-bold text-white mb-1">Confirm Change</h3>
            <p className="text-sm text-white/60 mb-1">
              {pendingChange.type === 'status' ? 'Change interview status' : 'Change interview decision'} for{' '}
              <span className="text-white font-medium">{pendingChange.interview.candidate_name}</span>?
            </p>
            <p className="text-sm text-white/50 mb-5">
              New {pendingChange.type}:{' '}
              <span className="font-semibold text-violet-300">{pendingChange.label}</span>
            </p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setPendingChange(null)}
                className="px-4 py-2 rounded-lg text-sm text-white/60 hover:text-white/90 border border-white/10 hover:border-white/25 transition-colors">
                Cancel
              </button>
              <button onClick={handleConfirmChange} disabled={!!updatingId}
                className="px-4 py-2 rounded-lg text-sm font-semibold text-white transition-all disabled:opacity-50"
                style={{ background: 'linear-gradient(90deg, #7c3aed 0%, #a259ff 100%)' }}>
                {updatingId ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Yes, Update'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Interviews;
