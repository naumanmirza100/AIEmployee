"""The AI Data Analyst goes on sale like the other agents (3 Nov 2026).

Its price is an Agent Plan, set in super-admin Agent Plans, which also creates it in Stripe; this makes the agent
row (for sale, and for counting its AI tokens) and gives its card its words.
"""
from django.db import migrations

DESCRIPTION = ('Ask questions about your own database in plain words. It writes the query, runs it read-only, and '
               'answers with the table and the SQL. PostgreSQL, MySQL / MariaDB or a SQLite file. Your data is never '
               'copied: only each question, its answer and its query are kept.')
FEATURES = [
    'PostgreSQL, MySQL / MariaDB, or an uploaded SQLite file',
    'Questions in plain words, answered with a table and the SQL that ran',
    'Read-only: every query is checked, and run in a read-only session',
    'Your data is never copied: only questions, answers and queries are kept',
    'Owners and admins choose who may ask each database',
    'Download any answer as a CSV',
]


def forwards(apps, schema_editor):
    Agent = apps.get_model('core', 'Agent')
    Agent.objects.update_or_create(slug='data_analyst_agent', defaults={
        'name': 'AI Data Analyst', 'description': DESCRIPTION, 'features': FEATURES, 'is_purchasable': True,
        'is_active': True})


def backwards(apps, schema_editor):
    apps.get_model('core', 'Agent').objects.filter(slug='data_analyst_agent').update(is_purchasable=False)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0121_company_assistant'),
        ('data_analyst_agent', '0001_initial'),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
