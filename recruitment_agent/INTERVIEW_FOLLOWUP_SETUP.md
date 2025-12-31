# Interview Follow-Up Email System - Setup Guide

## Overview

This system automatically sends follow-up emails to candidates for interview confirmations and reminders. It ensures:

1. **Follow-up emails** are sent to candidates who haven't confirmed their interview (PENDING status)
2. **Reminder emails** are sent before scheduled interviews (SCHEDULED status)
3. **No duplicate emails** - tracks sent emails to prevent spam
4. **No emails for past interviews** - automatically skips completed/cancelled/past interviews

## Features

### For Unconfirmed Interviews (PENDING)
- Sends follow-up emails if candidate hasn't confirmed after 48 hours (configurable)
- Maximum 3 follow-up emails per interview (configurable)
- Minimum 24 hours between follow-up emails
- Includes slot selection link in every email

### For Confirmed Interviews (SCHEDULED)
- Sends reminder email 24 hours before the interview (configurable)
- Only sends once per interview
- Only for future interviews (never for past interviews)

### Safety Features
- Never sends emails for COMPLETED or CANCELLED interviews
- Never sends emails for interviews in the past
- Tracks email count to prevent spam
- Automatically marks past interviews as COMPLETED

## Usage

### Manual Execution

Run the management command manually:

```bash
# Send follow-up emails (production mode)
python manage.py send_interview_followups

# Test run without sending emails (dry-run mode)
python manage.py send_interview_followups --dry-run

# Customize timing
python manage.py send_interview_followups --followup-hours 72 --reminder-hours 24 --max-followups 3
```

### Command Options

- `--dry-run`: Run without actually sending emails (for testing)
- `--followup-hours`: Hours to wait before sending first follow-up (default: 48)
- `--reminder-hours`: Hours before interview to send reminder (default: 24)
- `--max-followups`: Maximum number of follow-up emails to send (default: 3)

### Automated Execution (Cron Job)

To run this automatically, set up a cron job:

#### Linux/Mac (Crontab)

```bash
# Edit crontab
crontab -e

# Run every 6 hours
0 */6 * * * cd /path/to/your/project && /path/to/python manage.py send_interview_followups >> /path/to/logs/interview_followups.log 2>&1

# Or run every hour (more frequent checks)
0 * * * * cd /path/to/your/project && /path/to/python manage.py send_interview_followups >> /path/to/logs/interview_followups.log 2>&1
```

#### Windows (Task Scheduler)

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger (e.g., Daily at specific times, or every 6 hours)
4. Action: Start a program
5. Program: `python.exe`
6. Arguments: `manage.py send_interview_followups`
7. Start in: `D:\Umer Bhai Work\AI Project Django\AI Employee`

#### Using Django-Q or Celery (Recommended for Production)

If you're using Django-Q or Celery, you can schedule this as a periodic task:

```python
# In your settings.py or tasks.py
from django_q.tasks import schedule

schedule(
    'recruitment_agent.management.commands.send_interview_followups',
    name='Send Interview Follow-ups',
    schedule_type=Schedule.HOURLY,  # Run every hour
)
```

## How It Works

### Follow-Up Email Flow (PENDING Interviews)

1. **Check**: Find all PENDING interviews with invitation sent
2. **Time Check**: Verify 48+ hours have passed since invitation
3. **Count Check**: Verify we haven't sent max follow-ups (default: 3)
4. **Interval Check**: Verify 24+ hours since last follow-up
5. **Send**: Send follow-up email with slot selection link
6. **Update**: Increment followup_count and update last_followup_sent_at

### Reminder Email Flow (SCHEDULED Interviews)

1. **Check**: Find all SCHEDULED interviews with future scheduled_datetime
2. **Reminder Check**: Verify reminder hasn't been sent yet
3. **Time Check**: Verify we're within 2 hours of reminder time (24h before interview)
4. **Send**: Send pre-interview reminder email
5. **Update**: Set pre_interview_reminder_sent_at timestamp

### Safety Checks

- ✅ Skips COMPLETED interviews
- ✅ Skips CANCELLED interviews
- ✅ Skips past interviews (scheduled_datetime < now)
- ✅ Skips if reminder already sent
- ✅ Skips if max follow-ups reached
- ✅ Skips if not enough time has passed

## Database Fields Added

The following fields were added to the `Interview` model:

- `followup_count` (IntegerField): Number of follow-up emails sent (default: 0)
- `last_followup_sent_at` (DateTimeField): Last time a follow-up email was sent
- `pre_interview_reminder_sent_at` (DateTimeField): When the pre-interview reminder was sent

## Email Templates

The system uses the following email templates:

- **Follow-up emails**: `templates/recruitment_agent/emails/interview_followup.html` and `.txt`
- **Pre-interview reminders**: `templates/recruitment_agent/emails/interview_pre_reminder.html` and `.txt`

## Testing

Before deploying to production:

1. **Test with dry-run**:
   ```bash
   python manage.py send_interview_followups --dry-run
   ```

2. **Test with a single interview**:
   - Create a test interview with PENDING status
   - Wait 48+ hours (or adjust --followup-hours)
   - Run the command
   - Verify email is sent

3. **Test reminder**:
   - Create a test interview with SCHEDULED status
   - Set scheduled_datetime to 24 hours from now
   - Run the command
   - Verify reminder email is sent

## Monitoring

The command outputs detailed statistics:

```
📊 SUMMARY
======================================================================
  ✅ Follow-up emails sent: 2
  ✅ Reminder emails sent: 1
  ⏭️  Skipped (too soon): 5
  ⏭️  Skipped (max follow-ups): 1
  ⏭️  Skipped (past interviews): 0
  ⏭️  Skipped (completed/cancelled): 3
  ❌ Errors: 0
======================================================================
```

## Troubleshooting

### Emails not sending

1. Check EMAIL_BACKEND in settings.py
2. Verify SMTP credentials in .env file
3. Check email logs in console (if using console backend)
4. Verify templates exist in `templates/recruitment_agent/emails/`

### Too many emails

- Reduce `--max-followups` value
- Increase `--followup-hours` value
- Check that `pre_interview_reminder_sent_at` is being set correctly

### Emails sent to wrong candidates

- Verify interview status is correct
- Check that `scheduled_datetime` is set correctly
- Ensure past interviews are marked as COMPLETED

## Best Practices

1. **Run frequently**: Schedule to run every 1-6 hours for timely reminders
2. **Monitor logs**: Check command output regularly
3. **Test first**: Always test with `--dry-run` before production
4. **Set limits**: Use `--max-followups` to prevent spam
5. **Review templates**: Ensure email templates are professional and clear

## Support

For issues or questions, check:
- Interview model: `recruitment_agent/models.py`
- Management command: `recruitment_agent/management/commands/send_interview_followups.py`
- Interview agent: `recruitment_agent/agents/interview_scheduling/interview_scheduling_agent.py`

