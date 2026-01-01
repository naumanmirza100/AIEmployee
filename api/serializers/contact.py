from rest_framework import serializers
from core.models import ContactMessage, Complaint


class ContactMessageSerializer(serializers.ModelSerializer):
    """Serializer for Contact Message"""
    
    class Meta:
        model = ContactMessage
        fields = ['id', 'full_name', 'email', 'phone', 'message', 'project_title', 
                  'attachment_path', 'status', 'created_at']
        read_only_fields = ['id', 'status', 'created_at']


class ComplaintSerializer(serializers.ModelSerializer):
    """Serializer for Complaint"""
    
    class Meta:
        model = Complaint
        fields = ['id', 'full_name', 'email', 'phone', 'subject', 'description', 
                  'related_project_id', 'status', 'created_at', 'resolved_at']
        read_only_fields = ['id', 'status', 'created_at', 'resolved_at']

