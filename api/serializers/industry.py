from rest_framework import serializers
from core.models import Industry, IndustryChallenge


class IndustrySerializer(serializers.ModelSerializer):
    """Serializer for Industry model"""
    
    class Meta:
        model = Industry
        fields = ['id', 'name', 'slug', 'category', 'description', 'icon', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class IndustryChallengeSerializer(serializers.ModelSerializer):
    """Serializer for Industry Challenge model"""
    
    class Meta:
        model = IndustryChallenge
        fields = ['id', 'industry_slug', 'challenge_title', 'challenge_description', 'solution', 'created_at']
        read_only_fields = ['id', 'created_at']

