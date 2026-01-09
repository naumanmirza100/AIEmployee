"""
Test API endpoints directly to see what's happening
"""
import os
import sys
import django
import requests

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

email = 'darkknightmughal@gmail.com'
base_url = 'http://localhost:8000/api'

try:
    user = User.objects.get(email=email)
    token = Token.objects.get(user=user)
    
    print(f"\n{'='*60}")
    print(f"TESTING API ENDPOINTS")
    print(f"{'='*60}")
    print(f"User: {user.email}")
    print(f"is_staff: {user.is_staff}")
    print(f"Token: {token.key}")
    print(f"Base URL: {base_url}")
    print(f"{'='*60}\n")
    
    headers = {
        'Authorization': f'Token {token.key}',
        'Content-Type': 'application/json'
    }
    
    # Test /api/auth/me
    print("1. Testing /api/auth/me...")
    try:
        response = requests.get(f'{base_url}/auth/me', headers=headers, timeout=5)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text[:200]}")
    except requests.exceptions.ConnectionError:
        print("   ERROR: Cannot connect to server. Is Django server running?")
    except Exception as e:
        print(f"   ERROR: {e}")
    
    print()
    
    # Test /api/companies
    print("2. Testing /api/companies...")
    try:
        response = requests.get(f'{base_url}/companies?page=1&limit=20', headers=headers, timeout=5)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text[:200]}")
    except requests.exceptions.ConnectionError:
        print("   ERROR: Cannot connect to server.")
    except Exception as e:
        print(f"   ERROR: {e}")
    
    print()
    
    # Test /api/contact/admin
    print("3. Testing /api/contact/admin...")
    try:
        response = requests.get(f'{base_url}/contact/admin?page=1&limit=20', headers=headers, timeout=5)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text[:200]}")
    except requests.exceptions.ConnectionError:
        print("   ERROR: Cannot connect to server.")
    except Exception as e:
        print(f"   ERROR: {e}")
    
    print(f"\n{'='*60}\n")
    
except User.DoesNotExist:
    print(f"User {email} not found")
except Token.DoesNotExist:
    print(f"No token found for {email}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()


