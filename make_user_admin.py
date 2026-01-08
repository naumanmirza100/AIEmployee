"""
Script to make a user admin (set is_staff=True)
Usage: python make_user_admin.py <email>
"""
import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from django.contrib.auth.models import User

if len(sys.argv) < 2:
    print("Usage: python make_user_admin.py <email>")
    print("Example: python make_user_admin.py admin@example.com")
    sys.exit(1)

email = sys.argv[1]

try:
    user = User.objects.get(email=email)
    user.is_staff = True
    user.is_superuser = True  # Also make superuser for full admin access
    user.save()
    print(f"✅ Successfully made {email} an admin (is_staff=True, is_superuser=True)")
except User.DoesNotExist:
    print(f"❌ User with email {email} not found")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {str(e)}")
    sys.exit(1)


