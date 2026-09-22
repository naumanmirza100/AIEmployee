"""Database-level guards behind the ticket state machine (FL-DATA-17).

`choices` is enforced only by `full_clean()`, which none of the write paths
call, so any writer that skipped `_validate_ticket_transition` — a workflow
step, a data fix, a future endpoint — could store any string it liked. Same
for a CSAT rating outside 1–5 and a negative paused-seconds counter.

Existing rows are coerced to a valid value first: a constraint added over bad
data fails the migration halfway through a deploy, which is a worse outcome
than the bad data. Anything coerced is logged with its id so it can be
reviewed afterwards.
"""
import logging

from django.db import migrations, models

logger = logging.getLogger(__name__)

# Spelled out rather than imported from the model: a migration has to keep
# working even when the model's constants are renamed or removed later.
TICKET_STATUS_VALUES = ('new', 'open', 'in_progress', 'resolved', 'closed', 'auto_resolved')
TICKET_PRIORITY_VALUES = ('low', 'medium', 'high', 'urgent')
TICKET_CATEGORY_VALUES = ('technical', 'billing', 'account', 'feature_request', 'bug',
                          'knowledge_gap', 'other')
TICKET_HANDOFF_STATUS_VALUES = ('none', 'pending', 'accepted', 'resolved')


def coerce_invalid_rows(apps, schema_editor):
    Ticket = apps.get_model('Frontline_agent', 'Ticket')
    TicketSatisfaction = apps.get_model('Frontline_agent', 'TicketSatisfaction')

    for field, valid_values, fallback in (
        ('status', TICKET_STATUS_VALUES, 'open'),
        ('priority', TICKET_PRIORITY_VALUES, 'medium'),
        ('category', TICKET_CATEGORY_VALUES, 'other'),
        ('handoff_status', TICKET_HANDOFF_STATUS_VALUES, 'none'),
    ):
        bad = Ticket.objects.exclude(**{f'{field}__in': valid_values})
        bad_ids = list(bad.values_list('id', flat=True)[:500])
        if bad_ids:
            logger.warning("0045: coercing %s on %d ticket(s) to %r: ids=%s",
                           field, len(bad_ids), fallback, bad_ids)
            bad.update(**{field: fallback})

    negative = Ticket.objects.filter(sla_paused_accumulated_seconds__lt=0)
    if negative.exists():
        logger.warning("0045: clamping negative sla_paused_accumulated_seconds on %d ticket(s)",
                       negative.count())
        negative.update(sla_paused_accumulated_seconds=0)

    out_of_range = TicketSatisfaction.objects.filter(rating__isnull=False).exclude(
        rating__gte=1, rating__lte=5)
    if out_of_range.exists():
        logger.warning("0045: clearing %d out-of-range CSAT rating(s)", out_of_range.count())
        out_of_range.update(rating=None)


class Migration(migrations.Migration):

    dependencies = [
        ('Frontline_agent', '0044_ticketmessage_unique_message_id'),
    ]

    operations = [
        migrations.RunPython(coerce_invalid_rows, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='ticket',
            constraint=models.CheckConstraint(
                check=models.Q(status__in=TICKET_STATUS_VALUES),
                name='fl_ticket_status_valid'),
        ),
        migrations.AddConstraint(
            model_name='ticket',
            constraint=models.CheckConstraint(
                check=models.Q(priority__in=TICKET_PRIORITY_VALUES),
                name='fl_ticket_priority_valid'),
        ),
        migrations.AddConstraint(
            model_name='ticket',
            constraint=models.CheckConstraint(
                check=models.Q(category__in=TICKET_CATEGORY_VALUES),
                name='fl_ticket_category_valid'),
        ),
        migrations.AddConstraint(
            model_name='ticket',
            constraint=models.CheckConstraint(
                check=models.Q(handoff_status__in=TICKET_HANDOFF_STATUS_VALUES),
                name='fl_ticket_handoff_status_valid'),
        ),
        migrations.AddConstraint(
            model_name='ticket',
            constraint=models.CheckConstraint(
                check=(models.Q(sla_paused_accumulated_seconds__isnull=True)
                       | models.Q(sla_paused_accumulated_seconds__gte=0)),
                name='fl_ticket_paused_seconds_non_negative'),
        ),
        migrations.AddConstraint(
            model_name='ticketsatisfaction',
            constraint=models.CheckConstraint(
                check=(models.Q(rating__isnull=True)
                       | models.Q(rating__gte=1, rating__lte=5)),
                name='fl_csat_rating_between_1_and_5'),
        ),
    ]
