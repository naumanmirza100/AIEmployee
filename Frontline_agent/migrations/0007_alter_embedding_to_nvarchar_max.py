# Custom migration to explicitly set embedding column to NVARCHAR(MAX) in SQL Server

from django.db import migrations
import logging

logger = logging.getLogger(__name__)


def alter_embedding_to_max(apps, schema_editor):
    """Explicitly alter the embedding column to NVARCHAR(MAX) in SQL Server"""
    Document = apps.get_model('Frontline_agent', 'Document')
    table_name = Document._meta.db_table
    
    with schema_editor.connection.cursor() as cursor:
        # Alter column to NVARCHAR(MAX) - removes any size limit
        sql = f"""
        ALTER TABLE [dbo].[{table_name}]
        ALTER COLUMN [embedding] NVARCHAR(MAX) NULL
        """
        try:
            cursor.execute(sql)
            logger.info(f"Successfully altered embedding column to NVARCHAR(MAX) in {table_name}")
        except Exception as e:
            logger.warning(f"Warning: Could not alter column (may already be correct): {e}")


def reverse_alter(apps, schema_editor):
    """Reverse operation - not really needed, but included for completeness"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('Frontline_agent', '0006_change_embedding_to_textfield'),
    ]

    operations = [
        migrations.RunPython(alter_embedding_to_max, reverse_alter),
    ]

