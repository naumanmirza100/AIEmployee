from rest_framework import serializers
from core.models import ReferralCode, Referral, Credit


class ReferralCodeSerializer(serializers.ModelSerializer):
    """Serializer for Referral Code"""
    
    class Meta:
        model = ReferralCode
        fields = ['id', 'user', 'code', 'reward_type', 'reward_amount', 'max_uses',
                  'current_uses', 'expires_at', 'is_active', 'created_at']
        read_only_fields = ['id', 'code', 'current_uses', 'created_at']


class ReferralSerializer(serializers.ModelSerializer):
    """Serializer for Referral"""
    referral_code_code = serializers.CharField(source='referral_code.code', read_only=True)
    referrer_name = serializers.CharField(source='referrer.get_full_name', read_only=True)
    referred_user_name = serializers.CharField(source='referred_user.get_full_name', read_only=True)
    
    class Meta:
        model = Referral
        fields = ['id', 'referral_code', 'referral_code_code', 'referrer', 'referrer_name',
                  'referred_user', 'referred_user_name', 'status', 'reward_earned',
                  'reward_paid_at', 'created_at']
        read_only_fields = ['id', 'created_at']

