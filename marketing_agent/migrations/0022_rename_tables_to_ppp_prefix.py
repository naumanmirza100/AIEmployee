# Generated manually to rename all marketing_agent tables to ppp_marketingagent_ prefix

from django.db import migrations, connection

from ._rename_utils import alter_table_if_exists


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
        # PostgreSQL, MySQL, etc. Mirror the existence check the SQLite and
        # SQL Server branches already do — on a fresh database the table was
        # created under its new name to begin with, so there is nothing to
        # rename and an unguarded ALTER dies with "table doesn't exist".
        with schema_editor.connection.cursor() as cursor:
            if _table_exists(cursor, 'marketing_agent_campaign_leads'):
                cursor.execute("ALTER TABLE marketing_agent_campaign_leads RENAME TO ppp_marketingagent_campaign_leads")


def _table_exists(cursor, table_name):
    """Backend-agnostic existence check for the non-SQLite/MSSQL branches."""
    cursor.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = %s",
        [table_name],
    )
    return cursor.fetchone()[0] > 0


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
            if _table_exists(cursor, 'ppp_marketingagent_campaign_leads'):
                cursor.execute("ALTER TABLE ppp_marketingagent_campaign_leads RENAME TO marketing_agent_campaign_leads")


class Migration(migrations.Migration):

    dependencies = [
        ('marketing_agent', '0021_add_imap_fields_and_message_id'),
    ]

    operations = [
        # Rename all main tables
        alter_table_if_exists('lead', 'ppp_marketingagent_lead'),
        alter_table_if_exists('campaign', 'ppp_marketingagent_campaign'),
        alter_table_if_exists('marketresearch', 'ppp_marketingagent_marketresearch'),
        alter_table_if_exists('campaignperformance', 'ppp_marketingagent_campaignperformance'),
        alter_table_if_exists('marketingdocument', 'ppp_marketingagent_marketingdocument'),
        alter_table_if_exists('notificationrule', 'ppp_marketingagent_notificationrule'),
        alter_table_if_exists('marketingnotification', 'ppp_marketingagent_marketingnotification'),
        alter_table_if_exists('emailtemplate', 'ppp_marketingagent_emailtemplate'),
        alter_table_if_exists('emailsequence', 'ppp_marketingagent_emailsequence'),
        alter_table_if_exists('emailsequencestep', 'ppp_marketingagent_emailsequencestep'),
        alter_table_if_exists('emailsendhistory', 'ppp_marketingagent_emailsendhistory'),
        alter_table_if_exists('emailaccount', 'ppp_marketingagent_emailaccount'),
        alter_table_if_exists('campaigncontact', 'ppp_marketingagent_campaigncontact'),
        alter_table_if_exists('reply', 'ppp_marketingagent_reply'),
        # Rename the many-to-many table for Campaign.leads (conditionally)
        migrations.RunPython(
            rename_m2m_table,
            reverse_rename_m2m_table,
        ),
    ]
