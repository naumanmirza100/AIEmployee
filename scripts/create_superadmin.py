"""
Create Django Superadmin
========================
Run from the project root:
    python scripts/create_superadmin.py
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')

import django
django.setup()

from django.contrib.auth.models import User

USERNAME = 'admin'
EMAIL    = 'admin@gmail.com'
PASSWORD = 'pppadmin@123'

if User.objects.filter(username=USERNAME).exists():
    print(f"[SKIP] Superadmin '{USERNAME}' already exists.")
else:
    User.objects.create_superuser(username=USERNAME, email=EMAIL, password=PASSWORD)
    print(f"[OK] Superadmin created → username: {USERNAME}  |  password: {PASSWORD}")
