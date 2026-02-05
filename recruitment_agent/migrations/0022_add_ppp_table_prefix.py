# Migration: Rename recruitment_agent tables to ppp_recruitment_agent_* (match marketing prefix)

from django.db import migrations


def rename_tables_sqlserver(apps, schema_editor):
    """Rename tables to ppp_recruitment_agent_* for SQL Server."""
    renames = [
        ('recruitment_agent_recruiteremailsettings', 'ppp_recruitment_agent_recruiteremailsettings'),
        ('recruitment_agent_recruiterqualificationsettings', 'ppp_recruitment_agent_recruiterqualificationsettings'),
        ('recruitment_agent_recruiterinterviewsettings', 'ppp_recruitment_agent_recruiterinterviewsettings'),
        ('recruitment_agent_jobdescription', 'ppp_recruitment_agent_jobdescription'),
        ('ppp_cv_records', 'ppp_recruitment_agent_cvrecord'),
        ('recruitment_agent_interview', 'ppp_recruitment_agent_interview'),
        ('recruitment_agent_careerapplication', 'ppp_recruitment_agent_careerapplication'),
    ]
    for old_name, new_name in renames:
        schema_editor.execute(
            "EXEC sp_rename N'%s', N'%s';" % (old_name, new_name)
        )


def reverse_rename_tables_sqlserver(apps, schema_editor):
    """Reverse: rename ppp_* back to recruitment_agent_*."""
    renames = [
        ('ppp_recruitment_agent_recruiteremailsettings', 'recruitment_agent_recruiteremailsettings'),
        ('ppp_recruitment_agent_recruiterqualificationsettings', 'recruitment_agent_recruiterqualificationsettings'),
        ('ppp_recruitment_agent_recruiterinterviewsettings', 'recruitment_agent_recruiterinterviewsettings'),
        ('ppp_recruitment_agent_jobdescription', 'recruitment_agent_jobdescription'),
        ('ppp_recruitment_agent_cvrecord', 'ppp_cv_records'),
        ('ppp_recruitment_agent_interview', 'recruitment_agent_interview'),
        ('ppp_recruitment_agent_careerapplication', 'recruitment_agent_careerapplication'),
    ]
    for old_name, new_name in renames:
        schema_editor.execute(
            "EXEC sp_rename N'%s', N'%s';" % (old_name, new_name)
        )


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment_agent', '0021_recruiterinterviewsettings_default_interview_type'),
    ]

    operations = [
        migrations.RunPython(rename_tables_sqlserver, reverse_rename_tables_sqlserver),
    ]
