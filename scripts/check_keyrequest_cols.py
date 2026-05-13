from django.db import connection
cursor = connection.cursor()
cursor.execute("SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'core_keyrequest' ORDER BY ORDINAL_POSITION")
for row in cursor.fetchall():
    print(row)
