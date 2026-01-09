"""
Script to create an admin user or make existing user admin
Usage: python create_admin_user.py <email> [password]
"""
import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from django.contrib.auth.models import User
from core.models import UserProfile

if len(sys.argv) < 2:
    print("Usage: python create_admin_user.py <email> [password]")
    print("Example: python create_admin_user.py admin@example.com mypassword123")
    sys.exit(1)

email = sys.argv[1]
password = sys.argv[2] if len(sys.argv) > 2 else None

try:
    # Check if user exists
    try:
        user = User.objects.get(email=email)
        print(f"[OK] User {email} already exists")
        
        # Make them admin
        user.is_staff = True
        user.is_superuser = True
        if password:
            user.set_password(password)
        user.save()
        print(f"[SUCCESS] Successfully made {email} an admin (is_staff=True, is_superuser=True)")
        
    except User.DoesNotExist:
        # Create new user
        if not password:
            print("[ERROR] Password is required to create a new user")
            print("Usage: python create_admin_user.py <email> <password>")
            sys.exit(1)
        
        # Create user with email as username
        username = email
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            is_staff=True,
            is_superuser=True,
            first_name='Admin',
            last_name='User'
        )
        
        # Create profile if it doesn't exist
        if not hasattr(user, 'profile'):
            UserProfile.objects.create(user=user, role='project_manager')
        
        print(f"[SUCCESS] Successfully created admin user {email}")
        print(f"   Username: {username}")
        print(f"   Password: {password}")
        print(f"   is_staff: True")
        print(f"   is_superuser: True")
        
except Exception as e:
    print(f"[ERROR] Error: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

