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
        
        # Update status to 'opened' if not already opened or clicked
        if send_history.status not in ['opened', 'clicked']:
            # First mark as delivered if not already sent
            if send_history.status == 'sent' and not send_history.delivered_at:
                send_history.status = 'delivered'
                send_history.delivered_at = timezone.now()
            
            # Update to opened
            send_history.status = 'opened'
            send_history.opened_at = timezone.now()
            send_history.save()
            
            logger.info(f"Email opened: {send_history.recipient_email} (Campaign: {send_history.campaign.name})")
        
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
        
        # Get the original URL from query parameters
        original_url = request.GET.get('url', '')
        if not original_url:
            logger.warning(f"No URL parameter in click tracking for token {tracking_token}")
            # Redirect to campaign or homepage
            return HttpResponseRedirect('/')
        
        # Decode the URL
        original_url = unquote(original_url)
        
        # Update status to 'clicked'
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
            
            logger.info(f"Email link clicked: {send_history.recipient_email} -> {original_url} (Campaign: {send_history.campaign.name})")
        
        # Redirect to original URL
        return HttpResponseRedirect(original_url)
        
    except Exception as e:
        logger.error(f"Error tracking email click: {str(e)}")
        # Try to redirect to original URL anyway
        original_url = request.GET.get('url', '/')
        try:
            original_url = unquote(original_url)
            return HttpResponseRedirect(original_url)
        except:
            return HttpResponseRedirect('/')








