import logging
import secrets
from datetime import timedelta

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth.hashers import make_password, check_password
from rest_framework.authtoken.models import Token

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core.models import Company, CompanyUser, CompanyRegistrationToken, CompanyUserToken

logger = logging.getLogger(__name__)

# Password reset OTP settings
OTP_TTL_MINUTES = 10


def _find_login_company_user(email):
    """Resolve the CompanyUser that would be used for login with this email.
    Mirrors login_company_user's lookup (most recently active when duplicated)."""
    qs = CompanyUser.objects.filter(email=email).order_by('-last_login')
    return qs.first()


class CompanyAuthThrottle(AnonRateThrottle):
    """Throttle by IP for public login/register endpoints to slow brute-force
    attempts. Rate defined in settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']."""
    scope = 'company_auth'


@api_view(['GET'])
@permission_classes([AllowAny])
def verify_registration_token(request):
    """Verify registration token"""
    try:
        token = request.GET.get('token')
        
        if not token:
            return Response({
                'status': 'error',
                'message': 'Token is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            registration_token = CompanyRegistrationToken.objects.get(token=token)
        except CompanyRegistrationToken.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Invalid token'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if token is used
        if registration_token.is_used:
            return Response({
                'status': 'error',
                'message': 'Token has already been used'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if token is expired
        if registration_token.expires_at < timezone.now():
            return Response({
                'status': 'error',
                'message': 'Token has expired'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        company_name = registration_token.company.name if registration_token.company else None
        
        return Response({
            'status': 'success',
            'message': 'Token is valid',
            'data': {
                'valid': True,
                'companyId': registration_token.company.id if registration_token.company else None,
                'companyName': company_name,
                'expiresAt': registration_token.expires_at.isoformat()
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to verify token',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([CompanyAuthThrottle])
def register_company_user(request):
    """Register company account via token"""
    try:
        data = request.data
        token = data.get('token')
        email = data.get('email')
        password = data.get('password')
        full_name = data.get('fullName') or data.get('full_name', '')
        
        if not token or not email or not password:
            return Response({
                'status': 'error',
                'message': 'Token, email, and password are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Verify token
        try:
            registration_token = CompanyRegistrationToken.objects.get(token=token)
        except CompanyRegistrationToken.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Invalid token'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if registration_token.is_used:
            return Response({
                'status': 'error',
                'message': 'Token has already been used'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if registration_token.expires_at < timezone.now():
            return Response({
                'status': 'error',
                'message': 'Token has expired'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        company = registration_token.company
        
        # Check if email already exists for this company
        if CompanyUser.objects.filter(company=company, email=email).exists():
            return Response({
                'status': 'error',
                'message': 'Email already registered for this company'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create company user with company_user role by default
        company_user = CompanyUser.objects.create(
            company=company,
            email=email,
            password_hash=make_password(password),
            full_name=full_name,
            role='company_user',  # Default role for registered company users
            is_active=True
        )
        
        # Mark token as used
        registration_token.is_used = True
        registration_token.used_at = timezone.now()
        registration_token.save()
        
        # Generate or get authentication token for the newly registered user
        auth_token, created = CompanyUserToken.objects.get_or_create(company_user=company_user)
        
        return Response({
            'status': 'success',
            'message': 'Company account registered successfully',
            'data': {
                'user': {
                    'id': company_user.id,
                    'email': company_user.email,
                    'fullName': company_user.full_name,
                    'role': company_user.role,
                    'companyId': company.id,
                    'companyName': company.name
                },
                'token': auth_token.key  # Return authentication token for auto-login
            }
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to register company account',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([CompanyAuthThrottle])
def login_company_user(request):
    """Company login"""
    try:
        data = request.data
        email = data.get('email')
        password = data.get('password')
        company_id = data.get('companyId') or data.get('company_id')
        
        if not email or not password:
            return Response({
                'status': 'error',
                'message': 'Email and password are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Find company user
        try:
            if company_id:
                company = Company.objects.get(id=company_id)
                company_user = CompanyUser.objects.get(company=company, email=email)
            else:
                # Use filter+order_by to handle duplicate emails across companies gracefully
                # (picks the most recently active account)
                qs = CompanyUser.objects.filter(email=email).order_by('-last_login')
                if not qs.exists():
                    raise CompanyUser.DoesNotExist
                company_user = qs.first()
                company = company_user.company
        except (CompanyUser.DoesNotExist, Company.DoesNotExist):
            return Response({
                'status': 'error',
                'message': 'Invalid email or password'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Verify password
        if not check_password(password, company_user.password_hash):
            return Response({
                'status': 'error',
                'message': 'Invalid email or password'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Check if user is active
        if not company_user.is_active:
            return Response({
                'status': 'error',
                'message': 'Account is inactive'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Update last login
        company_user.last_login = timezone.now()
        company_user.save()
        
        # Generate or get token
        token, created = CompanyUserToken.objects.get_or_create(company_user=company_user)
        
        return Response({
            'status': 'success',
            'message': 'Login successful',
            'data': {
                'user': {
                    'id': company_user.id,
                    'email': company_user.email,
                    'fullName': company_user.full_name,
                    'role': company_user.role,
                    'companyId': company.id,
                    'companyName': company.name
                },
                'token': token.key
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to login',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def logout_company_user(request):
    """Invalidate the company user's auth token."""
    try:
        CompanyUserToken.objects.filter(company_user=request.user).delete()
    except Exception:
        pass
    return Response({'status': 'success', 'message': 'Logged out successfully.'}, status=status.HTTP_200_OK)


# Generic response so an attacker can't tell whether an email exists (avoids
# account enumeration). Used for the forgot-password entrypoint.
_FORGOT_GENERIC = {
    'status': 'success',
    'message': 'If an account exists for that email, a verification code has been sent.',
}


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([CompanyAuthThrottle])
def forgot_password(request):
    """Step 1: user submits their email. If a company account exists, generate
    a 6-digit OTP, store it (hashed lifetime via expiry) and email it.
    Always returns a generic success to prevent email enumeration."""
    try:
        email = (request.data.get('email') or '').strip()
        if not email:
            return Response({
                'status': 'error',
                'message': 'Email is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        company_user = _find_login_company_user(email)

        # Only actually send if the account exists and is active.
        if company_user and company_user.is_active:
            otp = f"{secrets.randbelow(1_000_000):06d}"
            company_user.reset_otp = otp
            company_user.reset_otp_expires = timezone.now() + timedelta(minutes=OTP_TTL_MINUTES)
            company_user.save(update_fields=['reset_otp', 'reset_otp_expires'])

            subject = 'Your password reset code'
            message = (
                f"Hi {company_user.full_name or 'there'},\n\n"
                f"Your password reset code is: {otp}\n\n"
                f"This code expires in {OTP_TTL_MINUTES} minutes. "
                f"If you didn't request this, you can safely ignore this email.\n\n"
                f"— {company_user.company.name if company_user.company else 'Pay Per Project'}"
            )
            try:
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [company_user.email],
                    fail_silently=False,
                )
            except Exception as mail_exc:
                logger.error(f"Failed to send reset OTP to {email}: {mail_exc}", exc_info=True)
                # Don't leak mail failures to the client; still return generic.

        return Response(_FORGOT_GENERIC, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"forgot_password error: {e}", exc_info=True)
        # Still return generic success to avoid leaking anything.
        return Response(_FORGOT_GENERIC, status=status.HTTP_200_OK)


def _validate_otp(company_user):
    """Return True if the stored OTP exists and hasn't expired."""
    if not company_user or not company_user.reset_otp or not company_user.reset_otp_expires:
        return False
    return company_user.reset_otp_expires >= timezone.now()


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([CompanyAuthThrottle])
def verify_reset_otp(request):
    """Step 2: verify the emailed OTP for the given email."""
    try:
        email = (request.data.get('email') or '').strip()
        otp = (request.data.get('otp') or '').strip()

        if not email or not otp:
            return Response({
                'status': 'error',
                'message': 'Email and code are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        company_user = _find_login_company_user(email)

        if not _validate_otp(company_user) or company_user.reset_otp != otp:
            return Response({
                'status': 'error',
                'message': 'Invalid or expired code'
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'status': 'success',
            'message': 'Code verified. You can now set a new password.'
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"verify_reset_otp error: {e}", exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Failed to verify code'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([CompanyAuthThrottle])
def reset_password(request):
    """Step 3: with a valid OTP, set the new password and clear the OTP."""
    try:
        email = (request.data.get('email') or '').strip()
        otp = (request.data.get('otp') or '').strip()
        new_password = request.data.get('password') or request.data.get('newPassword') or ''

        if not email or not otp or not new_password:
            return Response({
                'status': 'error',
                'message': 'Email, code, and new password are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        if len(new_password) < 8:
            return Response({
                'status': 'error',
                'message': 'Password must be at least 8 characters long'
            }, status=status.HTTP_400_BAD_REQUEST)

        company_user = _find_login_company_user(email)

        if not _validate_otp(company_user) or company_user.reset_otp != otp:
            return Response({
                'status': 'error',
                'message': 'Invalid or expired code'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Update password and invalidate the OTP + any existing sessions.
        company_user.password_hash = make_password(new_password)
        company_user.reset_otp = None
        company_user.reset_otp_expires = None
        company_user.save(update_fields=['password_hash', 'reset_otp', 'reset_otp_expires'])
        CompanyUserToken.objects.filter(company_user=company_user).delete()

        return Response({
            'status': 'success',
            'message': 'Password reset successfully. Please log in with your new password.'
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"reset_password error: {e}", exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Failed to reset password'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

