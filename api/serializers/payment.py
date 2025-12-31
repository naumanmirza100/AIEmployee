from rest_framework import serializers
from core.models import Payment, PaymentMethod


class PaymentMethodSerializer(serializers.ModelSerializer):
    """Serializer for Payment Method"""
    
    class Meta:
        model = PaymentMethod
        fields = ['id', 'user', 'type', 'gateway_customer_id', 'gateway_payment_method_id',
                  'last_four', 'brand', 'expiry_month', 'expiry_year', 'is_default',
                  'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer for Payment"""
    invoice_id = serializers.IntegerField(source='invoice.id', read_only=True, allow_null=True)
    payment_method_id = serializers.IntegerField(source='payment_method.id', read_only=True, allow_null=True)
    
    class Meta:
        model = Payment
        fields = ['id', 'invoice', 'invoice_id', 'user', 'amount', 'currency', 
                  'payment_method', 'payment_method_id', 'payment_gateway', 
                  'transaction_id', 'status', 'processed_at', 'created_at']
        read_only_fields = ['id', 'transaction_id', 'status', 'processed_at', 'created_at']

