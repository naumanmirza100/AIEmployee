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
import { Loader2, Calendar as CalendarIcon, Mail, Phone, Clock, CalendarClock } from 'lucide-react';
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
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold">Interviews</h2>
          <p className="text-sm text-muted-foreground">
            Manage interview scheduling and tracking
          </p>
        </div>
        <div className="flex gap-2">
          <Select value={statusFilter || "all"} onValueChange={(value) => setStatusFilter(value === "all" ? "" : value)}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Filter by status" />
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
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Filter by decision" />
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
          <CardContent className="py-12 text-center">
            <CalendarIcon className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <p className="text-lg font-medium mb-2">No interviews yet</p>
            <p className="text-sm text-muted-foreground">
              Interviews appear here when scheduled from Candidates.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {interviews.map((interview) => (
            <Card key={interview.id}>
              <CardHeader>
                <div className="flex justify-between items-start flex-wrap gap-2">
                  <div>
                    <CardTitle className="text-lg">{interview.candidate_name}</CardTitle>
                    <CardDescription className="mt-1">
                      {interview.job_title || interview.job_role}
                    </CardDescription>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    {getStatusBadge(interview.status)}
                    {interview.outcome && getOutcomeBadge(interview.outcome)}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-sm">
                      <Mail className="h-4 w-4 text-muted-foreground" />
                      <span>{interview.candidate_email}</span>
                    </div>
                    {interview.candidate_phone && (
                      <div className="flex items-center gap-2 text-sm">
                        <Phone className="h-4 w-4 text-muted-foreground" />
                        <span>{interview.candidate_phone}</span>
                      </div>
                    )}
                    <div className="flex items-center gap-2 text-sm">
                      <Badge variant="outline">{interview.interview_type}</Badge>
                    </div>
                  </div>
                  <div className="space-y-2">
                    {interview.scheduled_datetime && (
                      <div className="flex items-center gap-2 text-sm">
                        <Clock className="h-4 w-4 text-muted-foreground shrink-0" />
                        <span>
                          {format(new Date(interview.scheduled_datetime), 'EEEE, MMMM d, yyyy \'at\' h:mm a')}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-4 pt-4 border-t">
                  {(interview.status === 'PENDING' || interview.status === 'SCHEDULED') && (
                    <button
                      type="button"
                      onClick={() => openRescheduleModal(interview)}
                      className="inline-flex items-center gap-2 rounded-full border border-amber-200 bg-amber-50 px-3.5 py-1.5 text-sm font-medium text-amber-800 shadow-sm transition-colors hover:bg-amber-100 hover:border-amber-300 focus:outline-none focus:ring-2 focus:ring-amber-400/50 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200 dark:hover:bg-amber-900/50 dark:hover:border-amber-700"
                    >
                      <CalendarClock className="h-4 w-4 text-amber-600 dark:text-amber-400" />
                      Reschedule
                    </button>
                  )}
                  <div className="flex items-center gap-2">
                    <Label className="text-sm font-medium text-muted-foreground">Status</Label>
                    <Select
                      value={interview.status}
                      onValueChange={(value) => handleStatusChange(interview.id, value)}
                      disabled={updatingId === interview.id}
                    >
                      <SelectTrigger className="w-[160px] h-9">
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
                      <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                    )}
                  </div>
                  {(interview.status === 'COMPLETED' || interview.outcome) && (
                    <div className="flex items-center gap-2">
                      <Label className="text-sm font-medium text-muted-foreground">Decision</Label>
                      <Select
                        value={interview.outcome || 'none'}
                        onValueChange={(value) => handleOutcomeChange(interview.id, value === 'none' ? '' : value)}
                        disabled={updatingId === interview.id}
                      >
                        <SelectTrigger className="w-[180px] h-9">
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
        <DialogContent className="max-w-lg w-[calc(100%-2rem)] sm:w-full max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-lg sm:text-xl">Reschedule Interview</DialogTitle>
            {rescheduleInterviewObj && (
              <DialogDescription className="text-sm line-clamp-2 sm:line-clamp-none">
                {rescheduleInterviewObj.candidate_name} – {rescheduleInterviewObj.job_title || rescheduleInterviewObj.job_role}
              </DialogDescription>
            )}
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Pre-filled with current scheduled time. Change date or time as needed, then confirm.
            </p>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-2 min-w-0">
                <Label className="text-sm font-medium">Date</Label>
                <Popover>
                  <PopoverTrigger asChild>
                    <Button
                      variant="outline"
                      className="w-full justify-start h-[47px] text-left font-normal text-sm truncate"
                    >
                      <CalendarIcon className="mr-2 h-4 w-4 shrink-0" />
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
                <Label htmlFor="reschedule-time" className="text-sm font-medium">Time</Label>
                <Input
                  id="reschedule-time"
                  type="time"
                  value={reschedulePickedTime}
                  onChange={(e) => {
                    setReschedulePickedTime(e.target.value);
                    setRescheduleError('');
                  }}
                  className="w-full"
                />
              </div>
            </div>
            {rescheduleError && (
              <p className="text-sm text-destructive font-medium">
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
                className="w-full sm:w-auto shrink-0 order-2 sm:order-1"
              >
                Cancel
              </Button>
              <Button
                size="lg"
                onClick={handleRescheduleSubmit}
                disabled={!reschedulePickedDate || !reschedulePickedTime || rescheduleSubmitting}
                className="w-full sm:min-w-[240px] shrink-0 order-1 sm:order-2"
              >
                {rescheduleSubmitting ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Rescheduling...
                  </>
                ) : (
                  'Reschedule & notify candidate'
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

