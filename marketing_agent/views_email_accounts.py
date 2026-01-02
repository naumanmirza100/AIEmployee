from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from .models import EmailAccount, Campaign
import json


@login_required
@require_http_methods(["GET", "POST"])
def email_accounts_list(request):
    """List all email accounts for the current user"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            account = EmailAccount.objects.create(
                owner=request.user,
                name=data.get('name'),
                account_type=data.get('account_type', 'smtp'),
                email=data.get('email'),
                smtp_host=data.get('smtp_host'),
                smtp_port=int(data.get('smtp_port', 587)),
                smtp_username=data.get('smtp_username'),
                smtp_password=data.get('smtp_password'),
                use_tls=data.get('use_tls', True),
                use_ssl=data.get('use_ssl', False),
                is_gmail_app_password=data.get('is_gmail_app_password', False),
                is_active=data.get('is_active', True),
                is_default=data.get('is_default', False),
            )
            return JsonResponse({
                'success': True,
                'account_id': account.id,
                'message': 'Email account created successfully'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
    
    accounts = EmailAccount.objects.filter(owner=request.user).order_by('-is_default', '-is_active', '-created_at')
    return JsonResponse({
        'success': True,
        'accounts': [{
            'id': a.id,
            'name': a.name,
            'email': a.email,
            'account_type': a.account_type,
            'is_active': a.is_active,
            'is_default': a.is_default,
            'test_status': a.test_status,
            'last_tested_at': a.last_tested_at.isoformat() if a.last_tested_at else None,
        } for a in accounts]
    })


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def email_account_detail(request, account_id):
    """Get, update, or delete an email account"""
    account = get_object_or_404(EmailAccount, id=account_id, owner=request.user)
    
    if request.method == 'GET':
        return JsonResponse({
            'success': True,
            'account': {
                'id': account.id,
                'name': account.name,
                'account_type': account.account_type,
                'email': account.email,
                'smtp_host': account.smtp_host,
                'smtp_port': account.smtp_port,
                'smtp_username': account.smtp_username,
                'smtp_password': account.smtp_password,  # Note: In production, use encryption
                'use_tls': account.use_tls,
                'use_ssl': account.use_ssl,
                'is_gmail_app_password': account.is_gmail_app_password,
                'is_active': account.is_active,
                'is_default': account.is_default,
                'test_status': account.test_status,
            }
        })
    
    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
            account.name = data.get('name', account.name)
            account.account_type = data.get('account_type', account.account_type)
            account.email = data.get('email', account.email)
            account.smtp_host = data.get('smtp_host', account.smtp_host)
            account.smtp_port = int(data.get('smtp_port', account.smtp_port))
            account.smtp_username = data.get('smtp_username', account.smtp_username)
            if 'smtp_password' in data:
                account.smtp_password = data['smtp_password']
            account.use_tls = data.get('use_tls', account.use_tls)
            account.use_ssl = data.get('use_ssl', account.use_ssl)
            account.is_gmail_app_password = data.get('is_gmail_app_password', account.is_gmail_app_password)
            account.is_active = data.get('is_active', account.is_active)
            account.is_default = data.get('is_default', account.is_default)
            account.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Email account updated successfully'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
    
    elif request.method == 'DELETE':
        account.delete()
        return JsonResponse({
            'success': True,
            'message': 'Email account deleted successfully'
        })


@login_required
@require_http_methods(["POST"])
def test_email_account(request, account_id):
    """Test an email account by sending a test email"""
    account = get_object_or_404(EmailAccount, id=account_id, owner=request.user)
    
    try:
        data = json.loads(request.body)
        test_email = data.get('test_email', account.email)
        
        if not test_email:
            return JsonResponse({
                'success': False,
                'error': 'Test email address is required'
            }, status=400)
        
        # Validate email format
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError
        try:
            validate_email(test_email)
        except ValidationError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid test email address format'
            }, status=400)
        
        # Temporarily use this account's settings
        from django.core.mail import EmailMessage
        from django.core.mail.backends.smtp import EmailBackend
        import socket
        import smtplib
        
        try:
            # Create backend with timeout
            backend = EmailBackend(
                host=account.smtp_host,
                port=account.smtp_port,
                username=account.smtp_username,
                password=account.smtp_password,
                use_tls=account.use_tls,
                use_ssl=account.use_ssl,
                fail_silently=False,
                timeout=10,  # 10 second timeout
            )
            
            email = EmailMessage(
                subject='Test Email from Marketing Agent',
                body='This is a test email to verify your email account settings are correct.\n\nIf you received this email, your SMTP configuration is working correctly.',
                from_email=account.email,
                to=[test_email],
                connection=backend,
            )
            email.send()
            
            # Update account test status
            from django.utils import timezone
            account.last_tested_at = timezone.now()
            account.test_status = 'success'
            account.test_error = ''
            account.save()
            
            return JsonResponse({
                'success': True,
                'message': f'Test email sent successfully to {test_email}'
            })
            
        except (socket.timeout, smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, OSError) as e:
            # Connection/network errors
            error_msg = f'Connection failed: {str(e)}. Please check:\n'
            error_msg += f'1. SMTP host "{account.smtp_host}" is correct\n'
            error_msg += f'2. Port {account.smtp_port} is correct\n'
            error_msg += f'3. Your network/firewall allows connections to this server\n'
            error_msg += f'4. For Gmail, use App Password (not regular password)'
            
            from django.utils import timezone
            account.last_tested_at = timezone.now()
            account.test_status = 'failed'
            account.test_error = str(e)
            account.save()
            
            return JsonResponse({
                'success': False,
                'error': error_msg
            }, status=500)
            
        except smtplib.SMTPAuthenticationError as e:
            # Authentication errors
            error_msg = f'Authentication failed: {str(e)}. Please check:\n'
            error_msg += f'1. Username "{account.smtp_username}" is correct\n'
            error_msg += f'2. Password/App Password is correct\n'
            error_msg += f'3. For Gmail, make sure you\'re using an App Password (not your regular password)'
            
            from django.utils import timezone
            account.last_tested_at = timezone.now()
            account.test_status = 'failed'
            account.test_error = str(e)
            account.save()
            
            return JsonResponse({
                'success': False,
                'error': error_msg
            }, status=500)
            
        except smtplib.SMTPException as e:
            # Other SMTP errors
            error_msg = f'SMTP error: {str(e)}'
            
            from django.utils import timezone
            account.last_tested_at = timezone.now()
            account.test_status = 'failed'
            account.test_error = str(e)
            account.save()
            
            return JsonResponse({
                'success': False,
                'error': error_msg
            }, status=500)
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        # Generic error
        from django.utils import timezone
        account.last_tested_at = timezone.now()
        account.test_status = 'failed'
        account.test_error = str(e)
        account.save()
        
        return JsonResponse({
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }, status=500)

