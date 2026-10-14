from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone

from recruitment_agent.models import JobDescription, CareerApplication
from api.serializers.career import JobDescriptionSerializer, CareerApplicationSerializer
from api.permissions import IsAdmin


@api_view(['GET'])
@permission_classes([AllowAny])
def list_job_positions(request):
    """List active job positions with search, company filter, type filter, and pagination."""
    try:
        jobs = JobDescription.objects.select_related('company').filter(is_active=True).order_by('-created_at')

        # Filter by company
        company_id = request.GET.get('company_id')
        if company_id:
            jobs = jobs.filter(company_id=company_id)

        # Full-text search across title / description / department / location
        search = request.GET.get('search', '').strip()
        if search:
            jobs = jobs.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(department__icontains=search) |
                Q(location__icontains=search)
            )

        # Filter by location
        location = request.GET.get('location', '').strip()
        if location:
            jobs = jobs.filter(location__icontains=location)

        # Filter by job type
        job_type = request.GET.get('type', '').strip()
        if job_type:
            jobs = jobs.filter(type=job_type)

        total_count = jobs.count()

        # Pagination
        try:
            page = max(1, int(request.GET.get('page', 1)))
            page_size = int(request.GET.get('page_size', 10))
            if page_size not in (5, 10, 25, 50):
                page_size = 10
        except (ValueError, TypeError):
            page = 1
            page_size = 10

        offset = (page - 1) * page_size
        jobs_page = jobs[offset: offset + page_size]

        serializer = JobDescriptionSerializer(jobs_page, many=True)

        # Build unique company list from ALL active jobs (for filter dropdown)
        companies = (
            JobDescription.objects
            .filter(is_active=True)
            .select_related('company')
            .values('company__id', 'company__name')
            .distinct()
            .order_by('company__name')
        )
        company_list = [
            {'id': c['company__id'], 'name': c['company__name']}
            for c in companies
            if c['company__id'] and c['company__name']
        ]

        total_pages = max(1, (total_count + page_size - 1) // page_size)

        return Response({
            'status': 'success',
            'data': serializer.data,
            'pagination': {
                'total_count': total_count,
                'page': page,
                'page_size': page_size,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1,
            },
            'companies': company_list,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch job positions',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdmin])
def list_career_applications(request):
    """Get all career applications (Admin only)"""
    try:
        applications = CareerApplication.objects.all().order_by('-created_at')
        
        # Filter by status if provided
        status_filter = request.GET.get('status')
        if status_filter:
            applications = applications.filter(status=status_filter)
        
        # Filter by company if provided
        company_id = request.GET.get('company_id')
        if company_id:
            applications = applications.filter(company_id=company_id)
        
        # Pagination
        page = int(request.GET.get('page', 1))
        limit = int(request.GET.get('limit', 20))
        
        total = applications.count()
        total_pages = (total + limit - 1) // limit if limit > 0 else 1
        
        # Apply pagination
        start = (page - 1) * limit
        end = start + limit
        paginated_applications = applications[start:end]
        
        serializer = CareerApplicationSerializer(paginated_applications, many=True)
        
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
            'message': 'Failed to fetch applications',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdmin])
def get_career_application(request, id):
    """Get career application by ID (Admin only)"""
    try:
        application = get_object_or_404(CareerApplication, id=id)
        serializer = CareerApplicationSerializer(application)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch application',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated, IsAdmin])
def update_career_application_status(request, id):
    """Update career application status (Admin only)"""
    try:
        application = get_object_or_404(CareerApplication, id=id)
        new_status = request.data.get('status')
        
        if not new_status:
            return Response({
                'status': 'error',
                'message': 'Status is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate status
        valid_statuses = ['pending', 'reviewing', 'shortlisted', 'accepted', 'rejected']
        if new_status not in valid_statuses:
            return Response({
                'status': 'error',
                'message': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        application.status = new_status
        application.save()
        
        serializer = CareerApplicationSerializer(application)
        
        return Response({
            'status': 'success',
            'message': 'Application status updated successfully',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to update application status',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

