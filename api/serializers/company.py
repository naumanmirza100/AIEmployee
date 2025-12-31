from rest_framework import serializers
from core.models import Company, CompanyUser, CompanyRegistrationToken
from django.contrib.auth.models import User


class CompanySerializer(serializers.ModelSerializer):
    """Serializer for Company model"""
    
    class Meta:
        model = Company
        fields = ['id', 'name', 'email', 'phone', 'address', 'website', 'industry',
                  'company_size', 'description', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class CompanyUserSerializer(serializers.ModelSerializer):
    """Serializer for Company User model"""
    company_name = serializers.CharField(source='company.name', read_only=True)
    
    class Meta:
        model = CompanyUser
        fields = ['id', 'company', 'company_name', 'email', 'full_name', 'role',
                  'is_active', 'last_login', 'created_at']
        read_only_fields = ['id', 'last_login', 'created_at']


class CompanyRegistrationTokenSerializer(serializers.ModelSerializer):
    """Serializer for Company Registration Token"""
    company_name = serializers.CharField(source='company.name', read_only=True, allow_null=True)
    
    class Meta:
        model = CompanyRegistrationToken
        fields = ['id', 'token', 'company', 'company_name', 'expires_at', 'is_used',
                  'created_by', 'created_at', 'used_at']
        read_only_fields = ['id', 'token', 'created_at']

