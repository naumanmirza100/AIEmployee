# Recruiter Email Settings - Configuration Guide

## Overview

Recruiters can now configure their own email timing preferences for follow-up and reminder emails. Each recruiter can set:

1. **Follow-up Delay**: Kitne hours baad PENDING interviews ko follow-up email jani chahiye
2. **Reminder Timing**: Kitne hours pehle SCHEDULED interviews ko reminder email jani chahiye
3. **Max Follow-ups**: Maximum kitne follow-up emails bhejne hain
4. **Time Between Follow-ups**: Follow-up emails ke beech minimum kitne hours ka gap

## API Endpoints

### Get Current Settings

**GET** `/recruitment/api/recruiter/email-settings/`

**Response:**
```json
{
    "success": true,
    "settings": {
        "followup_delay_hours": 48,
        "min_hours_between_followups": 24,
        "max_followup_emails": 3,
        "reminder_hours_before": 24,
        "auto_send_followups": true,
        "auto_send_reminders": true
    }
}
```

### Update Settings

**POST** `/recruitment/api/recruiter/email-settings/`

**Request Body:**
```json
{
    "followup_delay_hours": 72,
    "min_hours_between_followups": 24,
    "max_followup_emails": 3,
    "reminder_hours_before": 48,
    "auto_send_followups": true,
    "auto_send_reminders": true
}
```

**Response:**
```json
{
    "success": true,
    "message": "Email settings updated successfully",
    "settings": {
        "followup_delay_hours": 72,
        "min_hours_between_followups": 24,
        "max_followup_emails": 3,
        "reminder_hours_before": 48,
        "auto_send_followups": true,
        "auto_send_reminders": true
    }
}
```

## Settings Explained

### 1. `followup_delay_hours` (Default: 48)
- **Meaning**: PENDING interviews ko kitne hours baad pehli follow-up email bhejni hai
- **Example**: Agar 72 set kiya, to invitation ke 72 hours baad pehli follow-up email jayegi
- **Range**: 1-168 (1 hour to 1 week)

### 2. `reminder_hours_before` (Default: 24)
- **Meaning**: SCHEDULED interviews ko kitne hours pehle reminder email bhejni hai
- **Example**: Agar 48 set kiya, to interview se 48 hours pehle reminder email jayegi
- **Range**: 1-168 (1 hour to 1 week)

### 3. `max_followup_emails` (Default: 3)
- **Meaning**: Maximum kitne follow-up emails bhejne hain
- **Example**: Agar 5 set kiya, to maximum 5 follow-up emails jayengi
- **Range**: 1-10

### 4. `min_hours_between_followups` (Default: 24)
- **Meaning**: Do follow-up emails ke beech minimum kitne hours ka gap hona chahiye
- **Example**: Agar 12 set kiya, to har 12 hours baad follow-up email bhej sakte hain
- **Range**: 1-72

### 5. `auto_send_followups` (Default: true)
- **Meaning**: Automatically follow-up emails bhejni hain ya manually
- **Options**: `true` (automatic) or `false` (manual)

### 6. `auto_send_reminders` (Default: true)
- **Meaning**: Automatically reminder emails bhejni hain ya manually
- **Options**: `true` (automatic) or `false` (manual)

## How It Works

### When Interview is Created

1. System automatically checks recruiter's email settings
2. If settings exist, uses recruiter preferences
3. If settings don't exist, uses default values (48 hours, 24 hours, etc.)
4. These preferences are saved with the interview

### When Follow-up Emails are Sent

1. System checks interview's `followup_delay_hours` (from recruiter settings)
2. Waits for that many hours after invitation
3. Sends follow-up email
4. Waits for `min_hours_between_followups` before next follow-up
5. Stops after `max_followup_emails` are sent

### When Reminder Emails are Sent

1. System checks interview's `reminder_hours_before` (from recruiter settings)
2. Calculates reminder time: `scheduled_datetime - reminder_hours_before`
3. Sends reminder email at that time
4. Only sends once per interview

## Example Usage

### Example 1: Fast Follow-ups
```json
{
    "followup_delay_hours": 24,
    "min_hours_between_followups": 12,
    "max_followup_emails": 5,
    "reminder_hours_before": 12
}
```
- Follow-up after 24 hours
- Next follow-up after 12 hours
- Maximum 5 follow-ups
- Reminder 12 hours before interview

### Example 2: Slow Follow-ups
```json
{
    "followup_delay_hours": 72,
    "min_hours_between_followups": 48,
    "max_followup_emails": 2,
    "reminder_hours_before": 48
}
```
- Follow-up after 72 hours (3 days)
- Next follow-up after 48 hours
- Maximum 2 follow-ups
- Reminder 48 hours before interview

### Example 3: Default Settings
```json
{
    "followup_delay_hours": 48,
    "min_hours_between_followups": 24,
    "max_followup_emails": 3,
    "reminder_hours_before": 24
}
```
- Follow-up after 48 hours (2 days)
- Next follow-up after 24 hours
- Maximum 3 follow-ups
- Reminder 24 hours before interview

## Frontend Integration

### JavaScript Example

```javascript
// Get current settings
async function getEmailSettings() {
    const response = await fetch('/recruitment/api/recruiter/email-settings/', {
        method: 'GET',
        headers: {
            'X-CSRFToken': getCsrfToken()
        }
    });
    const data = await response.json();
    return data.settings;
}

// Update settings
async function updateEmailSettings(settings) {
    const response = await fetch('/recruitment/api/recruiter/email-settings/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify(settings)
    });
    const data = await response.json();
    return data;
}

// Example usage
const settings = {
    followup_delay_hours: 72,
    reminder_hours_before: 48,
    max_followup_emails: 3,
    min_hours_between_followups: 24
};
await updateEmailSettings(settings);
```

## Notes

- Settings are per-recruiter (each recruiter has their own preferences)
- When a recruiter creates an interview, their settings are automatically applied
- Settings can be changed anytime and will affect new interviews
- Existing interviews keep their original settings
- Default values are used if recruiter hasn't set preferences

## Testing

1. Set your preferences via API
2. Create a new interview
3. Check that interview has your preferred settings
4. Wait for the configured time
5. Verify emails are sent according to your preferences

