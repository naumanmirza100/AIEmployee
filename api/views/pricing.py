from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone

from core.models import PricingPlan, Subscription, Invoice
from api.serializers.pricing import PricingPlanSerializer, SubscriptionSerializer, InvoiceSerializer
from api.permissions import IsAdmin


@api_view(['GET'])
@permission_classes([AllowAny])
def list_pricing_plans(request):
    """Get pricing plans"""
    try:
        # Only show active plans
        plans = PricingPlan.objects.filter(is_active=True).order_by('price')
        
        # Admin can see all plans
        if request.user.is_authenticated and request.user.is_staff:
            plans = PricingPlan.objects.all().order_by('price')
        
        serializer = PricingPlanSerializer(plans, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch pricing plans',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_subscriptions(request):
    """Get user subscriptions"""
    try:
        user = request.user
        subscriptions = Subscription.objects.filter(user=user).order_by('-created_at')
        
        serializer = SubscriptionSerializer(subscriptions, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch subscriptions',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_subscription(request):
    """Create subscription"""
    try:
        user = request.user
        plan_id = request.data.get('plan_id')
        
        if not plan_id:
            return Response({
                'status': 'error',
                'message': 'plan_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        plan = get_object_or_404(PricingPlan, id=plan_id, is_active=True)
        
        # Check if user already has an active subscription
        active_subscription = Subscription.objects.filter(
            user=user,
            status='active'
        ).first()
        
        if active_subscription:
            return Response({
                'status': 'error',
                'message': 'User already has an active subscription'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create subscription
        subscription = Subscription.objects.create(
            user=user,
            plan=plan,
            status='active',
            started_at=timezone.now()
        )
        
        serializer = SubscriptionSerializer(subscription)
        
        return Response({
            'status': 'success',
            'message': 'Subscription created successfully',
            'data': serializer.data
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to create subscription',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_invoices(request):
    """Get user invoices"""
    try:
        user = request.user
        invoices = Invoice.objects.filter(user=user).order_by('-created_at')
        
        serializer = InvoiceSerializer(invoices, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch invoices',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

