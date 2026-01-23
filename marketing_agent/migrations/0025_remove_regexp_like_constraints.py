# Migration to remove REGEXP_LIKE constraints that don't work with SQL Server
# REGEXP_LIKE is an Oracle/PostgreSQL function, not available in SQL Server

from django.db import migrations


def remove_regexp_like_constraints(apps, schema_editor):
    """Remove any check constraints that use REGEXP_LIKE (not supported in SQL Server)"""
    db_backend = schema_editor.connection.vendor
    
    if db_backend == 'mssql':
        with schema_editor.connection.cursor() as cursor:
            try:
                # Find all check constraints that might use REGEXP_LIKE
                # SQL Server stores constraints in sys.check_constraints
                cursor.execute("""
                    SELECT 
                        OBJECT_SCHEMA_NAME(parent_object_id) AS schema_name,
                        OBJECT_NAME(parent_object_id) AS table_name,
                        name AS constraint_name
                    FROM sys.check_constraints
                    WHERE definition LIKE '%REGEXP_LIKE%'
                       OR definition LIKE '%regexp_like%'
                """)
                
                constraints = cursor.fetchall()
                
                for schema_name, table_name, constraint_name in constraints:
                    try:
                        # Drop the constraint using proper schema qualification
                        full_table_name = f"[{schema_name}].[{table_name}]" if schema_name else f"[{table_name}]"
                        cursor.execute(f"ALTER TABLE {full_table_name} DROP CONSTRAINT [{constraint_name}]")
                        print(f"Removed constraint {constraint_name} from {full_table_name}")
                    except Exception as e:
                        print(f"Could not remove constraint {constraint_name} from {table_name}: {e}")
            except Exception as e:
                # If query fails, it might mean no such constraints exist - that's fine
                print(f"Could not check for REGEXP_LIKE constraints (may not exist): {e}")


def reverse_remove_regexp_like_constraints(apps, schema_editor):
    """Reverse: do nothing (constraints shouldn't be recreated)"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('marketing_agent', '0024_add_campaign_lead_through_model'),
    ]

    operations = [
        migrations.RunPython(
            remove_regexp_like_constraints,
            reverse_remove_regexp_like_constraints,
        ),
    ]
