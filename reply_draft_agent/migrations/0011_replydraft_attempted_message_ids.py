from django.db import migrations, models


def copy_attempted_id_forward(apps, schema_editor):
    """Carry any value in the old singular field over into the new plural
    field so existing failed drafts continue to suppress their Gmail
    Sent-folder shadow copies after the upgrade."""
    ReplyDraft = apps.get_model('reply_draft_agent', 'ReplyDraft')
    for d in ReplyDraft.objects.exclude(attempted_message_id='').only('id', 'attempted_message_id'):
        d.attempted_message_ids = d.attempted_message_id
        d.save(update_fields=['attempted_message_ids'])


def reverse_noop(apps, schema_editor):
    # No reverse needed — the old field stays around (we don't drop it
    # in this migration) and re-running migrate forward is idempotent.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('reply_draft_agent', '0010_replydraft_attempted_message_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='replydraft',
            name='attempted_message_ids',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.RunPython(copy_attempted_id_forward, reverse_noop),
    ]
