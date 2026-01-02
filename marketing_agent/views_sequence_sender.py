"""
View to manually trigger sequence email sending
"""
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.core.management import call_command
from django.views.decorators.http import require_http_methods
from io import StringIO
import sys

from .models import Campaign


@login_required
@require_http_methods(["POST"])
def trigger_sequence_emails(request, campaign_id):
    """Manually trigger the send_sequence_emails command for a specific campaign"""
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)
    
    if campaign.status != 'active':
        return JsonResponse({
            'success': False,
            'error': 'Campaign must be active to send sequence emails'
        }, status=400)
    
    try:
        # Capture command output
        out = StringIO()
        err = StringIO()
        
        # Call the management command
        call_command('send_sequence_emails', stdout=out, stderr=err)
        
        output = out.getvalue()
        errors = err.getvalue()
        
        return JsonResponse({
            'success': True,
            'message': 'Sequence emails processed successfully',
            'output': output,
            'errors': errors if errors else None
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

