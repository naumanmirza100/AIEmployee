"""
Views for Email Sequence Management
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db import transaction
import json

from .models import Campaign, EmailSequence, EmailSequenceStep, EmailTemplate, EmailAccount, EmailSendHistory
from django.utils import timezone


@login_required
def sequence_management(request, campaign_id):
    """Main page for managing email sequences for a campaign"""
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)
    
    # Get all sequences with their steps
    sequences = EmailSequence.objects.filter(campaign=campaign).prefetch_related('steps__template', 'email_account')
    
    # Get all templates for the campaign
    templates = EmailTemplate.objects.filter(campaign=campaign, is_active=True).order_by('name')
    
    # Get all email accounts
    email_accounts = EmailAccount.objects.filter(owner=request.user, is_active=True).order_by('-is_default', 'email')
    
    # Get sequence statistics
    sequences_data = []
    for sequence in sequences:
        steps = sequence.steps.all().order_by('step_order')
        
        # Get stats for this sequence
        total_sent = EmailSendHistory.objects.filter(
            campaign=campaign,
            email_template__sequence_steps__sequence=sequence
        ).count()
        
        sequences_data.append({
            'sequence': sequence,
            'steps': steps,
            'total_sent': total_sent,
        })
    
    context = {
        'campaign': campaign,
        'sequences': sequences_data,
        'templates': templates,
        'email_accounts': email_accounts,
    }
    
    return render(request, 'marketing/sequence_management.html', context)


@login_required
@require_http_methods(["POST"])
def create_sequence(request, campaign_id):
    """Create a new email sequence"""
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)
    
    try:
        data = json.loads(request.body)
        
        sequence = EmailSequence.objects.create(
            name=data.get('name'),
            campaign=campaign,
            email_account_id=data.get('email_account_id'),
            is_active=data.get('is_active', True)
        )
        
        # Add steps with sequential step_order (1, 2, 3...)
        steps_data = data.get('steps', [])
        for index, step_data in enumerate(steps_data, start=1):
            template = get_object_or_404(EmailTemplate, id=step_data.get('template_id'), campaign=campaign)
            EmailSequenceStep.objects.create(
                sequence=sequence,
                template=template,
                step_order=index,  # Always use sequential order (1, 2, 3...)
                delay_days=step_data.get('delay_days', 0),
                delay_hours=step_data.get('delay_hours', 0),
                delay_minutes=step_data.get('delay_minutes', 0),
            )
        
        return JsonResponse({
            'success': True,
            'sequence_id': sequence.id,
            'message': 'Sequence created successfully'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@require_http_methods(["PUT"])
def update_sequence(request, campaign_id, sequence_id):
    """Update an existing sequence"""
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)
    sequence = get_object_or_404(EmailSequence, id=sequence_id, campaign=campaign)
    
    try:
        data = json.loads(request.body)
        
        sequence.name = data.get('name', sequence.name)
        if 'email_account_id' in data:
            sequence.email_account_id = data.get('email_account_id')
        sequence.is_active = data.get('is_active', sequence.is_active)
        sequence.save()
        
        # Update steps if provided
        if 'steps' in data:
            # Delete existing steps
            sequence.steps.all().delete()
            
            # Create new steps with sequential step_order (1, 2, 3...)
            for index, step_data in enumerate(data['steps'], start=1):
                template = get_object_or_404(EmailTemplate, id=step_data.get('template_id'), campaign=campaign)
                EmailSequenceStep.objects.create(
                    sequence=sequence,
                    template=template,
                    step_order=index,  # Always use sequential order (1, 2, 3...)
                    delay_days=step_data.get('delay_days', 0),
                    delay_hours=step_data.get('delay_hours', 0),
                    delay_minutes=step_data.get('delay_minutes', 0),
                )
        
        return JsonResponse({
            'success': True,
            'message': 'Sequence updated successfully'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@require_http_methods(["DELETE"])
def delete_sequence(request, campaign_id, sequence_id):
    """Delete a sequence"""
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)
    sequence = get_object_or_404(EmailSequence, id=sequence_id, campaign=campaign)
    
    try:
        sequence_name = sequence.name
        sequence.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Sequence "{sequence_name}" deleted successfully'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@require_http_methods(["GET"])
def get_sequence_details(request, campaign_id, sequence_id):
    """Get detailed information about a sequence"""
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)
    sequence = get_object_or_404(EmailSequence, id=sequence_id, campaign=campaign)
    
    steps = sequence.steps.all().order_by('step_order')
    
    # Get statistics
    total_leads = campaign.leads.count()
    sequence_emails_sent = EmailSendHistory.objects.filter(
        campaign=campaign,
        email_template__sequence_steps__sequence=sequence
    )
    
    total_sent = sequence_emails_sent.count()
    total_delivered = sequence_emails_sent.filter(status__in=['delivered', 'opened', 'clicked']).count()
    total_opened = sequence_emails_sent.filter(status__in=['opened', 'clicked']).count()
    total_clicked = sequence_emails_sent.filter(status='clicked').count()
    
    # Get next send times for each lead
    next_sends = []
    for lead in campaign.leads.all()[:10]:  # Limit to first 10 for performance
        last_email = EmailSendHistory.objects.filter(
            campaign=campaign,
            lead=lead,
            email_template__sequence_steps__sequence=sequence
        ).order_by('-sent_at').first()
        
        if last_email:
            last_step = steps.filter(template=last_email.email_template).first()
            if last_step:
                next_step = steps.filter(step_order__gt=last_step.step_order).first()
                if next_step:
                    from datetime import timedelta
                    delay = timedelta(
                        days=next_step.delay_days,
                        hours=next_step.delay_hours,
                        minutes=next_step.delay_minutes
                    )
                    next_send_time = last_email.sent_at + delay
                    if next_send_time > timezone.now():
                        next_sends.append({
                            'lead_email': lead.email,
                            'next_step': next_step.step_order,
                            'next_send_time': next_send_time,
                        })
    
    return JsonResponse({
        'success': True,
        'sequence': {
            'id': sequence.id,
            'name': sequence.name,
            'is_active': sequence.is_active,
            'email_account': sequence.email_account.email if sequence.email_account else None,
            'email_account_id': sequence.email_account.id if sequence.email_account else None,
            'steps': [{
                'id': step.id,
                'template_id': step.template.id,
                'template_name': step.template.name,
                'step_order': step.step_order,
                'delay_days': step.delay_days,
                'delay_hours': step.delay_hours,
                'delay_minutes': step.delay_minutes,
            } for step in steps],
            'stats': {
                'total_leads': total_leads,
                'total_sent': total_sent,
                'total_delivered': total_delivered,
                'total_opened': total_opened,
                'total_clicked': total_clicked,
            },
            'next_sends': next_sends,
        }
    })

