# Generated manually to rename all marketing_agent tables to ppp_marketingagent_ prefix

from django.db import migrations, connection


def rename_m2m_table(apps, schema_editor):
    """Rename the M2M table if it exists"""
    db_backend = schema_editor.connection.vendor
    db_engine = schema_editor.connection.settings_dict.get('ENGINE', '')
    
    # Detect SQL Server by checking engine name or vendor
    is_sql_server = 'mssql' in db_engine.lower() or db_backend == 'mssql'
    
    if db_backend == 'sqlite':
        # SQLite: Check if table exists and rename
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='marketing_agent_campaign_leads'
            """)
            if cursor.fetchone():
                cursor.execute("ALTER TABLE marketing_agent_campaign_leads RENAME TO ppp_marketingagent_campaign_leads")
    elif is_sql_server:
        # SQL Server: Use sp_rename (must be executed separately, not in IF block)
        with schema_editor.connection.cursor() as cursor:
            # Check if table exists first
            cursor.execute("""
                SELECT COUNT(*) FROM sys.tables WHERE name = 'marketing_agent_campaign_leads'
            """)
            if cursor.fetchone()[0] > 0:
                # Use sp_rename for SQL Server
                cursor.execute("EXEC sp_rename 'marketing_agent_campaign_leads', 'ppp_marketingagent_campaign_leads'")
    else:
        # PostgreSQL, MySQL, etc.
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("ALTER TABLE marketing_agent_campaign_leads RENAME TO ppp_marketingagent_campaign_leads")


def reverse_rename_m2m_table(apps, schema_editor):
    """Reverse: rename back to original"""
    db_backend = schema_editor.connection.vendor
    db_engine = schema_editor.connection.settings_dict.get('ENGINE', '')
    
    # Detect SQL Server by checking engine name or vendor
    is_sql_server = 'mssql' in db_engine.lower() or db_backend == 'mssql'
    
    if db_backend == 'sqlite':
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='ppp_marketingagent_campaign_leads'
            """)
            if cursor.fetchone():
                cursor.execute("ALTER TABLE ppp_marketingagent_campaign_leads RENAME TO marketing_agent_campaign_leads")
    elif is_sql_server:
        # SQL Server: Use sp_rename (must be executed separately, not in IF block)
        with schema_editor.connection.cursor() as cursor:
            # Check if table exists first
            cursor.execute("""
                SELECT COUNT(*) FROM sys.tables WHERE name = 'ppp_marketingagent_campaign_leads'
            """)
            if cursor.fetchone()[0] > 0:
                # Use sp_rename for SQL Server
                cursor.execute("EXEC sp_rename 'ppp_marketingagent_campaign_leads', 'marketing_agent_campaign_leads'")
    else:
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("ALTER TABLE ppp_marketingagent_campaign_leads RENAME TO marketing_agent_campaign_leads")


class Migration(migrations.Migration):

    dependencies = [
        ('marketing_agent', '0021_add_imap_fields_and_message_id'),
    ]

    operations = [
        # Rename all main tables
        migrations.AlterModelTable(
            name='lead',
            table='ppp_marketingagent_lead',
        ),
        migrations.AlterModelTable(
            name='campaign',
            table='ppp_marketingagent_campaign',
        ),
        migrations.AlterModelTable(
            name='marketresearch',
            table='ppp_marketingagent_marketresearch',
        ),
        migrations.AlterModelTable(
            name='campaignperformance',
            table='ppp_marketingagent_campaignperformance',
        ),
        migrations.AlterModelTable(
            name='marketingdocument',
            table='ppp_marketingagent_marketingdocument',
        ),
        migrations.AlterModelTable(
            name='notificationrule',
            table='ppp_marketingagent_notificationrule',
        ),
        migrations.AlterModelTable(
            name='marketingnotification',
            table='ppp_marketingagent_marketingnotification',
        ),
        migrations.AlterModelTable(
            name='emailtemplate',
            table='ppp_marketingagent_emailtemplate',
        ),
        migrations.AlterModelTable(
            name='emailsequence',
            table='ppp_marketingagent_emailsequence',
        ),
        migrations.AlterModelTable(
            name='emailsequencestep',
            table='ppp_marketingagent_emailsequencestep',
        ),
        migrations.AlterModelTable(
            name='emailsendhistory',
            table='ppp_marketingagent_emailsendhistory',
        ),
        migrations.AlterModelTable(
            name='emailaccount',
            table='ppp_marketingagent_emailaccount',
        ),
        migrations.AlterModelTable(
            name='campaigncontact',
            table='ppp_marketingagent_campaigncontact',
        ),
        migrations.AlterModelTable(
            name='reply',
            table='ppp_marketingagent_reply',
        ),
        # Rename the many-to-many table for Campaign.leads (conditionally)
        migrations.RunPython(
            rename_m2m_table,
            reverse_rename_m2m_table,
        ),
    ]
