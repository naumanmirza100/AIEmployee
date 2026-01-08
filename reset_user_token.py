"""
Script to reset user token (delete old token so new one is generated on login)
Usage: python reset_user_token.py <email>
"""
import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

if len(sys.argv) < 2:
    print("Usage: python reset_user_token.py <email>")
    print("Example: python reset_user_token.py darkknightmughal@gmail.com")
    sys.exit(1)

email = sys.argv[1]

try:
    user = User.objects.get(email=email)
    
    # Delete existing token
    try:
        token = Token.objects.get(user=user)
        token.delete()
        print(f"[SUCCESS] Deleted old token for {email}")
    except Token.DoesNotExist:
        print(f"[INFO] No existing token found for {email}")
    
    # Verify admin status
    print(f"\nUser Status:")
    print(f"  Email: {user.email}")
    print(f"  is_staff: {user.is_staff}")
    print(f"  is_superuser: {user.is_superuser}")
    print(f"  is_active: {user.is_active}")
    
    if not user.is_staff:
        print(f"\n[WARNING] User is not staff! Run: python create_admin_user.py {email}")
    else:
        print(f"\n[SUCCESS] User is admin. Please log out and log back in to get a new token.")
        
except User.DoesNotExist:
    print(f"[ERROR] User with email {email} not found")
    sys.exit(1)
except Exception as e:
    print(f"[ERROR] Error: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)


