"""
Test script to simulate the actual API call
"""
import os
import sys
import django

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIRequestFactory, force_authenticate
from api.views.contact import list_contact_messages
from api.permissions import IsAdmin

email = 'darkknightmughal@gmail.com'

try:
    user = User.objects.get(email=email)
    token = Token.objects.get(user=user)
    
    print(f"\n{'='*60}")
    print(f"TESTING API CALL WITH TOKEN AUTHENTICATION")
    print(f"{'='*60}")
    print(f"User: {user.email}")
    print(f"is_staff: {user.is_staff}")
    print(f"Token: {token.key[:20]}...")
    
    # Create a request
    factory = APIRequestFactory()
    request = factory.get('/api/contact/admin')
    
    # Authenticate with token
    force_authenticate(request, user=user, token=token)
    
    print(f"\nAfter force_authenticate:")
    print(f"  request.user: {request.user.email if request.user else 'None'}")
    print(f"  request.user.is_authenticated: {request.user.is_authenticated if request.user else False}")
    print(f"  request.user.is_staff: {request.user.is_staff if request.user else 'N/A'}")
    
    # Test permission
    permission = IsAdmin()
    has_permission = permission.has_permission(request, None)
    print(f"\nPermission check result: {has_permission}")
    
    # Try calling the view
    try:
        response = list_contact_messages(request)
        print(f"\nView response status: {response.status_code}")
        if response.status_code == 403:
            print("  -> Got 403 Forbidden!")
        else:
            print("  -> Success!")
    except Exception as e:
        print(f"\nView error: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"{'='*60}\n")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()


