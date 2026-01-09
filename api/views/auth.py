from rest_framework import status, generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework.authtoken.models import Token

from api.serializers.auth import RegisterSerializer, LoginSerializer, UserSerializer


@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    """Register a new user"""
    serializer = RegisterSerializer(data=request.data)
    
    if serializer.is_valid():
        user = serializer.save()
        
        # Generate token
        token, created = Token.objects.get_or_create(user=user)
        
        # Get user type
        user_type = 'client'
        if hasattr(user, 'profile'):
            role = user.profile.role
            if role == 'developer':
                user_type = 'freelancer'
            elif user.is_staff:
                user_type = 'admin'
        
        user_data = UserSerializer(user).data
        
        return Response({
            'status': 'success',
            'message': 'User registered successfully',
            'data': {
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'userType': user_type,
                },
                'token': token.key,
            }
        }, status=status.HTTP_201_CREATED)
    
    return Response({
        'status': 'error',
        'message': 'Validation error',
        'errors': serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    """Login user"""
    serializer = LoginSerializer(data=request.data)
    
    if serializer.is_valid():
        user = serializer.validated_data['user']
        
        # Update last login
        user.last_login = timezone.now()
        user.save()
        
        # Generate or get token
        token, created = Token.objects.get_or_create(user=user)
        
        # Get user type
        user_type = 'client'
        account_status = 'active' if user.is_active else 'inactive'
        if hasattr(user, 'profile'):
            role = user.profile.role
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
                    'userType': user_type,
                    'accountStatus': account_status,
                    'emailVerified': True,
                },
                'token': token.key,
            }
        }, status=status.HTTP_200_OK)
    
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
    """Logout user"""
    # Delete token
    try:
        token = Token.objects.get(user=request.user)
        token.delete()
    except Token.DoesNotExist:
        pass
    
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
        
        # Debug info - check permission too
        try:
            from api.permissions import IsAdmin
            permission = IsAdmin()
            has_admin_permission = permission.has_permission(request, None)
        except Exception as e:
            has_admin_permission = False
        
        debug_info = {
            'email': request.user.email,
            'username': request.user.username,
            'id': request.user.id,
            'is_staff': request.user.is_staff,
            'is_superuser': request.user.is_superuser,
            'is_active': request.user.is_active,
            'has_admin_permission': has_admin_permission,
        }
        
        return Response({
            'status': 'success',
            'data': {
                'user': serializer.data,
                'debug': debug_info  # Remove this in production
            }
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to get current user',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

