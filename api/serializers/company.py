import re
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

    def validate_email(self, value):
        """Strict email validation - reject malformed emails"""
        email = value.strip().lower()
        # Strict email regex: local part allows alphanumeric, dots, hyphens, underscores, plus
        # Domain must have at least 2 parts, TLD must be 2+ alpha chars
        email_regex = r'^[a-zA-Z0-9][a-zA-Z0-9._%+-]*@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            raise serializers.ValidationError(
                'Enter a valid email address (e.g., company@example.com).'
            )
        # Reject multiple @ signs
        if email.count('@') != 1:
            raise serializers.ValidationError('Email must contain exactly one @ symbol.')
        # Reject consecutive dots in domain
        domain = email.split('@')[1]
        if '..' in domain:
            raise serializers.ValidationError('Email domain cannot contain consecutive dots.')
        # Check for duplicate email
        instance = self.instance  # None on create, existing object on update
        qs = Company.objects.filter(email__iexact=email)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError('A company with this email already exists.')
        return email

    def validate_name(self, value):
        """Validate company name - must contain at least 2 alphanumeric characters"""
        name = value.strip()
        if not name:
            raise serializers.ValidationError('Company name is required.')
        # Count alphanumeric characters
        alnum_count = sum(1 for c in name if c.isalnum())
        if alnum_count < 2:
            raise serializers.ValidationError(
                'Company name must contain at least 2 alphanumeric characters.'
            )
        # Check for duplicate name
        instance = self.instance
        qs = Company.objects.filter(name__iexact=name)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError('A company with this name already exists.')
        return name

    def validate_phone(self, value):
        """Validate phone number format"""
        if not value:
            return value
        phone = value.strip()
        phone_digits = sum(1 for c in phone if c.isdigit())
        if not re.match(r'^[+]?[\d\s\-()]{7,20}$', phone) or phone_digits < 7:
            raise serializers.ValidationError(
                'Enter a valid phone number (at least 7 digits, e.g., +1234567890).'
            )
        return phone

    def validate_address(self, value):
        """Validate address has meaningful text"""
        if not value:
            return value
        address = value.strip()
        alnum_count = sum(1 for c in address if c.isalnum())
        if alnum_count < 3:
            raise serializers.ValidationError(
                'Address must contain at least 3 alphanumeric characters.'
            )
        return address

    def validate_website(self, value):
        """Validate website URL format"""
        if not value:
            return value
        url = value.strip()
        # Basic URL pattern check
        url_regex = r'^(https?://)?([\w.-]+)\.[a-zA-Z]{2,}(/.*)?$'
        if not re.match(url_regex, url):
            raise serializers.ValidationError(
                'Enter a valid website URL (e.g., https://company.com).'
            )
        return url

    def validate_industry(self, value):
        """Validate industry has meaningful text"""
        if not value:
            return value
        industry = value.strip()
        alpha_count = sum(1 for c in industry if c.isalpha())
        if alpha_count < 2:
            raise serializers.ValidationError(
                'Industry must contain at least 2 alphabetic characters.'
            )
        return industry

    def validate_company_size(self, value):
        """Validate company size is numeric only (digits, hyphens, spaces, plus allowed)"""
        if not value:
            return value
        size = value.strip()
        if not re.match(r'^[\d\s\-+]+$', size):
            raise serializers.ValidationError(
                'Company size must contain only numbers (e.g., 50, 50-100, 200+).'
            )
        digit_count = sum(1 for c in size if c.isdigit())
        if digit_count < 1:
            raise serializers.ValidationError(
                'Company size must contain at least one number.'
            )
        return size

    def validate_description(self, value):
        """Validate description has meaningful text"""
        if not value:
            return value
        desc = value.strip()
        alnum_count = sum(1 for c in desc if c.isalnum())
        if alnum_count < 10:
            raise serializers.ValidationError(
                'Description must contain at least 10 alphanumeric characters.'
            )
        return desc


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

