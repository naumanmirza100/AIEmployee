from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from recruitment_agent.models import JobDescription, CareerApplication
from api.serializers.career import JobDescriptionSerializer, CareerApplicationSerializer
from api.permissions import IsCompanyUser


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_company_job(request):
    """Create job position (Company only)"""
    try:
        user = request.user
        
        # Check if user belongs to a company
        if not hasattr(user, 'profile') or not user.profile.company:
            return Response({
                'status': 'error',
                'message': 'User must be associated with a company'
            }, status=status.HTTP_403_FORBIDDEN)
        
        company = user.profile.company
        
        data = request.data.copy()
        data['company'] = company.id
        data['created_by'] = user.id
        data['is_active'] = True
        
        serializer = JobDescriptionSerializer(data=data)
        
        if serializer.is_valid():
            job = serializer.save(created_by=user, company=company)
            
            return Response({
                'status': 'success',
                'message': 'Job position created successfully',
                'data': JobDescriptionSerializer(job).data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'status': 'error',
            'message': 'Validation error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to create job position',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_company_jobs(request):
    """Get company's job positions (Company only)"""
    try:
        user = request.user
        
        # Check if user belongs to a company
        if not hasattr(user, 'profile') or not user.profile.company:
            return Response({
                'status': 'error',
                'message': 'User must be associated with a company'
            }, status=status.HTTP_403_FORBIDDEN)
        
        company = user.profile.company
        
        jobs = JobDescription.objects.filter(company=company).order_by('-created_at')
        
        # Filter by is_active if provided
        is_active = request.GET.get('is_active')
        if is_active is not None:
            is_active = is_active.lower() == 'true'
            jobs = jobs.filter(is_active=is_active)
        
        serializer = JobDescriptionSerializer(jobs, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch job positions',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_company_job(request, id):
    """Update job position (Company only)"""
    try:
        user = request.user
        
        # Check if user belongs to a company
        if not hasattr(user, 'profile') or not user.profile.company:
            return Response({
                'status': 'error',
                'message': 'User must be associated with a company'
            }, status=status.HTTP_403_FORBIDDEN)
        
        company = user.profile.company
        job = get_object_or_404(JobDescription, id=id, company=company)
        
        serializer = JobDescriptionSerializer(job, data=request.data, partial=True)
        
        if serializer.is_valid():
            job = serializer.save()
            
            return Response({
                'status': 'success',
                'message': 'Job position updated successfully',
                'data': JobDescriptionSerializer(job).data
            }, status=status.HTTP_200_OK)
        
        return Response({
            'status': 'error',
            'message': 'Validation error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to update job position',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_company_job_applications(request, jobId):
    """Get job applications for a specific job (Company only)"""
    try:
        user = request.user
        
        # Check if user belongs to a company
        if not hasattr(user, 'profile') or not user.profile.company:
            return Response({
                'status': 'error',
                'message': 'User must be associated with a company'
            }, status=status.HTTP_403_FORBIDDEN)
        
        company = user.profile.company
        job = get_object_or_404(JobDescription, id=jobId, company=company)
        
        applications = CareerApplication.objects.filter(position=job).order_by('-created_at')
        serializer = CareerApplicationSerializer(applications, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch applications',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_company_application_status(request, id):
    """Update application status (Company only)"""
    try:
        user = request.user
        
        # Check if user belongs to a company
        if not hasattr(user, 'profile') or not user.profile.company:
            return Response({
                'status': 'error',
                'message': 'User must be associated with a company'
            }, status=status.HTTP_403_FORBIDDEN)
        
        company = user.profile.company
        application = get_object_or_404(CareerApplication, id=id, company_id=company.id)
        
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

