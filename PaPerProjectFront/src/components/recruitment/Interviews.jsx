import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Plus, Calendar, Mail, Phone, Clock } from 'lucide-react';
import { getInterviews, scheduleInterview, getCVRecords } from '@/services/recruitmentAgentService';

const Interviews = ({ onUpdate }) => {
  const { toast } = useToast();
  const [interviews, setInterviews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [statusFilter, setStatusFilter] = useState('');
  const [formData, setFormData] = useState({
    candidate_name: '',
    candidate_email: '',
    candidate_phone: '',
    job_role: '',
    interview_type: 'ONLINE',
    cv_record_id: '',
  });
  const [cvRecords, setCvRecords] = useState([]);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchInterviews();
    fetchCVRecords();
  }, [statusFilter]);

  const fetchInterviews = async () => {
    try {
      setLoading(true);
      const response = await getInterviews(statusFilter ? { status: statusFilter } : {});
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

  const fetchCVRecords = async () => {
    try {
      const response = await getCVRecords({ decision: 'INTERVIEW' });
      if (response.status === 'success') {
        setCvRecords(response.data || []);
      }
    } catch (error) {
      console.error('Error fetching CV records:', error);
    }
  };

  const handleSchedule = async () => {
    if (!formData.candidate_name || !formData.candidate_email || !formData.job_role) {
      toast({
        title: 'Validation Error',
        description: 'Candidate name, email, and job role are required',
        variant: 'destructive',
      });
      return;
    }

    try {
      setSubmitting(true);
      const response = await scheduleInterview({
        ...formData,
        cv_record_id: formData.cv_record_id || null,
      });
      if (response.status === 'success') {
        toast({
          title: 'Success',
          description: 'Interview scheduled successfully',
        });
        setShowScheduleModal(false);
        resetForm();
        fetchInterviews();
        if (onUpdate) onUpdate();
      }
    } catch (error) {
      console.error('Error scheduling interview:', error);
      toast({
        title: 'Error',
        description: error.message || 'Failed to schedule interview',
        variant: 'destructive',
      });
    } finally {
      setSubmitting(false);
    }
  };

  const resetForm = () => {
    setFormData({
      candidate_name: '',
      candidate_email: '',
      candidate_phone: '',
      job_role: '',
      interview_type: 'ONLINE',
      cv_record_id: '',
    });
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
          <Button onClick={() => setShowScheduleModal(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Schedule Interview
          </Button>
        </div>
      </div>

      {interviews.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Calendar className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <p className="text-lg font-medium mb-2">No interviews yet</p>
            <p className="text-sm text-muted-foreground mb-4">
              Schedule your first interview to get started
            </p>
            <Button onClick={() => setShowScheduleModal(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Schedule Interview
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {interviews.map((interview) => (
            <Card key={interview.id}>
              <CardHeader>
                <div className="flex justify-between items-start">
                  <div>
                    <CardTitle className="text-lg">{interview.candidate_name}</CardTitle>
                    <CardDescription className="mt-1">
                      {interview.job_title || interview.job_role}
                    </CardDescription>
                  </div>
                  {getStatusBadge(interview.status)}
                </div>
              </CardHeader>
              <CardContent>
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
                        <Clock className="h-4 w-4 text-muted-foreground" />
                        <span>
                          {new Date(interview.scheduled_datetime).toLocaleString()}
                        </span>
                      </div>
                    )}
                    {interview.selected_slot && (
                      <div className="text-sm text-muted-foreground">
                        Selected: {interview.selected_slot}
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Schedule Modal */}
      <Dialog open={showScheduleModal} onOpenChange={setShowScheduleModal}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Schedule Interview</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="cv-record">Select Candidate (Optional)</Label>
              <Select
                value={formData.cv_record_id || "manual"}
                onValueChange={(value) => {
                  if (value === "manual") {
                    setFormData({ ...formData, cv_record_id: '' });
                    return;
                  }
                  setFormData({ ...formData, cv_record_id: value });
                  const record = cvRecords.find(r => r.id.toString() === value);
                  if (record && record.parsed) {
                    setFormData({
                      ...formData,
                      cv_record_id: value,
                      candidate_name: record.parsed.name || '',
                      candidate_email: record.parsed.email || '',
                      candidate_phone: record.parsed.phone || '',
                    });
                  }
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select from candidates" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="manual">Manual Entry</SelectItem>
                  {cvRecords.map((record) => (
                    <SelectItem key={record.id} value={record.id.toString()}>
                      {record.parsed?.name || record.file_name} - {record.parsed?.email || ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="candidate_name">Candidate Name *</Label>
              <Input
                id="candidate_name"
                value={formData.candidate_name}
                onChange={(e) => setFormData({ ...formData, candidate_name: e.target.value })}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="candidate_email">Candidate Email *</Label>
              <Input
                id="candidate_email"
                type="email"
                value={formData.candidate_email}
                onChange={(e) => setFormData({ ...formData, candidate_email: e.target.value })}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="candidate_phone">Candidate Phone</Label>
              <Input
                id="candidate_phone"
                value={formData.candidate_phone}
                onChange={(e) => setFormData({ ...formData, candidate_phone: e.target.value })}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="job_role">Job Role *</Label>
              <Input
                id="job_role"
                value={formData.job_role}
                onChange={(e) => setFormData({ ...formData, job_role: e.target.value })}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="interview_type">Interview Type</Label>
              <Select
                value={formData.interview_type}
                onValueChange={(value) => setFormData({ ...formData, interview_type: value })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ONLINE">Online</SelectItem>
                  <SelectItem value="ONSITE">Onsite</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => {
                setShowScheduleModal(false);
                resetForm();
              }} disabled={submitting}>
                Cancel
              </Button>
              <Button onClick={handleSchedule} disabled={submitting}>
                {submitting ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Scheduling...
                  </>
                ) : (
                  'Schedule Interview'
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

