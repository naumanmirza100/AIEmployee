"""
Email Tracking Views for Marketing Campaigns
Handles email open and click tracking.

How open/click rate is tracked:
- Open: A 1x1 tracking pixel is embedded in sent emails; when the client loads images,
  GET /marketing/track/email/<token>/open/ (or /token?t=<token>) is hit and EmailSendHistory
  status is set to 'opened'. Reply also implies open: when a Reply is saved with
  triggering_email, that send is marked 'opened' (see Reply post_save signal in models.py).
- Click: Links in emails are wrapped with a redirect URL; when the user clicks,
  GET /marketing/track/email/<token>/click/?url=... is hit, status is set to 'clicked',
  then redirect to the original URL.
- Open rate = (count of sends with status in ['opened','clicked']) / total_sent * 100.
- Click rate = (count of sends with status 'clicked') / total_sent * 100.
"""
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.urls import reverse
from urllib.parse import unquote
import logging

from .models import EmailSendHistory

logger = logging.getLogger(__name__)


@csrf_exempt  # Tracking pixels and links don't send CSRF tokens
@require_http_methods(["GET"])
def track_email_open(request, tracking_token):
    """
    Track email open by serving a 1x1 transparent pixel
    UPDATES STATUS IMMEDIATELY when pixel loads
    """
    try:
        send_history = get_object_or_404(EmailSendHistory, tracking_token=tracking_token)
        
        logger.info(
            f"[OPEN TRACKING REQUEST] Token: {tracking_token[:10]}..., "
            f"Email: {send_history.recipient_email}, "
            f"Current Status: {send_history.status}"
        )
        
        # STEP 1: UPDATE STATUS IMMEDIATELY (before returning pixel)
        old_status = send_history.status
        
        # Only update if not already opened/clicked
        if send_history.status not in ['opened', 'clicked']:
            # Mark as delivered first if needed
            if send_history.status == 'sent' and not send_history.delivered_at:
                send_history.delivered_at = timezone.now()
            
            # Update to opened
            send_history.status = 'opened'
            send_history.opened_at = timezone.now()
            send_history.save()  # SAVE IMMEDIATELY
            
            logger.info(
                f"✅ [STATUS UPDATED] Email: {send_history.recipient_email}, "
                f"Status: {old_status} → opened, "
                f"Opened At: {send_history.opened_at}"
            )
        else:
            # Update opened_at timestamp even if already opened (for analytics)
            if not send_history.opened_at:
                send_history.opened_at = timezone.now()
                send_history.save()
                logger.info(f"[OPEN TRACKING] Updated opened_at timestamp for already tracked email")
        
        # STEP 2: Return 1x1 transparent GIF pixel
        # Standard 1x1 transparent GIF (actual GIF file bytes)
        pixel = b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x04\x01\x00\x3b'
        response = HttpResponse(pixel, content_type='image/gif')
        
        # Prevent caching to ensure pixel loads every time
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        
        return response
        
    except Exception as e:
        import traceback
        logger.error(f"❌ Error tracking email open: {str(e)}", exc_info=True)
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Still return pixel even on error to avoid breaking email display
        pixel = b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x04\x01\x00\x3b'
        return HttpResponse(pixel, content_type='image/gif')


def _not_a_link():
    """The answer when a click is not one a real email carried: a plain page, no redirect (CO-125)."""
    from django.utils.html import escape
    message = 'This link is not valid. If it came in an email, open the email again and use the link there.'
    return HttpResponse(f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>Link not valid</title></head>'
                        f'<body style="font-family:sans-serif;padding:40px;color:#334155"><p>{escape(message)}</p>'
                        f'</body></html>', status=404)


def _click(request, tracking_token):
    """Record a click on a real email's link and send it on to the address that email carried."""
    from marketing_agent.services import click_links
    send_history = EmailSendHistory.objects.filter(tracking_token=tracking_token).first() if tracking_token else None
    if not send_history:
        return _not_a_link()
    redirect_url = click_links.destination(request, send_history)
    if not redirect_url:
        logger.warning('[CLICK TRACKING] Link not signed for this email: %s...', str(tracking_token)[:10])
        return _not_a_link()
    now = timezone.now()
    if send_history.status == 'sent' and not send_history.delivered_at:
        send_history.delivered_at = now
    if send_history.status in ('sent', 'delivered') and not send_history.opened_at:
        send_history.opened_at = now
    send_history.status = 'clicked'
    send_history.clicked_at = now
    send_history.save()
    return HttpResponseRedirect(redirect_url)


@csrf_exempt  # Tracking links don't send CSRF tokens
@require_http_methods(["GET"])
def track_email_click(request, tracking_token):
    """GET /marketing/track/email/<token>/click/?url=...&s=...: the older form of a tracked link."""
    try:
        return _click(request, tracking_token)
    except Exception:
        logger.exception('[CLICK TRACKING] Failed')
        return _not_a_link()


@csrf_exempt
@require_http_methods(["GET"])
def test_tracking(request, tracking_token):
    """Test endpoint to verify tracking token exists and show email info"""
    try:
        send_history = get_object_or_404(EmailSendHistory, tracking_token=tracking_token)
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Email Tracking Test</title>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 2rem; max-width: 800px; margin: 0 auto; }}
                .info {{ background: #f3f4f6; padding: 1rem; border-radius: 0.5rem; margin: 1rem 0; }}
                .status {{ font-weight: bold; padding: 0.5rem; border-radius: 0.25rem; display: inline-block; }}
                .sent {{ background: #dbeafe; color: #1e40af; }}
                .opened {{ background: #d1fae5; color: #065f46; }}
                .clicked {{ background: #ede9fe; color: #5b21b6; }}
            </style>
        </head>
        <body>
            <h1>📧 Email Tracking Test</h1>
            <div class="info">
                <p><strong>Email:</strong> {send_history.recipient_email}</p>
                <p><strong>Subject:</strong> {send_history.subject}</p>
                <p><strong>Campaign:</strong> {send_history.campaign.name if send_history.campaign else 'N/A'}</p>
                <p><strong>Status:</strong> 
                    <span class="status {'clicked' if send_history.status == 'clicked' else 'opened' if send_history.status == 'opened' else 'sent'}">
                        {send_history.status.upper()}
                    </span>
                </p>
                <p><strong>Sent At:</strong> {send_history.sent_at or 'Not sent yet'}</p>
                <p><strong>Opened At:</strong> {send_history.opened_at or 'Not opened yet'}</p>
                <p><strong>Clicked At:</strong> {send_history.clicked_at or 'Not clicked yet'}</p>
                <p><strong>Tracking Token:</strong> <code>{tracking_token}</code></p>
            </div>
            <div class="info">
                <h3>Test Links:</h3>
                <p><a href="/marketing/track/email/{tracking_token}/open/">Test Open Tracking</a></p>
                <p><a href="/marketing/track/email/{tracking_token}/click/?url=https://example.com">Test Click Tracking</a></p>
            </div>
        </body>
        </html>
        """
        return HttpResponse(html)
    except Exception as e:
        return HttpResponse(f"Error: {str(e)}", status=404)


# ============================================================================
# SIMPLE TOKEN TRACKING - New simple URL format: /token?t=TOKEN
# ============================================================================

@csrf_exempt
@require_http_methods(["GET"])
def simple_track_open(request, tracking_token=None):
    """
    Simple token tracking for email opens
    URL format: /token?t=TOKEN or /token/TOKEN
    Extracts token from URL and tracks email open
    If url parameter is present, it's a click - redirects instead
    """
    try:
        # Get token from path parameter, query parameter, or path
        if not tracking_token:
            tracking_token = request.GET.get('t', None)
        
        # If not in query, try to get from path (for /token/TOKEN format)
        if not tracking_token:
            # Check if URL path contains token after /token/
            path_parts = request.path.strip('/').split('/')
            if len(path_parts) >= 2 and path_parts[0] == 'token':
                tracking_token = path_parts[1]
        
        # Check if this is a click (has url parameter) - redirect to click handler
        if request.GET.get('url'):
            return simple_track_click(request, tracking_token)
        
        if not tracking_token:
            logger.error("[SIMPLE TRACK] No token provided in request")
            # Return pixel anyway to avoid breaking email
            pixel = b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x04\x01\x00\x3b'
            return HttpResponse(pixel, content_type='image/gif')
        
        # Find email send history by token
        send_history = EmailSendHistory.objects.filter(tracking_token=tracking_token).first()
        
        if not send_history:
            logger.warning(f"[SIMPLE TRACK] Token not found: {tracking_token[:10]}...")
            # Return pixel anyway
            pixel = b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x04\x01\x00\x3b'
            return HttpResponse(pixel, content_type='image/gif')
        
        logger.info(
            f"[SIMPLE OPEN TRACK] Token: {tracking_token[:10]}..., "
            f"Email: {send_history.recipient_email}, "
            f"Current Status: {send_history.status}"
        )
        
        # Update status if not already opened/clicked
        old_status = send_history.status
        
        if send_history.status not in ['opened', 'clicked']:
            # Mark as delivered first if needed
            if send_history.status == 'sent' and not send_history.delivered_at:
                send_history.delivered_at = timezone.now()
            
            # Update to opened
            send_history.status = 'opened'
            send_history.opened_at = timezone.now()
            send_history.save()
            
            logger.info(
                f"✅ [SIMPLE TRACK UPDATED] Email: {send_history.recipient_email}, "
                f"Status: {old_status} → opened, "
                f"Opened At: {send_history.opened_at}"
            )
        else:
            # Update opened_at timestamp even if already opened
            if not send_history.opened_at:
                send_history.opened_at = timezone.now()
                send_history.save()
        
        # If request is from a browser (user clicked "View in browser" link), return HTML page
        # so open is still counted and they see a message. Email client pixel request gets image.
        accept = (request.META.get('HTTP_ACCEPT') or '').lower()
        prefers_html = 'text/html' in accept and accept.strip().split(',')[0].strip().startswith('text/html')
        if prefers_html:
            html = (
                '<!DOCTYPE html><html><head><meta charset="utf-8"><title>Email displayed</title></head><body style="font-family:sans-serif;padding:20px;text-align:center;">'
                '<p style="color:#555;">Email displayed. You can close this window.</p>'
                '</body></html>'
            )
            response = HttpResponse(html, content_type='text/html; charset=utf-8')
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            return response
        
        # Return 1x1 transparent GIF pixel (for email client image load)
        pixel = b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x04\x01\x00\x3b'
        response = HttpResponse(pixel, content_type='image/gif')
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response
        
    except Exception as e:
        import traceback
        logger.error(f"❌ Error in simple track open: {str(e)}", exc_info=True)
        # Return pixel anyway
        pixel = b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x04\x01\x00\x3b'
        return HttpResponse(pixel, content_type='image/gif')


@csrf_exempt
@require_http_methods(["GET"])
def simple_track_click(request, tracking_token=None):
    """GET /token?t=TOKEN&url=ADDRESS&s=SIGNATURE (or /token/TOKEN?url=...): a click on a tracked link."""
    if not tracking_token:
        tracking_token = request.GET.get('t')
    try:
        return _click(request, tracking_token)
    except Exception:
        logger.exception('[SIMPLE CLICK TRACK] Failed')
        return _not_a_link()
