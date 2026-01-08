"""
Email Tracking Views for Marketing Campaigns
Handles email open and click tracking
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
    Updates EmailSendHistory status to 'opened' and sets opened_at timestamp
    """
    try:
        send_history = get_object_or_404(EmailSendHistory, tracking_token=tracking_token)
        
        # Debug: Log tracking attempt
        logger.info(
            f"[EMAIL OPEN TRACKING] Token: {tracking_token[:20]}..., "
            f"Email: {send_history.recipient_email}, "
            f"Current Status: {send_history.status}, "
            f"Campaign: {send_history.campaign.name if send_history.campaign else 'N/A'}"
        )
        
        # Update status to 'opened' (always update opened_at even if already clicked)
        if send_history.status not in ['opened', 'clicked']:
            old_status = send_history.status
            # First mark as delivered if not already sent
            if send_history.status == 'sent' and not send_history.delivered_at:
                send_history.status = 'delivered'
                send_history.delivered_at = timezone.now()
            
            # Update to opened
            send_history.status = 'opened'
            send_history.opened_at = timezone.now()
            send_history.save()
            
            logger.info(
                f"✅ [EMAIL OPENED] Email: {send_history.recipient_email}, "
                f"Campaign: {send_history.campaign.name if send_history.campaign else 'N/A'}, "
                f"Status changed: {old_status} → opened, "
                f"Token: {tracking_token[:10]}..., "
                f"Opened At: {send_history.opened_at}"
            )
        else:
            # Still update opened_at timestamp even if already tracked (for analytics)
            if not send_history.opened_at:
                send_history.opened_at = timezone.now()
                send_history.save()
            logger.debug(
                f"[EMAIL ALREADY TRACKED] Email: {send_history.recipient_email}, "
                f"Current Status: {send_history.status}, "
                f"Token: {tracking_token[:10]}..."
            )
        
        # Return 1x1 transparent GIF pixel
        # This is a standard 1x1 transparent GIF
        pixel = b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x04\x01\x00\x3b'
        response = HttpResponse(pixel, content_type='image/gif')
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response
        
    except Exception as e:
        logger.error(f"Error tracking email open: {str(e)}")
        # Still return pixel even on error to avoid breaking email display
        pixel = b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x04\x01\x00\x3b'
        return HttpResponse(pixel, content_type='image/gif')


@csrf_exempt  # Tracking links don't send CSRF tokens
@require_http_methods(["GET"])
def track_email_click(request, tracking_token):
    """
    Track email link click and redirect to original URL
    Updates EmailSendHistory status to 'clicked' and sets clicked_at timestamp
    """
    try:
        send_history = get_object_or_404(EmailSendHistory, tracking_token=tracking_token)
        
        # ALWAYS update click status first (even if URL is invalid)
        old_status = send_history.status
        status_updated = False
        
        if send_history.status != 'clicked':
            # First mark as delivered/opened if not already
            if send_history.status == 'sent' and not send_history.delivered_at:
                send_history.status = 'delivered'
                send_history.delivered_at = timezone.now()
            
            if send_history.status in ['sent', 'delivered'] and not send_history.opened_at:
                send_history.opened_at = timezone.now()
            
            send_history.status = 'clicked'
            send_history.clicked_at = timezone.now()
            send_history.save()
            status_updated = True
            
            logger.info(
                f"✅ [EMAIL CLICKED] Email: {send_history.recipient_email}, "
                f"Campaign: {send_history.campaign.name if send_history.campaign else 'N/A'}, "
                f"Status changed: {old_status} → clicked, "
                f"Token: {tracking_token[:10]}..., "
                f"Clicked At: {send_history.clicked_at}"
            )
        else:
            # Update clicked_at timestamp even if already clicked (for analytics)
            if not send_history.clicked_at:
                send_history.clicked_at = timezone.now()
                send_history.save()
            logger.debug(
                f"[EMAIL ALREADY CLICKED] Email: {send_history.recipient_email}, "
                f"Current Status: {send_history.status}, "
                f"Token: {tracking_token[:10]}..."
            )
        
        # Get the original URL from query parameters
        original_url = request.GET.get('url', '')
        logger.info(f"[CLICK TRACKING] Token: {tracking_token[:10]}..., URL param: {original_url}")
        
        if not original_url or original_url == '#' or original_url == '%23':
            logger.warning(f"No valid URL parameter in click tracking for token {tracking_token}, URL was: {original_url}")
            # If no URL or just anchor, redirect to campaign detail page or homepage
            if send_history.campaign:
                original_url = f'/marketing/campaigns/{send_history.campaign.id}/'
            else:
                original_url = '/marketing/'
        else:
            # Decode the URL
            try:
                original_url = unquote(original_url)
            except Exception as e:
                logger.error(f"Error decoding URL: {e}, using as-is: {original_url}")
            
            # Handle anchor links - if decoded URL is just '#', redirect to campaign
            if original_url == '#' or not original_url or original_url.startswith('#'):
                if send_history.campaign:
                    original_url = f'/marketing/campaigns/{send_history.campaign.id}/'
                else:
                    original_url = '/marketing/'
        
        # Build redirect URL
        # If URL is relative, make it absolute using SITE_URL
        if original_url.startswith('/'):
            from django.conf import settings
            base_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
            # Remove trailing slash from base_url if present
            base_url = base_url.rstrip('/')
            redirect_url = f"{base_url}{original_url}"
        elif original_url.startswith('http://') or original_url.startswith('https://'):
            # Already absolute URL
            redirect_url = original_url
        else:
            # If it's not a full URL and not relative, treat as relative
            from django.conf import settings
            base_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
            base_url = base_url.rstrip('/')
            redirect_url = f"{base_url}/{original_url}"
        
        logger.info(f"[CLICK TRACKING] Redirecting to: {redirect_url}")
        
        # Use HTML meta refresh as backup in case redirect fails
        # This ensures the redirect works even if HttpResponseRedirect has issues
        html_response = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta http-equiv="refresh" content="0;url={redirect_url}">
            <script>window.location.href = "{redirect_url}";</script>
            <title>Redirecting...</title>
        </head>
        <body>
            <p>Redirecting... <a href="{redirect_url}">Click here if you are not redirected</a></p>
        </body>
        </html>
        """
        response = HttpResponse(html_response)
        response['Location'] = redirect_url
        response.status_code = 302
        return response
        
    except Exception as e:
        import traceback
        logger.error(f"❌ Error tracking email click: {str(e)}", exc_info=True)
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Try to update status even on error
        try:
            send_history = EmailSendHistory.objects.filter(tracking_token=tracking_token).first()
            if send_history and send_history.status != 'clicked':
                send_history.status = 'clicked'
                send_history.clicked_at = timezone.now()
                send_history.save()
                logger.info(f"✅ [ERROR RECOVERY] Updated status to clicked for token {tracking_token[:10]}...")
        except Exception as save_error:
            logger.error(f"Failed to update status on error: {save_error}")
        
        # Try to redirect to original URL anyway
        original_url = request.GET.get('url', '')
        if original_url:
            try:
                original_url = unquote(original_url)
                if original_url.startswith('http://') or original_url.startswith('https://'):
                    return HttpResponseRedirect(original_url)
                elif original_url.startswith('/'):
                    from django.conf import settings
                    base_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
                    return HttpResponseRedirect(f"{base_url.rstrip('/')}{original_url}")
            except Exception as redirect_error:
                logger.error(f"Error in redirect fallback: {redirect_error}")
        
        # Final fallback - redirect to marketing dashboard with message
        from django.conf import settings
        base_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
        fallback_url = f"{base_url.rstrip('/')}/marketing/"
        html_response = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta http-equiv="refresh" content="0;url={fallback_url}">
            <script>window.location.href = "{fallback_url}";</script>
            <title>Redirecting...</title>
        </head>
        <body>
            <p>Redirecting... <a href="{fallback_url}">Click here if you are not redirected</a></p>
        </body>
        </html>
        """
        response = HttpResponse(html_response)
        response['Location'] = fallback_url
        response.status_code = 302
        return response


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









