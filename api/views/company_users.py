"""
Company User Management API Views
Allows company users to create and manage regular users (auth_user table)
"""

import re
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Q

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core.models import CompanyUser, UserProfile, Company
from api.serializers.company_users import CompanyUserManagementSerializer, UserListSerializer


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_user(request):
    """
    Create a new user (auth_user) by company user
    POST /api/company/users/create
    """
    try:
        # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
        company_user = request.user
        data = request.data

        # Validate required fields
        email = (data.get('email') or '').strip().lower()
        password = data.get('password', '')
        username = data.get('username') or email.split('@')[0]  # Use email prefix as username if not provided
        role = data.get('role', 'team_member')
        full_name = (data.get('fullName') or data.get('full_name', '')).strip()
        phone_number = (data.get('phoneNumber') or data.get('phone_number', '')).strip()

        if not email or not password:
            return Response({
                'status': 'error',
                'message': 'Email and password are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        if not full_name:
            return Response({
                'status': 'error',
                'message': 'Full name is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Full name: no digits allowed, only letters/spaces/dots/hyphens/apostrophes
        if re.search(r'[0-9]', full_name):
            return Response({
                'status': 'error',
                'message': 'Full name must not contain numbers.'
            }, status=status.HTTP_400_BAD_REQUEST)
        if not re.match(r"^[a-zA-Z\s.'\-]+$", full_name):
            return Response({
                'status': 'error',
                'message': "Full name can only contain letters, spaces, dots, hyphens, and apostrophes."
            }, status=status.HTTP_400_BAD_REQUEST)
        alpha_count = sum(1 for c in full_name if c.isalpha())
        if alpha_count < 2:
            return Response({
                'status': 'error',
                'message': 'Full name must contain at least 2 alphabetic characters.'
            }, status=status.HTTP_400_BAD_REQUEST)

        if not phone_number:
            return Response({
                'status': 'error',
                'message': 'Phone number is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Phone number validation - at least 7 digits, allows +, spaces, hyphens, parentheses
        phone_digits = sum(1 for c in phone_number if c.isdigit())
        if not re.match(r'^[+]?[\d\s\-()]{7,20}$', phone_number) or phone_digits < 7:
            return Response({
                'status': 'error',
                'message': 'Enter a valid phone number (at least 7 digits, e.g., +1234567890).'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Strict email validation
        email_regex = r'^[a-zA-Z0-9][a-zA-Z0-9._%+-]*@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            return Response({
                'status': 'error',
                'message': 'Enter a valid email address (e.g., user@example.com).'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Password strength validation: min 8 chars, 1 uppercase, 1 lowercase, 1 digit, 1 special char
        if len(password) < 8:
            return Response({
                'status': 'error',
                'message': 'Password must be at least 8 characters long.'
            }, status=status.HTTP_400_BAD_REQUEST)
        if not re.search(r'[A-Z]', password):
            return Response({
                'status': 'error',
                'message': 'Password must contain at least one uppercase letter.'
            }, status=status.HTTP_400_BAD_REQUEST)
        if not re.search(r'[a-z]', password):
            return Response({
                'status': 'error',
                'message': 'Password must contain at least one lowercase letter.'
            }, status=status.HTTP_400_BAD_REQUEST)
        if not re.search(r'[0-9]', password):
            return Response({
                'status': 'error',
                'message': 'Password must contain at least one digit.'
            }, status=status.HTTP_400_BAD_REQUEST)
        if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\\/~`]', password):
            return Response({
                'status': 'error',
                'message': 'Password must contain at least one special character (!@#$%^&* etc.).'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Location validation (if provided)
        location = (data.get('location') or '').strip()
        if location:
            loc_alpha = sum(1 for c in location if c.isalpha())
            if loc_alpha < 2:
                return Response({
                    'status': 'error',
                    'message': 'Location must contain at least 2 alphabetic characters.'
                }, status=status.HTTP_400_BAD_REQUEST)

        # Bio validation (if provided)
        bio = (data.get('bio') or '').strip()
        if bio:
            bio_alnum = sum(1 for c in bio if c.isalnum())
            if bio_alnum < 10:
                return Response({
                    'status': 'error',
                    'message': 'Bio must contain at least 10 alphanumeric characters.'
                }, status=status.HTTP_400_BAD_REQUEST)

        # Validate role
        valid_roles = [choice[0] for choice in UserProfile.ROLE_CHOICES]
        if role not in valid_roles:
            return Response({
                'status': 'error',
                'message': f'Invalid role. Must be one of: {", ".join(valid_roles)}'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check if user already exists in auth_user
        if User.objects.filter(email__iexact=email).exists():
            return Response({
                'status': 'error',
                'message': 'User with this email already exists'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check if email is already used by a company
        from core.models import Company as CompanyModel
        if CompanyModel.objects.filter(email__iexact=email).exists():
            return Response({
                'status': 'error',
                'message': 'This email is already registered as a company email'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check if email is already used by a company user
        if CompanyUser.objects.filter(email__iexact=email).exists():
            return Response({
                'status': 'error',
                'message': 'This email is already registered as a company user'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if username already exists
        if User.objects.filter(username=username).exists():
            # Append company user ID to make it unique
            username = f"{username}_{company_user.id}"
        
        # Get company from company_user
        company = company_user.company
        
        # Split full_name into first_name and last_name
        name_parts = full_name.split(maxsplit=1) if full_name else []
        first_name = name_parts[0] if len(name_parts) > 0 else ''
        last_name = name_parts[1] if len(name_parts) > 1 else ''
        
        # Create Django User
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_active=True,
            is_staff=False,
            is_superuser=False
        )
        
        # Create or update UserProfile
        profile, created = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'role': role,
                'company': company,
                'created_by_company_user': company_user,
                'company_name': company.name if company else None,
                'phone_number': data.get('phoneNumber') or data.get('phone_number'),
                'bio': data.get('bio'),
                'location': data.get('location'),
            }
        )
        
        # If profile already existed, update it
        if not created:
            profile.role = role
            profile.company = company
            profile.created_by_company_user = company_user
            if data.get('phoneNumber') or data.get('phone_number'):
                profile.phone_number = data.get('phoneNumber') or data.get('phone_number')
            if data.get('bio'):
                profile.bio = data.get('bio')
            if data.get('location'):
                profile.location = data.get('location')
            profile.save()
        
        # Generate token for the new user (optional - for auto-login)
        from rest_framework.authtoken.models import Token
        token, _ = Token.objects.get_or_create(user=user)
        
        serializer = UserListSerializer(user)
        
        return Response({
            'status': 'success',
            'message': 'User created successfully',
            'data': {
                'user': serializer.data,
                'token': token.key  # Return token for potential auto-login
            }
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({
            'status': 'error',
            'message': 'Failed to create user',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_users(request):
    """
    List all users created by the company user
    GET /api/company/users
    """
    try:
        # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
        company_user = request.user
        company = company_user.company
        
        # Get all users created by this company user
        # Filter only users that have profiles and were created by this company user
        users = User.objects.filter(
            profile__created_by_company_user=company_user
        ).select_related('profile').prefetch_related('profile__created_by_company_user').order_by('-date_joined')
        
        # Optional: Also include users from same company (not just created by this user)
        include_company_users = request.GET.get('include_company_users', 'false').lower() == 'true'
        if include_company_users:
            users = User.objects.filter(
                Q(profile__created_by_company_user=company_user) |
                Q(profile__company=company)
            ).select_related('profile').prefetch_related('profile__created_by_company_user').distinct().order_by('-date_joined')
        
        # Pagination
        page = int(request.GET.get('page', 1))
        limit = int(request.GET.get('limit', 20))
        
        total = users.count()
        total_pages = (total + limit - 1) // limit if limit > 0 else 1
        
        # Apply pagination
        start = (page - 1) * limit
        end = start + limit
        paginated_users = users[start:end]
        
        serializer = UserListSerializer(paginated_users, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'totalPages': total_pages
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        import traceback
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in list_users: {str(e)}")
        logger.error(traceback.format_exc())
        return Response({
            'status': 'error',
            'message': 'Failed to fetch users',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_user(request, userId):
    """
    Get user details
    GET /api/company/users/{userId}
    """
    try:
        # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
        company_user = request.user
        
        # Get user and verify it was created by this company user
        user = get_object_or_404(User, id=userId)
        
        # Check if user was created by this company user
        if not hasattr(user, 'profile') or user.profile.created_by_company_user != company_user:
            return Response({
                'status': 'error',
                'message': 'User not found or access denied'
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = UserListSerializer(user)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch user',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'PATCH'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_user(request, userId):
    """
    Update user
    PUT/PATCH /api/company/users/{userId}
    """
    try:
        # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
        company_user = request.user
        
        # Get user and verify it was created by this company user
        user = get_object_or_404(User, id=userId)
        
        if not hasattr(user, 'profile') or user.profile.created_by_company_user != company_user:
            return Response({
                'status': 'error',
                'message': 'User not found or access denied'
            }, status=status.HTTP_404_NOT_FOUND)
        
        data = request.data
        
        # Update user fields
        if 'email' in data:
            # Check if email is already taken by another user
            if User.objects.filter(email=data['email']).exclude(id=user.id).exists():
                return Response({
                    'status': 'error',
                    'message': 'Email already taken by another user'
                }, status=status.HTTP_400_BAD_REQUEST)
            user.email = data['email']
        
        if 'fullName' in data or 'full_name' in data:
            full_name = data.get('fullName') or data.get('full_name', '')
            name_parts = full_name.split(maxsplit=1) if full_name else []
            user.first_name = name_parts[0] if len(name_parts) > 0 else ''
            user.last_name = name_parts[1] if len(name_parts) > 1 else ''
        
        if 'password' in data:
            user.set_password(data['password'])
        
        user.save()
        
        # Update profile
        profile = user.profile
        if 'role' in data:
            valid_roles = [choice[0] for choice in UserProfile.ROLE_CHOICES]
            if data['role'] in valid_roles:
                profile.role = data['role']
        
        if 'phoneNumber' in data or 'phone_number' in data:
            profile.phone_number = data.get('phoneNumber') or data.get('phone_number')
        
        if 'bio' in data:
            profile.bio = data['bio']
        
        if 'location' in data:
            profile.location = data['location']
        
        profile.save()
        
        serializer = UserListSerializer(user)
        
        return Response({
            'status': 'success',
            'message': 'User updated successfully',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to update user',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def delete_user(request, userId):
    """
    Delete user (deactivate instead of hard delete)
    DELETE /api/company/users/{userId}
    """
    try:
        # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
        company_user = request.user
        
        # Get user and verify it was created by this company user
        user = get_object_or_404(User, id=userId)
        
        if not hasattr(user, 'profile') or user.profile.created_by_company_user != company_user:
            return Response({
                'status': 'error',
                'message': 'User not found or access denied'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Deactivate user instead of deleting
        user.is_active = False
        user.save()
        
        return Response({
            'status': 'success',
            'message': 'User deactivated successfully'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to delete user',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def reactivate_user(request, userId):
    """
    Reactivate a deactivated user
    POST /api/company/users/{userId}/reactivate
    """
    try:
        company_user = request.user

        user = get_object_or_404(User, id=userId)

        if not hasattr(user, 'profile') or user.profile.created_by_company_user != company_user:
            return Response({
                'status': 'error',
                'message': 'User not found or access denied'
            }, status=status.HTTP_404_NOT_FOUND)

        if user.is_active:
            return Response({
                'status': 'error',
                'message': 'User is already active'
            }, status=status.HTTP_400_BAD_REQUEST)

        user.is_active = True
        user.save()

        serializer = UserListSerializer(user)

        return Response({
            'status': 'success',
            'message': 'User reactivated successfully',
            'data': serializer.data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to reactivate user',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

