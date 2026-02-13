import React, { useState, useEffect } from 'react';
import { format, startOfDay } from 'date-fns';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Calendar } from '@/components/ui/calendar';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Calendar as CalendarIcon, Mail, Phone, Clock, CalendarClock, Briefcase, User } from 'lucide-react';
import { getInterviews, updateInterview, rescheduleInterview } from '@/services/recruitmentAgentService';

const Interviews = ({ onUpdate }) => {
  const { toast } = useToast();
  const [interviews, setInterviews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [decisionFilter, setDecisionFilter] = useState('');
  const [updatingId, setUpdatingId] = useState(null);
  const [showRescheduleModal, setShowRescheduleModal] = useState(false);
  const [rescheduleInterviewObj, setRescheduleInterviewObj] = useState(null);
  const [reschedulePickedDate, setReschedulePickedDate] = useState(null);
  const [reschedulePickedTime, setReschedulePickedTime] = useState('');
  const [rescheduleError, setRescheduleError] = useState('');
  const [rescheduleSubmitting, setRescheduleSubmitting] = useState(false);

  useEffect(() => {
    fetchInterviews();
  }, [statusFilter, decisionFilter]);

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

  const handleStatusChange = async (interviewId, newStatus) => {
    try {
      setUpdatingId(interviewId);
      const response = await updateInterview(interviewId, { status: newStatus });
      if (response.status === 'success') {
        toast({ title: 'Updated', description: 'Interview status updated' });
        fetchInterviews();
        if (onUpdate) onUpdate();
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to update status',
        variant: 'destructive',
      });
    } finally {
      setUpdatingId(null);
    }
  };

  const handleOutcomeChange = async (interviewId, newOutcome) => {
    try {
      setUpdatingId(interviewId);
      const response = await updateInterview(interviewId, { outcome: newOutcome || '' });
      if (response.status === 'success') {
        toast({ title: 'Updated', description: 'Interview outcome updated' });
        fetchInterviews();
        if (onUpdate) onUpdate();
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to update outcome',
        variant: 'destructive',
      });
    } finally {
      setUpdatingId(null);
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
          <h2 className="text-xl sm:text-2xl py-3 sm:py-5 font-bold">Interviews</h2>
          <p className="text-xs sm:text-sm text-muted-foreground">
            Manage interview scheduling and tracking
          </p>
        </div>
        <div className="flex flex-wrap gap-2 justify-end">
          <Select value={statusFilter || "all"} onValueChange={(value) => setStatusFilter(value === "all" ? "" : value)}>
            <SelectTrigger className="w-[140px] sm:w-[160px]">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Statuses</SelectItem>
              <SelectItem value="PENDING">Pending</SelectItem>
              <SelectItem value="SCHEDULED">Scheduled</SelectItem>
              <SelectItem value="COMPLETED">Completed</SelectItem>
              <SelectItem value="CANCELLED">Cancelled</SelectItem>
            </SelectContent>
          </Select>
          <Select value={decisionFilter === '' ? "all" : decisionFilter} onValueChange={(value) => setDecisionFilter(value === "all" ? "" : value)}>
            <SelectTrigger className="w-[140px] sm:w-[160px]">
              <SelectValue placeholder="Decision" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Decisions</SelectItem>
              <SelectItem value="NOT_SET">Not set</SelectItem>
              <SelectItem value="ONSITE_INTERVIEW">Onsite Interview</SelectItem>
              <SelectItem value="HIRED">Hired</SelectItem>
              <SelectItem value="PASSED">Passed</SelectItem>
              <SelectItem value="REJECTED">Rejected</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {interviews.length === 0 ? (
        <Card>
          <CardContent className="py-8 sm:py-12 text-center">
            <CalendarIcon className="h-10 w-10 sm:h-12 sm:w-12 mx-auto text-muted-foreground mb-4" />
            <p className="text-base sm:text-lg font-medium mb-2">No interviews yet</p>
            <p className="text-xs sm:text-sm text-muted-foreground px-4">
              Interviews appear here when scheduled from Candidates.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3 sm:space-y-4">
          {interviews.map((interview) => (
            <Card key={interview.id} className="overflow-hidden">
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
                  
                  {/* Status & Decision Controls */}
                  <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 w-full sm:w-auto">
                    {/* Status Select */}
                    <div className="flex items-center gap-2 w-full sm:w-auto">
                      <Label className="text-xs sm:text-sm font-medium text-muted-foreground whitespace-nowrap shrink-0">Status</Label>
                      <Select
                        value={interview.status}
                        onValueChange={(value) => handleStatusChange(interview.id, value)}
                        disabled={updatingId === interview.id}
                      >
                        <SelectTrigger className="w-full sm:w-[130px] h-8 sm:h-9 text-xs sm:text-sm">
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
                          onValueChange={(value) => handleOutcomeChange(interview.id, value === 'none' ? '' : value)}
                          disabled={updatingId === interview.id}
                        >
                          <SelectTrigger className="w-full sm:w-[150px] h-8 sm:h-9 text-xs sm:text-sm">
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
    </div>
  );
};

export default Interviews;

