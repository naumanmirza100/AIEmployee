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
def email_accounts_list(request):
    """List all email accounts for the current user"""
    if request.method == 'POST':
        # Handle AJAX POST requests (for adding accounts)
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
                # IMAP fields
                imap_host=data.get('imap_host', ''),
                imap_port=int(data.get('imap_port')) if data.get('imap_port') else None,
                imap_use_ssl=data.get('imap_use_ssl', True),
                imap_username=data.get('imap_username', ''),
                imap_password=data.get('imap_password', ''),
                enable_imap_sync=data.get('enable_imap_sync', False),
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
    
    # GET request - render HTML template
    accounts = EmailAccount.objects.filter(owner=request.user).order_by('-is_default', '-is_active', '-created_at')
    return render(request, 'marketing/email_accounts.html', {
        'accounts': accounts
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
                # IMAP fields
                'imap_host': account.imap_host,
                'imap_port': account.imap_port,
                'imap_use_ssl': account.imap_use_ssl,
                'imap_username': account.imap_username,
                'imap_password': account.imap_password,
                'enable_imap_sync': account.enable_imap_sync,
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
            # IMAP fields
            if 'imap_host' in data:
                account.imap_host = data.get('imap_host', '')
            if 'imap_port' in data:
                account.imap_port = int(data.get('imap_port')) if data.get('imap_port') else None
            if 'imap_use_ssl' in data:
                account.imap_use_ssl = data.get('imap_use_ssl', True)
            if 'imap_username' in data:
                account.imap_username = data.get('imap_username', '')
            if 'imap_password' in data:
                account.imap_password = data.get('imap_password', '')
            if 'enable_imap_sync' in data:
                account.enable_imap_sync = data.get('enable_imap_sync', False)
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

