"""
Module Purchase API Views
"""
import logging
from datetime import datetime, timedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core.models import CompanyUser, CompanyModulePurchase, Company

logger = logging.getLogger(__name__)

# Module pricing configuration
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
def purchase_module(request):
    """Purchase a module for the company"""
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
