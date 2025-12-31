from rest_framework import serializers
from core.models import AnalyticsEvent, PageView
import json


class AnalyticsEventSerializer(serializers.ModelSerializer):
    """Serializer for Analytics Event"""
    event_data = serializers.SerializerMethodField()
    
    class Meta:
        model = AnalyticsEvent
        fields = ['id', 'user', 'event_type', 'event_name', 'properties', 'event_data', 
                  'ip_address', 'user_agent', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def get_event_data(self, obj):
        """Parse properties JSON string to dict"""
        if obj.properties:
            try:
                return json.loads(obj.properties)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}
    


class PageViewSerializer(serializers.ModelSerializer):
    """Serializer for Page View"""
    
    class Meta:
        model = PageView
        fields = ['id', 'user', 'page_path', 'page_title', 'referrer', 'ip_address',
                  'user_agent', 'session_id', 'duration', 'created_at']
        read_only_fields = ['id', 'created_at']

