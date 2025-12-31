from rest_framework import serializers
from core.models import PricingPlan, Subscription, Invoice


class PricingPlanSerializer(serializers.ModelSerializer):
    """Serializer for Pricing Plan"""
    
    class Meta:
        model = PricingPlan
        fields = ['id', 'name', 'price', 'currency', 'description', 'features', 
                  'is_featured', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class SubscriptionSerializer(serializers.ModelSerializer):
    """Serializer for Subscription"""
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    plan_price = serializers.DecimalField(source='plan.price', max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = Subscription
        fields = ['id', 'user', 'plan', 'plan_name', 'plan_price', 'status', 
                  'started_at', 'expires_at', 'cancelled_at', 'auto_renew', 
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'started_at', 'created_at', 'updated_at']


class InvoiceSerializer(serializers.ModelSerializer):
    """Serializer for Invoice"""
    subscription_id = serializers.IntegerField(source='subscription.id', read_only=True, allow_null=True)
    
    class Meta:
        model = Invoice
        fields = ['id', 'user', 'subscription', 'subscription_id', 'invoice_number', 
                  'amount', 'currency', 'status', 'due_date', 'paid_at', 'created_at']
        read_only_fields = ['id', 'invoice_number', 'created_at']

