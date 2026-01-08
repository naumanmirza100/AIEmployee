from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.shortcuts import get_object_or_404
import json

from core.models import AIPredictorSubmission
from api.serializers.ai_predictor import AIPredictorSubmissionSerializer
from api.permissions import IsAdmin


@api_view(['POST'])
@permission_classes([AllowAny])
def submit_ai_predictor(request):
    """Submit AI prediction request"""
    try:
        data = request.data.copy()
        
        # Handle project_data - convert dict to JSON string
        project_data = data.get('projectData') or data.get('project_data', {})
        if isinstance(project_data, dict):
            project_data_str = json.dumps(project_data)
        else:
            project_data_str = project_data or '{}'
        
        predictor_data = {
            'email': data.get('email', ''),
            'project_type': data.get('projectType') or data.get('project_type', ''),
            'project_data': project_data_str,
        }
        
        serializer = AIPredictorSubmissionSerializer(data=predictor_data)
        
        if serializer.is_valid():
            submission = serializer.save()
            
            # TODO: Integrate with actual AI prediction service
            # For now, return placeholder predictions
            predicted_cost = data.get('predictedCost') or data.get('predicted_cost')
            predicted_duration = data.get('predictedDuration') or data.get('predicted_duration')
            predicted_team_size = data.get('predictedTeamSize') or data.get('predicted_team_size')
            prediction_confidence = data.get('predictionConfidence') or data.get('prediction_confidence')
            
            # Update submission with predictions if provided
            if predicted_cost or predicted_duration or predicted_team_size:
                submission.predicted_cost = predicted_cost
                submission.predicted_duration = predicted_duration
                submission.predicted_team_size = predicted_team_size
                submission.prediction_confidence = prediction_confidence or 0.75
                submission.save()
            
            response_serializer = AIPredictorSubmissionSerializer(submission)
            
            return Response({
                'status': 'success',
                'message': 'AI prediction request submitted successfully',
                'data': response_serializer.data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'status': 'error',
            'message': 'Validation error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to submit prediction request',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdmin])
def list_ai_predictions(request):
    """Get all AI predictions (Admin/Owner only)"""
    try:
        predictions = AIPredictorSubmission.objects.all().order_by('-created_at')
        
        # Filter by project_type if provided
        project_type = request.GET.get('project_type')
        if project_type:
            predictions = predictions.filter(project_type=project_type)
        
        # Pagination
        page = int(request.GET.get('page', 1))
        limit = int(request.GET.get('limit', 20))
        
        total = predictions.count()
        total_pages = (total + limit - 1) // limit if limit > 0 else 1
        
        # Apply pagination
        start = (page - 1) * limit
        end = start + limit
        paginated_predictions = predictions[start:end]
        
        serializer = AIPredictorSubmissionSerializer(paginated_predictions, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'totalPages': total_pages
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch predictions',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdmin])
def get_ai_prediction(request, id):
    """Get AI prediction by ID (Admin/Owner only)"""
    try:
        prediction = get_object_or_404(AIPredictorSubmission, id=id)
        serializer = AIPredictorSubmissionSerializer(prediction)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch prediction',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

