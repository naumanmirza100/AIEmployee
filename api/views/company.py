from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import models
from django.db.models import Count
from datetime import timedelta
import secrets
import string

from core.models import Company, CompanyRegistrationToken, CompanyModulePurchase
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
        # Debug: Log received data
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Received company data: {request.data}")
        
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
        
        # Debug: Log validation errors
        logger.error(f"Validation errors: {serializer.errors}")
        
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
        companies = Company.objects.all().annotate(
            user_count=Count('user_profiles', distinct=True),
            job_count=Count('job_positions', distinct=True),
        ).order_by('name')

        # Filter by is_active if provided
        is_active = request.GET.get('is_active')
        if is_active is not None:
            is_active = is_active.lower() == 'true'
            companies = companies.filter(is_active=is_active)

        # Pagination
        page = int(request.GET.get('page', 1))
        limit = int(request.GET.get('limit', 20))

        total = companies.count()
        total_pages = (total + limit - 1) // limit if limit > 0 else 1

        # Apply pagination
        start = (page - 1) * limit
        end = start + limit
        paginated_companies = companies[start:end]

        serializer = CompanySerializer(paginated_companies, many=True)

        # Add user_count and job_count to each company's data
        data = serializer.data
        for i, company in enumerate(paginated_companies):
            data[i]['user_count'] = company.user_count
            data[i]['job_count'] = company.job_count

        return Response({
            'status': 'success',
            'data': data,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'totalPages': total_pages
            }
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


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdmin])
def list_company_agents(request):
    """Get all AI agent module purchases across all companies (Admin only)"""
    try:
        # Auto-expire: update DB status for any purchase past its expires_at
        now = timezone.now()
        CompanyModulePurchase.objects.filter(
            status='active', expires_at__isnull=False, expires_at__lt=now
        ).update(status='expired')

        purchases = CompanyModulePurchase.objects.select_related(
            'company', 'purchased_by'
        ).order_by('-purchased_at')

        # Filters
        search = request.GET.get('search', '').strip()
        if search:
            purchases = purchases.filter(
                models.Q(company__name__icontains=search) |
                models.Q(module_name__icontains=search) |
                models.Q(company__email__icontains=search)
            )

        status_filter = request.GET.get('status', '').strip()
        if status_filter:
            purchases = purchases.filter(status=status_filter)

        module_filter = request.GET.get('module', '').strip()
        if module_filter:
            purchases = purchases.filter(module_name=module_filter)

        # Pagination
        page = int(request.GET.get('page', 1))
        limit = int(request.GET.get('limit', 20))
        total = purchases.count()
        total_pages = (total + limit - 1) // limit if limit > 0 else 1
        start = (page - 1) * limit
        end = start + limit
        paginated = purchases[start:end]

        data = []
        for purchase in paginated:
            # Determine effective status
            effective_status = purchase.status
            is_expired = purchase.status == 'expired'

            # Compute time remaining or time since expired
            time_remaining = None
            time_ended_ago = None
            if purchase.expires_at:
                if effective_status == 'active':
                    diff = purchase.expires_at - now
                    if diff.total_seconds() > 0:
                        days = diff.days
                        hours = diff.seconds // 3600
                        time_remaining = f"{days}d {hours}h remaining" if days > 0 else f"{hours}h remaining"
                    else:
                        # Edge case: still active in DB but actually expired
                        is_expired = True
                        effective_status = 'expired'
                if effective_status in ('expired',):
                    ended = now - purchase.expires_at
                    if ended.total_seconds() > 0:
                        days = ended.days
                        hours = ended.seconds // 3600
                        time_ended_ago = f"Ended {days}d {hours}h ago" if days > 0 else f"Ended {hours}h ago"

            # For active agents: time since purchase. For expired/cancelled: how long it was active.
            if effective_status == 'active':
                delta = now - purchase.purchased_at
                days_val = delta.days
            elif purchase.expires_at and is_expired:
                delta = purchase.expires_at - purchase.purchased_at
                days_val = delta.days
            elif purchase.cancelled_at:
                delta = purchase.cancelled_at - purchase.purchased_at
                days_val = delta.days
            else:
                delta = now - purchase.purchased_at
                days_val = delta.days

            if days_val > 365:
                active_duration = f"{days_val // 365}y {(days_val % 365) // 30}m"
            elif days_val > 30:
                active_duration = f"{days_val // 30}m {days_val % 30}d"
            else:
                active_duration = f"{days_val}d"

            # Label differs based on status
            if effective_status == 'active':
                active_label = f"Active since: {active_duration}"
            else:
                active_label = f"Was active for {active_duration}"

            data.append({
                'id': purchase.id,
                'company_id': purchase.company.id,
                'company_name': purchase.company.name,
                'company_email': purchase.company.email,
                'company_industry': purchase.company.industry,
                'company_is_active': purchase.company.is_active,
                'module_name': purchase.module_name,
                'module_display_name': purchase.get_module_name_display(),
                'status': effective_status,
                'is_expired': is_expired,
                'deactivated_by_admin': purchase.cancelled_reason == 'admin_deactivated',
                'price_paid': float(purchase.price_paid) if purchase.price_paid else None,
                'purchased_by_name': purchase.purchased_by.full_name if purchase.purchased_by else None,
                'purchased_by_email': purchase.purchased_by.email if purchase.purchased_by else None,
                'purchased_at': purchase.purchased_at.isoformat() if purchase.purchased_at else None,
                'expires_at': purchase.expires_at.isoformat() if purchase.expires_at else None,
                'cancelled_at': purchase.cancelled_at.isoformat() if purchase.cancelled_at else None,
                'cancelled_reason': purchase.cancelled_reason,
                'time_remaining': time_remaining,
                'time_ended_ago': time_ended_ago,
                'active_label': active_label,
                'created_at': purchase.created_at.isoformat() if purchase.created_at else None,
                'updated_at': purchase.updated_at.isoformat() if purchase.updated_at else None,
            })

        # Summary stats - compute expired properly (DB may still say 'active' but expires_at passed)
        all_purchases_qs = CompanyModulePurchase.objects.all()
        active_count = 0
        expired_count = 0
        cancelled_count = 0
        for p in all_purchases_qs:
            if p.status == 'cancelled':
                cancelled_count += 1
            elif p.status == 'active' and p.expires_at and now > p.expires_at:
                expired_count += 1
            elif p.status == 'expired':
                expired_count += 1
            elif p.status == 'active':
                active_count += 1
        stats = {
            'total_purchases': all_purchases_qs.count(),
            'active_count': active_count,
            'cancelled_count': cancelled_count,
            'expired_count': expired_count,
        }

        return Response({
            'status': 'success',
            'data': data,
            'stats': stats,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'totalPages': total_pages,
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch company agents',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated, IsAdmin])
def toggle_company_agent_status(request, purchaseId):
    """Toggle AI agent module status between active and cancelled (Admin only)"""
    try:
        purchase = get_object_or_404(CompanyModulePurchase, id=purchaseId)

        new_status = request.data.get('status')
        if new_status not in ('active', 'cancelled'):
            return Response({
                'status': 'error',
                'message': 'Status must be either "active" or "cancelled"'
            }, status=status.HTTP_400_BAD_REQUEST)

        purchase.status = new_status
        if new_status == 'cancelled':
            purchase.cancelled_at = timezone.now()
            purchase.cancelled_reason = 'admin_deactivated'
        else:
            purchase.cancelled_at = None
            purchase.cancelled_reason = None
            # Reset expires_at to 30 days from now when reactivating
            from datetime import timedelta
            purchase.purchased_at = timezone.now()
            purchase.expires_at = timezone.now() + timedelta(days=30)
        purchase.save()

        return Response({
            'status': 'success',
            'message': f'{purchase.get_module_name_display()} for {purchase.company.name} has been {"activated" if new_status == "active" else "deactivated"}',
            'data': {
                'id': purchase.id,
                'module_name': purchase.module_name,
                'module_display_name': purchase.get_module_name_display(),
                'status': purchase.status,
                'company_name': purchase.company.name,
                'cancelled_at': purchase.cancelled_at.isoformat() if purchase.cancelled_at else None,
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to update agent status',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

