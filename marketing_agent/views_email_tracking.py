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


@csrf_exempt  # Tracking links don't send CSRF tokens
@require_http_methods(["GET"])
def track_email_click(request, tracking_token):
    """
    Track email link click and redirect to original URL
    UPDATES STATUS FIRST, then redirects (this is critical!)
    """
    try:
        # Get email send history
        send_history = get_object_or_404(EmailSendHistory, tracking_token=tracking_token)
        
        logger.info(
            f"[CLICK TRACKING REQUEST] Token: {tracking_token[:10]}..., "
            f"Email: {send_history.recipient_email}, "
            f"Current Status: {send_history.status}"
        )
        
        # STEP 1: UPDATE STATUS FIRST (before any redirect logic)
        old_status = send_history.status
        
        # Mark as delivered/opened first if needed
        if send_history.status == 'sent' and not send_history.delivered_at:
            send_history.delivered_at = timezone.now()
        
        if send_history.status in ['sent', 'delivered'] and not send_history.opened_at:
            send_history.opened_at = timezone.now()
        
        # Update to clicked
        send_history.status = 'clicked'
        send_history.clicked_at = timezone.now()
        send_history.save()  # SAVE IMMEDIATELY
        
        logger.info(
            f"✅ [STATUS UPDATED] Email: {send_history.recipient_email}, "
            f"Status: {old_status} → clicked, "
            f"Clicked At: {send_history.clicked_at}"
        )
        
        # STEP 2: Get redirect URL from query parameter
        original_url = request.GET.get('url', '')
        logger.info(f"[CLICK TRACKING] URL parameter: {original_url}")
        
        # Handle missing or invalid URLs
        if not original_url or original_url == '#' or original_url == '%23':
            logger.warning(f"No valid URL in click tracking, using default")
            # Default to campaign page
            if send_history.campaign:
                original_url = f'/marketing/campaigns/{send_history.campaign.id}/'
            else:
                original_url = '/marketing/'
        else:
            # Decode URL
            try:
                original_url = unquote(original_url)
            except Exception as e:
                logger.error(f"Error decoding URL: {e}")
                original_url = '/marketing/'
            
            # Handle anchor links
            if original_url == '#' or original_url.startswith('#'):
                if send_history.campaign:
                    original_url = f'/marketing/campaigns/{send_history.campaign.id}/'
                else:
                    original_url = '/marketing/'
        
        # STEP 3: Build absolute redirect URL
        from django.conf import settings
        
        if original_url.startswith('http://') or original_url.startswith('https://'):
            # Already absolute - use as-is
            redirect_url = original_url
        elif original_url.startswith('/'):
            # Relative URL - make absolute
            base_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
            base_url = base_url.rstrip('/')
            redirect_url = f"{base_url}{original_url}"
        else:
            # Not a proper URL - treat as relative
            base_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
            base_url = base_url.rstrip('/')
            redirect_url = f"{base_url}/{original_url}"
        
        logger.info(f"[CLICK TRACKING] Redirecting to: {redirect_url}")
        
        # STEP 4: Return redirect response (multiple methods for compatibility)
        # Use HttpResponseRedirect first (standard Django redirect)
        response = HttpResponseRedirect(redirect_url)
        # Also set Location header explicitly
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
        
        # Return 1x1 transparent GIF pixel
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
    """
    Simple token tracking for email clicks
    URL format: /token?t=TOKEN&url=ORIGINAL_URL or /token/TOKEN?url=ORIGINAL_URL
    Extracts token from URL, tracks click, and redirects to original URL
    """
    try:
        # Get token from path parameter, query parameter, or path
        if not tracking_token:
            tracking_token = request.GET.get('t', None)
        
        # If not in query, try to get from path (for /token/TOKEN format)
        if not tracking_token:
            path_parts = request.path.strip('/').split('/')
            if len(path_parts) >= 2 and path_parts[0] == 'token':
                tracking_token = path_parts[1]
        
        if not tracking_token:
            logger.error("[SIMPLE CLICK TRACK] No token provided")
            # Redirect to default
            from django.conf import settings
            base_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
            return HttpResponseRedirect(f"{base_url.rstrip('/')}/marketing/")
        
        # Find email send history by token
        send_history = EmailSendHistory.objects.filter(tracking_token=tracking_token).first()
        
        if not send_history:
            logger.warning(f"[SIMPLE CLICK TRACK] Token not found: {tracking_token[:10]}...")
            # Try to redirect to original URL anyway
            original_url = request.GET.get('url', '/marketing/')
            if original_url and original_url != '#':
                try:
                    original_url = unquote(original_url)
                    if original_url.startswith('http://') or original_url.startswith('https://'):
                        return HttpResponseRedirect(original_url)
                except:
                    pass
            from django.conf import settings
            base_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
            return HttpResponseRedirect(f"{base_url.rstrip('/')}/marketing/")
        
        logger.info(
            f"[SIMPLE CLICK TRACK] Token: {tracking_token[:10]}..., "
            f"Email: {send_history.recipient_email}, "
            f"Current Status: {send_history.status}"
        )
        
        # Update status first
        old_status = send_history.status
        
        # Mark as delivered/opened first if needed
        if send_history.status == 'sent' and not send_history.delivered_at:
            send_history.delivered_at = timezone.now()
        
        if send_history.status in ['sent', 'delivered'] and not send_history.opened_at:
            send_history.opened_at = timezone.now()
        
        # Update to clicked
        send_history.status = 'clicked'
        send_history.clicked_at = timezone.now()
        send_history.save()
        
        logger.info(
            f"✅ [SIMPLE CLICK UPDATED] Email: {send_history.recipient_email}, "
            f"Status: {old_status} → clicked, "
            f"Clicked At: {send_history.clicked_at}"
        )
        
        # Get redirect URL
        original_url = request.GET.get('url', '')
        
        # Handle missing or invalid URLs
        if not original_url or original_url == '#' or original_url == '%23':
            if send_history.campaign:
                original_url = f'/marketing/campaigns/{send_history.campaign.id}/'
            else:
                original_url = '/marketing/'
        else:
            try:
                original_url = unquote(original_url)
            except:
                original_url = '/marketing/'
            
            if original_url == '#' or original_url.startswith('#'):
                if send_history.campaign:
                    original_url = f'/marketing/campaigns/{send_history.campaign.id}/'
                else:
                    original_url = '/marketing/'
        
        # Build absolute redirect URL
        from django.conf import settings
        
        if original_url.startswith('http://') or original_url.startswith('https://'):
            redirect_url = original_url
        elif original_url.startswith('/'):
            base_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
            base_url = base_url.rstrip('/')
            redirect_url = f"{base_url}{original_url}"
        else:
            base_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
            base_url = base_url.rstrip('/')
            redirect_url = f"{base_url}/{original_url}"
        
        logger.info(f"[SIMPLE CLICK TRACK] Redirecting to: {redirect_url}")
        
        return HttpResponseRedirect(redirect_url)
        
    except Exception as e:
        import traceback
        logger.error(f"❌ Error in simple track click: {str(e)}", exc_info=True)
        
        # Try to redirect anyway
        original_url = request.GET.get('url', '/marketing/')
        if original_url and original_url != '#':
            try:
                original_url = unquote(original_url)
                if original_url.startswith('http://') or original_url.startswith('https://'):
                    return HttpResponseRedirect(original_url)
            except:
                pass
        
        from django.conf import settings
        base_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
        return HttpResponseRedirect(f"{base_url.rstrip('/')}/marketing/")









