from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.shortcuts import get_object_or_404
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from core.models import ContactMessage, Complaint
from api.serializers.contact import ContactMessageSerializer, ComplaintSerializer
from api.permissions import IsAdmin


@api_view(['POST'])
@permission_classes([AllowAny])
def submit_contact_form(request):
    """Submit contact form with optional file upload"""
    try:
        data = request.data.copy()
        
        # Handle file upload if present
        attachment_path = None
        if 'file' in request.FILES:
            uploaded_file = request.FILES['file']
            # Save file to media/uploads/contact/
            file_path = f'contact/{uploaded_file.name}'
            saved_path = default_storage.save(file_path, ContentFile(uploaded_file.read()))
            attachment_path = saved_path
        
        # Map field names (handle both snake_case and camelCase)
        contact_data = {
            'full_name': data.get('fullName') or data.get('full_name', ''),
            'email': data.get('email', ''),
            'phone': data.get('phone'),
            'message': data.get('message') or data.get('description', ''),
            'project_title': data.get('projectTitle') or data.get('project_title'),
            'attachment_path': attachment_path,
            'status': 'new'
        }
        
        serializer = ContactMessageSerializer(data=contact_data)
        
        if serializer.is_valid():
            contact = serializer.save()
            
            return Response({
                'status': 'success',
                'message': 'Contact form submitted successfully',
                'data': {
                    'id': contact.id,
                    'message': 'We will get back to you soon',
                    'attachmentPath': contact.attachment_path
                }
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'status': 'error',
            'message': 'Validation error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to submit contact form',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def submit_complaint(request):
    """Submit complaint"""
    try:
        data = request.data.copy()
        
        complaint_data = {
            'full_name': data.get('fullName') or data.get('full_name', ''),
            'email': data.get('email', ''),
            'phone': data.get('phone'),
            'subject': data.get('subject', ''),
            'description': data.get('description') or data.get('message', ''),
            'related_project_id': data.get('relatedProjectId') or data.get('related_project_id'),
            'status': 'pending'
        }
        
        serializer = ComplaintSerializer(data=complaint_data)
        
        if serializer.is_valid():
            complaint = serializer.save()
            
            return Response({
                'status': 'success',
                'message': 'Complaint submitted successfully',
                'data': {
                    'id': complaint.id,
                    'message': 'Your complaint has been received and will be reviewed'
                }
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'status': 'error',
            'message': 'Validation error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to submit complaint',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdmin])
def list_contact_messages(request):
    """Get all contact messages (Admin only)"""
    try:
        # Filter by status if provided
        status_filter = request.GET.get('status')
        query = ContactMessage.objects.all()
        
        if status_filter:
            query = query.filter(status=status_filter)
        
        query = query.order_by('-created_at')
        
        serializer = ContactMessageSerializer(query, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch contact messages',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdmin])
def get_contact_message(request, id):
    """Get contact message by ID (Admin only)"""
    try:
        message = get_object_or_404(ContactMessage, id=id)
        serializer = ContactMessageSerializer(message)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch contact message',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated, IsAdmin])
def update_contact_message_status(request, id):
    """Update contact message status (Admin only)"""
    try:
        message = get_object_or_404(ContactMessage, id=id)
        new_status = request.data.get('status')
        
        if not new_status:
            return Response({
                'status': 'error',
                'message': 'Status is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate status
        valid_statuses = ['new', 'read', 'replied']
        if new_status not in valid_statuses:
            return Response({
                'status': 'error',
                'message': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        message.status = new_status
        message.save()
        
        serializer = ContactMessageSerializer(message)
        
        return Response({
            'status': 'success',
            'message': 'Contact message status updated successfully',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to update contact message status',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

