from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
import json

from core.models import QuizResponse
from api.serializers.quiz import QuizResponseSerializer


@api_view(['POST'])
@permission_classes([AllowAny])
def submit_quiz_response(request):
    """Submit quiz response"""
    try:
        data = request.data.copy()
        
        quiz_data = {
            'email': data.get('email', ''),
            'name': data.get('name'),
            'location': data.get('location'),
            'industry': data.get('industry'),
            'goal': data.get('goal'),
            'project_type': data.get('projectType') or data.get('project_type'),
            'responses': data.get('responses', {}),
        }
        
        # Convert responses dict to JSON string
        if isinstance(quiz_data['responses'], dict):
            quiz_data['responses'] = json.dumps(quiz_data['responses'])
        
        serializer = QuizResponseSerializer(data=quiz_data)
        
        if serializer.is_valid():
            quiz_response = serializer.save()
            
            # Parse responses for return
            responses_dict = {}
            if quiz_response.responses:
                try:
                    responses_dict = json.loads(quiz_response.responses)
                except (json.JSONDecodeError, TypeError):
                    pass
            
            return Response({
                'status': 'success',
                'message': 'Quiz response submitted successfully',
                'data': {
                    'id': quiz_response.id,
                    'email': quiz_response.email,
                    'projectType': quiz_response.project_type,
                    'responses': responses_dict
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
            'message': 'Failed to submit quiz response',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

