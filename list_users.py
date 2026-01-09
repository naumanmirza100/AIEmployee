"""
Script to list all users
Usage: python list_users.py
"""
import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from django.contrib.auth.models import User

print("\n" + "="*60)
print("LIST OF ALL USERS")
print("="*60)

users = User.objects.all().order_by('email')

if not users:
    print("No users found in the database.")
else:
    print(f"\nTotal users: {users.count()}\n")
    for user in users:
        print(f"Email: {user.email}")
        print(f"  Username: {user.username}")
        print(f"  Name: {user.first_name} {user.last_name}")
        print(f"  is_staff: {user.is_staff}")
        print(f"  is_superuser: {user.is_superuser}")
        print(f"  is_active: {user.is_active}")
        print("-" * 60)

print("\n")


