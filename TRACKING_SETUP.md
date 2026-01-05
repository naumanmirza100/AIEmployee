# Email Tracking Setup Guide

## Problem
Email tracking (opens and clicks) is not working because tracking URLs are using `localhost:8000` which is not accessible from external email clients.

## Solution

### Option 1: Set SITE_URL in settings.py (Recommended)

Add this to your `project_manager_ai/settings.py`:

```python
# Email Tracking Configuration
SITE_URL = 'http://127.0.0.1:8000'  # For local development
# OR for production:
# SITE_URL = 'https://yourdomain.com'
```

### Option 2: Set SITE_URL in .env file

Add to your `.env` file:
```
SITE_URL=http://127.0.0.1:8000
```

Then in `settings.py`:
```python
SITE_URL = os.getenv('SITE_URL', 'http://127.0.0.1:8000')
```

### Option 3: For Production/External Access

If you're deploying to a server and want tracking to work from external email clients:

1. **Set SITE_URL to your public domain:**
   ```python
   SITE_URL = 'https://yourdomain.com'
   ```

2. **Make sure ALLOWED_HOSTS includes your domain:**
   ```python
   ALLOWED_HOSTS = ['yourdomain.com', 'www.yourdomain.com']
   ```

3. **Ensure your server is accessible from the internet** (not just localhost)

## Testing Tracking

### Test Open Tracking:
1. Send a test email
2. Open the email in your email client
3. Check the server logs for: `✅ Email opened: ...`
4. Check the Email Sending Status page - the email should show as "Opened"

### Test Click Tracking:
1. Send a test email with a link
2. Click the link in the email
3. Check the server logs for: `✅ Email link clicked: ...`
4. Check the Email Sending Status page - the email should show as "Clicked"

## Troubleshooting

### Tracking not working?

1. **Check if tracking token exists:**
   ```python
   from marketing_agent.models import EmailSendHistory
   email = EmailSendHistory.objects.first()
   print(email.tracking_token)  # Should not be None
   ```

2. **Check tracking URLs in email:**
   - View the email source/HTML
   - Look for: `<img src="http://...track/email/.../open/"`
   - The URL should use your SITE_URL, not localhost

3. **Check server logs:**
   - Look for tracking requests: `GET /marketing/track/email/...`
   - Check for errors in the logs

4. **Test tracking endpoint directly:**
   - Visit: `http://your-site/marketing/track/email/[token]/open/`
   - Should return a 1x1 pixel (you won't see anything, but check network tab)

### Common Issues:

- **"localhost" in tracking URLs**: SITE_URL not set correctly
- **404 errors**: URL routing issue, check urls.py
- **No tracking token**: EmailSendHistory.tracking_token is None
- **Tracking works locally but not from Gmail**: SITE_URL needs to be your public domain

## Current Status

After fixing, tracking should work automatically:
- ✅ Opens tracked when email client loads images
- ✅ Clicks tracked when links are clicked
- ✅ Status updated in EmailSendHistory
- ✅ Counts updated in campaign stats


