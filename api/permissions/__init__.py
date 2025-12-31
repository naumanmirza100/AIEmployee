from rest_framework import permissions


class IsAdmin(permissions.BasePermission):
    """Allow access only to admin users."""
    
    def has_permission(self, request, view):
        return request.user and request.user.is_staff


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


class OptionalAuth(permissions.BasePermission):
    """Allow access to authenticated and unauthenticated users."""
    
    def has_permission(self, request, view):
        return True

