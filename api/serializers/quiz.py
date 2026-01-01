from rest_framework import serializers
from core.models import QuizResponse
import json


class QuizResponseSerializer(serializers.ModelSerializer):
    """Serializer for Quiz Response"""
    responses_data = serializers.SerializerMethodField()
    recommendations_data = serializers.SerializerMethodField()
    
    class Meta:
        model = QuizResponse
        fields = ['id', 'email', 'name', 'location', 'industry', 'goal', 'project_type',
                  'responses', 'responses_data', 'recommendations', 'recommendations_data',
                  'created_at']
        read_only_fields = ['id', 'created_at']
    
    def get_responses_data(self, obj):
        """Parse responses JSON string to dict"""
        if obj.responses:
            try:
                return json.loads(obj.responses)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}
    
    def get_recommendations_data(self, obj):
        """Parse recommendations JSON string to dict"""
        if obj.recommendations:
            try:
                return json.loads(obj.recommendations)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}
    
    def create(self, validated_data):
        """Convert responses dict to JSON string"""
        responses = self.initial_data.get('responses', {})
        if isinstance(responses, dict):
            validated_data['responses'] = json.dumps(responses)
        return super().create(validated_data)

