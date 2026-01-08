from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.shortcuts import get_object_or_404
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils import timezone
import secrets
import string

from recruitment_agent.models import JobDescription, CareerApplication
from api.serializers.career import JobDescriptionSerializer, CareerApplicationSerializer
from api.permissions import IsAdmin


def generate_application_token():
    """Generate a unique application token"""
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64))


@api_view(['GET'])
@permission_classes([AllowAny])
def list_job_positions(request):
    """List job positions"""
    try:
        jobs = JobDescription.objects.filter(is_active=True).order_by('-created_at')
        
        # Filter by company if provided
        company_id = request.GET.get('company_id')
        if company_id:
            jobs = jobs.filter(company_id=company_id)
        
        # Filter by location if provided
        location = request.GET.get('location')
        if location:
            jobs = jobs.filter(location__icontains=location)
        
        # Filter by type if provided
        job_type = request.GET.get('type')
        if job_type:
            jobs = jobs.filter(type=job_type)
        
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


@api_view(['POST'])
@permission_classes([AllowAny])
def submit_career_application(request):
    """Submit career application with optional resume file upload"""
    try:
        data = request.data.copy()
        
        # Handle file upload if present
        resume_path = None
        if 'file' in request.FILES or 'resume' in request.FILES:
            uploaded_file = request.FILES.get('file') or request.FILES.get('resume')
            # Save file to media/uploads/careers/
            file_path = f'careers/{uploaded_file.name}'
            saved_path = default_storage.save(file_path, ContentFile(uploaded_file.read()))
            resume_path = saved_path
        
        # Map field names (handle both camelCase and snake_case)
        position_id = data.get('positionId') or data.get('position_id')
        applicant_name = data.get('applicantName') or data.get('applicant_name') or data.get('name')
        email = data.get('email')
        phone = data.get('phone')
        cover_letter = data.get('coverLetter') or data.get('cover_letter') or data.get('message')
        
        if not email:
            return Response({
                'status': 'error',
                'message': 'Email is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get position if provided and determine position title
        position = None
        final_position_title = position_title if position_title else 'General Application'
        
        if position_id:
            try:
                position = JobDescription.objects.get(id=position_id)
                final_position_title = position.title
            except JobDescription.DoesNotExist:
                return Response({
                    'status': 'error',
                    'message': 'Invalid position ID'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Generate application token
        application_token = generate_application_token()
        
        # Get company if position is provided
        company = position.company if position else None
        
        # Create application
        application = CareerApplication.objects.create(
            position=position,
            position_title=final_position_title,
            applicant_name=applicant_name,
            email=email,
            phone=phone,
            cover_letter=cover_letter,
            resume_path=resume_path,
            company=company,
            application_token=application_token,
            status='pending'
        )
        
        serializer = CareerApplicationSerializer(application)
        
        return Response({
            'status': 'success',
            'message': 'Application submitted successfully',
            'data': {
                **serializer.data,
                'resumePath': resume_path,
                'statusCheckLink': f'/api/applicant/status?token={application_token}'
            }
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to submit application',
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

