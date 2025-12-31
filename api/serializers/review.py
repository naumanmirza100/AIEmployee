from rest_framework import serializers
from core.models import Review


class ReviewSerializer(serializers.ModelSerializer):
    """Serializer for Review model"""
    
    class Meta:
        model = Review
        fields = ['id', 'client_name', 'company', 'quote', 'rating', 'project_type', 
                  'industry', 'featured', 'display_order', 'created_at']
        read_only_fields = ['id', 'created_at']

