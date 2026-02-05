"""
Module Purchase API Views
"""
import logging
from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

import stripe

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core.models import CompanyUser, CompanyModulePurchase, Company

logger = logging.getLogger(__name__)

stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', None)

# Module pricing configuration (USD)
MODULE_PRICES = {
    'recruitment_agent': 99,
    'marketing_agent': 149,
    'project_manager_agent': 199,
}

MODULE_DISPLAY_NAMES = {
    'recruitment_agent': 'Recruitment Agent',
    'marketing_agent': 'Marketing Agent',
    'project_manager_agent': 'Project Manager Agent',
}


def _fulfill_purchase_from_metadata(metadata):
    """Create or update CompanyModulePurchase from Stripe metadata. Idempotent."""
    company_id = metadata.get('company_id')
    company_user_id = metadata.get('company_user_id')
    module_name = metadata.get('module_name')
    if not company_id or not module_name or module_name not in MODULE_PRICES:
        return False, 'invalid_metadata'
    try:
        company = Company.objects.get(pk=int(company_id))
    except (Company.DoesNotExist, ValueError, TypeError):
        return False, 'company_not_found'
    purchased_by = None
    if company_user_id:
        try:
            purchased_by = CompanyUser.objects.get(pk=int(company_user_id), company=company)
        except (CompanyUser.DoesNotExist, ValueError, TypeError):
            pass
    price = MODULE_PRICES[module_name]
    existing = CompanyModulePurchase.objects.filter(company=company, module_name=module_name).first()
    if existing:
        existing.status = 'active'
        existing.price_paid = price
        existing.purchased_by = purchased_by
        existing.purchased_at = timezone.now()
        existing.expires_at = None
        existing.cancelled_at = None
        existing.save()
        logger.info('Module %s re-activated for company %s (ID: %s)', module_name, company.name, company.id)
    else:
        CompanyModulePurchase.objects.create(
            company=company,
            module_name=module_name,
            status='active',
            price_paid=price,
            purchased_by=purchased_by,
            expires_at=None,
        )
        logger.info('Module %s purchased for company %s (ID: %s)', module_name, company.name, company.id)
    return True, module_name


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_purchased_modules(request):
    """Get list of modules purchased by the company"""
    try:
        company_user = request.user
        company = company_user.company
        
        purchases = CompanyModulePurchase.objects.filter(
            company=company,
            status='active'
        ).select_related('purchased_by')
        
        # Filter out expired purchases
        active_purchases = []
        for purchase in purchases:
            if purchase.is_active():
                active_purchases.append({
                    'module_name': purchase.module_name,
                    'module_display_name': purchase.get_module_name_display(),
                    'status': purchase.status,
                    'purchased_at': purchase.purchased_at.isoformat(),
                    'expires_at': purchase.expires_at.isoformat() if purchase.expires_at else None,
                    'price_paid': float(purchase.price_paid) if purchase.price_paid else None,
                })
        
        return Response({
            'status': 'success',
            'purchased_modules': active_purchases,
            'module_names': [p['module_name'] for p in active_purchases]
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error getting purchased modules: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'message': f'Failed to get purchased modules: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def check_module_access(request, module_name):
    """Check if company has access to a specific module"""
    try:
        company_user = request.user
        company = company_user.company
        
        try:
            purchase = CompanyModulePurchase.objects.get(
                company=company,
                module_name=module_name
            )
            
            has_access = purchase.is_active()
            
            return Response({
                'status': 'success',
                'has_access': has_access,
                'module_name': module_name,
                'module_display_name': purchase.get_module_name_display(),
                'purchase_status': purchase.status,
                'expires_at': purchase.expires_at.isoformat() if purchase.expires_at else None,
            }, status=status.HTTP_200_OK)
        
        except CompanyModulePurchase.DoesNotExist:
            return Response({
                'status': 'success',
                'has_access': False,
                'module_name': module_name,
                'module_display_name': MODULE_DISPLAY_NAMES.get(module_name, module_name),
            }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error checking module access: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'message': f'Failed to check module access: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_checkout_session(request):
    """Create a Stripe Checkout Session for module purchase. Returns checkout URL."""
    try:
        if not stripe.api_key or stripe.api_key == 'sk_test_placeholder':
            return Response({
                'status': 'error',
                'message': 'Stripe is not configured. Set STRIPE_SECRET_KEY in .env (use test keys for development).',
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        company_user = request.user
        company = company_user.company
        module_name = request.data.get('module_name')
        if not module_name:
            return Response({
                'status': 'error',
                'message': 'module_name is required',
            }, status=status.HTTP_400_BAD_REQUEST)
        if module_name not in MODULE_PRICES:
            return Response({
                'status': 'error',
                'message': f'Invalid module name. Valid: {", ".join(MODULE_PRICES.keys())}',
            }, status=status.HTTP_400_BAD_REQUEST)

        existing = CompanyModulePurchase.objects.filter(
            company=company, module_name=module_name
        ).first()
        if existing and existing.is_active():
            return Response({
                'status': 'error',
                'message': f'{MODULE_DISPLAY_NAMES[module_name]} is already purchased.',
            }, status=status.HTTP_400_BAD_REQUEST)

        price_usd = MODULE_PRICES[module_name]
        display_name = MODULE_DISPLAY_NAMES[module_name]
        frontend_url = (getattr(settings, 'FRONTEND_URL', None) or '').rstrip('/')

        session = stripe.checkout.Session.create(
            mode='payment',
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': price_usd * 100,
                    'product_data': {
                        'name': display_name,
                        'description': f'One-time purchase – {display_name} module',
                        'metadata': {'module_name': module_name},
                    },
                },
                'quantity': 1,
            }],
            metadata={
                'company_id': str(company.id),
                'company_user_id': str(company_user.id),
                'module_name': module_name,
            },
            success_url=f'{frontend_url}/module-purchase-success?session_id={{CHECKOUT_SESSION_ID}}',
            cancel_url=f'{frontend_url}/',
        )

        return Response({
            'status': 'success',
            'url': session.url,
            'session_id': session.id,
        }, status=status.HTTP_200_OK)
    except stripe.error.StripeError as e:
        logger.error('Stripe error creating checkout session: %s', str(e), exc_info=True)
        return Response({
            'status': 'error',
            'message': str(e.user_message) if getattr(e, 'user_message', None) else 'Payment setup failed.',
        }, status=status.HTTP_502_BAD_GATEWAY)
    except Exception as e:
        logger.error('Error creating checkout session: %s', str(e), exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Failed to create checkout session.',
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def purchase_module(request):
    """Legacy: direct purchase without Stripe. Prefer create_checkout_session + Stripe."""
    try:
        company_user = request.user
        company = company_user.company
        
        module_name = request.data.get('module_name')
        if not module_name:
            return Response({
                'status': 'error',
                'message': 'module_name is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if module_name not in MODULE_PRICES:
            return Response({
                'status': 'error',
                'message': f'Invalid module name. Valid options: {", ".join(MODULE_PRICES.keys())}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if already purchased
        existing_purchase = CompanyModulePurchase.objects.filter(
            company=company,
            module_name=module_name
        ).first()
        
        if existing_purchase and existing_purchase.is_active():
            return Response({
                'status': 'error',
                'message': f'Module {MODULE_DISPLAY_NAMES[module_name]} is already purchased and active'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get price
        price = MODULE_PRICES[module_name]
        
        # For now, we'll create the purchase directly
        # In production, you'd integrate with a payment gateway (Stripe, PayPal, etc.)
        # and only create purchase after successful payment
        
        # Create or update purchase
        if existing_purchase:
            existing_purchase.status = 'active'
            existing_purchase.price_paid = price
            existing_purchase.purchased_by = company_user
            existing_purchase.purchased_at = timezone.now()
            existing_purchase.expires_at = None  # Lifetime access for now
            existing_purchase.cancelled_at = None
            existing_purchase.save()
            purchase = existing_purchase
        else:
            purchase = CompanyModulePurchase.objects.create(
                company=company,
                module_name=module_name,
                status='active',
                price_paid=price,
                purchased_by=company_user,
                expires_at=None,  # Lifetime access for now (can be changed to subscription)
            )
        
        logger.info(f"Module {module_name} purchased by company {company.name} (ID: {company.id})")
        
        return Response({
            'status': 'success',
            'message': f'{MODULE_DISPLAY_NAMES[module_name]} purchased successfully',
            'purchase': {
                'module_name': purchase.module_name,
                'module_display_name': purchase.get_module_name_display(),
                'status': purchase.status,
                'price_paid': float(purchase.price_paid) if purchase.price_paid else None,
                'purchased_at': purchase.purchased_at.isoformat(),
            }
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        logger.error(f"Error purchasing module: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'message': f'Failed to purchase module: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
@require_http_methods(['POST'])
def stripe_webhook(request):
    """Handle Stripe webhooks. Verifies signature and creates CompanyModulePurchase on checkout.session.completed."""
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
    webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', None) or ''
    if not webhook_secret or webhook_secret == 'whsec_placeholder':
        logger.warning('STRIPE_WEBHOOK_SECRET not set; skipping webhook verification')
        return JsonResponse({'error': 'Webhook not configured'}, status=503)

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError as e:
        logger.warning('Stripe webhook invalid payload: %s', e)
        return JsonResponse({'error': 'Invalid payload'}, status=400)
    except stripe.error.SignatureVerificationError as e:
        logger.warning('Stripe webhook signature verification failed: %s', e)
        return JsonResponse({'error': 'Invalid signature'}, status=400)

    if event['type'] != 'checkout.session.completed':
        return JsonResponse({'received': True}, status=200)

    session = event['data']['object']
    metadata = session.get('metadata') or {}
    ok, _ = _fulfill_purchase_from_metadata(metadata)
    if not ok:
        logger.warning('Stripe webhook fulfill failed for metadata: %s', metadata)
    return JsonResponse({'received': True}, status=200)


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_session(request):
    """Verify Stripe Checkout session and fulfill module purchase. Public; called from success page."""
    session_id = (request.data or {}).get('session_id')
    if not session_id:
        return Response(
            {'status': 'error', 'message': 'session_id is required'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not stripe.api_key or stripe.api_key == 'sk_test_placeholder':
        return Response(
            {'status': 'error', 'message': 'Stripe is not configured.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.InvalidRequestError as e:
        logger.warning('Verify session invalid request: %s', e)
        return Response(
            {'status': 'error', 'message': 'Invalid session.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except stripe.error.StripeError as e:
        logger.error('Verify session Stripe error: %s', e, exc_info=True)
        return Response(
            {'status': 'error', 'message': 'Could not verify payment.'},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    if session.payment_status != 'paid':
        return Response(
            {'status': 'error', 'message': 'Payment not completed.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    raw = getattr(session, 'metadata', None) or {}
    metadata = dict(raw) if raw else {}
    ok, mod = _fulfill_purchase_from_metadata(metadata)
    if not ok:
        logger.warning('Verify session fulfill failed for session %s metadata: %s', session_id, metadata)
        return Response(
            {'status': 'error', 'message': 'Could not activate module.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response(
        {'status': 'success', 'message': 'Module activated.', 'module_name': mod},
        status=status.HTTP_200_OK,
    )


@api_view(['GET'])
def get_module_prices(request):
    """Get pricing information for all modules (public endpoint)"""
    try:
        prices = []
        for module_name, price in MODULE_PRICES.items():
            prices.append({
                'module_name': module_name,
                'module_display_name': MODULE_DISPLAY_NAMES[module_name],
                'price': price,
                'price_period': 'month',
            })
        
        return Response({
            'status': 'success',
            'modules': prices
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error getting module prices: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'message': f'Failed to get module prices: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
