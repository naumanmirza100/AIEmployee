import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.utils import timezone

from api.serializers.auth import LoginSerializer, UserSerializer
from api.views.company_auth import CompanyAuthThrottle
from core import sign_in
from core.models import UserToken

logger = logging.getLogger(__name__)

# The old marketplace sign-up (POST /api/auth/register) is gone (CO-269): it made a working account
# for any address, with no confirmation and no limit, and no screen used it. Employee logins are
# made by their company (Users), dashboard logins through the company sign-up.


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([CompanyAuthThrottle])
def login(request):
    """Login user (employees and platform staff).

    Limited per caller like the dashboard sign-in, and per account: after
    sign_in.MAX_WRONG_PASSWORDS wrong passwords the account refuses every password for a while
    (CO-100). Each sign-in gets its own token (CO-270)."""
    email = str(request.data.get('email') or '')
    if email and sign_in.is_locked('user', email):
        return Response({'status': 'error', 'message': sign_in.LOCKED_MESSAGE},
                        status=status.HTTP_429_TOO_MANY_REQUESTS)

    serializer = LoginSerializer(data=request.data)

    if serializer.is_valid():
        user = serializer.validated_data['user']
        sign_in.right_password('user', email)

        # Update last login
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])

        token = sign_in.new_user_token(user)

        # Get user type
        user_type = 'client'
        account_status = 'active' if user.is_active else 'inactive'
        role = None
        created_by_company_user = False

        if hasattr(user, 'profile'):
            profile = user.profile
            role = profile.role
            created_by_company_user = profile.created_by_company_user is not None

            if role == 'developer':
                user_type = 'freelancer'
            elif user.is_staff:
                user_type = 'admin'

        return Response({
            'status': 'success',
            'message': 'Login successful',
            'data': {
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'firstName': user.first_name,
                    'lastName': user.last_name,
                    # The same value auth/me sends, so the screens see one profile before and after a reload.
                    'phone': getattr(getattr(user, 'profile', None), 'phone_number', None) or None,
                    'userType': user_type,
                    'accountStatus': account_status,
                    'emailVerified': True,
                    'role': role,
                    'createdByCompanyUser': created_by_company_user,
                },
                'token': token.key,
            }
        }, status=status.HTTP_200_OK)

    if email:
        sign_in.wrong_password('user', email)
    return Response({
        'status': 'error',
        'message': serializer.errors.get('non_field_errors', ['Invalid credentials'])[0]
    }, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['POST'])
@permission_classes([AllowAny])
def refresh_token(request):
    """Refresh access token (placeholder - token refresh not implemented yet)"""
    return Response({
        'status': 'success',
        'message': 'Token refresh not implemented yet'
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    """Sign out this device only: its own token is deleted, other devices stay signed in (CO-270)."""
    if isinstance(request.auth, UserToken):
        request.auth.delete()

    return Response({
        'status': 'success',
        'message': 'Logout successful'
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_current_user(request):
    """Get current authenticated user"""
    try:
        # Refresh user to get latest data
        request.user.refresh_from_db()

        serializer = UserSerializer(request.user)

        return Response({
            'status': 'success',
            'data': {
                'user': serializer.data,
            }
        }, status=status.HTTP_200_OK)
    except Exception:
        logger.exception('auth/me failed for user %s', request.user.pk)
        return Response({
            'status': 'error',
            'message': 'Failed to get current user',
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
