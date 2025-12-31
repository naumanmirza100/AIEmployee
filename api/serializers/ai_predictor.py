from rest_framework import serializers
from core.models import AIPredictorSubmission
import json


class AIPredictorSubmissionSerializer(serializers.ModelSerializer):
    """Serializer for AI Predictor Submission"""
    project_data_dict = serializers.SerializerMethodField()
    
    class Meta:
        model = AIPredictorSubmission
        fields = ['id', 'email', 'project_type', 'project_data', 'project_data_dict',
                  'predicted_cost', 'predicted_duration', 'predicted_team_size',
                  'prediction_confidence', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def get_project_data_dict(self, obj):
        """Parse project_data JSON string to dict"""
        if obj.project_data:
            try:
                return json.loads(obj.project_data)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}
    
    def create(self, validated_data):
        """Convert project_data dict to JSON string"""
        project_data = self.initial_data.get('projectData') or self.initial_data.get('project_data', {})
        if isinstance(project_data, dict):
            validated_data['project_data'] = json.dumps(project_data)
        return super().create(validated_data)

