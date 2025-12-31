from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password
from rest_framework.authtoken.models import Token

from core.models import Company, CompanyUser, CompanyRegistrationToken


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
        
        # Create company user
        company_user = CompanyUser.objects.create(
            company=company,
            email=email,
            password_hash=make_password(password),
            full_name=full_name,
            role='admin',  # Default role for registered users
            is_active=True
        )
        
        # Mark token as used
        registration_token.is_used = True
        registration_token.used_at = timezone.now()
        registration_token.save()
        
        return Response({
            'status': 'success',
            'message': 'Company account registered successfully',
            'data': {
                'id': company_user.id,
                'email': company_user.email,
                'companyId': company.id,
                'companyName': company.name
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
                company_user = CompanyUser.objects.get(email=email)
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
        
        # For company users, we might want to create a token or session
        # For now, return basic user data
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
                }
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to login',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

