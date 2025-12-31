from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from core.models import UserProfile, Credit


class RegisterSerializer(serializers.Serializer):
    """Serializer for user registration"""
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True, min_length=8)
    firstName = serializers.CharField(required=False, allow_blank=True, source='first_name')
    lastName = serializers.CharField(required=False, allow_blank=True, source='last_name')
    phone = serializers.CharField(required=False, allow_blank=True)
    userType = serializers.CharField(required=False, default='client', source='user_type')
    
    def validate_email(self, value):
        """Check if email already exists"""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("User with this email already exists")
        return value
    
    def create(self, validated_data):
        """Create new user"""
        email = validated_data['email']
        password = validated_data['password']
        first_name = validated_data.get('first_name', '')
        last_name = validated_data.get('last_name', '')
        phone = validated_data.get('phone', '')
        user_type = validated_data.get('user_type', 'client')
        
        # Create user (using email as username)
        username = email  # Using email as username
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name
        )
        
        # Update user profile if needed
        if hasattr(user, 'profile'):
            profile = user.profile
        else:
            profile = UserProfile.objects.create(user=user)
        
        # Initialize credits
        Credit.objects.get_or_create(user=user, defaults={'balance': 0})
        
        return user


class LoginSerializer(serializers.Serializer):
    """Serializer for user login"""
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True)
    
    def validate(self, attrs):
        """Validate credentials"""
        email = attrs.get('email')
        password = attrs.get('password')
        
        if email and password:
            # Try to find user by email
            try:
                user = User.objects.get(email=email)
                user = authenticate(username=user.username, password=password)
            except User.DoesNotExist:
                user = None
            
            if not user:
                raise serializers.ValidationError('Invalid email or password')
            
            if not user.is_active:
                raise serializers.ValidationError('User account is disabled')
            
            attrs['user'] = user
        else:
            raise serializers.ValidationError('Must include "email" and "password"')
        
        return attrs


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user data"""
    firstName = serializers.CharField(source='first_name', read_only=True)
    lastName = serializers.CharField(source='last_name', read_only=True)
    userType = serializers.SerializerMethodField()
    accountStatus = serializers.SerializerMethodField()
    emailVerified = serializers.SerializerMethodField()
    lastLogin = serializers.DateTimeField(source='last_login', read_only=True)
    createdAt = serializers.DateTimeField(source='date_joined', read_only=True)
    profile = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'email', 'firstName', 'lastName', 'phone', 'userType', 
                  'accountStatus', 'emailVerified', 'lastLogin', 'createdAt', 'profile']
        read_only_fields = ['id', 'email']
    
    def get_userType(self, obj):
        """Get user type (client, freelancer, admin)"""
        # Map Django user types to PayPerProject types
        if obj.is_staff:
            return 'admin'
        # Check profile role if exists
        if hasattr(obj, 'profile'):
            role = obj.profile.role
            if role == 'project_manager':
                return 'client'
            elif role == 'developer':
                return 'freelancer'
        return 'client'
    
    def get_accountStatus(self, obj):
        """Get account status"""
        if obj.is_active:
            return 'active'
        return 'inactive'
    
    def get_emailVerified(self, obj):
        """Check if email is verified"""
        # For now, assume verified if user exists
        return True
    
    def get_phone(self, obj):
        """Get phone from user if exists"""
        # Django User model doesn't have phone field by default
        # Phone could be stored in UserProfile or we can return None
        return None
    
    def get_profile(self, obj):
        """Get user profile data"""
        if hasattr(obj, 'profile'):
            profile = obj.profile
            return {
                'companyName': profile.company_name,
                'bio': profile.bio,
                'avatarUrl': profile.avatar_url,
                'location': profile.location,
                'website': profile.website,
                'linkedin': profile.linkedin,
                'github': profile.github,
            }
        return {}

