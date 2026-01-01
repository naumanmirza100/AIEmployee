from rest_framework import serializers
from core.models import ChatbotConversation, ChatbotMessage


class ChatbotConversationSerializer(serializers.ModelSerializer):
    """Serializer for Chatbot Conversation"""
    
    class Meta:
        model = ChatbotConversation
        fields = ['id', 'user', 'status', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class ChatbotMessageSerializer(serializers.ModelSerializer):
    """Serializer for Chatbot Message"""
    conversation_id = serializers.IntegerField(source='conversation.id', read_only=True)
    
    class Meta:
        model = ChatbotMessage
        fields = ['id', 'conversation', 'conversation_id', 'sender_type', 'message',
                  'created_at']
        read_only_fields = ['id', 'created_at']

