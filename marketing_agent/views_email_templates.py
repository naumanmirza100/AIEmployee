from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from .models import Campaign, EmailTemplate, EmailSequence, EmailSequenceStep, Lead, EmailSendHistory
import json


@login_required
@require_http_methods(["GET", "POST"])
def email_templates_list(request, campaign_id):
    """List all email templates for a campaign"""
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)
    
    if request.method == 'POST':
        # Handle template creation
        try:
            data = json.loads(request.body)
            template = EmailTemplate.objects.create(
                campaign=campaign,
                name=data.get('name'),
                email_type=data.get('email_type', 'initial'),
                subject=data.get('subject'),
                html_content=data.get('html_content', ''),
                text_content=data.get('text_content', ''),
                followup_sequence_number=data.get('followup_sequence_number', 0),
            )
            return JsonResponse({
                'success': True,
                'template_id': template.id,
                'message': 'Email template created successfully'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
    
    templates = EmailTemplate.objects.filter(campaign=campaign).order_by('followup_sequence_number', 'created_at')
    return JsonResponse({
        'success': True,
        'templates': [{
            'id': t.id,
            'name': t.name,
            'email_type': t.email_type,
            'subject': t.subject,
            'followup_sequence_number': t.followup_sequence_number,
            'is_active': t.is_active,
        } for t in templates]
    })


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def email_template_detail(request, campaign_id, template_id):
    """Get, update, or delete an email template"""
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)
    template = get_object_or_404(EmailTemplate, id=template_id, campaign=campaign)
    
    if request.method == 'GET':
        return JsonResponse({
            'success': True,
            'template': {
                'id': template.id,
                'name': template.name,
                'email_type': template.email_type,
                'subject': template.subject,
                'html_content': template.html_content,
                'text_content': template.text_content,
                'followup_sequence_number': template.followup_sequence_number,
                'is_active': template.is_active,
            }
        })
    
    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
            template.name = data.get('name', template.name)
            template.email_type = data.get('email_type', template.email_type)
            template.subject = data.get('subject', template.subject)
            template.html_content = data.get('html_content', template.html_content)
            template.text_content = data.get('text_content', template.text_content)
            template.followup_sequence_number = data.get('followup_sequence_number', template.followup_sequence_number)
            template.is_active = data.get('is_active', template.is_active)
            template.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Email template updated successfully'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
    
    elif request.method == 'DELETE':
        template.delete()
        return JsonResponse({
            'success': True,
            'message': 'Email template deleted successfully'
        })


@login_required
@require_http_methods(["POST"])
def test_email_template(request, campaign_id, template_id):
    """Send a test email using a template"""
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)
    template = get_object_or_404(EmailTemplate, id=template_id, campaign=campaign)
    
    try:
        data = json.loads(request.body)
        test_email = data.get('test_email')
        
        if not test_email:
            return JsonResponse({
                'success': False,
                'error': 'Test email address is required'
            }, status=400)
        
        # Create a test lead context
        context = {
            'lead_name': data.get('lead_name', 'Test User'),
            'lead_email': test_email,
            'campaign_name': campaign.name,
        }
        
        # Render email content
        from django.template import Context, Template
        html_template = Template(template.html_content)
        text_template = Template(template.text_content or template.html_content)
        
        html_content = html_template.render(Context(context))
        text_content = text_template.render(Context(context))
        
        # Send test email
        send_mail(
            subject=template.subject,
            message=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[test_email],
            html_message=html_content,
            fail_silently=False,
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Test email sent to {test_email}'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET", "POST"])
def email_sequences_list(request, campaign_id):
    """List or create email sequences for a campaign"""
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # Get is_sub_sequence from request data (default to False if not provided)
            is_sub_sequence = data.get('is_sub_sequence', False)
            
            # ENFORCE: Only 1 main sequence per campaign
            # Determine if this is a sub-sequence (defaults to main sequence if not provided)
            is_sub_sequence = data.get('is_sub_sequence', False)
            
            # ENFORCE: Only 1 main sequence per campaign
            if not is_sub_sequence:
                existing_main_sequence = EmailSequence.objects.filter(
                    campaign=campaign,
                    is_sub_sequence=False
                ).first()
                
                if existing_main_sequence:
                    return JsonResponse({
                        'success': False,
                        'error': f'Only 1 main sequence is allowed per campaign. A sequence "{existing_main_sequence.name}" already exists. Please edit or delete it first.'
                    }, status=400)
            
            sequence = EmailSequence.objects.create(
                campaign=campaign,
                name=data.get('name'),
                is_sub_sequence=is_sub_sequence,
                is_sub_sequence=is_sub_sequence,
            )
            
            # Add steps if provided
            steps = data.get('steps', [])
            for step_data in steps:
                template_id = step_data.get('template_id')
                if template_id:
                    template = EmailTemplate.objects.get(id=template_id, campaign=campaign)
                    EmailSequenceStep.objects.create(
                        sequence=sequence,
                        template=template,
                        step_order=step_data.get('step_order', 1),
                        delay_days=step_data.get('delay_days', 0),
                        delay_hours=step_data.get('delay_hours', 0),
                        delay_minutes=step_data.get('delay_minutes', 0),
                    )
            
            return JsonResponse({
                'success': True,
                'sequence_id': sequence.id,
                'message': 'Email sequence created successfully'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
    
    sequences = EmailSequence.objects.filter(campaign=campaign)
    sequences_data = []
    for seq in sequences:
        steps = EmailSequenceStep.objects.filter(sequence=seq).order_by('step_order')
        sequences_data.append({
            'id': seq.id,
            'name': seq.name,
            'is_active': seq.is_active,
            'steps': [{
                'id': step.id,
                'template_id': step.template.id,
                'template_name': step.template.name,
                'step_order': step.step_order,
                'delay_days': step.delay_days,
                'delay_hours': step.delay_hours,
                'delay_minutes': step.delay_minutes,
            } for step in steps]
        })
    
    return JsonResponse({
        'success': True,
        'sequences': sequences_data
    })




