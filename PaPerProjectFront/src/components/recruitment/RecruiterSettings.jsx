import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useToast } from '@/components/ui/use-toast';
import { DatePicker } from '@/components/ui/date-picker';
import { Loader2, Mail, Calendar, Save, CheckCircle2, XCircle, ChevronLeft, ChevronRight, Lock, Target } from 'lucide-react';
import { 
  getEmailSettings, 
  updateEmailSettings, 
  getInterviewSettings, 
  updateInterviewSettings,
  getQualificationSettings,
  updateQualificationSettings
} from '@/services/recruitmentAgentService';

const RecruiterSettings = () => {
  const { toast } = useToast();
  const [emailSettings, setEmailSettings] = useState({
    followup_delay_hours: 48,
    min_hours_between_followups: 24,
    max_followup_emails: 3,
    reminder_hours_before: 24,
    auto_send_followups: true,
    auto_send_reminders: true,
  });
  const [interviewSettings, setInterviewSettings] = useState({
    schedule_from_date: '',
    schedule_to_date: '',
    start_time: '09:00',
    end_time: '17:00',
    interview_time_gap: 30,
  });
  const [qualificationSettings, setQualificationSettings] = useState({
    interview_threshold: 65,
    hold_threshold: 45,
    use_custom_thresholds: false,
  });
  const [scheduleFromDate, setScheduleFromDate] = useState(null);
  const [scheduleToDate, setScheduleToDate] = useState(null);
  const [timeSlots, setTimeSlots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [calendarMonth, setCalendarMonth] = useState(new Date());

  useEffect(() => {
    fetchSettings();
  }, []);

  // Update calendar month when date range changes
  useEffect(() => {
    if (scheduleFromDate) {
      setCalendarMonth(new Date(scheduleFromDate));
    }
  }, [scheduleFromDate]);

  const fetchSettings = async () => {
    try {
      setLoading(true);
      const [emailRes, interviewRes, qualificationRes] = await Promise.all([
        getEmailSettings(),
        getInterviewSettings(),
        getQualificationSettings().catch(() => ({ status: 'success', data: { interview_threshold: 65, hold_threshold: 45, use_custom_thresholds: false } })),
      ]);

      if (emailRes.status === 'success') {
        setEmailSettings(emailRes.data);
      }
      if (interviewRes.status === 'success') {
        const data = interviewRes.data;
        setInterviewSettings({
          schedule_from_date: data.schedule_from_date || '',
          schedule_to_date: data.schedule_to_date || '',
          start_time: data.start_time || '09:00',
          end_time: data.end_time || '17:00',
          interview_time_gap: data.interview_time_gap || 30,
        });
        // Load time slots from the response
        if (data.time_slots_json && Array.isArray(data.time_slots_json)) {
          setTimeSlots(data.time_slots_json);
        } else {
          setTimeSlots([]);
        }
        // Convert date strings to Date objects for DatePicker - use local time parsing
        if (data.schedule_from_date) {
          const fromDate = parseDateLocal(data.schedule_from_date);
          if (fromDate) {
            setScheduleFromDate(fromDate);
            setCalendarMonth(new Date(fromDate)); // Set calendar to show the start date month
          }
        } else {
          setScheduleFromDate(null);
        }
        if (data.schedule_to_date) {
          const toDate = parseDateLocal(data.schedule_to_date);
          if (toDate) {
            setScheduleToDate(toDate);
          }
        } else {
          setScheduleToDate(null);
        }
      }
      if (qualificationRes.status === 'success') {
        setQualificationSettings(qualificationRes.data);
      }
    } catch (error) {
      console.error('Error fetching settings:', error);
      toast({
        title: 'Error',
        description: 'Failed to load settings',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleSaveEmailSettings = async () => {
    try {
      setSaving(true);
      const response = await updateEmailSettings(emailSettings);
      if (response.status === 'success') {
        toast({
          title: 'Success',
          description: 'Email settings saved successfully',
        });
      }
    } catch (error) {
      console.error('Error saving email settings:', error);
      toast({
        title: 'Error',
        description: error.message || 'Failed to save email settings',
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleSaveInterviewSettings = async () => {
    try {
      setSaving(true);
        // Convert Date objects to local date strings (YYYY-MM-DD format) - avoid timezone issues
        const settingsToSave = {
          ...interviewSettings,
          schedule_from_date: scheduleFromDate ? formatDateLocal(scheduleFromDate) : '',
          schedule_to_date: scheduleToDate ? formatDateLocal(scheduleToDate) : '',
          // Don't send time_slots_json to trigger automatic generation when date range is provided
          // Only send it if we're explicitly updating availability
        };
      const response = await updateInterviewSettings(settingsToSave);
      if (response.status === 'success') {
        // Update time slots from response - they should be auto-generated
        if (response.data && response.data.time_slots_json) {
          setTimeSlots(response.data.time_slots_json);
        }
        // Update date strings in state
        if (response.data) {
          setInterviewSettings(prev => ({
            ...prev,
            schedule_from_date: response.data.schedule_from_date || '',
            schedule_to_date: response.data.schedule_to_date || '',
          }));
          // Update Date objects - use local time parsing to avoid timezone issues
          if (response.data.schedule_from_date) {
            const fromDate = parseDateLocal(response.data.schedule_from_date);
            if (fromDate) {
              setScheduleFromDate(fromDate);
              setCalendarMonth(new Date(fromDate)); // Update calendar to show the start date month
            }
          } else {
            setScheduleFromDate(null);
          }
          if (response.data.schedule_to_date) {
            const toDate = parseDateLocal(response.data.schedule_to_date);
            if (toDate) {
              setScheduleToDate(toDate);
            }
          } else {
            setScheduleToDate(null);
          }
        }
        toast({
          title: 'Success',
          description: response.data?.time_slots_json?.length 
            ? `Interview settings saved. ${response.data.time_slots_json.length} time slots generated.`
            : 'Interview settings saved successfully',
        });
      }
    } catch (error) {
      console.error('Error saving interview settings:', error);
      toast({
        title: 'Error',
        description: error.message || 'Failed to save interview settings',
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleToggleTimeSlot = (datetime) => {
    setTimeSlots(prevSlots => 
      prevSlots.map(slot => 
        slot.datetime === datetime 
          ? { ...slot, available: !slot.available }
          : slot
      )
    );
  };

  const handleGenerateTimeSlots = async () => {
    if (!scheduleFromDate || !scheduleToDate) {
      toast({
        title: 'Error',
        description: 'Please set both start and end dates to generate time slots',
        variant: 'destructive',
      });
      return;
    }

    // Just call the save function - it will automatically generate slots
    await handleSaveInterviewSettings();
  };

  const handleSaveQualificationSettings = async () => {
    try {
      setSaving(true);
      const response = await updateQualificationSettings(qualificationSettings);
      if (response.status === 'success') {
        toast({
          title: 'Success',
          description: 'Qualification settings saved successfully',
        });
        if (response.data) {
          setQualificationSettings(response.data);
        }
      }
    } catch (error) {
      console.error('Error saving qualification settings:', error);
      toast({
        title: 'Error',
        description: error.message || 'Failed to save qualification settings',
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateTimeSlotAvailability = async () => {
    try {
      setSaving(true);
      // Send only availability updates with the update_availability flag
      const response = await updateInterviewSettings({
        update_availability: true,
        time_slots_json: timeSlots,
      });
      if (response.status === 'success') {
        // Update time slots from response
        if (response.data && response.data.time_slots_json) {
          setTimeSlots(response.data.time_slots_json);
        }
        toast({
          title: 'Success',
          description: 'Time slot availability updated successfully',
        });
      }
    } catch (error) {
      console.error('Error updating time slot availability:', error);
      toast({
        title: 'Error',
        description: error.message || 'Failed to update time slot availability',
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  };

  // Format time for display (e.g., "10:00am")
  // Helper function to format date as YYYY-MM-DD in local time (not UTC)
  const formatDateLocal = (date) => {
    if (!date) return '';
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  // Helper function to parse date string to Date object in local time
  const parseDateLocal = (dateString) => {
    if (!dateString) return null;
    const [year, month, day] = dateString.split('-').map(Number);
    return new Date(year, month - 1, day);
  };

  const formatTime = (hours, mins) => {
    const period = hours >= 12 ? 'pm' : 'am';
    const displayHour = hours > 12 ? hours - 12 : (hours === 0 ? 12 : hours);
    return `${displayHour}:${mins.toString().padStart(2, '0')}${period}`;
  };

  // Format month and year for calendar header
  const formatMonthYear = (date) => {
    return date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  };

  // Get all unique dates from time slots or date range
  const getAvailableDates = () => {
    if (!scheduleFromDate || !scheduleToDate) return [];
    const dates = [];
    // Create new Date objects to avoid mutating originals
    const currentDate = new Date(scheduleFromDate.getFullYear(), scheduleFromDate.getMonth(), scheduleFromDate.getDate());
    const endDate = new Date(scheduleToDate.getFullYear(), scheduleToDate.getMonth(), scheduleToDate.getDate());
    
    // Include both start and end dates (inclusive range)
    while (currentDate <= endDate) {
      dates.push(new Date(currentDate));
      currentDate.setDate(currentDate.getDate() + 1);
    }
    return dates;
  };

  // Get all unique times from time slots
  const getUniqueTimes = () => {
    if (timeSlots.length === 0) return [];
    const times = new Set();
    timeSlots.forEach(slot => {
      if (slot.time) {
        times.add(slot.time);
      }
    });
    return Array.from(times).sort();
  };

  // Group time slots by date
  const getSlotsByDate = () => {
    const slotsByDate = {};
    timeSlots.forEach(slot => {
      const normalizedDate = slot.date.split('T')[0];
      if (!slotsByDate[normalizedDate]) {
        slotsByDate[normalizedDate] = [];
      }
      slotsByDate[normalizedDate].push(slot);
    });
    return slotsByDate;
  };

  // Generate calendar dates for the current month
  const generateCalendarDates = () => {
    const year = calendarMonth.getFullYear();
    const month = calendarMonth.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const startDay = firstDay.getDay();
    const daysInMonth = lastDay.getDate();
    const availableDates = getAvailableDates();

    // Create a set of available date strings for quick lookup - use local time
    const availableDateStrings = new Set(
      availableDates.map(d => formatDateLocal(d))
    );

    // Get date range strings - use local time
    const fromDateStr = scheduleFromDate ? formatDateLocal(scheduleFromDate) : null;
    const toDateStr = scheduleToDate ? formatDateLocal(scheduleToDate) : null;

    const dates = [];
    
    // Empty cells for days before month starts
    for (let i = 0; i < startDay; i++) {
      dates.push({ day: null, isAvailable: false, isInRange: false, isStart: false, isEnd: false });
    }

    // Days of the month
    for (let day = 1; day <= daysInMonth; day++) {
      const date = new Date(year, month, day);
      const dateStr = formatDateLocal(date); // Use local time formatting
      const isAvailable = availableDateStrings.has(dateStr);
      
      // Check if date is in the selected range
      let isInRange = false;
      let isStart = false;
      let isEnd = false;
      
      if (fromDateStr && toDateStr) {
        isInRange = dateStr >= fromDateStr && dateStr <= toDateStr;
        isStart = dateStr === fromDateStr;
        isEnd = dateStr === toDateStr;
      } else if (fromDateStr) {
        isStart = dateStr === fromDateStr;
        isInRange = isStart;
      }
      
      dates.push({ day, date: dateStr, isAvailable, isInRange, isStart, isEnd });
    }

    return dates;
  };

  const changeCalendarMonth = (direction) => {
    setCalendarMonth(prev => {
      const newDate = new Date(prev);
      newDate.setMonth(prev.getMonth() + direction);
      return newDate;
    });
  };

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Tabs defaultValue="email" className="space-y-4">
        <TabsList>
          <TabsTrigger value="email">
            <Mail className="h-4 w-4 mr-2" />
            Email Settings
          </TabsTrigger>
          <TabsTrigger value="interview">
            <Calendar className="h-4 w-4 mr-2" />
            Interview Settings
          </TabsTrigger>
          <TabsTrigger value="qualification">
            <Target className="h-4 w-4 mr-2" />
            Qualification Settings
          </TabsTrigger>
        </TabsList>

        <TabsContent value="email">
          <Card>
            <CardHeader>
              <CardTitle>Email Settings</CardTitle>
              <CardDescription>
                Configure email timing preferences for follow-ups and reminders
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="followup_delay">Follow-up Delay (hours)</Label>
                  <Input
                    id="followup_delay"
                    type="number"
                    step="0.1"
                    value={emailSettings.followup_delay_hours}
                    onChange={(e) => setEmailSettings({
                      ...emailSettings,
                      followup_delay_hours: parseFloat(e.target.value) || 0,
                    })}
                  />
                  <p className="text-xs text-muted-foreground">
                    Hours to wait before sending first follow-up email for unconfirmed interviews
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="min_hours_between">Min Hours Between Follow-ups</Label>
                  <Input
                    id="min_hours_between"
                    type="number"
                    step="0.1"
                    value={emailSettings.min_hours_between_followups}
                    onChange={(e) => setEmailSettings({
                      ...emailSettings,
                      min_hours_between_followups: parseFloat(e.target.value) || 0,
                    })}
                  />
                  <p className="text-xs text-muted-foreground">
                    Minimum hours between follow-up emails
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="max_followups">Max Follow-up Emails</Label>
                  <Input
                    id="max_followups"
                    type="number"
                    value={emailSettings.max_followup_emails}
                    onChange={(e) => setEmailSettings({
                      ...emailSettings,
                      max_followup_emails: parseInt(e.target.value) || 0,
                    })}
                  />
                  <p className="text-xs text-muted-foreground">
                    Maximum number of follow-up emails to send
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="reminder_hours">Reminder Hours Before Interview</Label>
                  <Input
                    id="reminder_hours"
                    type="number"
                    step="0.1"
                    value={emailSettings.reminder_hours_before}
                    onChange={(e) => setEmailSettings({
                      ...emailSettings,
                      reminder_hours_before: parseFloat(e.target.value) || 0,
                    })}
                  />
                  <p className="text-xs text-muted-foreground">
                    Hours before scheduled interview to send reminder email
                  </p>
                </div>

                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label htmlFor="auto_followups">Auto-send Follow-ups</Label>
                    <p className="text-xs text-muted-foreground">
                      Automatically send follow-up emails for unconfirmed interviews
                    </p>
                  </div>
                  <Switch
                    id="auto_followups"
                    checked={emailSettings.auto_send_followups}
                    onCheckedChange={(checked) => setEmailSettings({
                      ...emailSettings,
                      auto_send_followups: checked,
                    })}
                  />
                </div>

                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label htmlFor="auto_reminders">Auto-send Reminders</Label>
                    <p className="text-xs text-muted-foreground">
                      Automatically send pre-interview reminder emails
                    </p>
                  </div>
                  <Switch
                    id="auto_reminders"
                    checked={emailSettings.auto_send_reminders}
                    onCheckedChange={(checked) => setEmailSettings({
                      ...emailSettings,
                      auto_send_reminders: checked,
                    })}
                  />
                </div>
              </div>

              <Button onClick={handleSaveEmailSettings} disabled={saving}>
                {saving ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Saving...
                  </>
                ) : (
                  <>
                    <Save className="h-4 w-4 mr-2" />
                    Save Email Settings
                  </>
                )}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="interview">
          <Card>
            <CardHeader>
              <CardTitle>Interview Settings</CardTitle>
              <CardDescription>
                Configure interview scheduling preferences
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="schedule_from">Schedule From Date</Label>
                    <DatePicker
                      date={scheduleFromDate}
                      setDate={(date) => {
                        if (date) {
                          setScheduleFromDate(date);
                          setCalendarMonth(new Date(date)); // Update calendar to show selected month
                          // Also update the string format for consistency - use local time
                          setInterviewSettings({
                            ...interviewSettings,
                            schedule_from_date: formatDateLocal(date),
                          });
                        } else {
                          setScheduleFromDate(null);
                          setInterviewSettings({
                            ...interviewSettings,
                            schedule_from_date: '',
                          });
                        }
                      }}
                      placeholder="Select start date"
                    />
                    <p className="text-xs text-muted-foreground">
                      Start date for scheduling (leave empty for today)
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="schedule_to">Schedule To Date</Label>
                    <DatePicker
                      date={scheduleToDate}
                      setDate={(date) => {
                        if (date) {
                          setScheduleToDate(date);
                          // Also update the string format for consistency - use local time
                          setInterviewSettings({
                            ...interviewSettings,
                            schedule_to_date: formatDateLocal(date),
                          });
                        } else {
                          setScheduleToDate(null);
                          setInterviewSettings({
                            ...interviewSettings,
                            schedule_to_date: '',
                          });
                        }
                      }}
                      placeholder="Select end date"
                    />
                    <p className="text-xs text-muted-foreground">
                      End date for scheduling (leave empty for no limit)
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="start_time">Start Time</Label>
                    <Input
                      id="start_time"
                      type="time"
                      value={interviewSettings.start_time}
                      onChange={(e) => setInterviewSettings({
                        ...interviewSettings,
                        start_time: e.target.value,
                      })}
                    />
                    <p className="text-xs text-muted-foreground">
                      Start time of day for interviews
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="end_time">End Time</Label>
                    <Input
                      id="end_time"
                      type="time"
                      value={interviewSettings.end_time}
                      onChange={(e) => setInterviewSettings({
                        ...interviewSettings,
                        end_time: e.target.value,
                      })}
                    />
                    <p className="text-xs text-muted-foreground">
                      End time of day for interviews
                    </p>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="time_gap">Interview Time Gap (minutes)</Label>
                  <Input
                    id="time_gap"
                    type="number"
                    value={interviewSettings.interview_time_gap}
                    onChange={(e) => setInterviewSettings({
                      ...interviewSettings,
                      interview_time_gap: parseInt(e.target.value) || 30,
                    })}
                  />
                  <p className="text-xs text-muted-foreground">
                    Time gap between interview slots in minutes
                  </p>
                </div>
              </div>

              <div className="flex gap-2">
                <Button onClick={handleSaveInterviewSettings} disabled={saving}>
                  {saving ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <Save className="h-4 w-4 mr-2" />
                      Save Interview Settings
                    </>
                  )}
                </Button>
                {scheduleFromDate && scheduleToDate && (
                  <Button 
                    onClick={handleGenerateTimeSlots} 
                    disabled={saving}
                    variant="outline"
                  >
                    Generate Time Slots
                  </Button>
                )}
              </div>

              {/* Time Slots Display - Calendar and Grid Design */}
              {scheduleFromDate && scheduleToDate && timeSlots.length > 0 && (
                <div className="mt-8 space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Calendar className="h-5 w-5" />
                      <h3 className="text-lg font-semibold">Generated Time Slots</h3>
                    </div>
                    <Button 
                      onClick={handleUpdateTimeSlotAvailability} 
                      disabled={saving}
                      variant="outline"
                      className="bg-indigo-600 hover:bg-indigo-700 text-white border-indigo-600"
                    >
                      <Lock className="h-4 w-4 mr-2" />
                      {saving ? 'Updating...' : 'Update Availability'}
                    </Button>
                  </div>

                  <div className="flex gap-8 bg-slate-900 rounded-2xl p-8 border border-slate-700">
                    {/* Calendar View */}
                    <div className="min-w-[300px] bg-slate-800 rounded-xl p-5 border border-slate-600">
                      <div className="flex justify-between items-center mb-5">
                        <button
                          onClick={() => changeCalendarMonth(-1)}
                          className="w-9 h-9 flex items-center justify-center rounded-lg bg-slate-600 hover:bg-indigo-600 border border-slate-500 text-white transition-colors"
                        >
                          <ChevronLeft className="h-5 w-5" />
                        </button>
                        <div className="text-lg font-semibold text-white">
                          {formatMonthYear(calendarMonth)}
                        </div>
                        <button
                          onClick={() => changeCalendarMonth(1)}
                          className="w-9 h-9 flex items-center justify-center rounded-lg bg-slate-600 hover:bg-indigo-600 border border-slate-500 text-white transition-colors"
                        >
                          <ChevronRight className="h-5 w-5" />
                        </button>
                      </div>
                      <div className="grid grid-cols-7 gap-2 mb-3 text-xs font-semibold text-slate-400 text-center">
                        <div>S</div>
                        <div>M</div>
                        <div>T</div>
                        <div>W</div>
                        <div>T</div>
                        <div>F</div>
                        <div>S</div>
                      </div>
                      <div className="grid grid-cols-7 gap-2">
                        {generateCalendarDates().map((dateInfo, idx) => (
                          <div
                            key={idx}
                            className={`
                              aspect-square flex items-center justify-center rounded-lg text-sm transition-colors min-h-[36px]
                              ${dateInfo.day === null 
                                ? 'invisible' 
                                : dateInfo.isInRange
                                  ? dateInfo.isStart
                                    ? 'bg-indigo-600 text-white font-bold'
                                    : dateInfo.isEnd
                                      ? 'bg-indigo-500 text-white font-bold'
                                      : 'bg-indigo-500/70 text-white font-bold'
                                  : dateInfo.isAvailable
                                    ? 'bg-slate-600 text-white font-bold cursor-pointer hover:bg-indigo-600'
                                    : 'text-slate-500'
                              }
                            `}
                          >
                            {dateInfo.day}
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Time Slots Grid */}
                    <div className="flex-1 overflow-x-auto">
                      <div className="min-w-full">
                        {/* Header Row */}
                        <div className="grid mb-3 gap-3" style={{ gridTemplateColumns: `120px repeat(${getAvailableDates().length}, minmax(140px, 1fr))` }}>
                          <div></div>
                          {getAvailableDates().map((date) => {
                            const dayName = date.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase();
                            const dayNum = date.getDate();
                            const dateStr = formatDateLocal(date); // Use local time formatting
                            const fromDateStr = scheduleFromDate ? formatDateLocal(scheduleFromDate) : null;
                            const toDateStr = scheduleToDate ? formatDateLocal(scheduleToDate) : null;
                            const isStart = dateStr === fromDateStr;
                            const isInRange = fromDateStr && toDateStr && dateStr >= fromDateStr && dateStr <= toDateStr;
                            
                            return (
                              <div
                                key={formatDateLocal(date)}
                                className={`
                                  bg-slate-700 border border-slate-600 rounded-lg p-4 text-center font-semibold text-white text-sm
                                  ${isStart ? 'bg-indigo-600 border-indigo-600' : isInRange ? 'bg-indigo-500/80 border-indigo-500' : ''}
                                `}
                              >
                                {dayName} {dayNum}
                              </div>
                            );
                          })}
                        </div>

                        {/* Time Slot Rows */}
                        {getUniqueTimes().map((timeStr) => {
                          const [hours, mins] = timeStr.split(':').map(Number);
                          const displayTime = formatTime(hours, mins);
                          const slotsByDate = getSlotsByDate();
                          
                          return (
                            <div
                              key={timeStr}
                              className="grid mb-2 gap-3"
                              style={{ gridTemplateColumns: `120px repeat(${getAvailableDates().length}, minmax(140px, 1fr))` }}
                            >
                              <div className="font-semibold text-slate-400 text-sm flex items-center justify-end pr-4">
                                {displayTime}
                              </div>
                              {getAvailableDates().map((date) => {
                                const dateStr = formatDateLocal(date); // Use local time formatting
                                const slot = slotsByDate[dateStr]?.find(s => s.time === timeStr);
                                
                                if (slot) {
                                  const isAvailable = slot.available !== false;
                                  return (
                                    <div
                                      key={`${dateStr}-${timeStr}`}
                                      className={`
                                        bg-slate-800 border border-slate-600 rounded-lg p-3.5 text-sm text-white cursor-pointer transition-all relative min-h-[52px] flex items-center
                                        ${isAvailable 
                                          ? 'hover:bg-indigo-600 hover:border-indigo-500' 
                                          : 'opacity-50 line-through bg-slate-700'
                                        }
                                      `}
                                      onClick={() => handleToggleTimeSlot(slot.datetime)}
                                    >
                                      <input
                                        type="checkbox"
                                        checked={isAvailable}
                                        onChange={() => handleToggleTimeSlot(slot.datetime)}
                                        className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 accent-indigo-500 cursor-pointer z-10"
                                        onClick={(e) => e.stopPropagation()}
                                      />
                                      <span className="ml-11 block text-center w-full">{displayTime}</span>
                                    </div>
                                  );
                                } else {
                                  return (
                                    <div
                                      key={`${dateStr}-${timeStr}`}
                                      className="bg-slate-800 border border-slate-600 rounded-lg opacity-40 cursor-not-allowed flex items-center justify-center min-h-[52px]"
                                    >
                                      <span className="text-slate-500 text-lg">-</span>
                                    </div>
                                  );
                                }
                              })}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {timeSlots.length === 0 && scheduleFromDate && scheduleToDate && (
                <div className="mt-4 p-4 bg-slate-800 rounded-lg text-center text-sm text-slate-400 border border-slate-700">
                  No time slots generated yet. Click "Save Interview Settings" to automatically generate time slots based on your date range and time settings.
                </div>
              )}

              {timeSlots.length > 0 && scheduleFromDate && scheduleToDate && (
                <div className="mt-2 text-xs text-slate-400 text-center">
                  Showing {timeSlots.length} time slots for {getAvailableDates().length} day(s)
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="qualification">
          <Card>
            <CardHeader>
              <CardTitle>Qualification Settings</CardTitle>
              <CardDescription>
                Configure decision thresholds for candidate qualification (INTERVIEW/HOLD/REJECT)
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label htmlFor="use_custom_thresholds">Use Custom Thresholds</Label>
                    <p className="text-xs text-muted-foreground">
                      Enable custom decision thresholds. If disabled, default values (INTERVIEW: 65, HOLD: 45) will be used.
                    </p>
                  </div>
                  <Switch
                    id="use_custom_thresholds"
                    checked={qualificationSettings.use_custom_thresholds}
                    onCheckedChange={(checked) => setQualificationSettings({
                      ...qualificationSettings,
                      use_custom_thresholds: checked,
                    })}
                  />
                </div>

                {qualificationSettings.use_custom_thresholds && (
                  <>
                    <div className="space-y-2">
                      <Label htmlFor="interview_threshold">INTERVIEW Threshold (0-100)</Label>
                      <Input
                        id="interview_threshold"
                        type="number"
                        min="0"
                        max="100"
                        value={qualificationSettings.interview_threshold}
                        onChange={(e) => {
                          const value = parseInt(e.target.value) || 65;
                          setQualificationSettings({
                            ...qualificationSettings,
                            interview_threshold: Math.max(0, Math.min(100, value)),
                          });
                        }}
                      />
                      <p className="text-xs text-muted-foreground">
                        Minimum confidence score (0-100) to mark candidate as INTERVIEW. 
                        Candidates with score &gt;= this value will be marked for interview.
                      </p>
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="hold_threshold">HOLD Threshold (0-100)</Label>
                      <Input
                        id="hold_threshold"
                        type="number"
                        min="0"
                        max="100"
                        value={qualificationSettings.hold_threshold}
                        onChange={(e) => {
                          const value = parseInt(e.target.value) || 45;
                          setQualificationSettings({
                            ...qualificationSettings,
                            hold_threshold: Math.max(0, Math.min(100, value)),
                          });
                        }}
                      />
                      <p className="text-xs text-muted-foreground">
                        Minimum confidence score (0-100) to mark candidate as HOLD. 
                        Candidates with score &gt;= this value but &lt; INTERVIEW threshold will be put on hold.
                        Scores below this will be REJECTED.
                      </p>
                    </div>

                    <div className="p-4 bg-muted/50 rounded-lg border">
                      <p className="text-sm font-semibold mb-2">Decision Logic:</p>
                      <ul className="text-xs text-muted-foreground space-y-1 list-disc list-inside">
                        <li>Score &gt;= {qualificationSettings.interview_threshold} → <span className="text-green-500 font-medium">INTERVIEW</span></li>
                        <li>Score &gt;= {qualificationSettings.hold_threshold} and &lt; {qualificationSettings.interview_threshold} → <span className="text-yellow-500 font-medium">HOLD</span></li>
                        <li>Score &lt; {qualificationSettings.hold_threshold} → <span className="text-red-500 font-medium">REJECT</span></li>
                      </ul>
                      {qualificationSettings.interview_threshold <= qualificationSettings.hold_threshold && (
                        <p className="text-xs text-red-500 mt-2">
                          ⚠️ Warning: INTERVIEW threshold must be greater than HOLD threshold
                        </p>
                      )}
                    </div>
                  </>
                )}

                {!qualificationSettings.use_custom_thresholds && (
                  <div className="p-4 bg-muted/50 rounded-lg border">
                    <p className="text-sm font-semibold mb-2">Default Thresholds (Currently Active):</p>
                    <ul className="text-xs text-muted-foreground space-y-1 list-disc list-inside">
                      <li>Score &gt;= 65 → <span className="text-green-500 font-medium">INTERVIEW</span></li>
                      <li>Score &gt;= 45 and &lt; 65 → <span className="text-yellow-500 font-medium">HOLD</span></li>
                      <li>Score &lt; 45 → <span className="text-red-500 font-medium">REJECT</span></li>
                    </ul>
                  </div>
                )}
              </div>

              <Button onClick={handleSaveQualificationSettings} disabled={saving || (qualificationSettings.use_custom_thresholds && qualificationSettings.interview_threshold <= qualificationSettings.hold_threshold)}>
                {saving ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Saving...
                  </>
                ) : (
                  <>
                    <Save className="h-4 w-4 mr-2" />
                    Save Qualification Settings
                  </>
                )}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default RecruiterSettings;


