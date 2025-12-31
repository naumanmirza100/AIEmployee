from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
import secrets
import string

from core.models import ReferralCode, Referral, Credit
from api.serializers.referral import ReferralCodeSerializer, ReferralSerializer


def generate_referral_code():
    """Generate a unique referral code"""
    while True:
        code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        if not ReferralCode.objects.filter(code=code).exists():
            return code


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_my_referral_code(request):
    """Get my referral code"""
    try:
        user = request.user
        
        # Get or create referral code for user
        referral_code, created = ReferralCode.objects.get_or_create(
            user=user,
            defaults={
                'code': generate_referral_code(),
                'reward_type': 'credit',
                'reward_amount': 10.00,  # Default reward
                'is_active': True
            }
        )
        
        serializer = ReferralCodeSerializer(referral_code)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to get referral code',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def use_referral_code(request):
    """Use referral code"""
    try:
        user = request.user
        code = request.data.get('code')
        
        if not code:
            return Response({
                'status': 'error',
                'message': 'code is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            referral_code = ReferralCode.objects.get(code=code, is_active=True)
        except ReferralCode.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Invalid or inactive referral code'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if code is expired
        if referral_code.expires_at and referral_code.expires_at < timezone.now():
            return Response({
                'status': 'error',
                'message': 'Referral code has expired'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if user is trying to use their own code
        if referral_code.user == user:
            return Response({
                'status': 'error',
                'message': 'You cannot use your own referral code'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if code has reached max uses
        if referral_code.max_uses and referral_code.current_uses >= referral_code.max_uses:
            return Response({
                'status': 'error',
                'message': 'Referral code has reached maximum uses'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if user has already used this code
        existing_referral = Referral.objects.filter(
            referral_code=referral_code,
            referred_user=user
        ).first()
        
        if existing_referral:
            return Response({
                'status': 'error',
                'message': 'You have already used this referral code'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create referral
        referral = Referral.objects.create(
            referral_code=referral_code,
            referrer=referral_code.user,
            referred_user=user,
            status='pending'
        )
        
        # Increment current uses
        referral_code.current_uses += 1
        referral_code.save()
        
        # Apply reward if credit type
        if referral_code.reward_type == 'credit':
            credit, created = Credit.objects.get_or_create(user=user, defaults={'balance': 0})
            credit.balance += referral_code.reward_amount
            credit.save()
            
            # Mark referral as completed
            referral.status = 'completed'
            referral.reward_earned = referral_code.reward_amount
            referral.reward_paid_at = timezone.now()
            referral.save()
        
        serializer = ReferralSerializer(referral)
        
        return Response({
            'status': 'success',
            'message': 'Referral code applied successfully',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to use referral code',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_my_referrals(request):
    """Get my referrals"""
    try:
        user = request.user
        
        # Get referrals given by user (as referrer)
        referrals_given = Referral.objects.filter(referrer=user).order_by('-created_at')
        
        # Get referrals received by user (as referred_user)
        referrals_received = Referral.objects.filter(referred_user=user).order_by('-created_at')
        
        serializer_given = ReferralSerializer(referrals_given, many=True)
        serializer_received = ReferralSerializer(referrals_received, many=True)
        
        return Response({
            'status': 'success',
            'data': {
                'given': serializer_given.data,
                'received': serializer_received.data
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch referrals',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

