# Automatic Interview Follow-Up Email System

## 🚀 Fully Automatic System - No Commands Needed!

The system now **automatically** checks and sends follow-up emails without requiring any manual commands. The agent learns when to send emails and does it automatically.

## How It Works Automatically

### 1. **Django Signals (Automatic on Save)**
When an interview is created or updated, Django signals automatically trigger:
- ✅ Checks if follow-up email is needed
- ✅ Sends follow-up if conditions are met
- ✅ Sends pre-interview reminder if interview is confirmed
- ✅ Runs in background thread (doesn't slow down requests)

### 2. **Middleware (Automatic on Every Request)**
The middleware automatically checks every 30 minutes:
- ✅ Runs in background thread
- ✅ Checks all pending interviews
- ✅ Sends follow-up emails automatically
- ✅ Sends pre-interview reminders automatically
- ✅ No performance impact (runs in background)

### 3. **API Endpoint (removed)**
There used to be an address anyone could call to trigger the check
(`/recruitment/api/interviews/auto-check/`). It needed no login and answered
with internal details, and the check already runs by itself, so it is gone.

## Automatic Email Logic

### For Unconfirmed Interviews (PENDING Status)

**Automatically sends follow-up email when:**
- ✅ 48+ hours have passed since invitation
- ✅ Candidate hasn't confirmed yet
- ✅ Less than 3 follow-up emails sent (max limit)
- ✅ 24+ hours since last follow-up email
- ✅ Interview is not in the past

**What happens:**
1. Interview is created → Signal checks → No email (too soon)
2. After 48 hours → Signal/middleware checks → Sends follow-up #1
3. After 24 more hours → Signal/middleware checks → Sends follow-up #2
4. After 24 more hours → Signal/middleware checks → Sends follow-up #3
5. After that → No more emails (max limit reached)

### For Confirmed Interviews (SCHEDULED Status)

**Automatically sends reminder email when:**
- ✅ Interview is confirmed (status = SCHEDULED)
- ✅ Interview is 24 hours away (within 2-hour window)
- ✅ Reminder hasn't been sent yet
- ✅ Interview is in the future

**What happens:**
1. Candidate confirms interview → Status changes to SCHEDULED
2. Signal automatically checks → Sets up reminder
3. 24 hours before interview → Signal/middleware sends reminder
4. Reminder sent once → No duplicate reminders

## Safety Features (Automatic)

✅ **Never sends emails for:**
- COMPLETED interviews
- CANCELLED interviews
- Past interviews (scheduled_datetime < now)
- Interviews that already received max follow-ups
- Interviews that received reminder already

✅ **Automatically marks past interviews as COMPLETED**
- Interviews that are 2+ hours past scheduled time
- Prevents sending emails to old interviews

## No Manual Work Required!

The system is **fully automatic**:

1. **When interview is created** → Signal checks automatically
2. **When interview is updated** → Signal checks automatically  
3. **On every request** → Middleware checks every 30 minutes
4. **When candidate confirms** → Signal checks for reminder timing

## Testing the Automatic System

### Test Follow-Up Email

1. Create an interview (status = PENDING)
2. Wait 48+ hours (or modify signal timing for testing)
3. Update the interview (save it) → Signal will trigger
4. Or make any request → Middleware will check after 30 minutes
5. Email will be sent automatically!

### Test Pre-Interview Reminder

1. Confirm an interview (status = SCHEDULED, scheduled_datetime = 24 hours from now)
2. Wait until 24 hours before interview
3. Make any request → Middleware will check
4. Reminder email will be sent automatically!

## Configuration

### Adjust Timing (in signals.py)

```python
# Change follow-up delay (default: 48 hours)
if time_since_invitation >= timedelta(hours=48):  # Change 48 to your preference

# Change reminder timing (default: 24 hours before)
reminder_time = instance.scheduled_datetime - timedelta(hours=24)  # Change 24 to your preference

# Change max follow-ups (default: 3)
if instance.followup_count < 3:  # Change 3 to your preference
```

### Adjust Middleware Check Interval (in middleware.py)

```python
CHECK_INTERVAL = timedelta(minutes=30)  # Change 30 to your preference
```

## Monitoring

Check Django logs to see automatic email activity:

```
🤖 Auto-sending follow-up email for interview #123
✅ Follow-up email sent successfully for interview #123
🤖 Auto-sending pre-interview reminder for interview #456
✅ Pre-interview reminder sent successfully for interview #456
```

## Manual Override (Optional)

If you still want to run the command manually:

```bash
python manage.py send_interview_followups
```

But this is **not required** - the system works automatically!

## Summary

✅ **Fully Automatic** - No commands needed
✅ **Smart Learning** - Agent knows when to send emails
✅ **No Duplicates** - Tracks sent emails
✅ **No Past Emails** - Skips completed/past interviews
✅ **Background Processing** - Doesn't slow down requests
✅ **Multiple Triggers** - Signals + Middleware ensure emails are sent

The system is now **completely automatic** and will handle all follow-up emails without any manual intervention! 🎉

