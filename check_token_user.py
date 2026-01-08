"""
Check which user a token belongs to
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
    token = Token.objects.get(user=user)
    
    print(f"\n{'='*60}")
    print(f"TOKEN INFO FOR: {email}")
    print(f"{'='*60}")
    print(f"Token: {token.key}")
    print(f"Token User Email: {token.user.email}")
    print(f"Token User ID: {token.user.id}")
    print(f"Token User is_staff: {token.user.is_staff}")
    print(f"Token User is_superuser: {token.user.is_superuser}")
    print(f"{'='*60}\n")
    
    # Check all tokens
    print(f"\n{'='*60}")
    print(f"ALL TOKENS IN DATABASE")
    print(f"{'='*60}")
    all_tokens = Token.objects.all().select_related('user')
    for t in all_tokens:
        print(f"Token: {t.key[:20]}... | User: {t.user.email} | is_staff: {t.user.is_staff}")
    print(f"{'='*60}\n")
    
except User.DoesNotExist:
    print(f"User {email} not found")
except Token.DoesNotExist:
    print(f"No token found for {email}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()


