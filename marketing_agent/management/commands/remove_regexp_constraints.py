"""
Management command to remove REGEXP_LIKE constraints and functions from SQL Server database.
Run: python manage.py remove_regexp_constraints
"""
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Remove REGEXP_LIKE constraints and functions that are not supported in SQL Server'

    def handle(self, *args, **options):
        # Check if using SQL Server (vendor can be 'mssql' or check engine)
        db_engine = connection.settings_dict.get('ENGINE', '')
        is_sql_server = 'mssql' in db_engine.lower() or connection.vendor == 'mssql'
        
        if not is_sql_server:
            self.stdout.write(self.style.WARNING('This command is only for SQL Server databases.'))
            return

        self.stdout.write('Checking for REGEXP_LIKE constraints and functions in SQL Server...')
        
        with connection.cursor() as cursor:
            total_removed = 0
            
            # 1. Check and remove constraints
            try:
                self.stdout.write('\n1. Checking for REGEXP_LIKE constraints...')
                cursor.execute("""
                    SELECT 
                        OBJECT_SCHEMA_NAME(parent_object_id) AS schema_name,
                        OBJECT_NAME(parent_object_id) AS table_name,
                        name AS constraint_name,
                        definition
                    FROM sys.check_constraints
                    WHERE definition LIKE '%REGEXP_LIKE%'
                       OR definition LIKE '%regexp_like%'
                       OR definition LIKE '%REGEXP%'
                       OR definition LIKE '%regexp%'
                """)
                
                constraints = cursor.fetchall()
                
                if not constraints:
                    self.stdout.write(self.style.SUCCESS('  No REGEXP_LIKE constraints found.'))
                else:
                    self.stdout.write(f'  Found {len(constraints)} constraint(s) using REGEXP_LIKE:')
                    
                    for schema_name, table_name, constraint_name, definition in constraints:
                        self.stdout.write(f'    - {schema_name}.{table_name}.{constraint_name}')
                        self.stdout.write(f'      Definition: {definition[:100]}...')
                    
                    # Remove each constraint
                    removed_count = 0
                    for schema_name, table_name, constraint_name, definition in constraints:
                        try:
                            full_table_name = f"[{schema_name}].[{table_name}]" if schema_name else f"[{table_name}]"
                            drop_sql = f"ALTER TABLE {full_table_name} DROP CONSTRAINT [{constraint_name}]"
                            cursor.execute(drop_sql)
                            removed_count += 1
                            self.stdout.write(self.style.SUCCESS(f'    [OK] Removed {constraint_name} from {full_table_name}'))
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f'    [FAILED] Failed to remove {constraint_name}: {e}'))
                    
                    total_removed += removed_count
                    self.stdout.write(self.style.SUCCESS(f'  Removed {removed_count} constraint(s).'))
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  Error checking for constraints: {e}'))
                import traceback
                self.stdout.write(traceback.format_exc())
            
            # 2. Check and remove functions
            try:
                self.stdout.write('\n2. Checking for REGEXP_LIKE functions...')
                cursor.execute("""
                    SELECT 
                        SCHEMA_NAME(schema_id) AS schema_name,
                        name AS function_name
                    FROM sys.objects
                    WHERE (type = 'FN' OR type = 'IF' OR type = 'TF')
                    AND (
                        OBJECT_DEFINITION(object_id) LIKE '%REGEXP_LIKE%'
                        OR OBJECT_DEFINITION(object_id) LIKE '%regexp_like%'
                        OR name LIKE '%REGEXP%'
                        OR name LIKE '%regexp%'
                    )
                """)
                
                functions = cursor.fetchall()
                
                if not functions:
                    self.stdout.write(self.style.SUCCESS('  No REGEXP_LIKE functions found.'))
                else:
                    self.stdout.write(f'  Found {len(functions)} function(s) using REGEXP_LIKE:')
                    
                    for schema_name, function_name in functions:
                        self.stdout.write(f'    - {schema_name}.{function_name}')
                    
                    # Remove each function
                    removed_count = 0
                    for schema_name, function_name in functions:
                        try:
                            full_function_name = f"[{schema_name}].[{function_name}]" if schema_name else f"[{function_name}]"
                            drop_sql = f"DROP FUNCTION {full_function_name}"
                            cursor.execute(drop_sql)
                            removed_count += 1
                            self.stdout.write(self.style.SUCCESS(f'    [OK] Removed function {full_function_name}'))
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f'    [FAILED] Failed to remove {function_name}: {e}'))
                    
                    total_removed += removed_count
                    self.stdout.write(self.style.SUCCESS(f'  Removed {removed_count} function(s).'))
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  Error checking for functions: {e}'))
                import traceback
                self.stdout.write(traceback.format_exc())
            
            # Summary
            if total_removed > 0:
                self.stdout.write(self.style.SUCCESS(f'\nSuccessfully removed {total_removed} object(s) total.'))
                self.stdout.write(self.style.SUCCESS('Please restart Celery worker for changes to take effect.'))
            else:
                self.stdout.write(self.style.SUCCESS('\nNo REGEXP_LIKE objects found. Database is clean.'))
