"""One row per Message-ID per ticket (FL-DATA-8).

Inbound mail was not idempotent: a provider that didn't see our 202 in time
redelivered, and for a new thread there was nothing to match on, so a second
ticket and a second copy of the message were created. The task now checks the
Message-ID first, and this constraint decides the race the check can't — two
deliveries in flight at the same moment.

Existing duplicates are cleared before the constraint goes on. The earliest row
of each group keeps its Message-ID (threading follows that one); later copies
have theirs blanked rather than deleted, because they hold real customer text
and blank ids are exempt from the constraint.
"""
from django.db import migrations, models


def blank_duplicate_message_ids(apps, schema_editor):
    TicketMessage = apps.get_model('Frontline_agent', 'TicketMessage')

    seen = set()
    duplicate_ids = []
    rows = (TicketMessage.objects
            .exclude(message_id='')
            .order_by('ticket_id', 'message_id', 'created_at', 'id')
            .values_list('id', 'ticket_id', 'message_id')
            .iterator())
    for row_id, ticket_id, message_id in rows:
        key = (ticket_id, message_id)
        if key in seen:
            duplicate_ids.append(row_id)
        else:
            seen.add(key)

    for start in range(0, len(duplicate_ids), 500):
        TicketMessage.objects.filter(id__in=duplicate_ids[start:start + 500]).update(message_id='')


class Migration(migrations.Migration):

    dependencies = [
        ('Frontline_agent', '0043_shorten_message_id_for_mysql_index'),
    ]

    operations = [
        migrations.RunPython(blank_duplicate_message_ids, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='ticketmessage',
            constraint=models.UniqueConstraint(
                condition=models.Q(('message_id', ''), _negated=True),
                fields=('ticket', 'message_id'),
                name='fl_ticketmessage_unique_message_id_per_ticket',
            ),
        ),
    ]
