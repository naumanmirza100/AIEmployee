import React, { useState, useEffect } from 'react';
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
import { Loader2, Calendar as CalendarIcon, Mail, Phone, Clock, CalendarClock, Briefcase, User, Star, MessageSquare, CheckCircle2 } from 'lucide-react';
import { getInterviews, updateInterview, rescheduleInterview, getJobDescriptions, submitInterviewFeedback } from '@/services/recruitmentAgentService';
import SearchableSelect from '@/components/ui/searchable-select';

const Interviews = ({ onUpdate }) => {
  const { toast } = useToast();
  const [interviews, setInterviews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [decisionFilter, setDecisionFilter] = useState('');
  const [jobFilter, setJobFilter] = useState('');
  const [jobs, setJobs] = useState([]);
  const [updatingId, setUpdatingId] = useState(null);
  const [pendingChange, setPendingChange] = useState(null); // { interview, type: 'status'|'outcome', value, label }
  const [showRescheduleModal, setShowRescheduleModal] = useState(false);
  const [rescheduleInterviewObj, setRescheduleInterviewObj] = useState(null);
  const [reschedulePickedDate, setReschedulePickedDate] = useState(null);
  const [reschedulePickedTime, setReschedulePickedTime] = useState('');
  const [rescheduleError, setRescheduleError] = useState('');
  const [rescheduleSubmitting, setRescheduleSubmitting] = useState(false);
  const [feedbackModal, setFeedbackModal] = useState(null); // { interview, rating, notes, strengths, improvements }
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);

  useEffect(() => {
    fetchInterviews();
    fetchJobs();
  }, [statusFilter, decisionFilter]);

  const fetchJobs = async () => {
    try {
      const response = await getJobDescriptions();
      if (response.status === 'success') {
        setJobs(response.data || []);
      }
    } catch (error) {
      console.error('Error fetching jobs:', error);
    }
  };

  const fetchInterviews = async () => {
    try {
      setLoading(true);
      const filters = {};
      if (statusFilter) filters.status = statusFilter;
      if (decisionFilter !== '') filters.outcome = decisionFilter;
      const response = await getInterviews(filters);
      if (response.status === 'success') {
        setInterviews(response.data || []);
      }
    } catch (error) {
      console.error('Error fetching interviews:', error);
      toast({
        title: 'Error',
        description: 'Failed to load interviews',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (status) => {
    const variants = {
      PENDING: 'bg-yellow-500',
      SCHEDULED: 'bg-green-500',
      COMPLETED: 'bg-blue-500',
      CANCELLED: 'bg-red-500',
      RESCHEDULED: 'bg-purple-500',
    };
    return <Badge className={variants[status] || 'bg-gray-500'}>{status}</Badge>;
  };

  const getOutcomeBadge = (outcome) => {
    if (!outcome) return null;
    const variants = {
      ONSITE_INTERVIEW: 'bg-indigo-500',
      HIRED: 'bg-emerald-600',
      PASSED: 'bg-teal-500',
      REJECTED: 'bg-red-600',
    };
    const labels = {
      ONSITE_INTERVIEW: 'Onsite Interview',
      HIRED: 'Hired',
      PASSED: 'Passed',
      REJECTED: 'Rejected',
    };
    return <Badge className={variants[outcome] || 'bg-gray-500'}>{labels[outcome] || outcome}</Badge>;
  };

  const STATUS_LABELS = { PENDING: 'Pending', SCHEDULED: 'Scheduled', COMPLETED: 'Completed', CANCELLED: 'Cancelled', RESCHEDULED: 'Rescheduled' };
  const OUTCOME_LABELS = { ONSITE_INTERVIEW: 'Onsite Interview', HIRED: 'Hired', PASSED: 'Passed', REJECTED: 'Rejected', '': 'None' };

  const handleStatusChange = (interview, newStatus) => {
    setPendingChange({ interview, type: 'status', value: newStatus, label: STATUS_LABELS[newStatus] || newStatus });
  };

  const handleOutcomeChange = (interview, newOutcome) => {
    setPendingChange({ interview, type: 'outcome', value: newOutcome, label: OUTCOME_LABELS[newOutcome] || newOutcome || 'None' });
  };

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
    // Pre-fill with current scheduled time so recruiter can see and change it
    if (interview.scheduled_datetime) {
      try {
        const d = new Date(interview.scheduled_datetime);
        setReschedulePickedDate(d);
        setReschedulePickedTime(`${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`);
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
    const isoDatetime = combined.toISOString();
    try {
      setRescheduleSubmitting(true);
      const response = await rescheduleInterview(rescheduleInterviewObj.id, isoDatetime);
      if (response.status === 'success') {
        toast({
          title: 'Rescheduled',
          description: 'Interview rescheduled; candidate has been notified.',
        });
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
      toast({
        title: 'Reschedule failed',
        description: message,
        variant: 'destructive',
      });
    } finally {
      setRescheduleSubmitting(false);
    }
  };

  const openFeedbackModal = (interview) => {
    setFeedbackModal({
      interview,
      rating: interview.feedback_rating || 0,
      notes: interview.feedback_notes || '',
      strengths: interview.feedback_strengths || '',
      improvements: interview.feedback_improvements || '',
    });
  };

  const handleFeedbackSubmit = async () => {
    if (!feedbackModal) return;
    if (!feedbackModal.rating) {
      toast({ title: 'Rating required', description: 'Please select a star rating.', variant: 'destructive' });
      return;
    }
    try {
      setFeedbackSubmitting(true);
      const response = await submitInterviewFeedback(feedbackModal.interview.id, {
        feedback_rating: feedbackModal.rating,
        feedback_notes: feedbackModal.notes,
        feedback_strengths: feedbackModal.strengths,
        feedback_improvements: feedbackModal.improvements,
      });
      if (response.status === 'success') {
        toast({ title: 'Feedback saved', description: 'Interview feedback recorded successfully.' });
        setFeedbackModal(null);
        fetchInterviews();
      }
    } catch (error) {
      toast({ title: 'Error', description: error?.message || 'Failed to save feedback', variant: 'destructive' });
    } finally {
      setFeedbackSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    );
  }

  const filteredInterviews = jobFilter
    ? interviews.filter(i => (i.job_title || i.job_role || '') === jobFilter)
    : interviews;

  return (
    <div className="space-y-4 w-full">
      {/* Header and Filters */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-xl sm:text-2xl py-3 sm:py-5 font-bold text-white">Interviews</h2>
          <p className="text-xs sm:text-sm text-white/60">
            Manage interview scheduling and tracking
          </p>
        </div>
        <div className="flex flex-wrap gap-2 justify-end">
          <SearchableSelect
            value={statusFilter || 'all'}
            onValueChange={(value) => setStatusFilter(value === 'all' ? '' : value)}
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
            onValueChange={(value) => setDecisionFilter(value === 'all' ? '' : value)}
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
            onValueChange={(value) => setJobFilter(value === 'all' ? '' : value)}
            options={[{ value: 'all', label: 'All Jobs' }, ...jobs.map(j => ({ value: j.title, label: j.title }))]}
            placeholder="All Jobs"
            triggerClassName="w-[140px] sm:w-[180px]"
          />
        </div>
      </div>

      {filteredInterviews.length === 0 ? (
        <Card className="border-white/10 bg-black/20 backdrop-blur-sm">
          <CardContent className="py-8 sm:py-12 text-center">
            <CalendarIcon className="h-10 w-10 sm:h-12 sm:w-12 mx-auto text-white/40 mb-4" />
            <p className="text-base sm:text-lg font-medium mb-2 text-white">No interviews yet</p>
            <p className="text-xs sm:text-sm text-white/60 px-4">
              Interviews appear here when scheduled from Candidates.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3 sm:space-y-4">
          {filteredInterviews.map((interview) => (
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
                  {/* Contact Info */}
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
                  
                  {/* Schedule Info */}
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
                          <span className="text-muted-foreground">
                            {format(new Date(interview.scheduled_datetime), 'h:mm a')}
                          </span>
                        </span>
                      </div>
                    </div>
                  )}
                </div>

                {/* Actions */}
                <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center gap-3 sm:gap-4 pt-3 sm:pt-4 border-t">
                  {/* Reschedule Button */}
                  {(interview.status === 'PENDING' || interview.status === 'SCHEDULED') && (
                    <button
                      type="button"
                      onClick={() => openRescheduleModal(interview)}
                      className="inline-flex items-center justify-center gap-2 rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs sm:text-sm font-medium text-amber-800 shadow-sm transition-colors hover:bg-amber-100 hover:border-amber-300 focus:outline-none focus:ring-2 focus:ring-amber-400/50 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200 dark:hover:bg-amber-900/50 dark:hover:border-amber-700 w-full sm:w-auto"
                    >
                      <CalendarClock className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-amber-600 dark:text-amber-400" />
                      Reschedule
                    </button>
                  )}

                  {/* Feedback Button (COMPLETED interviews) */}
                  {interview.status === 'COMPLETED' && (
                    interview.feedback_submitted_at ? (
                      <button
                        type="button"
                        onClick={() => openFeedbackModal(interview)}
                        className="inline-flex items-center justify-center gap-2 rounded-full border border-green-800 bg-green-950/40 px-3 py-1.5 text-xs sm:text-sm font-medium text-green-300 hover:bg-green-900/50 transition-colors w-full sm:w-auto"
                      >
                        <CheckCircle2 className="h-3.5 w-3.5 text-green-400" />
                        View Feedback
                        {interview.feedback_rating && (
                          <span className="flex gap-0.5 ml-1">
                            {[1,2,3,4,5].map(s => <Star key={s} className={`h-2.5 w-2.5 ${s <= interview.feedback_rating ? 'text-amber-400 fill-amber-400' : 'text-white/20'}`} />)}
                          </span>
                        )}
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => openFeedbackModal(interview)}
                        className="inline-flex items-center justify-center gap-2 rounded-full border border-blue-800 bg-blue-950/40 px-3 py-1.5 text-xs sm:text-sm font-medium text-blue-300 hover:bg-blue-900/50 transition-colors w-full sm:w-auto"
                      >
                        <MessageSquare className="h-3.5 w-3.5 text-blue-400" />
                        Add Feedback
                      </button>
                    )
                  )}
                  
                  {/* Status & Decision Controls */}
                  <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 w-full sm:w-auto">
                    {/* Status Select */}
                    <div className="flex items-center gap-2 w-full sm:w-auto">
                      <Label className="text-xs sm:text-sm font-medium text-muted-foreground whitespace-nowrap shrink-0">Status</Label>
                      <Select
                        value={interview.status}
                        onValueChange={(value) => handleStatusChange(interview, value)}
                        disabled={updatingId === interview.id}
                      >
                        <SelectTrigger className="w-full sm:w-[130px] h-8 sm:h-9 text-xs sm:text-sm border-white/20">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="PENDING">Pending</SelectItem>
                          <SelectItem value="SCHEDULED">Scheduled</SelectItem>
                          <SelectItem value="COMPLETED">Completed</SelectItem>
                          <SelectItem value="CANCELLED">Cancelled</SelectItem>
                          <SelectItem value="RESCHEDULED">Rescheduled</SelectItem>
                        </SelectContent>
                      </Select>
                      {updatingId === interview.id && (
                        <Loader2 className="h-3 w-3 sm:h-4 sm:w-4 animate-spin text-muted-foreground shrink-0" />
                      )}
                    </div>
                    
                    {/* Decision Select */}
                    {(interview.status === 'COMPLETED' || interview.outcome) && (
                      <div className="flex items-center gap-2 w-full sm:w-auto">
                        <Label className="text-xs sm:text-sm font-medium text-muted-foreground whitespace-nowrap shrink-0">Decision</Label>
                        <Select
                          value={interview.outcome || 'none'}
                          onValueChange={(value) => handleOutcomeChange(interview, value === 'none' ? '' : value)}
                          disabled={updatingId === interview.id}
                        >
                          <SelectTrigger className="w-full sm:w-[150px] h-8 sm:h-9 text-xs sm:text-sm border-white/20">
                            <SelectValue placeholder="Set outcome" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="none">Not set</SelectItem>
                            <SelectItem value="ONSITE_INTERVIEW">Onsite Interview</SelectItem>
                            <SelectItem value="HIRED">Hired</SelectItem>
                            <SelectItem value="PASSED">Passed</SelectItem>
                            <SelectItem value="REJECTED">Rejected</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Reschedule Modal */}
      <Dialog open={showRescheduleModal} onOpenChange={(open) => {
        if (!open) {
          setShowRescheduleModal(false);
          setRescheduleInterviewObj(null);
          setReschedulePickedDate(null);
          setReschedulePickedTime('');
          setRescheduleError('');
        }
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
            <p className="text-xs sm:text-sm text-muted-foreground">
              Pre-filled with current scheduled time. Change date or time as needed, then confirm.
            </p>
            <div className="grid grid-cols-1 gap-3 sm:gap-4 sm:grid-cols-2">
              <div className="space-y-2 min-w-0">
                <Label className="text-xs sm:text-sm font-medium">Date</Label>
                <Popover>
                  <PopoverTrigger asChild>
                    <Button
                      variant="outline"
                      className="w-full justify-start h-10 sm:h-[47px] text-left font-normal text-xs sm:text-sm truncate"
                    >
                      <CalendarIcon className="mr-2 h-3.5 w-3.5 sm:h-4 sm:w-4 shrink-0" />
                      <span className="truncate">
                        {reschedulePickedDate ? format(reschedulePickedDate, 'PPP') : 'Pick a date'}
                      </span>
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto p-0" align="start">
                    <Calendar
                      mode="single"
                      selected={reschedulePickedDate}
                      onSelect={(d) => {
                        setReschedulePickedDate(d);
                        setRescheduleError('');
                      }}
                      disabled={{ before: startOfDay(new Date()) }}
                      initialFocus
                    />
                  </PopoverContent>
                </Popover>
              </div>
              <div className="space-y-2 min-w-0">
                <Label htmlFor="reschedule-time" className="text-xs sm:text-sm font-medium">Time</Label>
                <Input
                  id="reschedule-time"
                  type="time"
                  value={reschedulePickedTime}
                  onChange={(e) => {
                    setReschedulePickedTime(e.target.value);
                    setRescheduleError('');
                  }}
                  className="w-full h-10 sm:h-[47px] text-xs sm:text-sm"
                />
              </div>
            </div>
            {rescheduleError && (
              <p className="text-xs sm:text-sm text-destructive font-medium">
                {rescheduleError}
              </p>
            )}
            <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end sm:gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setShowRescheduleModal(false);
                  setRescheduleInterviewObj(null);
                  setReschedulePickedDate(null);
                  setReschedulePickedTime('');
                  setRescheduleError('');
                }}
                disabled={rescheduleSubmitting}
                className="w-full sm:w-auto h-9 sm:h-10 text-xs sm:text-sm"
              >
                Cancel
              </Button>
              <Button
                onClick={handleRescheduleSubmit}
                disabled={!reschedulePickedDate || !reschedulePickedTime || rescheduleSubmitting}
                className="w-full sm:w-auto h-10 sm:h-11 text-xs sm:text-sm"
              >
                {rescheduleSubmitting ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 sm:h-4 sm:w-4 mr-2 animate-spin" />
                    <span className="hidden sm:inline">Rescheduling...</span>
                    <span className="sm:hidden">Saving...</span>
                  </>
                ) : (
                  <>
                    <span className="hidden sm:inline">Reschedule & notify candidate</span>
                    <span className="sm:hidden">Reschedule & Notify</span>
                  </>
                )}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Interview Feedback Modal */}
      {feedbackModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)' }}
          onClick={() => setFeedbackModal(null)}
        >
          <div
            className="w-full max-w-md rounded-2xl p-5 space-y-4"
            style={{ background: 'linear-gradient(135deg, #0d0d1a 0%, #0a1020 100%)', border: '1px solid rgba(167,139,250,0.25)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div>
              <h3 className="text-base font-bold text-white">Interview Feedback</h3>
              <p className="text-sm text-white/50 mt-0.5">{feedbackModal.interview.candidate_name} – {feedbackModal.interview.job_title || feedbackModal.interview.job_role}</p>
            </div>

            {/* Star Rating */}
            <div>
              <Label className="text-xs text-white/60 mb-2 block">Overall Rating *</Label>
              <div className="flex gap-1">
                {[1,2,3,4,5].map(star => (
                  <button
                    key={star}
                    type="button"
                    onClick={() => setFeedbackModal(f => ({ ...f, rating: star }))}
                    className="transition-transform hover:scale-110 focus:outline-none"
                  >
                    <Star className={`h-7 w-7 transition-colors ${star <= feedbackModal.rating ? 'text-amber-400 fill-amber-400' : 'text-white/20 hover:text-amber-300'}`} />
                  </button>
                ))}
                {feedbackModal.rating > 0 && (
                  <span className="text-xs text-white/40 self-center ml-2">{['','Poor','Below Average','Average','Good','Excellent'][feedbackModal.rating]}</span>
                )}
              </div>
            </div>

            {/* Strengths */}
            <div>
              <Label className="text-xs text-white/60 mb-1.5 block">Strengths Observed</Label>
              <Textarea
                value={feedbackModal.strengths}
                onChange={(e) => setFeedbackModal(f => ({ ...f, strengths: e.target.value }))}
                placeholder="e.g. Strong communication skills, solid technical foundation..."
                className="min-h-[70px] text-sm bg-white/5 border-white/10 text-white placeholder:text-white/25 resize-none"
              />
            </div>

            {/* Improvements */}
            <div>
              <Label className="text-xs text-white/60 mb-1.5 block">Areas for Improvement</Label>
              <Textarea
                value={feedbackModal.improvements}
                onChange={(e) => setFeedbackModal(f => ({ ...f, improvements: e.target.value }))}
                placeholder="e.g. Needs more experience with system design..."
                className="min-h-[70px] text-sm bg-white/5 border-white/10 text-white placeholder:text-white/25 resize-none"
              />
            </div>

            {/* Notes */}
            <div>
              <Label className="text-xs text-white/60 mb-1.5 block">Additional Notes</Label>
              <Textarea
                value={feedbackModal.notes}
                onChange={(e) => setFeedbackModal(f => ({ ...f, notes: e.target.value }))}
                placeholder="Any other observations or comments..."
                className="min-h-[60px] text-sm bg-white/5 border-white/10 text-white placeholder:text-white/25 resize-none"
              />
            </div>

            <div className="flex gap-3 justify-end pt-1">
              <button
                onClick={() => setFeedbackModal(null)}
                disabled={feedbackSubmitting}
                className="px-4 py-2 rounded-lg text-sm text-white/60 hover:text-white/90 border border-white/10 hover:border-white/25 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleFeedbackSubmit}
                disabled={feedbackSubmitting || !feedbackModal.rating}
                className="px-4 py-2 rounded-lg text-sm font-semibold text-white transition-all disabled:opacity-50 flex items-center gap-2"
                style={{ background: 'linear-gradient(90deg, #7c3aed 0%, #a259ff 100%)' }}
              >
                {feedbackSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                Save Feedback
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Confirm Status / Decision Change Modal */}
      {pendingChange && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }}
          onClick={() => setPendingChange(null)}
        >
          <div
            className="w-full max-w-sm rounded-2xl p-6"
            style={{ background: 'linear-gradient(135deg, #0d0d1a 0%, #0a1020 100%)', border: '1px solid rgba(167,139,250,0.25)' }}
            onClick={(e) => e.stopPropagation()}
          >
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
              <button
                onClick={() => setPendingChange(null)}
                className="px-4 py-2 rounded-lg text-sm text-white/60 hover:text-white/90 border border-white/10 hover:border-white/25 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmChange}
                disabled={!!updatingId}
                className="px-4 py-2 rounded-lg text-sm font-semibold text-white transition-all disabled:opacity-50"
                style={{ background: 'linear-gradient(90deg, #7c3aed 0%, #a259ff 100%)' }}
              >
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

