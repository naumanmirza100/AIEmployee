"""The Company Assistant (CO-18, 2 Nov 2026): one chat that asks across the agents a company has.

It is not bought on its own: a company has it while it has two agents or more (`core.modules.INCLUDED_WITH`). Its
row in the catalogue is what lets its AI calls be counted under its own name and its own free-token allowance, like
any agent. Its chats are kept with the other Quick Chats.
"""
from django.db import migrations, models

DESCRIPTION = ('One chat that asks across your agents: who is free, who is away, what someone is working on, '
               'how a project is going, and which customers are waiting. It reads only, and shows where each fact '
               'came from.')
FEATURES = [
    'Questions across Project Manager, HR and Frontline at once',
    'Availability from the shared calendar: meetings, interviews, sales calls, leave, holidays',
    'Every fact with a link to the screen it came from',
    'Reads only: never assigns, books or emails',
    'Included with two agents or more',
]


def add_agent(apps, schema_editor):
    apps.get_model('core', 'Agent').objects.update_or_create(slug='company_assistant', defaults={
        'name': 'Company Assistant', 'description': DESCRIPTION, 'features': FEATURES,
        'default_provider': 'openai', 'is_purchasable': False, 'is_active': True, 'sort_order': 200})


def remove_agent(apps, schema_editor):
    apps.get_model('core', 'Agent').objects.filter(slug='company_assistant').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0120_sign_in_sessions'),
    ]

    operations = [
        migrations.AlterField(
            model_name='quickchat',
            name='agent',
            field=models.CharField(choices=[('pm', 'Project Manager'), ('hr', 'HR'), ('frontline', 'Frontline'),
                                            ('assistant', 'Company Assistant')], max_length=20),
        ),
        migrations.RunPython(add_agent, remove_agent),
    ]
