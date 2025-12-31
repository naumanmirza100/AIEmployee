from rest_framework import serializers
from django.contrib.auth.models import User


# Note: Notification model may be in Frontline_agent app
# Creating a basic serializer structure that can be adapted
class NotificationSerializer(serializers.Serializer):
    """Serializer for Notification - adapt based on actual model location"""
    id = serializers.IntegerField(read_only=True)
    user = serializers.IntegerField(source='user.id', read_only=True)
    title = serializers.CharField()
    message = serializers.CharField()
    type = serializers.CharField()
    is_read = serializers.BooleanField()
    created_at = serializers.DateTimeField(read_only=True)

