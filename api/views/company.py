from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.conf import settings as djsettings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import models
from django.db.models import Count
from datetime import timedelta
import logging
import secrets
import string

from core.models import Company, CompanyRegistrationToken, CompanyModulePurchase
from api.serializers.company import CompanySerializer, CompanyRegistrationTokenSerializer
from api.permissions import IsAdmin

logger = logging.getLogger(__name__)


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
        # Auto-expire: update DB status for legacy purchases past their expires_at
        # (Stripe subscriptions are managed via webhooks, not local expiry)
        now = timezone.now()
        CompanyModulePurchase.objects.filter(
            models.Q(stripe_subscription_id__isnull=True) | models.Q(is_complimentary=True),
            status='active',
            expires_at__isnull=False, expires_at__lt=now,
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
            # Determine effective status using the model's is_active() which
            # handles Stripe, complimentary, and legacy expiry correctly.
            is_active = purchase.is_active()
            is_expired = purchase.status != 'cancelled' and not is_active
            effective_status = purchase.status
            if is_expired and effective_status != 'expired':
                effective_status = 'expired'

            # Compute time remaining or time since expired — prefer Stripe
            # current_period_end over legacy expires_at.
            effective_expiry = None
            if purchase.stripe_subscription_id and purchase.current_period_end:
                effective_expiry = purchase.current_period_end
            elif purchase.expires_at:
                effective_expiry = purchase.expires_at

            time_remaining = None
            time_ended_ago = None
            if effective_expiry:
                if is_active:
                    diff = effective_expiry - now
                    if diff.total_seconds() > 0:
                        days = diff.days
                        hours = diff.seconds // 3600
                        time_remaining = f"{days}d {hours}h remaining" if days > 0 else f"{hours}h remaining"
                elif is_expired:
                    ended = now - effective_expiry
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
                'is_complimentary': purchase.is_complimentary,
                'deactivated_by_admin': purchase.cancelled_reason == 'admin_deactivated',
                'price_paid': float(purchase.price_paid) if purchase.price_paid else None,
                'purchased_by_name': purchase.purchased_by.full_name if purchase.purchased_by else None,
                'purchased_by_email': purchase.purchased_by.email if purchase.purchased_by else None,
                'purchased_at': purchase.purchased_at.isoformat() if purchase.purchased_at else None,
                'expires_at': purchase.expires_at.isoformat() if purchase.expires_at else None,
                'cancelled_at': purchase.cancelled_at.isoformat() if purchase.cancelled_at else None,
                'cancelled_reason': purchase.cancelled_reason,
                'history_kept': purchase.history_kept,
                'time_remaining': time_remaining,
                'time_ended_ago': time_ended_ago,
                'active_label': active_label,
                'created_at': purchase.created_at.isoformat() if purchase.created_at else None,
                'updated_at': purchase.updated_at.isoformat() if purchase.updated_at else None,
                # Stripe subscription fields
                'stripe_subscription_id': purchase.stripe_subscription_id,
                'current_period_end': purchase.current_period_end.isoformat() if purchase.current_period_end else None,
                'cancel_at_period_end': purchase.cancel_at_period_end,
                'billing_interval': purchase.billing_interval,
            })

        # Summary stats — use is_active() which handles both Stripe and legacy expiry
        all_purchases_qs = CompanyModulePurchase.objects.all()
        active_count = 0
        expired_count = 0
        cancelled_count = 0
        for p in all_purchases_qs:
            if p.status == 'cancelled':
                cancelled_count += 1
            elif p.is_active():
                active_count += 1
            else:
                expired_count += 1
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
    """Toggle AI agent module status between active and cancelled (Admin only).

    Deactivating a company that is on a live Stripe subscription ALSO cancels
    that subscription immediately — access and billing stop together, so we never
    keep charging someone we just cut off.

    Activating grants complimentary access, which bypasses the Stripe lifecycle
    and therefore must carry an expiry date (`complimentary_days`, default 30).
    Open-ended free access is too easy to grant by accident and never notice.
    """
    try:
        purchase = get_object_or_404(CompanyModulePurchase, id=purchaseId)

        new_status = request.data.get('status')
        if new_status not in ('active', 'cancelled'):
            return Response({
                'status': 'error',
                'message': 'Status must be either "active" or "cancelled"'
            }, status=status.HTTP_400_BAD_REQUEST)

        keep_history = request.data.get('keep_history', True)
        if isinstance(keep_history, str):
            keep_history = keep_history.lower() not in ('false', '0', 'no')

        # How long complimentary access lasts. Bounded so a typo can't grant a
        # decade of free access; 0/None is rejected rather than meaning "forever".
        complimentary_days = request.data.get('complimentary_days', 30)
        if new_status == 'active':
            try:
                complimentary_days = int(complimentary_days)
            except (TypeError, ValueError):
                return Response({
                    'status': 'error',
                    'message': 'complimentary_days must be a whole number of days.',
                }, status=status.HTTP_400_BAD_REQUEST)
            if not (1 <= complimentary_days <= 3650):
                return Response({
                    'status': 'error',
                    'message': 'complimentary_days must be between 1 and 3650.',
                }, status=status.HTTP_400_BAD_REQUEST)

        # Cancel the live Stripe subscription BEFORE touching local state: if
        # Stripe rejects it we must not end up with access revoked locally while
        # the customer's card keeps getting charged.
        stripe_cancelled = False
        if new_status == 'cancelled' and purchase.stripe_subscription_id:
            import stripe as _stripe
            _stripe.api_key = getattr(djsettings, 'STRIPE_SECRET_KEY', None)
            try:
                _stripe.Subscription.cancel(purchase.stripe_subscription_id)
                stripe_cancelled = True
            except _stripe.error.InvalidRequestError as exc:
                # Already gone at Stripe's end — nothing left to cancel, proceed.
                logger.warning(
                    'Admin deactivate: Stripe subscription %s not cancellable (%s); '
                    'continuing with local deactivation.',
                    purchase.stripe_subscription_id, exc,
                )
            except _stripe.error.StripeError as exc:
                logger.error(
                    'Admin deactivate: failed to cancel Stripe subscription %s: %s',
                    purchase.stripe_subscription_id, exc, exc_info=True,
                )
                return Response({
                    'status': 'error',
                    'message': (
                        'Could not cancel the Stripe subscription, so access was left '
                        'unchanged to avoid billing a company with no access. '
                        'Please retry or cancel it in the Stripe dashboard.'
                    ),
                }, status=status.HTTP_502_BAD_GATEWAY)

        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            purchase.status = new_status
            if new_status == 'cancelled':
                purchase.cancelled_at = timezone.now()
                purchase.cancelled_reason = 'admin_deactivated'
                purchase.history_kept = keep_history
                purchase.is_complimentary = False
                purchase.save()

                if not keep_history:
                    from core.models import AgentTokenQuota, CompanyAPIKey, KeyRequest
                    company = purchase.company
                    agent_name = purchase.module_name
                    KeyRequest.objects.filter(company=company, agent_name=agent_name).delete()
                    CompanyAPIKey.objects.filter(company=company, agent_name=agent_name).delete()
                    AgentTokenQuota.objects.filter(company=company, agent_name=agent_name).delete()
            else:
                # Admin-granted complimentary access — not tied to Stripe.
                purchase.cancelled_at = None
                purchase.cancelled_reason = None
                purchase.history_kept = None
                purchase.is_complimentary = True
                purchase.purchased_at = timezone.now()
                # Complimentary access is time-boxed. `is_active()` short-circuits
                # on is_complimentary, so this date is enforced by the same hourly
                # sweep that expires legacy purchases (which skips Stripe rows —
                # and a complimentary row has no subscription id by definition).
                purchase.expires_at = timezone.now() + timedelta(days=complimentary_days)
                # Stripe fields are cleared because this row is no longer billed —
                # but the subscription id is DELIBERATELY preserved, since wiping it
                # orphans a live subscription: every webhook handler looks the row up
                # by that id, so clearing it means renewals keep charging the customer
                # with nothing left to reconcile them against.
                purchase.current_period_start = None
                purchase.current_period_end = None
                purchase.cancel_at_period_end = False
                purchase.billing_interval = None
                purchase.save()

                # Quota handling
                from core.models import AgentTokenQuota, AdminPricingConfig, DEFAULT_FREE_TOKENS
                company = purchase.company
                agent_name = purchase.module_name
                try:
                    cfg = AdminPricingConfig.objects.get(agent_name=agent_name)
                    free_tokens = cfg.free_tokens_on_purchase
                except AdminPricingConfig.DoesNotExist:
                    free_tokens = DEFAULT_FREE_TOKENS

                quota_obj, created = AgentTokenQuota.objects.get_or_create(
                    company=company,
                    agent_name=agent_name,
                    defaults={'included_tokens': free_tokens},
                )
                if not created and quota_obj.preferred_pool == 'managed':
                    from core.models import CompanyAPIKey as _CAK
                    has_managed = _CAK.objects.filter(
                        company=company, agent_name=agent_name, mode='managed', status='active'
                    ).exists()
                    if not has_managed:
                        AgentTokenQuota.objects.filter(pk=quota_obj.pk).update(preferred_pool=None)

        return Response({
            'status': 'success',
            'message': f'{purchase.get_module_name_display()} for {purchase.company.name} has been {"activated (complimentary)" if new_status == "active" else "deactivated"}',
            'data': {
                'id': purchase.id,
                'module_name': purchase.module_name,
                'module_display_name': purchase.get_module_name_display(),
                'status': purchase.status,
                'is_complimentary': purchase.is_complimentary,
                'company_name': purchase.company.name,
                'cancelled_at': purchase.cancelled_at.isoformat() if purchase.cancelled_at else None,
                'history_kept': purchase.history_kept,
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to update agent status',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

