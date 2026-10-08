"""
Company User Tasks API Views
For company users to view all tasks of the company's employees
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core.models import Task
from core.tenancy import members_of
from api.serializers.user_tasks import TaskSerializer


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_all_users_tasks(request):
    """
    Get all tasks of the company's employees
    GET /api/company/users/tasks
    """
    try:
        # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
        company_user = request.user
        
        # The company's employees. It used to be only the ones this login had
        # created, so a second dashboard login saw an empty list.
        created_user_ids = list(
            members_of(getattr(company_user, 'company', None), company_user=company_user)
            .values_list('id', flat=True))
        
        # If no users created, return empty list
        if not created_user_ids:
            return Response({
                'status': 'success',
                'data': []
            }, status=status.HTTP_200_OK)
        
        # Get all tasks assigned to these users
        tasks = Task.objects.filter(
            assignee_id__in=created_user_ids
        ).select_related('project', 'assignee').order_by('-created_at')
        
        # Filter by status if provided
        status_filter = request.GET.get('status')
        if status_filter:
            tasks = tasks.filter(status=status_filter)
        
        # Filter by user if provided
        user_id = request.GET.get('user_id')
        if user_id:
            tasks = tasks.filter(assignee_id=user_id)
        
        # Filter by project if provided
        project_id = request.GET.get('project_id')
        if project_id:
            tasks = tasks.filter(project_id=project_id)
        
        # Pagination
        page = int(request.GET.get('page', 1))
        limit = int(request.GET.get('limit', 20))
        
        total = tasks.count()
        total_pages = (total + limit - 1) // limit if limit > 0 else 1
        
        # Apply pagination
        start = (page - 1) * limit
        end = start + limit
        paginated_tasks = tasks[start:end]
        
        serializer = TaskSerializer(paginated_tasks, many=True)
        
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
        import traceback
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_all_users_tasks: {str(e)}")
        logger.error(traceback.format_exc())
        return Response({
            'status': 'error',
            'message': 'Failed to fetch tasks',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

