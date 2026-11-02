"""CRM Sync goes on sale like the other agents (Abdullah's choice, 30 Oct 2026), and old Pipedrive errors lose the key.

The agent row was made by hand on the live site on 24 Oct, not for sale, so no company could buy it. Its price is
an Agent Plan, set in super-admin Agent Plans, which also creates it in Stripe; this only puts the agent on sale and
gives its card its words.

A Pipedrive call that failed wrote the request address, key and all, into the queue's and the log's error text
(CO-158). Those texts are cleared.
"""
from django.db import migrations

DESCRIPTION = ('Keeps your CRM up to date with what your agents do: AI SDR leads, the emails sent to them, the calls '
               'booked and their replies, and the mail Reply Draft reads from customers and leads, with the replies '
               'sent. HubSpot, Pipedrive or Salesforce.')
FEATURES = [
    'HubSpot, Pipedrive and Salesforce',
    'AI SDR leads as CRM contacts, never overwriting what you have',
    'Emails, calls and replies on each contact\'s timeline',
    'Moved and cancelled calls updated in the CRM',
    'Reply Draft: customer and lead mail, and the replies sent',
    'A queue that retries, and says what the CRM refused',
]


def forwards(apps, schema_editor):
    Agent = apps.get_model('core', 'Agent')
    Agent.objects.update_or_create(slug='crm_sync_agent', defaults={
        'name': 'CRM Sync', 'description': DESCRIPTION, 'features': FEATURES, 'is_purchasable': True,
        'is_active': True})
    for model in ('CRMSyncQueue', 'CRMSyncLog'):
        rows = apps.get_model('crm_sync_agent', model).objects.filter(error_message__contains='api_token=')
        rows.update(error_message='Pipedrive could not be reached. (The old error text was removed: it held the '
                                  'key. Make a new Pipedrive key if this company\'s was written here.)')


def backwards(apps, schema_editor):
    apps.get_model('core', 'Agent').objects.filter(slug='crm_sync_agent').update(is_purchasable=False)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0119_free_tokens_ten_million'),
        ('crm_sync_agent', '0005_waiting_skipped_inbox_meeting_ids'),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
