from rest_framework import serializers
from core.models import WhiteLabelProduct


class WhiteLabelProductSerializer(serializers.ModelSerializer):
    """Serializer for White Label Product"""
    partner_name = serializers.CharField(source='partner.get_full_name', read_only=True, allow_null=True)
    
    class Meta:
        model = WhiteLabelProduct
        fields = ['id', 'name', 'description', 'category', 'partner', 'partner_name',
                  'featured', 'status', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

