from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta
import secrets
import string

from core.models import Company, CompanyRegistrationToken
from api.serializers.company import CompanySerializer, CompanyRegistrationTokenSerializer
from api.permissions import IsAdmin


def generate_registration_token():
    """Generate a unique registration token"""
    while True:
        token = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64))
        if not CompanyRegistrationToken.objects.filter(token=token).exists():
            return token


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAdmin])
def create_company(request):
    """Create company and generate registration token (Admin only)"""
    try:
        serializer = CompanySerializer(data=request.data)
        
        if serializer.is_valid():
            company = serializer.save()
            
            # Generate registration token
            token_value = generate_registration_token()
            expires_at = timezone.now() + timedelta(days=7)  # Token expires in 7 days
            
            registration_token = CompanyRegistrationToken.objects.create(
                company=company,
                token=token_value,
                expires_at=expires_at,
                created_by=request.user
            )
            
            return Response({
                'status': 'success',
                'message': 'Company created successfully',
                'data': {
                    'company': CompanySerializer(company).data,
                    'registrationToken': {
                        'token': token_value,
                        'expiresAt': expires_at.isoformat(),
                        'companyId': company.id
                    }
                }
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'status': 'error',
            'message': 'Validation error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to create company',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdmin])
def list_companies(request):
    """Get all companies (Admin only)"""
    try:
        companies = Company.objects.all().order_by('name')
        
        # Filter by is_active if provided
        is_active = request.GET.get('is_active')
        if is_active is not None:
            is_active = is_active.lower() == 'true'
            companies = companies.filter(is_active=is_active)
        
        serializer = CompanySerializer(companies, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch companies',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdmin])
def get_company_tokens(request, companyId):
    """Get company registration tokens (Admin only)"""
    try:
        company = get_object_or_404(Company, id=companyId)
        
        tokens = CompanyRegistrationToken.objects.filter(company=company).order_by('-created_at')
        serializer = CompanyRegistrationTokenSerializer(tokens, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch tokens',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAdmin])
def generate_company_token(request, companyId):
    """Generate new registration token for existing company (Admin only)"""
    try:
        company = get_object_or_404(Company, id=companyId)
        
        # Generate token
        token_value = generate_registration_token()
        expires_at = timezone.now() + timedelta(days=7)
        
        registration_token = CompanyRegistrationToken.objects.create(
            company=company,
            token=token_value,
            expires_at=expires_at,
            created_by=request.user
        )
        
        serializer = CompanyRegistrationTokenSerializer(registration_token)
        
        return Response({
            'status': 'success',
            'message': 'Registration token generated successfully',
            'data': serializer.data
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to generate token',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

