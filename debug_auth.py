"""
Debug script to check authentication and permissions
"""
import os
import sys
import django

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

email = 'darkknightmughal@gmail.com'

try:
    user = User.objects.get(email=email)
    print(f"\n{'='*60}")
    print(f"USER DEBUG INFO")
    print(f"{'='*60}")
    print(f"Email: {user.email}")
    print(f"Username: {user.username}")
    print(f"ID: {user.id}")
    print(f"is_staff: {user.is_staff}")
    print(f"is_superuser: {user.is_superuser}")
    print(f"is_active: {user.is_active}")
    print(f"is_authenticated: {user.is_authenticated}")
    
    # Check token
    try:
        token = Token.objects.get(user=user)
        print(f"\nToken exists: {token.key[:20]}...")
    except Token.DoesNotExist:
        print(f"\nNo token found")
    
    # Test permission manually
    from api.permissions import IsAdmin
    from rest_framework.test import APIRequestFactory
    from rest_framework.request import Request
    
    factory = APIRequestFactory()
    request = factory.get('/api/contact/admin')
    request.user = user
    
    permission = IsAdmin()
    has_permission = permission.has_permission(request, None)
    
    print(f"\nPermission Check Result: {has_permission}")
    print(f"{'='*60}\n")
    
except User.DoesNotExist:
    print(f"User {email} not found")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()


