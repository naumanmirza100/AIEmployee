from rest_framework import serializers
from recruitment_agent.models import JobDescription, CareerApplication


def _validate_meaningful_text(value, field_name):
    """Validate that a field contains at least 2 alphanumeric characters."""
    text = (value or '').strip()
    if not text:
        raise serializers.ValidationError(f'{field_name} is required.')
    alnum_count = sum(1 for c in text if c.isalnum())
    if alnum_count < 2:
        raise serializers.ValidationError(
            f'{field_name} must contain at least 2 alphanumeric characters.'
        )
    return text


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

    def validate_title(self, value):
        return _validate_meaningful_text(value, 'Job title')

    def validate_description(self, value):
        text = _validate_meaningful_text(value, 'Description')
        alnum_count = sum(1 for c in text if c.isalnum())
        if alnum_count < 20:
            raise serializers.ValidationError(
                'Description must contain at least 20 alphanumeric characters. Please provide a meaningful description.'
            )
        return text

    def validate_requirements(self, value):
        if value:
            text = value.strip()
            alnum_count = sum(1 for c in text if c.isalnum())
            if alnum_count < 10:
                raise serializers.ValidationError(
                    'Requirements must contain at least 10 alphanumeric characters if provided.'
                )
            return text
        return value

    def validate_location(self, value):
        if value:
            return _validate_meaningful_text(value, 'Location')
        return value

    def validate_department(self, value):
        if value:
            return _validate_meaningful_text(value, 'Department')
        return value


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

