from rest_framework import serializers
from core.models import Project, Industry, ProjectApplication
from django.contrib.auth.models import User


class ProjectSerializer(serializers.ModelSerializer):
    """Serializer for Project model"""
    # Map Django field names to API field names
    title = serializers.CharField(source='name', required=False)
    client_id = serializers.IntegerField(source='owner.id', read_only=True)
    client_email = serializers.EmailField(source='owner.email', read_only=True)
    industry_id = serializers.IntegerField(source='industry.id', read_only=True, allow_null=True)
    project_manager_id = serializers.IntegerField(source='project_manager.id', read_only=True, allow_null=True)
    budget_min = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    budget_max = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    
    class Meta:
        model = Project
        fields = ['id', 'title', 'name', 'description', 'client_id', 'client_email', 
                  'industry_id', 'industry', 'project_type', 'project_manager_id', 'project_manager',
                  'budget_min', 'budget_max', 'deadline', 'priority', 'status',
                  'start_date', 'end_date', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        """Create project with mapped fields"""
        # Handle title -> name mapping
        if 'name' in validated_data:
            validated_data['name'] = validated_data['name']
        elif 'title' in self.initial_data:
            validated_data['name'] = self.initial_data['title']
        
        # Set owner from request user
        validated_data['owner'] = self.context['request'].user
        
        # Set status to draft by default
        validated_data['status'] = validated_data.get('status', 'draft')
        
        return super().create(validated_data)


class ProjectListSerializer(serializers.ModelSerializer):
    """Simplified serializer for project lists"""
    title = serializers.CharField(source='name')
    client_id = serializers.IntegerField(source='owner.id')
    industry_id = serializers.IntegerField(source='industry.id', allow_null=True)
    
    class Meta:
        model = Project
        fields = ['id', 'title', 'description', 'client_id', 'industry_id', 
                  'project_type', 'budget_min', 'budget_max', 'deadline', 
                  'priority', 'status', 'created_at']


class ProjectApplicationSerializer(serializers.ModelSerializer):
    """Serializer for project applications"""
    freelancer_id = serializers.IntegerField(source='freelancer.id', read_only=True)
    project_id = serializers.IntegerField(source='project.id', read_only=True)
    estimated_cost = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    
    class Meta:
        model = ProjectApplication
        fields = ['id', 'project_id', 'freelancer_id', 'proposal', 
                  'estimated_cost', 'estimated_duration', 'status', 'applied_at']
        read_only_fields = ['id', 'applied_at']

