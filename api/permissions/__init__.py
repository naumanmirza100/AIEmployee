from rest_framework import permissions


class IsAdmin(permissions.BasePermission):
    """Allow access only to admin users."""
    
    def has_permission(self, request, view):
        # Basic checks
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Get fresh user data from database to ensure we have latest is_staff status
        # This is important because user permissions might have changed after token was issued
        try:
            # Refresh from database to get latest user data
            user_id = request.user.id
            from django.contrib.auth.models import User
            fresh_user = User.objects.get(id=user_id)
            
            # Check if user is staff or superuser
            if fresh_user.is_staff or fresh_user.is_superuser:
                # Update request.user with fresh data
                request.user.is_staff = fresh_user.is_staff
                request.user.is_superuser = fresh_user.is_superuser
                return True
        except Exception:
            # Fallback to request.user if refresh fails
            if request.user.is_staff or request.user.is_superuser:
                return True
        
        return False


class IsOwnerOrAdmin(permissions.BasePermission):
    """Allow access to owners or admins."""
    
    def has_object_permission(self, request, view, obj):
        # Admin can access everything
        if request.user.is_staff:
            return True
        
        # Check if user is owner
        if hasattr(obj, 'owner'):
            return obj.owner == request.user
        elif hasattr(obj, 'user'):
            return obj.user == request.user
        elif hasattr(obj, 'client'):
            return obj.client == request.user
        
        return False


class IsCompanyUser(permissions.BasePermission):
    """Allow access only to company users."""
    
    def has_permission(self, request, view):
        # Check if user has company role
        if hasattr(request.user, 'profile'):
            return request.user.profile.role == 'project_manager'
        return False


class IsCompanyUserOnly(permissions.BasePermission):
    """Allow access only to authenticated CompanyUser instances (logged in through company login)."""
    
    def has_permission(self, request, view):
        # Check if request.user exists
        if not request.user:
            return False
        
        # Check if user is a CompanyUser instance (from CompanyUserTokenAuthentication)
        from core.models import CompanyUser
        if isinstance(request.user, CompanyUser):
            # CompanyUser is authenticated if it exists and is active
            return request.user.is_active
        
        # If it's a regular User, check is_authenticated
        if hasattr(request.user, 'is_authenticated'):
            return request.user.is_authenticated
        
        return False


class OptionalAuth(permissions.BasePermission):
    """Allow access to authenticated and unauthenticated users."""
    
    def has_permission(self, request, view):
        return True

