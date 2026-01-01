from rest_framework import serializers
from core.models import Consultation


class ConsultationSerializer(serializers.ModelSerializer):
    """Serializer for Consultation model"""
    
    class Meta:
        model = Consultation
        fields = ['id', 'name', 'email', 'phone', 'company', 'industry', 'project_type', 
                  'project_description', 'budget_range', 'timeline', 'status', 'scheduled_at', 
                  'notes', 'created_at']
        read_only_fields = ['id', 'status', 'created_at']

