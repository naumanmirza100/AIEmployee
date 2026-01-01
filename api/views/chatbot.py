from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone

from core.models import ChatbotConversation, ChatbotMessage
from api.serializers.chatbot import ChatbotConversationSerializer, ChatbotMessageSerializer


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_conversation(request):
    """Create chatbot conversation"""
    try:
        import uuid
        session_id = str(uuid.uuid4())
        
        conversation = ChatbotConversation.objects.create(
            user=request.user,
            session_id=session_id,
            status='active'
        )
        
        serializer = ChatbotConversationSerializer(conversation)
        
        return Response({
            'status': 'success',
            'message': 'Conversation created successfully',
            'data': serializer.data
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to create conversation',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_chatbot_message(request):
    """Send chatbot message"""
    try:
        data = request.data
        conversation_id = data.get('conversationId') or data.get('conversation_id')
        message = data.get('message', '')
        
        if not message:
            return Response({
                'status': 'error',
                'message': 'Message is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get or create conversation
        if conversation_id:
            conversation = get_object_or_404(ChatbotConversation, id=conversation_id, user=request.user)
        else:
            # Create new conversation
            conversation = ChatbotConversation.objects.create(
                user=request.user,
                status='active'
            )
        
        # Create user message
        user_message = ChatbotMessage.objects.create(
            conversation=conversation,
            sender_type='user',
            message=message
        )
        
        # TODO: Integrate with actual chatbot service to generate bot response
        # For now, return a placeholder bot response
        bot_response_text = "Thank you for your message. Our chatbot service is being configured."
        
        bot_message = ChatbotMessage.objects.create(
            conversation=conversation,
            sender_type='bot',
            message=bot_response_text
        )
        
        return Response({
            'status': 'success',
            'message': 'Message sent successfully',
            'data': {
                'conversationId': conversation.id,
                'userMessage': ChatbotMessageSerializer(user_message).data,
                'botMessage': ChatbotMessageSerializer(bot_message).data
            }
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to send message',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_conversation_messages(request, id):
    """Get conversation messages"""
    try:
        conversation = get_object_or_404(ChatbotConversation, id=id, user=request.user)
        
        messages = ChatbotMessage.objects.filter(conversation=conversation).order_by('created_at')
        serializer = ChatbotMessageSerializer(messages, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch messages',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

