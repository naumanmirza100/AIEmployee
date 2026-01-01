from rest_framework import serializers
from recruitment_agent.models import JobDescription, CareerApplication


class JobDescriptionSerializer(serializers.ModelSerializer):
    """Serializer for Job Description"""
    company_name = serializers.CharField(source='company.name', read_only=True, allow_null=True)
    company_id = serializers.IntegerField(source='company.id', read_only=True, allow_null=True)
    
    class Meta:
        model = JobDescription
        fields = ['id', 'title', 'description', 'location', 'department', 'type',
                  'requirements', 'keywords_json', 'company', 'company_id', 'company_name',
                  'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'keywords_json', 'created_at', 'updated_at']


class CareerApplicationSerializer(serializers.ModelSerializer):
    """Serializer for Career Application"""
    position_id = serializers.IntegerField(source='position.id', read_only=True, allow_null=True)
    company_id = serializers.IntegerField(source='company.id', read_only=True, allow_null=True)
    
    class Meta:
        model = CareerApplication
        fields = ['id', 'position', 'position_id', 'position_title', 'applicant_name',
                  'email', 'phone', 'cover_letter', 'resume_path', 'company', 'company_id',
                  'application_token', 'status', 'created_at']
        read_only_fields = ['id', 'application_token', 'created_at']

