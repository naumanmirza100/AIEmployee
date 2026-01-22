import json
import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404

from recruitment_agent.models import JobDescription, CareerApplication
from api.serializers.career import JobDescriptionSerializer, CareerApplicationSerializer
from api.permissions import IsCompanyUser, IsCompanyUserOnly
from api.authentication import CompanyUserTokenAuthentication
from core.models import CompanyUser, Company
from api.views.recruitment_agent import get_agents

logger = logging.getLogger(__name__)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_company_job(request):
    """Create job position (Company only)"""
    try:
        # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
        company_user = request.user
        company = company_user.company
        
        data = request.data.copy()
        data['company'] = company.id
        data['is_active'] = True
        
        # Handle parse_keywords - can be boolean True/False or string "true"/"false"
        # Default to True to match Django views.py behavior
        parse_keywords_val = data.get('parse_keywords', True)
        if isinstance(parse_keywords_val, str):
            parse_keywords = parse_keywords_val.lower() in ('true', '1', 'yes')
        else:
            parse_keywords = bool(parse_keywords_val)
        
        serializer = JobDescriptionSerializer(data=data)
        
        if serializer.is_valid():
            # Save with company and company_user
            job = serializer.save(company=company, company_user=company_user)
            
            # Parse keywords if requested (defaults to True, same as Django views.py)
            keywords_json = None
            if parse_keywords and job.description:
                try:
                    agents = get_agents()
                    job_desc_agent = agents['job_desc_agent']
                    log_service = agents['log_service']
                    
                    logger.info(f"Parsing keywords for company job: {job.title}")
                    parsed = job_desc_agent.parse_text(job.description)
                    keywords_json = json.dumps(parsed)
                    logger.info(f"Keywords parsed successfully. Keywords count: {len(parsed.get('keywords', []))}")
                    
                    # Update job with keywords
                    job.keywords_json = keywords_json
                    job.save(update_fields=['keywords_json'])
                    
                except Exception as exc:
                    logger.error(f"Error parsing keywords: {str(exc)}", exc_info=True)
                    log_service.log_error("job_description_keyword_parsing_failed", {"error": str(exc), "title": job.title})
                    # Continue without keywords if parsing fails
            
            # Verify keywords were saved
            keywords_saved = job.keywords_json is not None
            logger.info(f"Company job created. ID: {job.id}, Title: {job.title}, Keywords saved: {keywords_saved}")
            
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
        logger.error(f"Error creating company job: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Failed to create job position',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_company_jobs(request):
    """Get company's job positions (Company only)"""
    try:
        # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
        company_user = request.user
        company = company_user.company
        
        # Filter jobs by company_user - each user only sees their own jobs
        jobs = JobDescription.objects.filter(company_user=company_user).order_by('-created_at')
        
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
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_company_job(request, id):
    """Update job position (Company only)"""
    try:
        # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
        company_user = request.user
        company = company_user.company
        # Users can only update their own jobs
        job = get_object_or_404(JobDescription, id=id, company_user=company_user)
        
        # Check if description changed and if we should parse keywords
        description_changed = 'description' in request.data
        old_description = job.description
        
        # Handle parse_keywords - can be boolean True/False or string "true"/"false"
        parse_keywords_val = request.data.get('parse_keywords', False)
        if isinstance(parse_keywords_val, str):
            parse_keywords = parse_keywords_val.lower() in ('true', '1', 'yes')
        else:
            parse_keywords = bool(parse_keywords_val)
        
        serializer = JobDescriptionSerializer(job, data=request.data, partial=True)
        
        if serializer.is_valid():
            job = serializer.save()
            
            # Parse keywords if requested and description was updated
            if parse_keywords and description_changed and job.description:
                try:
                    agents = get_agents()
                    job_desc_agent = agents['job_desc_agent']
                    log_service = agents['log_service']
                    
                    logger.info(f"Parsing keywords for company job update: {job.id}")
                    parsed = job_desc_agent.parse_text(job.description)
                    keywords_json = json.dumps(parsed)
                    logger.info(f"Keywords parsed successfully. Keywords count: {len(parsed.get('keywords', []))}")
                    
                    # Update job with keywords
                    job.keywords_json = keywords_json
                    job.save(update_fields=['keywords_json'])
                    
                except Exception as exc:
                    logger.error(f"Error parsing keywords: {str(exc)}", exc_info=True)
                    log_service.log_error("job_description_keyword_parsing_failed", {"error": str(exc), "job_id": job.id})
                    # Continue without updating keywords if parsing fails
            
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
        logger.error(f"Error updating company job: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Failed to update job position',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_company_job_applications(request, jobId):
    """Get job applications for a specific job (Company only)"""
    try:
        # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
        company_user = request.user
        company = company_user.company
        # Users can only see applications for their own jobs
        job = get_object_or_404(JobDescription, id=jobId, company_user=company_user)
        
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
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_company_application_status(request, id):
    """Update application status (Company only)"""
    try:
        # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
        company_user = request.user
        company = company_user.company
        # Users can only update applications for their own jobs
        application = get_object_or_404(CareerApplication, id=id, position__company_user=company_user)
        
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

