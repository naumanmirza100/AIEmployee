from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
import uuid

from core.models import Payment, PaymentMethod, Invoice
from api.serializers.payment import PaymentSerializer, PaymentMethodSerializer


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def process_payment(request):
    """Process payment"""
    try:
        user = request.user
        data = request.data
        
        invoice_id = data.get('invoice_id')
        amount = data.get('amount')
        payment_method_id = data.get('payment_method_id')
        payment_gateway = data.get('payment_gateway', 'stripe')  # Default gateway
        
        if not amount:
            return Response({
                'status': 'error',
                'message': 'amount is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        invoice = None
        if invoice_id:
            invoice = get_object_or_404(Invoice, id=invoice_id, user=user)
            amount = float(invoice.amount)
        
        payment_method = None
        if payment_method_id:
            payment_method = get_object_or_404(PaymentMethod, id=payment_method_id, user=user)
        
        # Generate transaction ID
        transaction_id = str(uuid.uuid4())
        
        # Create payment record
        payment = Payment.objects.create(
            invoice=invoice,
            user=user,
            amount=amount,
            currency=data.get('currency', 'GBP'),
            payment_method=payment_method,
            payment_gateway=payment_gateway,
            transaction_id=transaction_id,
            status='pending'
        )
        
        # TODO: Integrate with actual payment gateway (Stripe, PayPal, etc.)
        # For now, simulate successful payment
        payment.status = 'completed'
        payment.processed_at = timezone.now()
        payment.save()
        
        # Update invoice if exists
        if invoice:
            invoice.status = 'paid'
            invoice.paid_at = timezone.now()
            invoice.save()
        
        serializer = PaymentSerializer(payment)
        
        return Response({
            'status': 'success',
            'message': 'Payment processed successfully',
            'data': serializer.data
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to process payment',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_payments(request):
    """Get user payments"""
    try:
        user = request.user
        payments = Payment.objects.filter(user=user).order_by('-created_at')
        
        serializer = PaymentSerializer(payments, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch payments',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_payment_methods(request):
    """Get user payment methods"""
    try:
        user = request.user
        payment_methods = PaymentMethod.objects.filter(user=user, is_active=True).order_by('-is_default', '-created_at')
        
        serializer = PaymentMethodSerializer(payment_methods, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch payment methods',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_payment_method(request):
    """Add payment method"""
    try:
        user = request.user
        data = request.data
        
        # If setting as default, unset other defaults
        if data.get('is_default', False):
            PaymentMethod.objects.filter(user=user, is_default=True).update(is_default=False)
        
        serializer = PaymentMethodSerializer(data=data)
        
        if serializer.is_valid():
            payment_method = serializer.save(user=user)
            
            return Response({
                'status': 'success',
                'message': 'Payment method added successfully',
                'data': PaymentMethodSerializer(payment_method).data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'status': 'error',
            'message': 'Validation error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to add payment method',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

