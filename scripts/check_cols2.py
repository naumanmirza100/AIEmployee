import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'payPerProject.settings')
django.setup()
from django.db import connection
cursor = connection.cursor()
cursor.execute("SELECT COLUMN_NAME, IS_NULLABLE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='core_keyrequest' ORDER BY ORDINAL_POSITION")
for row in cursor.fetchall():
    print(row)
