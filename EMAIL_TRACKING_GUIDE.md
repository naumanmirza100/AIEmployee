# Email Tracking Guide

## Overview
This guide explains how email tracking works in the Marketing Agent system for:
- ✅ **Email Opens** - Automatically tracked
- ✅ **Email Clicks** - Automatically tracked  
- ⚠️ **Email Replies** - Currently manual (can be automated)
- ⚠️ **Email Bounces** - Currently manual (can be automated)

---

## 1. 📧 Email Opens Tracking

### How It Works:
1. **Tracking Pixel Injection**: When an email is sent, a 1x1 transparent GIF pixel is automatically added to the HTML email content
2. **Unique Tracking Token**: Each email gets a unique `tracking_token` when sent
3. **Automatic Detection**: When the email client loads images, it requests the tracking pixel from your server
4. **Status Update**: The system automatically updates the email status to `'opened'` and records `opened_at` timestamp

### Implementation Details:

**Location**: `marketing_agent/services/email_service.py` - `_add_email_tracking()` method
```python
# Tracking pixel is added before </body> tag
tracking_pixel_url = f"{base_url}/marketing/track/email/{tracking_token}/open/"
tracking_pixel = f'<img src="{tracking_pixel_url}" width="1" height="1" style="display:none;" alt="" />'
```

**Tracking Endpoint**: `marketing_agent/views_email_tracking.py` - `track_email_open()`
- URL: `/marketing/track/email/<tracking_token>/open/`
- Returns: 1x1 transparent GIF pixel
- Updates: `EmailSendHistory.status = 'opened'` and `opened_at = timezone.now()`

### Status Flow:
- `pending` → `sent` → `opened` (when pixel loads)
- If already `clicked`, status stays `clicked` (clicks are higher priority)

---

## 2. 🔗 Email Clicks Tracking

### How It Works:
1. **Link Wrapping**: All `<a href="...">` links in the email HTML are automatically wrapped with tracking URLs
2. **Redirect System**: When a link is clicked, it first goes to your tracking endpoint
3. **Status Update**: The system updates status to `'clicked'` and records `clicked_at` timestamp
4. **Redirect**: User is then redirected to the original destination URL

### Implementation Details:

**Location**: `marketing_agent/services/email_service.py` - `_add_email_tracking()` method
```python
# Links are wrapped like this:
# Original: <a href="https://example.com">Click here</a>
# Becomes: <a href="/marketing/track/email/{token}/click/?url=https%3A%2F%2Fexample.com">Click here</a>
```

**Tracking Endpoint**: `marketing_agent/views_email_tracking.py` - `track_email_click()`
- URL: `/marketing/track/email/<tracking_token>/click/?url=<encoded_original_url>`
- Updates: `EmailSendHistory.status = 'clicked'` and `clicked_at = timezone.now()`
- Redirects: User to the original URL

### Status Flow:
- `pending` → `sent` → `clicked` (when link is clicked)
- If status is `opened`, it upgrades to `clicked`
- Click tracking also sets `opened_at` if not already set (assumes email was opened to click)

---

## 3. 💬 Email Replies Tracking

### Current Implementation (Manual):
Replies are currently tracked through the `CampaignContact` model, not `EmailSendHistory`.

**How It Works:**
1. **Manual Marking**: Admins can manually mark a contact as "replied" via the UI
2. **API Endpoint**: `POST /marketing/campaigns/<campaign_id>/contacts/<lead_id>/mark-replied/`
3. **Automation Stop**: When marked as replied, email sequences stop for that contact

**Location**: `marketing_agent/views.py` - `mark_contact_replied()`
```python
contact.mark_replied(reply_subject=reply_subject)
# This sets:
# - contact.replied = True
# - contact.replied_at = timezone.now()
# - contact.reply_subject = reply_subject
# - Stops all future sequence emails for this contact
```

**Model**: `marketing_agent/models.py` - `CampaignContact.mark_replied()`

### ⚠️ To Automate Reply Tracking:

You would need to implement one of these methods:

#### Option A: Email Webhook (Recommended)
- Set up an email webhook endpoint (e.g., using SendGrid, Mailgun, or your SMTP provider)
- When someone replies, the email service sends a webhook to your server
- Your server parses the reply and automatically marks the contact as replied

#### Option B: IMAP/POP3 Monitoring
- Periodically check the "Sent From" email account's inbox
- Look for replies (emails with "Re:" in subject or in-reply-to headers)
- Match reply sender to `CampaignContact.lead.email`
- Automatically mark as replied

#### Option C: Email Service Integration
- Use an email service API (SendGrid, Mailgun, AWS SES) that provides reply tracking
- Configure webhooks to receive reply notifications

**Example Webhook Implementation** (to be added):
```python
# marketing_agent/views.py
@csrf_exempt
def email_reply_webhook(request):
    """Handle email reply webhook from email service"""
    # Parse webhook data
    # Find matching CampaignContact by sender email
    # Mark as replied automatically
    pass
```

---

## 4. 📬 Email Bounces Tracking

### Current Implementation (Manual):
Bounces are currently **NOT automatically detected**. The system has the infrastructure but needs implementation.

**Model Support**: `EmailSendHistory` has:
- `status = 'bounced'` option
- `bounce_reason` field (Text field for error details)

### ⚠️ To Automate Bounce Tracking:

You need to catch SMTP bounce errors when sending emails:

#### Option A: SMTP Error Handling (Recommended)
Modify `marketing_agent/services/email_service.py` - `send_email()` method:

```python
try:
    email.send()
    send_history.status = 'sent'
except smtplib.SMTPRecipientsRefused as e:
    # Permanent failure (550, 554 errors)
    send_history.status = 'bounced'
    send_history.bounce_reason = str(e)
except smtplib.SMTPDataError as e:
    # Temporary failure
    send_history.status = 'failed'
    send_history.error_message = str(e)
except Exception as e:
    send_history.status = 'failed'
    send_history.error_message = str(e)
```

#### Option B: Email Service Webhooks
- Use email service provider (SendGrid, Mailgun) that sends bounce webhooks
- Handle bounce notifications via webhook endpoint

#### Option C: Bounce Email Monitoring
- Monitor a dedicated bounce email address
- Parse bounce messages and update `EmailSendHistory` records

**Common SMTP Bounce Codes:**
- `550`: Mailbox unavailable (permanent)
- `554`: Transaction failed (permanent)
- `421`: Service not available (temporary)
- `450`: Mailbox temporarily unavailable

---

## 📊 Viewing Tracking Data

### In the UI:
1. **Campaign Detail Page**: Shows summary stats (sent, opened, clicked, bounced, replied)
2. **Email Sending Status Page**: Full detailed history with all tracking data
   - URL: `/marketing/campaigns/<campaign_id>/email-status/`
   - Shows: All emails with their current status, timestamps, and details

### In the Database:
```python
from marketing_agent.models import EmailSendHistory, CampaignContact

# Get all opened emails
opened_emails = EmailSendHistory.objects.filter(status='opened')

# Get all clicked emails  
clicked_emails = EmailSendHistory.objects.filter(status='clicked')

# Get all bounced emails
bounced_emails = EmailSendHistory.objects.filter(status='bounced')

# Get all replied contacts
replied_contacts = CampaignContact.objects.filter(replied=True)
```

---

## 🔧 Current Tracking Status Summary

| Tracking Type | Status | Automation Level |
|--------------|--------|------------------|
| **Opens** | ✅ Working | Fully Automatic |
| **Clicks** | ✅ Working | Fully Automatic |
| **Replies** | ⚠️ Partial | Manual (needs webhook/IMAP) |
| **Bounces** | ⚠️ Partial | Manual (needs SMTP error handling) |

---

## 🚀 Next Steps to Complete Tracking

1. **Implement Bounce Detection**: Add SMTP error handling in `email_service.py`
2. **Implement Reply Tracking**: Set up email webhooks or IMAP monitoring
3. **Add Real-time Updates**: Use WebSockets or polling for live status updates
4. **Add Email Analytics**: Track open rates, click rates, bounce rates over time

---

## 📝 Notes

- **Tracking Pixel Limitations**: Some email clients block images by default, so opens may be underreported
- **Privacy**: Tracking pixels are standard in email marketing but users can disable images
- **Link Tracking**: All links are tracked, including unsubscribe links (if present)
- **Status Hierarchy**: `clicked` > `opened` > `sent` > `pending`


