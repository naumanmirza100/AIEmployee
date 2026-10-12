# A sequence's sending mailbox used to be saved as a bare number from the form,
# without checking whose mailbox it was. The sender now refuses a mailbox that is
# not the campaign owner's own (EmailSequence.get_sending_account), so a row like
# that is already harmless. This clears them, so the screen stops showing another
# login's address beside the sequence. Safe to run again; reversing is a no-op.

import logging

from django.db import migrations
from django.db.models import F

logger = logging.getLogger(__name__)


def clear_borrowed_mailboxes(apps, schema_editor):
    EmailSequence = apps.get_model('marketing_agent', 'EmailSequence')
    borrowed = list(
        EmailSequence._base_manager
        .exclude(email_account=None)
        .exclude(email_account__owner_id=F('campaign__owner_id'))
        .values_list('id', flat=True)
    )
    if borrowed:
        logger.warning('Marketing sequences %s named a sending mailbox that is not their campaign owner\'s. '
                       'Cleared: they now send from the campaign\'s own mailbox.', borrowed)
        EmailSequence._base_manager.filter(id__in=borrowed).update(email_account=None)


class Migration(migrations.Migration):

    dependencies = [
        ('marketing_agent', '0039_one_user_record_per_login'),
    ]

    operations = [
        migrations.RunPython(clear_borrowed_mailboxes, migrations.RunPython.noop),
    ]
