import django, os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings'); django.setup()
from django.db import connection; cursor = connection.cursor(); cursor.execute("SELECT COLUMN_NAME, IS_NULLABLE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'core_keyrequest' ORDER BY ORDINAL_POSITION"); print([r for r in cursor.fetchall()])
